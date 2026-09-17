"""Enrich the weekly ``versions_min`` extract with inherited metadata.

This module is deliberately an adapter between the collector and the existing
curated transform.  It does not alter a raw manifest and it never mutates the
previous Curated run.  DuckDB uses a file in ``output_dir`` so large weekly
extracts do not have to be materialised in Python memory.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Mapping

import duckdb


class MetadataInputError(ValueError):
    """The min extract or its parent lineage is not safe to enrich."""


def _paths(value: Iterable[str | Path] | str | Path) -> list[Path]:
    if isinstance(value, (str, Path)):
        value = [value]
    paths = [Path(p).resolve() for p in value]
    if not paths or any(not p.is_file() for p in paths):
        raise MetadataInputError("Parquet input is empty or missing")
    return paths


def _literal(path: Path) -> str:
    return "'" + path.as_posix().replace("'", "''") + "'"


def _view(con: duckdb.DuckDBPyConnection, name: str,
          files: Iterable[str | Path] | str | Path) -> list[str]:
    paths = _paths(files)
    quoted = ",".join(_literal(p) for p in paths)
    con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet([{quoted}], hive_partitioning=false)")
    return [row[0] for row in con.execute(f"DESCRIBE {name}").fetchall()]


def _q(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _column(columns: list[str], *names: str) -> str | None:
    lowered = {c.lower(): c for c in columns}
    for name in names:
        if name.lower() in lowered:
            return _q(lowered[name.lower()])
    return None


def _require(columns: list[str], *names: str) -> str:
    value = _column(columns, *names)
    if value is None:
        raise MetadataInputError("Missing required column: " + "/".join(names))
    return value


def _json_array_sql(expr: str, type_name: str) -> str:
    # Curated stores licenses as JSON text; accept the historical VARCHAR[]
    # representation as well as a JSON array string from older runs.
    if type_name.upper().startswith("VARCHAR[]"):
        return f"{expr}::VARCHAR[]"
    return f"CASE WHEN {expr} IS NULL THEN NULL ELSE {expr}::VARCHAR[] END"


def prepare_versions(
    con: duckdb.DuckDBPyConnection,
    versions_min_files: Iterable[str | Path] | str | Path,
    previous_package_files: Iterable[str | Path] | str | Path | None,
    previous_version_files: Iterable[str | Path] | str | Path | None,
    previous_id_files: Iterable[str | Path] | str | Path | None,
    output_dir: str | Path,
    parent_identity: Mapping[str, object] | None,
) -> dict[str, Path]:
    """Create full-shaped versions input plus per-row inheritance provenance.

    ``versions_min`` values are retained whenever present.  For a known
    package, missing metadata on a new version is copied from the nearest
    lower-ordinal eligible parent version.  Existing versions use their exact
    parent row.  New packages intentionally receive three NULL metadata
    fields.  The returned mapping has ``versions`` and ``provenance`` paths.
    """
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=False)
    con.execute("SET TimeZone='UTC'")
    min_cols = _view(con, "vmin", versions_min_files)
    name = _require(min_cols, "Name", "name")
    version = _require(min_cols, "Version", "version")
    ordinal = _require(min_cols, "ordinal")
    if con.execute("SELECT count(*) FROM (SELECT {0},{1} FROM vmin GROUP BY ALL HAVING count(*)>1)".format(name, version)).fetchone()[0]:
        raise MetadataInputError("Duplicate versions_min package/version keys")

    prev_pkg_cols: list[str] = []
    if previous_package_files:
        prev_pkg_cols = _view(con, "old_packages", previous_package_files)
    prev_ver_cols: list[str] = []
    if previous_version_files:
        prev_ver_cols = _view(con, "old_versions", previous_version_files)
    prev_id_cols: list[str] = []
    if previous_id_files:
        prev_id_cols = _view(con, "old_ids", previous_id_files)

    if not prev_pkg_cols or not prev_ver_cols or not prev_id_cols:
        con.execute("CREATE TEMP VIEW old_packages AS SELECT NULL::INTEGER AS package_id, NULL::VARCHAR AS name, NULL::VARCHAR AS repo_url WHERE false")
        con.execute("CREATE TEMP VIEW old_versions AS SELECT NULL::INTEGER AS package_id, NULL::VARCHAR AS version, NULL::BIGINT AS ordinal, NULL::VARCHAR AS description, NULL::VARCHAR[] AS licenses WHERE false")
        con.execute("CREATE TEMP VIEW old_ids AS SELECT NULL::INTEGER AS package_id, NULL::VARCHAR AS name WHERE false")
        prev_pkg_cols = ["package_id", "name", "repo_url"]
        prev_ver_cols = ["package_id", "version", "ordinal", "description", "licenses"]
        prev_id_cols = ["package_id", "name"]

    old_id = _require(prev_id_cols, "package_id")
    old_id_name = _require(prev_id_cols, "name")
    old_pkg_id = _require(prev_pkg_cols, "package_id")
    old_pkg_name = _require(prev_pkg_cols, "name")
    old_repo = _column(prev_pkg_cols, "repo_url", "source_repo")
    old_ver_id = _require(prev_ver_cols, "package_id")
    old_ver = _require(prev_ver_cols, "version")
    old_ord = _require(prev_ver_cols, "ordinal")
    old_desc = _column(prev_ver_cols, "description", "Description")
    old_lic = _column(prev_ver_cols, "licenses", "Licenses")
    if old_desc is None or old_lic is None:
        raise MetadataInputError("Previous versions require description and licenses")

    # Build a stable parent relation.  A duplicate old ID or old version is an
    # ambiguity that must stop the run rather than choose an arbitrary row.
    for table, cols in (("old_ids", (old_id_name,)), ("old_ids", (old_id,)),
                        ("old_versions", (old_ver_id, old_ver))):
        group = ",".join(cols)
        if con.execute(f"SELECT count(*) FROM (SELECT {group} FROM {table} GROUP BY {group} HAVING count(*)>1)").fetchone()[0]:
            raise MetadataInputError(f"Duplicate parent mapping in {table}")

    v_name = f"v.{name}"
    v_version = f"v.{version}"
    con.execute(f"""CREATE TEMP VIEW current AS
        SELECT v.*, i.package_id AS inherited_package_id,
               CASE WHEN i.package_id IS NULL THEN 'new_package'
                    WHEN ov.version IS NULL THEN 'new_version' ELSE 'existing_version' END AS row_kind
        FROM vmin v LEFT JOIN old_ids i ON i.name={v_name}
        LEFT JOIN old_versions ov ON ov.package_id=i.package_id AND ov.version={v_version}""")
    fields = []
    for col in min_cols:
        if col.lower() not in {"description", "licenses", "source_repo", "repo_url"}:
            fields.append(f"c.{_q(col)}")
    def min_expr(*names: str) -> str:
        value = _column(min_cols, *names)
        return f"c.{value}" if value else "NULL"
    current_desc = min_expr("Description", "description")
    current_lic = min_expr("Licenses", "licenses")
    current_repo = min_expr("source_repo", "repo_url")
    lic_type = next((r[1] for r in con.execute("DESCRIBE old_versions").fetchall() if r[0].lower() == "licenses"), "VARCHAR")
    source_repo_expr = f"pkg.{old_repo}" if old_repo else "NULL"
    # The lateral candidate is from the immutable parent only.  It is ranked
    # by ordinal first, then publication/version for deterministic ties.
    query = f"""SELECT {', '.join(fields)},
        CASE WHEN c.inherited_package_id IS NULL THEN NULL::VARCHAR
             WHEN c.row_kind='existing_version' THEN p.description
             ELSE cand.description END::VARCHAR AS Description,
        CASE WHEN c.inherited_package_id IS NULL THEN NULL::VARCHAR[]
             WHEN c.row_kind='existing_version' THEN {_json_array_sql('p.licenses', lic_type)}
             ELSE {_json_array_sql('cand.licenses', lic_type)} END::VARCHAR[] AS Licenses,
        CASE WHEN c.inherited_package_id IS NULL THEN NULL::VARCHAR
             ELSE {source_repo_expr} END::VARCHAR AS source_repo
        FROM current c
        LEFT JOIN old_versions p ON p.package_id=c.inherited_package_id AND p.version=c.{_q(version.strip(chr(34)))}
        LEFT JOIN old_packages pkg ON pkg.package_id=c.inherited_package_id
        LEFT JOIN LATERAL (
            SELECT ov.description, ov.licenses FROM old_versions ov
            JOIN old_ids oi ON oi.package_id=ov.package_id
            JOIN vmin vc ON oi.name=vc.{name} AND ov.version=vc.{version}
            WHERE ov.package_id=c.inherited_package_id AND vc.{ordinal}<c.{_q(ordinal.strip(chr(34)))}
            ORDER BY vc.{ordinal} DESC, ov.version ASC LIMIT 1
        ) cand ON TRUE"""
    # Use a fresh name to avoid relying on an output directory's current state.
    con.execute("CREATE TABLE enriched AS " + query)
    version_dir = out / "versions_full"
    version_dir.mkdir()
    version_path = version_dir / "part-000000.parquet"
    con.execute("COPY enriched TO ? (FORMAT PARQUET, COMPRESSION ZSTD)", [str(version_path)])

    provenance_path = out / "metadata_provenance.jsonl"
    parent = dict(parent_identity or {})
    cursor = con.execute(f"""SELECT c.{name},c.{version},c.row_kind,
        CASE WHEN c.row_kind='existing_version' THEN 'preserved'
             WHEN c.row_kind='new_version' AND cand.version IS NOT NULL THEN 'inherited'
             WHEN c.row_kind='new_version' THEN 'missing'
             ELSE 'missing' END AS status,
        cand.version AS source_version
        FROM current c LEFT JOIN LATERAL (
          SELECT ov.version FROM old_versions ov
          JOIN old_ids oi ON oi.package_id=ov.package_id
          JOIN vmin vc ON oi.name=vc.{name} AND ov.version=vc.{version}
          WHERE ov.package_id=c.inherited_package_id AND vc.{ordinal}<c.{ordinal}
          ORDER BY vc.{ordinal} DESC, ov.version ASC LIMIT 1
        ) cand ON TRUE ORDER BY c.{name},c.{version}""")
    with provenance_path.open("x", encoding="utf-8") as stream:
        while batch := cursor.fetchmany(8192):
            for row in batch:
                stream.write(json.dumps({"name": row[0], "version": row[1], "row_kind": row[2],
                                         "status": row[3], "source_version": row[1] if row[2] == 'existing_version' else row[4],
                                         "parent": parent}, ensure_ascii=False, default=str) + "\n")
    return {"versions": version_path, "provenance": provenance_path}
