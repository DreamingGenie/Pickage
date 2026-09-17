"""Historical interval/delta kernel and a bounded fixture comparison adapter.

The SQL kernel consumes normalized source/declaration interval tables. The fixture
adapter is intentionally small; production Parquet input/output belongs to H4/H5.
"""
from __future__ import annotations

from bisect import bisect_left
from collections import Counter, defaultdict
import json
from pathlib import Path

import duckdb

from pipeline.preprocessing.requirements_resolution.bridge import NodeSession, discover_runtime
from pipeline.preprocessing.requirements_resolution.policy import canonical_bytes, sha256
from pipeline.preprocessing.version_dependents.historical_reference import SOURCE_GAPS, _validate


WORKER = Path(__file__).with_name("historical_semver_worker.cjs")
INT_MAX = 2_147_483_647
STATUSES = {"RESOLVED", "NO_ELIGIBLE_TARGET", "NO_SATISFYING_VERSION", "UNMAPPED_TARGET_PACKAGE",
            "INVALID_PACKAGE_NAME", "INVALID_SPEC", "UNSUPPORTED_ALIAS", "UNSUPPORTED_TAG",
            "UNSUPPORTED_GIT", "UNSUPPORTED_FILE", "UNSUPPORTED_URL"}


def aggregate_interval_tables(con, snapshot_count: int):
    """Create edge_intervals, counts, and source_intervals in a local DuckDB.

    Required input tables: sources and declaration_intervals (see _create_tables).
    Counts remain sparse. No source-target row is expanded for every snapshot.
    Caller owns the connection, storage limits, input lineage, and publication.
    """
    if type(snapshot_count) is not int or not 0 < snapshot_count <= 4096:
        raise ValueError("Invalid snapshot count")
    n = snapshot_count
    invalid = con.execute("""
        SELECT EXISTS (
          SELECT 1 FROM sources
          WHERE birth_index IS NULL OR birth_index < 0 OR birth_index >= ?
             OR declaration_count IS NULL OR declaration_count < 0
             OR source_package_id IS NULL OR source_package_id <= 0 OR source_version IS NULL OR trim(source_version) = ''
             OR has_requirements IS NULL OR null_dependencies IS NULL
             OR ((NOT has_requirements OR null_dependencies) AND declaration_count <> 0)
             OR peer_count IS NULL OR peer_count < 0 OR optional_count IS NULL OR optional_count < 0
          UNION ALL
          SELECT 1 FROM declaration_intervals d LEFT JOIN sources s USING (source_package_id, source_version)
          WHERE s.source_package_id IS NULL OR d.start_index IS NULL OR d.end_index IS NULL
             OR d.start_index < s.birth_index OR d.end_index > ? OR d.start_index >= d.end_index
             OR d.declaration_index IS NULL OR d.declaration_index < 0 OR d.declaration_index >= s.declaration_count
             OR d.kind IS DISTINCT FROM 'dependencies' OR d.status IS NULL
             OR (d.status = 'RESOLVED' AND (d.target_package_id IS NULL OR d.target_package_id <= 0
                                          OR d.target_version IS NULL OR trim(d.target_version) = ''))
             OR (d.status <> 'RESOLVED' AND (d.target_package_id IS NOT NULL OR d.target_version IS NOT NULL))
        )
    """, [n, n]).fetchone()[0]
    if invalid:
        raise ValueError("Invalid source or declaration interval bounds")
    statuses = {row[0] for row in con.execute("SELECT DISTINCT status FROM declaration_intervals").fetchall()}
    if not statuses <= STATUSES:
        raise ValueError("Unknown declaration status")
    invalid_coverage = con.execute("""
        WITH ordered AS (
          SELECT d.*, lag(end_index) OVER (
            PARTITION BY source_package_id, source_version, declaration_index ORDER BY start_index) AS previous_end
          FROM declaration_intervals d
        ), declarations AS (
          SELECT source_package_id, source_version, declaration_index,
                 min(start_index) AS first_index, max(end_index) AS last_index,
                 count(*) FILTER (WHERE previous_end IS NOT NULL AND previous_end <> start_index) AS gaps
          FROM ordered GROUP BY source_package_id, source_version, declaration_index
        ), coverage AS (
          SELECT s.source_package_id, s.source_version, s.declaration_count, count(d.declaration_index) AS actual,
                 count(*) FILTER (WHERE d.first_index <> s.birth_index OR d.last_index <> ? OR d.gaps <> 0) AS gaps
          FROM sources s LEFT JOIN declarations d USING (source_package_id, source_version)
          GROUP BY s.source_package_id, s.source_version, s.declaration_count
        ) SELECT EXISTS (SELECT 1 FROM coverage WHERE actual <> declaration_count OR gaps <> 0)
    """, [n]).fetchone()[0]
    if invalid_coverage:
        raise ValueError("Declaration intervals overlap, have gaps, or omit source declarations")

    # Running MAX handles nested intervals; LAG(end_index) alone is insufficient.
    con.execute("""
        CREATE TEMP TABLE edge_intervals AS
        WITH ordered AS (
          SELECT source_package_id, source_version, target_package_id, target_version,
                 start_index, end_index, declaration_index,
                 max(end_index) OVER (
                   PARTITION BY source_package_id, source_version, target_package_id, target_version
                   ORDER BY start_index, end_index, declaration_index
                   ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS previous_end
          FROM declaration_intervals WHERE status = 'RESOLVED'
        ), marked AS (
          SELECT *, CASE WHEN previous_end IS NULL OR start_index > previous_end THEN 1 ELSE 0 END AS boundary
          FROM ordered
        ), grouped AS (
          SELECT *, sum(boundary) OVER (
            PARTITION BY source_package_id, source_version, target_package_id, target_version
            ORDER BY start_index, end_index, declaration_index ROWS UNBOUNDED PRECEDING) AS island
          FROM marked
        )
        SELECT source_package_id, source_version, target_package_id, target_version,
               min(start_index)::INTEGER AS start_index, max(end_index)::INTEGER AS end_index
        FROM grouped GROUP BY source_package_id, source_version, target_package_id, target_version, island
    """)
    con.execute("""
        CREATE TEMP TABLE target_deltas AS
        SELECT target_package_id, target_version, snapshot_index, sum(delta)::BIGINT AS delta
        FROM (
          SELECT target_package_id, target_version, start_index AS snapshot_index, 1::BIGINT AS delta FROM edge_intervals
          UNION ALL
          SELECT target_package_id, target_version, end_index, -1::BIGINT FROM edge_intervals
        ) GROUP BY target_package_id, target_version, snapshot_index
    """)
    con.execute(f"""
        CREATE TEMP TABLE count_intervals AS
        SELECT target_package_id, target_version, snapshot_index AS start_index,
               lead(snapshot_index, 1, {n}) OVER w AS end_index,
               sum(delta) OVER (w ROWS UNBOUNDED PRECEDING)::BIGINT AS dependents_count
        FROM target_deltas
        WINDOW w AS (PARTITION BY target_package_id, target_version ORDER BY snapshot_index)
    """)
    if con.execute("SELECT EXISTS (SELECT 1 FROM count_intervals WHERE dependents_count < 0 OR dependents_count > ?)",
                   [INT_MAX]).fetchone()[0]:
        raise ValueError("Count is negative or exceeds service INT range")
    if con.execute("SELECT EXISTS (SELECT 1 FROM count_intervals WHERE start_index = ? AND dependents_count <> 0)",
                   [n]).fetchone()[0]:
        raise ValueError("Target deltas do not close at calendar end")
    con.execute(f"""
        CREATE TEMP TABLE counts AS
        SELECT target_package_id AS package_id, target_version AS version,
               snapshot_index::INTEGER AS snapshot_index, dependents_count
        FROM count_intervals, range({n}) AS dates(snapshot_index)
        WHERE dependents_count > 0 AND start_index <= snapshot_index AND snapshot_index < end_index
    """)

    # Source quality counts declarations, before edge deduplication. A change of
    # winning target with unchanged RESOLVED status has zero net quality delta.
    con.execute(f"""
        CREATE TEMP TABLE source_intervals AS
        WITH events AS (
          SELECT source_package_id, source_version, birth_index AS snapshot_index, 0::BIGINT AS delta FROM sources
          UNION ALL
          SELECT source_package_id, source_version, start_index, 1::BIGINT FROM declaration_intervals WHERE status = 'RESOLVED'
          UNION ALL
          SELECT source_package_id, source_version, end_index, -1::BIGINT FROM declaration_intervals WHERE status = 'RESOLVED'
        ), summed AS (
          SELECT source_package_id, source_version, snapshot_index, sum(delta)::BIGINT AS delta
          FROM events GROUP BY source_package_id, source_version, snapshot_index
        ), changes AS (
          SELECT e.* FROM summed e JOIN sources s USING (source_package_id, source_version)
          WHERE e.delta <> 0 OR e.snapshot_index = s.birth_index
        ), intervals AS (
          SELECT source_package_id, source_version, snapshot_index AS start_index,
                 lead(snapshot_index, 1, {n}) OVER w AS end_index,
                 sum(delta) OVER (w ROWS UNBOUNDED PRECEDING)::BIGINT AS resolved_count
          FROM changes WINDOW w AS (PARTITION BY source_package_id, source_version ORDER BY snapshot_index)
        )
        SELECT i.source_package_id, i.source_version, i.start_index::INTEGER AS start_index,
               i.end_index::INTEGER AS end_index, s.declaration_count, i.resolved_count,
               s.declaration_count - i.resolved_count AS unresolved_count,
               CASE WHEN NOT s.has_requirements THEN 'MISSING_REQUIREMENTS'
                    WHEN s.null_dependencies THEN 'NULL_DEPENDENCY_LIST'
                    WHEN s.dependency_error THEN 'DEPENDENCY_EXTRACTION_ERROR'
                    WHEN s.dependency_error IS NULL THEN 'DEPENDENCY_EXTRACTION_UNKNOWN'
                    WHEN s.declaration_count = 0 THEN 'OBSERVED_NO_DEPENDENCIES'
                    WHEN i.resolved_count = s.declaration_count THEN 'RESOLVED'
                    WHEN i.resolved_count > 0 THEN 'PARTIAL' ELSE 'UNRESOLVED' END AS status
        FROM intervals i JOIN sources s USING (source_package_id, source_version)
        WHERE i.start_index < i.end_index AND i.start_index < {n}
    """)
    if con.execute("SELECT EXISTS (SELECT 1 FROM source_intervals WHERE resolved_count < 0 OR unresolved_count < 0)").fetchone()[0]:
        raise ValueError("Source resolved declaration count violates conservation")


