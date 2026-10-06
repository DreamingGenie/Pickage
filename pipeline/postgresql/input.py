"""Select and validate an immutable Curated package/version run.

This module stops before PostgreSQL. It creates escaped COPY TEXT shards
that the loader can stream into staging tables.
"""
from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import re

import duckdb

from pipeline.preprocessing.curated.storage import download_files, read_optional
from pipeline.preprocessing.common.curated_input import schema as _shared_schema
from pipeline.preprocessing.common.curated_input import sql_path as _shared_sql_path
from pipeline.preprocessing.common.curated_input import sql_paths as _shared_sql_paths
from pipeline.preprocessing.common.curated_input import SCHEMAS as _CURATED_SCHEMAS


CURATED_BUCKET = "pickage-curated"
PREFIX = "depsdev/v1/package-version"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RUN_ID = re.compile(r"^[A-Za-z0-9_-]+$")

DEFAULT_DEPENDENCY = {
    "dependencies": {},
    "peerDependencies": {},
    "optionalDependencies": {},
}
DEFAULT_DEPENDENCY_JSON = json.dumps(DEFAULT_DEPENDENCY, ensure_ascii=False, separators=(",", ":"))

_SCHEMAS = _CURATED_SCHEMAS


def _sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _read(s3, bucket: str, key: str) -> bytes:
    found = read_optional(s3, bucket, key)
    if found is None:
        raise ValueError(f"Required object missing: {key}")
    return found[0]


def _records(manifest: dict, prefix: str) -> list[dict]:
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("Curated manifest has no files")
    seen = set()
    for row in files:
        if not isinstance(row, dict):
            raise ValueError("Malformed Curated file record")
        key, size, checksum = row.get("key"), row.get("bytes"), row.get("sha256")
        if (not isinstance(key, str) or not key.startswith(prefix + "/attempts/")
                or key in seen or type(size) is not int or size <= 0
                or not isinstance(checksum, str) or not _SHA256.fullmatch(checksum)
                or "\\" in key or "\x00" in key or not key.endswith(".parquet")
                or any(part in ("", ".", "..") for part in key.split("/"))):
            raise ValueError("Malformed Curated file record")
        seen.add(key)
    return files


def _service_records(files: list[dict], prefix: str) -> dict[str, list[dict]]:
    groups = {"package": [], "version": []}
    attempts = set()
    pattern = re.compile(re.escape(prefix) + r"/attempts/([^/]+)/(package|version)/data/([^/]+\.parquet)$")
    for record in files:
        relative = record["key"][len(prefix + "/attempts/"):]
        parts = relative.split("/")
        if len(parts) < 3 or not _RUN_ID.fullmatch(parts[0]):
            raise ValueError("Invalid canonical attempt path")
        attempts.add(parts[0])
        match = pattern.fullmatch(record["key"])
        if not match:
            if len(parts) > 2 and parts[1] in groups:
                raise ValueError("Invalid service file path")
            continue
        attempt, table, filename = match.groups()
        groups[table].append(record)
    if len(attempts) != 1 or any(not value for value in groups.values()):
        raise ValueError("Package/version service files must use one canonical attempt")
    return groups


def select_run(s3, snapshot: str, run_id: str) -> dict:
    """Return metadata for one explicitly requested, completed Curated run."""
    if date.fromisoformat(snapshot).isoformat() != snapshot:
        raise ValueError("snapshot must be an ISO date")
    if not _RUN_ID.fullmatch(run_id):
        raise ValueError("Invalid run ID")
    prefix = f"{PREFIX}/snapshot={snapshot}/run_id={run_id}"
    marker = _read(s3, CURATED_BUCKET, prefix + "/_SUCCESS")
    body = _read(s3, CURATED_BUCKET, prefix + "/run_manifest.json")
    try:
        marker_json, manifest = json.loads(marker), json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Invalid completion or manifest JSON") from error
    digest = _sha(body)
    if marker_json != {"manifest_sha256": digest}:
        raise ValueError("Curated completion marker hash mismatch")
    if (not isinstance(manifest, dict) or type(manifest.get("contract_version")) is not int
            or manifest.get("contract_version") != 1 or manifest.get("status") != "PASSED"
            or manifest.get("verification") != "GET_SHA256_ALL_FILES"):
        raise ValueError("Unapproved Curated manifest")
    request = manifest.get("request")
    if (not isinstance(request, dict) or request.get("snapshot") != snapshot
            or request.get("run_id") != run_id):
        raise ValueError("Curated manifest request mismatch")
    files = _records(manifest, prefix)
    grouped = _service_records(files, prefix)
    report = manifest.get("report")
    counts = report.get("output_counts") if isinstance(report, dict) else None
    if not isinstance(counts, dict):
        raise ValueError("Curated report counts missing")
    expected = {"package": counts.get("package/data"), "version": counts.get("version/data")}
    if any(type(value) is not int or value < 0 for value in expected.values()):
        raise ValueError("Curated package/version counts missing")
    for key, table in (("packages", "package"), ("versions", "version")):
        if key in report and report[key] != expected[table]:
            raise ValueError("Curated report counts disagree")
    if report.get("snapshot_timestamp") is None:
        raise ValueError("Curated snapshot timestamp missing")
    try:
        timestamp = datetime.fromisoformat(report["snapshot_timestamp"])
    except (TypeError, ValueError) as error:
        raise ValueError("Invalid Curated snapshot timestamp") from error
    if timestamp.tzinfo is not None:
        raise ValueError("Curated snapshot timestamp must be naive")
    return {"dataset": "package-version", "snapshot": snapshot,
            "snapshot_timestamp": timestamp.isoformat(), "curated_run_id": run_id,
            "run_prefix": prefix, "manifest_sha256": digest, "manifest": manifest,
            "counts": expected, "_service_records": grouped}


