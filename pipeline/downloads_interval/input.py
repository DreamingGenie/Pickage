"""Pin and revalidate the immutable inputs for interval download aggregation."""
from __future__ import annotations

from datetime import date
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import os
import tempfile
from typing import Any
import duckdb

from pipeline.curated.storage import read_optional
from pipeline.postgresql.input import select_run
from pipeline.snapshot.input import read_candidate
from pipeline.snapshot.policy import parse_timestamp, policy_sha256

RAW_BUCKET = "pickage-raw"
CURATED_BUCKET = "pickage-curated"
RAW_PREFIX = "npm-downloads/v1/run_id={}"
_SHA = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$")
_DATE_PART = re.compile(r"(?:^|/)date=(\d{4}-\d{2}-\d{2})(?:/|$)")


def _sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _json(raw: bytes, label: str) -> dict:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid {label} JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _read(s3, bucket: str, key: str) -> bytes:
    found = read_optional(s3, bucket, key)
    if found is None:
        raise ValueError(f"required object missing: {key}")
    return found[0]


def _safe_relative(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or any(c in value for c in ("\\", "\x00", ":")):
        raise ValueError(f"invalid {label}")
    p = PurePosixPath(value)
    if p.is_absolute() or any(part in ("", ".", "..") for part in p.parts) or p.as_posix() != value:
        raise ValueError(f"unsafe {label}: {value!r}")
    return value


def _record(record: Any, label: str) -> dict:
    if not isinstance(record, dict):
        raise ValueError(f"invalid {label} record")
    path = _safe_relative(record.get("path"), f"{label}.path")
    size, checksum = record.get("bytes"), record.get("sha256")
    if type(size) is not int or size < 0 or not isinstance(checksum, str) or not _SHA.fullmatch(checksum):
        raise ValueError(f"invalid {label} record")
    return record | {"path": path}


def _file_digest(path: Path) -> tuple[int, str]:
    size = 0; digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(chunk); digest.update(chunk)
    return size, digest.hexdigest()


def _fetch(s3, bucket: str, key: str, record: dict, target: Path) -> Path:
    target = Path(target)
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise ValueError(f"cache path is not a regular file: {target}")
    parent = target.parent
    if any(part.is_symlink() for part in [parent, *parent.parents]):
        raise ValueError(f"cache path contains symlink: {target}")
    target = target.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    found = s3.get_object(Bucket=bucket, Key=key)
    body = found["Body"]
    digest = hashlib.sha256(); size = 0
    fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    os.close(fd); temporary = Path(temporary_name)
    try:
        with temporary.open("wb") as out:
            for chunk in iter(lambda: body.read(1024 * 1024), b""):
                digest.update(chunk); size += len(chunk); out.write(chunk)
        if size != record["bytes"] or digest.hexdigest() != record["sha256"]:
            raise ValueError(f"remote object verification failed: {key}")
        if target.exists() and _file_digest(target) != (record["bytes"], record["sha256"]):
            raise ValueError(f"cache differs for {key}")
        if not target.exists():
            temporary.replace(target)
    finally:
        close = getattr(body, "close", None)
        if close: close()
        temporary.unlink(missing_ok=True)
    return target


def _calendar_interval(candidate: dict, snapshot: str) -> dict:
    rows = candidate["calendar"]
    matches = [row for row in rows if row.get("snapshot_at") == snapshot]
    if len(matches) != 1:
        raise ValueError(f"snapshot is not uniquely present in candidate calendar: {snapshot}")
    return dict(matches[0])


def _bronze(s3, run_id: str, manifest_sha: str) -> tuple[dict, str]:
    if not isinstance(run_id, str) or not _ID.fullmatch(run_id) or not isinstance(manifest_sha, str) or not _SHA.fullmatch(manifest_sha):
        raise ValueError("invalid Bronze run identity")
    prefix = RAW_PREFIX.format(run_id)
    body = _read(s3, RAW_BUCKET, prefix + "/run_manifest.json")
    marker = _read(s3, RAW_BUCKET, prefix + "/_SUCCESS")
    if _sha(body) != manifest_sha or marker != (manifest_sha + "\n").encode("ascii"):
        raise ValueError("Bronze manifest or completion marker mismatch")
    input_body = _read(s3, RAW_BUCKET, prefix + "/_INPUT.json")
    if _json(input_body, "Bronze input") != {"manifest_sha256": manifest_sha}:
        raise ValueError("Bronze _INPUT manifest hash mismatch")
    manifest = _json(body, "Bronze manifest")
    if (manifest.get("dataset") != "npm-downloads" or manifest.get("run_id") != run_id
            or type(manifest.get("format_version")) is not int or manifest["format_version"] != 1
            or manifest.get("required_remote_verification") != "GET_SHA256_ALL_FILES"):
        raise ValueError("Bronze manifest identity mismatch")
    quality = manifest.get("quality")
    checks = quality.get("consistency_checks") if isinstance(quality, dict) else None
    if not isinstance(checks, dict) or not checks or any(value is not True for value in checks.values()):
        raise ValueError("Bronze quality checks are not approved")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("Bronze manifest has no files")
    normalized = [_record(row, "Bronze file") for row in files]
    if len({row["path"] for row in normalized}) != len(normalized):
        raise ValueError("Bronze manifest contains duplicate paths")
    allowed = {"target_csv", "status_parquet", "daily_parquet", "source_metadata", "raw_response"}
    if any(row.get("role") not in allowed for row in normalized):
        raise ValueError("Bronze manifest contains an unsupported file role")
    for row in normalized:
        if row["role"] in {"target_csv", "status_parquet", "daily_parquet"}:
            if type(row.get("row_count")) is not int or row["row_count"] < 0:
                raise ValueError("invalid Bronze row count")
        if row["role"] == "daily_parquet":
            match = re.fullmatch(r"parquet/downloads/date=(\d{4}-\d{2}-\d{2})/[^/]+\.parquet", row["path"])
            if not match or date.fromisoformat(match.group(1)).isoformat() != match.group(1):
                raise ValueError("invalid daily partition date/path")
            if row.get("min_date") != match.group(1) or row.get("max_date") != match.group(1):
                raise ValueError("daily partition and manifest date metadata differ")
            if type(row.get("row_count")) is not int or row["row_count"] < 0:
                raise ValueError("invalid daily row count")
    return {**manifest, "files": normalized, "prefix": prefix}, prefix


def _selected_daily(files: list[dict], interval: dict) -> list[dict]:
    start, end = interval.get("download_start_inclusive"), interval.get("download_end_exclusive")
    if start is None:
        return []
    selected = []
    for row in files:
        if row.get("role") != "daily_parquet": continue
        match = _DATE_PART.search(row["path"])
        if not match: raise ValueError(f"daily file lacks date partition: {row['path']}")
        day = match.group(1)
        if start <= day < end: selected.append(row)
    return sorted(selected, key=lambda row: row["path"])


def prepare(s3, *, snapshot: str, bronze_run_id: str, bronze_manifest_sha256: str,
            curated_run_id: str, curated_manifest_sha256: str, candidate_path: Path,
            candidate_sha256: str, cache_dir: Path, workers: int = 4) -> dict:
    if not isinstance(snapshot, str): raise ValueError("snapshot must be a date")
    if date.fromisoformat(snapshot).isoformat() != snapshot: raise ValueError("snapshot must be an ISO date")
    if type(workers) is not int or not 1 <= workers <= 16:
        raise ValueError("workers must be between 1 and 16")
    for value in (candidate_sha256, curated_manifest_sha256, bronze_manifest_sha256):
        if not isinstance(value, str) or not _SHA.fullmatch(value):
            raise ValueError("invalid input SHA")
    for value in (bronze_run_id, curated_run_id):
        if not isinstance(value, str) or not _ID.fullmatch(value):
            raise ValueError("invalid input run ID")
    candidate = read_candidate(Path(candidate_path))
    if candidate["candidate_sha256"] != candidate_sha256: raise ValueError("candidate hash mismatch")
    interval = _calendar_interval(candidate, snapshot)
    curated = select_run(s3, snapshot, curated_run_id)
    if curated["manifest_sha256"] != curated_manifest_sha256: raise ValueError("Curated manifest hash mismatch")
    expected_ts = parse_timestamp(interval["snapshot_timestamp"])
    actual_ts = parse_timestamp(curated["snapshot_timestamp"], allow_naive_utc=True)
    if actual_ts != expected_ts: raise ValueError("Curated snapshot timestamp mismatch")
    bronze, raw_prefix = _bronze(s3, bronze_run_id, bronze_manifest_sha256)
    records = bronze["files"]
    by_role = {}
    for row in records:
        by_role.setdefault(row.get("role"), []).append(row)
    def one(role: str) -> dict:
        values = by_role.get(role, [])
        if len(values) != 1: raise ValueError(f"Bronze manifest must contain one {role} file")
        return values[0]
    target, status = one("target_csv"), one("status_parquet")
    daily = _selected_daily(records, interval)
    all_daily = [row for row in records if row.get("role") == "daily_parquet"]
    available = [m.group(1) for row in all_daily for m in [_DATE_PART.search(row["path"])] if m]
    if not all_daily:
        raise ValueError("Bronze manifest has no daily files")
    if all_daily and not available: raise ValueError("Bronze daily records have no dates")
    root = Path(cache_dir)
    if any(p.is_symlink() for p in (root, *root.parents)):
        raise ValueError("cache directory must not be symlinked")
    root = root.resolve(); root.mkdir(parents=True, exist_ok=True)
    target_path = _fetch(s3, RAW_BUCKET, f"{raw_prefix}/data/{target['path']}", target, root / "bronze" / target["path"])
    status_path = _fetch(s3, RAW_BUCKET, f"{raw_prefix}/data/{status['path']}", status, root / "bronze" / status["path"])
    with ThreadPoolExecutor(max_workers=workers) as pool:
        daily_paths = list(pool.map(lambda row: _fetch(s3, RAW_BUCKET, f"{raw_prefix}/data/{row['path']}",
                                                     row, root / "bronze" / row["path"]), daily))
    package_records = curated["_service_records"]["package"]
    def fetch_package(row):
        rel = _safe_relative(row["key"][len(curated["run_prefix"] + "/attempts/"):], "Curated cache path")
        return _fetch(s3, CURATED_BUCKET, row["key"], row, root / "curated" / rel)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        package_paths = list(pool.map(fetch_package, package_records))
    with duckdb.connect() as con:
        target_rows = con.execute("SELECT count(*) FROM read_csv(?,header=true,all_varchar=true)", [str(target_path)]).fetchone()[0]
        if target_rows != target["row_count"]:
            raise ValueError("Bronze target CSV row count mismatch")
        for path, record in [(status_path, status), *zip(daily_paths, daily)]:
            if "row_count" in record:
                rows = con.execute("SELECT sum(num_rows) FROM parquet_file_metadata(?)", [str(path)]).fetchone()[0]
                if rows != record["row_count"]:
                    raise ValueError("Bronze Parquet footer row count mismatch")
        total_rows = 0
        for path in package_paths:
            schema = [(r[0], r[1].upper()) for r in con.execute("DESCRIBE SELECT * FROM read_parquet(?, hive_partitioning=false)", [str(path)]).fetchall()]
            if schema != [("package_id", "INTEGER"), ("name", "VARCHAR"), ("repo_url", "VARCHAR")]:
                raise ValueError(f"Curated package Parquet schema mismatch: {path.name}")
            total_rows += con.execute("SELECT sum(num_rows) FROM parquet_file_metadata(?)", [str(path)]).fetchone()[0]
        if total_rows != curated["counts"]["package"]:
            raise ValueError("Curated package footer row count mismatch")
    payload = {"snapshot": snapshot, "interval": interval, "bronze_run_id": bronze_run_id,
               "remote_inputs": {"bronze_uri": f"s3://{RAW_BUCKET}/{raw_prefix}/run_manifest.json",
                                 "curated_uri": f"s3://{CURATED_BUCKET}/{curated['run_prefix']}/run_manifest.json"},
               "bronze_manifest_sha256": bronze_manifest_sha256, "curated_run_id": curated_run_id,
               "curated_manifest_sha256": curated_manifest_sha256, "candidate_sha256": candidate_sha256,
               "policy_version": "snapshot-time-v1", "policy_sha256": policy_sha256(),
               "counts": {"bronze_files": len(records), "daily_files": len(all_daily), "selected_daily_files": len(daily),
                          "package_files": len(package_records), "expected_package_rows": curated["counts"]["package"]},
               "selected": {"target": target, "status": status, "daily": daily,
                            "package": [{"key": r["key"], "bytes": r["bytes"], "sha256": r["sha256"]} for r in package_records]},
               "candidate": {"sha256": candidate_sha256, "inventory_sha256": candidate.get("inventory_sha256"),
                             "policy_version": candidate["candidate"]["policy_version"] if "candidate" in candidate else "snapshot-time-v1",
                             "policy_sha256": candidate["candidate"]["policy_sha256"] if "candidate" in candidate else policy_sha256()},
               "calendar": candidate["calendar"], "excluded_snapshots": [
                   {"snapshot_at": r["snapshot_at"], "reason": "NOT_SELECTED_NO_APPROVED_POPULATION_INPUT"}
                   for r in candidate["calendar"] if r["snapshot_at"] != snapshot],
               "verification": {"consumed_files": "REMOTE_GET_SHA256_AND_LOCAL_SHA256",
                                "consumed_file_count": 2 + len(daily) + len(package_records),
                                "consumed_bytes": sum(r["bytes"] for r in (target, status, *daily, *package_records)),
                                "unconsumed_bronze_files": "APPROVED_MANIFEST_ONLY_NO_BYTE_RESCAN",
                                "unconsumed_curated_files": "APPROVED_MANIFEST_ONLY_NO_BYTE_RESCAN",
                                "candidate_source": "FROZEN_CANDIDATE_SHA_AND_PROJECTS_FOOTER_INVENTORY"}}
    manifest_sha = _sha(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())
    consumed = [target, status, *daily]
    return {"package_files": [str(p) for p in package_paths], "target_file": str(target_path), "status_file": str(status_path),
            "daily_files": [str(p) for p in daily_paths], "interval": interval,
            "available_start": min(available), "available_end": max(available),
            "expected_package_rows": curated["counts"]["package"], "input_manifest": payload,
            "input_manifest_sha256": manifest_sha, "lineage": {"input_manifest_sha256": manifest_sha, "policy_sha256": policy_sha256()},
            "_bronze_records": records, "_bronze_consumed_records": consumed, "_bronze_prefix": raw_prefix,
            "_bronze_run_id": bronze_run_id, "_bronze_manifest_sha256": bronze_manifest_sha256,
            "_curated": curated, "_curated_manifest_sha256": curated_manifest_sha256,
            "_candidate_path": str(candidate_path), "_candidate_sha256": candidate_sha256,
            "_cache_dir": str(root), "_package_records": package_records}


def revalidate(s3, prepared: dict) -> None:
    if not isinstance(prepared, dict): raise ValueError("prepared must be a mapping")
    candidate = read_candidate(Path(prepared["_candidate_path"]))
    if candidate["candidate_sha256"] != prepared["_candidate_sha256"]: raise ValueError("candidate changed")
    bronze, prefix = _bronze(s3, prepared["_bronze_run_id"], prepared["_bronze_manifest_sha256"])
    expected = {row["path"]: row for row in prepared["_bronze_consumed_records"]}
    actual = {row["path"]: row for row in bronze["files"]}
    if any(actual.get(key) != row for key, row in expected.items()):
        raise ValueError("consumed Bronze manifest records changed")
    for row in prepared["_bronze_consumed_records"]:
        local = Path(prepared["_cache_dir"]) / "bronze" / row["path"]
        if any(p.is_symlink() for p in (local, *local.parents)) or not local.is_file() or _file_digest(local) != (row["bytes"], row["sha256"]):
            raise ValueError(f"local consumed Bronze file changed: {row['path']}")
    for row in prepared["_bronze_consumed_records"]:
        _verify_remote(s3, RAW_BUCKET, f"{prefix}/data/{row['path']}", row)
    curated = select_run(s3, prepared["interval"]["snapshot_at"], prepared["_curated"]["curated_run_id"])
    if curated["manifest_sha256"] != prepared["_curated_manifest_sha256"]: raise ValueError("Curated manifest changed")
    for row in curated["_service_records"]["package"]:
        rel = row["key"][len(curated["run_prefix"] + "/attempts/"):]
        local = Path(prepared["_cache_dir"]) / "curated" / rel
        if any(p.is_symlink() for p in (local, *local.parents)) or not local.is_file() or _file_digest(local) != (row["bytes"], row["sha256"]):
            raise ValueError(f"local Curated file changed: {row['key']}")
        _verify_remote(s3, CURATED_BUCKET, row["key"], row)


def _verify_remote(s3, bucket: str, key: str, record: dict) -> None:
    found = s3.get_object(Bucket=bucket, Key=key)
    body = found["Body"]; size = 0; digest = hashlib.sha256()
    try:
        for chunk in iter(lambda: body.read(1024 * 1024), b""):
            size += len(chunk); digest.update(chunk)
    finally:
        close = getattr(body, "close", None)
        if close: close()
    if (size, digest.hexdigest()) != (record["bytes"], record["sha256"]):
        raise ValueError(f"remote object verification failed: {key}")


__all__ = ["prepare", "revalidate"]
