"""Disposable PostgreSQL tests for the package-snapshot publisher."""

from __future__ import annotations

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
import subprocess
import tempfile
import time
import unittest
import uuid

from pipeline.postgresql.package_snapshot.postgres import PackageSnapshotLoader


from pipeline.preprocessing.common.paths import REPO_ROOT

ROOT = REPO_ROOT
CONTAINER = os.environ.get("PICKAGE_PACKAGE_SNAPSHOT_TEST_CONTAINER")


@unittest.skipUnless(CONTAINER, "PICKAGE_PACKAGE_SNAPSHOT_TEST_CONTAINER is required")
class PackageSnapshotPostgresTests(unittest.TestCase):
    """Each test owns a fresh database and never touches the validation database."""

    def setUp(self):
        self.database = "pickage_288_test_" + uuid.uuid4().hex
        self.command = ["docker", "exec", "-i", CONTAINER, "psql", "-U", "postgres"]
        self.sql(f'CREATE DATABASE "{self.database}";', database="postgres")
        self.addCleanup(self.drop_database)
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        migration_dir = ROOT / "backend/src/main/resources/db/migration"
        for name in ("V1__init.sql", "V2__add_curated_load_execution.sql", "V3__add_snapshot_reference_execution.sql"):
            self.sql((migration_dir / name).read_text(encoding="utf-8"))
        self.seed_lineage()

    def sql(self, statement, *, database=None):
        result = subprocess.run(
            self.command + ["-d", database or self.database, "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1"],
            input=statement.encode("utf-8"), capture_output=True, timeout=60,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
        return result.stdout.decode("utf-8").strip()

    def drop_database(self):
        if not re.fullmatch(r"pickage_288_test_[0-9a-f]{32}", self.database):
            raise ValueError("refusing to drop database outside test namespace")
        self.sql(f'DROP DATABASE "{self.database}";', database="postgres")

    def seed_lineage(self):
        self.sql("""BEGIN;
            INSERT INTO package(package_id,name,repo_url) VALUES
              (1,'alpha','https://example.test/alpha'),(2,'beta','https://example.test/beta'),
              (3,'gamma','https://example.test/gamma');
            INSERT INTO version(version,package_id,ordinal,dependency) VALUES
              ('1.0.0',1,0,'{}'),('1.0.0',2,0,'{}'),('1.0.0',3,0,'{}');
            INSERT INTO snapshot(snapshot_at) VALUES (DATE '2026-08-24'),(DATE '2026-08-31');
            INSERT INTO etl_load_execution(execution_id,dataset,status,snapshot_at,snapshot_timestamp,
              curated_run_id,run_prefix,manifest_sha256,contract_sha256,input_metadata,expected_counts,active_attempt_id)
              VALUES ('population-execution','package-version','PUBLISHED',DATE '2026-08-31',
                '2026-08-31 21:01:10.517131','population-run','depsdev/v1/package-version',repeat('a',64),repeat('b',64),
                '{"dataset":"package-version"}','{"package":3,"version":3}','population-attempt');
            INSERT INTO etl_load_attempt(attempt_id,execution_id,status,phase,actual_counts,completed_at)
              VALUES ('population-attempt','population-execution','PUBLISHED','COMMIT','{"package":3,"version":3}',clock_timestamp());
            INSERT INTO etl_dataset_current(dataset,execution_id,snapshot_at,manifest_sha256,manifest)
              VALUES ('package-version','population-execution',DATE '2026-08-31',repeat('a',64),'{"dataset":"package-version"}');
            INSERT INTO etl_load_execution(execution_id,dataset,status,run_prefix,manifest_sha256,contract_sha256,
              input_metadata,expected_counts,active_attempt_id)
              VALUES ('reference-execution','snapshot-reference','PUBLISHED','snapshot/reference',repeat('c',64),repeat('d',64),
                '{"dataset":"snapshot-reference"}','{"snapshot":2}','reference-attempt');
            INSERT INTO etl_load_attempt(attempt_id,execution_id,status,phase,actual_counts,completed_at)
              VALUES ('reference-attempt','reference-execution','PUBLISHED','COMMIT','{"snapshot":2}',clock_timestamp());
            INSERT INTO etl_snapshot_reference(execution_id,snapshot_at,snapshot_timestamp,previous_snapshot_at)
              VALUES ('reference-execution',DATE '2026-08-24','2026-08-24 21:01:08.477988+00',NULL),
                     ('reference-execution',DATE '2026-08-31','2026-08-31 21:01:10.517131+00',DATE '2026-08-24');
            COMMIT;""")

    def metadata(self, *, manifest_hash="e" * 64, run_id="package-snapshot-test-v1", counts=3):
        input_manifest = {
            "population": {"manifest_sha256": "a" * 64, "run_id": "population-run"},
            "candidate": {"sha256": "c" * 64},
        }
        manifest = {
            "dataset": "package-snapshot", "input_manifest": input_manifest,
            "interval": {"previous_snapshot_at": "2026-08-24",
                          "previous_snapshot_timestamp": "2026-08-24T21:01:08.477988Z",
                          "snapshot_timestamp": "2026-08-31T21:01:10.517131Z"},
            "quality": {"downloads": {"COMPLETE": 1, "PARTIAL": 1, "UNAVAILABLE": 1}},
        }
        return {"dataset": "package-snapshot", "snapshot": "2026-08-31",
                "snapshot_timestamp": "2026-08-31T21:01:10.517131",
                "curated_run_id": run_id, "run_prefix": "depsdev/v1/package-snapshot/run-1",
                "manifest_sha256": manifest_hash, "manifest": manifest,
                "counts": {"package_snapshot": counts}}

    def files(self, *, values=None, identity=None):
        values = values or [(1, "2026-08-31", "10", "4", "2"),
                            (2, "2026-08-31", "0", "", "0"),
                            (3, "2026-08-31", "", "", "")]
        identity = identity or [(1, "alpha"), (2, "beta"), (3, "gamma")]
        root = Path(self.work.name)
        suffix = uuid.uuid4().hex
        snapshot = root / f"package_snapshot-{suffix}.copy.tsv"
        def copy_value(value):
            return "\\N" if value == "" else str(value)
        snapshot.write_text("".join("\t".join(copy_value(value) for value in row) + "\n" for row in values), encoding="utf-8", newline="")
        ident = root / f"package_identity-{suffix}.copy.tsv"
        ident.write_text("".join(f"{i}\t{name}\n" for i, name in identity), encoding="utf-8", newline="")
        return {"package_snapshot": [snapshot], "package_identity": [ident]}

    def load(self, execution_id="snapshot-load", *, attempt=None, metadata=None, files=None,
             contract="f" * 64, failpoint=None, before_commit=None):
        attempt = attempt or execution_id + "-attempt"
        metadata = metadata or self.metadata()
        with PackageSnapshotLoader(self.command + ["-d", self.database], Path(self.work.name)) as loader:
            loader.start(metadata, execution_id, contract, attempt)
            try:
                return loader.publish(files or self.files(), failpoint=failpoint, before_commit=before_commit)
            except BaseException as exc:
                loader.fail(exc)
                raise

    def test_publishes_partial_zero_and_independent_nulls(self):
        result = self.load()
        self.assertEqual(result["action"], "LOADED")
        self.assertEqual(self.sql("SELECT package_id||'|'||coalesce(downloads::text,'NULL')||'|'||coalesce(stars::text,'NULL')||'|'||coalesce(open_issues::text,'NULL') FROM package_snapshot ORDER BY package_id"),
                         "1|10|4|2\n2|0|NULL|0\n3|NULL|NULL|NULL")
        self.assertEqual(self.sql("SELECT status,actual_counts::text FROM etl_load_execution WHERE execution_id='snapshot-load'"),
                         'PUBLISHED|{"inserted": 3, "verified_rows": 3, "package_snapshot": 3}')

    def test_same_input_retry_compares_rows_and_preserves_first_counts(self):
        self.load()
        before = self.sql("SELECT actual_counts::text FROM etl_load_execution WHERE execution_id='snapshot-load'")
        result = self.load(attempt="snapshot-load-retry")
        self.assertEqual(result["action"], "REVERIFIED")
        self.assertEqual(self.sql("SELECT actual_counts::text FROM etl_load_execution WHERE execution_id='snapshot-load'"), before)
        self.assertEqual(self.sql("SELECT status FROM etl_load_attempt WHERE attempt_id='snapshot-load-retry'"), "REVERIFIED")

    def test_same_input_retry_accepts_changed_contract_and_preserves_publication_contract(self):
        self.load(contract="f" * 64)
        result = self.load(attempt="snapshot-load-new-contract", contract="e" * 64)
        self.assertEqual(result["action"], "REVERIFIED")
        self.assertEqual(
            self.sql("SELECT contract_sha256 FROM etl_load_execution WHERE execution_id='snapshot-load'"),
            "f" * 64,
        )
        self.assertEqual(
            self.sql("SELECT validation_contract_sha256 FROM etl_load_attempt "
                     "WHERE attempt_id='snapshot-load-new-contract'"),
            "e" * 64,
        )

    def test_failed_execution_rejects_changed_contract(self):
        with self.assertRaises(Exception):
            self.load("contract-guard", contract="f" * 64, failpoint="before_commit")
        with self.assertRaisesRegex(Exception, "different input or contract"):
            self.load("contract-guard", attempt="contract-guard-new", contract="e" * 64)

    def test_changed_validator_rejects_incompatible_service_schema(self):
        self.load(contract="f" * 64)
        self.sql("ALTER TABLE package_snapshot ALTER COLUMN stars TYPE bigint")
        with self.assertRaisesRegex(Exception, "service schema differs"):
            self.load(attempt="snapshot-load-wrong-schema", contract="e" * 64)
        self.assertEqual(self.sql("SELECT status||'|'||contract_sha256 FROM etl_load_execution "
                                  "WHERE execution_id='snapshot-load'"), "PUBLISHED|" + "f" * 64)
        self.assertEqual(self.sql("SELECT count(*) FROM package_snapshot"), "3")

    def test_retry_rejects_service_value_mutation(self):
        self.load()
        self.sql("UPDATE package_snapshot SET stars=999 WHERE package_id=1")
        with self.assertRaisesRegex(Exception, "service values differ"):
            self.load(attempt="snapshot-load-mutated")
        self.assertEqual(self.sql("SELECT status FROM etl_load_execution WHERE execution_id='snapshot-load'"), "PUBLISHED")

    def test_execution_identity_and_same_snapshot_input_conflicts_are_rejected(self):
        self.load()
        altered = self.metadata(manifest_hash="1" * 64)
        with self.assertRaisesRegex(ValueError, "different input or contract"):
            self.load(metadata=altered, attempt="conflicting-attempt")
        other = self.metadata(manifest_hash="2" * 64, run_id="other-run")
        with self.assertRaisesRegex(Exception, "different input"):
            self.load("other-execution", metadata=other, attempt="other-attempt")

    def test_existing_same_date_without_provenance_is_rejected(self):
        self.sql("INSERT INTO package_snapshot(package_id,snapshot_at,downloads) VALUES (1,DATE '2026-08-31',10)")
        with self.assertRaisesRegex(Exception, "provenance"):
            self.load("unprovenanced")

    def test_failpoints_rollback_rows_but_record_failed_attempt(self):
        for point in ("after_copy", "after_insert", "before_commit"):
            with self.subTest(point=point), self.assertRaises(Exception):
                self.load("failed-" + point, failpoint=point)
            self.assertEqual(self.sql("SELECT count(*) FROM package_snapshot"), "0")
            self.assertEqual(self.sql("SELECT status FROM etl_load_execution WHERE execution_id='failed-%s'" % point), "FAILED")
            self.assertEqual(self.sql("SELECT status FROM etl_load_attempt WHERE execution_id='failed-%s'" % point), "FAILED")

    def test_failed_execution_retries_successfully(self):
        with self.assertRaises(Exception):
            self.load("retryable", failpoint="before_commit")
        self.assertEqual(self.load("retryable", attempt="retryable-success")["status"], "PUBLISHED")

    def test_invalid_staging_rows_are_rejected(self):
        cases = [
            ("duplicate", self.files(values=[(1,"2026-08-31","1","1","1"),(1,"2026-08-31","1","1","1"),(2,"2026-08-31","0","0","0")]), "VALIDATE_STAGING"),
            ("unknown-id", self.files(values=[(1,"2026-08-31","1","1","1"),(2,"2026-08-31","0","0","0"),(9,"2026-08-31","1","1","1")]), "population"),
            ("negative", self.files(values=[(1,"2026-08-31","-1","1","1"),(2,"2026-08-31","0","0","0"),(3,"2026-08-31","1","1","1")]), "COPY"),
            ("wrong-date", self.files(values=[(1,"2026-08-30","1","1","1"),(2,"2026-08-30","0","0","0"),(3,"2026-08-30","1","1","1")]), "snapshot"),
            ("name-mismatch", self.files(identity=[(1,"wrong"),(2,"beta"),(3,"gamma")]), "ID/name"),
        ]
        for name, files, message in cases:
            with self.subTest(name=name), self.assertRaisesRegex(Exception, message):
                self.load("invalid-" + name, files=files)
            self.assertEqual(self.sql("SELECT count(*) FROM package_snapshot"), "0")

    def test_missing_lineage_is_rejected_without_service_rows(self):
        self.sql("DELETE FROM etl_snapshot_reference WHERE snapshot_at=DATE '2026-08-31'")
        with self.assertRaisesRegex(Exception, "snapshot-reference lineage"):
            self.load("missing-lineage")
        self.assertEqual(self.sql("SELECT count(*) FROM package_snapshot"), "0")

    def test_before_commit_callback_failure_rolls_back(self):
        def fail_callback():
            raise RuntimeError("input changed")
        with self.assertRaisesRegex(RuntimeError, "input changed"):
            self.load("callback-failure", before_commit=fail_callback)
        self.assertEqual(self.sql("SELECT count(*) FROM package_snapshot"), "0")
        self.assertEqual(self.sql("SELECT status FROM etl_load_attempt WHERE attempt_id='callback-failure-attempt'"), "FAILED")

    def test_other_snapshot_rows_are_preserved(self):
        self.sql("INSERT INTO package_snapshot(package_id,snapshot_at,downloads) VALUES (1,DATE '2026-08-24',7)")
        self.load()
        self.assertEqual(self.sql("SELECT count(*) FROM package_snapshot"), "4")
        self.assertEqual(self.sql("SELECT downloads FROM package_snapshot WHERE package_id=1 AND snapshot_at=DATE '2026-08-24'"), "7")

    def test_advisory_lock_rejects_writer(self):
        first = PackageSnapshotLoader(self.command + ["-d", self.database], Path(self.work.name))
        first.__enter__()
        try:
            first.start(self.metadata(), "lock-a", "f" * 64, "lock-a-attempt")
            with PackageSnapshotLoader(self.command + ["-d", self.database], Path(self.work.name)) as second:
                with self.assertRaisesRegex(RuntimeError, "another package-snapshot load"):
                    second.start(self.metadata(), "lock-b", "f" * 64, "lock-b-attempt")
        finally:
            first.__exit__(None, None, None)

    def test_reference_writer_can_insert_snapshot_while_loader_waits_for_reference_lock(self):
        """The loader's package -> reference -> snapshot lock order must not block a reference writer."""
        from pipeline.postgresql.postgres import PgLoader

        reference = PgLoader(self.command + ["-d", self.database], Path(self.work.name))
        reference.__enter__()
        try:
            reference._send("BEGIN; LOCK TABLE public.etl_snapshot_reference IN SHARE ROW EXCLUSIVE MODE;")
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(self.load, "lock-order")
                waiting = False
                for _ in range(100):
                    activity = self.sql(
                        "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() "
                        "AND wait_event_type='Lock' AND query LIKE '%etl_snapshot_reference%'")
                    if activity == "1":
                        waiting = True
                        break
                    time.sleep(0.05)
                self.assertTrue(waiting, "package loader did not wait on the reference lock")
                reference._send("SET LOCAL statement_timeout='2s'; "
                                "INSERT INTO public.snapshot(snapshot_at) VALUES (DATE '2026-09-01');")
                reference._send("COMMIT;")
                self.assertEqual(future.result(timeout=60)["status"], "PUBLISHED")
            self.assertEqual(self.sql("SELECT snapshot_at FROM snapshot WHERE snapshot_at=DATE '2026-09-01'"), "2026-09-01")
        finally:
            reference.__exit__(None, None, None)


if __name__ == "__main__":
    unittest.main()
