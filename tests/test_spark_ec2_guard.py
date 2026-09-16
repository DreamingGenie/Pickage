import unittest
from unittest.mock import patch

from pipeline.spark_experiment.runtime import ec2_guard


class Ec2GuardTests(unittest.TestCase):
    def test_stop_only_selects_containers_with_exact_experiment_label(self):
        with patch.object(ec2_guard, 'docker', side_effect=['own1\nown2\n', '']) as call:
            ec2_guard.stop_own()
        self.assertEqual(call.call_args_list[0].args,
                         ('ps', '-q', '--filter', 'label=pickage.experiment=' + ec2_guard.RUN))
        self.assertEqual(call.call_args_list[1].args, ('stop', '--time', '5', 'own1', 'own2'))

    def test_no_stop_command_when_no_experiment_containers_exist(self):
        with patch.object(ec2_guard, 'docker', return_value='') as call:
            ec2_guard.stop_own()
        self.assertEqual(call.call_count, 1)


if __name__ == '__main__':
    unittest.main()
