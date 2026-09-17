from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pipeline.spark_experiment.runtime import repository22_entry as entry


class Repository22EntryTests(unittest.TestCase):
    def test_barrier_requires_four_tasks_and_two_per_expected_worker(self):
        rows = ([{"private_ip": "172.26.8.249"}] * 2 +
                [{"private_ip": "172.26.6.235"}] * 2)
        result = entry.validate_barrier(rows)
        self.assertTrue(result["verified"])
        self.assertEqual(result["workers"], {
            "172.26.6.235": 2, "172.26.8.249": 2})
        with self.assertRaisesRegex(RuntimeError, "four barrier"):
            entry.validate_barrier(rows[:3])

    def test_barrier_rejects_unexpected_host(self):
        rows = ([{"private_ip": "172.26.8.249"}] * 2 +
                [{"private_ip": "10.0.0.1"}] * 2)
        with self.assertRaises(RuntimeError):
            entry.validate_barrier(rows)

    def test_frozen_manifest_identity_and_sha_are_pinned(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "local.json"
            shared = root / "shared.json"
            payload = {"sample": {"package_rows": 1000}, "input_identity": "same"}
            raw = json.dumps(payload).encode()
            source.write_bytes(raw)
            shared.write_text(json.dumps(payload), encoding="utf-8")
            with patch.object(entry, "SOURCE", source), \
                    patch.object(entry, "SHARED_SOURCE", shared), \
                    patch.object(entry, "SOURCE_SHA256", hashlib.sha256(raw).hexdigest()):
                baseline, common, digest = entry.verify_frozen_inputs()
            self.assertEqual(baseline, common)
            self.assertEqual(digest, hashlib.sha256(raw).hexdigest())

    def test_profile_requires_repository_tasks_on_both_hosts(self):
        summary = {"incomplete_log": False, "malformed_line_count": 0,
                   "profiles": [{"action": "_read:package:count",
                                  "hosts": ["172.26.8.249", "172.26.6.235"]}]}
        entry.verify_profile_summary(summary)
        summary["profiles"][0]["hosts"] = ["172.26.8.249"]
        with self.assertRaisesRegex(RuntimeError, "both EC2"):
            entry.verify_profile_summary(summary)

    def test_barrier_on_both_hosts_does_not_count_as_repository_work(self):
        summary = {
            "incomplete_log": False, "malformed_line_count": 0, "profiles": [],
            "event_log_summaries": [{
                "executors": [{"executor_id": "1", "host": "172.26.8.249"},
                               {"executor_id": "2", "host": "172.26.6.235"}],
                "stages": [
                    {"job_group_id": "cluster-benchmark-host-barrier",
                     "executors": ["1", "2"], "task_count": 4},
                    {"job_group_id": "repository-profile:0001:_read:package:count",
                     "executors": ["1"], "task_count": 2},
                ],
            }],
        }
        with self.assertRaisesRegex(RuntimeError, "both EC2"):
            entry.verify_profile_summary(summary)

    def test_output_download_rejects_parent_path(self):
        class Paginator:
            def paginate(self, **kwargs):
                return [{"Contents": [{"Key": entry.PREFIX + "/spark-output/../x.parquet",
                                        "Size": 1}]}]

        class S3:
            def get_paginator(self, name):
                return Paginator()

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "Unsafe"):
                entry.download_outputs(Path(directory), S3())


if __name__ == "__main__":
    unittest.main()
