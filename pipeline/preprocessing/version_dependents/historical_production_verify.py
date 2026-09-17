"""Independent small-input verifier for the historical production calculation.

This module deliberately recomputes every sample snapshot through the legacy
Node semver bridge.  It does not consume H3 interval/delta calculations; the
H4 cache is only read as an expected-result oracle.
"""
from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import time
from typing import Any, Iterable

import duckdb

from pipeline.preprocessing.requirements_resolution.bridge import NodeSession, discover_runtime
from pipeline.preprocessing.requirements_resolution.input import file_sha256
from pipeline.preprocessing.requirements_resolution.policy import canonical_bytes
from pipeline.preprocessing.version_dependents.historical_cache import verify_cache

MAX_DECLARATIONS = 100_000
MAX_LOOKUPS = 2_000
MAX_CANDIDATES = 100_000
WORKER = Path(__file__).with_name("historical_semver_worker.cjs")


def _files(paths: Iterable[Path]) -> list[str]:
    values = [Path(path).resolve() for path in paths]
    if not values or any(not path.is_file() or path.is_symlink() for path in values):
        raise ValueError("lookup interval files are missing or unsafe")
    return [str(path) for path in values]


def _read_rows(con: duckdb.DuckDBPyConnection, table: str, columns: str) -> list[tuple]:
    return con.execute(f"SELECT {columns} FROM {table}").fetchall()


def _cache_counts(cache_dir: Path, index: int) -> dict[tuple[int, str], int]:
    path = (Path(cache_dir) / "count_intervals.parquet").resolve()
    if not path.is_file() or path.is_symlink():
        raise ValueError("cache count_intervals.parquet is missing or unsafe")
    with duckdb.connect() as con:
        rows = con.execute(
            "SELECT package_id,version,dependents_count FROM read_parquet(?, hive_partitioning=false) "
            "WHERE start_index<=? AND ?<end_index", [str(path), index, index]
        ).fetchall()
    return {(int(pid), str(version)): int(count) for pid, version, count in rows}


def _manifest_calendar(manifest: dict[str, Any]) -> list[dict[str, str]]:
    calendar = manifest.get("calendar")
    if not isinstance(calendar, list) or not calendar:
        raise ValueError("prepared manifest has no calendar")
    for row in calendar:
        if not isinstance(row, dict) or not isinstance(row.get("snapshot_at"), str):
            raise ValueError("prepared manifest calendar is invalid")
    return calendar


def _runtime_contract(value: dict[str, Any]) -> dict[str, Any]:
    keys = ("node_version", "semver_version", "package_arg_version", "semver_sha256",
            "package_arg_sha256", "dependency_closure_sha256", "options",
            "equal_precedence_tie")
    if not isinstance(value, dict) or any(key not in value for key in keys):
        raise ValueError("runtime metadata is incomplete")
    return {key: value[key] for key in keys}


def _open_input(prepared_dir: Path, manifest: dict[str, Any]):
    # The production input adapter is intentionally imported lazily so this
    # verifier remains importable while the adapter is being assembled.
    from pipeline.preprocessing.version_dependents.historical_production_input import open_inputs
    con = duckdb.connect()
    opened = open_inputs(con, prepared_dir, manifest)
    return con, opened


def _close_input(con, opened) -> None:
    if opened is not None and opened is not con and hasattr(opened, "close"):
        opened.close()
    con.close()


def _runtime_fingerprint(runtime: dict[str, str] | None) -> dict[str, Any]:
    return discover_runtime() if runtime is None else runtime


