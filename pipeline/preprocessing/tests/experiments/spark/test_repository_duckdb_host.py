import json
import unittest
from unittest.mock import patch

from pipeline.preprocessing.experiments.spark.runtime import repository_duckdb_host as subject


class RepositoryDuckDBHostTests(unittest.TestCase):
    def test_abba_schedule_is_explicit(self):
        self.assertEqual(subject.TRIALS, ("spark-1", "duckdb-1", "duckdb-2", "spark-2"))

    def test_preflight_is_read_only_and_reports_caps(self):
        with patch.object(subject.socket, "gethostname", return_value="ip-172-26-8-249"), \
             patch.object(subject, "_sha", return_value=subject.MANIFEST_SHA), \
             patch.object(subject.host, "command", return_value="pickage-data-mlflow-1\npickage-data-minio-1"), \
             patch.object(subject.weekly_priority, "observe", return_value={"phase": "downloads_weekly"}), \
             patch.object(subject.weekly_priority, "violation", return_value=None), \
             patch.object(subject.profile, "preflight", return_value={"status": "READY", "code_files_sha256": {}}), \
             patch.object(subject.shutil, "disk_usage", return_value=type("Usage", (), {"free": 40 * 1024**3})()), \
             patch.object(subject.Path, "is_file", return_value=True), \
             patch.object(subject.Path, "read_bytes", return_value=b'{"sample":{"package_rows":1000},"input_identity":"id"}'):
            result = subject.preflight()
        self.assertEqual(result["status"], "READY")
        self.assertEqual(result["container_cpu_limit"], 2)
        self.assertEqual(result["container_memory_mib"], 7680)
        self.assertEqual(result["engine_memory"], "4GB")

    def test_phase_uses_loopback_network_and_resource_cap(self):
        supervisor = subject.WeeklyPrioritySupervisor({"phase": "downloads_weekly"})
        supervisor.result = {"phases": {}}
        captured = {}
        state = {"Running": False, "ExitCode": 0, "OOMKilled": False}
        with patch.object(supervisor, "start", side_effect=lambda *args, **kwargs: captured.update(kwargs) or "cid"), \
             patch.object(supervisor, "check"), patch.object(supervisor, "finish", return_value=state), \
             patch.object(subject.host, "save"), patch.object(subject.host, "command", return_value=json.dumps(state)):
            supervisor.phase("spark-1", ["python3", "-m", "entry", "run"])
        self.assertEqual(captured["network"], "none")
        self.assertIn("--hostname", captured["extra"])
        self.assertIn("--add-host", captured["extra"])

    def test_entry_contract_contains_run_and_compare_subcommands(self):
        source = subject.Path(__file__).parents[5] / "pipeline/preprocessing/experiments/spark/runtime/repository_duckdb_host.py"
        text = source.read_text(encoding="utf-8")
        self.assertIn('"run", "--engine"', text)
        self.assertIn('"compare", "--trials"', text)


if __name__ == "__main__": unittest.main()
