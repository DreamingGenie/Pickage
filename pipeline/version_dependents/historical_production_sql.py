"""Partition-local production SQL for the historical dependents calculation.

This module consumes already-normalized declaration and resolver intervals.  It
does not create a source-by-date or target-by-date relation; all published
relations remain sparse intervals and event deltas.
"""
from __future__ import annotations

import json
from typing import Any

import duckdb

from .historical import STATUSES
from .historical_reference import SOURCE_GAPS

_SOURCE_STATUSES = SOURCE_GAPS | {"OBSERVED_NO_DEPENDENCIES", "RESOLVED", "PARTIAL", "UNRESOLVED"}
_KNOWN_STATUS = STATUSES | {"OBSERVED_NO_DEPENDENCIES"}


def _exists(con, name: str) -> bool:
    return bool(sum(row[0] for row in con.execute("""
        SELECT count(*) FROM information_schema.tables
        WHERE table_schema NOT IN ('pg_catalog','information_schema') AND table_name=?
        UNION ALL
        SELECT count(*) FROM duckdb_views() WHERE schema_name NOT IN ('pg_catalog','information_schema') AND view_name=?
    """, [name, name]).fetchall()))


def _require_schema(con, name: str, required: dict[str, str]) -> None:
    if not _exists(con, name):
        raise ValueError(f"missing input relation: {name}")
    actual = {str(row[0]): str(row[1]).upper().replace('"', '')
              for row in con.execute(f"DESCRIBE {name}").fetchall()}
    for col, typ in required.items():
        if actual.get(col) != typ:
            raise ValueError(f"{name}.{col} type mismatch: {actual.get(col)} != {typ}")


def _validate_lookup(con, n: int) -> None:
    bad = con.execute("""
      SELECT count(*) FROM lookup_intervals
      WHERE lookup_id IS NULL OR start_index IS NULL OR end_index IS NULL
         OR start_index < 0 OR start_index >= end_index OR end_index > ?
         OR status IS NULL OR status NOT IN (SELECT unnest(?::VARCHAR[]))
         OR (status='RESOLVED') <> (target_package_id IS NOT NULL AND target_version IS NOT NULL)
    """, [n, list(_KNOWN_STATUS)]).fetchone()[0]
    if bad:
        raise ValueError("lookup interval has invalid bounds or status/target pairing")
    gaps = con.execute("""
      WITH x AS (
        SELECT lookup_id, start_index, end_index,
               lag(end_index) OVER (PARTITION BY lookup_id ORDER BY start_index,end_index) AS prior_end
        FROM lookup_intervals
      ), s AS (
        SELECT lookup_id, min(start_index) first_start, max(end_index) last_end,
               count(*) FILTER (WHERE prior_end IS NOT NULL AND prior_end <> start_index) gaps
        FROM x GROUP BY lookup_id
      ) SELECT count(*) FROM s WHERE first_start<>0 OR last_end<>? OR gaps<>0
    """, [n]).fetchone()[0]
    if gaps:
        raise ValueError("lookup intervals do not cover 0..snapshot_count without gaps")
    if con.execute("""
      SELECT count(*) FROM lookup_intervals i
      JOIN target_population t ON i.target_package_id=t.package_id AND i.target_version=t.version
      WHERE i.status='RESOLVED' AND t.birth_index > i.start_index
    """).fetchone()[0]:
        raise ValueError("resolved lookup target is not born before its interval")
    if con.execute("""
      SELECT count(*) FROM lookup_intervals i
      WHERE i.status='RESOLVED' AND NOT EXISTS (
        SELECT 1 FROM target_population t
        WHERE t.package_id=i.target_package_id AND t.version=i.target_version)
    """).fetchone()[0]:
        raise ValueError("resolved lookup target is absent from target_population")


