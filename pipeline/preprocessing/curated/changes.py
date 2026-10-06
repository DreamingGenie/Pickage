"""Build deterministic package and version upsert files from Curated runs.

The comparison is deliberately based on the native Parquet columns.  A change
to a metric or to a lineage column therefore remains visible to the eventual
database loader.  JSON values are compared after parsing and sorting object
keys, so serialization order is not treated as a data change.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import shutil
import uuid
from typing import Iterable

import duckdb


_JSON_COLUMNS = {"dependency", "dependencies", "peer_dependencies",
                 "optional_dependencies", "licenses"}
_BUCKET_ROWS = 1_000_000


def _paths(value: Iterable[str | Path], label: str) -> list[Path]:
    paths = [Path(p).resolve() for p in value]
    if not paths:
        raise ValueError(f"{label} must contain at least one Parquet file")
    if any(not p.is_file() or p.suffix.lower() != ".parquet" for p in paths):
        raise ValueError(f"{label} contains a missing or non-Parquet file")
    return paths


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _read_view(con, name: str, paths: list[Path]) -> tuple[list[str], dict[str, str]]:
    joined = ",".join(_sql_literal(p.as_posix()) for p in paths)
    con.execute(f"CREATE VIEW {_ident(name)} AS SELECT * FROM read_parquet([{joined}], hive_partitioning=false)")
    schema = [(row[0], str(row[1]).upper()) for row in con.execute(f"DESCRIBE {_ident(name)}").fetchall()]
    return [name for name, _ in schema], dict(schema)


def _identity(columns: list[str], kind: str) -> list[str]:
    if kind == "package":
        candidates = [["package_id"]]
    else:
        candidates = [["package_id", "version"], ["name", "version"]]
    for keys in candidates:
        if all(key in columns for key in keys):
            return keys
    raise ValueError(f"{kind} Parquet is missing its identity columns")


def _validate_keys(con, view: str, keys: list[str], kind: str) -> None:
    key_sql = ", ".join(_ident(key) for key in keys)
    nulls = " OR ".join(f"{_ident(key)} IS NULL" for key in keys)
    if con.execute(f"SELECT count(*) FROM {_ident(view)} WHERE {nulls}").fetchone()[0]:
        raise ValueError(f"{kind} input contains NULL identity")
    if con.execute(f"SELECT count(*) FROM (SELECT {key_sql} FROM {_ident(view)} GROUP BY {key_sql} HAVING count(*) > 1)").fetchone()[0]:
        raise ValueError(f"{kind} input contains duplicate identity")


def _json_columns(con, view: str, columns: list[str]) -> set[str]:
    types = {row[0]: row[1].upper()
             for row in con.execute(f"DESCRIBE {_ident(view)}").fetchall()}
    return {c for c in columns if c.lower() in _JSON_COLUMNS or "JSON" in types[c]}


def _bucket_predicate(alias: str, identity: list[str], bucket: int, buckets: int) -> str:
    values = ", ".join(f"CAST({alias}.{_ident(key)} AS VARCHAR)" for key in identity)
    return f"(hash(concat_ws(chr(31), {values})) % {buckets}) = {bucket}"


def _difference(con, current: str, previous: str, columns: list[str],
                identity: list[str], json_columns: set[str],
                *, bucket: int | None = None, buckets: int = 1) -> str:
    """Return a change query after materializing raw-difference candidates.

    Materializing candidates is intentional. DuckDB can decorrelate scalar
    ``json_tree`` subqueries out of a CASE expression, causing them to scan
    unchanged JSON values anyway. The candidate table contains only inserts,
    non-JSON changes, or rows whose JSON bytes differ, so semantic JSON walks
    are bounded by the actual change candidates.
    """
    join = " AND ".join(f"c.{_ident(k)} IS NOT DISTINCT FROM p.{_ident(k)}"
                        for k in identity)
    raw_changes = []
    semantic_changes = []
    old_aliases = {}
    select_old = []
    for col in columns:
        if col in identity:
            continue
        alias = f"__old_{len(old_aliases)}"
        old_aliases[col] = alias
        select_old.append(f"p.{_ident(col)} AS {_ident(alias)}")
        left, right = f"c.{_ident(col)}", _ident(alias)
        raw_left, raw_right = f"c.{_ident(col)}", f"p.{_ident(col)}"
        raw_changes.append(f"{raw_left} IS DISTINCT FROM {raw_right}")
        if col in json_columns:
            # json_tree's fullkey contains array indexes, while object keys are
            # sorted in the aggregate. This preserves array order and duplicate
            # elements, but ignores object member serialization order.
            left_json, right_json = f"CAST({left} AS JSON)", f"CAST({right} AS JSON)"
            left_tree = (f"(SELECT list(struct_pack(fullkey:=fullkey, type:=type, atom:=atom) "
                         f"ORDER BY fullkey, type, atom) FROM json_tree({left_json}))")
            right_tree = (f"(SELECT list(struct_pack(fullkey:=fullkey, type:=type, atom:=atom) "
                          f"ORDER BY fullkey, type, atom) FROM json_tree({right_json}))")
            left = (f"CASE WHEN {left} IS NOT DISTINCT FROM {right} THEN FALSE "
                    f"WHEN {left} IS NULL OR {right} IS NULL THEN TRUE "
                    f"ELSE {left_tree} IS DISTINCT FROM {right_tree} END")
            semantic_changes.append(left)
            continue
        semantic_changes.append(f"c.{_ident(col)} IS DISTINCT FROM {right}")
    candidate_name = _ident(f"change_candidates_{uuid.uuid4().hex}")
    bucket_sql = "" if bucket is None else f" AND {_bucket_predicate('c', identity, bucket, buckets)}"
    previous_source = _ident(previous)
    if bucket is not None:
        previous_source = (f"(SELECT * FROM {_ident(previous)} p0 "
                           f"WHERE {_bucket_predicate('p0', identity, bucket, buckets)})")
    raw_predicate = " OR ".join(raw_changes) or "FALSE"
    con.execute(
        f"CREATE TEMP TABLE {candidate_name} AS SELECT c.*, "
        f"p.{_ident(identity[0])} AS {_ident('__previous_key')}, "
        f"{', '.join(select_old)} "
        f"FROM {_ident(current)} c LEFT JOIN {previous_source} p ON {join} "
        f"WHERE (p.{_ident(identity[0])} IS NULL OR ({raw_predicate})){bucket_sql}"
    )
    insert = f"{_ident('__previous_key')} IS NULL"
    predicate = " OR ".join(semantic_changes) or "FALSE"
    current_columns = ", ".join(f"c.{_ident(col)}" for col in columns)
    return (f"SELECT {current_columns}, CASE WHEN {insert} THEN 'INSERT' ELSE 'UPDATE' END::VARCHAR AS change_type "
            f"FROM {candidate_name} c WHERE {insert} OR ({predicate})")


def _write(con, query: str, path: Path) -> dict:
    con.execute(f"COPY ({query}) TO {_sql_literal(path.as_posix())} "
                "(FORMAT PARQUET, COMPRESSION ZSTD)")
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return {"path": str(path), "sha256": digest.hexdigest(),
            "bytes": size, "rows": con.execute(
                f"SELECT count(*) FROM read_parquet({_sql_literal(path.as_posix())})"
            ).fetchone()[0]}


def _write_bucketed(con, query_factory, path: Path, work_dir: Path, buckets: int = 32) -> dict:
    """Write bounded bucket files, then consolidate them into the public path."""
    partials = []
    try:
        for bucket in range(buckets):
            partial = work_dir / f"{path.stem}-{bucket}.parquet"
            try:
                _write(con, query_factory(bucket), partial)
            finally:
                # Candidate tables are materialized per bucket so their
                # lifetime must end before the next bucket is built.
                names = con.execute(
                    "SELECT table_name FROM duckdb_tables() "
                    "WHERE temporary AND starts_with(table_name, 'change_candidates_')"
                ).fetchall()
                for (name,) in names:
                    con.execute(f"DROP TABLE IF EXISTS {_ident(name)}")
            partials.append(partial)
        files = ",".join(_sql_literal(p.as_posix()) for p in partials)
        con.execute(f"COPY (SELECT * FROM read_parquet([{files}])) TO {_sql_literal(path.as_posix())} "
                    "(FORMAT PARQUET, COMPRESSION ZSTD)")
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
        return {"path": str(path), "sha256": digest.hexdigest(), "bytes": size,
                "rows": con.execute(
                    f"SELECT count(*) FROM read_parquet({_sql_literal(path.as_posix())})"
                ).fetchone()[0]}
    finally:
        for partial in partials:
            partial.unlink(missing_ok=True)


def build_changes(previous_package_files, previous_version_files,
                  current_package_files, current_version_files, output_dir,
                  *, threads=2, memory_limit="1GB"):
    """Write package/version upserts and report identities missing in current.

    ``previous_*`` and ``current_*`` are iterables of Parquet paths.  The
    current rows are authoritative and deletions are intentionally omitted;
    ``missing_previous.parquet`` records identities present only in the prior
    run for quality review.
    """
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=False)
    pp, pv = _paths(previous_package_files, "previous_package_files"), _paths(previous_version_files, "previous_version_files")
    cp, cv = _paths(current_package_files, "current_package_files"), _paths(current_version_files, "current_version_files")
    con = duckdb.connect()
    temp_dir = None
    try:
        con.execute(f"SET threads={int(threads)}")
        con.execute(f"SET memory_limit={_sql_literal(memory_limit)}")
        con.execute("SET preserve_insertion_order=false")
        temp_dir = tempfile.mkdtemp(prefix=f".{out.name}-", dir=str(out.parent))
        con.execute(f"SET temp_directory={_sql_literal(temp_dir)}")
        results = {}
        for kind, old_paths, new_paths in (("package", pp, cp), ("version", pv, cv)):
            old, new = f"old_{kind}", f"new_{kind}"
            old_cols, old_types = _read_view(con, old, old_paths)
            new_cols, new_types = _read_view(con, new, new_paths)
            if old_cols != new_cols or old_types != new_types:
                raise ValueError(f"{kind} Parquet schemas differ between runs")
            keys = _identity(new_cols, kind)
            _validate_keys(con, old, keys, kind)
            _validate_keys(con, new, keys, kind)
            json_cols = _json_columns(con, new, new_cols)
            row_count = max(con.execute(f'SELECT count(*) FROM {_ident(new)}').fetchone()[0],
                            con.execute(f'SELECT count(*) FROM {_ident(old)}').fetchone()[0])
            buckets = min(16, max(1, (row_count + _BUCKET_ROWS - 1) // _BUCKET_ROWS))
            partial_dir = Path(temp_dir) / f"{kind}-upserts"
            partial_dir.mkdir(parents=True, exist_ok=True)
            results[f"{kind}_upserts"] = _write_bucketed(
                con,
                lambda bucket: _difference(con, new, old, new_cols, keys, json_cols,
                                           bucket=bucket, buckets=buckets),
                out / f"{kind}_upserts.parquet", Path(temp_dir) / f"{kind}-upserts", buckets)
            # Keep the native fields and add a stable quality reason.
            missing_dir = Path(temp_dir) / f"{kind}-missing"
            missing_dir.mkdir(parents=True, exist_ok=True)
            results.setdefault("missing_previous", {})[kind] = _write_bucketed(
                con,
                lambda bucket: (
                    f"SELECT m.*, 'MISSING_IN_CURRENT'::VARCHAR AS quality_reason "
                    f"FROM (SELECT p.* FROM {_ident(old)} p LEFT JOIN "
                    f"(SELECT * FROM {_ident(new)} c0 WHERE "
                    f"{_bucket_predicate('c0', keys, bucket, buckets)}) c ON "
                    + " AND ".join(f"p.{_ident(k)} IS NOT DISTINCT FROM c.{_ident(k)}" for k in keys)
                    + f" WHERE c.{_ident(keys[0])} IS NULL AND "
                    + _bucket_predicate('p', keys, bucket, buckets)
                    + ") m"
                ),
                out / f"missing_previous_{kind}.parquet", missing_dir, buckets)
        return {"output_dir": str(out), "files": results,
                "threads": int(threads), "memory_limit": memory_limit}
    finally:
        con.close()
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
