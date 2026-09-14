"""Persist and independently verify version-dependent count artifacts.

This module calls :func:`aggregate` on normalized inputs and stores the
result with caller-provided lineage, but does not prove that an upstream
manifest, the complete stable target population, or production approval was
correct.  Such proof is outside this local artifact layer.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

from .aggregate import aggregate

_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_ROLES = ("requirements_edges", "approved_sources", "approved_targets")
_FILES = ("counts.parquet", "lineage.parquet", "quality.parquet")
_FORMAT = "version-dependents-artifact-v1"
_UTC_TYPE = "TIMESTAMP WITH TIME ZONE"
_COUNT_SCHEMA = [
    ["package_id", "INTEGER"],
    ["version", "VARCHAR"],
    ["snapshot_at", "DATE"],
    ["snapshot_timestamp", _UTC_TYPE],
    ["dependents_count", "INTEGER"],
]
_LINEAGE_SCHEMA = [
    ["run_id", "VARCHAR"],
    ["snapshot_at", "DATE"],
    ["snapshot_timestamp", _UTC_TYPE],
    ["role", "VARCHAR"],
    ["upstream_run_id", "VARCHAR"],
    ["manifest_sha256", "VARCHAR"],
    ["policy_sha256", "VARCHAR"],
    ["verification_status", "VARCHAR"],
]
_QUALITY_SCHEMA = [
    ["run_id", "VARCHAR"],
    ["snapshot_at", "DATE"],
    ["snapshot_timestamp", _UTC_TYPE],
    ["input_verification", "VARCHAR"],
    ["ready_for_load", "BOOLEAN"],
    ["source_versions", "BIGINT"],
    ["input_edges", "BIGINT"],
    ["distinct_edges", "BIGINT"],
    ["duplicate_edges", "BIGINT"],
    ["target_versions", "BIGINT"],
    ["zero_target_versions", "BIGINT"],
    ["max_dependents_count", "BIGINT"],
    ["total_direct_dependents", "BIGINT"],
]


def _utc(value: datetime, expected: date) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("snapshot_timestamp must be timezone-aware")
    value = value.astimezone(timezone.utc)
    if value.date() != expected:
        raise ValueError("snapshot_timestamp UTC date must equal expected_snapshot_at")
    return value


def _epoch_us(value: datetime) -> int:
    return ((value.date() - date(1970, 1, 1)).days * 86_400 + value.hour * 3_600 + value.minute * 60 + value.second) * 1_000_000 + value.microsecond


def _validate_run_id(value: str) -> None:
    if not isinstance(value, str) or not _RUN_ID.fullmatch(value) or value.endswith("."):
        raise ValueError("run_id must be a safe ASCII path segment")
    # Windows reserves these device names even when an extension is present.
    if value.split(".", 1)[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        raise ValueError("run_id is a reserved device name")


def _validate_sha(value: str, field: str) -> None:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase 64-hex SHA-256")


def _validate_lineage(lineage: list[dict[str, str]]) -> list[dict[str, str]]:
    if not isinstance(lineage, list) or len(lineage) != 3:
        raise ValueError("input_lineage must contain exactly three entries")
    result: list[dict[str, str]] = []
    for item in lineage:
        if not isinstance(item, dict) or set(item) != {"role", "run_id", "manifest_sha256", "policy_sha256"}:
            raise ValueError("input_lineage entries have an invalid shape")
        if item["role"] not in _ROLES:
            raise ValueError("input_lineage has an invalid role")
        _validate_run_id(item["run_id"])
        _validate_sha(item["manifest_sha256"], "manifest_sha256")
        _validate_sha(item["policy_sha256"], "policy_sha256")
        result.append({key: item[key] for key in ("role", "run_id", "manifest_sha256", "policy_sha256")})
    if {item["role"] for item in result} != set(_ROLES):
        raise ValueError("input_lineage roles must contain each required role exactly once")
    return sorted(result, key=lambda item: _ROLES.index(item["role"]))


def _reparse(path: Path) -> bool:
    try:
        mode = os.lstat(path).st_mode
        if stat.S_ISLNK(mode):
            return True
        if os.name == "nt":
            import ctypes
            attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
            return attrs != 0xFFFFFFFF and bool(attrs & 0x400)
    except (FileNotFoundError, OSError):
        return False
    return False


def _safe_existing_dir(path: Path) -> None:
    if _reparse(path) or (path.exists() and not path.is_dir()):
        raise ValueError(f"unsafe output directory: {path}")


def _reject_reparse_ancestors(path: Path) -> None:
    absolute = path.absolute()
    for ancestor in reversed((absolute, *absolute.parents)):
        if _reparse(ancestor):
            raise ValueError(f"unsafe reparse-point ancestor: {ancestor}")


def _sql_literal(path: Path) -> str:
    return "'" + str(path.resolve()).replace("'", "''") + "'"


def _sha256(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _code_sha() -> str:
    root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for path in (root / "aggregate.py", root / "artifact.py"):
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _describe_file(path: Path) -> tuple[list[list[str]], int]:
    con = duckdb.connect()
    temp_dir = tempfile.TemporaryDirectory(prefix="version-dependents-verify-")
    try:
        con.execute("SET memory_limit='512MB'")
        con.execute("SET threads=2")
        con.execute("SET temp_directory=?", [temp_dir.name])
        literal = _sql_literal(path)
        rows = int(con.execute(f"SELECT count(*) FROM read_parquet({literal}, hive_partitioning=false)").fetchone()[0])
        schema = [[str(row[0]), str(row[1]).upper()] for row in con.execute(f"DESCRIBE SELECT * FROM read_parquet({literal}, hive_partitioning=false)").fetchall()]
        return schema, rows
    finally:
        con.close()
        temp_dir.cleanup()


def _file_record(path: Path) -> dict[str, Any]:
    schema, rows = _describe_file(path)
    size, digest = _sha256(path)
    return {"path": path.name, "bytes": size, "sha256": digest, "rows": rows, "schema": schema, "schema_sha256": hashlib.sha256(_canonical(schema)).hexdigest()}


def _input_stats(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    row = con.execute("""
        SELECT
          (SELECT count(*) FROM approved_sources),
          (SELECT count(*) FROM requirements_edges),
          (SELECT coalesce(sum(dependents_count), 0) FROM version_dependents),
          (SELECT count(*) FROM approved_targets)
    """).fetchone()
    input_edges, distinct_edges = int(row[1]), int(row[2])
    target_stats = con.execute("SELECT count(*), count(*) FILTER (WHERE dependents_count=0), coalesce(max(dependents_count),0), coalesce(sum(dependents_count),0) FROM version_dependents").fetchone()
    return {
        "source_versions": int(row[0]), "input_edges": input_edges,
        "distinct_edges": distinct_edges, "duplicate_edges": input_edges - distinct_edges,
        "target_versions": int(row[3]), "zero_target_versions": int(target_stats[1]),
        "max_dependents_count": int(target_stats[2]), "total_direct_dependents": int(target_stats[3]),
    }


def save_artifact(con: duckdb.DuckDBPyConnection, *, output_root: Path, run_id: str, expected_snapshot_at: date, snapshot_timestamp: datetime, resolution_status: str, ready_for_dependents: bool, input_lineage: list[dict[str, str]]) -> dict[str, Any]:
    """Save one snapshot's validated local result; upstream approval is not verified."""
    if not isinstance(expected_snapshot_at, date) or isinstance(expected_snapshot_at, datetime):
        raise ValueError("expected_snapshot_at must be a date")
    timestamp = _utc(snapshot_timestamp, expected_snapshot_at)
    if resolution_status != "COMPLETE" or type(ready_for_dependents) is not bool or not ready_for_dependents:
        raise ValueError("only COMPLETE with ready_for_dependents=True can be saved")
    _validate_run_id(run_id)
    lineage = _validate_lineage(input_lineage)
    root = Path(output_root).absolute()
    _safe_existing_dir(root)
    run_dir = root / f"snapshot={expected_snapshot_at.isoformat()}" / f"run_id={run_id}"
    _reject_reparse_ancestors(run_dir)
    if _reparse(run_dir) or run_dir.exists():
        raise ValueError("artifact run directory already exists or is unsafe")
    # The kernel owns schema, identity, population and snapshot validation.
    aggregate(
        con,
        expected_snapshot_at=expected_snapshot_at,
        snapshot_timestamp=timestamp,
        resolution_status=resolution_status,
        ready_for_dependents=ready_for_dependents,
    )
    stats = _input_stats(con)
    for value in stats.values():
        if value < 0:
            raise ValueError("quality values must be nonnegative")
    if stats["source_versions"] <= 0 or stats["target_versions"] <= 0 or stats["distinct_edges"] != stats["total_direct_dependents"]:
        raise ValueError("aggregate populations or edge totals are inconsistent")
    _reject_reparse_ancestors(run_dir)
    run_dir.parent.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(exist_ok=False)
    # A failed attempt keeps its exclusive directory but has no final manifest.
    con.execute(f"COPY (SELECT package_id::INTEGER AS package_id, version, snapshot_at, snapshot_timestamp, dependents_count FROM version_dependents ORDER BY package_id, version) TO {_sql_literal(run_dir / 'counts.parquet')} (FORMAT PARQUET, COMPRESSION ZSTD)")
    con.execute(f"COPY (SELECT ?::VARCHAR AS run_id, ?::DATE AS snapshot_at, ?::TIMESTAMPTZ AS snapshot_timestamp, role, upstream_run_id, manifest_sha256, policy_sha256, 'NOT_PERFORMED'::VARCHAR AS verification_status FROM (VALUES (?, ?, ?, ?), (?, ?, ?, ?), (?, ?, ?, ?)) AS v(role, upstream_run_id, manifest_sha256, policy_sha256) ORDER BY role) TO {_sql_literal(run_dir / 'lineage.parquet')} (FORMAT PARQUET, COMPRESSION ZSTD)", [run_id, expected_snapshot_at, timestamp, *sum(([item['role'], item['run_id'], item['manifest_sha256'], item['policy_sha256']] for item in lineage), [])])
    q = stats
    con.execute(f"COPY (SELECT ?::VARCHAR AS run_id, ?::DATE AS snapshot_at, ?::TIMESTAMPTZ AS snapshot_timestamp, 'NOT_PERFORMED'::VARCHAR AS input_verification, false::BOOLEAN AS ready_for_load, ?::BIGINT AS source_versions, ?::BIGINT AS input_edges, ?::BIGINT AS distinct_edges, ?::BIGINT AS duplicate_edges, ?::BIGINT AS target_versions, ?::BIGINT AS zero_target_versions, ?::BIGINT AS max_dependents_count, ?::BIGINT AS total_direct_dependents) TO {_sql_literal(run_dir / 'quality.parquet')} (FORMAT PARQUET, COMPRESSION ZSTD)", [run_id, expected_snapshot_at, timestamp, *[q[key] for key in ('source_versions','input_edges','distinct_edges','duplicate_edges','target_versions','zero_target_versions','max_dependents_count','total_direct_dependents')]])
    files = [_file_record(run_dir / name) for name in _FILES]
    manifest = {"format_version": _FORMAT, "run_id": run_id, "snapshot_at": expected_snapshot_at.isoformat(), "snapshot_timestamp": timestamp.isoformat().replace("+00:00", "Z"), "artifact_status": "COMPLETE", "resolution_status": "COMPLETE", "input_verification": "NOT_PERFORMED", "ready_for_load": False, "verification_scope": "LOCAL_ARTIFACT_ONLY", "dependency_kind": "dependencies", "null_published_at": "EXCLUDE", "input_lineage": lineage, "quality": q, "code_sha256": _code_sha(), "files": files}
    _verify_contents(run_dir, manifest, manifest_present=False)
    body = _canonical(manifest)
    with (run_dir / "run_manifest.json").open("xb") as stream:
        stream.write(body)
    return {"run_dir": str(run_dir), "manifest_sha256": hashlib.sha256(body).hexdigest(), "manifest": manifest}


