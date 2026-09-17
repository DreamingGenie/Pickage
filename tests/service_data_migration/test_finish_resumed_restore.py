import importlib.util
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parents[2] / 'scripts/service-data-migration'
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('finish_resumed_restore', HERE / 'finish_resumed_restore.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BenchmarkGateTests(unittest.TestCase):
    def plan(self, **changes):
        node = {'Node Type': 'Index Only Scan', 'Relation Name': 'version',
                'Heap Fetches': 0, 'Actual Rows': 100}
        node.update(changes)
        leaf = {'Node Type': 'Index Only Scan', 'Relation Name': 'd20260831',
                'Heap Fetches': 0, 'Actual Rows': 100}
        return [{'Plan': {'Node Type': 'Merge Anti Join', 'Plans': [node, leaf]}}]

    def test_accepts_observed_reference_index(self):
        module.benchmark_gate(self.plan())

    def test_estimated_plan_is_not_execution_evidence(self):
        plan = self.plan()
        del plan[0]['Plan']['Plans'][0]['Actual Rows']
        with self.assertRaises(ValueError):
            module.benchmark_gate(plan)

    def test_any_sample_with_heap_fetches_blocks_full_scan(self):
        with self.assertRaises(ValueError):
            module.benchmark_gate([self.plan(), self.plan(**{'Heap Fetches': 1})])

    def test_sort_or_heap_scan_blocks_full_scan(self):
        for node in ('Sort', 'Seq Scan'):
            with self.subTest(node=node), self.assertRaises(ValueError):
                module.benchmark_gate(self.plan(**{'Node Type': node}))

    def test_missing_plan_blocks_full_scan(self):
        with self.assertRaises(ValueError):
            module.benchmark_gate({'status': 'PASS'})


if __name__ == '__main__':
    unittest.main()
