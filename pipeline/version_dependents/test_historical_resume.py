"""H4 snapshot artifact lifecycle: sparse Parquet output and safe resume."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import duckdb

from .test_historical_reference import reference_fixture
from .historical_cache import create_fixture_cache
from .historical_artifact import build_history, verify_history


class HistoricalResumeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="historical-resume-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = self.root / "fixture.json"
        self.fixture.write_text(json.dumps(reference_fixture()), encoding="utf-8")
        cache = create_fixture_cache(self.fixture, self.root / "cache")
        self.cache_dir = Path(cache["cache_dir"])
        self.cache_sha = cache["manifest_sha256"]

    def build(self, output=None, **kwargs):
        return build_history(cache_dir=self.cache_dir, cache_sha256=self.cache_sha,
                             output=output or self.root / "run", **kwargs)

    def test_complete_run_writes_one_snapshot_bundle_and_sparse_counts(self):
        result = self.build()
        self.assertEqual(result["run_status"], "COMPLETE")
        self.assertEqual(len(result["completed_dates"]), 2)
        self.assertEqual(result["pending_dates"], [])
        run = Path(result["run_dir"])
        self.assertTrue((run / "run_plan.json").is_file())
        self.assertTrue((run / "run_manifest.json").is_file())
        self.assertTrue((run / "snapshot=2026-08-30" / "complete.json").exists())
        # The contract uses snapshot=YYYY-MM-DD directories and Parquet, not a
        # single giant relationship file.
        snapshot_dirs = sorted(run.glob("snapshot=*") )
        self.assertEqual(len(snapshot_dirs), 2)
        with duckdb.connect() as con:
            rows = con.execute(
                "SELECT package_id, version, dependents_count "
                "FROM read_parquet(?) ORDER BY package_id, version",
                [str(snapshot_dirs[-1] / "attempts" / next(snapshot_dirs[-1].glob("attempts/*")).name / "counts.parquet")],
            ).fetchall()
        self.assertTrue(rows)
        self.assertTrue(all(row[2] > 0 for row in rows))
        with duckdb.connect() as con:
            quality = con.execute(
                "SELECT resolution_status FROM read_parquet(?)",
                [str(snapshot_dirs[-1] / "attempts" / next(snapshot_dirs[-1].glob("attempts/*")).name / "quality.parquet")],
            ).fetchone()[0]
        self.assertEqual(quality, "PARTIAL")
        checked = verify_history(run_dir=run, cache_dir=self.cache_dir,
                                 cache_sha256=self.cache_sha,
                                 run_manifest_sha256=result["run_manifest_sha256"])
        self.assertEqual(checked["run_status"], "COMPLETE")

    def test_max_snapshots_then_resume_reuses_completed_snapshot(self):
        output = self.root / "resumable"
        first = self.build(output, max_snapshots=1)
        self.assertEqual(first["run_status"], "INCOMPLETE")
        self.assertEqual(first["completed_dates"], ["2026-08-30"])
        first_snapshot = output / "snapshot=2026-08-30"
        before = {p.relative_to(first_snapshot): p.stat().st_mtime_ns
                  for p in first_snapshot.rglob("*") if p.is_file()}
        resumed = self.build(output, resume=True)
        self.assertEqual(resumed["run_status"], "COMPLETE")
        self.assertEqual(resumed["reused_dates"], ["2026-08-30"])
        after = {p.relative_to(first_snapshot): p.stat().st_mtime_ns
                 for p in first_snapshot.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_complete_rerun_is_read_only(self):
        output = self.root / "complete"
        first = self.build(output)
        tracked = {p.relative_to(output): (p.stat().st_mtime_ns, p.read_bytes())
                   for p in output.rglob("*") if p.is_file()}
        second = self.build(output, resume=True)
        self.assertEqual(second["run_status"], "COMPLETE")
        self.assertEqual(second["reused_dates"], ["2026-08-30", "2026-08-31"])
        self.assertEqual(tracked, {p.relative_to(output): (p.stat().st_mtime_ns, p.read_bytes())
                                   for p in output.rglob("*") if p.is_file()})

    def test_failed_attempt_is_preserved_and_never_published_complete(self):
        output = self.root / "failed"
        import pipeline.version_dependents.historical_artifact as artifact
        calls = {"n": 0}
        original_publish = artifact._publish_json
        def fail_second_completion(path, body):
            if Path(path).name == "complete.json":
                calls["n"] += 1
                if calls["n"] == 2:
                    raise RuntimeError("injected completion publication failure")
            return original_publish(path, body)
        with patch.object(artifact, "_publish_json", side_effect=fail_second_completion):
            with self.assertRaises(RuntimeError):
                self.build(output)
        second = output / "snapshot=2026-08-31"
        self.assertTrue(list(second.glob("attempts/*/snapshot_manifest.json")))
        self.assertFalse((second / "complete.json").exists())
        self.assertFalse((output / "run_manifest.json").exists())
        resumed = self.build(output, resume=True)
        self.assertEqual(resumed["run_status"], "COMPLETE")

    def test_parquet_tamper_or_missing_file_is_rejected(self):
        output = self.root / "parquet-tamper"
        result = self.build(output)
        attempt = next((output / "snapshot=2026-08-31" / "attempts").iterdir())
        counts = attempt / "counts.parquet"
        original = counts.read_bytes()
        counts.write_bytes(original + b"tamper")
        with self.assertRaises(Exception):
            verify_history(run_dir=output, cache_dir=self.cache_dir,
                           cache_sha256=self.cache_sha,
                           run_manifest_sha256=result["run_manifest_sha256"])
        counts.write_bytes(original)
        (attempt / "quality.parquet").unlink()
        with self.assertRaises(Exception):
            verify_history(run_dir=output, cache_dir=self.cache_dir,
                           cache_sha256=self.cache_sha,
                           run_manifest_sha256=result["run_manifest_sha256"])

    def test_writer_contract_change_is_rejected(self):
        import pipeline.version_dependents.historical_artifact as artifact
        output = self.root / "contract"
        result = self.build(output)
        with patch.object(artifact, "_contract", return_value={"writer_sha256": "changed"}):
            with self.assertRaises(Exception):
                verify_history(run_dir=output, cache_dir=self.cache_dir,
                               cache_sha256=self.cache_sha,
                               run_manifest_sha256=result["run_manifest_sha256"])

    def test_cli_verify_works_in_a_separate_process(self):
        output = self.root / "cli"
        result = self.build(output)
        command = [sys.executable, "-B", "-m", "pipeline.version_dependents.historical_artifact",
                   "verify", "--run-dir", str(output), "--cache-dir", str(self.cache_dir),
                   "--cache-sha256", self.cache_sha,
                   "--run-manifest-sha256", result["run_manifest_sha256"]]
        completed = subprocess.run(command, cwd=Path.cwd(), capture_output=True, text=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["run_status"], "COMPLETE")

    def test_tampered_cache_and_wrong_manifest_are_rejected(self):
        output = self.root / "tamper"
        result = self.build(output)
        cache_manifest = self.cache_dir / "cache_manifest.json"
        original = cache_manifest.read_bytes()
        cache_manifest.write_bytes(original + b"\n")
        with self.assertRaisesRegex(ValueError, "manifest SHA"):
            verify_history(run_dir=output, cache_dir=self.cache_dir, cache_sha256=self.cache_sha,
                           run_manifest_sha256=result["run_manifest_sha256"])

    def test_single_writer_lock_rejects_second_owner(self):
        import pipeline.version_dependents.historical_artifact as artifact
        run = self.root / "locked"
        run.mkdir()
        with artifact._run_lock(run):
            with self.assertRaises(Exception):
                with artifact._run_lock(run):
                    pass

    def test_fixture_with_no_published_targets_writes_empty_counts(self):
        fixture = reference_fixture()
        for version in fixture["versions"]:
            version["published_at"] = None
        self.fixture.write_text(json.dumps(fixture), encoding="utf-8")
        cache = create_fixture_cache(self.fixture, self.root / "nested" / "empty-cache")
        result = build_history(cache_dir=cache["cache_dir"], cache_sha256=cache["manifest_sha256"],
                               output=self.root / "empty-run")
        checked = verify_history(run_dir=result["run_dir"], cache_dir=cache["cache_dir"],
                                 cache_sha256=cache["manifest_sha256"],
                                 run_manifest_sha256=result["run_manifest_sha256"])
        self.assertEqual(checked["snapshots_verified"], 2)
        with duckdb.connect() as con:
            for path in (self.root / "empty-run").rglob("counts.parquet"):
                self.assertEqual(con.execute("SELECT count(*) FROM read_parquet(?)", [str(path)]).fetchone()[0], 0)

    def test_oversized_fixture_is_rejected_before_output(self):
        self.fixture.write_bytes(b" " * (4 * 1024 * 1024 + 1))
        output = self.root / "oversized-cache"
        with self.assertRaisesRegex(ValueError, "4 MiB"):
            create_fixture_cache(self.fixture, output)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
