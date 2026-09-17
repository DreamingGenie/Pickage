"""Security-boundary and output tests for the host-side container monitor."""
import json
from pathlib import Path
import tempfile
import unittest

from pipeline.preprocessing.experiments.spark.runtime.monitor_container import docker_inspect, monitor, resolve_host_cgroup, validate_target


def target(**updates):
    value = {"Id": "abc123", "Name": "/spark-worker", "Labels": {"pickage.experiment": "run-7"},
             "Running": True, "Pid": 4321, "PidMode": "", "CgroupnsMode": "private",
             "NanoCpus": 2000000000, "CpuQuota": -1, "CpuPeriod": 100000,
             "CpusetCpus": "", "Memory": 1073741824, "MemorySwap": 1073741824}
    value.update(updates)
    return value


class ContainerValidationTests(unittest.TestCase):
    def test_accepts_exact_name_and_run_label(self):
        self.assertEqual(validate_target(target(), "spark-worker", "run-7")["Pid"], 4321)

    def test_refuses_mismatched_name_or_label(self):
        for info, name, run in ((target(), "spark", "run-7"),
                                (target(), "spark-worker", "other")):
            with self.subTest(info=info, name=name, run=run), self.assertRaises(ValueError):
                validate_target(info, name, run)

    def test_refuses_host_pid_or_cgroup_namespace(self):
        for info in (target(PidMode="host"), target(CgroupnsMode="host")):
            with self.subTest(info=info), self.assertRaises(ValueError):
                validate_target(info, "spark-worker", "run-7")

    def test_docker_inspect_requests_selective_fields_and_never_emits_env(self):
        fields = ["abc123", "/spark-worker", '{"pickage.experiment":"run-7"}', "true", "4321",
                  "", "private", "2000000000", "-1", "100000", "", "1073741824", "1073741824"]
        seen = []
        def fake(*args):
            seen.extend(args)
            return "\n".join(fields)
        value = docker_inspect("spark-worker", "run-7", docker_fn=fake)
        self.assertEqual(value["Memory"], 1073741824)
        self.assertIn("--format", seen)
        self.assertNotIn("Env", " ".join(seen))


class CgroupResolutionTests(unittest.TestCase):
    def test_resolves_host_pid_cgroup_v2_mount(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc = root / "4321"
            proc.mkdir()
            proc.joinpath("cgroup").write_text("0::/docker/abc123\n", encoding="ascii")
            mount = root / "cg"
            (mount / "docker" / "abc123").mkdir(parents=True)
            (root / "self").mkdir()
            root.joinpath("self/mountinfo").write_text(
                f"1 0 0:1 / {mount} rw - cgroup2 cgroup rw\n", encoding="ascii")
            self.assertEqual(resolve_host_cgroup(4321, proc_root=root), mount / "docker" / "abc123")

    def test_does_not_fall_back_when_cgroup_unresolvable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc = root / "4321"
            proc.mkdir()
            proc.joinpath("cgroup").write_text("2:cpu:/docker/abc\n", encoding="ascii")
            (root / "self").mkdir()
            root.joinpath("self/mountinfo").write_text("", encoding="ascii")
            with self.assertRaises(ValueError):
                resolve_host_cgroup(4321, proc_root=root)


class MonitorOutputTests(unittest.TestCase):
    def test_writes_flushed_jsonl_and_summary_without_mutating_container(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc = root / "proc" / "4321"
            proc.mkdir(parents=True)
            proc.joinpath("cgroup").write_text("0::/docker/abc123\n", encoding="ascii")
            cg = root / "cg" / "docker" / "abc123"
            cg.mkdir(parents=True)
            proc.joinpath("net").mkdir()
            proc.joinpath("net/dev").write_text("", encoding="ascii")
            (root / "proc/self").mkdir()
            (root / "proc/self/mountinfo").write_text(
                f"1 0 0:1 / {root / 'cg'} rw - cgroup2 cgroup rw\n", encoding="ascii")
            clock = [0]
            snapshots = []
            def snapshot_fn(**kwargs):
                self.assertEqual(kwargs["cgroup_dir"], cg)
                snap = {"timestamp": clock[0], "cpu": {"usage_usec": clock[0] * 10},
                        "memory": {"current": 100 + clock[0], "peak": 200,
                                   "events": {}},
                        "io": {"rbytes": clock[0] * 5},
                        "network": {"rx_bytes": None, "tx_bytes": None}}
                snapshots.append(snap)
                return snap
            def sleep(seconds):
                clock[0] += seconds
            summary = monitor(container="spark-worker", run_id="run-7", output=root / "out",
                              duration_seconds=1, proc_root=root / "proc", inspect_fn=target,
                              snapshot_fn=snapshot_fn, sleep_fn=sleep,
                              monotonic_fn=lambda: clock[0], wall_time_fn=lambda: 100 + clock[0])
            samples = (root / "out/container-metrics.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(samples), 2)
            self.assertEqual(summary["sample_count"], 2)
            self.assertEqual(summary["max_sampled_memory_current_bytes"], 101)
            self.assertEqual(summary["max_observed_memory_peak_bytes"], 200)
            self.assertEqual(summary["delta"]["cpu"]["usage_usec"], 10)
            self.assertIsNone(summary["delta"]["network"]["rx_bytes"])
            self.assertIn("cgroup-lifetime", summary["limitations"]["memory_peak"])
            self.assertTrue((root / "out/container-summary.json").exists())

    def test_refuses_to_overwrite_prior_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            (output / "container-metrics.jsonl").write_text("prior\n", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                monitor(container="spark-worker", run_id="run-7", output=output,
                        duration_seconds=1, inspect_fn=target)

    def test_stops_if_exact_name_now_resolves_to_replacement_container(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc = root / "proc" / "4321"
            proc.mkdir(parents=True)
            proc.joinpath("cgroup").write_text("0::/docker/abc123\n", encoding="ascii")
            cg = root / "cg" / "docker" / "abc123"
            cg.mkdir(parents=True)
            (root / "proc/self").mkdir()
            (root / "proc/self/mountinfo").write_text(
                f"1 0 0:1 / {root / 'cg'} rw - cgroup2 cgroup rw\n", encoding="ascii")
            proc.joinpath("net").mkdir()
            proc.joinpath("net/dev").write_text("", encoding="ascii")
            calls = [0]
            def inspect():
                calls[0] += 1
                return target() if calls[0] == 1 else target(Id="replacement-id")
            clock = [0]
            summary = monitor(container="spark-worker", run_id="run-7", output=root / "out",
                              duration_seconds=5, proc_root=root / "proc", inspect_fn=inspect,
                              snapshot_fn=lambda **_: {"timestamp": 1, "cpu": {}, "memory": {"current": None, "peak": None, "events": {}}, "io": {}, "network": {}},
                              sleep_fn=lambda _: clock.__setitem__(0, clock[0] + 1),
                              monotonic_fn=lambda: clock[0])
            self.assertEqual(summary["stop_reason"], "CONTAINER_REPLACED")
            self.assertEqual(summary["container_id"], "abc123")
            self.assertEqual(summary["sample_count"], 1)


if __name__ == "__main__":
    unittest.main()
