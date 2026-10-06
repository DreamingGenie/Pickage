"""Read-only validation of historical calculation keys against PostgreSQL.

The validator deliberately stages the two key files in temporary tables.  It
never inserts into a service table, and its durable-table checks run in one
repeatable-read, read-only transaction.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import re
from pathlib import Path
from typing import Any

from pipeline.postgresql.postgres import PgLoader


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_INT32_MAX = 2_147_483_647
_TABLES = {
    "identities": ("_h7_identities", ("package_id", "name")),
    "versions": ("_h7_versions", ("package_id", "version")),
}


def _literal(value: Any) -> str:
    return PgLoader._literal(value)


def _copy_field(value: str | int) -> bytes:
    return (str(value).replace("\\", "\\\\").replace("\t", "\\t")
            .replace("\n", "\\n").replace("\r", "\\r").encode("utf-8"))


def copy_file(database: PgLoader, table: str, columns: tuple[str, ...] | list[str], path: str | Path) -> dict[str, Any]:
    """COPY a UTF-8 text transport file into an already-created temp table.

    Data is streamed in 1 MiB blocks; the file is never loaded into a Python
    list.  ``table`` and ``columns`` are intentionally restricted to the two
    validator staging tables so this helper cannot accidentally target a
    durable relation.
    """
    expected = {name: cols for name, (_, cols) in _TABLES.items()}
    if table not in {v[0] for v in _TABLES.values()}:
        raise ValueError("copy_file only permits validator temporary tables")
    allowed = next(cols for temp, cols in _TABLES.values() if temp == table)
    if tuple(columns) != tuple(allowed):
        raise ValueError("unexpected COPY columns")
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    command = (f"COPY pg_temp.{table} ({','.join(columns)}) FROM STDIN "
               "WITH (FORMAT text, DELIMITER E'\\t', NULL '\\N', ENCODING 'UTF8');\n")
    try:
        database._process.stdin.write(command.encode("utf-8"))
        with source.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                database._process.stdin.write(block)
        database._process.stdin.write(b"\\.\n")
        database._process.stdin.flush()
    except (BrokenPipeError, OSError) as error:
        raise database._error() from error
    database._send("SELECT 1;")
    return {"path": str(source), "bytes": source.stat().st_size,
            "sha256": _file_sha256(source)}


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _date(value: Any) -> str:
    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        raise ValueError("calendar snapshot_at must be YYYY-MM-DD")
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("calendar snapshot_at must be a valid ISO date") from error
    return value


def _timestamp(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("calendar snapshot_timestamp must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("calendar snapshot_timestamp must be an ISO timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError("calendar snapshot_timestamp must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SHA_RE.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase SHA-256")
    return value


def _lineage_parts(lineage: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(lineage, dict):
        raise ValueError("lineage must be an object")
    population = dict(lineage.get("population")) if isinstance(lineage.get("population"), dict) else None
    calendar_lineage = dict(lineage.get("calendar")) if isinstance(lineage.get("calendar"), dict) else None
    if not isinstance(population, dict) or not isinstance(calendar_lineage, dict):
        raise ValueError("lineage must contain population and calendar")
    for field in ("run_id", "snapshot"):
        if not isinstance(population.get(field), str) or not population[field]:
            raise ValueError(f"population.{field} is required")
    population["snapshot"] = _date(population["snapshot"])
    population["snapshot_timestamp"] = _timestamp(population.get("snapshot_timestamp"))
    population["manifest_sha256"] = _sha(population.get("manifest_sha256"), "population.manifest_sha256")
    calendar_lineage["manifest_sha256"] = _sha(calendar_lineage.get("manifest_sha256"), "calendar.manifest_sha256")
    if "run_id" in calendar_lineage and (not isinstance(calendar_lineage["run_id"], str) or not calendar_lineage["run_id"]):
        raise ValueError("calendar.run_id must be a non-empty string when provided")
    return population, calendar_lineage


def _calendar_values(calendar: list[dict[str, Any]]) -> list[tuple[str, str]]:
    if not isinstance(calendar, list) or not calendar:
        raise ValueError("calendar must contain at least one row")
    values = [(_date(row.get("snapshot_at")), _timestamp(row.get("snapshot_timestamp")))
              if isinstance(row, dict) else (_date(None), _timestamp(None)) for row in calendar]
    if len({row[0] for row in values}) != len(values):
        raise ValueError("calendar dates must be unique")
    return values


def check_lineage(database: PgLoader, lineage: dict[str, Any], calendar: list[dict[str, Any]]) -> dict[str, Any]:
    """Check population and calendar provenance using SELECTs only."""
    population, calendar_lineage = _lineage_parts(lineage)
    values = _calendar_values(calendar)
    current = database._send(
        "SELECT count(*) FROM public.etl_dataset_current c "
        "JOIN public.etl_load_execution e ON e.dataset=c.dataset AND e.execution_id=c.execution_id "
        "AND e.snapshot_at=c.snapshot_at AND e.manifest_sha256=c.manifest_sha256 "
        f"WHERE c.dataset='package-version' AND e.curated_run_id={_literal(population['run_id'])} "
        f"AND c.snapshot_at={_literal(population['snapshot'])} "
        f"AND c.manifest_sha256={_literal(population['manifest_sha256'])} "
        f"AND e.snapshot_at={_literal(population['snapshot'])} "
        f"AND e.snapshot_timestamp={_literal(population['snapshot_timestamp'])}::timestamptz AT TIME ZONE 'UTC' AND e.status='PUBLISHED';")[0]
    if int(current) != 1:
        raise ValueError("published package-version population lineage does not match")
    rows = ",".join(f"({_literal(day)}::date,{_literal(stamp)}::timestamptz)" for day, stamp in values)
    run_filter = ""
    if calendar_lineage.get("run_id"):
        run_filter = f" AND e.execution_id={_literal(calendar_lineage['run_id'])}"
    missing = database._send(
        "SELECT count(*) FROM (VALUES " + rows + ") AS wanted(snapshot_at,snapshot_timestamp) "
        "WHERE NOT EXISTS (SELECT 1 FROM public.etl_snapshot_reference r "
        "JOIN public.etl_load_execution e ON e.dataset=r.dataset AND e.execution_id=r.execution_id "
        "WHERE r.snapshot_at=wanted.snapshot_at AND r.snapshot_timestamp=wanted.snapshot_timestamp "
        f"AND e.status='PUBLISHED' AND e.manifest_sha256={_literal(calendar_lineage['manifest_sha256'])}{run_filter});")[0]
    if int(missing) != 0:
        raise ValueError("calendar lineage does not match published snapshot references")
    return {"population": "MATCHED", "calendar": "MATCHED", "snapshot_count": len(values)}


def verify_keys(command: list[str], work_dir: str | Path, identity_file: str | Path,
                version_file: str | Path, calendar: list[dict[str, Any]], lineage: dict[str, Any],
                expected: dict[str, int]) -> dict[str, Any]:
    """Validate generated identity/version files against an isolated database."""
    if not isinstance(expected, dict) or set(expected) != {"identities", "versions"}:
        raise ValueError("expected must contain identities and versions")
    if any(type(value) is not int or value < 0 for value in expected.values()):
        raise ValueError("expected counts must be non-negative integers")
    values = _calendar_values(calendar)
    _lineage_parts(lineage)
    with PgLoader(command, Path(work_dir)) as database:
        database_name = database._send("SELECT current_database();")
        if len(database_name) != 1 or not database_name[0]:
            raise RuntimeError("could not determine validation database")
        database._send(
            "CREATE TEMP TABLE _h7_identities(package_id integer NOT NULL CHECK(package_id>0), "
            "name varchar(300) NOT NULL CHECK(length(trim(name))>0)); "
            "CREATE TEMP TABLE _h7_versions(package_id integer NOT NULL CHECK(package_id>0), "
            "version varchar(100) NOT NULL CHECK(length(trim(version))>0));")
        files = {
            "identities": copy_file(database, "_h7_identities", ("package_id", "name"), identity_file),
            "versions": copy_file(database, "_h7_versions", ("package_id", "version"), version_file),
        }
        database._send(
            "CREATE UNIQUE INDEX ON pg_temp._h7_identities(package_id); "
            "CREATE UNIQUE INDEX ON pg_temp._h7_identities(name); "
            "CREATE UNIQUE INDEX ON pg_temp._h7_versions(package_id,version); "
            "ANALYZE pg_temp._h7_identities; ANALYZE pg_temp._h7_versions;")
        counts = {"identities": int(database._send("SELECT count(*) FROM pg_temp._h7_identities;")[0]),
                  "versions": int(database._send("SELECT count(*) FROM pg_temp._h7_versions;")[0])}
        if counts != expected:
            raise ValueError(f"staged key counts differ from expected: {counts} != {expected}")
        database._send("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;")
        try:
            if int(database._send("SELECT count(*) FROM pg_temp._h7_versions v LEFT JOIN pg_temp._h7_identities i USING(package_id) WHERE i.package_id IS NULL;")[0]):
                raise ValueError("version package_id is missing from identity file")
            if int(database._send("SELECT count(*) FROM pg_temp._h7_identities i LEFT JOIN public.package p USING(package_id) WHERE p.package_id IS NULL OR p.name IS DISTINCT FROM i.name;")[0]):
                raise ValueError("DB package ID/name does not match identity file")
            if int(database._send("SELECT count(*) FROM pg_temp._h7_versions v LEFT JOIN public.version d USING(package_id,version) WHERE d.package_id IS NULL;")[0]):
                raise ValueError("DB version composite key is missing")
            lineage_report = check_lineage(database, lineage, calendar)
        finally:
            database._send("ROLLBACK;")
    return {"status": "VERIFIED", "database": database_name[0], "counts": counts,
            "calendar": {"rows": len(values)}, "files": files, "lineage": lineage_report}
