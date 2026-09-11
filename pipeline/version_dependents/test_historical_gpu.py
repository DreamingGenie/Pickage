"""Optional experiment tests; ordinary production runs do not require a GPU."""
import copy
import importlib.util
import os
from pathlib import Path
import random
import tempfile
import unittest

from pipeline.requirements_resolution.bridge import NodeSession, discover_runtime
from .historical_gpu import NORMALIZER, cpu_ranks, gpu_ranks, intervals_from_ranks, validate_plan


@unittest.skipUnless(importlib.util.find_spec('numpy'), 'Optional experiment requires NumPy')
class GpuResolverTests(unittest.TestCase):
    def normalize_and_oracle(self, payload):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = discover_runtime()
            with NodeSession(runtime, Path(tmp) / 'normalize.log', worker=NORMALIZER) as node:
                plan = node.request({**payload, 'verify_spans': True})
            with NodeSession(runtime, Path(tmp) / 'oracle.log',
                             worker=NORMALIZER.with_name('historical_semver_worker.cjs')) as node:
                oracle = node.request(payload)
        self.assertEqual(plan['accepted'], oracle['accepted'])
        self.assertEqual(plan['rejected'], oracle['rejected'])
        ranks, _ = cpu_ranks(plan)
        self.assertEqual(intervals_from_ranks(plan, ranks), oracle['lookups'])
        return plan, ranks, oracle['lookups']

    def fixture(self):
        return {'op': 'package', 'name': 'dep', 'known_package': True, 'snapshot_count': 7,
                'candidates': [
                    {'version': '1.0.0+z', 'birth_index': 1},
                    {'version': '1.0.0+aa', 'birth_index': 2},
                    {'version': 'v1.0.0', 'birth_index': 0},
                    {'version': '1.0.0', 'birth_index': 3},
                    {'version': '0.9.0', 'birth_index': 4},
                    {'version': '1.2.0', 'birth_index': 2},
                    {'version': '2.0.0', 'birth_index': 5},
                    {'version': '3.0.0-rc.1', 'birth_index': 1},
                    {'version': 'bad', 'birth_index': 0}],
                'requirements': ['^1', '~1.0.0', '1.x', '*', '', '1.0.0', '1.0.0+z',
                    '>1.0.0', '>=1.0.0', '<1.0.0', '<=1.0.0', '1.0 - 2.0',
                    '<1 || >=2', '>2 <1', '<0.0.0-0', '3.0.0-rc.1',
                    '>=1.0.0-rc.1 <1.0.0', '^0.0.1', '>=0.9 <2 || >=1 <3',
                    'npm:dep@^1', 'workspace:*', 'catalog:', 'latest', 'git+https://example.org/a',
                    'file:../local', 'https://example.org/a.tgz', 'not a range', None]}

    def test_range_policies_and_build_ties_match_all_dates(self):
        self.normalize_and_oracle(self.fixture())

    def test_candidate_order_does_not_change_winners(self):
        fixture = self.fixture()
        first, ranks, expected = self.normalize_and_oracle(fixture)
        fixture['candidates'].reverse()
        second, next_ranks, _ = self.normalize_and_oracle(fixture)
        self.assertEqual(first['rank_to_version'], second['rank_to_version'])
        self.assertEqual(intervals_from_ranks(second, next_ranks), expected)

    def test_empty_unmapped_invalid_and_late_candidate_states(self):
        base = self.fixture()
        for known in (True, False):
            self.normalize_and_oracle({**base, 'known_package': known, 'candidates': []})
        self.normalize_and_oracle({**base, 'name': 'bad name'})
        self.normalize_and_oracle({**base, 'candidates': [{'version': '2.0.0', 'birth_index': 6}]})
        self.normalize_and_oracle({**base, 'requirements': []})

    def test_randomized_boundaries_match_npm(self):
        rng = random.Random(193)
        for _ in range(4):
            candidates = [{'version': f'{major}.{minor}.{patch}', 'birth_index': rng.randrange(7)}
                          for major in range(3) for minor in range(4) for patch in range(3)]
            requirements = set()
            for _ in range(40):
                version = f'{rng.randrange(4)}.{rng.randrange(5)}.{rng.randrange(4)}'
                requirements.add(rng.choice(['^', '~', '>=', '>', '<=', '<', '']) + version)
            self.normalize_and_oracle({**self.fixture(), 'candidates': candidates,
                                       'requirements': sorted(requirements)})

    def test_duplicates_and_conflicting_births(self):
        fixture = self.fixture()
        fixture['candidates'].append(fixture['candidates'][0])
        self.normalize_and_oracle(fixture)
        fixture['candidates'].append({'version': '1.0.0+z', 'birth_index': 6})
        with self.assertRaisesRegex(RuntimeError, 'conflicting birth_index'):
            self.normalize_and_oracle(fixture)

    def test_plan_rejects_bad_birth_and_spans(self):
        plan, _, _ = self.normalize_and_oracle(self.fixture())
        invalid = copy.deepcopy(plan)
        invalid['birth_by_rank'][0] = 7
        with self.assertRaises(ValueError): validate_plan(invalid)
        invalid = copy.deepcopy(plan)
        invalid['lookups'][0]['spans'] = [[0, 1], [1, 2]]
        with self.assertRaises(ValueError): validate_plan(invalid)
        invalid = copy.deepcopy(plan)
        invalid['lookups'][0]['spans'] = [[0, len(plan['birth_by_rank']) + 1]]
        with self.assertRaises(ValueError): validate_plan(invalid)

    def test_rank_result_shape_and_bounds(self):
        import numpy as np
        plan, ranks, _ = self.normalize_and_oracle(self.fixture())
        with self.assertRaises(ValueError): intervals_from_ranks(plan, ranks[:, :2])
        with self.assertRaises(ValueError): intervals_from_ranks(plan, ranks.astype(float))
        with self.assertRaises(ValueError): intervals_from_ranks(plan, np.full(ranks.shape, 999))

    @unittest.skipUnless(os.environ.get('VD_GPU_TESTS') == '1', 'Set VD_GPU_TESTS=1 for real CUDA checks')
    def test_cuda_matches_oracle_and_repeats(self):
        import numpy as np
        import torch
        self.assertTrue(torch.cuda.is_available(), 'Explicit GPU tests require CUDA')
        for payload in [self.fixture(), {**self.fixture(), 'candidates': []},
                        {**self.fixture(), 'requirements': []}]:
            plan, cpu, expected = self.normalize_and_oracle(payload)
            for _ in range(3):
                result, metrics = gpu_ranks(plan, workspace_mib=1)
                np.testing.assert_array_equal(result, cpu)
                self.assertEqual(intervals_from_ranks(plan, result), expected)
                self.assertLess(metrics['peak_allocated_bytes'], 6 * 1024 ** 3)


if __name__ == '__main__':
    unittest.main()
