from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from pipeline.preprocessing.experiments.spark.runtime import benchmark_app_host as app_host


class BenchmarkAppHostTests(unittest.TestCase):
    def test_host_identity_requires_expected_app_ec2_and_address(self):
        app_host.host_identity(app_host.APP_HOSTNAME, address_is_local=True)
        with self.assertRaises(RuntimeError):
            app_host.host_identity("ip-172-26-8-249", address_is_local=True)
        with self.assertRaises(RuntimeError):
            app_host.host_identity(app_host.APP_HOSTNAME, address_is_local=False)

    def test_port_preflight_checks_only_experiment_worker_ports(self):
        checked = []

        def bind(host, port):
            checked.append((host, port))
            return True

        app_host.check_ports_free(bind=bind)
        self.assertEqual(checked, [(app_host.APP_HOST, 40014), (app_host.APP_HOST, 18081)])

    def test_worker_command_is_capped_labelled_and_passes_only_credential_names(self):
        with patch.dict(os.environ, {
            "AWS_ACCESS_KEY_ID": "never-persist-this-access-key",
            "AWS_SECRET_ACCESS_KEY": "never-persist-this-secret",
            "AWS_SESSION_TOKEN": "never-persist-this-token",
        }, clear=False):
            command = app_host.worker_docker_command()
        joined = " ".join(command)
        self.assertIn("--network host", joined)
        self.assertIn("--cpus 1", joined)
        self.assertIn("--memory 2816m", joined)
        self.assertIn("--memory-swap 2816m", joined)
        self.assertIn("--pids-limit 512", joined)
        self.assertIn("--cap-drop ALL", joined)
        self.assertIn("--security-opt no-new-privileges", joined)
        self.assertIn("pickage.experiment=" + app_host.RUN, joined)
        self.assertIn("--port 40014 --webui-port 18081 --cores 1 --memory 2048M", joined)
        self.assertIn("-e AWS_ACCESS_KEY_ID", joined)
        self.assertIn("-e AWS_SECRET_ACCESS_KEY", joined)
        self.assertIn("-e AWS_SESSION_TOKEN", joined)
        for secret in ("never-persist-this-access-key", "never-persist-this-secret",
                       "never-persist-this-token"):
            self.assertNotIn(secret, joined)
        self.assertIn("hadoop-aws-3.3.4.jar", joined)
        self.assertIn("aws-java-sdk-bundle-1.12.262.jar", joined)

    def test_foreign_or_mismatched_container_caps_are_rejected(self):
        valid = {"HostConfig": {"NanoCpus": 1_000_000_000,
                  "Memory": 2816 * 1024**2, "MemorySwap": 2816 * 1024**2,
                  "RestartPolicy": {"Name": "no"}},
                 "Config": {"Labels": {"pickage.experiment": app_host.RUN}}}
        app_host.verify_container_caps(valid)
        invalid = {**valid, "HostConfig": {**valid["HostConfig"], "Memory": 4 * 1024**3}}
        with self.assertRaises(RuntimeError):
            app_host.verify_container_caps(invalid)
        foreign = {**valid, "Config": {"Labels": {"pickage.experiment": "another-run"}}}
        with self.assertRaises(RuntimeError):
            app_host.verify_container_caps(foreign)

    def test_worker_exit_is_expected_only_after_master_was_seen_then_lost_repeatedly(self):
        self.assertEqual(app_host.classify_worker_exit(0, master_failures=3,
                                                       master_was_reachable=True),
                         "EXPECTED_MASTER_STOP")
        self.assertEqual(app_host.classify_worker_exit(0, master_failures=0,
                                                       master_was_reachable=True),
                         "WORKER_EXITED_BEFORE_MASTER_STOP")
        self.assertEqual(app_host.classify_worker_exit(1, master_failures=1,
                                                       master_was_reachable=True),
                         "WORKER_EXITED_NONZERO")
        self.assertEqual(app_host.classify_worker_exit(0, master_failures=5,
                                                       master_was_reachable=False),
                         "WORKER_EXITED_UNEXPECTEDLY")

    def test_default_cli_detaches_and_foreground_cli_runs_inline(self):
        with patch.object(app_host, "detach", return_value=0) as detach:
            self.assertEqual(app_host.main([]), 0)
            detach.assert_called_once_with()
        with patch.object(app_host, "run_supervisor", return_value={"status": "EXPECTED_MASTER_STOP"}) as run:
            self.assertEqual(app_host.main(["--foreground"]), 0)
            run.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
