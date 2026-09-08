"""PostgreSQL 16 integration tests. Each test owns a newly created database.

Set PICKAGE_TEST_CONTAINER to an existing isolated PostgreSQL Docker container.
The tests never connect to the application's database and never run seed files.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

from pipeline.postgresql.postgres import PgLoader


ROOT = Path(__file__).resolve().parents[2]
CONTAINER = os.environ.get("PICKAGE_TEST_CONTAINER")


def field(value):
    if value is None:
        return "\\N"
    return str(value).replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")


@unittest.skipUnless(CONTAINER, "PICKAGE_TEST_CONTAINER is required for a real PostgreSQL test")
class PostgresIntegrationTests(unittest.TestCase):
    def sql(self, sql, *, database=None):
        result = subprocess.run(
            ["docker", "exec", "-i", CONTAINER, "psql", "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1",
             "-U", "postgres", "-d", database or self.database],
            input=sql.encode("utf-8"), capture_output=True, timeout=60)
        if result.returncode:
            raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
        return result.stdout.decode("utf-8").strip()

    def setUp(self):
        self.database = "pickage_267_test_" + uuid.uuid4().hex
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.sql(f'CREATE DATABASE "{self.database}";', database="postgres")
        self.addCleanup(self.drop_owned_database)
        migrations = sorted((ROOT / "backend/src/main/resources/db/migration").glob("V*.sql"))
        self.sql("BEGIN;\n" + migrations[0].read_text(encoding="utf-8") + "\nCOMMIT;")
        self.v1_service_schema = self.service_schema()
        self.sql("BEGIN;\n" + "\n".join(path.read_text(encoding="utf-8") for path in migrations[1:]) + "\nCOMMIT;")
        self.command = ["docker", "exec", "-i", CONTAINER, "psql", "-U", "postgres", "-d", self.database]
        self.packages = [(1, "@scope/한글", None), (2, "literal\\N", "")]
        self.versions = [
            ("1.0.0", 1, "2026-08-30 01:02:03.123456", 9223372036854775807,
             "한글\n\\.\r\tquotes\"'\\N", "[]", "", '{"dependencies":{},"peerDependencies":{},"optionalDependencies":{}}'),
            ("2.0.0", 1, None, 0, "", "null", "\\N", "{}"),
            ("1.0.0", 2, "2026-08-30 00:00:00.000001", 1, None, None, None, '{"dependencies":{}}'),
        ]

    def drop_owned_database(self):
        if not self.database.startswith("pickage_267_test_") or len(self.database) != len("pickage_267_test_") + 32:
            raise ValueError("refusing to drop a database outside the generated test namespace")
        self.sql(f'DROP DATABASE "{self.database}" WITH (FORCE);', database="postgres")

    def service_schema(self):
        return self.sql("""SELECT json_build_object(
            'columns',(SELECT json_agg(s ORDER BY table_name,ordinal_position) FROM (
                SELECT c.table_name,c.ordinal_position,c.column_name,c.data_type,
                       c.character_maximum_length,c.is_nullable,c.column_default,
                       col_description(format('public.%I',c.table_name)::regclass,c.ordinal_position) AS comment
                FROM information_schema.columns c WHERE c.table_schema='public'
                AND c.table_name IN ('package','version','snapshot','package_snapshot','package_version_snapshot')) s),
            'constraints',(SELECT json_agg(s ORDER BY table_name,name) FROM (
                SELECT conrelid::regclass::text AS table_name,conname AS name,pg_get_constraintdef(oid) AS definition
                FROM pg_constraint WHERE conrelid IN ('public.package'::regclass,'public.version'::regclass,
                'public.snapshot'::regclass,'public.package_snapshot'::regclass,'public.package_version_snapshot'::regclass)) s));""")

    def test_v2_preserves_all_five_service_table_contracts(self):
        self.assertEqual(json.loads(self.service_schema()), json.loads(self.v1_service_schema))
        self.assertEqual(self.sql("SELECT is_nullable FROM information_schema.columns WHERE table_schema='public' AND table_name='version' AND column_name='dependency';"), "NO")

    def test_dependency_sql_null_is_rejected_without_service_changes(self):
        self.versions[0] = (*self.versions[0][:-1], None)
        with self.assertRaisesRegex(RuntimeError, "not-null constraint"):
            self.publish()
        self.assertEqual(self.sql("SELECT (SELECT count(*) FROM public.package),(SELECT count(*) FROM public.version),(SELECT count(*) FROM public.etl_dataset_current);"), "0|0|0")
        self.assertEqual(self.sql("SELECT status FROM public.etl_load_execution;"), "FAILED")

    def files(self):
        paths = {}
        for table, rows in (("package", self.packages), ("version", self.versions)):
            path = self.root / (table + ".copy.tsv")
            path.write_bytes(("\n".join("\t".join(field(value) for value in row) for row in rows) + "\n").encode("utf-8"))
            paths[table] = [path]
        return paths

    def metadata(self, run="sample", snapshot="2026-08-31", parent=None):
        manifest = {"request": {"run_id": run, "snapshot": snapshot, "parent": parent}}
        return {"dataset": "package-version", "snapshot": snapshot,
                "snapshot_timestamp": snapshot + "T21:01:10.517131", "curated_run_id": run,
                "run_prefix": "depsdev/v1/package-version/snapshot=" + snapshot + "/run_id=" + run,
                "manifest_sha256": hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest(),
                "manifest": manifest, "counts": {"package": len(self.packages), "version": len(self.versions)}}

    def publish(self, metadata=None, execution="load-test", failpoint=None, contract="a" * 64):
        metadata = metadata or self.metadata()
        with PgLoader(self.command, self.root) as database:
            try:
                previous = database.start(metadata, execution, contract, uuid.uuid4().hex)
                return database.reverified() if previous else database.publish(self.files(), metadata["counts"], failpoint)
            except BaseException as error:
                database.fail(error)
                raise

    def test_roundtrip_values_counts_and_atomic_publication(self):
        result = self.publish()
        self.assertEqual(result["status"], "PUBLISHED")
        actual = json.loads(self.sql("SELECT json_agg(row_to_json(v) ORDER BY package_id,version) FROM public.version v;"))
        first = actual[0]
        self.assertEqual(first["description"], self.versions[0][4])
        self.assertEqual(first["published_at"], "2026-08-30T01:02:03.123456")
        self.assertEqual(first["ordinal"], 9223372036854775807)
        self.assertEqual(first["licenses"], [])
        self.assertEqual(first["dependency"], {"dependencies": {}, "peerDependencies": {}, "optionalDependencies": {}})
        self.assertEqual(self.sql("SELECT licenses IS NULL, licenses::text='null', dependency::text='{}' FROM public.version WHERE package_id=1 AND version='2.0.0';"), "f|t|t")
        self.assertEqual(self.sql("SELECT status FROM public.etl_load_execution;"), "PUBLISHED")
        self.assertEqual(self.sql("SELECT execution_id FROM public.etl_dataset_current;"), "load-test")

    def test_failure_after_package_write_rolls_back_and_retry_succeeds(self):
        with self.assertRaisesRegex(RuntimeError, "failpoint"):
            self.publish(failpoint="after_package_insert")
        self.assertEqual(self.sql('SELECT (SELECT count(*) FROM public.package),(SELECT count(*) FROM public.version),(SELECT count(*) FROM public.etl_dataset_current);'), "0|0|0")
        self.assertEqual(self.sql("SELECT status FROM public.etl_load_execution;"), "FAILED")
        self.publish()
        self.assertEqual(self.sql("SELECT string_agg(status,',' ORDER BY created_at) FROM public.etl_load_attempt;"), "FAILED,PUBLISHED")

    def test_database_copy_error_has_failure_history(self):
        self.versions[0] = (*self.versions[0][:5], "invalid-json", *self.versions[0][6:])
        with self.assertRaises(Exception):
            self.publish()
        self.assertEqual(self.sql("SELECT status FROM public.etl_load_execution;"), "FAILED")
        self.assertEqual(self.sql("SELECT count(*) FROM public.package;"), "0")

    def test_existing_id_name_collision_is_rejected_without_overwrite(self):
        self.sql("INSERT INTO public.package VALUES (1,'existing-owner',NULL);")
        with self.assertRaisesRegex(Exception, "collision"):
            self.publish()
        self.assertEqual(self.sql("SELECT name FROM public.package WHERE package_id=1;"), "existing-owner")
        self.assertEqual(self.sql("SELECT count(*) FROM public.version;"), "0")

    def test_existing_name_id_collision_is_rejected(self):
        self.sql("INSERT INTO public.package VALUES (99,'@scope/한글',NULL);")
        with self.assertRaisesRegex(Exception, "collision"):
            self.publish()
        self.assertEqual(self.sql("SELECT package_id FROM public.package;"), "99")

    def test_same_execution_other_input_or_contract_is_rejected(self):
        self.publish()
        with self.assertRaisesRegex(ValueError, "different input or contract"):
            self.publish(self.metadata(run="other"))
        with self.assertRaisesRegex(ValueError, "different input or contract"):
            self.publish(contract="b" * 64)
        self.assertEqual(self.sql("SELECT status FROM public.etl_load_execution;"), "PUBLISHED")

    def test_same_input_retry_records_reverification(self):
        self.publish()
        result = self.publish()
        self.assertEqual(result["action"], "REVERIFIED")
        self.assertEqual(self.sql("SELECT count(*) FROM public.version;"), "3")
        self.assertEqual(self.sql("SELECT count(*) FROM public.etl_load_attempt;"), "2")

    def test_historical_reverification_does_not_restore_old_properties(self):
        old = self.metadata()
        self.publish(old)
        self.packages[0] = (1, self.packages[0][1], "https://example.invalid/new")
        new = self.metadata(run="child", parent={"manifest_sha256": old["manifest_sha256"]})
        self.publish(new, execution="load-child")
        self.publish(old)
        self.publish(old, execution="old-new-execution")
        self.assertEqual(self.sql("SELECT repo_url FROM public.package WHERE package_id=1;"), "https://example.invalid/new")
        self.assertEqual(self.sql("SELECT execution_id FROM public.etl_dataset_current;"), "load-child")

    def test_unpublished_old_snapshot_and_ambiguous_same_snapshot_are_rejected(self):
        self.publish()
        with self.assertRaisesRegex(ValueError, "older"):
            self.publish(self.metadata(run="older", snapshot="2026-08-30"), execution="older")
        with self.assertRaisesRegex(ValueError, "lineage"):
            self.publish(self.metadata(run="unrelated"), execution="unrelated")
        self.assertEqual(self.sql("SELECT execution_id FROM public.etl_dataset_current;"), "load-test")

    def test_second_session_cannot_start_while_first_holds_lock(self):
        with PgLoader(self.command, self.root) as first:
            first.start(self.metadata(), "first", "a" * 64, uuid.uuid4().hex)
            with PgLoader(self.command, self.root) as second:
                with self.assertRaisesRegex(Exception, "lock|running|another|concurrent"):
                    second.start(self.metadata(), "second", "a" * 64, uuid.uuid4().hex)
            first.fail(RuntimeError("test ended before publishing"))
        self.assertEqual(self.sql("SELECT count(*) FROM public.etl_load_execution;"), "1")

    def test_delayed_failure_cannot_overwrite_a_new_attempt(self):
        old = PgLoader(self.command, self.root)
        with old:
            old.start(self.metadata(), "retry", "a" * 64, uuid.uuid4().hex)
        with PgLoader(self.command, self.root) as new:
            new.start(self.metadata(), "retry", "a" * 64, uuid.uuid4().hex)
            old.fail(RuntimeError("delayed old failure"))
            self.assertEqual(self.sql("SELECT status FROM public.etl_load_execution;"), "PREPARING")
            new.publish(self.files(), self.metadata()["counts"])
        self.assertEqual(self.sql("SELECT status FROM public.etl_load_execution;"), "PUBLISHED")

    def test_failed_input_reverification_keeps_original_publication(self):
        self.publish()
        with PgLoader(self.command, self.root) as database:
            self.assertTrue(database.start(self.metadata(), "load-test", "a" * 64, uuid.uuid4().hex))
            database.fail(ValueError("corrupt input after original publication"))
        self.assertEqual(self.sql("SELECT status FROM public.etl_load_execution;"), "PUBLISHED")
        self.assertEqual(self.sql("SELECT string_agg(status,',' ORDER BY created_at) FROM public.etl_load_attempt;"), "PUBLISHED,FAILED")

    def test_actual_curated_builder_to_loader_roundtrip(self):
        from pipeline.curated import build
        # The existing Curated test helpers use unittest discovery's local
        # imports; scope that search path to importing those existing fixtures.
        with patch.object(sys, "path", [str(ROOT / "pipeline/curated")] + sys.path):
            from pipeline.curated.test_build import _seed_bronze, _valid_inputs
            from pipeline.curated.test_storage import FakeS3
        from pipeline.postgresql.load import run

        s3 = FakeS3()
        versions, requirements = _valid_inputs(("alpha", "beta"))
        _seed_bronze(s3, self.root, versions, requirements)
        build.run(s3, "2026-08-31", "bronze-test", "curated-roundtrip",
                  self.root / "curated", workers=1, threads=1)
        original_objects = dict(s3.objects)
        result = run(s3, "2026-08-31", "curated-roundtrip", "roundtrip",
                     self.root / "load", self.command, workers=1, threads=1)
        self.assertEqual(result["counts"], {"package": 2, "version": 2})
        self.assertEqual(result["service_after_counts"], result["counts"])
        self.assertEqual(self.sql("SELECT count(*) FROM public.version WHERE dependency IS NOT NULL;"), "2")
        self.assertEqual(s3.objects, original_objects)
        verified = subprocess.run([sys.executable, str(ROOT / "scripts/verify_package_version_load.py"),
                                   "--report", result["report_path"], "--docker-container", CONTAINER,
                                   "--database", self.database, "--output", str(self.root / "verification.json")],
                                  capture_output=True, timeout=60)
        self.assertEqual(verified.returncode, 0, verified.stderr.decode("utf-8", errors="replace"))
        self.assertEqual(json.loads((self.root / "verification.json").read_text(encoding="utf-8"))["status"], "PASSED")

    def test_null_dependency_defaulted_with_quality_history_and_reverification(self):
        import duckdb
        from pipeline.postgresql.test_input import InputTests, SNAPSHOT, RUN_ID
        from pipeline.postgresql.input import DEFAULT_DEPENDENCY
        from pipeline.postgresql.load import run

        fixture = InputTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        source = Path(fixture.temp.name)
        with duckdb.connect() as con:
            con.execute("CREATE TABLE v AS SELECT * FROM read_parquet(?)", [str(source / "version.parquet")])
            con.execute("UPDATE v SET dependency=NULL")
            con.execute(f"COPY v TO '{(source / 'null-version.parquet').as_posix()}' (FORMAT PARQUET)")
        fixture._install(source / "package.parquet", source / "null-version.parquet")
        original_objects = dict(fixture.s3.objects)
        result = run(fixture.s3, SNAPSHOT, RUN_ID, "defaulted", self.root / "defaulted", self.command, workers=1, threads=1)
        self.assertEqual(json.loads(self.sql("SELECT dependency FROM public.version;")), DEFAULT_DEPENDENCY)
        quality = result["quality"]["dependency_defaulted"]
        self.assertEqual(quality["count"], 1)
        self.assertEqual(json.loads(self.sql("SELECT quality_report FROM public.etl_load_attempt;")), result["quality"])
        self.assertEqual(fixture.s3.objects, original_objects)
        verified = subprocess.run([sys.executable, str(ROOT / "scripts/verify_package_version_load.py"),
                                   "--report", result["report_path"], "--docker-container", CONTAINER,
                                   "--database", self.database, "--output", str(self.root / "defaulted-verification.json")],
                                  capture_output=True, timeout=60)
        self.assertEqual(verified.returncode, 0, verified.stderr.decode("utf-8", errors="replace"))
        second = run(fixture.s3, SNAPSHOT, RUN_ID, "defaulted", self.root / "defaulted", self.command, workers=1, threads=1)
        self.assertEqual(second["action"], "REVERIFIED")
        self.assertEqual(second["quality"]["dependency_defaulted"]["sha256"], quality["sha256"])
        self.assertEqual(self.sql("SELECT count(*) FROM public.version;"), "1")
        self.assertEqual(self.sql("SELECT count(*) FROM public.etl_load_attempt WHERE quality_report->'dependency_defaulted'->>'count'='1';"), "2")


if __name__ == "__main__":
    unittest.main()
