import json
import unittest
from unittest.mock import patch

from pipeline.spark_experiment.runtime import repository_duckdb10k_host as subject


class RepositoryDuckDBHostTests(unittest.TestCase):
    def test_abba_schedule_is_explicit(self):
        self.assertEqual(subject.TRIALS, ("spark-1", "duckdb-1", "duckdb-2", "spark-2"))

    def test_resource_policy_is_fixed(self):
        self.assertEqual(subject.MANIFEST_SHA, "2a2a733c505a30023570a67078074acb37ba8ed5659ff703f3e81e87b524f765")
        self.assertEqual(subject.SOURCE_RUN, "sample-ec2-20260916-a1")
        self.assertEqual(subject.DEST, "/experiment/repository-duckdb10000-20260917-a1")

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
        source = subject.Path(__file__).parents[1] / "pipeline/spark_experiment/runtime/repository_duckdb10k_host.py"
        text = source.read_text(encoding="utf-8")
        self.assertIn('"run", "--engine"', text)
        self.assertIn('"compare", "--trials"', text)


if __name__ == "__main__": unittest.main()
