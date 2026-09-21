"""Production quality from first-resolution summaries, without source deltas.

Declaration statuses retain raw multiplicity. Source statuses use the earliest
and latest finite resolution dates after summaries from all partitions merge.
"""
from __future__ import annotations

import json
import time
from typing import Any

from pipeline.preprocessing.version_dependents.historical_production_sql import _KNOWN_STATUS, _event_series, _require_schema
from pipeline.preprocessing.version_dependents.historical_reference import SOURCE_GAPS


SOURCE_SUMMARY_SCHEMA = {
    "source_package_id": "INTEGER", "source_version": "VARCHAR",
    "birth_index": "INTEGER", "dependency_error": "BOOLEAN",
    "declaration_count": "BIGINT", "never_resolved_count": "BIGINT",
    "first_any_resolved_index": "INTEGER", "last_finite_resolved_index": "INTEGER",
}


def _calendar(n: int) -> None:
    if type(n) is not int or not 0 < n <= 4096:
        raise ValueError("invalid snapshot count")


def summarize_sources(con, n: int, partition_id: int) -> dict[str, int]:
    """Keep one raw-declaration summary per source in this partition."""
    _calendar(n)
    if type(partition_id) is not int or partition_id < 0:
        raise ValueError("invalid partition id")
    _require_schema(con, "w_lookup_summary", {
        "lookup_id": "BIGINT", "first_resolved_index": "INTEGER"})
    if con.execute("""SELECT EXISTS(SELECT 1 FROM w_lookup_summary
        WHERE lookup_id IS NULL OR first_resolved_index<0 OR first_resolved_index>=?)
        OR EXISTS(SELECT 1 FROM w_lookup_summary GROUP BY lookup_id HAVING count(*)<>1)
        """, [n]).fetchone()[0]:
        raise ValueError("invalid or duplicate first-resolution lookup summary")
    if con.execute("""SELECT EXISTS(SELECT 1 FROM declarations d
        LEFT JOIN w_lookup_summary l USING(lookup_id)
        WHERE d.partition_id=? AND l.lookup_id IS NULL)""", [partition_id]).fetchone()[0]:
        raise ValueError("source declaration references a missing lookup summary")
    if con.execute("""SELECT EXISTS(SELECT 1 FROM declarations WHERE partition_id=?
        GROUP BY source_package_id,source_version
        HAVING count(DISTINCT birth_index)>1
           OR count(DISTINCT coalesce(dependency_error::VARCHAR,'NULL'))>1)""",
        [partition_id]).fetchone()[0]:
        raise ValueError("source flags or birth differ within partition")
    con.execute("""CREATE OR REPLACE TEMP TABLE p_source_summary AS
        WITH resolved AS (
            SELECT d.source_package_id,d.source_version,d.birth_index,d.dependency_error,
                   CASE WHEN l.first_resolved_index IS NOT NULL
                        THEN greatest(d.birth_index,l.first_resolved_index)::INTEGER END first_index
            FROM declarations d JOIN w_lookup_summary l USING(lookup_id)
            WHERE d.partition_id=?
        )
        SELECT source_package_id,source_version,min(birth_index)::INTEGER birth_index,
               bool_or(dependency_error) AS dependency_error,
               count(*)::BIGINT declaration_count,
               count(*) FILTER (WHERE first_index IS NULL)::BIGINT never_resolved_count,
               min(first_index)::INTEGER first_any_resolved_index,
               max(first_index)::INTEGER last_finite_resolved_index
        FROM resolved GROUP BY source_package_id,source_version
        """, [partition_id])
    _validate_sources(con, "p_source_summary", n)
    return {"source_summaries": int(con.execute("SELECT count(*) FROM p_source_summary").fetchone()[0])}


