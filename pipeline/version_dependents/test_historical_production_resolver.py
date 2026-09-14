"""Boundary and conservation checks for the bounded production resolver adapter."""
import copy
import importlib.util
import unittest
from unittest.mock import patch

import duckdb

from . import historical_production_resolver as resolver
from .historical_gpu import cpu_ranks

META = {"node_version": "v24.18.0", "semver_version": "7.8.1", "package_arg_version": "13.0.2",
        "options": {"loose": False, "includePrerelease": False},
        "equal_precedence_tie": "original_version_utf16_ascending"}
CANDIDATES = [{"version": "1.0.0", "birth_index": 0}, {"version": "2.0.0", "birth_index": 1}]


class Node:
    def __init__(self, mutate=None):
        self.mutate = mutate
        self.requests = []

    def request(self, message):
        self.requests.append(message)
        plan = {"snapshot_count": message["snapshot_count"], "known_package": message["known_package"],
                "accepted": copy.deepcopy(message["candidates"]), "rejected": [],
                "rank_to_version": [c["version"] for c in message["candidates"]],
                "birth_by_rank": [c["birth_index"] for c in message["candidates"]],
                "earliest_accepted_birth": min((c["birth_index"] for c in message["candidates"]), default=message["snapshot_count"]),
                "runtime": {"node": META["node_version"], "semver": META["semver_version"],
                            "package_arg": META["package_arg_version"], "options": META["options"],
                            "tie": META["equal_precedence_tie"]},
                "lookups": [{"requirement": r, "normalized_range": "*", "fixed_status": None,
                             "spans": [[0, len(message["candidates"])]] if message["candidates"] else []}
                            for r in message["requirements"]]}
        if self.mutate:
            self.mutate(plan)
        return plan


def tables(con, count):
    con.execute("CREATE TABLE target_names AS SELECT 'dep' AS name,7::INTEGER AS package_id,true AS known_package,0 AS partition_id")
    con.execute("CREATE TABLE target_population AS SELECT * FROM (VALUES ('dep','1.0.0',0),('dep','2.0.0',1)) t(name,version,birth_index)")
    con.execute("CREATE TABLE lookups AS SELECT i::BIGINT AS lookup_id,'dep' AS declared_name,'*' AS requirement FROM range(?) t(i)", [count])


