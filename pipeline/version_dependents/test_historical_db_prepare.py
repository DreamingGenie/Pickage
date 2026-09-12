"""Zero restoration and DB identity gates without rebuilding historical inputs."""
import unittest

import duckdb

from .historical_db_prepare import restore_counts, validate_catalog, validate_scope


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.con = duckdb.connect()
        self.addCleanup(self.con.close)
        self.con.execute("CREATE TABLE pilot_names(package_id INT,name VARCHAR); INSERT INTO pilot_names VALUES(1,'alpha')")
        self.con.execute("CREATE TABLE pilot_targets(package_id INT,version VARCHAR,birth_index INT);"
                         "INSERT INTO pilot_targets VALUES(1,'1.0.0',0),(1,'2.0.0',1),(1,'3.0.0',2)")
        self.con.execute('CREATE TABLE counts(package_id INT,version VARCHAR,snapshot_at DATE,'
                         'snapshot_timestamp TIMESTAMPTZ,dependents_count BIGINT)')
        self.con.execute("INSERT INTO counts VALUES(1,'1.0.0','2026-08-30','2026-08-30T12:00:00Z',3),"
                         "(1,'2.0.0','2026-08-31','2026-08-31T12:00:00Z',5),"
                         "(2,'other','2026-08-31','2026-08-31T12:00:00Z',999)")
        self.calendar = [dict(snapshot_at=d, snapshot_timestamp=d + 'T12:00:00Z')
                         for d in ('2026-08-30', '2026-08-31', '2026-09-01')]

    def test_zero_is_restored_only_for_eligible_versions(self):
        actual = restore_counts(self.con, self.calendar, ['2026-08-30', '2026-08-31'])
        self.assertEqual(actual, [
            dict(package_id=1, version='1.0.0', snapshot_at='2026-08-30', dependents_count=3),
            dict(package_id=1, version='1.0.0', snapshot_at='2026-08-31', dependents_count=0),
            dict(package_id=1, version='2.0.0', snapshot_at='2026-08-31', dependents_count=5)])

    def test_future_positive_target_is_rejected(self):
        self.con.execute("INSERT INTO counts VALUES(1,'3.0.0','2026-08-31','2026-08-31T12:00:00Z',2)")
        with self.assertRaisesRegex(ValueError, 'eligible'):
            restore_counts(self.con, self.calendar, ['2026-08-31'])

    def test_duplicate_positive_is_rejected(self):
        self.con.execute("INSERT INTO counts SELECT * FROM counts WHERE package_id=1 AND version='2.0.0'")
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            restore_counts(self.con, self.calendar, ['2026-08-31'])

    def test_wrong_observation_timestamp_is_rejected(self):
        self.con.execute("UPDATE counts SET snapshot_timestamp='2026-08-31T00:00:00Z' WHERE version='2.0.0'")
        with self.assertRaisesRegex(ValueError, 'valid eligible'):
            restore_counts(self.con, self.calendar, ['2026-08-31'])

    def test_snapshot_outside_calendar_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'calendar'):
            restore_counts(self.con, self.calendar, ['2020-01-01'])

    def test_explicit_bounded_scope(self):
        self.assertEqual(validate_scope(['beta', 'alpha'], ['2026-08-31']), (['alpha', 'beta'], ['2026-08-31']))
        for names, dates in [([], ['2026-08-31']), (['a', 'a'], ['2026-08-31']),
                             (['a'], ['2026-02-30']), (['a'], ['20260831']),
                             ([str(i) for i in range(33)], ['2026-08-31'])]:
            with self.subTest(names=names, dates=dates), self.assertRaises(ValueError):
                validate_scope(names, dates)

    def test_db_key_mismatch_and_missing_keys_are_rejected(self):
        identities = [dict(package_id=1, name='alpha')]
        counts = [dict(package_id=1, version='1.0.0', snapshot_at='2026-08-31', dependents_count=0)]
        catalog = dict(packages=identities, versions=[dict(package_id=1, version='1.0.0')],
                       snapshots=[dict(snapshot_at='2026-08-31')])
        validate_catalog(identities, counts, catalog)
        for bad in [dict(catalog, packages=[dict(package_id=2, name='alpha')]),
                    dict(catalog, versions=[]), dict(catalog, snapshots=[])]:
            with self.assertRaises(ValueError):
                validate_catalog(identities, counts, bad)


if __name__ == '__main__':
    unittest.main()
