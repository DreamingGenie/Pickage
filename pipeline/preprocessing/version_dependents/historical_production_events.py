"""Weighted source births and lookup transitions for production aggregation."""
from __future__ import annotations

from collections import Counter
from itertools import groupby
import json
import time

from pipeline.preprocessing.version_dependents.historical import INT_MAX
from pipeline.preprocessing.version_dependents.historical_production_sql import _require_schema, _validate_inputs
from pipeline.preprocessing.version_dependents.historical_production_quality import summarize_sources

_BATCH_SIZE = 8192
_VALIDATION_BUCKET_TARGET_ROWS = 20_000_000
_EVENT_JSON = '[{"package_id":"INTEGER","version":"VARCHAR","snapshot_index":"INTEGER","delta":"BIGINT"}]'


def _validation_bucket_count(con, relation: str) -> int:
    """Choose bounded validation partitions without changing validation semantics."""
    rows = int(con.execute(f"SELECT count(*) FROM {relation}").fetchone()[0])
    return min(16, max(1, (rows + _VALIDATION_BUCKET_TARGET_ROWS - 1) // _VALIDATION_BUCKET_TARGET_ROWS))


def validate_weighted_inputs(con, n: int) -> dict[str, int]:
    """Check immutable prepared input globally, before resolver partitions exist."""
    if type(n) is not int or not 0 < n <= 4096:
        raise ValueError("invalid snapshot count")
    for name, schema in {
        "target_names": {"name": "VARCHAR", "package_id": "INTEGER", "known_package": "BOOLEAN", "partition_id": "INTEGER"},
        "target_population": {"package_id": "INTEGER", "name": "VARCHAR", "version": "VARCHAR", "birth_index": "INTEGER", "partition_id": "INTEGER"},
        "lookups": {"lookup_id": "BIGINT", "declared_name": "VARCHAR", "requirement": "VARCHAR", "partition_id": "INTEGER"},
        "declarations": {"source_package_id": "INTEGER", "source_version": "VARCHAR", "source_name": "VARCHAR", "birth_index": "INTEGER",
                         "dependency_error": "BOOLEAN", "original_declaration_index": "BIGINT", "declared_name": "VARCHAR",
                         "requirement": "VARCHAR", "lookup_id": "BIGINT", "partition_id": "INTEGER"},
    }.items():
        _require_schema(con, name, schema)
    if con.execute("""SELECT EXISTS(SELECT 1 FROM target_names WHERE name IS NULL
        OR partition_id IS NULL OR partition_id<0 OR known_package IS NULL
        OR known_package<>(package_id IS NOT NULL) OR package_id<=0)
        OR EXISTS(SELECT 1 FROM target_names GROUP BY name HAVING count(*)<>1)
        OR EXISTS(SELECT 1 FROM target_names WHERE package_id IS NOT NULL
                  GROUP BY package_id HAVING count(*)<>1)""").fetchone()[0]:
        raise ValueError("target name/package id mapping is not one-to-one")
    if con.execute("""SELECT EXISTS(SELECT 1 FROM lookups l LEFT JOIN target_names t ON l.declared_name=t.name
        WHERE l.lookup_id IS NULL OR l.lookup_id<0 OR t.name IS NULL
           OR l.partition_id IS DISTINCT FROM t.partition_id)
        OR EXISTS(SELECT 1 FROM lookups GROUP BY lookup_id HAVING count(*)<>1)
        OR EXISTS(SELECT 1 FROM lookups GROUP BY declared_name,requirement HAVING count(*)<>1)""").fetchone()[0]:
        raise ValueError("lookup name/partition mapping or identity is invalid")
    if con.execute("""SELECT EXISTS(SELECT 1 FROM target_population t LEFT JOIN target_names p ON p.name=t.name
        WHERE p.name IS NULL OR t.package_id IS DISTINCT FROM p.package_id
           OR t.partition_id IS DISTINCT FROM p.partition_id OR t.package_id IS NULL
           OR t.version IS NULL OR trim(t.version)='' OR t.birth_index IS NULL
           OR t.birth_index<0 OR t.birth_index>=?)
        OR EXISTS(SELECT 1 FROM target_population GROUP BY package_id,version HAVING count(*)<>1)
        """, [n]).fetchone()[0]:
        raise ValueError("target population mapping or birth is invalid")
    if con.execute("""SELECT EXISTS(SELECT 1 FROM declarations d LEFT JOIN lookups l USING(lookup_id)
        WHERE l.lookup_id IS NULL OR d.declared_name IS DISTINCT FROM l.declared_name
           OR d.requirement IS DISTINCT FROM l.requirement OR d.partition_id IS DISTINCT FROM l.partition_id
           OR d.source_package_id IS NULL OR d.source_package_id<=0 OR d.source_version IS NULL
           OR trim(d.source_version)='' OR d.source_name IS NULL OR d.birth_index IS NULL
           OR d.birth_index<0 OR d.birth_index>=? OR d.original_declaration_index IS NULL
           OR d.original_declaration_index<0)
        """, [n]).fetchone()[0]:
        raise ValueError("declaration identity or lookup mapping is invalid")
    buckets = _validation_bucket_count(con, "declarations")
    for bucket in range(buckets):
        if con.execute(f"""SELECT EXISTS(
                SELECT 1 FROM declarations
                WHERE source_package_id IS NULL OR hash(source_package_id) % {buckets} = {bucket}
                GROUP BY source_package_id,source_version,original_declaration_index
                HAVING count(*)<>1)""").fetchone()[0]:
            raise ValueError("declaration identity or lookup mapping is invalid")
    return {"target_names": int(con.execute("SELECT count(*) FROM target_names").fetchone()[0]),
            "lookups": int(con.execute("SELECT count(*) FROM lookups").fetchone()[0])}


def _validate_partition(con, n, partition_id):
    # Newly generated intervals are checked even after the prepared input check.
    _validate_inputs(con, n, partition_id)
    if con.execute("""SELECT EXISTS(SELECT 1 FROM lookup_intervals i LEFT JOIN lookups l USING(lookup_id)
        LEFT JOIN target_names t ON t.name=l.declared_name WHERE l.lookup_id IS NULL
           OR (i.status='RESOLVED' AND i.target_package_id IS DISTINCT FROM t.package_id))
        OR EXISTS(SELECT 1 FROM declarations d LEFT JOIN lookups l USING(lookup_id)
           WHERE d.partition_id=? AND (l.lookup_id IS NULL OR d.declared_name IS DISTINCT FROM l.declared_name
               OR d.requirement IS DISTINCT FROM l.requirement OR d.partition_id IS DISTINCT FROM l.partition_id))
        OR EXISTS(SELECT 1 FROM declarations d LEFT JOIN lookup_intervals i USING(lookup_id)
                  WHERE d.partition_id=? AND i.lookup_id IS NULL)""", [partition_id, partition_id]).fetchone()[0]:
        raise ValueError("declaration or resolved target references a missing or mismatched lookup")
    if con.execute("""SELECT EXISTS(SELECT 1 FROM declarations WHERE partition_id=?
        GROUP BY source_package_id,source_version HAVING count(DISTINCT birth_index)>1
        OR count(DISTINCT coalesce(dependency_error::VARCHAR,'NULL'))>1)""", [partition_id]).fetchone()[0]:
        raise ValueError("source flags or birth differ within partition")
    con.execute("""CREATE OR REPLACE TEMP TABLE w_lookup_summary AS
        SELECT lookup_id,min(start_index) FILTER(WHERE status='RESOLVED')::INTEGER first_resolved_index
        FROM lookup_intervals GROUP BY lookup_id""")
    if con.execute("""SELECT EXISTS(SELECT 1 FROM w_lookup_summary s JOIN lookup_intervals i USING(lookup_id)
        WHERE s.first_resolved_index IS NOT NULL AND i.start_index>=s.first_resolved_index
          AND i.status<>'RESOLVED')""").fetchone()[0]:
        raise ValueError("lookup resolution monotonicity failed")


def _prepare_weights(con, partition_id):
    con.execute("""CREATE OR REPLACE TEMP TABLE _weighted_unique AS
        SELECT DISTINCT source_package_id,source_version,declared_name,lookup_id,birth_index
        FROM declarations WHERE partition_id=?""", [partition_id])
    con.execute("""CREATE OR REPLACE TEMP TABLE _weighted_pairs AS
        SELECT source_package_id,source_version,declared_name,count(*)::BIGINT lookup_count
        FROM _weighted_unique GROUP BY 1,2,3""")
    con.execute("""CREATE OR REPLACE TEMP TABLE _weighted_fast AS
        SELECT u.lookup_id,u.birth_index,count(*)::BIGINT source_weight
        FROM _weighted_unique u JOIN _weighted_pairs p USING(source_package_id,source_version,declared_name)
        WHERE p.lookup_count=1 GROUP BY u.lookup_id,u.birth_index""")
    con.execute("""CREATE OR REPLACE TEMP TABLE _weighted_fallback AS
        SELECT u.* FROM _weighted_unique u JOIN _weighted_pairs p USING(source_package_id,source_version,declared_name)
        WHERE p.lookup_count>1""")
    con.execute("""CREATE OR REPLACE TEMP TABLE _weighted_decl AS
        SELECT lookup_id,birth_index,count(*)::BIGINT declaration_weight
        FROM declarations WHERE partition_id=? GROUP BY lookup_id,birth_index""", [partition_id])
    pairs, fast, fallback, expected_u = map(int, con.execute("""SELECT count(*),
        count(*) FILTER(WHERE lookup_count=1),count(*) FILTER(WHERE lookup_count>1),
        coalesce(sum(lookup_count),0) FROM _weighted_pairs""").fetchone())
    weight = int(con.execute("SELECT coalesce(sum(source_weight),0) FROM _weighted_fast").fetchone()[0])
    fallback_u = int(con.execute("SELECT count(*) FROM _weighted_fallback").fetchone()[0])
    raw = int(con.execute("SELECT count(*) FROM declarations WHERE partition_id=?", [partition_id]).fetchone()[0])
    if (pairs != fast + fallback or weight != fast or weight + fallback_u != expected_u
            or raw != con.execute("SELECT coalesce(sum(declaration_weight),0) FROM _weighted_decl").fetchone()[0]):
        raise ValueError("fast/fallback or raw declaration weight conservation failed")
    return {"raw_declarations": raw, "fast_pairs": fast, "fallback_pairs": fallback,
            "fallback_lookup_rows": fallback_u,
            "source_weight_bins": int(con.execute("SELECT count(*) FROM _weighted_fast").fetchone()[0]),
            "declaration_weight_bins": int(con.execute("SELECT count(*) FROM _weighted_decl").fetchone()[0])}


def _stream_rows(cursor):
    while rows := cursor.fetchmany(_BATCH_SIZE):
        yield from rows


def _sweep(con, n):
    # Physical scratch input is visible to a separate reader connection. Output
    # inserts cannot invalidate the reader's result or require a full Python list.
    con.execute("CREATE OR REPLACE TEMP TABLE _weighted_events(package_id INTEGER,version VARCHAR,snapshot_index INTEGER,delta BIGINT)")
    con.execute("""CREATE OR REPLACE TABLE _weighted_stream AS
        SELECT lookup_id,birth_index AS snapshot_index,1 AS kind,NULL::VARCHAR status,
               NULL::INTEGER target_package_id,NULL::VARCHAR target_version,source_weight AS weight FROM _weighted_fast
        UNION ALL SELECT lookup_id,birth_index,2,NULL,NULL,NULL,declaration_weight FROM _weighted_decl
        UNION ALL SELECT i.lookup_id,i.start_index,0,i.status,i.target_package_id,i.target_version,0::BIGINT
          FROM lookup_intervals i WHERE EXISTS(SELECT 1 FROM _weighted_decl d WHERE d.lookup_id=i.lookup_id)
        UNION ALL SELECT lookup_id,?::INTEGER,0,NULL,NULL,NULL,0::BIGINT FROM _weighted_decl GROUP BY lookup_id
        """, [n])
    status_events = Counter()
    buffer = []
    emitted = 0
    batches = 0

    def flush():
        nonlocal batches
        if buffer:
            con.execute("INSERT INTO _weighted_events SELECT unnest(from_json(?,?),recursive:=true)",
                        [json.dumps(buffer, ensure_ascii=False), _EVENT_JSON])
            buffer.clear()
            batches += 1

    def emit(target, index, delta):
        nonlocal emitted
        if target is None or delta == 0:
            return
        buffer.append({"package_id": target[0], "version": target[1], "snapshot_index": index, "delta": delta})
        emitted += 1
        if len(buffer) >= _BATCH_SIZE:
            flush()

    reader = con.cursor()
    try:
        reader.execute("SELECT * FROM _weighted_stream ORDER BY lookup_id,snapshot_index,kind")
        current_id = None
        active_source = active_declarations = 0
        old_target = old_status = None
        for (lookup_id, index), rows in groupby(_stream_rows(reader), key=lambda row: (row[0], row[1])):
            if lookup_id != current_id:
                if old_target is not None or old_status is not None:
                    raise ValueError("lookup event stream does not close")
                current_id = lookup_id
                active_source = active_declarations = 0
            new_target, new_status = old_target, old_status
            source_birth = declaration_birth = 0
            for _lid, _index, kind, status, target_id, version, weight in rows:
                if kind == 0:
                    new_status = status
                    new_target = (target_id, version) if status == "RESOLVED" else None
                elif kind == 1:
                    source_birth += weight
                else:
                    declaration_birth += weight
            # Transfer only pre-existing sources, then add today's new births.
            if old_target != new_target:
                emit(old_target, index, -active_source)
                emit(new_target, index, active_source)
            emit(new_target, index, source_birth)
            if old_status != new_status:
                if old_status is not None:
                    status_events[index, old_status] -= active_declarations
                if new_status is not None:
                    status_events[index, new_status] += active_declarations
            if new_status is not None:
                status_events[index, new_status] += declaration_birth
            active_source += source_birth
            active_declarations += declaration_birth
            old_target, old_status = new_target, new_status
        if old_target is not None or old_status is not None:
            raise ValueError("lookup event stream does not close")
        flush()
    finally:
        reader.close()
        con.execute("DROP TABLE _weighted_stream")
    con.execute("CREATE OR REPLACE TEMP TABLE p_status_deltas(snapshot_index INTEGER,status VARCHAR,delta BIGINT)")
    status_rows = [(index, status, delta) for (index, status), delta in sorted(status_events.items()) if delta]
    if status_rows:
        con.executemany("INSERT INTO p_status_deltas VALUES (?,?,?)", status_rows)
    return {"fast_count_events": emitted, "event_insert_batches": batches,
            "max_event_buffer_rows": min(emitted, _BATCH_SIZE), "status_events": len(status_rows)}


def _fallback(con):
    con.execute("""CREATE OR REPLACE TEMP TABLE _weighted_fallback_edges AS
        WITH spans AS (
            SELECT d.source_package_id,d.source_version,i.target_package_id,i.target_version,
                   greatest(d.birth_index,i.start_index)::INTEGER start_index,i.end_index
            FROM _weighted_fallback d JOIN lookup_intervals i USING(lookup_id)
            WHERE i.status='RESOLVED' AND greatest(d.birth_index,i.start_index)<i.end_index
        ), dedup AS (SELECT DISTINCT * FROM spans), ordered AS (
            SELECT *,max(end_index) OVER(PARTITION BY source_package_id,source_version,target_package_id,target_version
              ORDER BY start_index,end_index ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) prior_end FROM dedup
        ), marked AS (SELECT *,CASE WHEN prior_end IS NULL OR start_index>prior_end THEN 1 ELSE 0 END boundary FROM ordered),
        grouped AS (SELECT *,sum(boundary) OVER(PARTITION BY source_package_id,source_version,target_package_id,target_version
              ORDER BY start_index,end_index ROWS UNBOUNDED PRECEDING) island FROM marked)
        SELECT target_package_id,target_version,min(start_index)::INTEGER start_index,max(end_index)::INTEGER end_index
        FROM grouped GROUP BY source_package_id,source_version,target_package_id,target_version,island""")
    con.execute("""INSERT INTO _weighted_events
        SELECT target_package_id,target_version,start_index,1::BIGINT FROM _weighted_fallback_edges
        UNION ALL SELECT target_package_id,target_version,end_index,-1::BIGINT FROM _weighted_fallback_edges""")
    return int(con.execute("SELECT count(*) FROM _weighted_fallback_edges").fetchone()[0]) * 2


def _counts(con, n):
    con.execute("""CREATE OR REPLACE TEMP TABLE _weighted_running AS
        WITH e AS (SELECT package_id,version,snapshot_index,sum(delta)::BIGINT delta
                   FROM _weighted_events GROUP BY 1,2,3 HAVING sum(delta)<>0)
        SELECT *,sum(delta) OVER(PARTITION BY package_id,version ORDER BY snapshot_index ROWS UNBOUNDED PRECEDING)::BIGINT running_count,
          lead(snapshot_index,1,?) OVER(PARTITION BY package_id,version ORDER BY snapshot_index) end_index FROM e""", [n])
    if con.execute("SELECT EXISTS(SELECT 1 FROM _weighted_running WHERE running_count<0 OR running_count>?)", [INT_MAX]).fetchone()[0]:
        raise ValueError("invalid production dependent count")
    if con.execute("SELECT EXISTS(SELECT 1 FROM _weighted_events GROUP BY package_id,version HAVING sum(delta)<>0)").fetchone()[0]:
        raise ValueError("target delta stream does not close at calendar end")
    # Removing net-zero target events already coalesces adjacent equal counts.
    con.execute("""CREATE OR REPLACE TEMP TABLE p_counts AS
        SELECT package_id,version,snapshot_index::INTEGER start_index,end_index::INTEGER end_index,
               running_count::BIGINT dependents_count FROM _weighted_running
        WHERE running_count>0 AND snapshot_index<? AND snapshot_index<end_index""", [n])
    if con.execute("""SELECT EXISTS(SELECT 1 FROM p_counts c LEFT JOIN target_population t USING(package_id,version)
        WHERE t.package_id IS NULL OR c.start_index<t.birth_index)""").fetchone()[0]:
        raise ValueError("count target absent or begins before target birth")


def aggregate_partition_weighted(con, n: int, partition_id: int, *, global_validated=False):
    started = time.perf_counter()
    if not global_validated:
        validate_weighted_inputs(con, n)
    _validate_partition(con, n, partition_id)
    validated = time.perf_counter()
    metrics = _prepare_weights(con, partition_id)
    weighted = time.perf_counter()
    metrics.update(_sweep(con, n))
    swept = time.perf_counter()
    metrics["fallback_events"] = _fallback(con)
    _counts(con, n)
    counted = time.perf_counter()
    metrics.update(summarize_sources(con, n, partition_id))
    ended = time.perf_counter()
    metrics.update({"partition_id": partition_id,
        "lookups": int(con.execute("SELECT count(*) FROM lookups WHERE partition_id=?", [partition_id]).fetchone()[0]),
        "count_events": metrics["fast_count_events"] + metrics["fallback_events"],
        "count_intervals": int(con.execute("SELECT count(*) FROM p_counts").fetchone()[0]),
        "phase_seconds": {"validation": validated-started, "weighting": weighted-validated,
                          "event_sweep": swept-weighted, "fallback_and_counts": counted-swept,
                          "source_summary": ended-counted}, "seconds": ended-started})
    return metrics