def _validate_sources(con, table: str, n: int) -> None:
    _require_schema(con, table, SOURCE_SUMMARY_SCHEMA)
    if con.execute(f"""SELECT EXISTS(SELECT 1 FROM {table} WHERE
          source_package_id IS NULL OR source_package_id<=0
          OR source_version IS NULL OR trim(source_version)=''
          OR birth_index IS NULL OR birth_index<0 OR birth_index>=?
          OR declaration_count IS NULL OR declaration_count<0
          OR never_resolved_count IS NULL OR never_resolved_count<0
          OR never_resolved_count>declaration_count
          OR (never_resolved_count=declaration_count AND
              (first_any_resolved_index IS NOT NULL OR last_finite_resolved_index IS NOT NULL))
          OR (never_resolved_count<declaration_count AND
              (first_any_resolved_index IS NULL OR last_finite_resolved_index IS NULL))
          OR first_any_resolved_index<birth_index
          OR last_finite_resolved_index<first_any_resolved_index
          OR last_finite_resolved_index>=?)""", [n, n]).fetchone()[0]:
        raise ValueError("invalid source first-resolution summary")


def _source_status_series(con, n: int) -> list[dict[str, int]]:
    # At most three intervals per normal source, irrespective of target changes.
    con.execute("""CREATE OR REPLACE TEMP TABLE _weighted_source_status_deltas AS
        WITH intervals AS (
            SELECT birth_index AS start_index,?::INTEGER AS end_index,
                   CASE WHEN dependency_error=true THEN 'DEPENDENCY_EXTRACTION_ERROR'
                        WHEN dependency_error IS NULL THEN 'DEPENDENCY_EXTRACTION_UNKNOWN'
                        ELSE 'OBSERVED_NO_DEPENDENCIES' END AS status
            FROM _weighted_sources
            WHERE dependency_error IS DISTINCT FROM false OR declaration_count=0
            UNION ALL
            SELECT birth_index,coalesce(first_any_resolved_index,?), 'UNRESOLVED'
            FROM _weighted_sources WHERE dependency_error=false AND declaration_count>0
            UNION ALL
            SELECT first_any_resolved_index,
                   CASE WHEN never_resolved_count=0 THEN last_finite_resolved_index ELSE ? END,
                   'PARTIAL'
            FROM _weighted_sources WHERE dependency_error=false AND declaration_count>0
                AND first_any_resolved_index IS NOT NULL
            UNION ALL
            SELECT last_finite_resolved_index,?, 'RESOLVED'
            FROM _weighted_sources WHERE dependency_error=false AND declaration_count>0
                AND never_resolved_count=0
        ), e AS (
            SELECT start_index AS snapshot_index,status,1::BIGINT delta FROM intervals
            WHERE start_index<end_index
            UNION ALL
            SELECT end_index,status,-1::BIGINT FROM intervals WHERE start_index<end_index
        ) SELECT snapshot_index::INTEGER AS snapshot_index,status,sum(delta)::BIGINT delta
          FROM e GROUP BY snapshot_index,status HAVING sum(delta)<>0
        """, [n, n, n, n])
    return _event_series(con, "_weighted_source_status_deltas", "snapshot_index", "status", n)


