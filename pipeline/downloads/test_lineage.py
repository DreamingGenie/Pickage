import gzip
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from pipeline.downloads.lineage import inspect_lineage


def _row(name="demo", value=12):
    return {"name": name, "rank": 1, "kind": "single", "start": "2026-01-01",
            "end": "2026-01-02", "tier": "A", "fetched_at": "2026-01-03T00:00:00+00:00",
            "task_id": "single-1", "status": "ok",
            "downloads": [{"downloads": value, "day": "2026-01-01"}]}


class LineageTests(unittest.TestCase):
    def test_streams_responses_and_does_not_call_response_rows_daily_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "part-00000.jsonl.gz"
            with gzip.open(path, "wt", encoding="utf-8") as stream:
                stream.write(json.dumps(_row()) + "\n")
                stream.write(json.dumps(_row("other", 0)) + "\n")
            result = inspect_lineage(root, [{"path": path.name, "role": "raw_response"}], "2026-09-02")
            self.assertEqual(result["summary"]["response_row_count"], 2)
            self.assertEqual(result["summary"]["unique_package_count"], 2)
            self.assertTrue(result["summary"]["daily_row_count_is_not_inferred"])
            self.assertEqual(result["raw_files"][0]["min_date"], "2026-01-01")

    def test_rejects_invalid_nested_value(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "part.jsonl.gz"
            bad = _row()
            bad["downloads"] = [{"downloads": -1, "day": "2026-01-01"}]
            with gzip.open(path, "wt", encoding="utf-8") as stream:
                stream.write(json.dumps(bad) + "\n")
            with self.assertRaises(ValueError):
                inspect_lineage(root, [{"path": path.name, "role": "raw_response"}], "run")

    def test_not_found_response_has_null_downloads(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "part.jsonl.gz"
            row = _row("missing")
            row["status"] = "not_found"
            row["downloads"] = None
            with gzip.open(path, "wt", encoding="utf-8") as stream:
                stream.write(json.dumps(row) + "\n")
            result = inspect_lineage(root, [{"path": path.name, "role": "raw_response"}], "run")
            self.assertEqual(result["summary"]["response_row_count"], 1)
            self.assertIsNone(result["summary"]["min_date"])

    def test_history_provenance_is_explicit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "part.jsonl.gz"
            with gzip.open(path, "wt", encoding="utf-8") as stream:
                stream.write(json.dumps(_row()) + "\n")
            result = inspect_lineage(root, [{"path": path.name, "role": "raw_response"}], "run")
            provenance = result["provenance"]["generator_candidate"]
            self.assertEqual(provenance["status"], "HISTORY_ONLY_CANDIDATE")
            self.assertEqual(provenance["commit"], "33b49adef8ea6f6f01bf1f91048ffcf239c7a73d")

    def test_latest_fetched_duplicate_is_used_and_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "part.jsonl.gz"
            old, new = _row("dup", 10), _row("dup", 20)
            old["fetched_at"], new["fetched_at"] = "2026-01-03T00:00:00+00:00", "2026-01-04T00:00:00+00:00"
            with gzip.open(path, "wt", encoding="utf-8") as stream:
                stream.write(json.dumps(old) + "\n")
                stream.write(json.dumps(new) + "\n")
            records = [{"path": path.name, "role": "raw_response"}, {"path": "out.parquet", "role": "daily_parquet"}]
            with patch("pipeline.downloads.lineage._safe_path", side_effect=lambda root, p: (p, path)):
                with patch("pipeline.downloads.lineage._parquet_values", return_value={("dup", "2026-01-01"): (99, False)}):
                    with self.assertRaises(ValueError):
                        inspect_lineage(root, records, "run")


if __name__ == "__main__":
    unittest.main()