def _create_tables(con):
    con.execute("""CREATE TABLE sources (
        source_package_id INTEGER, source_version VARCHAR, birth_index INTEGER,
        dependency_error BOOLEAN, has_requirements BOOLEAN, null_dependencies BOOLEAN,
        declaration_count BIGINT, peer_count BIGINT, optional_count BIGINT,
        PRIMARY KEY (source_package_id, source_version))""")
    con.execute("""CREATE TABLE declaration_intervals (
        source_package_id INTEGER, source_version VARCHAR, declaration_index INTEGER,
        kind VARCHAR, declared_name VARCHAR, requirement VARCHAR, normalized_range VARCHAR,
        status VARCHAR, target_package_id INTEGER, target_version VARCHAR,
        start_index INTEGER, end_index INTEGER,
        PRIMARY KEY (source_package_id, source_version, declaration_index, start_index))""")


def _rows(con, query):
    cursor = con.execute(query)
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _insert_fixture_rows(con, table, rows):
    if table not in {"sources", "declaration_intervals"}:
        raise ValueError("Unknown fixture table")
    if not rows:
        return
    columns = {row[0]: row[1] for row in con.execute(f"DESCRIBE {table}").fetchall()}
    # DuckDB's Python scalar conversion repeatedly attempts to import missing
    # pandas in this runtime. Two JSON strings avoid that per-cell conversion.
    # This is only the bounded fixture adapter; production tables come from files.
    body = json.dumps([dict(zip(columns, row)) for row in rows], separators=(",", ":"))
    con.execute(f"INSERT INTO {table} SELECT unnest(from_json(?,?), recursive:=true)",
                [body, json.dumps([columns])])


