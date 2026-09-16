import unittest
from unittest.mock import patch
from pipeline.spark_experiment.runtime import benchmark_data_host as host

class BaselineHostnameTest(unittest.TestCase):
    def test_baseline_keeps_network_isolation_and_resolves_own_hostname(self):
        supervisor = host.Supervisor()
        state = {'Running': False, 'ExitCode': 0, 'OOMKilled': False}
        with patch.object(host, 'save'), patch.object(supervisor, 'check'), \
             patch.object(supervisor, 'start', return_value='test-cid') as start, \
             patch.object(supervisor, 'finish', return_value=state), \
             patch.object(host, 'command', return_value='{"Running": false}'):
            supervisor.phase('baseline', extra=['-e', 'SPARK_LOCAL_IP=127.0.0.1'])
        args, kwargs = start.call_args
        self.assertEqual(args[1:3], (3, '7680m'))
        self.assertEqual(kwargs['network'], 'none')
        extra = kwargs['extra']
        hostname = extra[extra.index('--hostname') + 1]
        self.assertEqual(extra[extra.index('--add-host') + 1], hostname + ':127.0.0.1')
        self.assertIn('SPARK_LOCAL_IP=127.0.0.1', extra)

if __name__ == '__main__':
    unittest.main()
