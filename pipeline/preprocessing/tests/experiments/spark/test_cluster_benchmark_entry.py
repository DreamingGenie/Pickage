from __future__ import annotations

import unittest
from pathlib import Path

from pipeline.preprocessing.experiments.spark.runtime.cluster_benchmark_entry import EXPECTED_WORKERS, summarize_data_stage_hosts, validate_barrier_hosts, validate_paths


RUN = "benchmark-ec2-20260915-a1"
BASE = f"s3a://pickage-curated/experiments/{RUN}"


class ClusterBenchmarkEntryTests(unittest.TestCase):
    def test_paths_pin_output_to_experiment_run_and_allow_shared_frozen_manifest(self):
        validate_paths(
            RUN,
            "s3a://pickage-curated/experiments/raw-freeze-20260915-b1/inputs/manifest.json",
            BASE + "/spark-output",
            Path(f"/experiment/{RUN}/telemetry"),
            Path(f"/experiment/{RUN}/events"),
            Path(f"/experiment/{RUN}/summary.json"),
        )

    def test_paths_reject_production_or_other_run_output(self):
        common = (
            RUN,
            "s3a://pickage-curated/experiments/raw-freeze-20260915-b1/inputs/manifest.json",
        )
        paths = (Path(f"/experiment/{RUN}/telemetry"),
                 Path(f"/experiment/{RUN}/events"), Path(f"/experiment/{RUN}/summary.json"))
        for output in (
            "s3a://pickage-curated/current/curated",
            "s3a://pickage-curated/experiments/other-run/spark-output",
            BASE + "/../current",
        ):
            with self.subTest(output=output), self.assertRaises(ValueError):
                validate_paths(*common, output, *paths)

    def test_barrier_requires_exactly_one_task_on_each_ec2_worker(self):
        rows = [{"private_ip": ip} for ip in sorted(EXPECTED_WORKERS)]
        self.assertTrue(validate_barrier_hosts(rows)["verified"])
        with self.assertRaises(RuntimeError):
            validate_barrier_hosts([{"private_ip": "172.26.8.249"}] * 2)

    def test_data_stage_evidence_excludes_barrier_and_requires_both_hosts(self):
        logs = [{
            "completed": True,
            "malformed_line_count": 0,
            "executors": [{"executor_id": "1", "host": "172.26.8.249"},
                          {"executor_id": "2", "host": "172.26.6.235"}],
            "stages": [
                {"job_group_id": "cluster-benchmark-host-barrier", "task_count": 2,
                 "executors": ["1", "2"]},
                {"job_group_id": "package_version", "task_count": 17,
                 "executors": ["1", "2"]},
                {"job_group_id": "downloads", "task_count": 3,
                 "executors": ["1"]},
            ],
        }]
        evidence = summarize_data_stage_hosts(logs, ["package_version", "downloads"])
        self.assertTrue(evidence["verified"])
        self.assertEqual(evidence["per_stage"]["package_version"]["task_count"], 17)
        self.assertEqual(evidence["per_stage"]["downloads"]["hosts"], ["172.26.8.249"])
        self.assertEqual(evidence["observed_hosts"], sorted(EXPECTED_WORKERS))

    def test_data_stage_evidence_rejects_single_host_only(self):
        evidence = summarize_data_stage_hosts([{
            "completed": True,
            "malformed_line_count": 0,
            "executors": [{"executor_id": "1", "host": "172.26.8.249"}],
            "stages": [{"job_group_id": "repository", "task_count": 30,
                        "executors": ["1"]}],
        }], ["repository"])
        self.assertFalse(evidence["verified"])


if __name__ == "__main__":
    unittest.main()
