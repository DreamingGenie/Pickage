import tempfile
import unittest
import os
from pathlib import Path

import duckdb

from pipeline.preprocessing.curated.build import _write_master


class MasterWriterTests(unittest.TestCase):
    def _parquet(self, root, name, columns, rows):
        path = Path(root) / name
        con = duckdb.connect()
        try:
            values = ",".join("(" + ",".join("?" for _ in columns) + ")" for _ in rows)
            con.execute(
                f"CREATE TABLE t AS SELECT * FROM (VALUES {values}) v({','.join(columns)})",
                [value for row in rows for value in row],
            )
            con.execute("COPY t TO ? (FORMAT PARQUET)", [str(path)])
        finally:
            con.close()
        return path

    def test_current_files_are_hardlinked_and_override_previous(self):
        with tempfile.TemporaryDirectory() as root:
            current = self._parquet(root, "current.parquet", ["package_id", "name"],
                                    [(1, "new"), (3, "current")])
            previous = self._parquet(root, "previous.parquet", ["package_id", "name"],
                                     [(1, "old"), (2, "retained")])
            con = duckdb.connect()
            try:
                paths = _write_master(con, [current], [previous], Path(root) / "out", "package")
                linked = Path(root) / "out/master_package/data/current-000.parquet"
                self.assertTrue(os.path.samefile(current, linked))
                rows = con.execute("SELECT package_id, name FROM read_parquet(?) ORDER BY package_id",
                                   [[str(path) for path in paths]]).fetchall()
                self.assertEqual(rows, [(1, "new"), (2, "retained"), (3, "current")])
                current.unlink()
                self.assertEqual(con.execute("SELECT count(*) FROM read_parquet(?)", [str(linked)]).fetchone()[0], 2)
            finally:
                con.close()

    def test_forced_multiple_buckets_matches_anti_join_oracle(self):
        with tempfile.TemporaryDirectory() as root:
            current = self._parquet(root, "current.parquet", ["package_id", "name"],
                                    [(1, "one"), (3, "three")])
            previous = self._parquet(root, "previous.parquet", ["package_id", "name"],
                                     [(1, "old"), (2, "two"), (4, "four")])
            con = duckdb.connect()
            try:
                paths = _write_master(con, [current], [previous], Path(root) / "out", "package",
                                      bucket_target_rows=1)
                rows = con.execute("SELECT package_id, name FROM read_parquet(?) ORDER BY package_id",
                                   [[str(path) for path in paths]]).fetchall()
                self.assertEqual(rows, [(1, "one"), (2, "two"), (3, "three"), (4, "four")])
                self.assertEqual(len(list((Path(root) / "out/master_package/data").glob("missing-*.parquet"))), 3)
            finally:
                con.close()

    def test_paths_with_apostrophes_are_escaped(self):
        with tempfile.TemporaryDirectory() as root:
            quoted = Path(root) / "quote'dir"
            quoted.mkdir()
            current = self._parquet(quoted, "current.parquet", ["package_id", "name"], [(1, "one")])
            previous = self._parquet(quoted, "previous.parquet", ["package_id", "name"], [(2, "two")])
            con = duckdb.connect()
            try:
                paths = _write_master(con, [current], [previous], Path(root) / "out", "package")
                self.assertEqual(con.execute("SELECT count(*) FROM read_parquet(?)", [[str(p) for p in paths]]).fetchone()[0], 2)
            finally:
                con.close()

    def test_version_identity_keeps_old_version_for_same_package(self):
        with tempfile.TemporaryDirectory() as root:
            current = self._parquet(root, "current.parquet", ["package_id", "version", "value"],
                                    [(1, "2.0", "new")])
            previous = self._parquet(root, "previous.parquet", ["package_id", "version", "value"],
                                     [(1, "1.0", "old"), (1, "2.0", "stale")])
            con = duckdb.connect()
            try:
                paths = _write_master(con, [current], [previous], Path(root) / "out", "version")
                rows = con.execute("SELECT package_id, version, value FROM read_parquet(?) ORDER BY version",
                                   [[str(path) for path in paths]]).fetchall()
                self.assertEqual(rows, [(1, "1.0", "old"), (1, "2.0", "new")])
            finally:
                con.close()


if __name__ == "__main__":
    unittest.main()