def _interval_histograms(con, table, n):
    # Table is selected internally; input strings never become SQL identifiers.
    if table not in {"declaration_intervals", "source_intervals"}:
        raise ValueError("Unknown quality interval table")
    events = defaultdict(Counter)
    for index, status, delta in con.execute(f"""
        SELECT snapshot_index, status, sum(delta)::BIGINT FROM (
          SELECT start_index AS snapshot_index, status, 1::BIGINT AS delta FROM {table}
          UNION ALL SELECT end_index, status, -1::BIGINT FROM {table}
        ) GROUP BY snapshot_index, status
    """).fetchall():
        events[index][status] += delta
    active, result = Counter(), []
    for index in range(n + 1):
        active.update(events[index])
        if any(value < 0 for value in active.values()):
            raise ValueError("Negative quality count")
        if index < n:
            result.append(dict(sorted((key, value) for key, value in active.items() if value)))
        elif any(active.values()):
            raise ValueError("Quality intervals do not close at calendar end")
    return result


def _check_lookup(intervals, n):
    end = 0
    for row in intervals:
        a, b = row["start_index"], row["end_index"]
        if type(a) is not int or type(b) is not int or a != end or not a < b <= n:
            raise ValueError("Worker intervals must cover the complete calendar without overlap")
        if row["status"] not in STATUSES or (row["status"] == "RESOLVED") != (row["target_version"] is not None):
            raise ValueError("Worker target/status mismatch")
        end = b
    if end != n:
        raise ValueError("Worker interval coverage is incomplete")


