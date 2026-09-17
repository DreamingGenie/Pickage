import copy
import os
import unittest
import uuid

from pipeline.preprocessing.requirements_resolution.policy import sha256
from pipeline.postgresql.version_dependents.tests import test_historical_db_keys as key_tests
from pipeline.postgresql.version_dependents.tests import test_historical_db_publish as legacy_tests
from pipeline.postgresql.version_dependents.historical_db_fast_publish import FastCountLoader, target_schema


class FastPublisherUnitTests(unittest.TestCase):
    def test_target_cannot_be_public_or_sql(self):
        for value in ('public', 'vd193_reload_x;drop table x', 'vd193_reload_', 'vd193_bench_x'):
            with self.assertRaises(ValueError):
                target_schema(value)


@unittest.skipUnless(os.environ.get('PICKAGE_TEST_CONTAINER'), 'PICKAGE_TEST_CONTAINER required')
class FastPublisherIntegrationTests(key_tests.HistoricalDbKeyValidationIntegrationTests):
    def setUp(self):
        super().setUp()
        self._sql('ALTER TABLE package_version_snapshot ALTER COLUMN dependents_count SET DEFAULT 0; ALTER TABLE package_version_snapshot ALTER COLUMN snapshot_at DROP DEFAULT;')
        self.schema = 'vd193_reload_'+uuid.uuid4().hex
        self.counts = self.root/'counts.tsv'
        self.counts.write_bytes(b'1\t1.0.0\t2026-08-31\t0\n1\t2.0.0\t2026-08-31\t4\n2\t1.0.0\t2026-08-31\t2\n')
        self.metadata = legacy_tests.HistoricalCountLoaderIntegrationTests._publisher_metadata(self)
        self.files = {'identities':self.identity, 'counts':self.counts}
        self.plan = {'schema':self.schema, 'generation':{'fixture':'c'*64},
                     'dates':['2026-08-30','2026-08-31'], 'rows_by_date':{'2026-08-30':3,'2026-08-31':3},
                     'expected_rows':6, 'expected_dates':2}

    def loader(self, plan=None):
        return FastCountLoader(self.command, self.root, self.schema, plan or self.plan)

    def publish(self, failpoint=None, callback=None, execution='fast-1'):
        with self.loader() as db:
            db.initialize()
            return db.publish_day(self.metadata,self.files,execution,callback or (lambda:None),failpoint)

    def public_state(self):
        return self._sql("SELECT json_agg(row_to_json(e) ORDER BY execution_id) FROM public.etl_load_execution e;") + self._sql('SELECT count(*) FROM public.package_version_snapshot;')

    def test_readonly_check_and_atomic_zero_resume(self):
        before = self.public_state()
        with self.loader() as db:
            self.assertFalse(db.inspect_target()['exists'])
        self.assertEqual(self._sql(f"SELECT count(*) FROM pg_namespace WHERE nspname='{self.schema}';"),'0')
        self.assertEqual(self.publish()['action'],'LOADED')
        self.assertEqual(self.publish()['inserted_rows'],0)
        with self.loader() as db:
            report = db.inspect_target()
        self.assertEqual((report['completed_dates'],report['completed_rows']),(1,3))
        self.assertEqual(before,self.public_state())
        self.assertEqual(self._sql(f"SELECT dependents_count FROM {self.schema}.package_version_snapshot WHERE package_id=1 AND version='1.0.0';"),'0')

    def test_failures_rollback_entire_day_and_retry(self):
        for failpoint in ('after_copy','after_attach','before_commit'):
            with self.subTest(failpoint=failpoint):
                with self.assertRaisesRegex(RuntimeError,'injected'):
                    self.publish(failpoint)
                self.assertEqual(self._sql(f'SELECT count(*) FROM {self.schema}.package_version_snapshot;'),'0')
                self.assertEqual(self._sql(f"SELECT status FROM {self.schema}.etl_load_execution WHERE execution_id='fast-1';"),'FAILED')
        self.assertEqual(self.publish()['action'],'LOADED')

    def test_lost_commit_response_stays_published(self):
        with self.assertRaisesRegex(RuntimeError,'lost_commit_response'):
            self.publish('after_commit')
        self.assertEqual(self._sql(f"SELECT status FROM {self.schema}.etl_load_execution WHERE execution_id='fast-1';"),'PUBLISHED')
        self.assertEqual(self.publish()['action'],'REVERIFIED')

    def test_changed_saved_values_and_missing_zero_are_rejected(self):
        self.publish()
        self._sql(f"UPDATE {self.schema}.d20260831 SET dependents_count=99 WHERE package_id=1 AND version='1.0.0';")
        with self.assertRaisesRegex((RuntimeError, ValueError),'Stored values|Stored row count'):
            self.publish()
        self._sql(f"DELETE FROM {self.schema}.d20260831 WHERE package_id=1 AND version='1.0.0';")
        with self.assertRaisesRegex((RuntimeError, ValueError),'Stored values|Stored row count'):
            self.publish()

    def test_before_commit_file_change_rolls_back(self):
        def mutate():
            self.counts.write_bytes(self.counts.read_bytes().replace(b'\t0\n',b'\t9\n'))
        with self.assertRaisesRegex(ValueError,'does not match manifest'):
            self.publish(callback=mutate)
        self.assertEqual(self._sql(f'SELECT count(*) FROM {self.schema}.package_version_snapshot;'),'0')

    def test_plan_change_and_orphan_are_rejected(self):
        self.publish()
        plan = copy.deepcopy(self.plan)
        plan['generation']['fixture'] = 'd'*64
        with self.loader(plan) as db:
            with self.assertRaisesRegex(ValueError,'plan/code/input'):
                db.initialize()
        self._sql(f'DELETE FROM {self.schema}.reload_partition;')
        with self.loader() as db:
            with self.assertRaisesRegex(RuntimeError,'receipt coverage'):
                db.inspect_target()

    def test_global_lock_blocks_competing_loader(self):
        with self.loader():
            with self.assertRaisesRegex(RuntimeError,'load is active'):
                with self.loader():
                    pass

    def test_old_date_preserves_newer_current_and_sibling(self):
        self.publish()
        self.counts.write_bytes(self.counts.read_bytes().replace(b'2026-08-31',b'2026-08-30'))
        self.metadata = legacy_tests.HistoricalCountLoaderIntegrationTests._publisher_metadata(self,'2026-08-30')
        self.publish(execution='fast-old')
        self.assertEqual(self._sql(f'SELECT snapshot_at FROM {self.schema}.etl_dataset_current;'),'2026-08-31')
        with self.loader() as db:
            self.assertEqual(db.inspect_target()['completed_rows'],6)

    def test_constraints_reject_invalid_data(self):
        self.publish()
        for sql in (
            f"INSERT INTO {self.schema}.package_version_snapshot VALUES(1,'missing','2026-08-31',1);",
            f"INSERT INTO {self.schema}.package_version_snapshot VALUES(1,'1.0.0','2026-08-31',1);",
            f"UPDATE {self.schema}.d20260831 SET dependents_count=-1;",
            f"UPDATE {self.schema}.d20260831 SET dependents_count=NULL;",
            f"UPDATE {self.schema}.d20260831 SET snapshot_at='2026-08-30';",
        ):
            with self.assertRaises(RuntimeError):
                self._sql(sql)

    def test_dropped_foreign_key_blocks_readiness(self):
        self.publish()
        self._sql(f'ALTER TABLE {self.schema}.package_version_snapshot DROP CONSTRAINT version_fk;')
        with self.loader() as db:
            with self.assertRaisesRegex(ValueError,'constraints changed'):
                db.inspect_target()

    def test_deleted_current_pointer_blocks_readiness(self):
        self.publish()
        self._sql(f'DELETE FROM {self.schema}.etl_dataset_current;')
        with self.loader() as db:
            with self.assertRaisesRegex(ValueError,'Current pointer'):
                db.inspect_target()


if __name__ == '__main__':
    unittest.main()
