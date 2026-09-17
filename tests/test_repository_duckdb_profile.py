import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.spark_experiment.runtime.repository_duckdb_profile import DuckDBProfiler, profile_connection


class Cursor:
    def __init__(self, rows=()): self.rows = list(rows)
    def fetchone(self): return self.rows[0] if self.rows else None
    def fetchall(self): return self.rows


class Connection:
    def execute(self, sql, params=None):
        return Cursor([(1,)]) if str(sql).upper().startswith("SELECT") else Cursor()
    def executemany(self, sql, params): return Cursor()


def snap():
    return {"timestamp": 1, "cpu": {"usage_usec": 1, "user_usec": 1, "system_usec": 0},
            "memory": {"current": 1, "peak": 1, "stat": {"anon": 1, "file": 0, "kernel": 0, "sock": 0},
                        "events": {k: 0 for k in ("low", "high", "max", "oom", "oom_kill", "oom_group_kill")}},
            "io": {k: 0 for k in ("rbytes", "wbytes", "rios", "wios")},
            "network": {"rx_bytes": 0, "tx_bytes": 0}}


class DuckDBProfileTests(unittest.TestCase):
    def test_execute_and_fetch_are_one_event_with_delta(self):
        with tempfile.TemporaryDirectory() as root, patch("pipeline.spark_experiment.runtime.repository_duckdb_profile.read_snapshot", side_effect=[snap(), snap()]):
            path = Path(root) / "actions.jsonl"
            with DuckDBProfiler(path) as profiler:
                profiler.connection(Connection()).execute("SELECT count(*) FROM input_version").fetchone()
            events = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["fetch_method"], "fetchone")
            self.assertEqual(events[0]["category"], "validation")
            self.assertIn("delta", events[0])
            self.assertEqual(json.loads(path.with_name("actions-summary.json").read_text())["operation_count"], 1)

    def test_executemany_and_failure_are_durable(self):
        with tempfile.TemporaryDirectory() as root, patch("pipeline.spark_experiment.runtime.repository_duckdb_profile.read_snapshot", return_value=snap()):
            path = Path(root) / "actions.jsonl"
            with self.assertRaisesRegex(RuntimeError, "boom"):
                with profile_connection(Connection(), path) as con:
                    con.executemany("INSERT INTO url_map VALUES (?, ?)", [("a", "b")])
                    raise RuntimeError("boom")
            summary = json.loads(path.with_name("actions-summary.json").read_text())
            self.assertEqual(summary["status"], "FAILED")
            self.assertEqual(summary["failed"]["type"], "RuntimeError")
            self.assertEqual(summary["operation_count"], 1)

    def test_output_recount_is_not_attributed_to_input_read(self):
        with tempfile.TemporaryDirectory() as root, patch("pipeline.spark_experiment.runtime.repository_duckdb_profile.read_snapshot", return_value=snap()):
            path = Path(root) / "actions.jsonl"
            with DuckDBProfiler(path) as profiler:
                profiler.connection(Connection()).execute("SELECT count(*) FROM read_parquet(?)", ["out.parquet"]).fetchone()
            event = json.loads(path.read_text().splitlines()[0])
            self.assertEqual(event["category"], "output_recount")

    def test_copy_uses_output_write_and_create_target_uses_target_category(self):
        with tempfile.TemporaryDirectory() as root, patch("pipeline.spark_experiment.runtime.repository_duckdb_profile.read_snapshot", return_value=snap()):
            path = Path(root) / "actions.jsonl"
            with DuckDBProfiler(path) as profiler:
                con = profiler.connection(Connection())
                con.execute("COPY (SELECT * FROM candidates_out) TO ? (FORMAT PARQUET)")
                con.execute("CREATE OR REPLACE TEMP TABLE candidates AS SELECT * FROM matched")
            events = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual([e["category"] for e in events], ["output_write", "candidates_selection"])

    def test_unfetched_select_is_marked_uncompleted_on_exit(self):
        with tempfile.TemporaryDirectory() as root, patch("pipeline.spark_experiment.runtime.repository_duckdb_profile.read_snapshot", return_value=snap()):
            path = Path(root) / "actions.jsonl"
            with DuckDBProfiler(path) as profiler:
                profiler.connection(Connection()).execute("SELECT 1")
            event = json.loads(path.read_text().splitlines()[0])
            self.assertFalse(event["completed"])
            self.assertTrue(event["uncompleted"])


if __name__ == "__main__":
    unittest.main()
