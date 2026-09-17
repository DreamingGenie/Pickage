import json
import tempfile
import unittest
from pathlib import Path

import duckdb

from pipeline.preprocessing.curated.weekly_metadata import MetadataInputError, prepare_versions


class WeeklyMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def parquet(self, name, schema, rows):
        path = self.root / (name + ".parquet")
        with duckdb.connect() as con:
            con.execute("CREATE TABLE input (" + schema + ")")
            if rows:
                con.executemany("INSERT INTO input VALUES (" + ",".join("?" for _ in rows[0]) + ")", rows)
            con.execute("COPY input TO ? (FORMAT PARQUET)", [str(path)])
        return path

    def run_adapter(self, minimum, packages, previous, ids):
        with duckdb.connect() as con:
            return prepare_versions(con, minimum, packages, previous, ids,
                                    self.root / "out", {"run_id": "parent-1"})

    def read(self, result):
        with duckdb.connect() as con:
            return con.execute("SELECT * FROM read_parquet(?) ORDER BY Name, Version",
                               [str(result["versions"])]).fetchall()

    def test_existing_metadata_is_preserved_and_new_version_inherits(self):
        minimum = self.parquet("minimum", "Name VARCHAR, Version VARCHAR, ordinal BIGINT, is_release BOOLEAN",
                               [("known", "1.0.0", 1, True), ("known", "2.0.0", 2, True)])
        packages = self.parquet("packages", "package_id INTEGER, name VARCHAR, repo_url VARCHAR",
                                [(7, "known", "https://example/known")])
        previous = self.parquet("previous", "package_id INTEGER, version VARCHAR, ordinal BIGINT, description VARCHAR, licenses VARCHAR[]",
                                [(7, "1.0.0", 1, "old description", ["MIT"])])
        ids = self.parquet("ids", "package_id INTEGER, name VARCHAR", [(7, "known")])

        result = self.run_adapter(minimum, packages, previous, ids)
        rows = self.read(result)
        self.assertEqual(rows[0][-3:], ("old description", ["MIT"], "https://example/known"))
        self.assertEqual(rows[1][-3:], ("old description", ["MIT"], "https://example/known"))
        provenance = [json.loads(line) for line in result["provenance"].read_text().splitlines()]
        inherited = next(row for row in provenance if row["version"] == "2.0.0")
        self.assertEqual(inherited["status"], "inherited")
        self.assertEqual(inherited["source_version"], "1.0.0")

    def test_new_package_metadata_is_always_null(self):
        minimum = self.parquet("minimum", "Name VARCHAR, Version VARCHAR, ordinal BIGINT, Description VARCHAR, Licenses VARCHAR[], source_repo VARCHAR",
                               [("new", "1.0.0", 1, "must be blank", ["Apache-2.0"], "https://wrong")])
        result = self.run_adapter(minimum, None, None, None)
        self.assertIsNone(self.read(result)[0][-3])
        self.assertIsNone(self.read(result)[0][-2])
        self.assertIsNone(self.read(result)[0][-1])

    def test_duplicate_min_key_is_rejected(self):
        minimum = self.parquet("minimum", "Name VARCHAR, Version VARCHAR, ordinal BIGINT",
                               [("dup", "1.0.0", 1), ("dup", "1.0.0", 1)])
        with self.assertRaises(MetadataInputError):
            self.run_adapter(minimum, None, None, None)

    def test_no_lower_parent_keeps_missing_metadata_and_records_status(self):
        minimum = self.parquet("minimum", "Name VARCHAR, Version VARCHAR, ordinal BIGINT",
                               [("known", "1.0.0", 1)])
        packages = self.parquet("packages", "package_id INTEGER, name VARCHAR, repo_url VARCHAR",
                                [(7, "known", None)])
        previous = self.parquet("previous", "package_id INTEGER, version VARCHAR, ordinal BIGINT, description VARCHAR, licenses VARCHAR[]",
                                [(7, "2.0.0", 2, "later", ["MIT"])])
        ids = self.parquet("ids", "package_id INTEGER, name VARCHAR", [(7, "known")])
        result = self.run_adapter(minimum, packages, previous, ids)
        row = self.read(result)[0]
        self.assertIsNone(row[-3])
        event = json.loads(result["provenance"].read_text())
        self.assertEqual(event["status"], "missing")

    def test_candidate_uses_current_ordinal_after_snapshot_rebase(self):
        minimum = self.parquet("minimum", "Name VARCHAR, Version VARCHAR, ordinal BIGINT",
                               [("known", "1.0.0", 1), ("known", "2.0.0", 2)])
        packages = self.parquet("packages", "package_id INTEGER, name VARCHAR, repo_url VARCHAR",
                                [(7, "known", "https://repo")])
        previous = self.parquet("previous", "package_id INTEGER, version VARCHAR, ordinal BIGINT, description VARCHAR, licenses VARCHAR[]",
                                [(7, "1.0.0", 20, "rebased parent", ["MIT"])])
        ids = self.parquet("ids", "package_id INTEGER, name VARCHAR", [(7, "known")])
        result = self.run_adapter(minimum, packages, previous, ids)
        rows = self.read(result)
        self.assertEqual(rows[1][-3], "rebased parent")

    def test_parent_version_missing_from_current_min_is_not_a_candidate(self):
        minimum = self.parquet("minimum", "Name VARCHAR, Version VARCHAR, ordinal BIGINT",
                               [("known", "2.0.0", 2)])
        packages = self.parquet("packages", "package_id INTEGER, name VARCHAR, repo_url VARCHAR",
                                [(7, "known", "https://repo")])
        previous = self.parquet("previous", "package_id INTEGER, version VARCHAR, ordinal BIGINT, description VARCHAR, licenses VARCHAR[]",
                                [(7, "1.0.0", 1, "not in current", ["MIT"])])
        ids = self.parquet("ids", "package_id INTEGER, name VARCHAR", [(7, "known")])
        result = self.run_adapter(minimum, packages, previous, ids)
        self.assertIsNone(self.read(result)[0][-3])

    def test_null_parent_metadata_stays_null_with_inherited_source(self):
        minimum = self.parquet("minimum", "Name VARCHAR, Version VARCHAR, ordinal BIGINT",
                               [("known", "1.0.0", 1), ("known", "2.0.0", 2)])
        packages = self.parquet("packages", "package_id INTEGER, name VARCHAR, repo_url VARCHAR",
                                [(7, "known", None)])
        previous = self.parquet("previous", "package_id INTEGER, version VARCHAR, ordinal BIGINT, description VARCHAR, licenses VARCHAR[]",
                                [(7, "1.0.0", 1, None, None)])
        ids = self.parquet("ids", "package_id INTEGER, name VARCHAR", [(7, "known")])
        result = self.run_adapter(minimum, packages, previous, ids)
        rows = self.read(result)
        self.assertIsNone(rows[1][-3])
        event = [json.loads(line) for line in result["provenance"].read_text().splitlines()]
        self.assertEqual(next(row for row in event if row["version"] == "2.0.0")["status"], "inherited")


if __name__ == "__main__":
    unittest.main()