def compute_optimized(fixture: dict, *, runtime=None, log_path: Path, partition_count=1) -> dict:
    """Run H3 on H2-sized normalized fixtures; never a production backfill CLI."""
    if type(partition_count) is not int or not 1 <= partition_count <= 64:
        raise ValueError("partition_count must be between 1 and 64")
    calendar, packages, versions, requirements = _validate(fixture)
    stamps, n = [stamp for _, stamp in calendar], len(calendar)
    births = {key: bisect_left(stamps, row["published"]) for key, row in versions.items()
              if row["published"] is not None}
    active = {key: index for key, index in births.items() if index < n}
    ids = {name: pid for pid, name in packages.items()}
    candidates, requests = defaultdict(list), defaultdict(set)
    for (pid, version), birth in active.items():
        candidates[packages[pid]].append({"version": version, "birth_index": birth})
    declarations, sources = [], []
    for key, birth in sorted(active.items()):
        req = requirements.get(key)
        deps = None if req is None else req["dependencies"]
        sources.append((*key, birth, versions[key]["dependency_error"], req is not None, deps is None,
                        len(deps or []), len((req or {}).get("peer_dependencies") or []),
                        len((req or {}).get("optional_dependencies") or [])))
        for index, item in enumerate(deps or []):
            item = item or {}
            name, spec = item.get("name"), item.get("requirement")
            declarations.append((*key, index, name, spec, birth))
            requests[name].add(spec)
    lookup_intervals, targets, rejected = {}, [], []
    metrics = Counter({"candidate_checks": 0, "parsed_requirements": 0, "worker_requests": 0})
    groups = sorted(set(candidates) | set(requests), key=lambda name:
                    (int(sha256(name), 16) % partition_count, canonical_bytes(name)))
    with NodeSession(runtime or discover_runtime(), Path(log_path), worker=WORKER) as node:
        metadata = node.request({"op": "metadata"})
        for name in groups:
            specs = sorted(requests[name], key=canonical_bytes)
            # Batching only divides lookups. All candidates of a target package
            # remain together; declarations are globally unioned after mapping.
            for offset in range(0, max(len(specs), 1), 128):
                batch = specs[offset:offset + 128]
                reply = node.request({"op": "package", "name": name, "known_package": name in ids,
                                      "snapshot_count": n, "candidates": candidates[name], "requirements": batch})
                metrics["worker_requests"] += 1
                for metric in ("candidate_checks", "parsed_requirements"):
                    metrics[metric] += reply["metrics"][metric]
                if offset == 0:
                    targets.extend({"package_id": ids[name], **row} for row in reply["accepted"])
                    rejected.extend(reply["rejected"])
                if [row["requirement"] for row in reply["lookups"]] != batch:
                    raise ValueError("Worker changed lookup identity/order")
                for lookup in reply["lookups"]:
                    _check_lookup(lookup["intervals"], n)
                    lookup_intervals[name, lookup["requirement"]] = lookup["intervals"]
    targets.sort(key=lambda row: (row["package_id"], row["version"]))
    target_birth = {(row["package_id"], row["version"]): row["birth_index"] for row in targets}
    intervals = []
    for pid, version, index, name, spec, birth in declarations:
        for row in lookup_intervals[name, spec]:
            start, end = max(birth, row["start_index"]), row["end_index"]
            if start >= end:
                continue
            target_id = ids.get(name) if row["status"] == "RESOLVED" else None
            target_version = row["target_version"]
            if row["status"] == "RESOLVED" and target_birth.get((target_id, target_version), n) > start:
                raise ValueError("Resolved target is absent or not yet eligible")
            intervals.append((pid, version, index, "dependencies", name, spec, row["normalized_range"],
                              row["status"], target_id, target_version, start, end))
    with duckdb.connect(config={"threads": 2, "memory_limit": "1GB"}) as con:
        _create_tables(con)
        _insert_fixture_rows(con, "sources", sources)
        _insert_fixture_rows(con, "declaration_intervals", intervals)
        aggregate_interval_tables(con, n)
        count_rows = _rows(con, "SELECT * FROM counts ORDER BY snapshot_index, package_id, version")
        source_intervals = _rows(con, "SELECT * FROM source_intervals ORDER BY source_package_id, source_version, start_index")
        declaration_intervals = _rows(con, "SELECT * FROM declaration_intervals ORDER BY source_package_id, source_version, declaration_index, start_index")
        source_statuses = _interval_histograms(con, "source_intervals", n)
        declaration_statuses = _interval_histograms(con, "declaration_intervals", n)
        metrics["resolved_declaration_intervals"] = con.execute("SELECT count(*) FROM declaration_intervals WHERE status = 'RESOLVED'").fetchone()[0]
        metrics["merged_edge_intervals"] = con.execute("SELECT count(*) FROM edge_intervals").fetchone()[0]
        metrics["target_delta_events"] = con.execute("SELECT count(*) FROM target_deltas WHERE delta <> 0").fetchone()[0]
    by_date = defaultdict(list)
    for row in count_rows:
        index = row.pop("snapshot_index")
        by_date[index].append(row)
    source_events, target_events, rejection_events = defaultdict(Counter), Counter(), defaultdict(Counter)
    for row in sources:
        birth = row[2]
        source_events[birth].update({"source_versions": 1, "selected_declarations": row[6],
                                     "peer_dependencies": row[7], "optional_dependencies": row[8]})
    for row in targets:
        target_events[row["birth_index"]] += 1
    for row in rejected:
        rejection_events[row["birth_index"]][row["reason"]] += 1
    totals, exclusions, target_count, snapshots = Counter(), Counter(), 0, []
    for index, (day, stamp) in enumerate(calendar):
        totals.update(source_events[index])
        exclusions.update(rejection_events[index])
        target_count += target_events[index]
        states, source_states = declaration_statuses[index], source_statuses[index]
        resolved, selected = states.get("RESOLVED", 0), totals["selected_declarations"]
        edges = sum(row["dependents_count"] for row in by_date[index])
        if (sum(states.values()) != selected or sum(source_states.values()) != totals["source_versions"]
                or not 0 <= edges <= resolved <= selected):
            raise ValueError("Historical counts/quality failed conservation")
        quality = {"source_versions": totals["source_versions"], "target_versions": target_count,
                   "selected_declarations": selected, "resolved_declarations": resolved,
                   "unresolved_declarations": selected - resolved, "distinct_edges": edges,
                   "duplicate_resolved_declarations": resolved - edges,
                   "resolution_status": "COMPLETE" if resolved == selected and not any(
                       source_states.get(status, 0) for status in SOURCE_GAPS) else "PARTIAL",
                   "source_status_counts": source_states, "declaration_status_counts": states,
                   "excluded_kind_declarations": {kind: totals[kind] for kind in ("peer_dependencies", "optional_dependencies")},
                   "source_null_publication_excluded": len(versions) - len(births),
                   "source_future_excluded": len(births) - totals["source_versions"],
                   "target_rejections": dict(sorted(exclusions.items()))}
        snapshots.append({"snapshot_at": day,
                          "snapshot_timestamp": stamp.isoformat(timespec="microseconds").replace("+00:00", "Z"),
                          "counts": by_date[index], "quality": quality})
    metrics.update({"unique_lookups": len(lookup_intervals),
                    "lookup_intervals": sum(map(len, lookup_intervals.values())),
                    "declaration_intervals": len(intervals), "source_intervals": len(source_intervals),
                    "sparse_count_rows": len(count_rows),
                    "reference_resolution_calls": sum(s["quality"]["selected_declarations"] for s in snapshots)})
    return {"scope": "BOUNDED_H3_FIXTURE", "method": "WINNER_INTERVALS_UNION_AND_DELTAS",
            "calculation_mode": "HISTORICAL_RECONSTRUCTION_FROM_FIXED_INPUT", "ready_for_load": False,
            "input_sha256": sha256(fixture), "observed_snapshot_timestamp": fixture["observed_snapshot_timestamp"],
            "runtime": metadata, "snapshots": snapshots, "target_population": targets,
            "declaration_intervals": declaration_intervals, "source_intervals": source_intervals,
            "metrics": dict(metrics)}
