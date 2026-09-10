import gzip
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import duckdb

from .input import discover_source, inspect_source


class DownloadsInputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "raw" / "run=run-1").mkdir(parents=True)
        (self.root / "parquet" / "downloads" / "date=2026-09-01").mkdir(parents=True)
        (self.root / "targets_top100k_20260902.csv").write_text(
            "rank,name,downloads_last_month,dependent_packages_count,status\n1,alpha,2,3,READY\n2,beta,0,0,NOT_FOUND\n2,beta,0,0,NOT_FOUND\n", encoding="utf-8")
        run = self.root / "raw" / "run=run-1"
        (run / "run.json").write_text(json.dumps({"run": "run-1", "targets": "targets_top100k_20260902.csv"}), encoding="utf-8")
        (run / "manifest.json").write_text(json.dumps({"run": "run-1", "targets": "data/downloads/targets_top100k_20260902.csv", "final": True}), encoding="utf-8")
        with gzip.open(run / "part-00000.jsonl.gz", "wt", encoding="utf-8") as out:
            out.write(json.dumps({"name": "alpha"}) + "\n")
        con = duckdb.connect()
        con.execute("CREATE TABLE d(name VARCHAR, downloads BIGINT, imputed_gap BOOLEAN, tier VARCHAR, fetched_at TIMESTAMP, date DATE)")
        con.execute("INSERT INTO d VALUES ('alpha', 0, false, 'A', TIMESTAMP '2026-09-01 00:00:00', DATE '2026-09-01')")
        con.execute("COPY d TO ? (FORMAT PARQUET)", [str(self.root / "parquet" / "downloads" / "date=2026-09-01" / "part-0.parquet")])
        con.execute("CREATE TABLE s(name VARCHAR, tier VARCHAR, status VARCHAR, first_date DATE, last_date DATE, last_fetched_at TIMESTAMP)")
        con.execute("INSERT INTO s VALUES ('alpha', 'A', 'READY', DATE '2026-09-01', DATE '2026-09-01', TIMESTAMP '2026-09-01 00:00:00'), ('beta', 'A', 'NOT_FOUND', NULL, NULL, NULL)")
        con.execute("COPY s TO ? (FORMAT PARQUET)", [str(self.root / "parquet" / "downloads_status.parquet")])
        con.close()
        (self.root / "parquet_smoke").mkdir()
        (self.root / "parquet_smoke" / "x.parquet").write_bytes(b"smoke")
        (self.root / "backfill.log").write_text("log", encoding="utf-8")
        self.addCleanup(self.tmp.cleanup)

    def _replace_daily(self, downloads, gap=False, name="alpha"):
        path = next((self.root / "parquet" / "downloads" / "date=2026-09-01").glob("*.parquet"))
        con = duckdb.connect()
        con.execute("CREATE TABLE d(name VARCHAR, downloads BIGINT, imputed_gap BOOLEAN, tier VARCHAR, fetched_at TIMESTAMP, date DATE)")
        con.execute("INSERT INTO d VALUES (?, ?, ?, 'A', TIMESTAMP '2026-09-01 00:00:00', DATE '2026-09-01')", [name, downloads, gap])
        con.execute("COPY d TO ? (FORMAT PARQUET)", [str(path)])
        con.close()

    def test_discovery_and_inspection_keep_csv_duplicates_and_exclusions(self):
        discovered = discover_source(self.root, "run-1")
        self.assertTrue(any(item["path"] == "parquet_smoke/x.parquet" for item in discovered["excluded"]))
        result = inspect_source(self.root, "run-1")
        self.assertEqual(result["format_version"], 1)
        self.assertEqual(result["dataset"], "npm-downloads")
        self.assertEqual(result["quality"]["target_rows"], 3)
        self.assertEqual(result["quality"]["target_unique_names"], 2)
        self.assertEqual(result["quality"]["target_duplicate_names"][0]["name"], "beta")
        self.assertEqual(result["quality"]["downloads_zero"], 1)
        self.assertEqual({item["role"] for item in result["files"]}, {"target_csv", "source_metadata", "raw_response", "daily_parquet", "status_parquet"})

    def test_daily_duplicate_is_rejected(self):
        path = self.root / "parquet" / "downloads" / "date=2026-09-01" / "part-1.parquet"
        shutil.copyfile(next(path.parent.glob("*.parquet")), path)
        with self.assertRaisesRegex(ValueError, "duplicate daily"):
            inspect_source(self.root, "run-1")

    def test_unknown_file_is_rejected(self):
        (self.root / "unexpected.bin").write_bytes(b"x")
        with self.assertRaisesRegex(ValueError, "unknown regular file"):
            discover_source(self.root, "run-1")

    def test_metadata_identity_is_checked(self):
        path = self.root / "raw" / "run=run-1" / "manifest.json"
        path.write_text(json.dumps({"run": "other", "targets": "targets_top100k_20260902.csv", "final": True}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "metadata run"):
            inspect_source(self.root, "run-1")

    def test_target_blank_and_negative_downloads_are_rejected(self):
        target = self.root / "targets_top100k_20260902.csv"
        target.write_text("name,status\n,READY\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "target names"):
            inspect_source(self.root, "run-1")
        target.write_text("name,status\nalpha,READY\n", encoding="utf-8")
        self._replace_daily(-1)
        with self.assertRaisesRegex(ValueError, "negative downloads"):
            inspect_source(self.root, "run-1")

    def test_gap_must_correspond_to_null_download(self):
        self._replace_daily(0, gap=True)
        with self.assertRaisesRegex(ValueError, "disagreement"):
            inspect_source(self.root, "run-1")

    def test_ready_coverage_reports_null_without_imputation(self):
        # A NULL value with an explicit gap marker is retained as an observed
        # day and counted separately from missing calendar days.
        self._replace_daily(None, gap=True)
        result = inspect_source(self.root, "run-1")
        coverage = result["quality"]["ready_period_coverage"]
        self.assertEqual(coverage["packages"], 1)
        self.assertEqual(coverage["expected_days"], 1)
        self.assertEqual(coverage["observed_days"], 1)
        self.assertEqual(coverage["missing_days"], 0)
        self.assertEqual(coverage["packages_with_null_values"], 1)
        self.assertEqual(coverage["complete_packages"], 0)

    def test_physical_schema_variation_is_rejected_before_casting(self):
        directory = self.root / "parquet" / "downloads" / "date=2026-09-01"
        second = directory / "part-1.parquet"
        con = duckdb.connect()
        con.execute("CREATE TABLE d(name VARCHAR, downloads DOUBLE, imputed_gap BOOLEAN, tier VARCHAR, fetched_at TIMESTAMP, date DATE)")
        con.execute("INSERT INTO d VALUES ('alpha', 1.5, false, 'A', TIMESTAMP '2026-09-01 00:00:00', DATE '2026-09-01')")
        con.execute("COPY d TO ? (FORMAT PARQUET)", [str(second)])
        con.close()
        with self.assertRaisesRegex(ValueError, "physical schemas differ"):
            inspect_source(self.root, "run-1")


if __name__ == "__main__":
    unittest.main()
