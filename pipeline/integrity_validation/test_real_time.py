import copy
import unittest
from .real_time import assess_time


def metadata():
    refs = [{"snapshot_at": "2026-08-24", "snapshot_timestamp": "2026-08-24T21:00:00Z", "previous_snapshot_at": None, "interval_days": None}, {"snapshot_at": "2026-08-31", "snapshot_timestamp": "2026-08-31T21:00:00Z", "previous_snapshot_at": "2026-08-24", "interval_days": 7}]
    ps = {"snapshot_timestamp": "2026-08-31T21:00:00Z", "interval": {"snapshot_at": "2026-08-31", "previous_snapshot_at": "2026-08-24", "download_end_exclusive": "2026-08-31", "download_start_inclusive": "2026-08-24", "interval_days": 7, "snapshot_timestamp": "2026-08-31T21:00:00Z", "previous_snapshot_timestamp": "2026-08-24T21:00:00Z"}}
    vd = {"snapshot_timestamp": "2026-08-31T21:00:00Z", "quality": {"snapshot_timestamp": "2026-08-31T21:00:00Z"}}
    return {"references": refs, "executions": [{"execution_id": "ps", "dataset": "package-snapshot", "status": "PUBLISHED", "snapshot_at": "2026-08-31", "snapshot_timestamp": "2026-08-31T21:00:00Z", "input_metadata": ps}, {"execution_id": "vd", "dataset": "version-dependents", "status": "PUBLISHED", "snapshot_at": "2026-08-31", "snapshot_timestamp": "2026-08-31T21:00:00Z", "input_metadata": vd}]}


class RealTimeTest(unittest.TestCase):
    def test_utc_and_half_open_interval_pass(self): self.assertEqual(assess_time(metadata())["status"], "PASS")
    def test_timezone_date_and_previous_interval_fail(self):
        for mutate in (lambda m: m["references"][1].update(snapshot_timestamp="2026-08-31T00:00:00+09:00"), lambda m: m["references"][1].update(previous_snapshot_at="2026-08-23")):
            value = copy.deepcopy(metadata()); mutate(value); self.assertEqual(assess_time(value)["status"], "FAIL")
    def test_precision_over_six_digits_fails(self):
        value = metadata(); value["references"][0]["snapshot_timestamp"] = "2026-08-24T21:00:00.1234567Z"; self.assertEqual(assess_time(value)["status"], "FAIL")
