"""Contract and syntax tests for the portable validation query catalogue."""

import unittest

import duckdb

from pipeline.integrity_validation.queries import CHECKS
from pipeline.integrity_validation.schema import TABLES


class QueryCatalogueTest(unittest.TestCase):
    def _connection(self):
        con = duckdb.connect(":memory:", config={"threads": 1, "memory_limit": "128MB", "max_temp_directory_size": "0B"})
        con.execute("CREATE SCHEMA public")
        con.execute("CREATE SCHEMA validation")
        for qualified, columns in TABLES.items():
            definition = ", ".join(f'"{column}" {kind}' for column, kind in columns)
            con.execute(f"CREATE TABLE {qualified} ({definition})")
        con.execute("INSERT INTO public.package VALUES (1, 'alpha', NULL), (2, 'beta', NULL)")
        con.execute("INSERT INTO public.snapshot VALUES ('2026-08-31')")
        con.execute("INSERT INTO public.package_snapshot VALUES (1, '2026-08-31', 10, 2, 3)")
        con.execute("INSERT INTO public.version VALUES ('1.0.0', 1, '2026-08-31 10:00:00', 0, NULL, NULL, NULL, '{}')")
        con.execute("INSERT INTO public.package_version_snapshot VALUES (1, '1.0.0', '2026-08-31', 1)")
        con.execute("INSERT INTO validation.snapshot_context VALUES ('2026-08-31', '2026-08-31 12:00:00')")
        con.execute("INSERT INTO validation.package_population VALUES (1, '2026-08-31')")
        con.execute("INSERT INTO validation.target_population VALUES (1, '1.0.0', '2026-08-31')")
        con.execute("INSERT INTO validation.expected_package_metrics VALUES (1, '2026-08-31', 10, 2, 3)")
        con.execute("INSERT INTO validation.resolved_edges VALUES (1, '1.0.0', 1, '1.0.0', '2026-08-31')")
        con.execute("INSERT INTO validation.source_quality VALUES ('2026-08-31', 'COMPLETE', 'COMPLETE', 0)")
        return con

    def test_catalogue_has_stable_scalar_selects(self):
        self.assertGreaterEqual(len(CHECKS), 10)
        ids = [check["id"] for check in CHECKS]
        self.assertEqual(len(ids), len(set(ids)))
        for check in CHECKS:
            self.assertRegex(check["id"], r"^[a-z][a-z0-9_]*$")
            self.assertTrue(check["description"])
            self.assertRegex(check["sql"].lstrip().upper(), r"^SELECT\b")

    def test_every_query_executes_against_empty_fixture(self):
        con = duckdb.connect(":memory:", config={"threads": 1, "memory_limit": "128MB", "max_temp_directory_size": "0B"})
        try:
            con.execute("CREATE SCHEMA public")
            con.execute("CREATE SCHEMA validation")
            for qualified, columns in TABLES.items():
                definition = ", ".join(f'"{column}" {kind}' for column, kind in columns)
                con.execute(f"CREATE TABLE {qualified} ({definition})")
            for check in CHECKS:
                value = con.execute(check["sql"]).fetchone()
                self.assertIsNotNone(value, check["id"])
                self.assertEqual(len(value), 1, check["id"])
                self.assertIsInstance(value[0], int, check["id"])
        finally:
            con.close()

    def test_direct_count_detects_pvs_value_mismatch(self):
        con = self._connection()
        try:
            query = next(c["sql"] for c in CHECKS if c["id"] == "resolved_edges_direct_count")
            self.assertEqual(con.execute(query).fetchone()[0], 0)
            con.execute("UPDATE public.package_version_snapshot SET dependents_count = 0")
            self.assertGreater(con.execute(query).fetchone()[0], 0)
        finally:
            con.close()

    def test_valid_fixture_has_no_violations(self):
        con = self._connection()
        try:
            violations = {
                check["id"]: con.execute(check["sql"]).fetchone()[0]
                for check in CHECKS
            }
            self.assertEqual(violations, {check["id"]: 0 for check in CHECKS})
        finally:
            con.close()

    def test_extra_pvs_and_missing_quality_are_detected(self):
        con = self._connection()
        try:
            extra_query = next(c["sql"] for c in CHECKS if c["id"] == "target_pvs_extra")
            quality_query = next(c["sql"] for c in CHECKS if c["id"] == "source_quality_snapshot_coverage")
            self.assertEqual(con.execute(extra_query).fetchone()[0], 0)
            con.execute("INSERT INTO public.version VALUES ('2.0.0', 1, '2026-08-31 10:00:00', 0, NULL, NULL, NULL, '{}')")
            con.execute("INSERT INTO public.package_version_snapshot VALUES (1, '2.0.0', '2026-08-31', 1)")
            self.assertGreater(con.execute(extra_query).fetchone()[0], 0)
            con.execute("DELETE FROM validation.source_quality")
            self.assertGreater(con.execute(quality_query).fetchone()[0], 0)
        finally:
            con.close()


if __name__ == "__main__":
    unittest.main()