@unittest.skipUnless(importlib.util.find_spec('numpy'), 'Optional CPU/GPU backend requires NumPy')
class ProductionResolverTests(unittest.TestCase):
    def test_options_and_generation(self):
        for backend in ("npm", "cpu", "gpu"):
            resolver.validate_options(backend, 1024, 128)
        for options in (("cuda", 1, 1), ("cpu", 1025, 1), ("cpu", True, 1), ("gpu", 1, 513)):
            with self.subTest(options=options), self.assertRaises(ValueError):
                resolver.validate_options(*options)
        self.assertEqual(set(resolver.generation_contract()), {
            "historical_production_resolver.py", "historical_gpu.py", "historical_gpu_normalize.cjs"})
        with duckdb.connect() as con, self.assertRaisesRegex(ValueError, "original production"):
            resolver.resolve_partition(con, None, META, 0, 3, backend="npm")

    def test_2701_conditions_are_all_batched(self):
        original = [(i, '*') for i in range(2701)]
        batches = list(resolver._batches('dep', True, CANDIDATES, iter(original), 229, 1024))
        self.assertEqual([len(rows) for rows, _ in batches], [1024, 1024, 653])
        self.assertEqual([row for rows, _ in batches for row in rows], original)

    def test_multibyte_frame_and_empty_lookup_candidate_guard(self):
        with patch.object(resolver, "MAX_FRAME_BYTES", 480):
            batches = list(resolver._batches('dep', True, CANDIDATES, [(i, '한' * 30) for i in range(8)], 3, 1024))
            self.assertEqual(sum(len(rows) for rows, _ in batches), 8)
            self.assertTrue(all(len(resolver.canonical_bytes(msg)) < 480 for _, msg in batches))
            with self.assertRaisesRegex(ValueError, "framing"):
                list(resolver._batches('dep', True, CANDIDATES, [(1, '한' * 400)], 3, 1024))
            with self.assertRaisesRegex(ValueError, "framing"):
                list(resolver._batches('dep', True, [{"version": "a" * 500, "birth_index": 0}], [], 3, 1024))

    def test_rejects_candidate_rank_birth_requirement_and_runtime_drift(self):
        message = dict(op="package", name="dep", known_package=True, snapshot_count=3,
                       candidates=CANDIDATES, requirements=['*'])
        changes = {
            "candidate": lambda p: p["accepted"].pop(),
            "rejected": lambda p: p["rejected"].append(p["accepted"].pop()),
            "rank": lambda p: p["rank_to_version"].__setitem__(1, '1.0.0'),
            "birth": lambda p: p["birth_by_rank"].__setitem__(1, 0),
            "node": lambda p: p["runtime"].__setitem__("node", "v1"),
            "tie": lambda p: p["runtime"].__setitem__("tie", "other"),
            "requirement": lambda p: p["lookups"][0].__setitem__("requirement", "other"),
            "earliest": lambda p: p.__setitem__("earliest_accepted_birth", 2),
        }
        for name, mutate in changes.items():
            with self.subTest(name=name), self.assertRaises(ValueError):
                resolver._checked_plan(Node(mutate), message, META)

    def test_insert_does_not_truncate_stream_after_first_batch(self):
        with duckdb.connect() as con:
            tables(con, 2051)
            node = Node()
            metrics = resolver.resolve_partition(con, node, META, 0, 3, backend="cpu")
            self.assertEqual(metrics["resolved_lookups"], 2051)
            self.assertEqual([len(m['requirements']) for m in node.requests], [1024, 1024, 3])
            self.assertEqual(con.execute("SELECT count(*),count(DISTINCT lookup_id),min(lookup_id),max(lookup_id) FROM lookup_intervals").fetchone(), (4102, 2051, 0, 2050))
            self.assertEqual(con.execute("SELECT start_index,end_index,status,target_package_id,target_version,count(*) FROM lookup_intervals GROUP BY ALL ORDER BY 1").fetchall(),
                             [(0, 1, 'RESOLVED', 7, '1.0.0', 2051), (1, 3, 'RESOLVED', 7, '2.0.0', 2051)])

    def test_zero_lookup_validates_candidates_without_numeric_work(self):
        with duckdb.connect() as con:
            tables(con, 0)
            node = Node()
            with patch.object(resolver, "gpu_ranks", side_effect=AssertionError("unexpected numeric work")):
                metrics = resolver.resolve_partition(con, node, META, 0, 3, backend="gpu")
            self.assertEqual(metrics["zero_lookup_packages"], 1)
            self.assertEqual(len(node.requests), 1)
            self.assertEqual(con.execute("SELECT count(*) FROM lookup_intervals").fetchone()[0], 0)
        with duckdb.connect() as con:
            tables(con, 0)
            with self.assertRaises(ValueError):
                resolver.resolve_partition(con, Node(lambda p: p["accepted"].pop()), META, 0, 3, backend="cpu")

    def test_gpu_times_sum_and_memory_peaks_take_maximum(self):
        def fake_gpu(plan, **_):
            ranks, _ = cpu_ranks(plan)
            return ranks, {"host_preparation_seconds": 1, "h2d_seconds": 2, "compute_seconds": 3,
                           "d2h_seconds": 4, "peak_allocated_bytes": 10, "peak_reserved_bytes": 20}
        with duckdb.connect() as con:
            tables(con, 3)
            with patch.object(resolver, "gpu_ranks", side_effect=fake_gpu):
                metrics = resolver.resolve_partition(con, Node(), META, 0, 3, backend="gpu", lookup_batch=2)
            self.assertEqual([metrics[k] for k in ("host_preparation_seconds", "h2d_seconds", "compute_seconds", "d2h_seconds")], [2, 4, 6, 8])
            self.assertEqual([metrics[k] for k in ("peak_allocated_bytes", "peak_reserved_bytes")], [10, 20])


if __name__ == "__main__":
    unittest.main()
