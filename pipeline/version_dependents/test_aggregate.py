from datetime import date, datetime, timedelta, timezone
import unittest

import duckdb

from .aggregate import aggregate


SNAPSHOT = date(2026, 8, 31)
STAMP = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)


def setup(edges, sources, targets, *, source_type="INTEGER", target_type="INTEGER"):
    con = duckdb.connect()
    con.execute(f"CREATE TABLE requirements_edges(source_package_id {source_type}, source_version VARCHAR, target_package_id {target_type}, target_version VARCHAR, snapshot_at DATE, snapshot_timestamp TIMESTAMPTZ)")
    con.execute(f"CREATE TABLE approved_sources(package_id {source_type}, version VARCHAR, published_at TIMESTAMPTZ, snapshot_at DATE, snapshot_timestamp TIMESTAMPTZ)")
    con.execute(f"CREATE TABLE approved_targets(package_id {target_type}, version VARCHAR, published_at TIMESTAMPTZ, snapshot_at DATE, snapshot_timestamp TIMESTAMPTZ)")
    if edges:
        con.executemany("INSERT INTO requirements_edges VALUES (?, ?, ?, ?, ?, ?)", [(*row, SNAPSHOT, STAMP) for row in edges])
    if sources:
        con.executemany("INSERT INTO approved_sources VALUES (?, ?, ?, ?, ?)", [(*row, SNAPSHOT, STAMP) for row in sources])
    if targets:
        con.executemany("INSERT INTO approved_targets VALUES (?, ?, ?, ?, ?)", [(*row, SNAPSHOT, STAMP) for row in targets])
    return con