def verify_sample(*, prepared_dir: Path, manifest_sha256: str, cache_dir: Path,
                  cache_sha256: str, lookup_interval_paths: list[Path], output: Path,
                  runtime=None, diagnostic_counts: Path | None = None) -> dict[str, Any]:
    """Verify a bounded prepared sample and write an exclusive JSON report."""
    prepared_dir, cache_dir, output = (Path(prepared_dir).resolve(), Path(cache_dir).resolve(),
                                       Path(output).resolve())
    if output.exists():
        raise ValueError("verification output already exists")
    started = time.monotonic()
    from pipeline.preprocessing.version_dependents.historical_production_input import verify_inputs
    manifest = verify_inputs(prepared_dir, manifest_sha256)
    if manifest.get("scope") != "SAMPLE":
        raise ValueError("sample verifier accepts only scope=SAMPLE")
    calendar = _manifest_calendar(manifest)
    cache_manifest = verify_cache(cache_dir, cache_sha256)
    cache_calendar = cache_manifest.get("calendar", [])
    if calendar != cache_calendar:
        raise ValueError("prepared and cache calendars differ")
    runtime = _runtime_fingerprint(runtime)
    con, opened = _open_input(prepared_dir, manifest)
    try:
        for table, limit in (("declarations", MAX_DECLARATIONS), ("lookups", MAX_LOOKUPS),
                             ("target_population", MAX_CANDIDATES)):
            if con.execute(f"SELECT count(*) FROM {table}").fetchone()[0] > limit:
                raise ValueError(f"prepared sample exceeds verifier bounds: {table}")
        declarations = _read_rows(con, "declarations", "source_package_id,source_version,birth_index,declared_name,requirement,lookup_id")
        lookups = _read_rows(con, "lookups", "lookup_id,declared_name,requirement")
        targets = _read_rows(con, "target_population", "package_id,name,version,birth_index")
        target_names = _read_rows(con, "target_names", "name,package_id,known_package")
        if len(declarations) > MAX_DECLARATIONS or len(lookups) > MAX_LOOKUPS or len(targets) > MAX_CANDIDATES:
            raise ValueError("prepared sample exceeds verifier bounds")
        lookup_by_id = {int(row[0]): (row[1], row[2]) for row in lookups}
        if len(lookup_by_id) != len(lookups):
            raise ValueError("duplicate lookup_id")
        selected = {str(name): (None if pid is None else int(pid), bool(known))
                    for name, pid, known in target_names}
        candidates_by_name: dict[str, list[tuple[str, int]]] = defaultdict(list)
        for pid, name, version, birth in targets:
            candidates_by_name[str(name)].append((str(version), int(birth)))
        source_rows_by_index: dict[int, list[tuple]] = defaultdict(list)
        for row in declarations:
            source_rows_by_index[int(row[2])].append(row)
        interval_con = duckdb.connect()
        interval_files = _files(lookup_interval_paths)
        parquet_list = "[" + ",".join("'" + path.replace("'", "''") + "'" for path in interval_files) + "]"
        interval_con.execute("CREATE VIEW production_lookup_intervals AS SELECT * FROM read_parquet(" + parquet_list + ", hive_partitioning=false)")
        results = []
        expected_mismatches = []
        total_resolved = 0
        with NodeSession(runtime, output.with_name(output.name + ".node.log"), worker=None) as node:
            node_meta = node.request({"op": "metadata"})
            if _runtime_contract(node_meta) != _runtime_contract(cache_manifest.get("runtime")):
                raise ValueError("legacy resolver runtime differs from cache runtime")
            for index, calendar_row in enumerate(calendar):
                available: dict[str, list[str]] = {}
                for name, values in candidates_by_name.items():
                    available[name] = [version for version, birth in values if birth <= index]
                mapping: dict[int, dict[str, Any]] = {}
                for name in sorted({str(row[1]) for row in lookups}):
                    package_info = selected.get(name, (None, False))
                    node.request({"op": "start", "name": name})
                    versions = available.get(name, [])
                    for start in range(0, len(versions), 4096):
                        node.request({"op": "candidates", "versions": versions[start:start + 4096]})
                    ids = [int(row[0]) for row in lookups if str(row[1]) == name]
                    for start in range(0, len(ids), 256):
                        batch_ids = ids[start:start + 256]
                        replies = node.request({"op": "resolve", "requirements": [lookup_by_id[item][1] for item in batch_ids]})
                        if len(replies) != len(batch_ids):
                            raise ValueError("legacy resolver returned a mismatched reply batch")
                        for lookup_id, reply in zip(batch_ids, replies):
                            if reply.get("requirement") != lookup_by_id[lookup_id][1]:
                                raise ValueError("legacy resolver changed the original requirement")
                            if reply.get("status") == "NO_ELIGIBLE_TARGET" and not package_info[1]:
                                reply = {**reply, "status": "UNMAPPED_TARGET_PACKAGE"}
                            mapping[lookup_id] = reply
                reference_con = con
                reference_con.execute("DROP TABLE IF EXISTS reference_mappings")
                reference_con.execute("CREATE TEMP TABLE reference_mappings(lookup_id BIGINT, status VARCHAR, normalized_range VARCHAR, target_version VARCHAR, target_package_id INTEGER)")
                mapped_values = []
                for lookup_id, reply in mapping.items():
                    name = lookup_by_id[lookup_id][0]
                    pid = selected.get(str(name), (None, False))[0] if reply.get("status") == "RESOLVED" else None
                    mapped_values.append((lookup_id, reply.get("status"), reply.get("normalized_range"), reply.get("target_version"), pid))
                if mapped_values:
                    reference_con.executemany("INSERT INTO reference_mappings VALUES (?,?,?,?,?)", mapped_values)
                active_sources = [row for birth, rows in source_rows_by_index.items() if birth <= index for row in rows]
                edges = set()
                for source_pid, source_version, _birth, _name, _req, lookup_id in active_sources:
                    reply = mapping[int(lookup_id)]
                    if reply.get("status") != "RESOLVED":
                        continue
                    name, _ = lookup_by_id[int(lookup_id)]
                    target_pid = selected.get(str(name), (None, False))[0]
                    target_version = reply.get("target_version")
                    if target_pid is not None and target_version is not None:
                        edges.add((int(source_pid), str(source_version), int(target_pid), str(target_version)))
                counts = defaultdict(int)
                for _sp, _sv, target_pid, target_version in edges:
                    counts[(target_pid, target_version)] += 1
                cache = _cache_counts(cache_dir, index)
                mismatch = {key: (counts.get(key, 0), cache.get(key, 0))
                             for key in set(counts) | set(cache) if counts.get(key, 0) != cache.get(key, 0)}
                expected_rows = interval_con.execute(
                    "SELECT lookup_id,status,normalized_range,target_package_id,target_version "
                    "FROM production_lookup_intervals WHERE start_index<=? AND ?<end_index",
                    [index, index]).fetchall()
                if len({int(row[0]) for row in expected_rows}) != len(expected_rows):
                    raise ValueError("production lookup intervals overlap at a snapshot")
                expected_by_lookup = {int(row[0]): tuple(row[1:]) for row in expected_rows}
                lookup_mismatches = []
                for lookup_id, reply in mapping.items():
                    name = lookup_by_id[lookup_id][0]
                    target_pid = selected.get(str(name), (None, False))[0] if reply.get("status") == "RESOLVED" else None
                    actual = (reply.get("status"), reply.get("normalized_range"), target_pid,
                              reply.get("target_version"))
                    if expected_by_lookup.get(lookup_id) != actual:
                        lookup_mismatches.append((lookup_id, expected_by_lookup.get(lookup_id), actual))
                if set(expected_by_lookup) != set(mapping):
                    lookup_mismatches.append(("coverage", len(expected_by_lookup), len(mapping)))
                actual_lookup_rows = sum(1 for reply in mapping.values() if reply.get("status") == "RESOLVED")
                row = {"snapshot_index": index, "snapshot_at": calendar_row["snapshot_at"],
                       "resolved_lookups": actual_lookup_rows, "distinct_edges": len(edges),
                       "target_keys": len(counts), "cache_target_keys": len(cache),
                       "lookup_interval_rows": len(expected_by_lookup),
                       "lookup_mismatch_count": len(lookup_mismatches),
                       "mismatch_count": len(mismatch) + len(lookup_mismatches)}
                results.append(row)
                if mismatch or lookup_mismatches:
                    expected_mismatches.append({**row,
                        "count_examples": [list(key) + list(value) for key, value in list(mismatch.items())[:20]],
                        "lookup_examples": [list(item) for item in lookup_mismatches[:20]]})
                total_resolved += actual_lookup_rows
        interval_con.close()
    finally:
        _close_input(con, opened)
    report = {"scope": "SAMPLE", "method": "LEGACY_NODE_PER_SNAPSHOT_RECOMPUTATION",
              "ready_for_load": False, "prepared_manifest_sha256": manifest_sha256,
              "cache_manifest_sha256": cache_sha256, "snapshot_count": len(calendar),
              "declaration_count": len(declarations), "lookup_count": len(lookups),
              "candidate_count": len(targets), "total_resolved_lookups": total_resolved,
              "snapshots": results, "mismatches": expected_mismatches,
              "mismatch_count": sum(row["mismatch_count"] for row in results),
              "runtime": node_meta, "elapsed_seconds": time.monotonic() - started,
              "diagnostic_counts": str(Path(diagnostic_counts).resolve()) if diagnostic_counts else None}
    if diagnostic_counts:
        diagnostic_path = Path(diagnostic_counts).resolve()
        if not diagnostic_path.is_file() or diagnostic_path.is_symlink():
            raise ValueError("diagnostic count parquet is missing or unsafe")
        with duckdb.connect() as diagnostic_con:
            cols = {str(row[0]) for row in diagnostic_con.execute("DESCRIBE SELECT * FROM read_parquet(?, hive_partitioning=false)", [str(diagnostic_path)]).fetchall()}
            required = {"package_id", "version", "snapshot_at", "snapshot_timestamp",
                        "resolved_dependents_count", "dataset_status"}
            if not required <= cols:
                raise ValueError("diagnostic count parquet has an incompatible schema")
            target_keys = {(int(pid), str(version)) for pid, _name, version, _birth in targets}
            latest = {key: value for key, value in _cache_counts(cache_dir, len(calendar) - 1).items()
                      if key in target_keys}
            diagnostic_con.execute("CREATE TEMP TABLE diagnostic_target_keys AS "
                                   "SELECT package_id,version FROM read_parquet(?, hive_partitioning=false)",
                                   [str(prepared_dir / "target_population.parquet")])
            latest_day = calendar[-1]["snapshot_at"]
            latest_timestamp = calendar[-1]["snapshot_timestamp"]
            diagnostic_rows = diagnostic_con.execute(
                "SELECT d.package_id,d.version,d.resolved_dependents_count "
                "FROM read_parquet(?, hive_partitioning=false) d JOIN diagnostic_target_keys k USING(package_id,version) "
                "WHERE d.snapshot_at=CAST(? AS DATE) "
                "AND d.snapshot_timestamp=CAST(? AS TIMESTAMPTZ)",
                [str(diagnostic_path), latest_day, latest_timestamp]).fetchall()
            actual_calendar = diagnostic_con.execute(
                "SELECT DISTINCT snapshot_at::VARCHAR,strftime(snapshot_timestamp AT TIME ZONE 'UTC', "
                "'%Y-%m-%dT%H:%M:%S.%fZ') "
                "FROM read_parquet(?, hive_partitioning=false)", [str(diagnostic_path)]).fetchall()
            expected_calendar = [(str(latest_day), str(latest_timestamp))]
            if actual_calendar != expected_calendar:
                raise ValueError("diagnostic count parquet snapshot does not match latest calendar")
            if len({(int(pid), str(version)) for pid, version, _count in diagnostic_rows}) != len(diagnostic_rows):
                raise ValueError("diagnostic count parquet has duplicate target keys")
            diagnostic = {(int(pid), str(version)): int(count) for pid, version, count in diagnostic_rows}
        diagnostic_mismatches = {key: (latest.get(key, 0), diagnostic.get(key, 0))
                                for key in target_keys
                                if latest.get(key, 0) != diagnostic.get(key, 0)}
        report["diagnostic_mismatch_count"] = len(diagnostic_mismatches)
        if diagnostic_mismatches:
            raise ValueError("latest diagnostic count mismatch: " + json.dumps(
                {"examples": [list(k) + list(v) for k, v in list(diagnostic_mismatches.items())[:20]]}, ensure_ascii=False))
    else:
        report["diagnostic_mismatch_count"] = None
    if report["mismatch_count"]:
        raise ValueError("sample verification mismatch: " + json.dumps(report, ensure_ascii=False))
    report["elapsed_seconds"] = time.monotonic() - started
    output.mkdir(parents=True, exist_ok=False)
    report_path = output / "report.json"
    report_path.write_bytes(canonical_bytes(report))
    report["report_path"] = str(report_path)
    report["report_sha256"] = file_sha256(report_path)
    return report
