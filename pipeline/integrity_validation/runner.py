"""Run bounded, synthetic integrity checks without any external connection."""
from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
import re

import duckdb

from pipeline.preprocessing.snapshot.policy import parse_timestamp
from .schema import SERVICE_TABLES, TABLES


MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 5000
DEFERRED_CHECKS = (
    "approved_native_run_manifests_and_all_file_hashes",
    "postgresql_schema_types_defaults_and_ordered_constraints",
    "full_database_rows_against_approved_source_population",
    "downloads_interval_and_repository_observation_source_reconciliation",
    "loader_failure_rollback_restart_and_concurrent_retry",
    "postgresql_query_plans_latency_wal_disk_and_cache_measurement",
)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"Invalid JSON constant: {value}")


def load_fixture(path: Path) -> tuple[dict, str]:
    with Path(path).open("rb") as stream:
        body = stream.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ValueError("Fixture exceeds the 2 MiB preparation limit")
    document = json.loads(body, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    return document, hashlib.sha256(body).hexdigest()


def _value(value, sql_type, label):
    if value is None:
        return None
    if sql_type in ("INTEGER", "BIGINT"):
        bits = 32 if sql_type == "INTEGER" else 64
        if type(value) is not int or not -(2 ** (bits - 1)) <= value < 2 ** (bits - 1):
            raise ValueError(f"{label}: expected signed {bits}-bit integer or explicit null")
        return value
    if not isinstance(value, str) or len(value) > 65536 or "\x00" in value:
        raise ValueError(f"{label}: expected a bounded string or explicit null")
    if sql_type == "DATE":
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError(f"{label}: expected YYYY-MM-DD")
        return parsed
    if sql_type == "TIMESTAMP":
        # This adapter declares V1's naive TIMESTAMP storage to mean UTC.
        return parse_timestamp(value, allow_naive_utc=True).replace(tzinfo=None)
    if sql_type == "JSON":
        json.loads(value, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    return value


def _prepare(document):
    required = {"format_version", "kind", "fixture_id", "tables", "expected_counts"}
    if not isinstance(document, dict) or set(document) != required:
        raise ValueError("Fixture root fields do not match format version 1")
    if type(document["format_version"]) is not int or document["format_version"] != 1:
        raise ValueError("Unsupported fixture format_version")
    if document["kind"] != "synthetic_fixture":
        raise ValueError("Only synthetic_fixture input is supported; native runs need their own validators")
    if not isinstance(document["fixture_id"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", document["fixture_id"]):
        raise ValueError("Invalid fixture_id")
    tables = document["tables"]
    counts = document["expected_counts"]
    if not isinstance(tables, dict) or set(tables) != set(TABLES):
        raise ValueError("Fixture must explicitly contain every service and evidence table")
    if not isinstance(counts, dict) or set(counts) != set(SERVICE_TABLES):
        raise ValueError("Expected row counts are required for all five service tables")
    if any(type(v) is not int or not 0 <= v <= MAX_ROWS for v in counts.values()):
        raise ValueError("Invalid expected row count")
    prepared, total = {}, 0
    for name, columns in TABLES.items():
        rows = tables[name]
        if not isinstance(rows, list):
            raise ValueError(f"{name}: rows must be a list")
        total += len(rows)
        if total > MAX_ROWS:
            raise ValueError("Fixture exceeds the 5000-row preparation limit")
        required_columns = {column for column, _ in columns}
        prepared[name] = []
        for row in rows:
            if not isinstance(row, dict) or set(row) != required_columns:
                raise ValueError(f"{name}: every column must be present; absent and explicit null differ")
            prepared[name].append(tuple(_value(row[column], kind, f"{name}.{column}")
                                        for column, kind in columns))
    if not tables["validation.snapshot_context"]:
        raise ValueError("At least one explicit snapshot context is required")
    if not tables["public.package"] or not tables["public.version"]:
        raise ValueError("An empty fixture cannot prove integrated key/count checks")
    return prepared


def validate_fixture(document: dict) -> dict:
    from .queries import CHECKS

    prepared = _prepare(document)
    results = []
    with duckdb.connect(":memory:", config={"threads": 1, "memory_limit": "128MB",
                                           "max_temp_directory_size": "0B"}) as connection:
        connection.execute("SET TimeZone='UTC'")
        for namespace in ("public", "validation"):
            connection.execute(f'CREATE SCHEMA "{namespace}"')
        for name, columns in TABLES.items():
            definitions = ",".join(f'"{column}" {kind}' for column, kind in columns)
            connection.execute(f"CREATE TABLE {name} ({definitions})")
            if prepared[name]:
                placeholders = ",".join("?" for _ in columns)
                connection.executemany(f"INSERT INTO {name} VALUES ({placeholders})", prepared[name])
        for name in SERVICE_TABLES:
            actual = connection.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
            expected = document["expected_counts"][name]
            results.append({"id": "rows_" + name.split(".")[1], "description": name + " 기대 행 수",
                            "status": "PASS" if actual == expected else "FAIL",
                            "violations": abs(actual - expected), "expected": expected, "actual": actual})
        for check in CHECKS:
            try:
                rows = connection.execute(check["sql"]).fetchall()
                if len(rows) != 1 or len(rows[0]) != 1 or type(rows[0][0]) is not int or rows[0][0] < 0:
                    raise ValueError("Check must return one nonnegative violation count")
                violations = rows[0][0]
                results.append({"id": check["id"], "description": check["description"],
                                "status": "FAIL" if violations else "PASS", "violations": violations})
            except (duckdb.Error, ValueError) as error:
                results.append({"id": check["id"], "description": check["description"],
                                "status": "ERROR", "violations": None, "error": str(error)})
    status = "ERROR" if any(r["status"] == "ERROR" for r in results) else (
        "FAIL" if any(r["status"] == "FAIL" for r in results) else "PASS")
    return {
        "report_version": 1, "scope": "SYNTHETIC_FIXTURE_ONLY", "fixture_id": document["fixture_id"],
        "fixture_content_sha256": hashlib.sha256(json.dumps(document, sort_keys=True, ensure_ascii=False,
                                                            separators=(",", ":")).encode("utf-8")).hexdigest(),
        "engine": {"name": "DuckDB", "version": duckdb.__version__, "threads": 1, "memory_limit": "128MB"},
        "validation_status": status, "ready_for_publication": False, "task_09_complete": False,
        "checks": results,
        "quality": document["tables"]["validation.source_quality"],
        "deferred_checks": [{"id": check, "status": "NOT_RUN"} for check in DEFERRED_CHECKS],
    }
