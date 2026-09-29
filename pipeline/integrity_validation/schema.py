"""Fixture projections; service column order follows V1__init.sql.

Constraints deliberately remain in checks so malformed rows can be injected.
The validation schema is evidence for tests, not a proposed service migration.
"""

TABLES = {
    "public.package": (("package_id", "INTEGER"), ("name", "VARCHAR"), ("repo_url", "VARCHAR")),
    "public.package_snapshot": (("package_id", "INTEGER"), ("snapshot_at", "DATE"),
                                ("downloads", "BIGINT"), ("stars", "INTEGER"), ("open_issues", "INTEGER")),
    "public.version": (("version", "VARCHAR"), ("package_id", "INTEGER"), ("published_at", "TIMESTAMP"),
                       ("ordinal", "BIGINT"), ("description", "VARCHAR"), ("licenses", "JSON"),
                       ("deprecated", "VARCHAR"), ("dependency", "JSON")),
    "public.snapshot": (("snapshot_at", "DATE"),),
    "public.package_version_snapshot": (("package_id", "INTEGER"), ("version", "VARCHAR"),
                                        ("snapshot_at", "DATE"), ("dependents_count", "INTEGER")),
    "validation.snapshot_context": (("snapshot_at", "DATE"), ("snapshot_timestamp", "TIMESTAMP")),
    "validation.package_population": (("package_id", "INTEGER"), ("snapshot_at", "DATE")),
    "validation.target_population": (("package_id", "INTEGER"), ("version", "VARCHAR"), ("snapshot_at", "DATE")),
    "validation.resolved_edges": (("source_package_id", "INTEGER"), ("source_version", "VARCHAR"),
                                  ("target_package_id", "INTEGER"), ("target_version", "VARCHAR"), ("snapshot_at", "DATE")),
    "validation.source_quality": (("snapshot_at", "DATE"), ("calculation_status", "VARCHAR"),
                                  ("resolution_status", "VARCHAR"), ("unresolved_count", "BIGINT")),
    "validation.expected_package_metrics": (("package_id", "INTEGER"), ("snapshot_at", "DATE"),
                                            ("downloads", "BIGINT"), ("stars", "INTEGER"), ("open_issues", "INTEGER")),
}

SERVICE_TABLES = tuple(name for name in TABLES if name.startswith("public."))
