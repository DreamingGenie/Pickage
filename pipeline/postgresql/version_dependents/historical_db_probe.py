"""Bounded PostgreSQL probe for applying dependents-count samples.

This module is deliberately restricted to databases named
``pickage_193_probe_<32 lowercase hex characters>``.  It is a validation aid
for the H6 load shape and does not publish an ETL run or change the service
loader.
"""
from __future__ import annotations

from datetime import date
import re
from pathlib import Path

from pipeline.postgresql.postgres import PgLoader


_DATABASE_RE = re.compile(r"^pickage_193_probe_[0-9a-f]{32}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_INT32_MAX = 2_147_483_647


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError(f"{field} must be a non-empty string without NUL")
    return value


def _iso_date(value: object, field: str) -> str:
    value = _text(value, field)
    if not _DATE_RE.fullmatch(value):
        raise ValueError(f"{field} must be an ISO date (YYYY-MM-DD)")
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO date (YYYY-MM-DD)") from error
    return value


def _positive_int32(value: object, field: str) -> int:
    if type(value) is not int or not 0 < value <= _INT32_MAX:
        raise ValueError(f"{field} must be a positive int32")
    return value


def _nonnegative_int32(value: object, field: str) -> int:
    if type(value) is not int or not 0 <= value <= _INT32_MAX:
        raise ValueError(f"{field} must be a non-negative int32")
    return value


def _copy_field(value: object) -> bytes:
    """Encode one non-NULL PostgreSQL COPY TEXT field."""
    return (str(value).replace("\\", "\\\\").replace("\t", "\\t")
            .replace("\n", "\\n").replace("\r", "\\r").encode("utf-8"))


def _copy_rows(database: PgLoader, table: str, columns: str, rows: list[tuple]) -> None:
    command = (f"COPY pg_temp.{table} ({columns}) FROM STDIN "
               "WITH (FORMAT text, NULL '\\N', ENCODING 'UTF8');\n")
    try:
        database._process.stdin.write(command.encode("utf-8"))
        for row in rows:
            database._process.stdin.write(b"\t".join(_copy_field(v) for v in row) + b"\n")
        database._process.stdin.write(b"\\.\n")
        database._process.stdin.flush()
    except (BrokenPipeError, OSError) as error:
        raise database._error() from error
    database._send("SELECT 1;")


def _catalog_inputs(names: list[str], dates: list[str]) -> tuple[list[str], list[str]]:
    if not isinstance(names, list) or len(names) > 32:
        raise ValueError("names must contain at most 32 items")
    if not isinstance(dates, list) or len(dates) > 4:
        raise ValueError("dates must contain at most 4 items")
    clean_names = [_text(value, "name") for value in names]
    clean_dates = [_iso_date(value, "snapshot_at") for value in dates]
    if len(set(clean_names)) != len(clean_names) or len(set(clean_dates)) != len(clean_dates):
        raise ValueError("duplicate names or dates are not allowed")
    return clean_names, clean_dates


def _in_list(values: list[str]) -> str:
    return ",".join(PgLoader._literal(value) for value in values) or "NULL"


def read_catalog(command: list[str], work_dir: Path, names: list[str], dates: list[str]) -> dict:
    """Read bounded package/version/snapshot identities in a read-only transaction."""
    names, dates = _catalog_inputs(names, dates)
    with PgLoader(command, Path(work_dir)) as database:
        database._send("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;")
        package_rows = database._send(
            "SELECT row_to_json(x) FROM (SELECT package_id,name FROM public.package "
            f"WHERE name IN ({_in_list(names)}) ORDER BY package_id) x;")
        version_rows = database._send(
            "SELECT row_to_json(x) FROM (SELECT v.package_id,v.version FROM public.version v "
            "JOIN public.package p ON p.package_id=v.package_id "
            f"WHERE p.name IN ({_in_list(names)}) ORDER BY v.package_id,v.version) x;")
        snapshot_rows = database._send(
            "SELECT row_to_json(x) FROM (SELECT snapshot_at FROM public.snapshot "
            f"WHERE snapshot_at IN ({_in_list(dates)}) ORDER BY snapshot_at) x;")
        database._send("ROLLBACK;")
    import json
    return {"packages": [json.loads(row) for row in package_rows],
            "versions": [json.loads(row) for row in version_rows],
            "snapshots": [json.loads(row) for row in snapshot_rows]}


def validate_rows(counts: list[dict], identities: list[dict]) -> tuple[list[tuple], list[tuple]]:
    if not isinstance(counts, list) or len(counts) > 100_000:
        raise ValueError("counts must contain at most 100000 rows")
    if not isinstance(identities, list) or len(identities) > 100_000:
        raise ValueError("identities must contain at most 100000 rows")
    identity_rows = []
    identity_keys = set()
    identity_names = set()
    for row in identities:
        if not isinstance(row, dict):
            raise ValueError("identity rows must be objects")
        package_id = _positive_int32(row.get("package_id"), "package_id")
        name = _text(row.get("name"), "name")
        if len(name) > 300:
            raise ValueError("name exceeds 300 characters")
        if package_id in identity_keys or name in identity_names:
            raise ValueError("duplicate identity key")
        identity_keys.add(package_id)
        identity_names.add(name)
        identity_rows.append((package_id, name))
    count_rows = []
    count_keys = set()
    for row in counts:
        if not isinstance(row, dict):
            raise ValueError("count rows must be objects")
        package_id = _positive_int32(row.get("package_id"), "package_id")
        version = _text(row.get("version"), "version")
        if len(version) > 100:
            raise ValueError("version exceeds 100 characters")
        snapshot_at = _iso_date(row.get("snapshot_at"), "snapshot_at")
        dependents_count = _nonnegative_int32(row.get("dependents_count"), "dependents_count")
        key = (package_id, version, snapshot_at)
        if key in count_keys:
            raise ValueError("duplicate count key")
        count_keys.add(key)
        count_rows.append(key + (dependents_count,))
    count_package_ids = {row[0] for row in count_rows}
    if not count_package_ids.issubset(identity_keys):
        raise ValueError("every count package_id must have an identity")
    return count_rows, identity_rows


def apply_sample(command: list[str], work_dir: Path, counts: list[dict], identities: list[dict]) -> dict:
    """Atomically upsert a bounded sample into an explicitly isolated probe DB."""
    count_rows, identity_rows = validate_rows(counts, identities)
    with PgLoader(command, Path(work_dir)) as database:
        current = database._send("SELECT current_database();")
        if len(current) != 1 or not _DATABASE_RE.fullmatch(current[0]):
            raise PermissionError("apply_sample only permits pickage_193_probe_<uuid> databases")
        database._send(
            "BEGIN; CREATE TEMP TABLE _h6_identities (package_id INT NOT NULL, name VARCHAR(300) NOT NULL); "
            "CREATE TEMP TABLE _h6_counts (package_id INT NOT NULL, version VARCHAR(100) NOT NULL, "
            "snapshot_at DATE NOT NULL, dependents_count INT NOT NULL);")
        _copy_rows(database, "_h6_identities", "package_id,name", identity_rows)
        _copy_rows(database, "_h6_counts", "package_id,version,snapshot_at,dependents_count", count_rows)
        database._send("CREATE UNIQUE INDEX ON _h6_identities(package_id); CREATE UNIQUE INDEX ON _h6_counts(package_id,version,snapshot_at);")
        bad_identity = database._send(
            "SELECT count(*) FROM _h6_identities i LEFT JOIN public.package p USING(package_id) "
            "WHERE p.package_id IS NULL OR p.name IS DISTINCT FROM i.name;")[0]
        if int(bad_identity) != 0:
            raise ValueError("identity does not match public.package")
        bad_count = database._send(
            "SELECT count(*) FROM _h6_counts c LEFT JOIN public.version v USING(package_id,version) "
            "LEFT JOIN public.snapshot s USING(snapshot_at) "
            "WHERE v.package_id IS NULL OR s.snapshot_at IS NULL;")[0]
        if int(bad_count) != 0:
            raise ValueError("count references a missing version or snapshot")
        changed = database._send(
            "WITH changed AS (INSERT INTO public.package_version_snapshot "
            "(package_id,version,snapshot_at,dependents_count) "
            "SELECT package_id,version,snapshot_at,dependents_count FROM _h6_counts "
            "ON CONFLICT (package_id,version,snapshot_at) DO UPDATE SET dependents_count=EXCLUDED.dependents_count "
            "WHERE public.package_version_snapshot.dependents_count IS DISTINCT FROM EXCLUDED.dependents_count "
            "RETURNING 1) SELECT count(*) FROM changed;")[0]
        mismatch = database._send(
            "SELECT count(*) FROM _h6_counts c LEFT JOIN public.package_version_snapshot p "
            "USING(package_id,version,snapshot_at) WHERE p.package_id IS NULL "
            "OR p.dependents_count IS DISTINCT FROM c.dependents_count;")[0]
        if int(mismatch) != 0:
            raise RuntimeError("stored sample values failed verification")
        database._send("COMMIT;")
    return {"rows": len(count_rows), "changed_rows": int(changed)}
