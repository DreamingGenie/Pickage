"""Immutable lifecycle runner for requirements-resolution (07)."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
from datetime import datetime, timezone
import argparse
import copy

import duckdb

from pipeline.curated.storage import put_immutable, read_optional, writer_lock, _verify_remote
from . import bridge as bridge_module
from . import runtime as runtime_module
from .input import prepare_inputs, reverify_inputs
from .policy import canonical_bytes, validate_policy

RUN_ID = re.compile(r"^[A-Za-z0-9_-]+$")
BUCKET = "pickage-curated"
PREFIX = "depsdev/v1/requirements-resolution"


def _io_path(path: Path) -> Path:
    """Windows Python/DuckDB need extended syntax beyond MAX_PATH."""
    value = str(path.absolute())
    if os.name == "nt" and not value.startswith("\\\\?\\"):
        value = "\\\\?\\UNC\\" + value[2:] if value.startswith("\\\\") else "\\\\?\\" + value
    return Path(value)


def _hash_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with _io_path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
            size += len(block)
    return size, digest.hexdigest()


def _code_fingerprint() -> str:
    root = Path(__file__).resolve().parent
    repo = root.parents[1]
    paths = sorted(p for p in root.glob("*") if p.suffix in {".py", ".cjs"} and not p.name.startswith("test_"))
    paths += [Path(__file__).parents[1] / "curated" / name for name in ("build.py", "storage.py", "transform.py", "repository.py")]
    paths += [Path(__file__).parents[1] / "postgresql" / "input.py", Path(__file__).parents[1] / "snapshot" / "policy.py"]
    paths += [Path(__file__).parents[1] / "minio" / "ingest_raw.py"]
    records = []
    for path in sorted(set(paths)):
        if not path.is_file():
            raise ValueError("required production source is missing: " + str(path))
        records.append((path.relative_to(repo).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()))
    return hashlib.sha256(canonical_bytes(records)).hexdigest()


def _runtime_identity(runtime):
    if runtime is None:
        runtime = bridge_module.discover_runtime()
    return dict(runtime)


def _runtime_metadata(runtime) -> dict:
    command = [runtime["node"], "--max-old-space-size=768",
               str(Path(__file__).with_name("semver_worker.cjs")),
               runtime["semver_module"], runtime["package_arg_module"]]
    try:
        completed = subprocess.run(command, input=canonical_bytes({"op": "metadata"}).decode(),
                                   text=True, capture_output=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError("Node runtime metadata probe failed") from error
    if completed.returncode != 0 or not completed.stdout.strip():
        raise ValueError("Node runtime metadata probe failed")
    try:
        reply = json.loads(completed.stdout.strip().splitlines()[-1])
    except json.JSONDecodeError as error:
        raise ValueError("Node runtime metadata was not JSON") from error
    if not isinstance(reply, dict) or reply.get("ok") is not True or not isinstance(reply.get("result"), dict):
        raise ValueError("Node runtime metadata contract failed")
    result = reply["result"]
    required = {"node_version", "semver_version", "package_arg_version", "semver_sha256", "package_arg_sha256", "dependency_closure_sha256", "options", "equal_precedence_tie"}
    hashes = ("semver_sha256", "package_arg_sha256", "dependency_closure_sha256")
    if (set(result) != required or result.get("equal_precedence_tie") != "original_version_utf16_ascending"
            or result.get("options") != {"loose": False, "includePrerelease": False}
            or any(not isinstance(result.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", result[key]) for key in hashes)
            or any(not isinstance(result.get(key), str) or not result[key] for key in ("node_version", "semver_version", "package_arg_version"))):
        raise ValueError("Node runtime metadata incomplete")
    return result


def _write_new(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(canonical_bytes(value))


def _output_inventory(root: Path) -> list[dict]:
    records = []
    for path in sorted(root.rglob("*.parquet")):
        if path.is_symlink():
            raise ValueError("symlinked output Parquet")
        size, digest = _hash_file(path)
        with duckdb.connect(config={"threads": 1, "memory_limit": "256MB"}) as con:
            rows = con.execute("SELECT sum(num_rows) FROM parquet_file_metadata(?)", [[str(_io_path(path))]]).fetchone()[0]
        records.append({"path": path.relative_to(root).as_posix(), "bytes": size, "sha256": digest, "rows": int(rows)})
    if not records:
        raise ValueError("finalize produced no Parquet outputs")
    return records


def _output_group_counts(root: Path) -> dict[str, int]:
    counts = {}
    for directory in sorted(p for p in root.iterdir() if p.is_dir()):
        total = 0
        for path in directory.rglob("*.parquet"):
            with duckdb.connect(config={"threads": 1, "memory_limit": "256MB"}) as con:
                total += int(con.execute("SELECT sum(num_rows) FROM parquet_file_metadata(?)", [[str(_io_path(path))]]).fetchone()[0])
        counts[directory.name] = total
    return counts


def _verify_stage_counts(root: Path, report: dict) -> None:
    expected = report.get("output_counts", {}) if isinstance(report, dict) else {}
    required = {"declaration_outcomes", "source_outcomes", "edges", "target_quality"}
    if not isinstance(expected, dict) or set(expected) != required:
        raise ValueError("finalize report output_counts missing")
    actual = _output_group_counts(root)
    if set(actual) != required or any(actual[key] < 0 for key in required):
        raise ValueError("finalize output groups incomplete")
    if any(not list((root / key).rglob("*.parquet")) for key in required):
        raise ValueError("finalize output group has no Parquet")
    for key, value in expected.items():
        if type(value) is not int or value < 0 or actual[key] != value:
            raise ValueError(f"finalize output count mismatch: {key}")
    status, ready = report.get("resolution_status"), report.get("ready_for_dependents")
    if status not in {"COMPLETE", "PARTIAL"} or type(ready) is not bool or (status == "COMPLETE") != ready:
        raise ValueError("finalize status/readiness mismatch")
    counts = tuple(report.get(key) for key in ("selected_declarations", "resolved_declarations", "unresolved_declarations"))
    if any(type(value) is not int or value < 0 for value in counts) or counts[1] + counts[2] != counts[0] or (status == "COMPLETE" and counts[2] != 0):
        raise ValueError("finalize declaration count mismatch")
    if expected["declaration_outcomes"] != counts[0] or actual["source_outcomes"] <= 0:
        raise ValueError("finalize source/declaration count mismatch")
    source_status = report.get("source_status_counts")
    declaration_status = report.get("declaration_status_counts")
    for values, total in ((source_status, actual["source_outcomes"]), (declaration_status, counts[0])):
        if (not isinstance(values, dict) or any(type(v) is not int or v < 0 for v in values.values())
                or sum(values.values()) != total):
            raise ValueError("finalize quality status counts mismatch")
    if declaration_status.get("RESOLVED", 0) != counts[1]:
        raise ValueError("finalize resolved status count mismatch")
    incomplete_sources = sum(value for key, value in source_status.items()
                             if key not in {"OBSERVED_NO_DEPENDENCIES", "RESOLVED"})
    if ready != (counts[2] == 0 and incomplete_sources == 0):
        raise ValueError("finalize coverage and readiness disagree")


def _verify_inventory(root: Path, records: list[dict]) -> None:
    root = _plain_root(root)
    names = [row.get("path") for row in records]
    if any(not isinstance(name, str) or not name or Path(name).is_absolute() or "\\" in name
           or any(part in ("", ".", "..") for part in Path(name).parts) for name in names) or len(set(names)) != len(names):
        raise ValueError("invalid or duplicate output record path")
    actual = {p.relative_to(root).as_posix(): p for p in root.rglob("*.parquet")}
    if set(actual) != {row["path"] for row in records}:
        raise ValueError("output file set changed")
    for row in records:
        path = actual[row["path"]]
        _plain_root(path)
        size, digest = _hash_file(path)
        if size != row["bytes"] or digest != row["sha256"]:
            raise ValueError("output file changed: " + row["path"])
        with duckdb.connect(config={"threads": 1, "memory_limit": "256MB"}) as con:
            rows = con.execute("SELECT sum(num_rows) FROM parquet_file_metadata(?)", [[str(_io_path(path))]]).fetchone()[0]
        if type(row.get("rows")) is not int or rows != row["rows"]:
            raise ValueError("output row metadata changed")


def _safe_output(root: Path, relative: str) -> Path:
    if (not isinstance(relative, str) or not relative or Path(relative).is_absolute() or "\\" in relative
            or ":" in relative or any(part in ("", ".", "..") for part in relative.split("/"))):
        raise ValueError("invalid final output path")
    path = _plain_root(root / relative)
    if not path.is_relative_to(root.resolve()) or any(parent.is_symlink() for parent in [path, *path.parents] if parent != root):
        raise ValueError("final output escapes run root")
    return path


def _plain_root(path: Path) -> Path:
    absolute = path.absolute()
    for item in (absolute, *absolute.parents):
        if item.is_symlink() or getattr(item, "is_junction", lambda: False)():
            raise ValueError("linked work/output path")
    return absolute.resolve()


def _completed(root: Path, request: dict, policy: dict, code: str, runtime_id: dict, runtime_metadata: dict, s3):
    marker = root / "_SUCCESS"
    manifest_path = root / "run_manifest.json"
    if marker.is_file() is False and manifest_path.is_file() is False:
        return None
    if marker.is_file() is False and manifest_path.is_file() is True:
        marker_missing = True
    elif marker.is_file() is True and manifest_path.is_file() is False:
        raise ValueError("incomplete completion marker state")
    else:
        marker_missing = False
    body = manifest_path.read_bytes()
    if not marker_missing:
        marker_value = json.loads(marker.read_bytes())
        if marker_value != {"manifest_sha256": hashlib.sha256(body).hexdigest()}:
            raise ValueError("completion marker hash mismatch")
    manifest = json.loads(body)
    if manifest.get("status") != "PASSED" or manifest.get("request") != request:
        raise ValueError("completed run request mismatch")
    if (manifest.get("code_sha256") != code or manifest.get("runtime_identity") != runtime_id
            or manifest.get("runtime_metadata") != runtime_metadata):
        raise ValueError("completed run code/runtime mismatch")
    if manifest.get("policy") != policy:
        raise ValueError("completed run policy mismatch")
    reverify_inputs(manifest["input"], s3)
    final_root = _safe_output(root, manifest["final_output"])
    _verify_inventory(final_root, manifest["files"])
    _verify_stage_counts(final_root, manifest["finalize_report"])
    _verify_manifest_status(manifest)
    if marker_missing:
        _write_new(marker, {"manifest_sha256": hashlib.sha256(body).hexdigest()})
    return manifest


def run(s3, *, snapshot, curated_run_id, curated_outputs, versions_dir, requirements_dir,
        run_id, work_dir, policy, runtime=None, publish=False, verify_only=False,
        threads=2, shuffle_partitions=32):
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        raise ValueError("Invalid run ID")
    if verify_only and publish:
        raise ValueError("--verify-only and --publish cannot be combined")
    validate_policy(policy)
    work_dir = _plain_root(Path(work_dir))
    roots = [_plain_root(Path(curated_outputs)), _plain_root(Path(versions_dir)), _plain_root(Path(requirements_dir))]
    if any(work_dir == root or work_dir.is_relative_to(root) or root.is_relative_to(work_dir) for root in roots):
        raise ValueError("Work directory overlaps or contains input roots")
    work_dir.mkdir(parents=True, exist_ok=True)
    run_root = _plain_root(work_dir / run_id)
    if not run_root.is_relative_to(work_dir):
        raise ValueError("Run output escapes work directory")
    if any(run_root == root or run_root.is_relative_to(root) or root.is_relative_to(run_root) for root in roots):
        raise ValueError("Run output overlaps input root")
    code = _code_fingerprint()
    runtime_id = _runtime_identity(runtime)
    runtime_metadata = _runtime_metadata(runtime_id)
    request = {"snapshot": snapshot, "curated_run_id": curated_run_id, "run_id": run_id,
               "sources": {"curated_outputs": str(roots[0]), "versions_dir": str(roots[1]), "requirements_dir": str(roots[2])},
               "policy_sha256": policy["sha256"], "spark_image": runtime_module.IMAGE,
               "threads": threads, "shuffle_partitions": shuffle_partitions}
    run_root.mkdir(exist_ok=True)
    lock = work_dir / ("." + run_id + ".lock")
    token = secrets.token_hex(16)
    try:
        with lock.open("xb") as stream:
            stream.write(canonical_bytes({"run_id": run_id, "token": token}))
        completed = _completed(run_root, request, policy, code, runtime_id, runtime_metadata, s3)
        if completed:
            if verify_only and publish:
                raise ValueError("--verify-only and --publish cannot be combined")
            if publish:
                _publish(s3, completed, run_root / completed["final_output"], snapshot, run_id)
            return {"status": completed["status"], "resolution_status": completed["resolution_status"],
                    "ready_for_dependents": completed["ready_for_dependents"], "reverified": True,
                    "manifest_sha256": hashlib.sha256((run_root / "run_manifest.json").read_bytes()).hexdigest(),
                    "path": str(run_root / "run_manifest.json")}
        if verify_only:
            raise ValueError("verify-only requires a completed run")
        attempt = _plain_root(run_root / "attempts" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
        attempt.mkdir(parents=True, exist_ok=False)
        phase = "prepare_inputs"
        prepared = prepare_inputs(s3, snapshot=snapshot, curated_run_id=curated_run_id,
                                  curated_outputs=roots[0], versions_dir=roots[1], requirements_dir=roots[2],
                                  output=attempt / "input-manifest.json")
        phase = "spark_prepare"
        stage_prepare = runtime_module.run_stage("prepare", prepared, policy, attempt / "prepare",
                                                 run_id=run_id, threads=threads, shuffle_partitions=shuffle_partitions)
        prepared_dir = attempt / "prepare" / "outputs"
        bridge_out = attempt / "bridge"
        phase = "bridge"
        bridge_report = bridge_module.resolve_prepared(prepared_dir, bridge_out, runtime_id, threads=threads)
        if bridge_report.get("runtime") != runtime_metadata:
            raise ValueError("Bridge runtime metadata differs from initial probe")
        phase = "spark_finalize"
        stage_finalize = runtime_module.run_stage("finalize", prepared, policy, attempt / "finalize",
                                                  prepared_dir=prepared_dir, bridge_dir=bridge_out,
                                                  run_id=run_id, threads=threads, shuffle_partitions=shuffle_partitions)
        phase = "reverify_inputs"
        reverify_inputs(prepared, s3)
        final_root = attempt / "finalize" / "outputs"
        phase = "output_inventory"
        _verify_stage_counts(final_root, stage_finalize)
        files = _output_inventory(final_root)
        if _code_fingerprint() != code or _runtime_metadata(runtime_id) != runtime_metadata:
            raise ValueError("Code/runtime changed during calculation")
        manifest = {"status": "PASSED", "resolution_status": stage_finalize.get("resolution_status", "PARTIAL"),
                    "ready_for_dependents": stage_finalize.get("ready_for_dependents", False),
                    "request": request, "input": prepared, "policy": policy,
                    "code_sha256": code, "runtime_identity": runtime_id,
                    "runtime_metadata": runtime_metadata,
                    "final_output": final_root.relative_to(run_root).as_posix(),
                    "prepare_report": stage_prepare, "bridge_report": bridge_report,
                    "finalize_report": stage_finalize, "files": files}
        body = canonical_bytes(manifest)
        phase = "publish_local_marker"
        _write_new(run_root / "run_manifest.json", manifest)
        _write_new(run_root / "_SUCCESS", {"manifest_sha256": hashlib.sha256(body).hexdigest()})
        if publish:
            if not manifest["ready_for_dependents"]:
                raise ValueError("Refusing to publish an incomplete resolution")
            _publish(s3, manifest, final_root, snapshot, run_id)
        return manifest
    except Exception as error:
        if "attempt" in locals():
            try:
                _write_new(attempt / "error.json", {"phase": phase, "error_code": type(error).__name__})
            except FileExistsError:
                pass
        raise
    finally:
        try:
            if lock.read_text(encoding="utf-8") == canonical_bytes({"run_id": run_id, "token": token}).decode():
                lock.unlink()
        except FileNotFoundError:
            pass


def _verify_manifest_status(manifest):
    report = manifest["finalize_report"]
    if (manifest.get("resolution_status") != report.get("resolution_status")
            or manifest.get("ready_for_dependents") != report.get("ready_for_dependents")
            or type(manifest.get("ready_for_dependents")) is not bool):
        raise ValueError("Manifest and finalize readiness disagree")


def _publish(s3, manifest, final_root: Path, snapshot: str, run_id: str):
    _verify_manifest_status(manifest)
    if manifest.get("ready_for_dependents") is not True:
        raise ValueError("Refusing to publish an incomplete resolution")
    prefix = f"{PREFIX}/snapshot={snapshot}/run_id={run_id}"
    _verify_stage_counts(final_root, manifest["finalize_report"])
    _verify_inventory(final_root, manifest["files"])
    receipt = copy.deepcopy(manifest)
    receipt["request"]["sources"] = {key: "local-input" for key in receipt["request"].get("sources", {})}
    receipt["input"].pop("files", None)
    receipt["input"].pop("file_records", None)
    receipt["input"].pop("metadata_records", None)
    receipt["input"].pop("sources", None)
    receipt["final_output"] = "data"
    receipt.pop("runtime_identity", None)
    body = canonical_bytes(receipt)
    marker_body = canonical_bytes({"manifest_sha256": hashlib.sha256(body).hexdigest()})
    with writer_lock(s3, BUCKET, PREFIX + "/_writer.lock", run_id):
        existing_manifest = read_optional(s3, BUCKET, prefix + "/run_manifest.json")
        existing_marker = read_optional(s3, BUCKET, prefix + "/_SUCCESS")
        if existing_manifest is None and existing_marker is not None:
            raise ValueError("remote publish has marker without manifest")
        if existing_manifest is not None:
            if existing_manifest[0] != body or (existing_marker is not None and existing_marker[0] != marker_body):
                raise ValueError("remote publish manifest differs")
        for record in manifest["files"]:
            path = final_root / record["path"]
            if record["bytes"] > 5 * 1024 * 1024 * 1024:
                raise ValueError("publish object exceeds 5 GiB limit")
            key = prefix + "/data/" + record["path"]
            # Conditional streaming PUT avoids loading a large shard into memory.
            try:
                with _io_path(path).open("rb") as stream:
                    s3.put_object(Bucket=BUCKET, Key=key, Body=stream,
                                  ContentLength=record["bytes"], IfNoneMatch="*")
            except Exception:
                # A retry/concurrent create is acceptable only for exact bytes.
                _verify_remote(s3, BUCKET, key, record["bytes"], record["sha256"])
            _verify_remote(s3, BUCKET, key, record["bytes"], record["sha256"])
        put_immutable(s3, BUCKET, prefix + "/run_manifest.json", body)
        _verify_remote(s3, BUCKET, prefix + "/run_manifest.json", len(body), hashlib.sha256(body).hexdigest())
        put_immutable(s3, BUCKET, prefix + "/_SUCCESS", marker_body)
        _verify_remote(s3, BUCKET, prefix + "/_SUCCESS", len(marker_body), hashlib.sha256(marker_body).hexdigest())


def _client_from_env(path: Path):
    import boto3
    from botocore.config import Config
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    required = ("MINIO_ROOT_USER", "MINIO_ROOT_PASSWORD")
    if any(key not in values for key in required):
        raise ValueError("MinIO env file lacks required credentials")
    return boto3.client("s3", endpoint_url=values.get("MINIO_ENDPOINT", "http://localhost:9000"),
                        aws_access_key_id=values["MINIO_ROOT_USER"],
                        aws_secret_access_key=values["MINIO_ROOT_PASSWORD"], region_name="us-east-1",
                        config=Config(retries={"mode": "standard", "max_attempts": 5}, s3={"addressing_style": "path"}))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("snapshot", "curated-run-id", "curated-outputs", "versions-dir", "requirements-dir", "run-id", "work-dir", "policy-file"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--minio-env", type=Path)
    parser.add_argument("--node")
    parser.add_argument("--semver-module")
    parser.add_argument("--package-arg-module")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--shuffle-partitions", type=int, default=32)
    args = parser.parse_args(argv)
    policy = json.loads(Path(args.policy_file).read_bytes())
    validate_policy(policy)
    if args.minio_env is None:
        raise ValueError("--minio-env is required")
    s3 = _client_from_env(args.minio_env)
    runtime = bridge_module.discover_runtime(args.node, args.semver_module, args.package_arg_module)
    result = run(s3, snapshot=args.snapshot, curated_run_id=args.curated_run_id,
                 curated_outputs=args.curated_outputs, versions_dir=args.versions_dir,
                 requirements_dir=args.requirements_dir, run_id=args.run_id,
                 work_dir=args.work_dir, policy=policy, runtime=runtime,
                 publish=args.publish, verify_only=args.verify_only,
                 threads=args.threads, shuffle_partitions=args.shuffle_partitions)
    compact = {key: result.get(key) for key in ("status", "resolution_status", "ready_for_dependents", "reverified", "output_counts", "manifest_sha256", "path") if key in result}
    print(json.dumps(compact, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


__all__ = ["run"]


if __name__ == "__main__":
    raise SystemExit(main())
