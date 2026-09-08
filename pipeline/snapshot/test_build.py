"""Candidate provenance and explicit-date SQL boundary tests."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from .build import prepare, snapshot_sql


class BuildTests(unittest.TestCase):
    def source(self):
        return {
            "timestamps": ["2026-08-31T21:01:10.517131Z", "2026-08-24T20:00:00Z"],
            "validation": "PARQUET_FOOTER_TIMESTAMP_CHECKED", "file_count": 2,
            "total_rows": 20, "snapshots": [],
        }

    @patch("pipeline.snapshot.build.inspect_projects")
    def test_candidate_keeps_hashes_window_and_unpublished_status(self, inspect):
        inspect.return_value = self.source()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "result"
            result = prepare(Path(tmp) / "projects", target)
            candidate = json.loads((target / "snapshot-candidate.json").read_text())
            self.assertEqual(result["snapshot_count"], 2)
            self.assertFalse(candidate["db_published"])
            self.assertFalse(candidate["service_ready"])
            self.assertEqual(candidate["calendar"][1]["previous_snapshot_at"], "2026-08-24")
            self.assertEqual(candidate["calendar"][1]["interval_days"], 7)
            for item in candidate["files"]:
                self.assertEqual(item["sha256"], hashlib.sha256((target / item["path"]).read_bytes()).hexdigest())
            self.assertEqual(candidate["source"]["inventory_sha256"], candidate["files"][0]["sha256"])
            sql = (target / "snapshot-dates.sql").read_text()
            self.assertIn("DATE '2026-08-24'", sql)
            self.assertIn("ON CONFLICT (snapshot_at) DO NOTHING", sql)
            self.assertNotIn("DEFAULT", sql)
            with self.assertRaises(ValueError):
                prepare(Path(tmp), target)
            self.assertEqual(inspect.call_count, 1)

    @patch("pipeline.snapshot.build.inspect_projects", side_effect=ValueError("bad source"))
    def test_invalid_input_does_not_create_output(self, inspect):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "result"
            with self.assertRaises(ValueError):
                prepare(Path(tmp), target)
            self.assertFalse(target.exists())

    def test_sql_rejects_unordered_duplicate_and_injected_dates(self):
        for rows in ([], [{"snapshot_at": "2026-08-31"}, {"snapshot_at": "2026-08-24"}],
                     [{"snapshot_at": "2026-08-31"}] * 2,
                     [{"snapshot_at": "2026-08-31'); DROP TABLE snapshot; --"}]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                snapshot_sql(rows)


if __name__ == "__main__":
    unittest.main()
