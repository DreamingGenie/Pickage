"""Independent process lifecycle and resource-limit tests for H5-A."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from pipeline.requirements_resolution.input import file_sha256
from pipeline.requirements_resolution.policy import canonical_bytes
from .historical_job import supervise, _memory, _worker_python, _worker_environment


class HistoricalJobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="h5-job-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / "config.json"
        self.settings = {"format": "historical-profile-job-v1", "job_dir": str(self.root),
                         "profile_args": {"input_dir": "unused", "input_manifest_sha256": "a" * 64,
                                          "threads": 1, "memory_limit": "256MB", "max_temp_size": "1GB"},
                         "budget": {"max_rss_bytes": 1024**3, "max_scratch_bytes": 1024**3,
                                    "max_output_bytes": 1024**3, "min_free_disk_bytes": 1024**3,
                                    "max_seconds": 10, "sample_seconds": 1}}
        self.config.write_bytes(canonical_bytes(self.settings))

    def run_child(self, code):
        script = self.root / "fixture_child.py"
        script.write_text(code, encoding="utf-8")
        with patch("pipeline.version_dependents.historical_job._command", return_value=[_worker_python(), "-B", str(script)]):
            return supervise(config=self.config, config_sha256=file_sha256(self.config))

    def test_real_process_memory_and_success_receipt(self):
        child = subprocess.Popen([_worker_python(), "-B", "-c", "import time; time.sleep(10)"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            self.assertGreater(_memory(child)["rss_bytes"], 0)
        finally:
            child.terminate()
            child.wait(timeout=10)
        code = """from pathlib import Path
import json, hashlib
p=Path(__file__).parent/'profile'
p.mkdir()
m={'profile_status':'COMPLETE','count_status':'NOT_COMPUTED'}
f=p/'profile_manifest.json';f.write_text(json.dumps(m))
(p/'result.json').write_text(json.dumps({'output':str(p),'profile_status':'COMPLETE','count_status':'NOT_COMPUTED','ready_for_load':False,'manifest_sha256':hashlib.sha256(f.read_bytes()).hexdigest()}))
"""
        result = self.run_child(code)
        self.assertEqual(result["status"], "COMPLETE", result)
        self.assertEqual(result, json.loads((self.root / "status.json").read_bytes()))
        with self.assertRaisesRegex(ValueError, "already started"):
            supervise(config=self.config, config_sha256=file_sha256(self.config))

    def test_nonzero_exit_is_failed(self):
        result = self.run_child("raise SystemExit(7)")
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["exit_code"], 7)

    def test_zero_exit_without_completion_receipt_is_failed(self):
        result = self.run_child("pass")
        self.assertEqual(result["status"], "FAILED")

    def test_deadline_terminates_only_owned_child(self):
        self.settings["budget"]["max_seconds"] = 1
        self.config.write_bytes(canonical_bytes(self.settings))
        result = self.run_child("import time; time.sleep(30)")
        self.assertEqual(result["status"], "BUDGET_EXCEEDED")
        self.assertEqual(result["reason"], "elapsed time")
        self.assertIsNotNone(result["exit_code"])
        self.assertLess(result["elapsed_seconds"], 10)

    def test_null_deadline_allows_real_child_to_finish_past_one_hour(self):
        self.settings["budget"]["max_seconds"] = None
        self.config.write_bytes(canonical_bytes(self.settings))
        real_monotonic = time.monotonic
        started = real_monotonic()
        clock_calls = 0

        def advanced_clock():
            nonlocal clock_calls
            clock_calls += 1
            return real_monotonic() - started + (0 if clock_calls == 1 else 7200)

        code = """from pathlib import Path
