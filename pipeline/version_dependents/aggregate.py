"""Calculate direct dependents per approved package version.

The caller owns a DuckDB connection and must create these normalized tables:
``requirements_edges``, ``approved_sources``, and ``approved_targets``.
``aggregate`` validates them before creating the ``version_dependents`` table.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import duckdb

_INT_MAX = 2_147_483_647
_RESULT = "version_dependents"
_TABLES = {
    "requirements_edges": {
        "source_package_id": ("INTEGER", "BIGINT"),
        "source_version": ("VARCHAR",),
        "target_package_id": ("INTEGER", "BIGINT"),
        "target_version": ("VARCHAR",),
        "snapshot_at": ("DATE",),
        "snapshot_timestamp": ("TIMESTAMP WITH TIME ZONE",),
    },
    "approved_sources": {
        "package_id": ("INTEGER", "BIGINT"),
        "version": ("VARCHAR",),
        "published_at": ("TIMESTAMP WITH TIME ZONE",),
        "snapshot_at": ("DATE",),
        "snapshot_timestamp": ("TIMESTAMP WITH TIME ZONE",),
    },
    "approved_targets": {
        "package_id": ("INTEGER", "BIGINT"),
        "version": ("VARCHAR",),
        "published_at": ("TIMESTAMP WITH TIME ZONE",),
        "snapshot_at": ("DATE",),
        "snapshot_timestamp": ("TIMESTAMP WITH TIME ZONE",),
    },
}


def _schema(con: duckdb.DuckDBPyConnection, table: str, expected: dict[str, tuple[str, ...]]) -> None:
    try:
        actual = {row[0]: row[1].upper() for row in con.execute(f"DESCRIBE {table}").fetchall()}
    except duckdb.Error as exc:
        raise ValueError(f"missing input table: {table}") from exc
    if set(actual) != set(expected):
        raise ValueError(f"{table} must contain exactly: {', '.join(expected)}")
    for name, accepted in expected.items():
        if actual[name] not in accepted:
            raise ValueError(f"{table}.{name} must be {' or '.join(accepted)}, got {actual[name]}")


def _reject(con: duckdb.DuckDBPyConnection, query: str, message: str, params: list[object] | None = None) -> None:
    if con.execute(f"SELECT EXISTS ({query})", params or []).fetchone()[0]:
        raise ValueError(message)


def aggregate(
    con: duckdb.DuckDBPyConnection,
    *,
    expected_snapshot_at: date,
    snapshot_timestamp: datetime,
    resolution_status: str,
    ready_for_dependents: bool,
) -> dict[str, int | str]:
    """Validate normalized inputs and publish direct counts into one result table.

    ``resolution_status`` and ``ready_for_dependents`` are upstream guards. They
    do not prove that a production manifest, full population, or output marker
    was verified. The caller should use a fresh connection per attempt.
    """
    if not isinstance(expected_snapshot_at, date) or isinstance(expected_snapshot_at, datetime):
        raise ValueError("expected_snapshot_at must be a date")
    if not isinstance(snapshot_timestamp, datetime) or snapshot_timestamp.tzinfo is None or snapshot_timestamp.utcoffset() is None:
        raise ValueError("snapshot_timestamp must be timezone-aware")
    snapshot_timestamp = snapshot_timestamp.astimezone(timezone.utc)
    if snapshot_timestamp.date() != expected_snapshot_at:
        raise ValueError("snapshot_timestamp UTC date must equal expected_snapshot_at")
    if resolution_status != "COMPLETE":
        raise ValueError("resolution_status must be COMPLETE")
    if type(ready_for_dependents) is not bool or ready_for_dependents is not True:
        raise ValueError("ready_for_dependents must be the boolean True")

    for table, expected in _TABLES.items():
        _schema(con, table, expected)
    if con.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name IN (?, ?))", [_RESULT, "_version_dependents"]).fetchone()[0]:
        raise ValueError("result or internal table already exists; use a fresh connection")
    for table in _TABLES:
        _reject(con, f"SELECT 1 FROM {table} WHERE snapshot_at IS NULL OR snapshot_at <> ?", f"{table} has wrong snapshot_at", [expected_snapshot_at])
        _reject(con, f"SELECT 1 FROM {table} WHERE snapshot_timestamp IS NULL OR snapshot_timestamp <> ?", f"{table} has wrong snapshot_timestamp", [snapshot_timestamp])

    for table, prefix in (("approved_sources", "source"), ("approved_targets", "target")):
        _reject(con, f"SELECT 1 FROM {table} WHERE package_id IS NULL OR package_id <= 0 OR package_id > {_INT_MAX}", f"invalid {prefix} package ID")
        _reject(con, f"SELECT 1 FROM {table} WHERE version IS NULL OR regexp_matches(version, '^\\s*$') OR length(version)>100 OR contains(version, chr(0))", f"invalid {prefix} version")
        _reject(con, f"SELECT 1 FROM {table} WHERE published_at IS NULL OR published_at > ?", f"invalid {prefix} published_at", [snapshot_timestamp])
        _reject(con, f"SELECT package_id, version FROM {table} GROUP BY package_id, version HAVING count(*) > 1", f"duplicate {prefix} population key")
        if con.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0:
            raise ValueError(f"{table} must not be empty")

    _reject(con, f"SELECT 1 FROM requirements_edges WHERE source_package_id IS NULL OR source_package_id <= 0 OR source_package_id > {_INT_MAX} OR target_package_id IS NULL OR target_package_id <= 0 OR target_package_id > {_INT_MAX}", "invalid edge package ID")
    _reject(con, "SELECT 1 FROM requirements_edges WHERE source_version IS NULL OR regexp_matches(source_version, '^\\s*$') OR length(source_version)>100 OR contains(source_version, chr(0)) OR target_version IS NULL OR regexp_matches(target_version, '^\\s*$') OR length(target_version)>100 OR contains(target_version, chr(0))", "invalid edge version")
    _reject(con, "SELECT 1 FROM requirements_edges e ANTI JOIN approved_sources s ON (e.source_package_id,e.source_version)=(s.package_id,s.version)", "edge source is outside approved source population")
    _reject(con, "SELECT 1 FROM requirements_edges e ANTI JOIN approved_targets t ON (e.target_package_id,e.target_version)=(t.package_id,t.version)", "edge target is outside approved target population")

    con.execute("BEGIN TRANSACTION")
    try:
        con.execute("CREATE TEMP TABLE _version_dependents AS SELECT package_id, version, snapshot_at, snapshot_timestamp, 0::BIGINT AS dependents_count FROM approved_targets")
        con.execute("""UPDATE _version_dependents AS result SET dependents_count = counts.raw_count
            FROM (SELECT target_package_id AS package_id, target_version AS version,
                         count(*)::BIGINT AS raw_count
                  FROM (SELECT DISTINCT source_package_id, source_version,
                                        target_package_id, target_version
                        FROM requirements_edges) AS distinct_edges
                  GROUP BY target_package_id, target_version) AS counts
            WHERE result.package_id = counts.package_id AND result.version = counts.version""")
        _reject(con, "SELECT 1 FROM _version_dependents WHERE dependents_count > 2147483647", "dependents_count exceeds INTEGER")
        counts = con.execute("SELECT count(*), coalesce(sum(dependents_count), 0) FROM _version_dependents").fetchone()
        con.execute("CREATE TABLE version_dependents AS SELECT package_id, version, snapshot_at, snapshot_timestamp, dependents_count::INTEGER AS dependents_count FROM _version_dependents")
        con.execute("DROP TABLE _version_dependents")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return {"target_rows": int(counts[0]), "total_direct_dependents": int(counts[1]), "snapshot_at": expected_snapshot_at.isoformat()}