def _schema(con, path: Path, table: str) -> None:
    _shared_schema(con, path, table, _SCHEMAS)


def _sql_path(path: Path) -> str:
    return _shared_sql_path(path)


def _sql_paths(paths: list[Path | str]) -> str:
    return _shared_sql_paths(paths)


def _validate(con, paths: dict[str, list[Path]], expected: dict[str, int]) -> dict:
    for table, files in paths.items():
        for path in files:
            _schema(con, path, table)
        physical_count = con.execute("SELECT sum(num_rows) FROM parquet_file_metadata(?)", [[str(p) for p in files]]).fetchone()[0]
        if physical_count != expected[table]:
            raise ValueError("Curated input validation failed: manifest counts differ from Parquet metadata: " + table)
        print(f"Schema and Parquet metadata verified: {table}, {physical_count:,} rows", flush=True)
    package_paths, version_paths = [str(p) for p in paths["package"]], [str(p) for p in paths["version"]]
    con.execute(f"CREATE TEMP VIEW package_input AS SELECT * FROM read_parquet({_sql_paths(package_paths)})")
    con.execute(f"CREATE TEMP VIEW version_input AS SELECT * FROM read_parquet({_sql_paths(version_paths)})")
    checks = [
        ("package_id range", "SELECT count(*) FROM package_input WHERE package_id IS NULL OR package_id<1 OR package_id>2147483647"),
        ("package name", "SELECT count(*) FROM package_input WHERE name IS NULL OR trim(name)='' OR length(name)>300 OR contains(name,chr(0))"),
        ("package repo", "SELECT count(*) FROM package_input WHERE repo_url IS NOT NULL AND (length(repo_url)>200 OR contains(repo_url,chr(0)))"),
        ("package duplicate id", "SELECT count(*) FROM (SELECT package_id FROM package_input GROUP BY package_id HAVING count(*)>1)"),
        ("package duplicate name", "SELECT count(*) FROM (SELECT name FROM package_input GROUP BY name HAVING count(*)>1)"),
        ("version package FK", "SELECT count(*) FROM version_input v ANTI JOIN package_input p USING(package_id)"),
        ("version key", "SELECT count(*) FROM version_input WHERE version IS NULL OR trim(version)='' OR length(version)>100 OR contains(version,chr(0))"),
        ("version ordinal", "SELECT count(*) FROM version_input WHERE ordinal IS NULL OR ordinal<0"),
        ("version description", "SELECT count(*) FROM version_input WHERE description IS NOT NULL AND contains(description,chr(0))"),
        ("version deprecated", "SELECT count(*) FROM version_input WHERE deprecated IS NOT NULL AND contains(deprecated,chr(0))"),
        ("version duplicate", "SELECT count(*) FROM (SELECT package_id,version FROM version_input GROUP BY ALL HAVING count(*)>1)"),
        ("licenses JSON", "SELECT count(*) FROM version_input WHERE licenses IS NOT NULL AND NOT json_valid(licenses)"),
        ("dependency JSON", "SELECT count(*) FROM version_input WHERE dependency IS NOT NULL AND NOT json_valid(dependency)"),
    ]
    failures = {}
    for label, query in checks:
        print("Input check: " + label, flush=True)
        failures[label] = con.execute(query).fetchone()[0]
    failures = {label: count for label, count in failures.items() if count}
    counts = {table: con.execute(f"SELECT count(*) FROM {table}_input").fetchone()[0] for table in paths}
    if counts != expected:
        failures["manifest counts"] = counts
    if failures:
        raise ValueError("Curated input validation failed: " + json.dumps(failures, default=str, sort_keys=True))
    return {"counts": counts, "schemas": {table: _SCHEMAS[table] for table in paths}, "checks": "PASSED"}


