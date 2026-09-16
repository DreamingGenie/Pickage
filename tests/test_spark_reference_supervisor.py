import unittest
import json
from pathlib import Path
import tempfile
from pipeline.spark_experiment.runtime.reference_supervisor import stop_reason, computation_complete


class ReferenceSupervisorTests(unittest.TestCase):
    def test_retry_completion_requires_successful_stage_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.assertFalse(computation_complete(root, 'repository-retry'))
            report = root / 'repository-retry/report.json'
            report.parent.mkdir()
            for status, expected in [('RUNNING', False), ('FAILED', False), ('COMPUTED', True)]:
                report.write_text(json.dumps({'status': status}))
                self.assertEqual(computation_complete(root, 'repository-retry'), expected)
            self.assertFalse(computation_complete(root, 'reference'))

    def test_guard_monitor_stale_or_disk_failure_stops_compute(self):
        good = [100, 99, 100 * 1024**3, True, True]
        self.assertIsNone(stop_reason(*good))
        for index, value, reason in (
            (1, 70, 'SERVICE_GUARD_STALE'), (2, 29 * 1024**3, 'DISK_FREE_BELOW_30_GIB'),
            (3, False, 'SERVICE_GUARD_EXITED'), (4, False, 'RESOURCE_MONITOR_EXITED')):
            case = good.copy()
            case[index] = value
            self.assertEqual(stop_reason(*case), reason)


if __name__ == '__main__':
    unittest.main()