def _validate_inputs(con, n: int, partition_id: int) -> None:
    if type(n) is not int or not 0 < n <= 4096:
        raise ValueError("invalid snapshot count")
    if type(partition_id) is not int or partition_id < 0:
        raise ValueError("invalid partition id")
    _require_schema(con, "declarations", {
        "source_package_id": "INTEGER", "source_version": "VARCHAR", "source_name": "VARCHAR",
        "birth_index": "INTEGER", "dependency_error": "BOOLEAN",
        "original_declaration_index": "BIGINT", "declared_name": "VARCHAR", "requirement": "VARCHAR",
        "lookup_id": "BIGINT", "partition_id": "INTEGER"})
    _require_schema(con, "lookup_intervals", {
        "lookup_id": "BIGINT", "start_index": "INTEGER", "end_index": "INTEGER",
        "status": "VARCHAR", "normalized_range": "VARCHAR", "target_package_id": "INTEGER",
        "target_version": "VARCHAR"})
    _require_schema(con, "target_population", {
        "package_id": "INTEGER", "name": "VARCHAR", "version": "VARCHAR",
        "birth_index": "INTEGER", "partition_id": "INTEGER"})
    _validate_lookup(con, n)
    if con.execute("""
      SELECT count(*) FROM declarations WHERE partition_id=? AND
        (source_package_id IS NULL OR source_package_id<=0 OR source_version IS NULL
         OR trim(source_version)='' OR source_name IS NULL OR birth_index IS NULL
         OR birth_index<0 OR birth_index>=? OR original_declaration_index IS NULL
         OR original_declaration_index<0 OR lookup_id IS NULL OR lookup_id<0)
    """, [partition_id, n]).fetchone()[0]:
        raise ValueError("declaration has invalid identity, birth, or index")
    if con.execute("""
      SELECT count(*) FROM (
        SELECT source_package_id,source_version,original_declaration_index
        FROM declarations WHERE partition_id=? GROUP BY 1,2,3 HAVING count(*)<>1
      )
    """, [partition_id]).fetchone()[0]:
        raise ValueError("duplicate declaration key in partition")
    if con.execute("""
      SELECT count(*) FROM target_population
      WHERE package_id IS NULL OR package_id<=0 OR name IS NULL OR version IS NULL
         OR trim(version)='' OR birth_index IS NULL OR birth_index<0 OR birth_index>=?
         OR partition_id IS NULL OR partition_id<0
    """, [n]).fetchone()[0]:
        raise ValueError("target population has invalid row")
    if con.execute("""
      SELECT count(*) FROM (SELECT package_id,version FROM target_population
                           GROUP BY 1,2 HAVING count(*)<>1)
    """).fetchone()[0]:
        raise ValueError("target population key is duplicated")