class DirectDependentsTests(unittest.TestCase):
    def make(self, *args, **kwargs):
        con = setup(*args, **kwargs)
        self.addCleanup(con.close)
        return con

    def test_duplicate_and_multiple_sources_count(self):
        con = self.make([(1,"1.0",10,"2.0"),(1,"1.0",10,"2.0"),(1,"1.1",10,"2.0"),(2,"1.0",10,"2.0")], [(1,"1.0",date(2020,1,1)),(1,"1.1",date(2020,1,1)),(2,"1.0",date(2020,1,1))], [(10,"2.0",date(2020,1,1))])
        self.assertEqual(aggregate(con, expected_snapshot_at=SNAPSHOT, snapshot_timestamp=STAMP, resolution_status="COMPLETE", ready_for_dependents=True)["total_direct_dependents"], 3)
        self.assertEqual(con.execute("SELECT dependents_count FROM version_dependents").fetchone()[0], 3)

    def test_target_versions_are_separate_and_chain_is_direct_only(self):
        con = self.make([(1,"1",10,"1"),(10,"1",20,"1")], [(1,"1",date(2020,1,1)),(10,"1",date(2020,1,1))], [(10,"1",date(2020,1,1)),(20,"1",date(2020,1,1)),(20,"2",date(2020,1,1))])
        aggregate(con, expected_snapshot_at=SNAPSHOT, snapshot_timestamp=STAMP, resolution_status="COMPLETE", ready_for_dependents=True)
        self.assertEqual(con.execute("SELECT package_id,version,dependents_count FROM version_dependents ORDER BY package_id,version").fetchall(), [(10,"1",1),(20,"1",1),(20,"2",0)])

    def test_empty_edges_still_emit_zero_targets(self):
        con = self.make([], [(1,"1",date(2020,1,1))], [(10,"1",date(2020,1,1))])
        aggregate(con, expected_snapshot_at=SNAPSHOT, snapshot_timestamp=STAMP, resolution_status="COMPLETE", ready_for_dependents=True)
        self.assertEqual(con.execute("SELECT dependents_count FROM version_dependents").fetchone()[0], 0)
        self.assertEqual(con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name='_version_dependents'").fetchone()[0], 0)

    def test_compound_keys_are_not_concatenated(self):
        con = self.make([(1,"23",10,"1"),(12,"3",10,"1")], [(1,"23",date(2020,1,1)),(12,"3",date(2020,1,1))], [(10,"1",date(2020,1,1))])
        aggregate(con, expected_snapshot_at=SNAPSHOT, snapshot_timestamp=STAMP, resolution_status="COMPLETE", ready_for_dependents=True)
        self.assertEqual(con.execute("SELECT dependents_count FROM version_dependents").fetchone()[0], 2)

    def test_guard_rejection_leaves_no_result(self):
        con = self.make([], [(1,"1",date(2020,1,1))], [(10,"1",date(2020,1,1))])
        for status, ready in (("PARTIAL", True), ("COMPLETE", False), ("COMPLETE", 1)):
            with self.assertRaises(ValueError):
                aggregate(con, expected_snapshot_at=SNAPSHOT, snapshot_timestamp=STAMP, resolution_status=status, ready_for_dependents=ready)
            self.assertEqual(con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name='version_dependents'").fetchone()[0], 0)

    def test_malformed_population_and_orphan_rejected(self):
        con = self.make([(1,"1",99,"1")], [(1,"1",date(2020,1,1))], [(10,"1",date(2020,1,1))])
        with self.assertRaises(ValueError):
            aggregate(con, expected_snapshot_at=SNAPSHOT, snapshot_timestamp=STAMP, resolution_status="COMPLETE", ready_for_dependents=True)
        con.close()

    def test_orphan_source_and_invalid_identity_rejected(self):
        con = self.make([(99,"1",10,"1")], [(1,"1",date(2020,1,1))], [(10,"1",date(2020,1,1))])
        with self.assertRaises(ValueError):
            aggregate(con, expected_snapshot_at=SNAPSHOT, snapshot_timestamp=STAMP, resolution_status="COMPLETE", ready_for_dependents=True)
        con.close()
        con = self.make([], [(2_147_483_648,"1",date(2020,1,1))], [(10,"1",date(2020,1,1))], source_type="BIGINT")
        with self.assertRaises(ValueError):
            aggregate(con, expected_snapshot_at=SNAPSHOT, snapshot_timestamp=STAMP, resolution_status="COMPLETE", ready_for_dependents=True)

    def test_empty_population_and_bad_version_rejected(self):
        con = self.make([], [], [(10,"1",date(2020,1,1))])
        with self.assertRaises(ValueError):
            aggregate(con, expected_snapshot_at=SNAPSHOT, snapshot_timestamp=STAMP, resolution_status="COMPLETE", ready_for_dependents=True)
        con.close()
        con = self.make([], [(1,"1",date(2020,1,1))], [])
        with self.assertRaises(ValueError):
            aggregate(con, expected_snapshot_at=SNAPSHOT, snapshot_timestamp=STAMP, resolution_status="COMPLETE", ready_for_dependents=True)
        con.close()
        con = self.make([], [(1,"",date(2020,1,1))], [(10,"1",date(2020,1,1))])
        with self.assertRaises(ValueError):
            aggregate(con, expected_snapshot_at=SNAPSHOT, snapshot_timestamp=STAMP, resolution_status="COMPLETE", ready_for_dependents=True)

    def test_wrong_microsecond_timestamp_rejected(self):
        con = self.make([], [(1,"1",date(2020,1,1))], [(10,"1",date(2020,1,1))])
        with self.assertRaises(ValueError):
            aggregate(con, expected_snapshot_at=SNAPSHOT, snapshot_timestamp=STAMP.replace(microsecond=1), resolution_status="COMPLETE", ready_for_dependents=True)

    def test_publication_exact_timestamp_is_allowed_but_later_is_rejected(self):
        con = self.make([], [(1,"1",STAMP)], [(10,"1",STAMP)])
        aggregate(con, expected_snapshot_at=SNAPSHOT, snapshot_timestamp=STAMP, resolution_status="COMPLETE", ready_for_dependents=True)
        con.close()
        con = self.make([], [(1,"1",STAMP + timedelta(microseconds=1))], [(10,"1",STAMP)])
        with self.assertRaises(ValueError):
            aggregate(con, expected_snapshot_at=SNAPSHOT, snapshot_timestamp=STAMP, resolution_status="COMPLETE", ready_for_dependents=True)

    def test_non_utc_equivalent_timestamp_is_normalized(self):
        con = self.make([], [(1,"1",STAMP)], [(10,"1",STAMP)])
        aggregate(con, expected_snapshot_at=SNAPSHOT, snapshot_timestamp=datetime(2026, 8, 31, 21, 0, tzinfo=timezone(timedelta(hours=9))), resolution_status="COMPLETE", ready_for_dependents=True)

    def test_mismatched_snapshot_date_and_timestamp_rejected(self):
        con = self.make([], [(1,"1",STAMP)], [(10,"1",STAMP)])
        with self.assertRaises(ValueError):
            aggregate(con, expected_snapshot_at=date(2026, 9, 1), snapshot_timestamp=STAMP, resolution_status="COMPLETE", ready_for_dependents=True)
        with self.assertRaises(ValueError):
            aggregate(con, expected_snapshot_at=SNAPSHOT, snapshot_timestamp=datetime(2026, 9, 1, tzinfo=timezone.utc), resolution_status="COMPLETE", ready_for_dependents=True)

    def test_type_mismatch_rejected(self):
        con = self.make([], [(1,"1",STAMP)], [(10,"1",STAMP)], source_type="VARCHAR")
        with self.assertRaises(ValueError):
            aggregate(con, expected_snapshot_at=SNAPSHOT, snapshot_timestamp=STAMP, resolution_status="COMPLETE", ready_for_dependents=True)

    def test_invalid_version_forms_rejected_in_both_populations(self):
        for value in ("   ", "\t", "\n", None, "x\x00y", "x" * 101):
            con = self.make([], [(1, value, STAMP)], [(10,"1",STAMP)])
            with self.assertRaises(ValueError):
                aggregate(con, expected_snapshot_at=SNAPSHOT, snapshot_timestamp=STAMP, resolution_status="COMPLETE", ready_for_dependents=True)
            con.close()
            con = self.make([], [(1,"1",STAMP)], [(10, value, STAMP)])
            with self.assertRaises(ValueError):
                aggregate(con, expected_snapshot_at=SNAPSHOT, snapshot_timestamp=STAMP, resolution_status="COMPLETE", ready_for_dependents=True)

    def test_result_count_is_integer(self):
        con = self.make([], [(1,"1",date(2020,1,1))], [(10,"1",date(2020,1,1))])
        aggregate(con, expected_snapshot_at=SNAPSHOT, snapshot_timestamp=STAMP, resolution_status="COMPLETE", ready_for_dependents=True)
        self.assertEqual(con.execute("DESCRIBE version_dependents").fetchall()[-1][1], "INTEGER")

    def test_failed_retry_preserves_previous_result(self):
        con = self.make([(1,"1",10,"1")], [(1,"1",date(2020,1,1))], [(10,"1",date(2020,1,1))])
        aggregate(con, expected_snapshot_at=SNAPSHOT, snapshot_timestamp=STAMP, resolution_status="COMPLETE", ready_for_dependents=True)
        con.execute("UPDATE requirements_edges SET target_package_id=99")
        with self.assertRaises(ValueError):
            aggregate(con, expected_snapshot_at=SNAPSHOT, snapshot_timestamp=STAMP, resolution_status="COMPLETE", ready_for_dependents=True)
        self.assertEqual(con.execute("SELECT dependents_count FROM version_dependents").fetchone()[0], 1)

    def test_existing_scratch_is_rejected_without_replacement(self):
        con = self.make([], [(1,"1",date(2020,1,1))], [(10,"1",date(2020,1,1))])
        con.execute("CREATE TEMP TABLE _version_dependents(marker INTEGER)")
        con.execute("INSERT INTO _version_dependents VALUES (7)")
        with self.assertRaises(ValueError):
            aggregate(con, expected_snapshot_at=SNAPSHOT, snapshot_timestamp=STAMP, resolution_status="COMPLETE", ready_for_dependents=True)
        self.assertEqual(con.execute("SELECT marker FROM _version_dependents").fetchone()[0], 7)

    def test_result_creation_failure_rolls_back_scratch_and_result(self):
        class FailingConnection:
            def __init__(self, inner):
                self.inner = inner
                self.failed = False

            def execute(self, sql, params=None):
                if "CREATE TABLE version_dependents AS" in sql and not self.failed:
                    self.failed = True
                    raise duckdb.Error("injected result creation failure")
                return self.inner.execute(sql, params or [])

        con = self.make([(1,"1",10,"1")], [(1,"1",date(2020,1,1))], [(10,"1",date(2020,1,1))])
        failing = FailingConnection(con)
        with self.assertRaisesRegex(duckdb.Error, "injected"):
            aggregate(failing, expected_snapshot_at=SNAPSHOT, snapshot_timestamp=STAMP, resolution_status="COMPLETE", ready_for_dependents=True)
        self.assertEqual(con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name IN ('version_dependents','_version_dependents')").fetchone()[0], 0)
        self.assertEqual(con.execute("SELECT count(*) FROM requirements_edges").fetchone()[0], 1)

    def test_duplicate_empty_and_wrong_snapshot_rejected(self):
        con = self.make([], [(1,"1",date(2020,1,1)),(1,"1",date(2020,1,1))], [(10,"1",date(2020,1,1))])
        with self.assertRaises(ValueError):
            aggregate(con, expected_snapshot_at=SNAPSHOT, snapshot_timestamp=STAMP, resolution_status="COMPLETE", ready_for_dependents=True)
        con.close()
        con = self.make([], [(1,"1",date(2020,1,1))], [(10,"1",date(2020,1,1))])
        con.execute("UPDATE approved_targets SET snapshot_at=DATE '2026-08-30'")
        with self.assertRaises(ValueError):
            aggregate(con, expected_snapshot_at=SNAPSHOT, snapshot_timestamp=STAMP, resolution_status="COMPLETE", ready_for_dependents=True)

    def test_future_and_null_publication_rejected(self):
        for published in (None, date(2026, 9, 1)):
            con = self.make([], [(1,"1",published)], [(10,"1",date(2020,1,1))])
            with self.assertRaises(ValueError):
                aggregate(con, expected_snapshot_at=SNAPSHOT, snapshot_timestamp=STAMP, resolution_status="COMPLETE", ready_for_dependents=True)


if __name__ == "__main__":
    unittest.main()
