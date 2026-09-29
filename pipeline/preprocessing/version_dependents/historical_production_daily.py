"""Production daily output verification using one set of cumulative totals.

The immutable H4 helpers retain the original path. These adapters preserve the
actual output value comparisons while replacing repeated expected aggregates.
"""
from __future__ import annotations

import json
import re

from pipeline.preprocessing.requirements_resolution.input import file_sha256
from pipeline.preprocessing.requirements_resolution.policy import canonical_bytes, sha256
from pipeline.preprocessing.snapshot.policy import parse_timestamp
from pipeline.preprocessing.version_dependents.historical_artifact import FILES, FORMAT, METRIC, MODE, _file_info, _json_table, _load_views as _base_load_views, _path, _read_json, _sql_literal, _validate_sha
from pipeline.preprocessing.version_dependents.historical_production_cache import daily_totals


def _load_views(con, cache_dir, cache):
    _base_load_views(con, cache_dir)
    rows = [dict(snapshot_index=i, **row) for i, row in enumerate(
        daily_totals(con, len(cache["calendar"]), counts="cache_counts", targets="cache_targets"))]
    schema = [{"snapshot_index": "INTEGER", "target_versions": "BIGINT",
               "positive_target_versions": "BIGINT", "distinct_edges": "BIGINT",
               "max_dependents_count": "BIGINT"}]
    con.execute("CREATE TEMP TABLE production_daily_totals AS SELECT unnest(from_json(?,?),recursive:=true)",
                [json.dumps(rows), json.dumps(schema)])


def _expected_tables(con, cache, plan, index):
    day = plan["calendar"][index]["snapshot_at"]
    stamp = parse_timestamp(plan["calendar"][index]["snapshot_timestamp"]).isoformat(timespec="microseconds").replace("+00:00", "Z")
    plan_sha = sha256(plan)
    con.execute(f"""CREATE OR REPLACE TEMP VIEW expected_counts AS
        SELECT package_id, version, DATE '{day}' AS snapshot_at, TIMESTAMPTZ '{stamp}' AS snapshot_timestamp,
               dependents_count::INTEGER AS dependents_count
        FROM cache_counts WHERE start_index <= {index} AND {index} < end_index""")
    totals = con.execute("SELECT target_versions,positive_target_versions,distinct_edges,max_dependents_count FROM production_daily_totals WHERE snapshot_index=?", [index]).fetchone()
    if totals is None:
        raise ValueError("Missing prepared daily totals")
    targets, positive, total, maximum = totals
    original = con.execute("SELECT quality_json FROM cache_quality WHERE snapshot_index=?", [index]).fetchone()
    if original is None:
        raise ValueError("Missing cache snapshot quality")
    q = json.loads(original[0])
    if targets != q["target_versions"] or total != q["distinct_edges"] or positive > targets:
        raise ValueError("Cache count/quality/population mismatch")
    summary = {"source_versions": q["source_versions"], "target_versions": targets,
               "positive_target_versions": positive, "zero_target_versions": targets - positive,
               "selected_declarations": q["selected_declarations"], "resolved_declarations": q["resolved_declarations"],
               "unresolved_declarations": q["unresolved_declarations"], "distinct_edges": total,
               "duplicate_resolved_declarations": q["duplicate_resolved_declarations"],
               "max_dependents_count": maximum}
    body = {"run_plan_sha256": plan_sha, "snapshot_at": day, "snapshot_timestamp": stamp,
            "calculation_status": "COMPLETE", "resolution_status": q["resolution_status"],
            "ready_for_load": False, **summary, "quality_json": canonical_bytes(q).decode("utf-8")}
    schema = {"run_plan_sha256": "VARCHAR", "snapshot_at": "DATE", "snapshot_timestamp": "TIMESTAMPTZ",
              "calculation_status": "VARCHAR", "resolution_status": "VARCHAR", "ready_for_load": "BOOLEAN",
              **{key: "BIGINT" for key in summary}, "quality_json": "VARCHAR"}
    _json_table(con, "expected_quality", body, schema)
    lineage = {"run_plan_sha256": plan_sha, "cache_manifest_sha256": plan["cache_manifest_sha256"],
               **cache["lineage"], "snapshot_at": day, "snapshot_timestamp": stamp,
               "observed_snapshot_timestamp": cache["observed_snapshot_timestamp"], "calculation_mode": MODE,
               "metric_definition": METRIC, "verification_scope": "NORMALIZED_HISTORY_TABLES_ONLY",
               "generation_contract_sha256": sha256(plan["generation_contract"]), "ready_for_load": False}
    schema = {key: "VARCHAR" for key in lineage}
    schema.update(snapshot_at="DATE", snapshot_timestamp="TIMESTAMPTZ", observed_snapshot_timestamp="TIMESTAMPTZ",
                  ready_for_load="BOOLEAN")
    _json_table(con, "expected_lineage", lineage, schema)
    return {**summary, "resolution_status": q["resolution_status"]}


