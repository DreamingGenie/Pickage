"""Small shared helpers for validating and addressing Curated Parquet input.

These helpers have no PostgreSQL dependency so preprocessing stages can use
the same validation and DuckDB path quoting at their own boundary.
"""
from __future__ import annotations

from pathlib import Path


SCHEMAS = {
    "package": [("package_id", "INTEGER"), ("name", "VARCHAR"), ("repo_url", "VARCHAR")],
    "version": [("version", "VARCHAR"), ("package_id", "INTEGER"),
                ("published_at", "TIMESTAMP"), ("ordinal", "BIGINT"),
                ("description", "VARCHAR"), ("licenses", "JSON"),
                ("deprecated", "VARCHAR"), ("dependency", "JSON")],
}


def schema(con: object, path: Path, table: str,
           expected: dict[str, list[tuple[str, str]]] | list[tuple[str, str]] | None = None) -> None:
    """Validate a Parquet schema against a caller-owned table contract."""
    rows = con.execute(
        "DESCRIBE SELECT * FROM read_parquet(?, hive_partitioning=false)", [str(path)]
    ).fetchall()
    actual = [(row[0], row[1].upper()) for row in rows]
    contract = (expected[table] if isinstance(expected, dict) else expected) or SCHEMAS[table]
    if actual != contract:
        raise ValueError(f"{table} Parquet schema mismatch: {path.name}")


def sql_path(path: Path) -> str:
    """Return one safely quoted absolute path for DuckDB SQL."""
    return "'" + str(path.resolve()).replace("'", "''") + "'"


def sql_paths(paths: list[Path | str]) -> str:
    """Return a DuckDB list literal containing safely quoted paths."""
    return "[" + ",".join(sql_path(Path(path)) for path in paths) + "]"


__all__ = ["SCHEMAS", "schema", "sql_path", "sql_paths"]
