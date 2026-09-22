import unittest
from datetime import date, datetime, timezone

from . import weekly
from .test_support import FakeS3

NOW = datetime(2026, 9, 22, 3, 0, tzinfo=timezone.utc)
RAW = "pickage-raw"


def run_doc(week: str, status: str, **extra):
    doc = {"week_of": week, "status": status, "consecutive_failures": 0, "last_error": None,
           "manual_claimed_at": None, "started_at": f"{week}T01:00:00+00:00", "finished_at": None,
           "updated_at": f"{week}T02:00:00+00:00",
           "coverage": {"depsdev_snapshot": week, "downloads_through": "2026-09-20",
                        "downloads_window": ["2026-09-07", "2026-09-20"]},
           "steps": [{"step": "depsdev_t2", "status": "SUCCEEDED", "attempt_count": 1,
                      "started_at": None, "finished_at": None, "error_message": None, "detail": {"tables": 3}},
                     {"step": "gcs_sync", "status": "FAILED", "attempt_count": 2,
                      "started_at": None, "finished_at": None, "error_message": "x" * 2000, "detail": {}}]}
    doc.update(extra)
    return doc


class SummarizeTest(unittest.TestCase):
    def test_trims_errors_and_keeps_steps(self):
        row = weekly.summarize(date(2026, 9, 21), run_doc("2026-09-21", "FAILED", last_error="y" * 1000), None)
        self.assertEqual(row["status"], "FAILED")
        self.assertEqual(len(row["last_error"]), weekly.ERROR_SHOWN + 1)
        self.assertEqual([s["status"] for s in row["steps"]], ["SUCCEEDED", "FAILED"])
        self.assertEqual(row["steps"][0]["detail"], {"tables": 3})
        self.assertFalse(row["manual"]["pending"])

    def test_manual_pending_uses_runner_rule(self):
        manual = {"requested_at": "2026-09-22T02:00:00+00:00"}
        row = weekly.summarize(date(2026, 9, 21), run_doc("2026-09-21", "BLOCKED"), manual)
        self.assertTrue(row["manual"]["pending"])
        claimed = run_doc("2026-09-21", "RUNNING", manual_claimed_at="2026-09-22T02:30:00+00:00")
        self.assertFalse(weekly.summarize(date(2026, 9, 21), claimed, manual)["manual"]["pending"])

    def test_mailbox_without_run_is_requested(self):
        row = weekly.summarize(date(2026, 9, 28), None, {"requested_at": "2026-09-22T02:00:00+00:00"})
        self.assertEqual(row["status"], "REQUESTED")
        self.assertTrue(row["manual"]["pending"])
        self.assertNotIn("steps", row)


class CollectTest(unittest.TestCase):
    def test_newest_first_capped_with_two_lists(self):
        s3 = FakeS3()
        for week, status in (("2026-09-07", "SUCCEEDED"), ("2026-09-14", "SUCCEEDED"), ("2026-09-21", "RUNNING")):
            s3.add(RAW, f"_ops/weekly/{week}/run.json", run_doc(week, status))
        s3.add(RAW, "_ops/weekly/2026-09-14/manual-request.json", {"requested_at": "2026-09-22T00:00:00+00:00"})
        out = weekly.collect(s3, bucket=RAW, max_runs=2, now=NOW)
        self.assertEqual(out["weeks_total"], 3)
        self.assertEqual([r["week_of"] for r in out["runs"]], ["2026-09-21", "2026-09-14"])
        self.assertTrue(out["runs"][1]["manual"]["pending"])
        self.assertEqual(s3.list_calls, 2)
        # NOW 는 화요일 12:00 KST — 이번 주(09-21) 창이 열렸고 회차 객체가 있으니 missing 이 아니다
        self.assertEqual(out["expected"], {"week_of": "2026-09-21", "window_open_at": "2026-09-22T01:00:00+00:00",
                                           "window_open": True, "present": True, "missing": False})

    def test_missing_current_week_is_named_when_window_is_open(self):
        """타이머가 안 돌아 이번 주 객체가 아예 없으면 — 지난주 SUCCEEDED 만 있어 초록으로 보이던 것을 잡는다."""
        s3 = FakeS3()
        s3.add(RAW, "_ops/weekly/2026-09-14/run.json", run_doc("2026-09-14", "SUCCEEDED"))
        out = weekly.collect(s3, bucket=RAW, max_runs=8, now=NOW)
        self.assertEqual([r["week_of"] for r in out["runs"]], ["2026-09-14"])
        self.assertTrue(out["expected"]["missing"])
        # 창이 아직 안 열렸으면(월요일) 없는 게 정상이다
        monday = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
        out = weekly.collect(s3, bucket=RAW, max_runs=8, now=monday)
        self.assertEqual((out["expected"]["window_open"], out["expected"]["missing"]), (False, False))
        # 우편함만 있어도 "객체가 있다" — 다음 발화가 집어 가는지는 is_manual_pending 이 본다
        s3.add(RAW, "_ops/weekly/2026-09-21/manual-request.json", {"requested_at": "2026-09-22T02:00:00+00:00"})
        out = weekly.collect(s3, bucket=RAW, max_runs=8, now=NOW)
        self.assertEqual((out["expected"]["present"], out["expected"]["missing"]), (True, False))


if __name__ == "__main__":
    unittest.main()
