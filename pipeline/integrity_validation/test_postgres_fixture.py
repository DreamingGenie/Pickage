"""Opt-in PostgreSQL contract checks for the tiny integrity fixture.

The module never starts or removes containers.  It runs only when the caller
explicitly supplies a disposable container name in ``INTEGRITY_TEST_CONTAINER``.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import unittest

from pipeline.integrity_validation.queries import CHECKS
from pipeline.integrity_validation.schema import TABLES


CONTAINER = os.environ.get("INTEGRITY_TEST_CONTAINER", "")
DB = "integrity09_fixture"
FIXTURE = Path(__file__).with_name("fixtures") / "normal.json"
SKIP_REASON = "INTEGRITY_TEST_CONTAINER is not set to an explicitly prefixed container"


def _sql_literal(value, kind):
    if value is None:
        return "NULL"
    if kind in ("INTEGER", "BIGINT"):
        return str(value)
    escaped = str(value).replace("'", "''")
    if kind == "JSON":
        return f"'{escaped}'::json"
    if kind == "DATE":
        return f"'{escaped}'::date"
    if kind.startswith("TIMESTAMP"):
        return f"'{escaped}'::{kind.lower()}"
    return f"'{escaped}'"


def _run(sql: str, *, check=True):
    if not CONTAINER.startswith("integrity09-fixture-"):
        raise unittest.SkipTest(SKIP_REASON)
    command = ["docker", "exec", "-i", CONTAINER, "psql", "-X", "-U", "postgres", "-d", DB,
               "-v", "ON_ERROR_STOP=1", "-Atq", "-f", "-"]
    result = subprocess.run(command, input="\\set VERBOSITY verbose\n" + sql, text=True, encoding="utf-8",
                            capture_output=True, check=False, timeout=30)
    if check and result.returncode:
        detail = " ".join(result.stderr.split())[:500]
        raise RuntimeError(f"psql failed ({result.returncode}): {detail}")
    return result


def _validation_ddl():
    statements = ["CREATE SCHEMA IF NOT EXISTS validation"]
    for qualified, columns in TABLES.items():
        if qualified.startswith("public."):
            continue
        schema, table = qualified.split(".", 1)
        definition = ", ".join(f'"{name}" {kind}' for name, kind in columns)
        statements.append(f'CREATE TABLE "{schema}"."{table}" ({definition})')
    return ";".join(statements) + ";"


def _fixture_inserts(document):
    statements = []
    order = ("public.package", "public.snapshot", "public.version", "public.package_snapshot",
             "public.package_version_snapshot", "validation.snapshot_context",
             "validation.package_population", "validation.target_population",
             "validation.resolved_edges", "validation.source_quality",
             "validation.expected_package_metrics")
    for qualified in order:
        rows = document["tables"].get(qualified, [])
        columns = TABLES[qualified]
        names = ",".join(f'"{name}"' for name, _ in columns)
        values = []
        for row in rows:
            values.append("(" + ",".join(_sql_literal(row.get(name), kind) for name, kind in columns) + ")")
        if values:
            statements.append(f'INSERT INTO {qualified} ({names}) VALUES {",".join(values)}')
    return ";".join(statements) + ";"


@unittest.skipUnless(CONTAINER.startswith("integrity09-fixture-"), SKIP_REASON)
class PostgresFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The owner creates the disposable container and database.  This class
        # only resets its contents, then every test runs inside a rollback.
        ddl = Path("backend/src/main/resources/db/migration/V1__init.sql").read_text(encoding="utf-8")
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        _run("DROP SCHEMA IF EXISTS validation CASCADE;DROP SCHEMA IF EXISTS public CASCADE;CREATE SCHEMA public;" + ddl + _validation_ddl() + _fixture_inserts(fixture))

    def setUp(self):
        # Each docker exec opens a new psql session, so transaction-scoped
        # mutations are issued as one command below and explicitly rolled back.
        pass

    def _check_results(self):
        return {check["id"]: int(_run(check["sql"]).stdout.strip() or "0") for check in CHECKS}

    def test_normal_fixture_passes_all_postgresql_checks(self):
        self.assertEqual(self._check_results(), {check["id"]: 0 for check in CHECKS})

    def test_null_package_name_is_detected(self):
        check = next(item["sql"] for item in CHECKS if item["id"] == "package_identity")
        result = _run("BEGIN;UPDATE public.package SET name='' WHERE package_id=1;" + check + ";ROLLBACK;")
        self.assertGreater(int(result.stdout.strip()), 0)

    def test_missing_population_row_is_detected(self):
        check = next(item["sql"] for item in CHECKS if item["id"] == "package_snapshot_population")
        result = _run("BEGIN;DELETE FROM validation.package_population WHERE package_id=1 AND snapshot_at='2026-01-01';" + check + ";ROLLBACK;")
        self.assertGreater(int(result.stdout.strip()), 0)

    def test_composite_foreign_key_rejects_mismatched_package_version(self):
        result = _run("INSERT INTO public.package_version_snapshot(package_id,version,snapshot_at,dependents_count) VALUES (1,'9.9.9','2026-01-01',0);", check=False)
        self.assertNotEqual(result.returncode, 0)

    def test_primary_key_rejects_duplicate_package(self):
        result = _run("INSERT INTO public.package(package_id,name) VALUES (1,'duplicate');", check=False)
        self.assertNotEqual(result.returncode, 0)

    def test_read_only_transaction_rejects_service_write_with_sqlstate_25006(self):
        result = _run("BEGIN READ ONLY; INSERT INTO public.package(package_id,name) VALUES (99,'blocked');", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("25006", result.stderr)

    def test_rollback_restores_mutated_row_count(self):
        before = int(_run("SELECT count(*) FROM public.package;").stdout.strip())
        result = _run("BEGIN;INSERT INTO public.package(package_id,name) VALUES (99,'temporary');SELECT count(*) FROM public.package;ROLLBACK;SELECT count(*) FROM public.package;")
        self.assertEqual([int(value) for value in result.stdout.splitlines()], [before + 1, before])


if __name__ == "__main__":
    unittest.main()
