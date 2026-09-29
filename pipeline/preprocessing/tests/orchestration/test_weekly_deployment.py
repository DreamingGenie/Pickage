"""Exercise production shell control flow with fake Docker and flock, no daemon."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from pipeline.preprocessing.common.paths import REPO_ROOT


@unittest.skipUnless(os.name == "posix", "POSIX shell control flow; run in the Curated runtime image")
class WeeklyDeploymentTests(unittest.TestCase):
    def invoke(self, script="run-weekly-ingest.sh", args=(), **settings):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "deploy/prod/data"
            target.mkdir(parents=True)
            (root / "pipeline/minio").mkdir(parents=True)
            (root / "pipeline/minio/.env.data").touch()
            (target / ".env").touch()
            for name in ("run-weekly-ingest.sh", "run-curated-retry.sh"):
                body = (REPO_ROOT / "deploy/prod/data" / name).read_text()
                (target / name).write_text(body.replace("/tmp/pickage-weekly.lock", str(root / "weekly.lock")))
            binary = root / "bin"
            binary.mkdir()
            (binary / "flock").write_text('#!/bin/sh\nexit "${LOCK_STATUS:-0}"\n')
            (binary / "docker").write_text('''#!/bin/sh
echo "$*" >> "$CALL_LOG"
case "$*" in
  *"compose run"*"ingest-weekly"*) exit "${INGEST_STATUS:-0}" ;;
  *"compose run"*"curated-dispatch"*) exit "${CURATED_STATUS:-0}" ;;
esac
exit 0
''')
            for path in binary.iterdir():
                path.chmod(0o755)
            log = root / "calls"
            env = {**os.environ, "PATH": str(binary) + ":" + os.environ["PATH"],
                   "CALL_LOG": str(log), **settings}
            completed = subprocess.run(["sh", str(target / script), *args], env=env, capture_output=True, text=True)
            return completed.returncode, log.read_text().splitlines() if log.exists() else []

    def test_ingest_failure_still_runs_curated_and_retains_failure(self):
        code, calls = self.invoke(INGEST_STATUS="7")
        self.assertEqual(code, 7)
        runs = [call for call in calls if call.startswith("compose")]
        self.assertEqual(len(runs), 2)
        self.assertTrue(runs[0].endswith("ingest-weekly"))
        self.assertTrue(runs[1].endswith("curated-dispatch"))

    def test_curated_failure_is_propagated(self):
        self.assertEqual(self.invoke(CURATED_STATUS="2")[0], 2)

    def test_diagnostics_never_invoke_curated(self):
        for args in (("--dry-run",), ("--only", "gcs_sync")):
            with self.subTest(args=args):
                code, calls = self.invoke(args=args)
                self.assertEqual(code, 0)
                runs = [call for call in calls if call.startswith("compose")]
                self.assertEqual(len(runs), 1)
                self.assertIn("ingest-weekly", runs[0])

    def test_lock_contention_does_not_even_cleanup(self):
        self.assertEqual(self.invoke(LOCK_STATUS="1"), (0, []))

    def test_manual_retry_uses_lock_and_cleans_both_orphans(self):
        code, calls = self.invoke("run-curated-retry.sh", ("--retry-snapshot", "2026-09-14"))
        self.assertEqual(code, 0)
        self.assertIn("rm -f pickage-weekly-run", calls)
        self.assertIn("rm -f pickage-curated-dispatch", calls)
        self.assertEqual(len([call for call in calls if call.startswith("compose")]), 1)
        self.assertTrue(calls[-1].endswith("curated-dispatch --retry-snapshot 2026-09-14"))


if __name__ == "__main__":
    unittest.main()
