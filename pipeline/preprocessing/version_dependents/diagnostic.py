"""Count only resolved edges from a pinned PARTIAL run; never approve DB loading."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import time

import duckdb

from pipeline.preprocessing.version_dependents.artifact import _canonical, _epoch_us, _file_record, _reject_reparse_ancestors, _sql_literal, _utc, _validate_run_id, _validate_sha
from pipeline.preprocessing.version_dependents.diagnostic_input import prepare_input, verify_input_files

_FORMAT = "version-dependents-diagnostic-v1"
_MANIFEST = "diagnostic_manifest.json"
_COUNTS_SCHEMA = [
    ["package_id", "INTEGER"], ["version", "VARCHAR"], ["snapshot_at", "DATE"],
    ["snapshot_timestamp", "TIMESTAMP WITH TIME ZONE"],
    ["resolved_dependents_count", "INTEGER"], ["dataset_status", "VARCHAR"],
]
_LINEAGE_SCHEMA = [
    ["run_id", "VARCHAR"], ["snapshot_at", "DATE"],
    ["snapshot_timestamp", "TIMESTAMP WITH TIME ZONE"], ["upstream_run_id", "VARCHAR"],
    ["candidate_sha256", "VARCHAR"], ["input_sha256", "VARCHAR"], ["policy_sha256", "VARCHAR"],
    ["curated_run_id", "VARCHAR"], ["bronze_run_id", "VARCHAR"],
    ["verification_scope", "VARCHAR"], ["recovery_gaps_json", "VARCHAR"],
]
_QUALITY_SCHEMA = [
    ["run_id", "VARCHAR"], ["snapshot_at", "DATE"],
    ["snapshot_timestamp", "TIMESTAMP WITH TIME ZONE"], ["dataset_status", "VARCHAR"],
    ["ready_for_load", "BOOLEAN"], ["input_edge_rows", "BIGINT"], ["distinct_edges", "BIGINT"],
    ["duplicate_edges", "BIGINT"], ["target_versions", "BIGINT"],
    ["max_resolved_dependents_count", "BIGINT"], ["upstream_quality_json", "VARCHAR"],
    ["full_source_target_population_verified", "BOOLEAN"],
]
_SCHEMAS = {"resolved_counts.parquet": _COUNTS_SCHEMA,
            "lineage.parquet": _LINEAGE_SCHEMA, "quality.parquet": _QUALITY_SCHEMA}
_STAT_KEYS = {"input_edge_rows", "distinct_edges", "duplicate_edges", "target_versions",
              "max_resolved_dependents_count"}


def _code_hashes() -> dict:
    root = Path(__file__).parent
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in ("diagnostic.py", "diagnostic_input.py", "artifact.py",
                         "../requirements_resolution/policy.py", "../snapshot/policy.py")}


def _json_text(value) -> str:
    return _canonical(value).decode("utf-8")


def _rows(manifest: dict) -> tuple[tuple, tuple]:
    source, stats = manifest["input"], manifest["statistics"]
    snapshot = date.fromisoformat(manifest["snapshot_at"])
    timestamp = _utc(datetime.fromisoformat(manifest["snapshot_timestamp"].replace("Z", "+00:00")), snapshot)
    upstream_quality = {key: source[key] for key in (
        "selected_declarations", "resolved_declarations", "unresolved_declarations",
        "source_status_counts", "declaration_status_counts", "upstream_reported_excluded_kind_counts",
        "upstream_reported_excluded_unknown_publication_versions")}
    lineage = (manifest["run_id"], snapshot, timestamp, source["upstream_run_id"],
               source["candidate_sha256"], source["input_sha256"], source["policy_sha256"],
               source["curated_run_id"], source["bronze_run_id"], source["verification_scope"],
               _json_text(source["recovery_gaps"]))
    quality = (manifest["run_id"], snapshot, timestamp, "PARTIAL", False,
               stats["input_edge_rows"], stats["distinct_edges"], stats["duplicate_edges"],
               stats["target_versions"], stats["max_resolved_dependents_count"],
               _json_text(upstream_quality), False)
    return lineage, quality


def _write_row(con, path: Path, schema: list, values: tuple) -> None:
    columns = ", ".join(f"?::{kind} AS {name}" for name, kind in schema)
    con.execute(f"COPY (SELECT {columns}) TO {_sql_literal(path)} (FORMAT PARQUET, COMPRESSION ZSTD)", list(values))


def _progress(run_dir: Path, stage: str, **details) -> None:
    payload = {"stage": stage, "recorded_at_utc": datetime.now(timezone.utc).isoformat(), **details}
    temp = run_dir / "progress.next.json"
    temp.write_bytes(_canonical(payload))
    temp.replace(run_dir / "progress.json")


def build_diagnostic(*, source_run: Path, candidate_manifest: Path, candidate_sha256: str,
                     expected_snapshot_at: date, output_root: Path, run_id: str,
                     threads: int = 8, memory_limit: str = "8GB") -> dict:
    """Create an immutable diagnostic artifact; original inputs are read-only."""
    if type(expected_snapshot_at) is not date:
        raise ValueError("expected_snapshot_at must be a date")
    if type(threads) is not int or threads < 1:
        raise ValueError("threads must be a positive integer")
    _validate_run_id(run_id)
    _validate_sha(candidate_sha256, "candidate_sha256")
    source_run, candidate_manifest = Path(source_run).absolute(), Path(candidate_manifest).absolute()
    run_dir = Path(output_root).absolute() / f"snapshot={expected_snapshot_at}" / f"run_id={run_id}"
    _reject_reparse_ancestors(run_dir)
    if run_dir.resolve().is_relative_to(source_run.resolve()):
        raise ValueError("output must be outside the source run")
    run_dir.parent.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(exist_ok=False)
    output = run_dir / "outputs"
    output.mkdir()
    scratch = run_dir / "scratch"
    scratch.mkdir()
    started = time.perf_counter()
    timings = {}
    initial_code = _code_hashes()
    try:
        with duckdb.connect() as con:
            con.execute("SET enable_progress_bar=false")
            con.execute("SET threads=?", [threads])
            con.execute("SET memory_limit=?", [memory_limit])
            con.execute("SET temp_directory=?", [str(scratch)])
            _progress(run_dir, "VERIFYING_INPUT", threads=threads, memory_limit=memory_limit)
            before = time.perf_counter()
            prepared = prepare_input(con, source_run=source_run, candidate_manifest=candidate_manifest,
                                     candidate_sha256=candidate_sha256, expected_snapshot_at=expected_snapshot_at)
            timings["input_verification_seconds"] = time.perf_counter() - before
            _progress(run_dir, "AGGREGATING", input_edge_rows=prepared["rows"])
            before = time.perf_counter()
            con.execute("""CREATE TEMP TABLE diagnostic_counts AS
                SELECT target_package_id AS package_id, target_version AS version,
                       count(*)::BIGINT AS resolved_dependents_count
                FROM (SELECT DISTINCT source_package_id, source_version, target_package_id, target_version
                      FROM diagnostic_edges) AS unique_edges
                GROUP BY target_package_id, target_version""")
            count, total, maximum = con.execute("""SELECT count(*), coalesce(sum(resolved_dependents_count),0),
                        coalesce(max(resolved_dependents_count),0) FROM diagnostic_counts""").fetchone()
            if maximum > 2_147_483_647:
                raise ValueError("resolved_dependents_count exceeds INTEGER")
            if total > prepared["rows"]:
                raise ValueError("distinct edge count exceeds input rows")
            stats = {"input_edge_rows": prepared["rows"], "distinct_edges": int(total),
                     "duplicate_edges": prepared["rows"] - int(total), "target_versions": int(count),
                     "max_resolved_dependents_count": int(maximum)}
            timings["aggregation_seconds"] = time.perf_counter() - before
            _progress(run_dir, "WRITING_OUTPUT", **stats)
            before = time.perf_counter()
            snapshot = date.fromisoformat(prepared["snapshot_at"])
            stamp = _utc(datetime.fromisoformat(prepared["snapshot_timestamp"].replace("Z", "+00:00")), snapshot)
            con.execute(f"""COPY (SELECT package_id, version, ?::DATE AS snapshot_at,
                            ?::TIMESTAMPTZ AS snapshot_timestamp,
                            resolved_dependents_count::INTEGER AS resolved_dependents_count,
                            'PARTIAL'::VARCHAR AS dataset_status
                            FROM diagnostic_counts ORDER BY package_id, version)
                            TO {_sql_literal(output / 'resolved_counts.parquet')}
                            (FORMAT PARQUET, COMPRESSION ZSTD)""", [snapshot, stamp])
            manifest = {"format_version": _FORMAT, "artifact_status": "COMPLETE", "dataset_status": "PARTIAL",
                        "ready_for_load": False, "run_id": run_id, "snapshot_at": snapshot.isoformat(),
                        "snapshot_timestamp": stamp.isoformat().replace("+00:00", "Z"),
                        "metric_scope": "distinct_source_versions_on_resolved_edges_only",
                        "target_scope": "targets_present_in_resolved_edges_no_zero_population",
                        "input": prepared, "statistics": stats, "code_sha256": initial_code,
                        "runtime": {"duckdb_version": duckdb.__version__, "threads": threads, "memory_limit": memory_limit},
                        "timings": timings}
            lineage, quality = _rows(manifest)
            _write_row(con, output / "lineage.parquet", _LINEAGE_SCHEMA, lineage)
            _write_row(con, output / "quality.parquet", _QUALITY_SCHEMA, quality)
            manifest["files"] = [_file_record(output / name) for name in _SCHEMAS]
            timings["output_write_seconds"] = time.perf_counter() - before
        _progress(run_dir, "REVERIFYING_INPUT")
        before = time.perf_counter()
        verify_input_files(source_run, prepared)
        timings["input_reverification_seconds"] = time.perf_counter() - before
        _progress(run_dir, "VERIFYING_OUTPUT")
        before = time.perf_counter()
        _verify_outputs(output, manifest, manifest_present=False)
        timings["output_verification_seconds"] = time.perf_counter() - before
        timings["total_seconds"] = time.perf_counter() - started
        if _code_hashes() != initial_code:
            raise ValueError("diagnostic code changed during execution")
        body = _canonical(manifest)
        with (output / _MANIFEST).open("xb") as stream:
            stream.write(body)
        sha = hashlib.sha256(body).hexdigest()
        _progress(run_dir, "COMPLETE", dataset_status="PARTIAL", ready_for_load=False,
                  manifest_sha256=sha, statistics=stats, timings=timings)
        return {"run_dir": str(run_dir), "output_dir": str(output), "manifest_sha256": sha, "manifest": manifest}
    except Exception as exc:
        _progress(run_dir, "FAILED", error_type=type(exc).__name__, error=str(exc))
        raise


def _verify_outputs(output: Path, manifest: dict, *, manifest_present: bool) -> dict:
    expected_keys = {"format_version", "artifact_status", "dataset_status", "ready_for_load", "run_id",
                     "snapshot_at", "snapshot_timestamp", "metric_scope", "target_scope", "input",
                     "statistics", "code_sha256", "runtime", "timings", "files"}
    if not isinstance(manifest, dict) or set(manifest) != expected_keys:
        raise ValueError("invalid diagnostic manifest fields")
    if (manifest["format_version"] != _FORMAT or manifest["artifact_status"] != "COMPLETE" or
            manifest["dataset_status"] != "PARTIAL" or manifest["ready_for_load"] is not False or
            manifest["metric_scope"] != "distinct_source_versions_on_resolved_edges_only" or
            manifest["target_scope"] != "targets_present_in_resolved_edges_no_zero_population"):
        raise ValueError("invalid diagnostic-only contract")
    _validate_run_id(manifest["run_id"])
    source, stats = manifest["input"], manifest["statistics"]
    if not isinstance(source, dict) or not isinstance(stats, dict) or set(stats) != _STAT_KEYS:
        raise ValueError("invalid diagnostic input or statistics")
    if any(type(value) is not int or value < 0 for value in stats.values()):
        raise ValueError("invalid diagnostic statistics")
    if (source.get("resolution_status") != "PARTIAL" or source.get("ready_for_load") is not False or
            source.get("full_source_target_population_verified") is not False or
            source.get("verification_scope") != "PINNED_RESOLVED_EDGE_FILES" or
            source.get("snapshot_at") != manifest["snapshot_at"] or
            source.get("snapshot_timestamp") != manifest["snapshot_timestamp"] or
            type(source.get("rows")) is not int or source["rows"] != stats["input_edge_rows"] or
            stats["input_edge_rows"] != stats["distinct_edges"] + stats["duplicate_edges"]):
        raise ValueError("diagnostic input and output disagree")
    for field in ("candidate_sha256", "input_sha256", "policy_sha256"):
        _validate_sha(source.get(field), field)
    try:
        lineage, quality = _rows(manifest)
        snapshot, timestamp = lineage[1:3]
        if snapshot.isoformat() != manifest["snapshot_at"] or timestamp.isoformat().replace("+00:00", "Z") != manifest["snapshot_timestamp"]:
            raise ValueError("noncanonical snapshot")
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        raise ValueError("invalid diagnostic lineage") from exc
    entries = manifest["files"]
    if (not isinstance(entries, list) or len(entries) != 3 or
            any(not isinstance(e, dict) or set(e) != {"path", "bytes", "sha256", "rows", "schema", "schema_sha256"} for e in entries) or
            [e["path"] for e in entries] != list(_SCHEMAS)):
        raise ValueError("invalid diagnostic file inventory")
    _reject_reparse_ancestors(output)
    expected = set(_SCHEMAS) | ({_MANIFEST} if manifest_present else set())
    if {p.name for p in output.iterdir()} != expected:
        raise ValueError("extra or missing diagnostic files")
    for entry in entries:
        path = output / entry["path"]
        _reject_reparse_ancestors(path)
        if not path.is_file() or type(entry["bytes"]) is not int or type(entry["rows"]) is not int:
            raise ValueError("invalid diagnostic file")
        actual = _file_record(path)
        if actual != entry or actual["schema"] != _SCHEMAS[path.name]:
            raise ValueError("diagnostic file checksum, schema or row count mismatch")
        if path.name != "resolved_counts.parquet" and actual["rows"] != 1:
            raise ValueError("diagnostic metadata must have exactly one row")
    with tempfile.TemporaryDirectory(prefix="dependents-diagnostic-verify-") as temp, duckdb.connect() as con:
        con.execute("SET memory_limit='512MB'")
        con.execute("SET threads=2")
        con.execute("SET temp_directory=?", [temp])
        con.execute(f"CREATE VIEW counts AS SELECT * FROM read_parquet({_sql_literal(output / 'resolved_counts.parquet')}, hive_partitioning=false)")
        observed = con.execute("""SELECT count(*), count(DISTINCT (package_id,version)),
            coalesce(sum(resolved_dependents_count),0), coalesce(max(resolved_dependents_count),0),
            count(*) FILTER (WHERE package_id IS NULL OR package_id<=0 OR version IS NULL
                OR regexp_matches(version,'^\\s*$') OR length(version)>100 OR contains(version,chr(0))
                OR snapshot_at IS DISTINCT FROM ? OR epoch_us(snapshot_timestamp) IS DISTINCT FROM ?
                OR dataset_status IS DISTINCT FROM 'PARTIAL'
                OR resolved_dependents_count IS NULL OR resolved_dependents_count<=0)
            FROM counts""", [snapshot, _epoch_us(timestamp)]).fetchone()
        if (observed[0] != observed[1] or observed[4] != 0 or
                (int(observed[0]), int(observed[2]), int(observed[3])) !=
                (stats["target_versions"], stats["distinct_edges"], stats["max_resolved_dependents_count"])):
            raise ValueError("diagnostic count content mismatch")
        for name, expected_row in (("lineage.parquet", lineage), ("quality.parquet", quality)):
            # Compare the exact UTC instant without requiring DuckDB's optional pytz adapter.
            rows = con.execute(f"SELECT * REPLACE (epoch_us(snapshot_timestamp) AS snapshot_timestamp) FROM read_parquet({_sql_literal(output / name)}, hive_partitioning=false)").fetchall()
            normalized = expected_row[:2] + (_epoch_us(expected_row[2]),) + expected_row[3:]
            if rows != [normalized]:
                raise ValueError("diagnostic lineage or quality mismatch")
    return manifest


def verify_diagnostic(output_dir: Path, *, manifest_sha256: str) -> dict:
    """Validate saved files only; keep incomplete upstream status and original gaps."""
    _validate_sha(manifest_sha256, "manifest_sha256")
    output = Path(output_dir).absolute()
    path = output / _MANIFEST
    _reject_reparse_ancestors(path)
    if not path.is_file():
        raise ValueError("missing diagnostic manifest")
    with path.open("rb") as stream:
        raw = stream.read(8 * 1024 * 1024 + 1)
    if len(raw) > 8 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != manifest_sha256:
        raise ValueError("diagnostic manifest checksum mismatch")
    try:
        manifest = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("invalid diagnostic JSON") from exc
    return _verify_outputs(output, manifest, manifest_present=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolved-edge diagnostic counts; never DB-ready")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    for name in ("source-run", "candidate-manifest", "output-root"):
        build.add_argument(f"--{name}", type=Path, required=True)
    for name in ("candidate-sha256", "run-id"):
        build.add_argument(f"--{name}", required=True)
    build.add_argument("--snapshot-at", type=date.fromisoformat, required=True)
    build.add_argument("--threads", type=int, default=8)
    build.add_argument("--memory-limit", default="8GB")
    verify = commands.add_parser("verify")
    verify.add_argument("--output-dir", type=Path, required=True)
    verify.add_argument("--manifest-sha256", required=True)
    args = parser.parse_args()
    if args.command == "build":
        result = build_diagnostic(source_run=args.source_run, candidate_manifest=args.candidate_manifest,
                                  candidate_sha256=args.candidate_sha256, expected_snapshot_at=args.snapshot_at,
                                  output_root=args.output_root, run_id=args.run_id,
                                  threads=args.threads, memory_limit=args.memory_limit)
        manifest = result.pop("manifest")
    else:
        manifest = verify_diagnostic(args.output_dir, manifest_sha256=args.manifest_sha256)
        result = {"output_dir": str(args.output_dir.absolute()), "manifest_sha256": args.manifest_sha256}
    result.update(dataset_status="PARTIAL", ready_for_load=False, statistics=manifest["statistics"],
                  timings=manifest["timings"])
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
