"""Enrich the weekly ``versions_min`` extract with inherited metadata.

This module is deliberately an adapter between the collector and the existing
curated transform.  It does not alter a raw manifest and it never mutates the
previous Curated run.  DuckDB uses a file in ``output_dir`` so large weekly
extracts do not have to be materialised in Python memory.
"""
from __future__ import annotations

import json
import re
import time
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


def _parent_struct_sql(parent: Mapping[str, object]) -> str:
    """Return a typed DuckDB struct literal for the compact provenance path."""
    if not parent:
        return "NULL::STRUCT(run_id VARCHAR)"
    fields = []
    for key, value in parent.items():
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(key)):
            raise MetadataInputError(f"Invalid parent identity field: {key}")
        if value is None:
            literal = "NULL::VARCHAR"
        elif isinstance(value, bool):
            literal = "TRUE" if value else "FALSE"
        elif isinstance(value, (int, float)):
            literal = str(value)
        else:
            literal = "'" + str(value).replace("'", "''") + "'"
        fields.append(f"{_q(str(key))} := {literal}")
    return "struct_pack(" + ", ".join(fields) + ")"


def prepare_versions(
    con: duckdb.DuckDBPyConnection,
    versions_min_files: Iterable[str | Path] | str | Path,
    previous_package_files: Iterable[str | Path] | str | Path | None,
    previous_version_files: Iterable[str | Path] | str | Path | None,
    previous_id_files: Iterable[str | Path] | str | Path | None,
    output_dir: str | Path,
    parent_identity: Mapping[str, object] | None,
    provenance_format: str = "jsonl",
    output_buckets: int | None = None,
) -> dict[str, Path | list[Path]]:
    """Create full-shaped versions input plus per-row inheritance provenance.

    Collector fields are retained except description/licenses/repository,
    whose policy is inherited from the approved parent. For a known
    package, metadata on a new version is copied from the nearest
    lower-ordinal eligible parent version.  Existing versions use their exact
    parent row.  New packages intentionally receive three NULL metadata
    fields. ``versions`` always contains all output paths. ``provenance`` is
    a path list for Parquet or a single path for legacy JSONL output.
    """
    if provenance_format not in {"jsonl", "parquet"}:
        raise ValueError("provenance_format must be jsonl or parquet")
    if output_buckets is not None and not 1 <= output_buckets <= 256:
        raise ValueError("output_buckets must be between 1 and 256")
    started = time.monotonic()
    def progress(phase):
        print(f"METADATA_STAGE phase={phase} elapsed_seconds={time.monotonic()-started:.3f}", flush=True)
    progress("validate_inputs")
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=False)
    con.execute("SET TimeZone='UTC'")
    # The output is a streaming Parquet sink; preserving insertion order only
    # increases DuckDB's memory pressure for this wide, multi-million-row
    # result.  Keep spill files beside the run so the orchestration cleanup
    # can account for and remove them with the rest of the run workspace.
    spill_dir = out / ".duckdb-tmp"
    spill_dir.mkdir()
    con.execute("SET preserve_insertion_order=false")
    con.execute("SET temp_directory=?", [str(spill_dir)])
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
    # Materialize the input-to-parent key classification once.  Rebuilding
    # this exact-key join for every output bucket repeatedly scanned all old
    # IDs and version keys.  The compressed working copy is removed after all
    # outputs are written; it is not published as Curated data.
    progress("materialize_current")
    con.execute("CREATE TEMP VIEW old_version_keys AS SELECT package_id,version FROM old_versions")
    working_dir = out / "working"
    working_dir.mkdir()
    current_path = working_dir / "current.parquet"
    current_sql = f"""SELECT v.*, i.package_id AS inherited_package_id,
               CASE WHEN i.package_id IS NULL THEN 'new_package'
                    WHEN ov.version IS NULL THEN 'new_version' ELSE 'existing_version' END AS row_kind
        FROM vmin v LEFT JOIN old_ids i ON i.name={v_name}
        LEFT JOIN old_version_keys ov ON ov.package_id=i.package_id AND ov.version={v_version}"""
    con.execute("COPY (" + current_sql + ") TO ? (FORMAT PARQUET, COMPRESSION ZSTD)", [str(current_path)])
    con.execute("DROP VIEW old_version_keys")
    con.execute("CREATE VIEW current AS SELECT * FROM read_parquet(" + _literal(current_path) + ")")
    fields = []
    for col in min_cols:
        if col.lower() not in {"description", "licenses", "source_repo", "repo_url"}:
            fields.append(f"c.{_q(col)}")
    lic_type = next((r[1] for r in con.execute("DESCRIBE old_versions").fetchall() if r[0].lower() == "licenses"), "VARCHAR")
    source_repo_expr = f"pkg.{old_repo}" if old_repo else "NULL"
    # Restrict predecessor lookup to new versions and reduce it to one source
    # row per package/current ordinal before the ASOF join.  The old lateral
    # lookup joined every current row to every lower eligible version, which
    # made the intermediate relation grow quadratically for large packages.
    # ``eligible_parent_versions`` deliberately uses the current snapshot's
    # ordinal: the parent ordinal is only used to identify the source row's
    # package/version, while the current snapshot determines ordering.
    progress("eligible_parent_versions")
    con.execute(f"""CREATE TEMP TABLE eligible_parent_versions AS
        SELECT package_id, current_ordinal, version
        FROM (
            SELECT vc.inherited_package_id AS package_id, vc.{ordinal} AS current_ordinal,
                   vc.{version} AS version,
                   row_number() OVER (
                       PARTITION BY vc.inherited_package_id, vc.{ordinal}
                       ORDER BY vc.{version} ASC
                   ) AS rn
            FROM current vc
            WHERE vc.row_kind='existing_version'
        ) ranked
        WHERE rn=1""")
    progress("new_version_candidates")
    con.execute(f"""CREATE TEMP TABLE candidate_map AS
        SELECT c.{name} AS target_name, c.{version} AS target_version,
               cand.package_id AS source_package_id, cand.version AS source_version
        FROM (SELECT * FROM current WHERE row_kind='new_version') c
        ASOF LEFT JOIN eligible_parent_versions cand
          ON c.inherited_package_id=cand.package_id
         AND cand.current_ordinal<c.{ordinal}
        """)
    # Candidate selection no longer needs the ordinal/source lookup table.
    # Release its blocks before the wide output buckets start.
    con.execute("DROP TABLE eligible_parent_versions")
    query = f"""SELECT {', '.join(fields)},
        CASE WHEN c.inherited_package_id IS NULL THEN NULL::VARCHAR
             WHEN c.row_kind='existing_version' THEN p.description
             ELSE source.description END::VARCHAR AS Description,
        CASE WHEN c.inherited_package_id IS NULL THEN NULL::VARCHAR[]
             WHEN c.row_kind='existing_version' THEN {_json_array_sql('p.licenses', lic_type)}
             ELSE {_json_array_sql('source.licenses', lic_type)} END::VARCHAR[] AS Licenses,
        CASE WHEN c.inherited_package_id IS NULL THEN NULL::VARCHAR
             ELSE {source_repo_expr} END::VARCHAR AS source_repo
        FROM current c
        LEFT JOIN old_versions p ON p.package_id=c.inherited_package_id AND p.version=c.{_q(version.strip(chr(34)))}
        LEFT JOIN old_packages pkg ON pkg.package_id=c.inherited_package_id
        LEFT JOIN candidate_map cm ON cm.target_name=c.{name}
                                  AND cm.target_version=c.{version}
        LEFT JOIN old_versions source ON source.package_id=cm.source_package_id
                                     AND source.version=cm.source_version"""
    def bucket_query(bucket: int, count: int) -> str:
        # Constrain every wide parent relation as well as the left side.  A
        # WHERE on c alone still permits DuckDB to build the full old_versions
        # hash table for p/source on every bucket.
        current_filter = f"hash({name}) % {count} = {bucket}"
        parent_filter = f"hash(pi.{old_id_name}) % {count} = {bucket}"
        result = query.replace(
            "FROM current c",
            f"FROM (SELECT * FROM current WHERE {current_filter}) c",
        )
        result = result.replace(
            "LEFT JOIN old_versions p ON",
            "LEFT JOIN (SELECT p.* FROM old_versions p "
            f"JOIN old_ids pi ON pi.package_id=p.package_id WHERE {parent_filter}) p ON",
        )
        result = result.replace(
            "LEFT JOIN old_packages pkg ON",
            "LEFT JOIN (SELECT pkg.* FROM old_packages pkg "
            f"JOIN old_ids pi ON pi.package_id=pkg.package_id WHERE {parent_filter}) pkg ON",
        )
        result = result.replace(
            "LEFT JOIN candidate_map cm ON",
            "LEFT JOIN (SELECT * FROM candidate_map WHERE "
            f"hash(target_name) % {count} = {bucket}) cm ON",
        )
        result = result.replace(
            "LEFT JOIN old_versions source ON",
            "LEFT JOIN (SELECT si.* FROM old_versions si SEMI JOIN "
            "(SELECT DISTINCT source_package_id,source_version FROM candidate_map "
            f"WHERE hash(target_name) % {count} = {bucket}) sm ON "
            "sm.source_package_id=si.package_id AND sm.source_version=si.version) source ON",
        )
        return result
    version_dir = out / "versions_full"
    version_dir.mkdir()
    version_paths = []
    # A single wide COPY keeps all 54m rows in one join pipeline and can spill
    # beyond the bounded scratch budget.  Hash buckets keep each join/output
    # working set bounded while preserving every row and its exact projection.
    row_count = con.execute("SELECT count(*) FROM current").fetchone()[0]
    bucket_count = (1 if provenance_format != "parquet" else
                    (output_buckets if output_buckets is not None else
                     min(16, max(1, (row_count + 999_999) // 1_000_000))))
    progress("write_versions")
    for bucket in range(bucket_count):
        version_path = version_dir / f"part-{bucket:06d}.parquet"
        con.execute("COPY (" + bucket_query(bucket, bucket_count) + ") TO ? "
                    "(FORMAT PARQUET, COMPRESSION ZSTD)", [str(version_path)])
        version_paths.append(version_path)
        progress(f"version_bucket_{bucket + 1}_of_{bucket_count}")

    parent = dict(parent_identity or {})
    provenance_base = f"""SELECT c.{name} AS name,c.{version} AS version,c.row_kind,
        CASE WHEN c.row_kind='existing_version' THEN 'preserved'
             WHEN c.row_kind='new_version' AND cm.source_version IS NOT NULL THEN 'inherited'
             WHEN c.row_kind='new_version' THEN 'missing'
             ELSE 'missing' END AS status,
        CASE WHEN c.row_kind='existing_version' THEN c.{version}
             ELSE cm.source_version END AS source_version
        FROM current c LEFT JOIN candidate_map cm
          ON cm.target_name=c.{name} AND cm.target_version=c.{version}
        """
    if provenance_format == "parquet":
        progress("write_provenance_parquet")
        provenance_dir = out / "metadata_provenance"
        provenance_dir.mkdir()
        provenance_path = provenance_dir / "part-000000.parquet"
        # This projection is narrow and has no wide metadata joins. Stream it
        # once instead of rescanning all current rows for every version bucket.
        con.execute(
            "COPY (SELECT p.*, " + _parent_struct_sql(parent) +
            " AS parent FROM (" + provenance_base + ") p) TO ? "
            "(FORMAT PARQUET, COMPRESSION ZSTD)",
            [str(provenance_path)],
        )
        provenance_paths = [provenance_path]
    else:
        provenance_path = out / "metadata_provenance.jsonl"
        cursor = con.execute(provenance_base + f" ORDER BY c.{name},c.{version}")
        with provenance_path.open("x", encoding="utf-8") as stream:
            while batch := cursor.fetchmany(8192):
                for row in batch:
                    stream.write(json.dumps({"name": row[0], "version": row[1], "row_kind": row[2],
                                             "status": row[3], "source_version": row[1] if row[2] == 'existing_version' else row[4],
                                             "parent": parent}, ensure_ascii=False, default=str) + "\n")
    con.execute("DROP VIEW current")
    if current_path.is_file():
        current_path.unlink()
    try:
        working_dir.rmdir()
    except OSError:
        pass
    progress("complete")
    result = {"versions": version_paths, "provenance":
              provenance_paths if provenance_format == "parquet" else provenance_path}
    return result
