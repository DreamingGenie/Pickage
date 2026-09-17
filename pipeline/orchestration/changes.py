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
from typing import Iterable

import duckdb


_JSON_COLUMNS = {"dependency", "dependencies", "peer_dependencies",
                 "optional_dependencies", "licenses"}


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


def _difference(con, current: str, previous: str, columns: list[str],
                identity: list[str], json_columns: set[str]) -> str:
    join = " AND ".join(f"c.{_ident(k)} IS NOT DISTINCT FROM p.{_ident(k)}"
                        for k in identity)
    changes = []
    for col in columns:
        if col in identity:
            continue
        left, right = f"c.{_ident(col)}", f"p.{_ident(col)}"
        if col in json_columns:
            # json_tree's fullkey contains array indexes, while object keys are
            # sorted in the aggregate. This preserves array order and duplicate
            # elements, but ignores object member serialization order.
            left_json, right_json = f"CAST({left} AS JSON)", f"CAST({right} AS JSON)"
            left_tree = (f"(SELECT list(struct_pack(fullkey:=fullkey, type:=type, atom:=atom) "
                         f"ORDER BY fullkey, type, atom) FROM json_tree({left_json}))")
            right_tree = (f"(SELECT list(struct_pack(fullkey:=fullkey, type:=type, atom:=atom) "
                          f"ORDER BY fullkey, type, atom) FROM json_tree({right_json}))")
            left = (f"CASE WHEN {left} IS NULL OR {right} IS NULL THEN {left} IS DISTINCT FROM {right} "
                    f"ELSE {left_tree} IS DISTINCT FROM {right_tree} END")
            changes.append(left)
            continue
        changes.append(f"{left} IS DISTINCT FROM {right}")
    predicate = " OR ".join(changes) or "FALSE"
    return (f"SELECT c.*, CASE WHEN p.{_ident(identity[0])} IS NULL "
            f"THEN 'INSERT' ELSE 'UPDATE' END::VARCHAR AS change_type "
            f"FROM {_ident(current)} c LEFT JOIN {_ident(previous)} p ON {join} "
            f"WHERE p.{_ident(identity[0])} IS NULL OR ({predicate})")


def _write(con, query: str, path: Path) -> dict:
    con.execute(f"COPY ({query}) TO {_sql_literal(path.as_posix())} "
                "(FORMAT PARQUET, COMPRESSION ZSTD)")
    body = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(body).hexdigest(),
            "bytes": len(body), "rows": con.execute(
                f"SELECT count(*) FROM read_parquet({_sql_literal(path.as_posix())})"
            ).fetchone()[0]}


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
            results[f"{kind}_upserts"] = _write(
                con, _difference(con, new, old, new_cols, keys, json_cols),
                out / f"{kind}_upserts.parquet")
            missing = (f"SELECT p.* FROM {_ident(old)} p LEFT JOIN {_ident(new)} c ON "
                       + " AND ".join(f"p.{_ident(k)} IS NOT DISTINCT FROM c.{_ident(k)}" for k in keys)
                       + f" WHERE c.{_ident(keys[0])} IS NULL")
            # Keep the native fields and add a stable quality reason.
            results.setdefault("missing_previous", {})[kind] = _write(
                con, f"SELECT m.*, 'MISSING_IN_CURRENT'::VARCHAR AS quality_reason FROM ({missing}) m",
                out / f"missing_previous_{kind}.parquet")
        return {"output_dir": str(out), "files": results,
                "threads": int(threads), "memory_limit": memory_limit}
    finally:
        con.close()
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
