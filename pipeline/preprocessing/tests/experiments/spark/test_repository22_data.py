import unittest
from unittest.mock import patch

from pipeline.preprocessing.experiments.spark.runtime import repository22_data as data


class DataPolicyTests(unittest.TestCase):
    def test_each_role_has_bounded_resources_and_low_priority(self):
        expected = {'baseline': (2, '7680m'), 'worker': (2, '5632m'),
                    'spark': (1, '2048m'), 'master': (.25, '512m'), 'compare': (1, '2048m')}
        supervisor = data.Supervisor({})
        for name, limits in expected.items():
            with self.subTest(name=name), patch.object(data.host.Supervisor, 'start', return_value='id') as start:
                self.assertEqual(supervisor.start(name, 99, '99g', ['python3', 'job.py'], extra=['--network', 'none']), 'id')
                args, kwargs = start.call_args
                self.assertEqual(args[1:3], limits)
                self.assertEqual(args[3][:3], ['nice', '-n', '10'])
                extra = kwargs['extra']
                self.assertEqual(extra[extra.index('--cpu-shares') + 1], '128')
                self.assertEqual(extra[extra.index('--device-read-bps') + 1], '/dev/nvme0n1:32mb')
                self.assertEqual(extra[extra.index('--device-write-bps') + 1], '/dev/nvme0n1:32mb')


if __name__ == '__main__':
    unittest.main()
