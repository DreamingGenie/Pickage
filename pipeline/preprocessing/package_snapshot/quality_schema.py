"""Quality output schema and generation projection, independent of validators."""
from __future__ import annotations

QUALITY_SCHEMA_ID = "package-snapshot-quality-v2"
DOWNLOAD_FIELDS = [
    ("snapshot_at", "DATE"), ("previous_snapshot_at", "DATE"),
    ("download_sum", "BIGINT"), ("expected_days", "INTEGER"),
    ("observed_days", "INTEGER"), ("valid_days", "INTEGER"),
    ("data_status", "VARCHAR"), ("null_reason", "VARCHAR"),
    ("quality_reasons", "VARCHAR[]"), ("input_manifest_sha256", "VARCHAR"),
    ("policy_sha256", "VARCHAR"), ("aggregation_policy_sha256", "VARCHAR"),
]
SELECTION_FIELDS = [
    ("version", "VARCHAR"), ("ordinal", "BIGINT"), ("repo_url", "VARCHAR"),
    ("provider", "VARCHAR"), ("project_path", "VARCHAR"),
    ("comparison_project_path", "VARCHAR"), ("observed_project_path", "VARCHAR"),
    ("snapshot", "VARCHAR"), ("snapshot_timestamp", "VARCHAR"),
    ("observed_timestamp", "TIMESTAMP WITH TIME ZONE"),
    ("reason", "VARCHAR"), ("mapping_status", "VARCHAR"),
]
LEGACY_OBSERVED_SCHEMA = [("package_id", "INTEGER"), ("name", "VARCHAR")] + DOWNLOAD_FIELDS + [
    ("repository_" + name, kind) for name, kind in SELECTION_FIELDS
]
COMMON_SCHEMA = LEGACY_OBSERVED_SCHEMA + [("stars", "INTEGER"), ("open_issues", "INTEGER")]
HISTORY_FIELDS = [("first_published_at", "TIMESTAMP WITH TIME ZONE"),
                  ("selected_published_at", "TIMESTAMP WITH TIME ZONE")]
QUALITY_SCHEMA = COMMON_SCHEMA + HISTORY_FIELDS
LEGACY_HISTORY_SCHEMA = [
    ("package_id", "INTEGER"), ("snapshot_at", "DATE"), *HISTORY_FIELDS,
    ("download_sum", "BIGINT"), ("stars", "INTEGER"), ("open_issues", "INTEGER"),
    ("data_status", "VARCHAR"), ("expected_days", "INTEGER"),
    ("observed_days", "INTEGER"), ("valid_days", "INTEGER"),
    ("null_reason", "VARCHAR"), ("quality_reasons", "VARCHAR[]"),
    ("repository_reason", "VARCHAR"), ("repo_url", "VARCHAR"),
    ("selected_version", "VARCHAR"), ("observed_timestamp", "TIMESTAMP WITH TIME ZONE"),
]


def require_schema(con, view, expected):
    actual = [(row[0], row[1]) for row in con.execute("DESCRIBE " + view).fetchall()]
    if actual != expected:
        raise ValueError("quality schema mismatch: " + view)


def history_quality_projection(con, interval):
    """Name/type alignment only; do not invent missing upstream selection evidence.

    quality_raw has the original historical fields; package_identity supplies name.
    These views are local to a DuckDB connection and never replace pinned files.
    """
    require_schema(con, "quality_raw", LEGACY_HISTORY_SCHEMA)
    # The parameterized table avoids interpolating input timestamps or dates into SQL.
    con.execute("CREATE TEMP TABLE quality_interval AS SELECT ?::DATE previous_snapshot_at,"
                "?::VARCHAR snapshot_timestamp", [interval.get("previous_snapshot_at"),
                                                  interval["snapshot_timestamp"]])
    rename = {"repository_repo_url": "repo_url", "repository_version": "selected_version",
              "repository_observed_timestamp": "observed_timestamp"}
    source_fields = {name for name, _ in LEGACY_HISTORY_SCHEMA}
    expressions = []
    for name, kind in QUALITY_SCHEMA:
        if name == "name":
            expression = "p.name"
        elif name == "previous_snapshot_at":
            expression = "i.previous_snapshot_at"
        elif name == "repository_snapshot":
            expression = "CAST(q.snapshot_at AS VARCHAR)"
        elif name == "repository_snapshot_timestamp":
            expression = "i.snapshot_timestamp"
        elif name == "repository_mapping_status":
            expression = ("CASE WHEN q.repo_url IS NULL THEN 'NO_SELECTED_REPOSITORY' "
                          "WHEN q.observed_timestamp IS NULL THEN 'NO_EXACT_PROVIDER_PATH_MATCH' "
                          "ELSE 'MATCHED' END")
        elif name in rename:
            expression = "q." + rename[name]
        elif name in source_fields:
            expression = "q." + name
        else:
            # Historical aggregation has no separate downloads-interval run or
            # retained provider/path selection columns. The manifest holds its lineage.
            expression = "NULL"
        expressions.append(f"CAST({expression} AS {kind}) AS {name}")
    con.execute("CREATE TEMP VIEW quality AS SELECT " + ",".join(expressions) +
                " FROM quality_raw q LEFT JOIN package_identity p USING(package_id) "
                "CROSS JOIN quality_interval i")
