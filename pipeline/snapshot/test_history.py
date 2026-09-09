"""PostgreSQL integration tests for snapshot-reference execution history."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
import uuid

from .build import snapshot_sql
from .postgres import SnapshotLoader
from .policy import build_calendar


ROOT = Path(__file__).resolve().parents[2]
CONTAINER = os.environ.get("PICKAGE_SNAPSHOT_TEST_CONTAINER")


@unittest.skipUnless(CONTAINER, "PICKAGE_SNAPSHOT_TEST_CONTAINER is required")
class SnapshotHistoryTests(unittest.TestCase):
    def setUp(self):
        self.database = "pickage_269_history_test_" + uuid.uuid4().hex
        self.command = ["docker", "exec", "-i", CONTAINER, "psql", "-U", "postgres"]
        self.sql(f'CREATE DATABASE "{self.database}";', database="postgres")
        self.addCleanup(self.drop_database)
        temporary = tempfile.TemporaryDirectory()
        self.work_dir = Path(temporary.name)
        self.addCleanup(temporary.cleanup)
        migrations = ROOT / "backend/src/main/resources/db/migration"
        for name in ("V1__init.sql", "V2__add_curated_load_execution.sql", "V3__add_snapshot_reference_execution.sql"):
            self.sql((migrations / name).read_text(encoding="utf-8"))
        self.calendar = build_calendar(["2026-08-24T21:00:00Z", "2026-08-31T21:00:00Z"])
        self.metadata = self.meta(self.calendar)
        self.seed_existing()

    def sql(self, statement, *, database=None):
        command = self.command + ["-d", database or self.database, "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1"]
        result = subprocess.run(command, input=statement.encode("utf-8"), capture_output=True, timeout=45)
        if result.returncode:
            raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
        return result.stdout.decode("utf-8").strip()

    def drop_database(self):
        if not re.fullmatch(r"pickage_269_history_test_[0-9a-f]{32}", self.database):
            raise ValueError("refusing to drop database outside test namespace")
        self.sql(f'DROP DATABASE "{self.database}";', database="postgres")

    @staticmethod
    def meta(calendar):
        manifest = {"candidate": {"calendar": calendar}}
        return {"dataset": "snapshot-reference", "manifest_sha256": hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest(),
                "run_prefix": "snapshot/history-test", "manifest": manifest,
                "counts": {"snapshot": len(calendar)}}

    def seed_existing(self):
        self.sql("""BEGIN;
            INSERT INTO snapshot(snapshot_at) VALUES (DATE '2026-08-01');
            INSERT INTO package(package_id,name,repo_url) VALUES (7,'kept-package','https://old.example');
            INSERT INTO version(version,package_id,ordinal,dependency) VALUES ('1.0.0',7,0,'{}');
            INSERT INTO package_version_snapshot(package_id,version,snapshot_at) VALUES (7,'1.0.0',DATE '2026-08-01');
            INSERT INTO etl_load_execution(execution_id,dataset,status,snapshot_at,snapshot_timestamp,curated_run_id,run_prefix,manifest_sha256,contract_sha256,input_metadata,expected_counts,active_attempt_id)
              VALUES ('seed-execution','package-version','PUBLISHED',DATE '2026-08-01','2026-08-01 00:00:00','seed-run','seed',repeat('a',64),repeat('b',64),'{}','{"package":1,"version":1}','seed-attempt');
            INSERT INTO etl_load_attempt(attempt_id,execution_id,status,phase,actual_counts,completed_at)
              VALUES ('seed-attempt','seed-execution','PUBLISHED','COMMIT','{"package":1,"version":1}',clock_timestamp());
            INSERT INTO etl_dataset_current(dataset,execution_id,snapshot_at,manifest_sha256,manifest)
              VALUES ('package-version','seed-execution',DATE '2026-08-01',repeat('a',64),'{}');
            COMMIT;""")

    def load(self, execution_id, calendar=None, *, contract="c" * 64, attempt=None, failpoint=None):
        calendar = calendar or self.calendar
        attempt = attempt or execution_id + "-attempt"
        metadata = self.meta(calendar)
        with SnapshotLoader(self.command + ["-d", self.database], self.work_dir) as loader:
            loader.start(metadata, execution_id, contract, attempt)
            try:
                return loader.publish(calendar, failpoint=failpoint)
            except BaseException as exc:
                loader.fail(exc)
                raise

    def rows(self, query):
        return self.sql(query).splitlines()

    def test_preserves_existing_dates_service_rows_and_current(self):
        self.load("history-a")
        self.assertEqual(self.rows("SELECT snapshot_at FROM snapshot ORDER BY snapshot_at"), ["2026-08-01", "2026-08-24", "2026-08-31"])
        self.assertEqual(self.sql("SELECT name || '|' || repo_url FROM package WHERE package_id=7"), "kept-package|https://old.example")
        self.assertEqual(self.sql("SELECT execution_id FROM etl_dataset_current WHERE dataset='package-version'"), "seed-execution")
        self.assertEqual(self.sql("SELECT count(*) FROM version WHERE package_id=7 AND version='1.0.0' AND dependency::text='{}'"), '1')
        self.assertEqual(self.sql("SELECT count(*) FROM package_version_snapshot"), '1')
        self.assertEqual(self.sql("SELECT status||'|'||contract_sha256 FROM etl_load_execution WHERE execution_id='seed-execution'"), 'PUBLISHED|'+'b'*64)

    def test_publishes_exact_timestamp_previous_and_membership(self):
        self.load("history-a")
        self.assertEqual(self.rows("SELECT snapshot_at || '|' || snapshot_timestamp AT TIME ZONE 'UTC' || '|' || coalesce(previous_snapshot_at::text,'NULL') FROM etl_snapshot_reference WHERE execution_id='history-a' ORDER BY snapshot_at"), ["2026-08-24|2026-08-24 21:00:00|NULL", "2026-08-31|2026-08-31 21:00:00|2026-08-24"])

    def test_same_id_rerun_is_reverified_and_keeps_original_counts(self):
        self.load("history-a")
        before = self.sql("SELECT actual_counts::text FROM etl_load_execution WHERE execution_id='history-a'")
        result = self.load("history-a", attempt="history-a-retry")
        self.assertEqual(result["action"], "REVERIFIED")
        self.assertEqual(result['counts']['inserted'], 0)
        self.assertEqual(self.sql("SELECT actual_counts::text FROM etl_load_execution WHERE execution_id='history-a'"), before)
        self.assertEqual(self.sql("SELECT status FROM etl_load_attempt WHERE attempt_id='history-a-retry'"), "REVERIFIED")

    def test_different_id_same_input_creates_its_own_membership(self):
        self.load("history-a")
        self.assertEqual(self.load("history-b")['action'], 'LINKED_EXISTING')
        self.assertEqual(self.sql("SELECT count(*) FROM etl_snapshot_reference WHERE execution_id IN ('history-a','history-b')"), "4")

    def test_failpoints_rollback_and_record_failed(self):
        for failpoint in ("after_dates", "after_references", "before_commit"):
            with self.subTest(failpoint=failpoint), self.assertRaises(Exception):
                self.load("failed-" + failpoint, failpoint=failpoint)
            self.assertEqual(self.sql("SELECT count(*) FROM etl_snapshot_reference WHERE execution_id LIKE 'failed-%'"), "0")
            self.assertEqual(self.sql("SELECT status FROM etl_load_execution WHERE execution_id='failed-%s'" % failpoint), "FAILED")
            self.assertEqual(self.rows('SELECT snapshot_at FROM snapshot ORDER BY snapshot_at'), ['2026-08-01'])
            self.assertEqual(self.sql("SELECT status FROM etl_load_attempt WHERE execution_id='failed-%s'" % failpoint), 'FAILED')

    def test_failed_execution_can_retry_same_id(self):
        with self.assertRaises(Exception):
            self.load("retry-me", failpoint="before_commit")
        self.assertEqual(self.load("retry-me", attempt="retry-me-success")["status"], "PUBLISHED")

    def test_same_id_different_input_is_rejected(self):
        self.load("history-a")
        altered = build_calendar(["2026-08-24T22:00:00Z", "2026-08-31T21:00:00Z"])
        with self.assertRaisesRegex(ValueError, "different input"):
            self.load("history-a", altered)

    def test_corrupt_published_child_fails_without_silent_repair(self):
        self.load("history-a")
        before = self.sql("SELECT actual_counts::text FROM etl_load_execution WHERE execution_id='history-a'")
        self.sql("DELETE FROM etl_snapshot_reference WHERE execution_id='history-a' AND snapshot_at=DATE '2026-08-31'")
        with self.assertRaises(Exception):
            self.load("history-a", attempt="history-a-reverify")
        self.assertEqual(self.sql("SELECT status FROM etl_load_execution WHERE execution_id='history-a'"), "PUBLISHED")
        self.assertEqual(self.sql("SELECT count(*) FROM etl_snapshot_reference WHERE execution_id='history-a'"), "1")
        self.assertEqual(self.sql("SELECT actual_counts::text FROM etl_load_execution WHERE execution_id='history-a'"), before)
        self.assertEqual(self.sql("SELECT a.status FROM etl_load_execution e JOIN etl_load_attempt a ON a.attempt_id=e.active_attempt_id WHERE e.execution_id='history-a'"), 'FAILED')

    def test_same_date_different_instant_is_rejected(self):
        self.load("history-a")
        altered = build_calendar(["2026-08-24T22:00:00Z", "2026-08-31T21:00:00Z"])
        with self.assertRaises(Exception):
            self.load("history-b", altered)
        self.assertEqual(self.sql("SELECT count(*) FROM etl_snapshot_reference WHERE execution_id='history-b'"), "0")

    def test_dedicated_advisory_lock_rejects_concurrent_loader(self):
        first = SnapshotLoader(self.command + ["-d", self.database], self.work_dir)
        first.__enter__()
        try:
            first.start(self.metadata, "lock-a", "c" * 64, "lock-a-attempt")
            with SnapshotLoader(self.command + ["-d", self.database], self.work_dir) as second:
                with self.assertRaisesRegex(RuntimeError, "another snapshot-reference load"):
                    second.start(self.metadata, "lock-b", "c" * 64, "lock-b-attempt")
        finally:
            first.__exit__(None, None, None)

    def test_v3_constraints_enforce_reference_only_shape_and_previous_fk(self):
        with self.assertRaisesRegex(RuntimeError, 'ck_etl_execution_snapshot_scope'):
            self.sql("INSERT INTO etl_load_execution(execution_id,dataset,status,run_prefix,manifest_sha256,contract_sha256,input_metadata,expected_counts,active_attempt_id) VALUES ('bad','package-version','PREPARING','x',repeat('a',64),repeat('b',64),'{}','{}','x')")
        self.load('history-a')
        self.sql("INSERT INTO snapshot(snapshot_at) VALUES(DATE '2026-09-01')")
        with self.assertRaisesRegex(RuntimeError, 'previous_snapshot_at'):
            self.sql("INSERT INTO etl_snapshot_reference(execution_id,snapshot_at,snapshot_timestamp,previous_snapshot_at) VALUES ('history-a',DATE '2026-09-01','2026-09-01 21:00:00+00',DATE '2026-08-30')")
        with self.assertRaisesRegex(RuntimeError, 'foreign key'):
            self.sql("INSERT INTO etl_snapshot_reference(execution_id,snapshot_at,snapshot_timestamp,previous_snapshot_at) VALUES ('history-a',DATE '2026-10-01','2026-10-01 21:00:00+00',DATE '2026-08-31')")

    def test_reference_table_write_lock_blocks_external_writer_race(self):
        with SnapshotLoader(self.command + ['-d', self.database], self.work_dir) as external:
            external._send('BEGIN; LOCK TABLE public.etl_snapshot_reference IN ROW EXCLUSIVE MODE;')
            with self.assertRaisesRegex(RuntimeError, 'lock timeout'):
                self.load('blocked')
        self.assertEqual(self.sql("SELECT status FROM etl_load_execution WHERE execution_id='blocked'"), 'FAILED')

    def test_reverification_records_new_contract_without_rewriting_original(self):
        self.load('history-a')
        self.load('history-a', attempt='new-contract', contract='d'*64)
        self.assertEqual(self.sql("SELECT contract_sha256 FROM etl_load_execution WHERE execution_id='history-a'"), 'c'*64)
        self.assertEqual(self.sql("SELECT validation_contract_sha256 FROM etl_load_attempt WHERE attempt_id='new-contract'"), 'd'*64)


if __name__ == "__main__":
    unittest.main()
