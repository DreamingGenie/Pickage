"""Runner integration for the opt-in weighted receipt and resume contract."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import duckdb

from pipeline.requirements_resolution.input import file_sha256
from .historical_production import (DEFAULT_ALGORITHM, WEIGHTED_ALGORITHM,
                                    WEIGHTED_FORMAT, contract, run, verify_run)
from .test_historical_production import prepared_fixture


class WeightedProductionTests(unittest.TestCase):
    def test_weighted_partition_date_resume_and_legacy_value_equality(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            digest = prepared_fixture(root / "in")
            common = dict(prepared_dir=root / "in", manifest_sha256=digest, min_free_bytes=0)
            legacy = run(**common, output=root / "old")
            args = dict(**common, output=root / "new", algorithm=WEIGHTED_ALGORITHM)
            partial = run(**args, max_partitions=1)
            self.assertEqual(partial["run_status"], "INCOMPLETE")
            marker = next((root / "new" / "partitions").glob("*/complete.json"))
            marker_bytes = marker.read_bytes()
            second = run(**args, resume=True, max_snapshots=1)
            self.assertEqual(second["run_status"], "INCOMPLETE")
            self.assertEqual(marker.read_bytes(), marker_bytes)
            with self.assertRaisesRegex(ValueError, "plan|changed|differs"):
                run(**common, output=root / "new", resume=True, algorithm=DEFAULT_ALGORITHM)
            result = run(**args, resume=True)
            self.assertEqual(result["run_status"], "COMPLETE")
            self.assertFalse(result["ready_for_load"])
            self.assertTrue(verify_run(run_dir=root / "new", manifest_sha256=result["run_manifest_sha256"])["verified"])
            self.assertEqual(json.loads((root / "new" / "run_plan.json").read_bytes())["format"], WEIGHTED_FORMAT)
            receipt = json.loads((marker.parent / json.loads(marker_bytes)["attempt"] / "receipt.json").read_bytes())
            self.assertEqual({f["name"] for f in receipt["files"]}, {
                "lookup_intervals.parquet", "counts.parquet", "source_summary.parquet", "status_deltas.parquet"})
            with duckdb.connect() as con:
                for name in ("quality", "target_population"):
                    old = con.execute("SELECT * FROM read_parquet(?) ORDER BY ALL", [str(Path(legacy["cache_dir"]) / (name + ".parquet"))]).fetchall()
                    new = con.execute("SELECT * FROM read_parquet(?) ORDER BY ALL", [str(Path(result["cache_dir"]) / (name + ".parquet"))]).fetchall()
                    self.assertEqual(old, new)
                for index in range(3):
                    def counts(cache):
                        return con.execute("""SELECT package_id,version,dependents_count FROM read_parquet(?)
                            WHERE start_index<=? AND ?<end_index ORDER BY 1,2""",
                            [str(Path(cache) / "count_intervals.parquet"), index, index]).fetchall()
                    self.assertEqual(counts(legacy["cache_dir"]), counts(result["cache_dir"]))
            again = run(**args, resume=True)
            self.assertEqual(again["run_manifest_sha256"], result["run_manifest_sha256"])
            self.assertEqual(again["written_partitions"], [])
            summary = marker.parent / json.loads(marker_bytes)["attempt"] / "source_summary.parquet"
            summary.write_bytes(summary.read_bytes() + b"changed")
            with self.assertRaises(ValueError):
                run(**args, resume=True)

    def test_mapping_validation_precedes_any_partition_resolution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            digest = prepared_fixture(root / "in")
            with patch("pipeline.version_dependents.historical_production_events.validate_weighted_inputs",
                       side_effect=ValueError("global target mapping conflict")) as validate, \
                 patch("pipeline.version_dependents.historical_production._resolve_partition") as resolve:
                with self.assertRaisesRegex(ValueError, "global target mapping"):
                    run(prepared_dir=root / "in", manifest_sha256=digest, output=root / "run",
                        algorithm=WEIGHTED_ALGORITHM, min_free_bytes=0)
                validate.assert_called_once()
                resolve.assert_not_called()

    def test_weighted_generation_pins_both_new_modules(self):
        generation = contract(WEIGHTED_ALGORITHM)
        self.assertEqual(generation["algorithm"], WEIGHTED_ALGORITHM)
        for key, name in (("weighted_events_sha256", "historical_production_events.py"),
                          ("weighted_quality_sha256", "historical_production_quality.py")):
            self.assertEqual(generation[key], file_sha256(Path(__file__).with_name(name)))
        with self.assertRaisesRegex(ValueError, "algorithm"):
            contract("typo")


if __name__ == "__main__":
    unittest.main()