def finalize_quality_weighted(con, n: int) -> dict[str, Any]:
    """Merge source summaries globally and preserve every existing quality field."""
    started_at = time.perf_counter()
    _calendar(n)
    _validate_sources(con, "all_source_summary", n)
    for name, schema in {
        "all_status_deltas": {"snapshot_index": "INTEGER", "status": "VARCHAR", "delta": "BIGINT"},
        "all_counts": {"package_id": "INTEGER", "version": "VARCHAR", "start_index": "INTEGER",
                       "end_index": "INTEGER", "dependents_count": "BIGINT"},
        "target_population": {"package_id": "INTEGER", "name": "VARCHAR", "version": "VARCHAR", "birth_index": "INTEGER"},
    }.items():
        _require_schema(con, name, schema)
    if con.execute("""SELECT EXISTS(SELECT 1 FROM all_status_deltas
        WHERE snapshot_index IS NULL OR snapshot_index<0 OR snapshot_index>?
           OR delta IS NULL OR status IS NULL OR status NOT IN (SELECT unnest(?::VARCHAR[])))""",
        [n, sorted(_KNOWN_STATUS)]).fetchone()[0]:
        raise ValueError("invalid declaration status delta")
    if con.execute("""SELECT EXISTS(SELECT 1 FROM all_counts WHERE
        package_id IS NULL OR package_id<=0 OR version IS NULL OR trim(version)=''
        OR start_index IS NULL OR end_index IS NULL OR start_index<0
        OR end_index<=start_index OR end_index>?
        OR dependents_count IS NULL OR dependents_count<=0 OR dependents_count>2147483647)""",
        [n]).fetchone()[0]:
        raise ValueError("all_counts contains an invalid production dependent count interval")
    if con.execute("""SELECT EXISTS(SELECT 1 FROM (
        SELECT start_index,max(end_index) OVER(PARTITION BY package_id,version
            ORDER BY start_index,end_index ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) prior_end
        FROM all_counts) WHERE start_index<prior_end)""").fetchone()[0]:
        raise ValueError("overlapping count intervals across partitions")
    if con.execute("""SELECT EXISTS(SELECT 1 FROM target_population
        WHERE package_id IS NULL OR package_id<=0 OR version IS NULL OR trim(version)=''
           OR birth_index IS NULL OR birth_index<0 OR birth_index>=?)
        OR EXISTS(SELECT 1 FROM target_population GROUP BY package_id,version HAVING count(*)<>1)
        """, [n]).fetchone()[0]:
        raise ValueError("invalid target population")
    if con.execute("""SELECT EXISTS(SELECT 1 FROM all_counts c
        LEFT JOIN target_population t USING(package_id,version)
        WHERE t.package_id IS NULL OR c.start_index<t.birth_index)""").fetchone()[0]:
        raise ValueError("count target is absent or interval begins before target birth")
    con.execute("""CREATE OR REPLACE TEMP TABLE _weighted_sources AS
        SELECT source_package_id,source_version,min(birth_index)::INTEGER birth_index,
               bool_or(dependency_error) AS dependency_error,
               sum(declaration_count)::BIGINT declaration_count,
               sum(never_resolved_count)::BIGINT never_resolved_count,
               min(first_any_resolved_index)::INTEGER first_any_resolved_index,
               max(last_finite_resolved_index)::INTEGER last_finite_resolved_index,
               min(birth_index)::INTEGER _birth_min,
               max(birth_index)::INTEGER _birth_max,
               bool_or(dependency_error=true) _has_error,
               bool_or(dependency_error=false) _has_no_error,
               bool_or(dependency_error IS NULL) _has_unknown
        FROM all_source_summary GROUP BY source_package_id,source_version""")
    print(f"QUALITY_STAGE weighted_sources elapsed_seconds={time.perf_counter() - started_at:.3f}", flush=True)
    if con.execute("""SELECT EXISTS(SELECT 1 FROM _weighted_sources
        WHERE _birth_min<>_birth_max
           OR (_has_error AND _has_no_error)
           OR (_has_error AND _has_unknown)
           OR (_has_no_error AND _has_unknown))""").fetchone()[0]:
        raise ValueError("source flags or birth differ across partitions")
    _validate_sources(con, "_weighted_sources", n)
    source_states = _source_status_series(con, n)
    print(f"QUALITY_STAGE source_statuses elapsed_seconds={time.perf_counter() - started_at:.3f}", flush=True)
    declaration_states = _event_series(con, "all_status_deltas", "snapshot_index", "status", n)
    print(f"QUALITY_STAGE declaration_statuses elapsed_seconds={time.perf_counter() - started_at:.3f}", flush=True)
    target_birth = dict(con.execute("SELECT birth_index,count(*) FROM target_population GROUP BY birth_index").fetchall())
    source_birth = dict(con.execute("SELECT birth_index,count(*) FROM _weighted_sources GROUP BY birth_index").fetchall())
    declaration_birth = dict(con.execute("SELECT birth_index,sum(declaration_count)::BIGINT FROM _weighted_sources GROUP BY birth_index").fetchall())
    edge_deltas = dict(con.execute("""SELECT snapshot_index,sum(delta)::BIGINT FROM (
        SELECT start_index snapshot_index,dependents_count delta FROM all_counts
        UNION ALL SELECT end_index,-dependents_count FROM all_counts
        ) GROUP BY snapshot_index""").fetchall())
    totals = con.execute("""SELECT count(*),coalesce(sum(declaration_count),0),
        coalesce(sum(never_resolved_count),0) FROM _weighted_sources""").fetchone()
    total_sources, total_declarations, never_resolved = map(int, totals)
    targets = edges = selected = sources = 0
    rows = []
    for index in range(n):
        targets += int(target_birth.get(index, 0))
        sources += int(source_birth.get(index, 0))
        selected += int(declaration_birth.get(index, 0))
        edges += int(edge_deltas.get(index, 0))
        statuses, source_statuses = declaration_states[index], source_states[index]
        resolved = statuses.get("RESOLVED", 0)
        unresolved = selected - resolved
        if sum(statuses.values()) != selected or unresolved < 0 or edges < 0 or edges > resolved:
            raise ValueError("declaration quality conservation or distinct edge count failed")
        if sum(source_statuses.values()) != sources:
            raise ValueError("source quality conservation failed")
        row = {
            "source_versions": sources, "target_versions": targets, "selected_declarations": selected,
            "resolved_declarations": resolved, "unresolved_declarations": unresolved,
            "distinct_edges": edges, "duplicate_resolved_declarations": resolved - edges,
            "source_status_counts": source_statuses, "declaration_status_counts": statuses,
            "resolution_status": "COMPLETE" if unresolved == 0 and not any(source_statuses.get(k, 0) for k in SOURCE_GAPS) else "PARTIAL",
            "source_null_publication_excluded": 0, "source_future_excluded": total_sources - sources,
            "excluded_kind_declarations": {"peer_dependencies": 0, "optional_dependencies": 0},
            "target_rejections": {}, "quality_scope": "SELECTED_TARGET_DECLARATIONS_FROM_H1_ELIGIBLE_SOURCES",
            "source_status_scope": "SOURCES_WITH_SELECTED_TARGET_DECLARATIONS",
            "upstream_resolution_status": "PARTIAL",
            "prefiltered_exclusion_counts": "NOT_ORIGINAL_POPULATION_COUNTS",
            "upstream_exclusions_scope": "H1_MANIFEST",
        }
        rows.append((index, json.dumps(row, sort_keys=True, separators=(',', ':'))))
    if edges + int(edge_deltas.get(n, 0)) != 0:
        raise ValueError("count intervals do not close at calendar end")
    if selected != total_declarations or declaration_states[-1].get("RESOLVED", 0) != total_declarations - never_resolved:
        raise ValueError("source summary and declaration status totals differ")
    con.execute("CREATE OR REPLACE TEMP TABLE history_count_intervals AS SELECT * FROM all_counts")
    con.execute("""CREATE OR REPLACE TEMP TABLE history_target_population AS
        SELECT package_id,version,birth_index FROM target_population""")
    con.execute("CREATE OR REPLACE TEMP TABLE history_quality(snapshot_index INTEGER,quality_json VARCHAR)")
    con.executemany("INSERT INTO history_quality VALUES (?,?)", rows)
    print(f"QUALITY_STAGE quality_rows elapsed_seconds={time.perf_counter() - started_at:.3f}", flush=True)
    return {"partitions_merged": total_sources, "source_versions": total_sources,
            "target_versions": sum(target_birth.values()),
            "count_intervals": int(con.execute("SELECT count(*) FROM all_counts").fetchone()[0]),
            "quality_rows": n, "quality_scope": "SELECTED_TARGET_DECLARATIONS_FROM_H1_ELIGIBLE_SOURCES"}