def _export_csv(con, paths: dict[str, list[Path]], work_dir: Path) -> dict[str, list[Path]]:
    out = work_dir / "csv"
    out.mkdir(parents=True, exist_ok=True)
    result = {"package": [], "version": []}
    # PostgreSQL COPY TEXT uses backslash escapes.  Materialise every value
    # as escaped text so a multiline/string value can never create a control
    # line (in particular the psql ``\\.`` end marker).
    def escaped(column: str, kind: str) -> str:
        value_column = column
        if column == "dependency":
            value_column = f"COALESCE({column}, json '{DEFAULT_DEPENDENCY_JSON}')"
        source = (f"strftime({value_column}, '%Y-%m-%d %H:%M:%S.%f')"
                  if kind == "TIMESTAMP" else f"CAST({value_column} AS VARCHAR)")
        value = source
        value = f"replace({value}, chr(92), chr(92)||chr(92))"
        value = f"replace({value}, chr(9), chr(92)||'t')"
        value = f"replace({value}, chr(10), chr(92)||'n')"
        value = f"replace({value}, chr(13), chr(92)||'r')"
        return f"CASE WHEN {value_column} IS NULL THEN NULL ELSE {value} END"

    for table, files in paths.items():
        columns = ", ".join(escaped(name, kind) for name, kind in _SCHEMAS[table])
        for index, parquet in enumerate(files):
            target = out / f"{table}-{index:05d}.copy.tsv"
            print(f"Export COPY text: {table} {index + 1}/{len(files)}", flush=True)
            con.execute(f"COPY (SELECT {columns} FROM read_parquet({_sql_path(parquet)})) TO {_sql_path(target)} "
                        "(FORMAT CSV, DELIMITER '\\t', QUOTE '', ESCAPE '', HEADER false, NULL '\\N')")
            result[table].append(target)
    return result


def _write_dependency_quality(con, work_dir: Path, metadata: dict) -> dict:
    quality_dir = work_dir / "quality"
    quality_dir.mkdir(parents=True, exist_ok=True)
    path = quality_dir / "dependency_defaulted.jsonl"
    count = 0
    checksum = hashlib.sha256()
    with path.open("w", encoding="utf-8", newline="\n") as output:
        rows = con.execute(
            """SELECT v.package_id, p.name, v.version
               FROM version_input v
               JOIN package_input p USING (package_id)
               WHERE v.dependency IS NULL
               ORDER BY v.package_id, v.version"""
        ).fetchmany(1024)
        while rows:
            for package_id, name, version in rows:
                record = {
                    "package_id": package_id,
                    "name": name,
                    "version": version,
                    "reason": "DEPENDENCY_SQL_NULL_DEFAULTED",
                    "source_dependency_is_sql_null": True,
                    "replacement": DEFAULT_DEPENDENCY,
                    "source_run": metadata["curated_run_id"],
                    "manifest_sha256": metadata["manifest_sha256"],
                }
                line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
                output.write(line)
                checksum.update(line.encode("utf-8"))
                count += 1
            rows = con.fetchmany(1024)
    return {
        "count": count,
        "path": str(path.resolve()),
        "sha256": checksum.hexdigest(),
        "default_json": DEFAULT_DEPENDENCY,
        "reason": "DEPENDENCY_SQL_NULL_DEFAULTED",
    }


def prepare(s3, metadata: dict, work_dir: Path, workers: int = 4,
            threads: int = 4, memory: str = "4GB", export_csv: bool = True) -> dict:
    """Download exact service files, validate all inputs, and optionally export CSV."""
    required = {"dataset", "snapshot", "curated_run_id", "manifest", "counts"}
    if not required.issubset(metadata):
        raise ValueError("Incomplete run metadata")
    records = metadata.get("_service_records")
    if records is None:
        prefix = metadata["run_prefix"]
        records = _service_records(_records(metadata["manifest"], prefix), prefix)
    root = Path(work_dir).resolve()
    cache = root / "cache"
    paths = {}
    for table in ("package", "version"):
        print(f"Download and SHA verify: {table}, {len(records[table])} files", flush=True)
        paths[table] = download_files(s3, CURATED_BUCKET, records[table], cache / table, workers=workers)
    with duckdb.connect(str(root / "input.duckdb"), config={"threads": threads, "memory_limit": memory}) as con:
        validation = _validate(con, paths, metadata["counts"])
        quality = _write_dependency_quality(con, root, metadata)
        csv_files = _export_csv(con, paths, root) if export_csv else {"package": [], "version": []}
    return {"csv_files": csv_files, "counts": metadata["counts"], "validation": validation, "quality": {"dependency_defaulted": quality}}


__all__ = ["select_run", "prepare", "DEFAULT_DEPENDENCY", "DEFAULT_DEPENDENCY_JSON"]
