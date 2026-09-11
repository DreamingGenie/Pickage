"""Regression tests for the optimized historical production writer."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import duckdb

from pipeline.requirements_resolution.policy import canonical_bytes
from pipeline.requirements_resolution.input import file_sha256
from . import historical_artifact as base
from . import historical_production_daily as daily
from .historical_cache import create_fixture_cache
from .historical_production_writer import build_history, verify_history
from .test_historical_reference import reference_fixture


class HistoricalProductionWriterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="historical-production-writer-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        fixture = copy.deepcopy(reference_fixture())
        fixture["observed_snapshot_timestamp"] = "2026-09-01T00:00:00.000000Z"
        fixture["calendar"].append({
            "snapshot_at": "2026-09-01",
            "snapshot_timestamp": "2026-09-01T00:00:00.000000Z",
        })
        self.fixture = self.root / "fixture.json"
        self.fixture.write_bytes(canonical_bytes(fixture))
        cache = create_fixture_cache(self.fixture, self.root / "cache")
        self.cache_dir = Path(cache["cache_dir"])
        self.cache_sha = cache["manifest_sha256"]

    def _build(self, output: Path, **kwargs):
        return build_history(cache_dir=self.cache_dir, cache_sha256=self.cache_sha,
                             output=output, **kwargs)

    @staticmethod
    def _attempt(run_dir: Path, day: str) -> Path:
        marker = json.loads((run_dir / f"snapshot={day}" / "complete.json").read_bytes())
        return run_dir / f"snapshot={day}" / "attempts" / marker["attempt_id"]

    @staticmethod
    def _change_counts(path: Path) -> None:
        temporary = path.with_name(path.name + ".tmp")
        with duckdb.connect() as con:
            con.execute("CREATE TABLE changed AS SELECT * FROM read_parquet(?,hive_partitioning=false)", [str(path)])
            con.execute("UPDATE changed SET dependents_count = dependents_count + 1 WHERE rowid = 1")
            con.execute("COPY changed TO ? (FORMAT PARQUET, COMPRESSION ZSTD)", [str(temporary)])
        os.replace(temporary, path)

    def test_fresh_three_days_validate_each_snapshot_once(self):
        output = self.root / "fresh"
        with patch.object(daily, "_verify_snapshot", wraps=daily._verify_snapshot) as checked:
            result = self._build(output)
        self.assertEqual(result["run_status"], "COMPLETE")
        self.assertEqual(checked.call_count, 3)

    def test_old_writer_baseline_keeps_duplicate_validation_evidence(self):
        output = self.root / "old"
        with patch.object(base, "_verify_snapshot", wraps=base._verify_snapshot) as checked:
            result = base.build_history(cache_dir=self.cache_dir, cache_sha256=self.cache_sha,
                                        output=output)
        self.assertEqual(result["run_status"], "COMPLETE")
        self.assertEqual(checked.call_count, 6)

    def test_resume_verifies_existing_and_new_snapshot_once(self):
        output = self.root / "resume"
        self._build(output, max_snapshots=1)
        with patch.object(daily, "_verify_snapshot", wraps=daily._verify_snapshot) as checked:
            result = self._build(output, resume=True, max_snapshots=1)
        self.assertEqual(result["run_status"], "INCOMPLETE")
        self.assertEqual(checked.call_count, 2)
        self.assertEqual(result["reused_dates"], ["2026-08-30"])
        self.assertEqual(result["written_dates"], ["2026-08-31"])

    def test_published_count_and_quality_values_match_old_writer(self):
        old_dir, new_dir = self.root / "old", self.root / "new"
        old = base.build_history(cache_dir=self.cache_dir, cache_sha256=self.cache_sha,
                                 output=old_dir)
        new = self._build(new_dir)
        self.assertEqual(old["run_status"], new["run_status"])
        self.assertEqual(old["completed_dates"], new["completed_dates"])
        for day in old["completed_dates"]:
            old_attempt = self._attempt(old_dir, day)
            new_attempt = self._attempt(new_dir, day)
            self.assertEqual(file_sha256(old_attempt / "counts.parquet"),
                             file_sha256(new_attempt / "counts.parquet"),
                             f"published {day}/counts.parquet")
            with duckdb.connect() as con:
                old_quality = con.execute("SELECT quality_json FROM read_parquet(?)",
                                          [str(old_attempt / "quality.parquet")]).fetchone()
                new_quality = con.execute("SELECT quality_json FROM read_parquet(?)",
                                          [str(new_attempt / "quality.parquet")]).fetchone()
            self.assertEqual(old_quality, new_quality, f"published {day}/quality.parquet")

    def test_corrupt_output_before_completion_marker_refuses_completion(self):
        output = self.root / "corrupt"
        original = daily._verify_snapshot

        def verify_then_corrupt(*args, **kwargs):
            manifest = original(*args, **kwargs)
            self._change_counts(Path(args[1]) / "counts.parquet")
            return manifest

        with patch.object(daily, "_verify_snapshot", side_effect=verify_then_corrupt):
            with self.assertRaisesRegex(ValueError, "Snapshot file"):
                self._build(output)
        self.assertFalse((output / "snapshot=2026-08-30" / "complete.json").exists())

    def test_tampered_completed_parquet_is_rejected_on_resume_and_verify(self):
        output = self.root / "tampered"
        result = self._build(output)
        counts = self._attempt(output, "2026-08-30") / "counts.parquet"
        self._change_counts(counts)
        with self.assertRaisesRegex(ValueError, "Snapshot file"):
            self._build(output, resume=True)
        with self.assertRaisesRegex(ValueError, "Snapshot file"):
            verify_history(run_dir=output, cache_dir=self.cache_dir, cache_sha256=self.cache_sha,
                           run_manifest_sha256=result["run_manifest_sha256"])

    def test_changed_writer_identity_refuses_reuse(self):
        output = self.root / "identity"
        self._build(output, max_snapshots=1)
        plan_path = output / "run_plan.json"
        plan = json.loads(plan_path.read_bytes())
        plan["production_writer_sha256"] = "0" * 64
        plan_path.write_bytes(canonical_bytes(plan))
        with self.assertRaisesRegex(ValueError, "generation contract|code identity|writer"):
                self._build(output, resume=True)

    def test_daily_totals_built_once_for_all_dates_and_rebuilt_on_resume(self):
        output = self.root / "once"
        with patch.object(daily, "daily_totals", wraps=daily.daily_totals) as totals:
            self._build(output, max_snapshots=1)
            self.assertEqual(totals.call_count, 1)
        with patch.object(daily, "daily_totals", wraps=daily.daily_totals) as totals:
            result = self._build(output, resume=True)
            self.assertEqual(totals.call_count, 1)
            self.assertEqual(result["run_status"], "COMPLETE")

    def test_cache_changed_after_last_output_check_refuses_run_manifest(self):
        output = self.root / "cache-changed"
        original = daily._verify_snapshot

        def check_then_change_cache(*args, **kwargs):
            result = original(*args, **kwargs)
            if args[4] == 2:
                self._change_counts(self.cache_dir / "count_intervals.parquet")
            return result

        with patch.object(daily, "_verify_snapshot", side_effect=check_then_change_cache):
            with self.assertRaises(ValueError):
                self._build(output)
        self.assertFalse((output / "run_manifest.json").exists())

    def test_rehashed_wrong_output_values_are_still_rejected(self):
        output = self.root / "wrong-values"
        self._build(output, max_snapshots=1)
        day = output / "snapshot=2026-08-30"
        attempt = self._attempt(output, "2026-08-30")
        counts = attempt / "counts.parquet"
        self._change_counts(counts)
        manifest_path = attempt / "snapshot_manifest.json"
        manifest = json.loads(manifest_path.read_bytes())
        with duckdb.connect() as con:
            manifest["files"]["counts.parquet"] = base._file_info(con, counts)
        manifest_path.write_bytes(canonical_bytes(manifest))
        marker_path = day / "complete.json"
        marker = json.loads(marker_path.read_bytes())
        marker["manifest_sha256"] = file_sha256(manifest_path)
        marker_path.write_bytes(canonical_bytes(marker))
        with self.assertRaisesRegex(ValueError, "values differ"):
            self._build(output, resume=True)


if __name__ == "__main__":
    unittest.main()
