"""Pin and validate the resolved edge files of a recovery candidate.

This is deliberately a diagnostic input boundary.  It accepts the resolved
part of a PARTIAL run, but never turns that run into a load-ready result.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

import duckdb
from pipeline.preprocessing.requirements_resolution.policy import validate_policy
from pipeline.preprocessing.snapshot.policy import parse_timestamp

from pipeline.preprocessing.version_dependents.artifact import _canonical, _reparse, _sha256, _sql_literal, _reject_reparse_ancestors, _validate_run_id

_MAX_JSON = 4 * 1024 * 1024
_EDGE_SCHEMA = [
    ["snapshot_at", "DATE"], ["source_package_id", "INTEGER"],
    ["source_version", "VARCHAR"], ["target_package_id", "INTEGER"],
    ["target_version", "VARCHAR"], ["dependency_kinds", "VARCHAR[]"],
    ["declaration_count", "BIGINT"], ["snapshot_timestamp", "TIMESTAMP WITH TIME ZONE"],
    ["run_id", "VARCHAR"], ["input_sha256", "VARCHAR"],
    ["curated_run_id", "VARCHAR"], ["bronze_run_id", "VARCHAR"],
    ["policy_sha256", "VARCHAR"],
]
_HEX = set("0123456789abcdef")


def _read_json(path: Path, raw: bytes | None = None) -> dict[str, Any]:
    if not path.is_file() or _reparse(path):
        raise ValueError(f"candidate manifest must be a regular file: {path}")
    if raw is None:
        with path.open("rb") as stream:
            raw = stream.read(_MAX_JSON + 1)
    if len(raw) > _MAX_JSON:
        raise ValueError("candidate manifest exceeds 4 MiB")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("candidate manifest is not valid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("candidate manifest root must be an object")
    return value


def _sha(value: Any, name: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in _HEX for ch in value):
        raise ValueError(f"{name} must be a lowercase SHA-256")


def _safe_relative(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value or value.startswith("/") or Path(value).drive:
        raise ValueError(f"{name} must be a safe relative POSIX path")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"{name} contains an unsafe path component")
    return value


def _parse_timestamp(value: Any, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be an ISO timestamp")
    return parse_timestamp(value)


def _output_dir(source_run: Path, final_output: Any) -> Path:
    rel = _safe_relative(final_output, "final_output")
    source = source_run.absolute()
    candidate = source / rel
    _reject_reparse_ancestors(candidate)
    try:
        candidate.resolve().relative_to(source.resolve())
    except ValueError as exc:
        raise ValueError("final_output escaped source_run") from exc
    if not (candidate / "edges").is_dir():
        raise ValueError("final_output does not resolve to an edges directory")
    return candidate


def _reject_tree(path: Path) -> None:
    """Reject reparse points in the selected provenance tree."""
    path = path.absolute()
    if not path.exists() or _reparse(path):
        raise ValueError(f"missing or unsafe path: {path}")
    for current, dirs, files in os.walk(path, followlinks=False):
        current_path = Path(current)
        if _reparse(current_path):
            raise ValueError(f"unsafe reparse-point ancestor: {current_path}")
        for name in (*dirs, *files):
            child = current_path / name
            if _reparse(child):
                raise ValueError(f"unsafe reparse point: {child}")


def _file_record(con: duckdb.DuckDBPyConnection, path: Path, root: Path) -> dict[str, Any]:
    relative = path.relative_to(root).as_posix()
    size, digest = _sha256(path)
    literal = _sql_literal(path)
    rows = int(con.execute(f"SELECT count(*) FROM read_parquet({literal}, hive_partitioning=false)").fetchone()[0])
    schema = [[str(row[0]), str(row[1]).upper()] for row in con.execute(f"DESCRIBE SELECT * FROM read_parquet({literal}, hive_partitioning=false)").fetchall()]
    return {"path": relative, "bytes": size, "sha256": digest, "rows": rows,
            "schema": schema, "schema_sha256": hashlib.sha256(_canonical(schema)).hexdigest()}


def _resolve_files(con: duckdb.DuckDBPyConnection, manifest: dict[str, Any], output: Path) -> tuple[list[dict[str, Any]], list[Path]]:
    raw_files = manifest.get("files")
    if not isinstance(raw_files, list):
        raise ValueError("candidate files must be a list")
    records: dict[str, dict[str, Any]] = {}
    for item in raw_files:
        if not isinstance(item, dict):
            raise ValueError("candidate file record must be an object")
        rel = _safe_relative(item.get("path"), "candidate file path")
        if rel in records:
            raise ValueError("candidate file paths must be unique")
        records[rel] = item
    selected = {rel: item for rel, item in records.items() if rel.startswith("edges/")}
    if not selected:
        raise ValueError("candidate contains no edges files")
    _reject_tree(output / "edges")
    actual_paths = sorted(path for path in (output / "edges").rglob("*.parquet") if path.is_file())
    actual = {path.relative_to(output).as_posix(): path for path in actual_paths}
    if set(selected) != set(actual):
        raise ValueError("candidate edges file set does not match the current edges directory")
    verified: list[dict[str, Any]] = []
    paths: list[Path] = []
    for rel in sorted(selected):
        path = actual[rel]
        record = _file_record(con, path, output)
        expected = selected[rel]
        for key in ("bytes", "rows"):
            if type(expected.get(key)) is not int or expected[key] < 0:
                raise ValueError(f"candidate file {rel} {key} must be a nonnegative integer")
        _sha(expected.get("sha256"), f"candidate file {rel} sha256")
        for key in ("bytes", "sha256", "rows"):
            if expected.get(key) != record[key]:
                raise ValueError(f"candidate file {rel} {key} mismatch")
        if record["schema"] != _EDGE_SCHEMA or ("schema" in expected and expected["schema"] != record["schema"]):
            raise ValueError(f"candidate file {rel} schema mismatch")
        verified.append(record)
        paths.append(path)
    return verified, paths


def prepare_input(con: duckdb.DuckDBPyConnection, *, source_run: Path, candidate_manifest: Path,
                  candidate_sha256: str, expected_snapshot_at: date) -> dict[str, Any]:
    """Validate and expose only resolved edge files from a pinned candidate."""
    if not isinstance(con, duckdb.DuckDBPyConnection):
        raise TypeError("con must be a DuckDB connection")
    if not isinstance(expected_snapshot_at, date) or isinstance(expected_snapshot_at, datetime):
        raise ValueError("expected_snapshot_at must be a date")
    _sha(candidate_sha256, "candidate_sha256")
    source_run = Path(source_run).absolute()
    candidate_manifest = Path(candidate_manifest).absolute()
    _reject_reparse_ancestors(candidate_manifest)
    _reject_reparse_ancestors(source_run)
    if not candidate_manifest.resolve().is_relative_to(source_run.resolve()):
        raise ValueError("candidate manifest escaped source_run")
    with candidate_manifest.open("rb") as stream:
        raw = stream.read(_MAX_JSON + 1)
    if len(raw) > _MAX_JSON or hashlib.sha256(raw).hexdigest() != candidate_sha256:
        raise ValueError("candidate manifest SHA-256 mismatch")
    candidate = _read_json(candidate_manifest, raw)
    if candidate.get("status") != "RECOVERY_CANDIDATE" or candidate.get("resolution_status") != "PARTIAL" or candidate.get("ready_for_dependents") is not False:
        raise ValueError("candidate must be RECOVERY_CANDIDATE/PARTIAL and not ready")
    report = candidate.get("finalize_report")
    if not isinstance(report, dict):
        raise ValueError("candidate finalize_report is required")
    if report.get("resolution_status") != "PARTIAL" or report.get("ready_for_dependents") is not False:
        raise ValueError("finalize report must preserve PARTIAL and not ready")
    for section in ("input", "request", "prepare_report", "recovery"):
        if not isinstance(candidate.get(section), dict):
            raise ValueError(f"candidate {section} must be an object")
    _validate_run_id(report.get("run_id"))
    for key in ("input_sha256", "curated_run_id", "bronze_run_id"):
        value = report.get(key)
        if not isinstance(value, str) or not value.strip() or candidate["input"].get(key) != value:
            raise ValueError(f"candidate input and finalize {key} differ")
    for key in ("snapshot", "input_sha256"):
        if candidate["prepare_report"].get(key) != report.get(key):
            raise ValueError(f"candidate prepare and finalize {key} differ")
    if candidate.get("input", {}).get("snapshot") != expected_snapshot_at.isoformat():
        raise ValueError("candidate input snapshot does not match expected snapshot")
    if candidate.get("request", {}).get("run_id") != report.get("run_id"):
        raise ValueError("candidate request and finalize run_id differ")
    snapshot = report.get("snapshot")
    if snapshot != expected_snapshot_at.isoformat():
        raise ValueError("candidate snapshot does not match expected snapshot")
    timestamp = _parse_timestamp(candidate.get("input", {}).get("snapshot_timestamp"), "snapshot_timestamp")
    if timestamp.date() != expected_snapshot_at:
        raise ValueError("snapshot_timestamp UTC date does not match snapshot")
    for section in ("prepare_report", "finalize_report"):
        if "snapshot_timestamp" in candidate[section] and _parse_timestamp(candidate[section]["snapshot_timestamp"], section) != timestamp:
            raise ValueError(f"candidate {section} snapshot timestamp differs")
    output = _output_dir(Path(source_run), candidate.get("final_output"))
    policy = candidate.get("policy")
    try:
        policy_doc = validate_policy(policy)
    except (TypeError, ValueError) as exc:
        raise ValueError("candidate policy is not the approved dependencies/PARTIAL policy") from exc
    if policy_doc["unknown_published_at"] != "exclude" or policy_doc["unresolved"] != "partial":
        raise ValueError("candidate policy must exclude unknown publication and preserve unresolved as PARTIAL")
    policy_sha = policy.get("sha256")
    _sha(policy_sha, "policy_sha256")
    if report.get("policy_sha256") != policy_sha or candidate.get("prepare_report", {}).get("policy_sha256") != policy_sha:
        raise ValueError("candidate policy lineage does not match finalize report")
    files, paths = _resolve_files(con, candidate, output)
    # Ensure the view name cannot silently replace caller state.
    if con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name='diagnostic_edges'").fetchone()[0]:
        raise ValueError("diagnostic_edges view already exists")
    literals = ", ".join(_sql_literal(path) for path in paths)
    con.execute(f"CREATE VIEW diagnostic_edges AS SELECT * FROM read_parquet([{literals}], hive_partitioning=false)")
    schema = [[str(row[0]), str(row[1]).upper()] for row in con.execute("DESCRIBE diagnostic_edges").fetchall()]
    if schema != _EDGE_SCHEMA:
        raise ValueError("resolved edge schema mismatch")
    expected = {"snapshot_at": expected_snapshot_at.isoformat(), "snapshot_timestamp": timestamp,
                "run_id": report.get("run_id"), "input_sha256": report.get("input_sha256"),
                "curated_run_id": report.get("curated_run_id"), "bronze_run_id": report.get("bronze_run_id"),
                "policy_sha256": report.get("policy_sha256")}
    for key in ("input_sha256", "policy_sha256"):
        _sha(expected[key], key)
    checks = con.execute("""
      SELECT count(*) AS rows,
             coalesce(sum(declaration_count),0)::BIGINT AS resolved,
             count(*) FILTER (WHERE snapshot_at IS DISTINCT FROM ?::DATE OR snapshot_timestamp IS DISTINCT FROM ?::TIMESTAMPTZ
               OR run_id IS DISTINCT FROM ? OR input_sha256 IS DISTINCT FROM ? OR curated_run_id IS DISTINCT FROM ? OR bronze_run_id IS DISTINCT FROM ? OR policy_sha256 IS DISTINCT FROM ?
               OR source_package_id IS NULL OR target_package_id IS NULL
               OR source_package_id <= 0 OR target_package_id <= 0
               OR source_version IS NULL OR target_version IS NULL
               OR length(source_version) NOT BETWEEN 1 AND 100 OR length(target_version) NOT BETWEEN 1 AND 100
               OR contains(source_version, chr(0)) OR contains(target_version, chr(0))
               OR regexp_matches(source_version, '^\\s*$') OR regexp_matches(target_version, '^\\s*$')
               OR dependency_kinds IS NULL OR dependency_kinds IS DISTINCT FROM ['dependencies']
               OR declaration_count IS NULL OR declaration_count <= 0) AS invalid
      FROM diagnostic_edges
    """, [expected_snapshot_at, timestamp, expected["run_id"], expected["input_sha256"], expected["curated_run_id"], expected["bronze_run_id"], expected["policy_sha256"]]).fetchone()
    report_edges = report.get("output_counts", {}).get("edges")
    if type(report_edges) is not int or int(checks[0]) != sum(item["rows"] for item in files) or int(checks[0]) != report_edges:
        raise ValueError("edge row totals do not reconcile")
    for key in ("selected_declarations", "resolved_declarations", "unresolved_declarations"):
        if type(report.get(key)) is not int or report[key] < 0:
            raise ValueError(f"finalize report {key} must be nonnegative integer")
    if int(checks[1]) != report["resolved_declarations"] or int(checks[2]) != 0:
        raise ValueError("resolved edge content or declaration count mismatch")
    declared = report["selected_declarations"]
    unresolved = report["unresolved_declarations"]
    if declared - int(checks[1]) != unresolved:
        raise ValueError("resolved and unresolved declaration counts do not reconcile")
    statuses = report.get("declaration_status_counts")
    if not isinstance(statuses, dict) or any(type(value) is not int or value < 0 for value in statuses.values()) or sum(statuses.values()) != declared or statuses.get("RESOLVED", 0) != int(checks[1]):
        raise ValueError("declaration status counts do not reconcile")
    source_statuses = report.get("source_status_counts")
    if not isinstance(source_statuses, dict) or any(type(value) is not int or value < 0 for value in source_statuses.values()):
        raise ValueError("source status counts must be nonnegative integers")
    prepare_report = candidate.get("prepare_report", {})
    recovery = candidate.get("recovery", {})
    excluded = prepare_report.get("excluded_kind_counts")
    unknown = prepare_report.get("excluded_unknown_publication_versions")
    if excluded is not None and (not isinstance(excluded, dict) or any(type(n) is not int or n < 0 for n in excluded.values())):
        raise ValueError("invalid upstream excluded kind counts")
    if unknown is not None and (type(unknown) is not int or unknown < 0):
        raise ValueError("invalid upstream unknown publication count")
    gaps = recovery.get("gaps")
    if not isinstance(gaps, list) or any(not isinstance(gap, str) or not gap for gap in gaps):
        raise ValueError("recovery gaps must be preserved as a list of strings")
    return {"candidate_manifest": str(candidate_manifest), "candidate_sha256": candidate_sha256,
            "snapshot_at": expected_snapshot_at.isoformat(), "snapshot_timestamp": timestamp.isoformat().replace("+00:00", "Z"),
            "upstream_run_id": report.get("run_id"), "input_sha256": expected["input_sha256"], "policy_sha256": expected["policy_sha256"],
            "curated_run_id": expected["curated_run_id"], "bronze_run_id": expected["bronze_run_id"],
            "resolution_status": "PARTIAL", "ready_for_load": False, "files": files, "final_output": str(output),
            "rows": sum(item["rows"] for item in files), "resolved_declarations": int(checks[1]),
            "selected_declarations": declared, "unresolved_declarations": unresolved,
            "source_status_counts": source_statuses, "declaration_status_counts": statuses,
            "upstream_reported_excluded_kind_counts": excluded,
            "upstream_reported_excluded_unknown_publication_versions": unknown,
            "recovery_gaps": gaps,
            "recovery_output_hash_semantics": recovery.get("output_hash_semantics"),
            "input_schema": _EDGE_SCHEMA,
            "verification_scope": "PINNED_RESOLVED_EDGE_FILES", "full_source_target_population_verified": False,
            "input_data_validation": "PASSED", "policy_document": policy_doc}


def verify_input_files(source_run: Path, prepared: dict[str, Any]) -> None:
    """Recheck candidate and every selected file after aggregation."""
    source = Path(source_run).absolute()
    _reject_reparse_ancestors(source)
    manifest = Path(prepared["candidate_manifest"]).absolute()
    _reject_reparse_ancestors(manifest)
    try:
        manifest.resolve().relative_to(source.resolve())
    except ValueError as exc:
        raise ValueError("candidate manifest escaped source_run") from exc
    with manifest.open("rb") as stream:
        raw = stream.read(_MAX_JSON + 1)
    size, digest = len(raw), hashlib.sha256(raw).hexdigest()
    if digest != prepared["candidate_sha256"] or size > _MAX_JSON:
        raise ValueError("candidate manifest changed after preparation")
    candidate = _read_json(manifest, raw)
    output = _output_dir(source, candidate.get("final_output"))
    if output != Path(prepared["final_output"]).absolute():
        raise ValueError("final_output changed after preparation")
    _reject_tree(output / "edges")
    actual = sorted(path for path in (output / "edges").rglob("*.parquet") if path.is_file())
    expected = {item["path"]: item for item in prepared["files"]}
    if {path.relative_to(output).as_posix() for path in actual} != set(expected):
        raise ValueError("selected edge files changed after preparation")
    for path in actual:
        rel = path.relative_to(output).as_posix()
        original = expected[rel]
        if _sha256(path) != (original["bytes"], original["sha256"]):
            raise ValueError(f"edge file changed after preparation: {rel}")
