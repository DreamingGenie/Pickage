"""Telemetry tests against mocked Linux proc/cgroup filesystems."""
import json
from pathlib import Path
import tempfile
import unittest

from pipeline.spark_experiment.telemetry import parse_event_log, read_snapshot, snapshot_delta


class CgroupTelemetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cg = self.root / "cgroup"
        self.cg.mkdir()
        self.net = self.root / "net.dev"
        self.net.write_text("Inter-| Receive | Transmit\n face |bytes packets errs drop fifo frame compressed multicast|bytes packets errs drop fifo colls carrier compressed\n eth0: 100 1 0 0 0 0 0 0 200 2 0 0 0 0 0 0\n")

    def tearDown(self):
        self.temp.cleanup()

    def write_cgroup(self, cpu="usage_usec 10\nuser_usec 6\nsystem_usec 4\n",
                     memory="100", peak="120", events="oom 0\noom_kill 0\nhigh 2\n",
                     io="8:0 rbytes=30 wbytes=40 rios=3 wios=4\n",
                     memory_stat="anon 60\nfile 40\nkernel 10\nsock 2\n"):
        (self.cg / "cpu.stat").write_text(cpu)
        (self.cg / "memory.current").write_text(memory)
        (self.cg / "memory.peak").write_text(peak)
        (self.cg / "memory.events").write_text(events)
        (self.cg / "io.stat").write_text(io)
        (self.cg / "memory.stat").write_text(memory_stat)

    def read(self, at=1):
        return read_snapshot(cgroup_dir=self.cg, net_dev=self.net, timestamp=at)

    def test_snapshot_delta_aggregates_io_and_reports_counter_changes(self):
        self.write_cgroup()
        before = self.read()
        self.write_cgroup(cpu="usage_usec 70\nuser_usec 50\nsystem_usec 20\n",
                          memory="150", peak="160", events="oom 1\noom_kill 0\nhigh 3\n",
                          io="8:0 rbytes=40 wbytes=50 rios=4 wios=5\n8:16 rbytes=10 wbytes=20 rios=1 wios=2\n",
                          memory_stat="anon 70\nfile 80\nkernel 12\nsock 3\n")
        self.net.write_text("Inter-| Receive | Transmit\nface |bytes packets errs drop fifo frame compressed multicast|bytes packets errs drop fifo colls carrier compressed\neth0: 130 1 0 0 0 0 0 0 280 2 0 0 0 0 0 0\n")
        after = self.read(4)
        delta = snapshot_delta(before, after)
        self.assertEqual(delta["elapsed_seconds"], 3)
        self.assertEqual(delta["cpu"], {"usage_usec": 60, "user_usec": 44, "system_usec": 16})
        self.assertEqual(delta["io"], {"rbytes": 20, "wbytes": 30, "rios": 2, "wios": 3})
        self.assertEqual(delta["network"], {"rx_bytes": 30, "tx_bytes": 80})
        self.assertEqual(delta["memory"]["current"], 150)
        self.assertEqual(before["memory"]["stat"], {"anon": 60, "file": 40, "kernel": 10, "sock": 2})
        self.assertEqual(delta["memory"]["stat"], {"anon": 70, "file": 80, "kernel": 12, "sock": 3})
        self.assertEqual(delta["memory"]["events"]["oom"], 1)

    def test_missing_memory_stat_gauges_stay_null(self):
        self.write_cgroup(memory_stat="anon 10\nfile 20\n")
        snap = self.read()
        self.assertEqual(snap["memory"]["stat"], {"anon": 10, "file": 20, "kernel": None, "sock": None})

    def test_delta_accepts_legacy_samples_without_memory_stat(self):
        before = {"timestamp": 1, "cpu": {"usage_usec": 10}, "memory": {"current": 100, "peak": 200, "events": {}},
                  "io": {"rbytes": 3}, "network": {"rx_bytes": None, "tx_bytes": None}}
        after = {"timestamp": 2, "cpu": {"usage_usec": 15}, "memory": {"current": 110, "peak": 200, "events": {}} ,
                 "io": {"rbytes": 8}, "network": {"rx_bytes": None, "tx_bytes": None}}
        delta = snapshot_delta(before, after)
        self.assertEqual(delta["cpu"]["usage_usec"], 5)
        self.assertEqual(delta["memory"]["stat"], {"anon": None, "file": None, "kernel": None, "sock": None})

    def test_counter_reset_is_null_and_marks_discontinuity(self):
        self.write_cgroup(cpu="usage_usec 80\n", io="8:0 rbytes=100\n")
        before = self.read()
        self.write_cgroup(cpu="usage_usec 5\n", io="bad format\n")
        after = self.read(2)
        delta = snapshot_delta(before, after)
        self.assertIsNone(delta["cpu"]["usage_usec"])
        self.assertTrue(delta["counter_resets"]["cpu"]["usage_usec"])
        self.assertFalse(delta["counter_resets"]["cpu"]["user_usec"])
        self.assertIsNone(delta["cpu"]["user_usec"])
        self.assertIsNone(delta["io"]["rbytes"])
        self.assertIsNone(delta["io"]["wbytes"])

    def test_unavailable_cgroup_and_network_are_not_reported_as_zero(self):
        snapshot = read_snapshot(cgroup_dir=self.root / "absent", net_dev=self.root / "absent-net", timestamp=0)
        self.assertIsNone(snapshot["cpu"]["usage_usec"])
        self.assertIsNone(snapshot["memory"]["current"])
        self.assertIsNone(snapshot["io"]["rbytes"])
        self.assertIsNone(snapshot["network"]["rx_bytes"])