def _verify_snapshot(con, attempt, cache, plan, index, expected_sha):
    attempt = _path(attempt)
    if not re.fullmatch("[0-9a-f]{32}", attempt.name):
        raise ValueError("Invalid attempt identity")
    path = attempt / "snapshot_manifest.json"
    manifest = _read_json(path)
    if file_sha256(path) != expected_sha:
        raise ValueError("Snapshot manifest SHA mismatch")
    if {p.name for p in attempt.iterdir()} != {*FILES, "snapshot_manifest.json"}:
        raise ValueError("Snapshot attempt file set mismatch")
    summary = _expected_tables(con, cache, plan, index)
    required = {"format": FORMAT, "run_plan_sha256": sha256(plan), "cache_manifest_sha256": plan["cache_manifest_sha256"],
                "snapshot_index": index, **plan["calendar"][index], "attempt_id": attempt.name,
                "quality_summary": summary, "ready_for_load": False}
    if set(manifest) != set(required) | {"files"} or any(manifest.get(k) != v for k, v in required.items()):
        raise ValueError("Snapshot manifest identity or quality mismatch")
    if set(manifest["files"]) != set(FILES):
        raise ValueError("Snapshot manifest has unexpected output files")
    for filename, table in zip(FILES, ("expected_counts", "expected_quality", "expected_lineage")):
        target = attempt / filename
        actual_info = _file_info(con, target)
        if actual_info != manifest["files"][filename]:
            raise ValueError("Snapshot file SHA/schema/row count mismatch: " + filename)
        expected_schema = [[row[0], row[1]] for row in con.execute("DESCRIBE " + table).fetchall()]
        if actual_info["schema"] != expected_schema:
            raise ValueError("Snapshot file schema mismatch: " + filename)
        actual = f"SELECT * FROM read_parquet({_sql_literal(target)},hive_partitioning=false)"
        mismatch = con.execute(f"""SELECT EXISTS (
            (SELECT * FROM {table} EXCEPT ALL {actual}) UNION ALL
            ({actual} EXCEPT ALL SELECT * FROM {table}))""").fetchone()[0]
        if mismatch:
            raise ValueError("Snapshot values differ from pinned cache: " + filename)
    return manifest


def _read_completed(con, run_dir, cache, plan, index):
    day = plan["calendar"][index]["snapshot_at"]
    day_dir = _path(run_dir / ("snapshot=" + day))
    marker = day_dir / "complete.json"
    if not marker.exists():
        return None
    anchor = _read_json(marker)
    if (set(anchor) != {"snapshot_at", "attempt_id", "manifest_sha256", "run_plan_sha256"}
            or anchor["snapshot_at"] != day or anchor["run_plan_sha256"] != sha256(plan)
            or not isinstance(anchor["attempt_id"], str) or not re.fullmatch("[0-9a-f]{32}", anchor["attempt_id"])):
        raise ValueError("Snapshot completion marker identity mismatch")
    _validate_sha(anchor["manifest_sha256"], "snapshot manifest SHA")
    manifest = _verify_snapshot(con, day_dir / "attempts" / anchor["attempt_id"], cache, plan, index, anchor["manifest_sha256"])
    return {**anchor, "complete_sha256": file_sha256(marker), "quality_summary": manifest["quality_summary"]}



