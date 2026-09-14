from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

import duckdb

from .historical_profile_queries import profile_tables, verify_profile_tables


class HistoricalProfileQueriesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.con = duckdb.connect()
        self.con.execute("""
            CREATE TABLE source_population(
              source_package_id INTEGER, source_name VARCHAR, source_version VARCHAR,
              birth_index INTEGER, requirements_present BOOLEAN, selected_list_null BOOLEAN,
              declaration_count BIGINT, excluded_peer_count BIGINT,
              excluded_optional_count BIGINT, dependency_error BOOLEAN)
        """)
        self.con.execute("""
            CREATE TABLE target_population(package_id INTEGER, name VARCHAR, version VARCHAR, birth_index INTEGER)
        """)
        self.con.execute("""
            CREATE TABLE input_requirements(Name VARCHAR, Version VARCHAR,
              Dependencies STRUCT(Name VARCHAR, Requirement VARCHAR)[])
        """)
        self.con.execute("CREATE TABLE input_package(package_id INTEGER, name VARCHAR)")

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def fixture(self, reverse=False):
        self.con.execute("INSERT INTO input_package VALUES (1,'alpha'),(2,'beta'),(3,'unused')")
        self.con.execute("INSERT INTO target_population VALUES (1,'alpha','1.0.0',0),(1,'alpha','1.1.0',1),(2,'beta','2.0.0',2)")
        rows = [
            (10, 'src-a', '1.0.0', 0, True, False, 4, 0, 0, False),
            (11, 'src-b', '1.0.0', 2, True, False, 1, 0, 0, False),
            (12, 'src-empty', '1.0.0', 1, True, False, 0, 0, 0, False),
        ]
        self.con.executemany("INSERT INTO source_population VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
        deps = [
            ("src-a", "1.0.0", "[{'Name':'alpha','Requirement':'^1.0.0'},{'Name':'alpha','Requirement':'^1.0.0'},{'Name':'missing','Requirement':'~9.0.0'},{'Name':NULL,'Requirement':''}]"),
            ("src-b", "1.0.0", "[{'Name':'alpha','Requirement':'^1.0.0'}]"),
            ("src-empty", "1.0.0", "[]"),
        ]
        if reverse:
            deps = list(reversed(deps))
        for name, version, literal in deps:
            self.con.execute(f"INSERT INTO input_requirements VALUES (?, ?, {literal})", [name, version])

    def test_profile_preserves_null_duplicates_unknown_and_late_birth(self):
        self.fixture()
        out = Path(self.tmp.name) / "profile"
        stats = profile_tables(self.con, output=out, snapshot_count=3)
        self.assertEqual(stats["source_declarations"], 5)
        self.assertEqual(stats["lookup_declarations"], 5)
        self.assertEqual(stats["unique_lookups"], 3)
        self.assertEqual(stats["known_package_names"], 2)  # target names include beta
        self.assertEqual(stats["candidate_overbound_package_count"], 0)
        rows = self.con.execute("SELECT * FROM read_parquet(?) ORDER BY lookup_id", [str(out / "lookup_workload.parquet")]).fetchall()
        self.assertEqual([(r[1], r[2], r[3], r[4]) for r in rows], [
            (None, '', 1, 0), ('alpha', '^1.0.0', 3, 0), ('missing', '~9.0.0', 1, 0)])
        packages = self.con.execute("SELECT * FROM read_parquet(?) ORDER BY name NULLS FIRST", [str(out / "package_workload.parquet")]).fetchall()
        self.assertTrue(any(r[:6] == ('missing', 0, 1, 1, False, None) for r in packages))
        self.assertTrue(any(r[:6] == (None, 0, 1, 1, False, None) for r in packages))
        verified = verify_profile_tables(self.con, out, stats)
        self.assertTrue(verified["verified"])

    def test_order_reversal_has_same_lookup_output(self):
        self.fixture()
        first = Path(self.tmp.name) / "first"
        profile_tables(self.con, output=first, snapshot_count=3)
        expected = self.con.execute("SELECT * FROM read_parquet(?) ORDER BY lookup_id", [str(first / "lookup_workload.parquet")]).fetchall()
        self.con.close()
        self.con = duckdb.connect()
        self.setUpTablesAgain = None
        # Recreate the same schema and data in the opposite source row order.
        for sql in (
            "CREATE TABLE source_population(source_package_id INTEGER, source_name VARCHAR, source_version VARCHAR, birth_index INTEGER, requirements_present BOOLEAN, selected_list_null BOOLEAN, declaration_count BIGINT, excluded_peer_count BIGINT, excluded_optional_count BIGINT, dependency_error BOOLEAN)",
            "CREATE TABLE target_population(package_id INTEGER, name VARCHAR, version VARCHAR, birth_index INTEGER)",
            "CREATE TABLE input_requirements(Name VARCHAR, Version VARCHAR, Dependencies STRUCT(Name VARCHAR, Requirement VARCHAR)[])",
            "CREATE TABLE input_package(package_id INTEGER, name VARCHAR)"):
            self.con.execute(sql)
        self.fixture(reverse=True)
        second = Path(self.tmp.name) / "second"
        profile_tables(self.con, output=second, snapshot_count=3)
        actual = self.con.execute("SELECT * FROM read_parquet(?) ORDER BY lookup_id", [str(second / "lookup_workload.parquet")]).fetchall()
        self.assertEqual(expected, actual)

    def test_missing_declaration_fails_conservation(self):
        self.fixture()
        self.con.execute("UPDATE source_population SET declaration_count=6 WHERE source_name='src-a'")
        with self.assertRaisesRegex(ValueError, "conservation"):
            profile_tables(self.con, output=Path(self.tmp.name) / "bad", snapshot_count=3)

    def test_known_package_without_candidates_is_not_unknown(self):
        self.fixture()
        self.con.execute("UPDATE input_package SET name='missing' WHERE package_id=3")
        out = Path(self.tmp.name) / "known-empty"
        stats = profile_tables(self.con, output=out, snapshot_count=3)
        row = self.con.execute("SELECT known_package,candidate_count,package_id FROM package_workload WHERE name='missing'").fetchone()
        self.assertEqual(row, (True, 0, 3))
        self.assertEqual(stats["target_names_without_lookup"], 1)

    def test_candidate_worker_limit_is_reported_without_discarding_rows(self):
        self.fixture()
        self.con.execute("DELETE FROM target_population WHERE name='alpha'")
        self.con.execute("INSERT INTO target_population SELECT 1,'alpha','1.0.'||i,0 FROM range(100001) r(i)")
        stats = profile_tables(self.con, output=Path(self.tmp.name)/"large", snapshot_count=229)
        self.assertEqual(stats["active_candidate_count_overbound_packages"], 1)
        self.assertTrue(stats["worker_batch_overbound"])
        self.assertEqual(stats["max_active_candidate_count"], 100001)
        self.assertEqual(stats["worker_requirement_batch_max"], 19)
        self.assertEqual(stats["source_declarations"], 5)

    def test_rehashed_output_values_are_compared_with_sql_relation(self):
        self.fixture()
        out=Path(self.tmp.name)/"tamper"
        stats=profile_tables(self.con, output=out, snapshot_count=3)
        self.con.execute("COPY (SELECT * REPLACE ('changed' AS requirement) FROM lookup_workload) TO ? (FORMAT PARQUET)",
                         [str(out/'replacement.parquet')])
        (out/'replacement.parquet').replace(out/'lookup_workload.parquet')
        with self.assertRaisesRegex(ValueError, "differs from the original"):
            verify_profile_tables(self.con,out,stats)


if __name__ == "__main__":
    unittest.main()
