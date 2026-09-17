"""Build, reverify, and optionally publish one explicit repository-metrics run."""
from __future__ import annotations
from pipeline.preprocessing.common.paths import REPO_ROOT

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import uuid

import duckdb

from pipeline.preprocessing.curated.storage import put_immutable, read_optional, writer_lock
from pipeline.preprocessing.repository_metrics.policy import canonical_bytes, policy_document, policy_sha256

ROOT = REPO_ROOT
DATASET = "repository-metrics"
PREFIX = "depsdev/v1/repository-metrics"
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$")


def sha_file(path):
    checksum = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def code_sha256():
    paths = list(Path(__file__).parent.glob("*.py"))
    paths += [ROOT / p for p in (
        "pipeline/preprocessing/curated/repository.py", "pipeline/preprocessing/curated/storage.py",
        "pipeline/preprocessing/curated/build.py", "pipeline/minio/ingest_raw.py",
        "pipeline/postgresql/input.py", "pipeline/preprocessing/common/curated_input.py", "pipeline/preprocessing/snapshot/policy.py",
        "pipeline/preprocessing/snapshot/projects.py", "pipeline/preprocessing/snapshot/input.py", "pipeline/preprocessing/snapshot/build.py")]
    checksum = hashlib.sha256()
    for path in sorted(p for p in paths if not p.name.startswith("test_")):
        checksum.update(path.relative_to(ROOT).as_posix().encode() + b"\0")
        checksum.update(path.read_bytes() + b"\0")
    return checksum.hexdigest()


