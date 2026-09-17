"""Create a tiny, local-only native metadata bundle for selector tests."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import duckdb

from pipeline.preprocessing.package_snapshot.quality_schema import LEGACY_OBSERVED_SCHEMA
from pipeline.preprocessing.curated.storage import json_bytes

SNAPSHOT = "2026-08-31"
RUN_ID = "tiny-native-demo"
SNAPSHOT_TIMESTAMP = "2026-08-31T12:34:56.123456Z"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_parquet(path: Path, sql: str) -> int:
    with duckdb.connect(database=":memory:") as con:
        con.execute("SET threads=1")
        con.execute("SET memory_limit='128MB'")
        con.execute("SET max_temp_directory_size='0B'")
        con.execute(sql)
        count = con.execute("SELECT count(*) FROM source").fetchone()[0]
        con.execute("COPY source TO ? (FORMAT PARQUET)", [str(path)])
    return count


def _quality_sql() -> str:
    columns = ",".join(f'"{name}" {kind}' for name, kind in LEGACY_OBSERVED_SCHEMA)
    values = ",".join("NULL" for _ in LEGACY_OBSERVED_SCHEMA)
    # Keep values deliberately unapproved: this file exists to exercise metadata selection.
    return f"CREATE TABLE source ({columns}); INSERT INTO source VALUES ({values}), ({values})"


def create_demo(root: Path, dataset: str = "package-version") -> Path:
    """Create a fresh demo bundle and return its directory.

    The returned directory contains only local files and metadata.  Existing directories
    are rejected to make accidental fixture replacement visible.
    """
    root = Path(root)
    if dataset not in ("package-version", "package-snapshot-observed"):
        raise ValueError("dataset must be package-version or package-snapshot-observed")
    root.mkdir(parents=True, exist_ok=False)

    prefix_dataset = "package-version" if dataset == "package-version" else "package-snapshot"
    prefix = f"depsdev/v1/{prefix_dataset}/snapshot={SNAPSHOT}/run_id={RUN_ID}"
    files_dir = root / "files"
    files_dir.mkdir()
    records = []
    if dataset == "package-version":
        specs = {
            "package": "CREATE TABLE source (package_id INTEGER, name VARCHAR, repo_url VARCHAR); INSERT INTO source VALUES (1,'alpha','https://example.invalid/a'),(2,'beta',NULL)",
            "version": "CREATE TABLE source (version VARCHAR, package_id INTEGER, published_at TIMESTAMP, ordinal BIGINT, description VARCHAR, licenses JSON, deprecated VARCHAR, dependency JSON); INSERT INTO source VALUES ('1.0.0',1,TIMESTAMP '2026-08-30 01:02:03.123456',0,NULL,NULL,NULL,'{\"dependencies\":{},\"peerDependencies\":{},\"optionalDependencies\":{}}'),('1.0.0',2,TIMESTAMP '2026-08-30 01:02:03.123456',0,NULL,NULL,NULL,'{\"dependencies\":{},\"peerDependencies\":{},\"optionalDependencies\":{}}')",
        }
        for role, sql in specs.items():
            path = files_dir / f"{role}.parquet"
            rows = _write_parquet(path, sql)
            records.append({"key": f"{prefix}/attempts/a1/{role}/data/{path.name}", "bytes": path.stat().st_size, "sha256": _sha(path), "row_count": rows})
        manifest = {"contract_version": 1, "status": "PASSED", "verification": "GET_SHA256_ALL_FILES", "request": {"snapshot": SNAPSHOT, "run_id": RUN_ID}, "report": {"snapshot_timestamp": SNAPSHOT_TIMESTAMP[:-1], "output_counts": {"package/data": 2, "version/data": 2}}, "files": records, "synthetic_demo": True}
        counts = {"package": 2, "version": 2}
        sample_records = records
    else:
        specs = {
            "package_snapshot": "CREATE TABLE source (package_id INTEGER, snapshot_at DATE, downloads BIGINT, stars INTEGER, open_issues INTEGER); INSERT INTO source VALUES (1,DATE '2026-08-31',NULL,NULL,NULL),(2,DATE '2026-08-31',NULL,NULL,NULL)",
            "package_identity": "CREATE TABLE source (package_id INTEGER, name VARCHAR); INSERT INTO source VALUES (1,'alpha'),(2,'beta')",
            "quality": _quality_sql(),
        }
        for role, sql in specs.items():
            path = files_dir / f"{role}.parquet"
            rows = _write_parquet(path, sql)
            records.append({"path": path.name, "role": role, "bytes": path.stat().st_size, "sha256": _sha(path), "row_count": rows})
        interval = {"snapshot_at": SNAPSHOT, "snapshot_timestamp": SNAPSHOT_TIMESTAMP}
        input_manifest = {"interval": interval}
        manifest = {"dataset": "package-snapshot", "status": "PASSED", "format_version": 1, "snapshot": SNAPSHOT, "run_id": RUN_ID, "snapshot_timestamp": SNAPSHOT_TIMESTAMP, "interval": interval, "input_manifest": input_manifest, "input_manifest_sha256": hashlib.sha256(json_bytes(input_manifest)).hexdigest(), "policy": {}, "policy_sha256": hashlib.sha256(json_bytes({})).hexdigest(), "contract_sha256": "a" * 64, "counts": {"package_snapshot": 2}, "required_remote_verification": "GET_SHA256_ALL_FILES", "files": records, "synthetic_demo": True}
        counts = {"package_snapshot": 2}
        sample_records = [r for r in records if r["role"] in ("package_snapshot", "package_identity")]

    manifest_path = root / "run_manifest.json"
    manifest_path.write_bytes(json_bytes(manifest))
    manifest_sha = _sha(manifest_path)
    (root / "_SUCCESS").write_bytes((manifest_sha + "\n").encode() if dataset != "package-version" else json_bytes({"manifest_sha256": manifest_sha}))
    if dataset == "package-snapshot-observed":
        (root / "_INPUT.json").write_bytes(json_bytes({"manifest_sha256": manifest_sha}))
    objects = {prefix + "/run_manifest.json": "run_manifest.json", prefix + "/_SUCCESS": "_SUCCESS"}
    if dataset == "package-snapshot-observed":
        objects[prefix + "/_INPUT.json"] = "_INPUT.json"
    def sample_binding(record):
        filename = record.get("path") or record["key"].split("/")[-1]
        return {"key": record.get("key") or f"{prefix}/data/{filename}", "path": f"files/{filename}"}
    samples = [sample_binding(record) for record in sample_records]
    request = {"format_version": 1, "kind": "native_metadata_bundle", "dataset": dataset, "snapshot": SNAPSHOT, "run_id": RUN_ID, "snapshot_timestamp": SNAPSHOT_TIMESTAMP, "manifest_sha256": manifest_sha, "expected_counts": counts, "objects": objects, "samples": samples}
    (root / "request.json").write_bytes(json_bytes(request))
    return root


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dataset", default="package-version", choices=("package-version", "package-snapshot-observed"))
    args = parser.parse_args()
    create_demo(args.output, args.dataset)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
