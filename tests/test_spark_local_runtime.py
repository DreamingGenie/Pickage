from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "pipeline" / "spark_experiment" / "runtime"


class LocalSparkRuntimeTests(unittest.TestCase):
    def test_compose_is_opt_in_isolated_and_bounded(self):
        compose = (RUNTIME / "compose.local.yaml").read_text(encoding="utf-8")
        self.assertIn("${EXPERIMENT_IMAGE:?", compose)
        self.assertIn("internal: true", compose)
        self.assertIn("profiles: [smoke]", compose)
        self.assertEqual(compose.count("memswap_limit:"), 4)
        self.assertNotIn("ports:", compose)
        self.assertNotIn("docker.sock", compose)
        self.assertNotIn("minio", compose.lower())
        self.assertNotIn("/var/run/docker.sock", compose)
        self.assertIn("read_only: true", compose)
        self.assertIn("${EXPERIMENT_OUTPUT_DIR:?", compose)

    def test_smoke_checks_two_hosts_and_node_semver(self):
        source = (RUNTIME / "cluster_smoke.py").read_text(encoding="utf-8")
        self.assertIn("spark://master:7077", source)
        self.assertIn("socket.gethostname()", source)
        self.assertIn("node_semver_passed", source)
        self.assertIn("distinct_workers_observed", source)
        self.assertIn("SPARK_RESULT_PATH", source)
        self.assertIn(".barrier().mapPartitions(inspect_partition)", source)
        self.assertIn('"python_version"', source)
        self.assertIn('"java_version"', source)
        self.assertIn('"node_version"', source)
        self.assertIn('"spark.driver.memory", "512m"', source)

    def test_runbook_uses_unique_runtime_project_and_image(self):
        readme = (ROOT / "pipeline" / "spark_experiment" / "README.md").read_text(encoding="utf-8")
        self.assertIn("pickage-runtime-local-20260915", readme)
        self.assertIn("pickage-spark-experiment:runtime-3.5.3", readme)


if __name__ == "__main__":
    unittest.main()
