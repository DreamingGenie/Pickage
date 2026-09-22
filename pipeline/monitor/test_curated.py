import unittest
from datetime import datetime, timezone

from . import curated
from .test_support import FakeS3

NOW = datetime(2026, 9, 22, 3, 0, tzinfo=timezone.utc)
CUR = "pickage-curated"
STAGES = ("snapshot", "package_version", "downloads", "repository", "package_snapshot", "dependents")


def seeded():
    s3 = FakeS3()
    # 완료된 회차 — 포인터가 가리킨다
    s3.add(CUR, f"{curated.OPS}/2026-09-14/status.json",
           {"snapshot": "2026-09-14", "run_id": "curated-weekly-20260914", "status": "COMPLETE", "attempt": 1,
            "consecutive_failures": 0, "started_at": "2026-09-16T02:00:00+00:00",
            "finished_at": "2026-09-16T05:10:00+00:00", "next_retry_at": None, "error": None,
            "updated_at": "2026-09-16T05:10:00+00:00"})
    s3.add(CUR, f"{curated.BUNDLE}/snapshot=2026-09-14/run_id=curated-weekly-20260914/status.json",
           {"status": "COMPLETE", "phase": "COMPLETE",
            "stages": {name: {"status": "COMPLETE", "attempt": 1} for name in STAGES}})
    # 실패한 회차 — downloads 단계에서 두 번째 시도 실패, 20분 뒤 재시도
    s3.add(CUR, f"{curated.OPS}/2026-09-21/status.json",
           {"snapshot": "2026-09-21", "run_id": "curated-weekly-20260921", "status": "FAILED", "attempt": 2,
            "consecutive_failures": 2, "started_at": "2026-09-23T02:00:00+00:00",
            "finished_at": "2026-09-23T02:40:00+00:00", "next_retry_at": "2026-09-23T03:00:00+00:00",
            "error": {"type": "RuntimeError", "message": "x" * 2000}, "updated_at": "2026-09-23T02:40:00+00:00"})
    s3.add(CUR, f"{curated.BUNDLE}/snapshot=2026-09-21/run_id=curated-weekly-20260921/status.json",
           {"status": "FAILED", "phase": "downloads",
            "stages": {"snapshot": {"status": "COMPLETE", "attempt": 1, "action": "REVERIFIED"},
                       "package_version": {"status": "COMPLETE", "attempt": 1},
                       "downloads": {"status": "FAILED", "attempt": 2, "error": {"type": "RuntimeError", "message": "boom"}}}})
    # 실행기 상태가 아직 없는 회차 (WAITING_INPUT — raw 가 안 끝났다)
    s3.add(CUR, f"{curated.OPS}/2026-09-28/status.json",
           {"snapshot": "2026-09-28", "run_id": "curated-weekly-20260928", "status": "WAITING_INPUT",
            "consecutive_failures": 0, "error": {"type": "WaitingInput", "message": "Raw weekly run has not succeeded"}})
    s3.add(CUR, f"{curated.OPS}/_dispatcher/status.json", {"status": "TICK_FINISHED", "exit_code": 1})
    s3.add(CUR, f"{curated.BUNDLE}/_current.json",
           {"snapshot": "2026-09-14", "run_prefix": f"{curated.BUNDLE}/snapshot=2026-09-14/run_id=curated-weekly-20260914",
            "manifest_sha256": "f" * 64})
    return s3


class CollectTest(unittest.TestCase):
    def test_newest_first_with_stages_and_pointer(self):
        out = curated.collect(seeded(), bucket=CUR, max_runs=8, now=NOW)
        self.assertEqual([r["snapshot"] for r in out["runs"]], ["2026-09-28", "2026-09-21", "2026-09-14"])
        self.assertEqual(out["snapshots_total"], 3)
        self.assertEqual(out["current"]["snapshot"], "2026-09-14")
        self.assertEqual(out["dispatcher"], {"status": "TICK_FINISHED", "exit_code": 1, "error": None, "updated_at": None})
        waiting, failed, done = out["runs"]
        self.assertEqual((waiting["status"], waiting["stages"]), ("WAITING_INPUT", []))   # 실행기 상태가 없다
        self.assertEqual(failed["status"], "FAILED")
        self.assertEqual(failed["phase"], "downloads")
        self.assertEqual([(s["stage"], s["status"]) for s in failed["stages"]],
                         [("snapshot", "COMPLETE"), ("package_version", "COMPLETE"), ("downloads", "FAILED")])
        self.assertEqual(failed["stages"][0]["action"], "REVERIFIED")
        self.assertEqual(failed["stages"][2]["error"]["message"], "boom")
        self.assertEqual(len(failed["error"]["message"]), curated.ERROR_SHOWN + 1)      # 잘렸다
        self.assertTrue(done["is_current"]); self.assertFalse(failed["is_current"])
        self.assertEqual(len(done["stages"]), 6)

    def test_max_runs_caps_gets_but_counts_all(self):
        s3 = seeded()
        out = curated.collect(s3, bucket=CUR, max_runs=1, now=NOW)
        self.assertEqual(len(out["runs"]), 1)
        self.assertEqual(out["snapshots_total"], 3)
        self.assertEqual(s3.list_calls, 1)                       # 목록은 한 번

    def test_empty_bucket_is_not_an_error(self):
        out = curated.collect(FakeS3(), bucket=CUR, max_runs=8, now=NOW)
        self.assertEqual((out["runs"], out["current"], out["dispatcher"], out["snapshots_total"]), ([], None, None, 0))

    def test_broken_json_is_named_not_hidden(self):
        s3 = seeded()
        s3.add(CUR, f"{curated.BUNDLE}/_current.json", "not json")
        out = curated.collect(s3, bucket=CUR, max_runs=8, now=NOW)
        self.assertIsNone(out["current"])
        self.assertFalse(any(r["is_current"] for r in out["runs"]))


if __name__ == "__main__":
    unittest.main()
