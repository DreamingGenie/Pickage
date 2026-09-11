"""Independent H4 publication-anchor and process-lock regression tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest

import duckdb

from pipeline.requirements_resolution.input import file_sha256
from pipeline.requirements_resolution.policy import canonical_bytes
from .historical_artifact import _file_info, _run_lock, build_history, verify_history
from .historical_cache import create_fixture_cache
from .test_historical_reference import reference_fixture


class HistoricalPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="historical-publication-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = self.root / "fixture.json"
        self.fixture.write_bytes(canonical_bytes(reference_fixture()))
        cache = create_fixture_cache(self.fixture, self.root / "cache")
        self.cache_dir = Path(cache["cache_dir"])
        self.cache_sha = cache["manifest_sha256"]

    def _build(self, output: Path | None = None):
        return build_history(
            cache_dir=self.cache_dir,
            cache_sha256=self.cache_sha,
            output=output or self.root / "run",
        )

    def test_lock_is_released_after_child_process_termination(self):
        run_dir = self.root / "process-lock"
        ready = self.root / "child-ready"
        script = textwrap.dedent(
            """
            import sys
            import time
            from pathlib import Path
            from pipeline.version_dependents.historical_artifact import _run_lock

            run = Path(sys.argv[1])
            marker = Path(sys.argv[2])
            run.mkdir(parents=True, exist_ok=False)
            with _run_lock(run):
                marker.write_text("ready", encoding="ascii")
                time.sleep(60)
            """
        )
        child = subprocess.Popen(
            [sys.executable, "-B", "-c", script, str(run_dir), str(ready)],
            cwd=Path.cwd(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            deadline = time.monotonic() + 5
            while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(ready.exists(), child.stderr.read() if child.poll() is not None else "child did not acquire lock")
            child.terminate()
            child.wait(timeout=5)
            with _run_lock(run_dir):
                acquired = self.root / "parent-acquired"
                acquired.write_text("ok", encoding="ascii")
            self.assertEqual(acquired.read_text(encoding="ascii"), "ok")
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
            if child.stdout is not None:
                child.stdout.close()
            if child.stderr is not None:
                child.stderr.close()

    def test_completion_anchor_rejects_path_escape(self):
        output = self.root / "anchor-escape"
        result = self._build(output)
        marker = output / "snapshot=2026-08-30" / "complete.json"
        anchor = json.loads(marker.read_bytes())
        anchor["attempt_id"] = "../outside"
        marker.write_bytes(canonical_bytes(anchor))
        with self.assertRaisesRegex(ValueError, "completion marker identity mismatch"):
            verify_history(
                run_dir=output,
                cache_dir=self.cache_dir,
                cache_sha256=self.cache_sha,
                run_manifest_sha256=result["run_manifest_sha256"],
            )

    def test_rehashed_snapshot_files_cannot_override_pinned_cache(self):
        output = self.root / "rehash"
        result = self._build(output)
        attempt = next((output / "snapshot=2026-08-30" / "attempts").iterdir())
        counts = attempt / "counts.parquet"
        changed = attempt / "counts.parquet.tmp"
        with duckdb.connect() as con:
            con.execute(
                """CREATE TABLE changed AS SELECT package_id::INTEGER AS package_id,
                   version::VARCHAR AS version, snapshot_at::DATE AS snapshot_at,
                   snapshot_timestamp::TIMESTAMPTZ AS snapshot_timestamp,
                   dependents_count::INTEGER AS dependents_count FROM read_parquet(?)""",
                [str(counts)],
            )
            con.execute("UPDATE changed SET dependents_count = dependents_count + 1 WHERE rowid = 1")
            con.execute("COPY changed TO ? (FORMAT PARQUET, COMPRESSION ZSTD)", [str(changed)])
        os.replace(changed, counts)

        snapshot_manifest_path = attempt / "snapshot_manifest.json"
        snapshot_manifest = json.loads(snapshot_manifest_path.read_bytes())
        with duckdb.connect() as con:
            snapshot_manifest["files"]["counts.parquet"] = _file_info(con, counts)
        snapshot_manifest_path.write_bytes(canonical_bytes(snapshot_manifest))
        anchor_path = output / "snapshot=2026-08-30" / "complete.json"
        anchor = json.loads(anchor_path.read_bytes())
        anchor["manifest_sha256"] = file_sha256(snapshot_manifest_path)
        anchor_path.write_bytes(canonical_bytes(anchor))

        with self.assertRaisesRegex(ValueError, "Snapshot values differ from pinned cache"):
            build_history(
                cache_dir=self.cache_dir,
                cache_sha256=self.cache_sha,
                output=output,
                resume=True,
            )


if __name__ == "__main__":
    unittest.main()
