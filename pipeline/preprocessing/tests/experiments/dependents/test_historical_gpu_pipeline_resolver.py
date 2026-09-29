"""Parity tests for the stateful Node normalizer and GPU client boundary."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

import duckdb
from pipeline.preprocessing.requirements_resolution.bridge import NodeSession, discover_runtime
from pipeline.preprocessing.experiments.dependents import historical_gpu_pipeline_resolver as resolver
from pipeline.preprocessing.version_dependents import historical_production_resolver as production
from pipeline.preprocessing.version_dependents.historical_gpu import cpu_ranks


def tables(con, count=5):
    con.execute("CREATE TABLE target_names AS SELECT 'dep' AS name,7::INTEGER AS package_id,true AS known_package,0 AS partition_id")
    con.execute("CREATE TABLE target_population AS SELECT * FROM (VALUES ('dep','1.0.0',0),('dep','2.0.0',1)) t(name,version,birth_index)")
    con.execute("CREATE TABLE lookups AS SELECT i::BIGINT lookup_id,'dep' declared_name,('>=' || i::VARCHAR || '.0.0') requirement FROM range(?) t(i)", [count])


class CpuClient:
    def __init__(self, fail=False): self.active = set(); self.fail = fail; self.batch_sizes = []
    def begin(self, key, plan): self.active.add(key); return {"client_begin": 1}
    def ranks(self, key, plan):
        self.batch_sizes.append(len(plan['lookups']))
        if self.fail: raise RuntimeError("numeric failure")
        return cpu_ranks(plan)
    def end(self, key): self.active.discard(key); return {"client_end": 1}


class MutatingNode:
    def __init__(self, node, field): self.node, self.field = node, field
    def request(self, message):
        result = self.node.request(message)
        if message.get("op") == "begin":
            if self.field == "birth": result["birth_by_rank"][0] = 1
            elif self.field == "runtime": result["runtime"]["node"] = "drift"
        return result


@unittest.skipUnless(importlib.util.find_spec("numpy"), "requires NumPy")
class ResolverTests(unittest.TestCase):
    def test_long_calendar_reduces_batch_to_fit_gpu_response(self):
        runtime = self._runtime()
        with tempfile.TemporaryDirectory() as td, NodeSession(runtime, Path(td) / 'node.log', worker=resolver.NORMALIZER) as node, duckdb.connect() as con:
            metadata = self._metadata(node)
            tables(con, 511); client = CpuClient()
            result = resolver.resolve_partition(con, node, metadata, 0, 4096, client=client, attempt_identity=self._identity())
            self.assertEqual(client.batch_sizes, [510, 1])
            self.assertEqual(result['resolved_lookups'], 511)

    def _runtime(self):
        try: return discover_runtime()
        except ValueError as exc: self.skipTest(str(exc))

    def _identity(self):
        return {"run_plan_sha256": "a" * 64, "epoch": "b" * 32, "attempt": "partitions/000/attempts/" + "c" * 32, "partition_id": 0}

    def _metadata(self, node):
        key = "probe-" + "a" * 8
        base = node.request({"op": "begin", "package_key": key, "name": "dep", "known_package": True,
                             "candidates": [{"version": "1.0.0", "birth_index": 0}], "snapshot_count": 3})
        node.request({"op": "end", "package_key": key})
        runtime = base["runtime"]
        return {"node_version": runtime["node"], "semver_version": runtime["semver"],
                "package_arg_version": runtime["package_arg"], "options": runtime["options"],
                "equal_precedence_tie": runtime["tie"]}

    def test_actual_node_batches_and_cpu_client_cleanup(self):
        runtime = self._runtime()
        with tempfile.TemporaryDirectory() as td, NodeSession(runtime, Path(td) / "node.log", worker=resolver.NORMALIZER) as node, duckdb.connect() as con:
            metadata = self._metadata(node)
            tables(con, 2051); client = CpuClient()
            result = resolver.resolve_partition(con, node, metadata, 0, 3, client=client, attempt_identity=self._identity())
            self.assertEqual(result["resolved_lookups"], 2051); self.assertEqual(result["lookup_requests"], 3)
            self.assertFalse(client.active); self.assertEqual(con.execute("SELECT count(DISTINCT lookup_id) FROM lookup_intervals").fetchone()[0], 2051)

    def test_zero_lookup_still_validates_and_cleans_up(self):
        runtime = self._runtime()
        with tempfile.TemporaryDirectory() as td, NodeSession(runtime, Path(td) / "node.log", worker=resolver.NORMALIZER) as node, duckdb.connect() as con:
            metadata = self._metadata(node)
            tables(con, 0); client = CpuClient()
            result = resolver.resolve_partition(con, node, metadata, 0, 3, client=client, attempt_identity=self._identity())
            self.assertEqual(result["zero_lookup_packages"], 1); self.assertFalse(client.active)

    def test_numeric_failure_still_calls_end(self):
        runtime = self._runtime()
        with tempfile.TemporaryDirectory() as td, NodeSession(runtime, Path(td) / "node.log", worker=resolver.NORMALIZER) as node, duckdb.connect() as con:
            metadata = self._metadata(node)
            tables(con, 1); client = CpuClient(fail=True)
            with self.assertRaises(RuntimeError): resolver.resolve_partition(con, node, metadata, 0, 3, client=client, attempt_identity=self._identity())
            self.assertFalse(client.active)

    def test_matches_original_cpu_resolver_rows(self):
        runtime = self._runtime()
        old_worker = production.NORMALIZER
        with tempfile.TemporaryDirectory() as td:
            with NodeSession(runtime, Path(td) / "new.log", worker=resolver.NORMALIZER) as new_node, NodeSession(runtime, Path(td) / "old.log", worker=old_worker) as old_node:
                new_meta = self._metadata(new_node)
                old_meta = new_meta
                with duckdb.connect() as new_con, duckdb.connect() as old_con:
                    tables(new_con, 2051); tables(old_con, 2051)
                    new_client = CpuClient()
                    resolver.resolve_partition(new_con, new_node, new_meta, 0, 3, client=new_client, attempt_identity=self._identity())
                    production.resolve_partition(old_con, old_node, old_meta, 0, 3, backend="cpu")
                    self.assertEqual(new_con.execute("SELECT * FROM lookup_intervals ORDER BY ALL").fetchall(), old_con.execute("SELECT * FROM lookup_intervals ORDER BY ALL").fetchall())

    def test_candidate_and_runtime_drift_rejected_with_cleanup(self):
        runtime = self._runtime()
        with tempfile.TemporaryDirectory() as td, NodeSession(runtime, Path(td) / "node.log", worker=resolver.NORMALIZER) as node, duckdb.connect() as con:
            metadata = self._metadata(node); tables(con, 1)
            for field in ("birth", "runtime"):
                client = CpuClient()
                with self.subTest(field=field), self.assertRaises(ValueError):
                    resolver.resolve_partition(con, MutatingNode(node, field), metadata, 0, 3, client=client, attempt_identity=self._identity())
                self.assertFalse(client.active)
                con.execute("DROP TABLE lookup_intervals")


if __name__ == "__main__": unittest.main()