def write_json(path, value):
    """Publish complete bytes atomically without replacing an existing file."""
    path = Path(path)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.pending")
    try:
        with temporary.open("xb") as stream:
            stream.write(canonical_bytes(value))
            stream.flush()
            os.fsync(stream.fileno())
        # Same-directory hard linking is atomic and fails if the target exists.
        os.link(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _contained(root, text):
    if not isinstance(text, str) or not text or "\\" in text:
        raise ValueError("Invalid manifest path")
    relative = Path(text)
    if relative.is_absolute() or any(p in ("", ".", "..") for p in text.split("/")):
        raise ValueError("Invalid manifest path")
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Manifest path escapes run directory")
    return path


def inventory_outputs(run_dir, output, expected_counts):
    """Read every produced Parquet again; retain schemas and exact file hashes."""
    records, actual_counts = [], {}
    with duckdb.connect(":memory:") as con:
        con.execute("SET threads=2")
        for group, expected in sorted(expected_counts.items()):
            folder = _contained(output, group)
            files = sorted(folder.rglob("*.parquet"))
            if not files:
                raise ValueError(f"Missing output Parquet: {group}")
            total = 0
            group_schema = None
            for path in files:
                if not path.resolve().is_relative_to(output.resolve()):
                    raise ValueError("Output file escapes run directory")
                count = con.execute("SELECT count(*) FROM read_parquet(?,hive_partitioning=false)",
                                    [str(path)]).fetchone()[0]
                schema = [list(row[:2]) for row in con.execute(
                    "DESCRIBE SELECT * FROM read_parquet(?,hive_partitioning=false)", [str(path)]).fetchall()]
                if group_schema is not None and schema != group_schema:
                    raise ValueError(f"Output schema drift: {group}")
                group_schema = schema
                records.append({"path": path.relative_to(run_dir).as_posix(), "dataset": group,
                                "bytes": path.stat().st_size, "sha256": sha_file(path),
                                "rows": count, "schema": schema})
                total += count
            if type(expected) is not int or total != expected:
                raise ValueError(f"Output count mismatch: {group}")
            actual_counts[group] = total
    listed = {r["path"] for r in records}
    physical = {p.relative_to(run_dir).as_posix() for p in output.rglob("*.parquet")}
    if physical != listed:
        raise ValueError("Unlisted output Parquet")
    return records, actual_counts


def verify_completed(run_dir, *, require_marker=True):
    run_dir = Path(run_dir).resolve()
    body = (run_dir / "run_manifest.json").read_bytes()
    manifest = json.loads(body)
    if require_marker:
        marker = json.loads((run_dir / "_SUCCESS").read_bytes())
        if marker != {"manifest_sha256": hashlib.sha256(body).hexdigest()}:
            raise ValueError("Completion marker hash mismatch")
    if manifest.get("dataset") != DATASET or manifest.get("status") != "PASSED":
        raise ValueError("Unapproved repository metrics manifest")
    output = _contained(run_dir, manifest["output_path"])
    records, counts = inventory_outputs(run_dir, output, manifest["report"]["output_counts"])
    if records != manifest["files"] or counts != manifest["report"]["output_counts"]:
        raise ValueError("Completed outputs changed")
    return manifest, body


def publish_run(s3, run_dir):
    """Publish this dataset only, verifying all remote bytes before the marker."""
    manifest, body = verify_completed(run_dir)
    run_dir = Path(run_dir).resolve()
    if not RUN_ID.fullmatch(manifest["run_id"]):
        raise ValueError("Invalid run ID")
    prefix = f'{PREFIX}/snapshot={manifest["snapshot"]}/run_id={manifest["run_id"]}'
    bucket = "pickage-curated"
    marker_body = canonical_bytes({"manifest_sha256": hashlib.sha256(body).hexdigest()})
    with writer_lock(s3, bucket, prefix + "/_writer.lock", uuid.uuid4().hex):
        prior = read_optional(s3, bucket, prefix + "/_SUCCESS")
        if prior is not None:
            remote_manifest = read_optional(s3, bucket, prefix + "/run_manifest.json")
            if prior[0] != marker_body or remote_manifest is None or remote_manifest[0] != body:
                raise ValueError("Existing remote run differs")
        for record in manifest["files"]:
            key = prefix + "/" + record["path"]
            if prior is None:
                put_immutable(s3, bucket, key, _contained(run_dir, record["path"]).read_bytes())
            found = read_optional(s3, bucket, key)
            if found is None or len(found[0]) != record["bytes"] or hashlib.sha256(found[0]).hexdigest() != record["sha256"]:
                raise ValueError("Remote output verification failed")
        # The local manifest includes full input lineage and the code/policy hashes.
        put_immutable(s3, bucket, prefix + "/run_manifest.json", body)
        put_immutable(s3, bucket, prefix + "/_SUCCESS", marker_body)
    return {"status": "PUBLISHED", "action": "REVERIFIED" if prior else "PUBLISHED",
            "bucket": bucket, "prefix": prefix, "verification": "GET_SHA256_ALL_FILES",
            "manifest_sha256": hashlib.sha256(body).hexdigest()}


def run(s3, *, snapshot, curated_run_id, curated_outputs, versions_dir, projects_dir,
        candidate_path, run_id, work_dir, threads=2, driver_memory="4g", publish=False,
        spark=None, engine="native"):
    from pipeline.preprocessing.repository_metrics.input import prepare_inputs, reverify_inputs
    from pipeline.preprocessing.repository_metrics.runtime import create_spark
    from pipeline.preprocessing.repository_metrics.transform import transform
    if not RUN_ID.fullmatch(run_id):
        raise ValueError("Invalid run ID")
    work_dir = Path(work_dir).resolve()
    for source in (curated_outputs, versions_dir, projects_dir, Path(candidate_path).parent):
        source = Path(source).resolve()
        if work_dir == source or work_dir.is_relative_to(source) or source.is_relative_to(work_dir):
            raise ValueError("Work directory overlaps input")
    run_dir = work_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    lock = run_dir / ".writer.lock"
    with lock.open("x") as stream:
        stream.write(uuid.uuid4().hex)
    attempt_dir = run_dir / "attempts" / uuid.uuid4().hex
    report = {"run_id": run_id, "status": "RUNNING", "phase": "INPUT",
              "started_at": datetime.now(timezone.utc).isoformat()}
    owned_spark = False
    try:
        attempt_dir.mkdir(parents=True, exist_ok=False)
        inputs = prepare_inputs(s3, snapshot=snapshot, curated_run_id=curated_run_id,
                                curated_outputs=Path(curated_outputs), versions_dir=Path(versions_dir),
                                projects_dir=Path(projects_dir), candidate_path=Path(candidate_path),
                                output=attempt_dir / "input-manifest.json")
        identity = {"input_sha256": hashlib.sha256(canonical_bytes(inputs)).hexdigest(),
                    "code_sha256": code_sha256(), "policy_sha256": policy_sha256()}
        request_path = run_dir / "request.json"
        if request_path.exists():
            if json.loads(request_path.read_bytes()) != identity:
                raise ValueError("Run ID already belongs to a different input or contract")
        else:
            write_json(request_path, identity)
        if (run_dir / "run_manifest.json").exists():
            has_marker = (run_dir / "_SUCCESS").exists()
            manifest, body = verify_completed(run_dir, require_marker=has_marker)
            if manifest["request"] != identity:
                raise ValueError("Completed run request mismatch")
            reverify_inputs(inputs, s3=s3)
            if not has_marker:
                write_json(run_dir / "_SUCCESS", {"manifest_sha256": hashlib.sha256(body).hexdigest()})
            report.update(status="REVERIFIED", action="REVERIFIED", manifest=str(run_dir / "run_manifest.json"))
        else:
            report["phase"] = "TRANSFORM"
            if engine == "docker" and spark is None:
                from pipeline.preprocessing.repository_metrics.docker_runtime import transform_docker
                result = transform_docker(inputs, attempt_dir / "outputs", threads=threads,
                                          driver_memory=driver_memory)
                runtime_info = result.pop("runtime")
            elif engine == "native" or spark is not None:
                if spark is None:
                    spark = create_spark(attempt_dir / "runtime", threads=threads, driver_memory=driver_memory)
                    owned_spark = True
                result = transform(spark, inputs, attempt_dir / "outputs")
                runtime_info = {"engine": "native", "spark": spark.version, "python": sys.version.split()[0]}
            else:
                raise ValueError("Unsupported execution engine")
            report["phase"] = "VERIFY"
            files, _ = inventory_outputs(run_dir, attempt_dir / "outputs", result["output_counts"])
            reverify_inputs(inputs, s3=s3)
            if code_sha256() != identity["code_sha256"]:
                raise ValueError("Implementation changed during run")
            manifest = {"format_version": 1, "dataset": DATASET, "status": "PASSED",
                        "run_id": run_id, "snapshot": snapshot,
                        "snapshot_timestamp": inputs["snapshot_timestamp"], "request": identity,
                        "policy": policy_document(), "input": inputs,
                        "runtime": runtime_info,
                        "output_path": (attempt_dir / "outputs").relative_to(run_dir).as_posix(),
                        "files": files, "report": result,
                        "verification": "LOCAL_SHA256_PARQUET_RECONCILIATION"}
            manifest_path = run_dir / "run_manifest.json"
            if manifest_path.exists():
                raise ValueError("Unfinished run has a prepared manifest; use a new run ID")
            write_json(manifest_path, manifest)
            write_json(run_dir / "_SUCCESS", {"manifest_sha256": sha_file(manifest_path)})
            report.update(status="PASSED", action="BUILT", manifest=str(manifest_path),
                          output_counts=result["output_counts"])
        if publish:
            report["phase"] = "PUBLISH"
            report["publication"] = publish_run(s3, run_dir)
        report["phase"] = "COMPLETE"
        return report
    except BaseException as error:
        report.update(status="FAILED", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        if attempt_dir.exists():
            write_json(attempt_dir / "execution-report.json", report)
        try:
            if owned_spark:
                spark.stop()
        finally:
            lock.unlink()


def client_from_env(path, endpoint):
    """Read an explicitly selected MinIO config without printing credentials."""
    import boto3
    from botocore.config import Config
    values = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return boto3.client("s3", endpoint_url=endpoint,
                        aws_access_key_id=values["MINIO_ROOT_USER"],
                        aws_secret_access_key=values["MINIO_ROOT_PASSWORD"],
                        region_name="us-east-1", config=Config(connect_timeout=5, read_timeout=60,
                        retries={"mode": "standard", "max_attempts": 2}, s3={"addressing_style": "path"}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("snapshot", "curated-run-id", "run-id"):
        parser.add_argument("--" + flag, required=True)
    for flag in ("curated-outputs", "versions-dir", "projects-dir", "candidate-path", "minio-env"):
        parser.add_argument("--" + flag, type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, default=ROOT / "data/repository-metrics")
    parser.add_argument("--minio-endpoint", default="http://localhost:9000")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--driver-memory", default="4g")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--engine", choices=("native", "docker"), default="native")
    args = vars(parser.parse_args())
    s3 = client_from_env(args.pop("minio_env"), args.pop("minio_endpoint"))
    print(json.dumps(run(s3, **args), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