class SparkEventLogTests(unittest.TestCase):
    def test_v35_task_metrics_executor_hosts_and_repeated_heartbeat(self):
        events = [
            {"Event": "SparkListenerExecutorAdded", "Executor ID": "1", "Executor Info": {"Host": "worker-a:7337"}},
            {"Event": "SparkListenerExecutorAdded", "Executor ID": "2", "Executor Info": {"Host": "worker-b:7337"}},
            {"Event": "SparkListenerStageSubmitted", "Stage ID": 5, "Stage Attempt ID": 0,
             "Properties": {"spark.jobGroup.id": "downloads_stage"}},
            {"Event": "SparkListenerExecutorMetricsUpdate", "Executor ID": "1", "Accumulator Updates": [
                {"Task ID": 91, "Stage ID": 4, "Stage Attempt ID": 0, "Accumulables": [{"ID": 3, "Update": 8}]},
                {"Task ID": 91, "Stage ID": 4, "Stage Attempt ID": 0, "Accumulables": [{"ID": 3, "Update": 8}]},
            ]},
            # Spark 3.5's compact JSON event encoding; updates are cumulative.
            {"Event": "SparkListenerExecutorMetricsUpdate", "accumUpdates": [
                [91, 4, 0, [[3, "records", 8, 8]]], [91, 4, 0, [[3, "records", 12, 12]]],
            ]},
            {"Event": "SparkListenerTaskEnd", "Stage ID": 4, "Stage Attempt ID": 0,
             "Task Info": {"Task ID": 91, "Executor ID": "1"},
             "Task Metrics": {"Executor CPU Time": 100, "Executor Run Time": 20,
                "Shuffle Read Metrics": {"Local Bytes Read": 2, "Remote Bytes Read": 30},
                "Shuffle Write Metrics": {"Shuffle Bytes Written": 40},
                "Memory Bytes Spilled": 50, "Disk Bytes Spilled": 60}},
            # Duplicate TaskEnd records can occur in merged/replayed logs; count one task.
            {"Event": "SparkListenerTaskEnd", "Stage ID": 4, "Stage Attempt ID": 0,
             "Task Info": {"Task ID": 91, "Executor ID": "1"},
             "Task Metrics": {"Executor CPU Time": 100, "Executor Run Time": 20}},
            {"Event": "SparkListenerTaskEnd", "Stage ID": 4, "Stage Attempt ID": 0,
             "Task Info": {"Task ID": 92, "Executor ID": "2"}, "Task Metrics": {}},
            {"Event": "SparkListenerTaskEnd", "Stage ID": 5, "Stage Attempt ID": 0,
             "Task Info": {"Task ID": 501, "Executor ID": "missing-executor", "Host": "worker-c:7337"},
             "Task Metrics": {"Executor CPU Time": 0}},
            {"Event": "SparkListenerApplicationEnd", "Timestamp": 123},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            path.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8-sig")
            result = parse_event_log(path)
        self.assertEqual(result["executor_hosts"], ["worker-a", "worker-b", "worker-c"])
        self.assertTrue(result["completed"])
        self.assertFalse(result["incomplete_log"])
        self.assertEqual(result["malformed_line_count"], 0)
        self.assertEqual(result["heartbeat_accumulator_count"], 1)
        self.assertEqual(result["heartbeat_accumulators"][0]["max_update"], 12)
        stage = result["stages"][0]
        self.assertEqual(stage["task_count"], 2)
        self.assertIsNone(stage["executor_cpu_time_ns"])
        self.assertEqual(stage["metric_coverage"]["executor_cpu_time_ns"],
                         {"reported_tasks": 1, "expected_tasks": 2, "incomplete": True})
        self.assertIsNone(stage["shuffle_remote_read_bytes"])
        self.assertIsNone(stage["executor_run_time_ms"])
        self.assertTrue(stage["metric_coverage"]["executor_run_time_ms"]["incomplete"])
        named_stage = result["stages"][1]
        self.assertEqual(named_stage["stage_name"], "downloads_stage")
        self.assertEqual(named_stage["executor_cpu_time_ns"], 0)
        self.assertFalse(named_stage["metric_coverage"]["executor_cpu_time_ns"]["incomplete"])
        self.assertIsNone(named_stage["disk_spill_bytes"])
        self.assertTrue(named_stage["metric_coverage"]["disk_spill_bytes"]["incomplete"])

    def test_truncated_inprogress_log_is_explicitly_incomplete(self):
        task_end = {"Event": "SparkListenerTaskEnd", "Stage ID": 1, "Stage Attempt ID": 0,
                    "Task Info": {"Task ID": 1}, "Task Metrics": {"Executor CPU Time": 0}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "app.inprogress"
            path.write_text(json.dumps(task_end) + "\n{\"Event\":", encoding="utf-8")
            result = parse_event_log(path)
        self.assertEqual(result["malformed_line_count"], 1)
        self.assertFalse(result["completed"])
        self.assertTrue(result["incomplete_log"])
        stage = result["stages"][0]
        self.assertEqual(stage["executor_cpu_time_ns"], 0)
        self.assertEqual(stage["metric_coverage"]["executor_cpu_time_ns"]["reported_tasks"], 1)


if __name__ == "__main__":
    unittest.main()