def aggregate_partition(con: duckdb.DuckDBPyConnection, n: int, partition_id: int) -> dict[str, Any]:
    """Aggregate one declaration partition into sparse count and quality events."""
    _validate_inputs(con, n, partition_id)
    con.execute("DROP TABLE IF EXISTS _prod_declarations; DROP TABLE IF EXISTS _prod_edges; DROP TABLE IF EXISTS _prod_target_deltas; DROP TABLE IF EXISTS p_counts; DROP TABLE IF EXISTS p_sources; DROP TABLE IF EXISTS p_source_deltas; DROP TABLE IF EXISTS p_status_deltas")
    con.execute("""
      CREATE TEMP TABLE _prod_declarations AS
      SELECT d.*, greatest(d.birth_index, i.start_index)::INTEGER AS start_index,
             i.end_index::INTEGER AS end_index, i.status, i.target_package_id, i.target_version
      FROM declarations d JOIN lookup_intervals i USING (lookup_id)
      LEFT JOIN target_population t ON i.target_package_id=t.package_id AND i.target_version=t.version
      WHERE d.partition_id=?
    """, [partition_id])
    if con.execute("""
      SELECT count(*) FROM declarations d LEFT JOIN lookup_intervals i USING(lookup_id)
      WHERE d.partition_id=? AND i.lookup_id IS NULL
    """, [partition_id]).fetchone()[0]:
        raise ValueError("declaration references a missing lookup interval")
    # Source rows are deliberately scoped to this partition. finalize_quality
    # merges the rows by source identity across partitions.
    con.execute("""
      CREATE TEMP TABLE p_sources AS
      SELECT source_package_id, source_version, min(birth_index)::INTEGER birth_index,
             bool_or(dependency_error) AS dependency_error,
             count(DISTINCT original_declaration_index)::BIGINT AS declaration_count
      FROM _prod_declarations GROUP BY source_package_id,source_version
    """)
    con.execute("""
      CREATE TEMP TABLE p_source_deltas AS
      SELECT source_package_id, source_version, snapshot_index::INTEGER AS snapshot_index, sum(delta)::BIGINT delta
      FROM (
        SELECT source_package_id,source_version,start_index snapshot_index,1::BIGINT delta
        FROM _prod_declarations WHERE status='RESOLVED' AND start_index<end_index
        UNION ALL
        SELECT source_package_id,source_version,end_index,-1::BIGINT
        FROM _prod_declarations WHERE status='RESOLVED' AND start_index<end_index
      ) GROUP BY source_package_id,source_version,snapshot_index
    """)
    con.execute("""
      CREATE TEMP TABLE p_status_deltas AS
      SELECT snapshot_index::INTEGER AS snapshot_index, status, sum(delta)::BIGINT delta
      FROM (
        SELECT start_index snapshot_index,status,1::BIGINT delta FROM _prod_declarations
        WHERE start_index<end_index
        UNION ALL
        SELECT end_index,status,-1::BIGINT FROM _prod_declarations WHERE start_index<end_index
      ) GROUP BY snapshot_index,status
    """)
    # Running MAX creates islands for nested and adjacent declarations from the
    # same source version to the same target.  No date expansion occurs here.
    con.execute("""
      CREATE TEMP TABLE _prod_edges AS
      WITH ordered AS (
        SELECT source_package_id,source_version,target_package_id,target_version,start_index,end_index,original_declaration_index,
          max(end_index) OVER (PARTITION BY source_package_id,source_version,target_package_id,target_version
            ORDER BY start_index,end_index,original_declaration_index
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) prior_end
        FROM _prod_declarations WHERE status='RESOLVED' AND start_index<end_index
      ), marked AS (
        SELECT *, CASE WHEN prior_end IS NULL OR start_index>prior_end THEN 1 ELSE 0 END boundary
        FROM ordered
      ), islands AS (
        SELECT *, sum(boundary) OVER (PARTITION BY source_package_id,source_version,target_package_id,target_version
          ORDER BY start_index,end_index,original_declaration_index ROWS UNBOUNDED PRECEDING) island
        FROM marked
      ) SELECT source_package_id,source_version,target_package_id,target_version,
               min(start_index)::INTEGER start_index,max(end_index)::INTEGER end_index
        FROM islands GROUP BY source_package_id,source_version,target_package_id,target_version,island
    """)
    con.execute("""
      CREATE TEMP TABLE _prod_target_deltas AS
      SELECT target_package_id,target_version,snapshot_index,sum(delta)::BIGINT delta
      FROM (
        SELECT target_package_id,target_version,start_index snapshot_index,1::BIGINT delta FROM _prod_edges
        UNION ALL SELECT target_package_id,target_version,end_index,-1::BIGINT FROM _prod_edges
      ) GROUP BY target_package_id,target_version,snapshot_index
    """)
    con.execute("""
      CREATE TEMP TABLE p_counts AS
      WITH running AS (
        SELECT target_package_id package_id,target_version AS "version",snapshot_index,
               lead(snapshot_index,1,?) OVER w end_index,
               sum(delta) OVER (w ROWS UNBOUNDED PRECEDING)::BIGINT dependents_count
        FROM _prod_target_deltas
        WINDOW w AS (PARTITION BY target_package_id,target_version ORDER BY snapshot_index)
      ) SELECT package_id,version,snapshot_index::INTEGER AS start_index,end_index::INTEGER AS end_index,
               dependents_count::BIGINT AS dependents_count FROM running WHERE dependents_count>0 AND snapshot_index<?
    """, [n, n])
    if con.execute("SELECT count(*) FROM p_counts WHERE dependents_count<0 OR dependents_count>2147483647").fetchone()[0]:
        raise ValueError("invalid production dependent count")
    if con.execute("SELECT count(*) FROM p_counts c JOIN target_population t USING(package_id,version) WHERE c.start_index<t.birth_index").fetchone()[0]:
        raise ValueError("count interval begins before target birth")
    return {
        "partition_id": partition_id,
        "declarations": int(con.execute("SELECT count(*) FROM _prod_declarations").fetchone()[0]),
        "sources": int(con.execute("SELECT count(*) FROM p_sources").fetchone()[0]),
        "count_intervals": int(con.execute("SELECT count(*) FROM p_counts").fetchone()[0]),
        "resolved_declaration_events": int(con.execute("SELECT count(*) FROM p_source_deltas").fetchone()[0]),
    }


