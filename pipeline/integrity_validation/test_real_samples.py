import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import duckdb

from .real_samples import sample_sources


class RealSamplesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.dates = ["2026-01-01", "2026-02-01", "2026-03-01"]
        self.rows = [(1, 0, None, 4), (2, None, 0, None), (3, 12, 8, 0), (4, None, None, 2)]
        self._build()

    def tearDown(self):
        self.tmp.cleanup()

    def _build(self):
        for date in self.dates:
            output = self.root / "data/package_snapshot/history/full-history-288-20260909-v1" / date / "output"
            output.mkdir(parents=True)
            parquet = output / "package_snapshot.parquet"
            with duckdb.connect() as con:
                con.execute("CREATE TABLE source(package_id INTEGER,snapshot_at DATE,downloads BIGINT,stars INTEGER,open_issues INTEGER)")
                con.executemany("INSERT INTO source VALUES (?,?::date,?,?,?)", [(a, date, b, c, d) for a, b, c, d in self.rows])
                con.execute("COPY source TO ? (FORMAT PARQUET)", [str(parquet)])
            digest = hashlib.sha256(parquet.read_bytes()).hexdigest()
            manifest = {"files": [{"role": "package_snapshot", "path": "package_snapshot.parquet", "bytes": parquet.stat().st_size, "sha256": digest, "row_count": len(self.rows)}]}
            (output.parent / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def plan(self):
        return {"dates": self.dates}

    def db_query(self, _container, _database, sql):
        date = next(value for value in self.dates if value in sql)
        result = [{"package_id": a, "snapshot_at": date, "downloads": b, "stars": c, "open_issues": d} for a, b, c, d in self.rows]
        return result, 0.001

    def test_compares_first_middle_last_pinned_samples_and_reports_hashes(self):
        with patch("pipeline.integrity_validation.real_samples.query", side_effect=self.db_query):
            result = sample_sources(self.root, self.plan(), "container", "database")
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["dates"], self.dates)
        self.assertEqual(len(result["files"]), 3)
        self.assertEqual({(r["date"], r["package_id"]) for r in result["samples"]},
                         {(day, row[0]) for day in self.dates for row in self.rows})
        self.assertEqual(result["mismatches"], [])
        for item in result["files"]:
            self.assertEqual(item["sha256"], hashlib.sha256(Path(self.root / item["source_path"]).read_bytes()).hexdigest())

    def test_rejects_tampered_parquet_pin_before_database_query(self):
        path = self.root / "data/package_snapshot/history/full-history-288-20260909-v1" / self.dates[0] / "output/package_snapshot.parquet"
        path.write_bytes(path.read_bytes() + b"tamper")
        with patch("pipeline.integrity_validation.real_samples.query", side_effect=self.db_query) as database:
            with self.assertRaisesRegex(ValueError, "file pin mismatch"):
                sample_sources(self.root, self.plan(), "container", "database")
        database.assert_not_called()

    def test_reports_null_safe_metric_mismatch(self):
        def mismatching_query(container, database, sql):
            result, elapsed = self.db_query(container, database, sql)
            result[0]["downloads"] = 999
            return result, elapsed
        with patch("pipeline.integrity_validation.real_samples.query", side_effect=mismatching_query):
            result = sample_sources(self.root, self.plan(), "container", "database")
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any(item["field"] == "downloads" for item in result["mismatches"]))


if __name__ == "__main__":
    unittest.main()