import json, hashlib, time
time.sleep(1.2)
p=Path(__file__).parent/'profile';p.mkdir()
m={'profile_status':'COMPLETE','count_status':'NOT_COMPUTED'}
f=p/'profile_manifest.json';f.write_text(json.dumps(m))
(p/'result.json').write_text(json.dumps({'output':str(p),'profile_status':'COMPLETE','count_status':'NOT_COMPUTED','ready_for_load':False,'manifest_sha256':hashlib.sha256(f.read_bytes()).hexdigest()}))
"""
        with patch("pipeline.version_dependents.historical_job.time.monotonic", side_effect=advanced_clock):
            result = self.run_child(code)
        self.assertEqual(result["status"], "COMPLETE", result)
        self.assertGreater(result["elapsed_seconds"], 3600)
        self.assertGreaterEqual(result["memory_samples"], 2)
        self.assertIsNone(result["budget"]["max_seconds"])
        self.assertFalse(result["elapsed_limit_enforced"])
        receipt = json.loads((self.root / "job_receipt.json").read_bytes())
        self.assertIsNone(receipt["budget"]["max_seconds"])
        self.assertEqual(receipt["exit_code"], 0)

    def test_invalid_or_missing_deadline_does_not_launch(self):
        for value in (0, -1, True, False, "unlimited", 1.5, "missing"):
            with self.subTest(value=value):
                if value == "missing":
                    self.settings["budget"].pop("max_seconds", None)
                else:
                    self.settings["budget"]["max_seconds"] = value
                self.config.write_bytes(canonical_bytes(self.settings))
                with patch("pipeline.version_dependents.historical_job.subprocess.Popen") as launch:
                    with self.assertRaises(ValueError):
                        supervise(config=self.config, config_sha256=file_sha256(self.config))
                    launch.assert_not_called()
                self.assertFalse((self.root / "status.json").exists())

    def test_null_resource_limit_is_not_an_unlimited_deadline(self):
        self.settings["budget"]["max_seconds"] = None
        self.settings["budget"]["max_rss_bytes"] = None
        self.config.write_bytes(canonical_bytes(self.settings))
        with self.assertRaises(ValueError):
            supervise(config=self.config, config_sha256=file_sha256(self.config))
        self.assertFalse((self.root / "status.json").exists())

    def test_rss_limit_terminates_child(self):
        self.settings["budget"]["max_seconds"] = None
        self.config.write_bytes(canonical_bytes(self.settings))
        with patch("pipeline.version_dependents.historical_job._memory",
                   return_value={"rss_bytes": 2 * 1024**3, "os_peak_rss_bytes": 2 * 1024**3, "private_bytes": 0}):
            result = self.run_child("import time; time.sleep(30)")
        self.assertEqual(result["status"], "BUDGET_EXCEEDED")
        self.assertEqual(result["reason"], "process RSS")

    def test_bad_config_pin_does_not_launch(self):
        with self.assertRaisesRegex(ValueError, "identity"):
            supervise(config=self.config, config_sha256="0" * 64)
        self.assertFalse((self.root / "status.json").exists())

    def test_output_limit_is_enforced(self):
        self.settings["budget"]["max_output_bytes"] = 10
        self.config.write_bytes(canonical_bytes(self.settings))
        result = self.run_child("from pathlib import Path\nimport time\np=Path(__file__).parent/'profile';p.mkdir();(p/'large.bin').write_bytes(b'x'*1024);time.sleep(30)")
        self.assertEqual(result["status"], "BUDGET_EXCEEDED")
        self.assertEqual(result["reason"], "output size")

    def test_corrupt_completion_hash_is_failed(self):
        code="""from pathlib import Path
import json
p=Path(__file__).parent/'profile';p.mkdir()
(p/'profile_manifest.json').write_text('{}')
(p/'result.json').write_text(json.dumps({'output':str(p),'profile_status':'COMPLETE','count_status':'NOT_COMPUTED','ready_for_load':False,'manifest_sha256':'0'*64}))
"""
        result=self.run_child(code)
        self.assertEqual(result["status"], "FAILED")
        self.assertIn("receipt mismatch",result["reason"])

    def test_engine_limits_cannot_exceed_supervisor_budget(self):
        self.settings["profile_args"]["max_temp_size"] = "2GB"
        self.config.write_bytes(canonical_bytes(self.settings))
        with self.assertRaisesRegex(ValueError, "Engine limits"):
            supervise(config=self.config, config_sha256=file_sha256(self.config))
        self.assertFalse((self.root / "status.json").exists())

    def test_forced_supervisor_exit_stops_guarded_worker(self):
        repository = Path(__file__).resolve().parents[2]
        child_code = """import os, time, sys
from pathlib import Path
sys.path.insert(0, REPOSITORY)
from pipeline.version_dependents.historical_job import _start_parent_guard
job=Path(__file__).parent
_start_parent_guard(os.getppid(),job)
(job/'guard_ready').write_text(str(os.getpid()))
time.sleep(60)
""".replace("REPOSITORY", repr(str(repository)))
        sleeper=self.root/'guarded.py';sleeper.write_text(child_code,encoding='utf-8')
        parent_code="""import subprocess, sys, time
from pathlib import Path
subprocess.Popen([sys.executable,'-B',str(Path(__file__).parent/'guarded.py')])
time.sleep(60)
"""
        parent_path=self.root/'parent.py';parent_path.write_text(parent_code,encoding='utf-8')
        (self.root/'status.json').write_bytes(canonical_bytes({'status':'RUNNING'}))
        parent=subprocess.Popen([_worker_python(),'-B',str(parent_path)],stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,env=_worker_environment())
        try:
            deadline=time.monotonic()+10
            while not (self.root/'guard_ready').exists() and time.monotonic()<deadline:
                time.sleep(.1)
            self.assertTrue((self.root/'guard_ready').exists())
            parent.terminate();parent.wait(timeout=10)
            deadline=time.monotonic()+10
            while not (self.root/'supervisor_lost.json').exists() and time.monotonic()<deadline:
                time.sleep(.1)
            state=json.loads((self.root/'supervisor_lost.json').read_bytes())
            self.assertEqual(state['status'],'FAILED')
            self.assertEqual(state['reason'],'SUPERVISOR_LOST')
        finally:
            if parent.poll() is None:
                parent.terminate();parent.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
