import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import duckdb

from pipeline.preprocessing.curated.changes import build_changes


class ChangesTest(unittest.TestCase):
    def _parquet(self, root, name, rows):
        path = Path(root) / name
        con = duckdb.connect()
        try:
            con.execute("CREATE TABLE t AS SELECT * FROM (VALUES " +
                        ",".join("(CAST(? AS INTEGER), CAST(? AS VARCHAR), CAST(? AS VARCHAR), CAST(? AS VARCHAR))" for _ in rows) +
                        ") AS x(package_id, version, description, dependency)",
                        [v for row in rows for v in row])
            con.execute(f"COPY t TO '{path.as_posix()}' (FORMAT PARQUET)")
        finally:
            con.close()
        return path

    def _package(self, root, name, rows):
        path = Path(root) / name
        con = duckdb.connect()
        try:
            con.execute("CREATE TABLE t AS SELECT * FROM (VALUES " +
                        ",".join("(CAST(? AS INTEGER), CAST(? AS VARCHAR), CAST(? AS VARCHAR))" for _ in rows) +
                        ") AS x(package_id, name, repo_url)",
                        [v for row in rows for v in row])
            con.execute(f"COPY t TO '{path.as_posix()}' (FORMAT PARQUET)")
        finally:
            con.close()
        return path

    @patch('pipeline.preprocessing.curated.changes._BUCKET_ROWS', 1)
    def test_insert_update_unchanged_and_missing(self):
        with tempfile.TemporaryDirectory() as d:
            oldp = self._package(d, "oldp.parquet", [(1, "a", "r"), (2, "b", "r")])
            newp = self._package(d, "newp.parquet", [(1, "a", "r2"), (3, "c", "r")])
            oldv = self._parquet(d, "oldv.parquet", [(1, "1.0", "same", '{"a":1,"b":2}'), (2, "1.0", "gone", None)])
            newv = self._parquet(d, "newv.parquet", [(1, "1.0", "same", '{"b":2,"a":1}'), (1, "2.0", "copy", None)])
            result = build_changes([oldp], [oldv], [newp], [newv], Path(d) / "out")
            con = duckdb.connect()
            try:
                self.assertEqual(con.execute("SELECT package_id, change_type FROM read_parquet(?) ORDER BY package_id", [result["files"]["package_upserts"]["path"]]).fetchall(), [(1, "UPDATE"), (3, "INSERT")])
                self.assertEqual(con.execute("SELECT package_id, version, change_type FROM read_parquet(?) ORDER BY package_id, version", [result["files"]["version_upserts"]["path"]]).fetchall(), [(1, "2.0", "INSERT")])
                self.assertEqual(con.execute("SELECT package_id FROM read_parquet(?)", [result["files"]["missing_previous"]["package"]["path"]]).fetchall(), [(2,)])
            finally:
                con.close()

    def test_null_is_a_change(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._package(d, "p.parquet", [(1, "a", "r")])
            old = self._parquet(d, "old.parquet", [(1, "1", "x", None)])
            new = self._parquet(d, "new.parquet", [(1, "1", None, None)])
            result = build_changes([p], [old], [p], [new], Path(d) / "out")
            con = duckdb.connect()
            self.assertEqual(con.execute("SELECT count(*) FROM read_parquet(?)", [result["files"]["version_upserts"]["path"]]).fetchone()[0], 1)
            con.close()

    def test_json_array_order_and_duplicates_are_changes(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._package(d, "p.parquet", [(1, "a", "r")])
            old = self._parquet(d, "old.parquet", [(1, "1", "x", '{"items":[1,2,2]}')])
            new = self._parquet(d, "new.parquet", [(1, "1", "x", '{"items":[2,1,2]}')])
            result = build_changes([p], [old], [p], [new], Path(d) / "out")
            con = duckdb.connect()
            self.assertEqual(con.execute("SELECT count(*) FROM read_parquet(?)", [result["files"]["version_upserts"]["path"]]).fetchone()[0], 1)
            con.close()

    def test_identical_json_rows_are_filtered_before_semantic_comparison(self):
        """Large unchanged JSON populations must produce no upsert rows."""
        with tempfile.TemporaryDirectory() as d:
            p = self._package(d, "p.parquet", [(1, "a", "r")])
            rows = [(1, str(i), "same", '{"a":1,"nested":{"b":[1,2,2]}}')
                    for i in range(1000)]
            old = self._parquet(d, "old.parquet", rows)
            new = self._parquet(d, "new.parquet", rows)
            result = build_changes([p], [old], [p], [new], Path(d) / "out")
            con = duckdb.connect()
            try:
                self.assertEqual(
                    con.execute("SELECT count(*) FROM read_parquet(?)",
                                [result["files"]["version_upserts"]["path"]]).fetchone()[0],
                    0,
                )
            finally:
                con.close()

    def test_identity_null_and_duplicate_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            old = self._package(d, "old.parquet", [(1, "a", "r")])
            new = self._package(d, "new.parquet", [(1, "a", "r"), (1, "a2", "r")])
            v = self._parquet(d, "v.parquet", [(1, "1", "x", None)])
            with self.assertRaisesRegex(ValueError, "duplicate identity"):
                build_changes([old], [v], [new], [v], Path(d) / "out")


if __name__ == "__main__":
    unittest.main()
