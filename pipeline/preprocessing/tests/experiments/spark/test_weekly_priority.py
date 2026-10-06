import unittest
from pipeline.preprocessing.experiments.spark.runtime.weekly_priority import violation


class WeeklyPriorityTests(unittest.TestCase):
    def sample(self, **updates):
        row = {'phase': ['downloads_weekly', '시작'], 'checkpoint_age_seconds': 2,
               'available_memory_bytes': 10 * 1024**3, 'weekly_anon_bytes': 220 * 1024**2,
               'io_pressure_avg10': 0, 'memory_pressure_avg10': 0, 'container_id': 'weekly',
               'restarts': 0, 'monotonic': 10, 'weekly_cpu_usage_usec': 1000}
        row.update(updates)
        return row

    def test_quiet_collection_can_coexist(self):
        self.assertIsNone(violation(self.sample(monotonic=13, weekly_cpu_usage_usec=2000), self.sample()))

    def test_phase_change_stale_progress_and_resources_stop_experiment(self):
        cases = [({'phase': ['downloads_parquet', '시작']}, 'WEEKLY_PHASE_CHANGED'),
                 ({'checkpoint_age_seconds': 121}, 'WEEKLY_CHECKPOINT_STALE'),
                 ({'available_memory_bytes': 4 * 1024**3}, 'AVAILABLE_MEMORY_BELOW_5G'),
                 ({'weekly_anon_bytes': 2 * 1024**3}, 'WEEKLY_MEMORY_INCREASED'),
                 ({'io_pressure_avg10': 11}, 'HOST_RESOURCE_PRESSURE'),
                 ({'memory_pressure_avg10': 2}, 'HOST_RESOURCE_PRESSURE')]
        for updates, expected in cases:
            with self.subTest(updates=updates):
                self.assertEqual(violation(self.sample(**updates)), expected)

    def test_restart_and_cpu_growth_stop_experiment(self):
        self.assertEqual(violation(self.sample(restarts=1), self.sample()), 'WEEKLY_CONTAINER_CHANGED')
        self.assertEqual(violation(self.sample(container_id='new'), self.sample()), 'WEEKLY_CONTAINER_CHANGED')
        self.assertEqual(violation(self.sample(monotonic=12, weekly_cpu_usage_usec=2001000), self.sample()),
                         'WEEKLY_CPU_INCREASED')


if __name__ == '__main__':
    unittest.main()