def verify_artifact(run_dir: Path, *, manifest_sha256: str, expected_snapshot_at: date | None = None, snapshot_timestamp: datetime | None = None) -> dict[str, Any]:
    """Verify stored bytes and internal consistency using a fresh DuckDB connection."""
    _validate_sha(manifest_sha256, "manifest_sha256")
    path = Path(run_dir).absolute()
    _reject_reparse_ancestors(path)
    if not path.is_dir() or _reparse(path):
        raise ValueError("run_dir must be a real directory")
    manifest_path = path / "run_manifest.json"
    if not manifest_path.is_file() or _reparse(manifest_path):
        raise ValueError("missing run_manifest.json")
    with manifest_path.open("rb") as stream:
        raw = stream.read(4 * 1024 * 1024 + 1)
    if len(raw) > 4 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != manifest_sha256:
        raise ValueError("manifest SHA-256 mismatch")
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid manifest JSON") from exc
    return _verify_contents(path, manifest, expected_snapshot_at=expected_snapshot_at,
                            snapshot_timestamp=snapshot_timestamp, manifest_present=True)


def _verify_contents(path: Path, manifest: dict, *, manifest_present: bool,
                     expected_snapshot_at: date | None = None,
                     snapshot_timestamp: datetime | None = None) -> dict:
    """Shared pre-manifest and standalone validation; never reads upstream inputs."""
    keys = {"format_version", "run_id", "snapshot_at", "snapshot_timestamp", "artifact_status",
            "resolution_status", "input_verification", "ready_for_load", "verification_scope",
            "dependency_kind", "null_published_at", "input_lineage", "quality", "code_sha256", "files"}
    if not isinstance(manifest, dict) or set(manifest) != keys:
        raise ValueError("manifest must contain exactly the artifact contract fields")
    if manifest.get("format_version") != _FORMAT or manifest.get("artifact_status") != "COMPLETE" or manifest.get("resolution_status") != "COMPLETE":
        raise ValueError("invalid artifact status")
    if manifest.get("input_verification") != "NOT_PERFORMED" or manifest.get("ready_for_load") is not False or manifest.get("verification_scope") != "LOCAL_ARTIFACT_ONLY" or manifest.get("dependency_kind") != "dependencies" or manifest.get("null_published_at") != "EXCLUDE":
        raise ValueError("invalid local verification contract")
    _validate_sha(manifest.get("code_sha256"), "code_sha256")
    _validate_run_id(manifest.get("run_id"))
    try:
        snap = date.fromisoformat(manifest["snapshot_at"])
        ts_text = manifest["snapshot_timestamp"]
        ts = datetime.fromisoformat(ts_text.replace("Z", "+00:00"))
        ts = _utc(ts, snap)
        if snap.isoformat() != manifest["snapshot_at"] or ts.isoformat().replace("+00:00", "Z") != ts_text:
            raise ValueError("snapshot must use canonical date and exact UTC timestamp")
    except (TypeError, AttributeError, ValueError) as exc:
        raise ValueError("invalid manifest snapshot") from exc
    if expected_snapshot_at is not None and type(expected_snapshot_at) is not date:
        raise ValueError("expected_snapshot_at must be a date")
    if expected_snapshot_at is not None and snap != expected_snapshot_at:
        raise ValueError("manifest snapshot_at mismatch")
    if snapshot_timestamp is not None and _utc(snapshot_timestamp, snap) != ts:
        raise ValueError("manifest snapshot_timestamp mismatch")
    entries = manifest.get("files")
    file_keys = {"path", "bytes", "sha256", "rows", "schema", "schema_sha256"}
    if not isinstance(entries, list) or any(not isinstance(entry, dict) or set(entry) != file_keys for entry in entries) or tuple(entry["path"] for entry in entries) != _FILES:
        raise ValueError("manifest file list must contain exactly the three parquet files")
    if any(type(entry["bytes"]) is not int or entry["bytes"] < 0 or type(entry["rows"]) is not int or entry["rows"] < 0 for entry in entries):
        raise ValueError("manifest file sizes and rows must be nonnegative integers")
    actual = {item.name for item in path.iterdir()}
    expected_files = set(_FILES) | ({"run_manifest.json"} if manifest_present else set())
    if actual != expected_files or any(_reparse(path / name) or not (path / name).is_file() for name in actual):
        raise ValueError("artifact contains missing, extra, or unsafe files")
    con = duckdb.connect()
    temp_dir = tempfile.TemporaryDirectory(prefix="version-dependents-verify-")
    try:
        con.execute("SET memory_limit='512MB'")
        con.execute("SET threads=2")
        con.execute("SET temp_directory=?", [temp_dir.name])
        for entry, expected_schema in zip(entries, (_COUNT_SCHEMA, _LINEAGE_SCHEMA, _QUALITY_SCHEMA)):
            file = path / entry["path"]
            size, digest = _sha256(file)
            if entry.get("bytes") != size or entry.get("sha256") != digest:
                raise ValueError(f"file hash mismatch: {entry['path']}")
            schema, rows = _describe_file(file)
            if schema != expected_schema or entry.get("schema") != schema or entry.get("rows") != rows or entry.get("schema_sha256") != hashlib.sha256(_canonical(schema)).hexdigest():
                raise ValueError(f"file schema or row metadata mismatch: {entry['path']}")
            if (entry["path"] == "lineage.parquet" and rows != 3) or (entry["path"] == "quality.parquet" and rows != 1):
                raise ValueError("lineage must have three rows and quality must have one row")
        clit = _sql_literal(path / "counts.parquet")
        expected_epoch = _epoch_us(ts)
        bad = con.execute(f"SELECT EXISTS (SELECT 1 FROM read_parquet({clit}, hive_partitioning=false) WHERE package_id IS NULL OR package_id <= 0 OR version IS NULL OR regexp_matches(version, '^\\s*$') OR contains(version, chr(0)) OR length(version)>100 OR snapshot_at IS NULL OR snapshot_at <> ? OR snapshot_timestamp IS NULL OR epoch_us(snapshot_timestamp) <> ? OR dependents_count IS NULL OR dependents_count < 0)", [snap, expected_epoch]).fetchone()[0]
        duplicate = con.execute(f"SELECT EXISTS (SELECT 1 FROM (SELECT package_id, version FROM read_parquet({clit}, hive_partitioning=false) GROUP BY package_id, version HAVING count(*) > 1))").fetchone()[0]
        if bad or duplicate:
            raise ValueError("invalid counts rows")
        count_stats = con.execute(f"SELECT count(*), count(*) FILTER (WHERE dependents_count=0), coalesce(max(dependents_count),0), coalesce(sum(dependents_count),0) FROM read_parquet({clit}, hive_partitioning=false)").fetchone()
        quality = manifest.get("quality")
        if not isinstance(quality, dict):
            raise ValueError("missing quality")
        numeric = ("source_versions", "input_edges", "distinct_edges", "duplicate_edges", "target_versions", "zero_target_versions", "max_dependents_count", "total_direct_dependents")
        if set(quality) != set(numeric) or any(type(quality.get(key)) is not int or quality[key] < 0 for key in numeric) or quality["source_versions"] <= 0 or quality["target_versions"] <= 0 or quality["max_dependents_count"] > quality["source_versions"] or quality["input_edges"] != quality["distinct_edges"] + quality["duplicate_edges"] or quality["distinct_edges"] != quality["total_direct_dependents"] or quality["target_versions"] != int(count_stats[0]) or quality["zero_target_versions"] != int(count_stats[1]) or quality["total_direct_dependents"] != int(count_stats[3]) or quality["max_dependents_count"] != int(count_stats[2]):
            raise ValueError("quality values are inconsistent with counts")
        lineage = manifest.get("input_lineage")
        if _validate_lineage(lineage) != lineage:
            raise ValueError("invalid input lineage")
        llit = _sql_literal(path / "lineage.parquet")
        stored_lineage = con.execute(f"SELECT role, upstream_run_id, manifest_sha256, policy_sha256, verification_status, snapshot_at, epoch_us(snapshot_timestamp), run_id FROM read_parquet({llit}, hive_partitioning=false) ORDER BY role").fetchall()
        expected_lineage = [(item["role"], item["run_id"], item["manifest_sha256"], item["policy_sha256"], "NOT_PERFORMED", snap, expected_epoch, manifest["run_id"]) for item in sorted(lineage, key=lambda item: item["role"])]
        if stored_lineage != expected_lineage:
            raise ValueError("lineage parquet disagrees with manifest")
        qlit = _sql_literal(path / "quality.parquet")
        stored_quality = con.execute(f"SELECT run_id, snapshot_at, epoch_us(snapshot_timestamp), input_verification, ready_for_load, source_versions, input_edges, distinct_edges, duplicate_edges, target_versions, zero_target_versions, max_dependents_count, total_direct_dependents FROM read_parquet({qlit}, hive_partitioning=false)").fetchall()
        expected_quality = (manifest["run_id"], snap, expected_epoch, "NOT_PERFORMED", False, *[quality[key] for key in numeric])
        if stored_quality != [expected_quality]:
            raise ValueError("quality parquet disagrees with manifest")
        return manifest
    finally:
        con.close()
        temp_dir.cleanup()