def _event_series(con, relation: str, index_col: str, value_col: str, n: int) -> list[dict[str, int]]:
    rows = con.execute(f"SELECT {index_col}, {value_col}, sum(delta)::BIGINT FROM {relation} GROUP BY 1,2").fetchall()
    events: dict[int, dict[str, int]] = {}
    for index, value, delta in rows:
        events.setdefault(int(index), {})[str(value)] = events.setdefault(int(index), {}).get(str(value), 0) + int(delta)
    active: dict[str, int] = {}
    result = []
    for index in range(n):
        for value, delta in events.get(index, {}).items():
            active[value] = active.get(value, 0) + delta
            if active[value] < 0:
                raise ValueError(f"negative event count in {relation}")
        result.append(dict(sorted((k, v) for k, v in active.items() if v)))
    for value, delta in events.get(n, {}).items():
        active[value] = active.get(value, 0) + delta
    if any(active.values()):
        raise ValueError(f"{relation} intervals do not close at calendar end")
    return result


def finalize_quality(con: duckdb.DuckDBPyConnection, n: int) -> dict[str, Any]:
    """Merge partition views and create the H4 cache tables plus quality rows."""
    if type(n) is not int or not 0 < n <= 4096:
        raise ValueError("invalid snapshot count")
    for name, schema in {
        "all_sources": {"source_package_id":"INTEGER","source_version":"VARCHAR","birth_index":"INTEGER","dependency_error":"BOOLEAN","declaration_count":"BIGINT"},
        "all_source_deltas": {"source_package_id":"INTEGER","source_version":"VARCHAR","snapshot_index":"INTEGER","delta":"BIGINT"},
        "all_status_deltas": {"snapshot_index":"INTEGER","status":"VARCHAR","delta":"BIGINT"},
        "all_counts": {"package_id":"INTEGER","version":"VARCHAR","start_index":"INTEGER","end_index":"INTEGER","dependents_count":"BIGINT"},
        "target_population": {"package_id":"INTEGER","name":"VARCHAR","version":"VARCHAR","birth_index":"INTEGER"},
    }.items():
        _require_schema(con, name, schema)
    if con.execute("SELECT count(*) FROM all_counts WHERE start_index<0 OR end_index<=start_index OR end_index>? OR dependents_count<=0", [n]).fetchone()[0]:
        raise ValueError("all_counts contains an invalid sparse interval")
    if con.execute("SELECT count(*) FROM all_source_deltas WHERE snapshot_index<0 OR snapshot_index>?", [n]).fetchone()[0]:
        raise ValueError("source delta is outside calendar")
    if con.execute("SELECT count(*) FROM all_status_deltas WHERE status NOT IN (SELECT unnest(?::VARCHAR[]))", [list(_KNOWN_STATUS)]).fetchone()[0]:
        raise ValueError("unknown status delta")
    if con.execute("""
      SELECT count(*) FROM (
        SELECT source_package_id,source_version
        FROM all_sources GROUP BY 1,2
        HAVING count(DISTINCT birth_index)>1
            OR count(DISTINCT coalesce(dependency_error::VARCHAR,'NULL'))>1
      )
    """).fetchone()[0]:
        raise ValueError("source flags or birth differ across partitions")
    con.execute("""
      CREATE OR REPLACE TEMP TABLE _prod_sources AS
      SELECT source_package_id,source_version,min(birth_index)::INTEGER birth_index,
             CASE WHEN bool_or(dependency_error) THEN true
                  WHEN count(*) FILTER (WHERE dependency_error IS NULL)>0 THEN NULL
                  ELSE false END AS dependency_error,
             sum(declaration_count)::BIGINT declaration_count
      FROM all_sources GROUP BY source_package_id,source_version
    """)
    if con.execute("SELECT count(*) FROM _prod_sources WHERE birth_index<0 OR birth_index>=? OR declaration_count<0", [n]).fetchone()[0]:
        raise ValueError("merged source metadata is invalid")
    # Duplicate declaration event keys across partition output would count the
    # same source transition twice; aggregate deltas and reject non-closing data.
    target_birth = {int(i): int(c) for i, c in con.execute("SELECT birth_index,count(*) FROM target_population GROUP BY birth_index").fetchall()}
    edge_events = con.execute("""
      SELECT snapshot_index,sum(delta)::BIGINT FROM (
        SELECT start_index snapshot_index,dependents_count::BIGINT delta FROM all_counts
        UNION ALL SELECT end_index,-dependents_count::BIGINT FROM all_counts
      ) GROUP BY snapshot_index
    """).fetchall()
    edge_by_index = {int(i): int(d) for i, d in edge_events}
    source_birth = {int(i): int(c) for i, c in con.execute("SELECT birth_index,sum(declaration_count) FROM _prod_sources GROUP BY birth_index").fetchall()}
    source_versions_birth = {int(i): int(c) for i, c in con.execute("SELECT birth_index,count(*) FROM _prod_sources GROUP BY birth_index").fetchall()}
    resolved_series = _event_series(con, "all_source_deltas", "snapshot_index", "'resolved'", n)
    target_count = edge_count = selected = 0
    quality_rows = []
    # Build source status event intervals once, using the compact source-event
    # relation; this avoids a source-by-snapshot expansion.
    con.execute("""
      CREATE OR REPLACE TEMP TABLE _prod_source_status_events AS
      WITH e AS (
        SELECT source_package_id,source_version,birth_index snapshot_index,0::BIGINT delta FROM _prod_sources
        UNION ALL SELECT source_package_id,source_version,snapshot_index,delta FROM all_source_deltas
      ), s AS (
        SELECT source_package_id,source_version,snapshot_index,sum(delta)::BIGINT delta FROM e GROUP BY 1,2,3
      ), r AS (
        SELECT s.*, sum(delta) OVER(PARTITION BY source_package_id,source_version ORDER BY snapshot_index ROWS UNBOUNDED PRECEDING) resolved_count,
               lead(snapshot_index,1,?) OVER(PARTITION BY source_package_id,source_version ORDER BY snapshot_index) next_index
        FROM s JOIN _prod_sources USING(source_package_id,source_version)
      ) SELECT r.snapshot_index,r.next_index,
        CASE WHEN p.dependency_error=true THEN 'DEPENDENCY_EXTRACTION_ERROR'
             WHEN p.dependency_error IS NULL THEN 'DEPENDENCY_EXTRACTION_UNKNOWN'
             WHEN p.declaration_count=0 THEN 'OBSERVED_NO_DEPENDENCIES'
             WHEN r.resolved_count=0 THEN 'UNRESOLVED'
             WHEN r.resolved_count=p.declaration_count THEN 'RESOLVED'
             ELSE 'PARTIAL' END status
      FROM r JOIN _prod_sources p USING(source_package_id,source_version)
      WHERE r.snapshot_index<r.next_index
    """, [n])
    # Aggregate before crossing the Python boundary: the source relation can
    # contain tens of millions of versions, while the quality series is bounded
    # by snapshot_count and the finite status vocabulary.
    source_status_events = con.execute("""
      SELECT snapshot_index,status,sum(delta)::BIGINT delta
      FROM (
        SELECT snapshot_index,status,1::BIGINT delta FROM _prod_source_status_events
        UNION ALL SELECT next_index,status,-1::BIGINT FROM _prod_source_status_events
      ) GROUP BY snapshot_index,status
    """).fetchall()
    source_status_at: dict[int, dict[str, int]] = {}
    for index, status, delta in source_status_events:
        source_status_at.setdefault(int(index), {})[str(status)] = source_status_at.setdefault(int(index), {}).get(str(status), 0) + int(delta)
    active_source_status: dict[str, int] = {}
    decl_status = _event_series(con, "all_status_deltas", "snapshot_index", "status", n)
    for index in range(n):
        for status, delta in source_status_at.get(index, {}).items():
            active_source_status[status] = active_source_status.get(status, 0) + delta
        target_count += target_birth.get(index, 0)
        selected += source_birth.get(index, 0)
        edge_count += edge_by_index.get(index, 0)
        resolved = int(resolved_series[index].get("resolved", 0))
        statuses = decl_status[index]
        unresolved = selected - resolved
        if resolved < 0 or unresolved < 0 or sum(statuses.values()) != selected:
            raise ValueError("declaration quality conservation failed")
        duplicate = resolved - edge_count
        if duplicate < 0:
            raise ValueError("distinct edge count exceeds resolved declarations")
        row = {
            "source_versions": sum(source_versions_birth.get(i, 0) for i in range(index + 1)),
            "target_versions": target_count, "selected_declarations": selected,
            "resolved_declarations": resolved, "unresolved_declarations": unresolved,
            "distinct_edges": edge_count, "duplicate_resolved_declarations": duplicate,
            "source_status_counts": dict(sorted((k, v) for k, v in active_source_status.items() if v)),
            "declaration_status_counts": statuses,
            "resolution_status": "COMPLETE" if unresolved == 0 and not any(active_source_status.get(k, 0) for k in SOURCE_GAPS) else "PARTIAL",
            "source_null_publication_excluded": 0, "source_future_excluded": sum(source_versions_birth.get(i, 0) for i in range(index + 1, n)),
            "excluded_kind_declarations": {"peer_dependencies": 0, "optional_dependencies": 0},
            "target_rejections": {}, "quality_scope": "SELECTED_TARGET_DECLARATIONS_FROM_H1_ELIGIBLE_SOURCES",
            "source_status_scope": "SOURCES_WITH_SELECTED_TARGET_DECLARATIONS",
            "upstream_resolution_status": "PARTIAL",
            "prefiltered_exclusion_counts": "NOT_ORIGINAL_POPULATION_COUNTS",
            "upstream_exclusions_scope": "H1_MANIFEST",
        }
        quality_rows.append((index, json.dumps(row, sort_keys=True, separators=(',', ':'))))
    con.execute("""CREATE OR REPLACE TEMP TABLE history_count_intervals AS
      SELECT package_id::INTEGER AS package_id, version AS version,
             start_index::INTEGER AS start_index, end_index::INTEGER AS end_index,
             dependents_count::BIGINT AS dependents_count
      FROM all_counts WHERE dependents_count>0""")
    con.execute("""CREATE OR REPLACE TEMP TABLE history_target_population AS
      SELECT package_id::INTEGER AS package_id, version AS version,
             birth_index::INTEGER AS birth_index FROM target_population""")
    con.execute("CREATE OR REPLACE TEMP TABLE history_quality(snapshot_index INTEGER,quality_json VARCHAR)")
    con.executemany("INSERT INTO history_quality VALUES (?,?)", quality_rows)
    return {
        "partitions_merged": int(con.execute("SELECT count(DISTINCT source_package_id || ':' || source_version) FROM all_sources").fetchone()[0]),
        "source_versions": int(con.execute("SELECT count(*) FROM _prod_sources").fetchone()[0]),
        "target_versions": int(con.execute("SELECT count(*) FROM target_population").fetchone()[0]),
        "count_intervals": int(con.execute("SELECT count(*) FROM history_count_intervals").fetchone()[0]),
        "quality_rows": n,
        "quality_scope": "SELECTED_TARGET_DECLARATIONS_FROM_H1_ELIGIBLE_SOURCES",
    }
