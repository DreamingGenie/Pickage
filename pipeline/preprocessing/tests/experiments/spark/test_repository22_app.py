from __future__ import annotations

import unittest
from unittest.mock import patch

from pipeline.preprocessing.experiments.spark.runtime import repository22_app as app
from pipeline.preprocessing.experiments.spark.runtime import repository22_guard as guard


class Repository22AppTests(unittest.TestCase):
    def test_pressure_parser(self):
        self.assertEqual(app.parse_pressure_avg10("some avg10=3.25 avg60=1.0 avg300=0.0 total=1\n"), 3.25)
        with self.assertRaises(ValueError):
            app.parse_pressure_avg10("full avg10=0.0 avg60=0.0 avg300=0.0 total=1\n")

    def test_resource_limits(self):
        self.assertEqual(app.validate_host_resources(available_memory=8 * 1024**3,
                                                     io_avg10=10, memory_avg10=1)["io_pressure_avg10"], 10)
        for kwargs in ({"available_memory": 7 * 1024**3, "io_avg10": 0, "memory_avg10": 0},
                       {"available_memory": 9 * 1024**3, "io_avg10": 10.1, "memory_avg10": 0},
                       {"available_memory": 9 * 1024**3, "io_avg10": 0, "memory_avg10": 1.1}):
            with self.assertRaises(RuntimeError):
                app.validate_host_resources(**kwargs)

    def test_unknown_experiment_ignores_production_and_own_label(self):
        rows = [{"name": "spring", "running": True, "experiment": None},
                {"name": "mine", "running": True, "experiment": app.RUN},
                {"name": "foreign", "running": True, "experiment": "other-run"},
                {"name": "stopped", "running": False, "experiment": "other-run"}]
        self.assertEqual(app.unknown_running_experiments(rows), [rows[2]])
        with self.assertRaises(RuntimeError):
            app.validate_no_unknown_running_experiments(rows)

    def test_worker_command_has_two_core_caps_and_no_secret_values(self):
        command = app.worker_docker_command(credential_names=())
        self.assertEqual(command[0], "docker")
        joined = " ".join(command)
        self.assertIn("--cpus 2", joined)
        self.assertIn("--memory 5632m", joined)
        self.assertIn("--memory-swap 5632m", joined)
        self.assertIn("--cores 2 --memory 4096M", joined)
        self.assertIn("--cpu-shares 128", joined)
        self.assertIn("--device-read-bps /dev/nvme0n1:32mb", joined)
        self.assertIn("--device-write-bps /dev/nvme0n1:32mb", joined)
        self.assertLess(command.index("--cpu-shares"), command.index(app.base.IMAGE))
        image = command.index(app.base.IMAGE)
        self.assertEqual(command[image + 1:image + 4], ["nice", "-n", "10"])

    def test_wrapper_uses_saved_base_worker_without_recursion(self):
        original = app.base.worker_docker_command
        try:
            app.base.worker_docker_command = lambda **kwargs: ["unexpected"]
            command = app.worker_docker_command(credential_names=())
            self.assertIn(app.base.IMAGE, command)
        finally:
            app.base.worker_docker_command = original

    def test_wrapper_routes_only_common_guard_module(self):
        command = ["python3", "-m", "pipeline.preprocessing.experiments.spark.runtime.ec2_guard"]
        routed = app._rewrite_guard_command(command)
        self.assertEqual(routed[-1], "pipeline.preprocessing.experiments.spark.runtime.repository22_guard")
        self.assertEqual(app._rewrite_guard_command(["python3", "-m", "other"]),
                         ["python3", "-m", "other"])

    def test_caps_accept_exact_repository22_container(self):
        info = {"HostConfig": {"NanoCpus": 2_000_000_000,
                                "Memory": 5632 * 1024**2,
                                "MemorySwap": 5632 * 1024**2,
                                "CpuShares": 128,
                                "RestartPolicy": {"Name": "no"}},
                "Config": {"Labels": {"pickage.experiment": app.RUN}}}
        app.verify_container_caps(info)

    def test_known_failure_requires_same_id_running_state_and_signature(self):
        item = {"Id": "known-id", "State": {"Running": True, "Restarting": True, "ExitCode": 1}}

        def fake_docker(*args):
            if args[:2] == ("inspect", "known-id"):
                return __import__("json").dumps([item])
            if args[:2] == ("logs", "--tail"):
                return guard.KNOWN_SIGNATURE
            raise AssertionError(args)

        with patch.object(guard, "docker", side_effect=fake_docker):
            self.assertTrue(guard.check_known_failure("known-id")["skipped"])
            item["State"]["Running"] = False
            with self.assertRaises(RuntimeError):
                guard.check_known_failure("known-id")

    def test_changed_known_failure_signature_is_rejected(self):
        with patch.object(guard, "_inspect", return_value=[{"Id": "known-id", "State": {"Running": True, "Restarting": True, "ExitCode": 1}}]), \
             patch.object(guard, "docker", return_value="a different error"):
            with self.assertRaisesRegex(RuntimeError, "signature changed"):
                guard.check_known_failure("known-id")

    def test_recovered_loader_is_not_hidden_by_old_error_logs(self):
        item = {'Id': 'known-id', 'State': {'Running': True, 'Restarting': False, 'ExitCode': 0}}
        with patch.object(guard, '_inspect', return_value=[item]), patch.object(guard, 'docker', return_value=guard.KNOWN_SIGNATURE):
            with self.assertRaisesRegex(RuntimeError, 'recovered'):
                guard.check_known_failure('known-id')


if __name__ == "__main__":
    unittest.main()
