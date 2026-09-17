"""Build and publish package downloads for one approved snapshot interval."""
from __future__ import annotations
from pipeline.preprocessing.common.paths import REPO_ROOT

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
import uuid

import duckdb

from pipeline.downloads.bronze import publish
from pipeline.minio.ingest_raw import client
from pipeline.preprocessing.downloads_interval.aggregate import aggregate
from pipeline.preprocessing.downloads_interval.input import prepare, revalidate
from pipeline.preprocessing.downloads_interval.policy import policy_document, policy_sha256

ROOT = REPO_ROOT
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}")
OUTPUT_BUCKET = "pickage-curated"
OUTPUT_PREFIX = "npm-downloads-interval/v1"


def encoded(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def contract_sha256() -> str:
    paths = [p for p in Path(__file__).parent.glob("*.py") if not p.name.startswith("test_")]
    paths += [ROOT / name for name in (
        "pipeline/downloads/bronze.py", "pipeline/preprocessing/curated/storage.py", "pipeline/postgresql/input.py", "pipeline/preprocessing/common/curated_input.py",
        "pipeline/minio/ingest_raw.py", "pipeline/preprocessing/snapshot/input.py", "pipeline/preprocessing/snapshot/build.py",
        "pipeline/preprocessing/snapshot/policy.py", "pipeline/preprocessing/snapshot/projects.py")]
    digest = hashlib.sha256(b"npm-downloads-interval-v1\0")
    for path in sorted(paths):
        digest.update(path.relative_to(ROOT).as_posix().encode() + b"\0")
        digest.update(path.read_text(encoding="utf-8").encode() + b"\0")
    digest.update(duckdb.__version__.encode())
    return digest.hexdigest()


def write_report(path: Path, report: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def run(*, snapshot: str, bronze_run_id: str, bronze_manifest_sha256: str,
        curated_run_id: str, curated_manifest_sha256: str, candidate_path: Path,
        candidate_sha256: str, run_id: str, work_dir: Path, s3=None,
        verify_only: bool = False, workers: int = 4, memory_limit: str = "2GB",
        threads: int = 4, failpoint: str | None = None,
        additional_bronze_refs: list[dict] | None = None) -> dict:
    if not isinstance(run_id, str) or not SAFE_ID.fullmatch(run_id):
        raise ValueError("invalid interval run ID")
    if date.fromisoformat(snapshot).isoformat() != snapshot:
        raise ValueError("snapshot must be an ISO date")
    if type(workers) is not int or not 1 <= workers <= 16:
        raise ValueError("workers must be between 1 and 16")
    if type(threads) is not int or not 1 <= threads <= 16:
        raise ValueError("threads must be between 1 and 16")
    if not re.fullmatch(r"[1-9][0-9]*(?:MB|GB)", memory_limit):
        raise ValueError("memory limit must be a positive MB or GB value")
    work_dir = Path(work_dir).resolve()
    source = (ROOT / "data/raw").resolve()
    if work_dir == source or source in work_dir.parents:
        raise ValueError("execution artifacts must be outside the raw source directory")
    run_dir = work_dir / run_id
    if run_dir.is_symlink() or (run_dir.exists() and not run_dir.is_dir()):
        raise ValueError("run path must be a normal directory")
    if run_dir.resolve().parent != work_dir:
        raise ValueError("run path escapes the work directory")
    attempt = uuid.uuid4().hex
    attempt_dir = run_dir / attempt
    attempt_dir.mkdir(parents=True, exist_ok=False)
    report_path = attempt_dir / "execution_report.json"
    started = time.monotonic()
    report = {"dataset": "npm-downloads-interval", "run_id": run_id, "attempt_id": attempt,
              "snapshot_at": snapshot, "status": "PREPARING", "phase": "VALIDATE_INPUT",
              "mode": "VERIFY_ONLY" if verify_only else "PUBLISH_CURATED",
              "started_at": datetime.now(timezone.utc).isoformat(), "report_path": str(report_path)}
    write_report(report_path, report)
    try:
        contract_hash = contract_sha256()
        s3 = client() if s3 is None else s3
        inputs = prepare(s3, snapshot=snapshot, bronze_run_id=bronze_run_id,
                         bronze_manifest_sha256=bronze_manifest_sha256, curated_run_id=curated_run_id,
                         curated_manifest_sha256=curated_manifest_sha256, candidate_path=candidate_path,
                         candidate_sha256=candidate_sha256, cache_dir=attempt_dir / "inputs", workers=workers,
                         additional_bronze_refs=additional_bronze_refs)
        inputs["lineage"]["aggregation_policy_sha256"] = policy_sha256()
        input_body = encoded(inputs["input_manifest"])
        if hashlib.sha256(input_body).hexdigest() != inputs["input_manifest_sha256"]:
            raise ValueError("input manifest hash mismatch")
        (attempt_dir / "input-manifest.json").write_bytes(input_body)
        report.update(phase="AGGREGATE", interval=inputs["interval"],
                      input_manifest_sha256=inputs["input_manifest_sha256"])
        write_report(report_path, report)
        output_dir = attempt_dir / "output"
        output_dir.mkdir()
        result = aggregate(inputs, output_dir, memory_limit=memory_limit, threads=threads)
        if contract_sha256() != contract_hash:
            raise ValueError("implementation changed during aggregation")
        manifest = {"dataset": "npm-downloads-interval", "format_version": 1,
                    "run_id": run_id, "status": "PASSED", "interval": inputs["interval"],
                    "input_manifest": inputs["input_manifest"],
                    "input_manifest_sha256": inputs["input_manifest_sha256"],
                    "aggregation_policy": policy_document(), "aggregation_policy_sha256": policy_sha256(),
                    "contract_sha256": contract_hash, "duckdb_version": duckdb.__version__,
                    "files": result["files"], "quality": result["quality"],
                    "output_schema": result["schema"],
                    "required_remote_verification": "GET_SHA256_ALL_FILES"}
        manifest_body = encoded(manifest)
        manifest_path = attempt_dir / "run-manifest.json"
        manifest_path.write_bytes(manifest_body)
        report.update(manifest_path=str(manifest_path), output_dir=str(output_dir),
                      contract_sha256=contract_hash, aggregation_policy_sha256=policy_sha256(),
                      manifest_sha256=hashlib.sha256(manifest_body).hexdigest(), quality=result["quality"],
                      file_count=len(result["files"]))

        def before_commit():
            revalidate(s3, inputs)
            if contract_sha256() != contract_hash:
                raise ValueError("implementation changed during execution")

        before_commit()
        if verify_only:
            report.update(status="VERIFIED", action="VERIFIED_LOCAL")
        else:
            prefix = f"{OUTPUT_PREFIX}/snapshot={snapshot}/run_id={run_id}"
            report.update(phase="PUBLISH_CURATED", bucket=OUTPUT_BUCKET, prefix=prefix)
            write_report(report_path, report)
            result = publish(s3, bucket=OUTPUT_BUCKET, prefix=prefix, root=output_dir,
                             manifest=manifest, failpoint=failpoint, before_commit=before_commit)
            report.update(result)
        report["phase"] = "COMPLETE"
    except BaseException as error:
        report.update(status="FAILED", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        report.update(finished_at=datetime.now(timezone.utc).isoformat(),
                      elapsed_seconds=round(time.monotonic() - started, 3))
        write_report(report_path, report)
        print(f"{report['status']}: {report_path}", flush=True)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--bronze-run-id", required=True)
    parser.add_argument("--bronze-manifest-sha256", required=True)
    parser.add_argument("--curated-run-id", required=True)
    parser.add_argument("--curated-manifest-sha256", required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--candidate-sha256", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--work-dir", type=Path, default=ROOT / "data/downloads_interval/executions")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--memory-limit", default="2GB")
    parser.add_argument("--threads", type=int, default=4)
    args = vars(parser.parse_args())
    args["candidate_path"] = args.pop("candidate")
    try:
        run(**args)
    except Exception as error:
        print(f"Interval load failed ({type(error).__name__}); see execution report", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
