"""실제 MinIO 를 쓰는 느린 층. 지정하지 않으면 skip 이다.

    docker compose --profile data up -d minio
    WEEKLY_MINIO_TEST=1 .venv-bq/Scripts/python -m unittest pipeline.weekly.test_integration -v

여기서만 드러나는 것은 **가짜 S3 가 흉내 낼 수 없는 계약**이다.

* 없는 객체를 GET 하면 어떤 예외가 나는가 — `state._missing()` 이 그 모양에 기대고 있다.
  틀리면 "회차가 없다" 가 예외로 터져서 타이머가 매 발화 실패한다.
* `Delimiter` 를 준 `list_objects_v2` 가 `CommonPrefixes` 를 실제로 그렇게 주는가 —
  `weeks()` 가 그 모양에 기대고 있다. 틀리면 지난 회차 정리가 조용히 아무것도 안 한다.
* 한글이 든 JSON 이 왕복해도 그대로인가.

실제 회차 경로를 건드리지 않도록 **먼 미래 주차**를 쓰고, 끝나면 지운다.
"""
import os
import unittest
from datetime import date, datetime, timedelta, timezone

from .state import ObjectStore, WeeklyState, manual_key, run_key

# 2099년의 어느 월요일. 실제 수집이 닿을 일이 없고, 달력에서 유도하므로 요일이 틀릴 수 없다.
ANCHOR = date(2099, 1, 1)
WEEK = ANCHOR - timedelta(days=ANCHOR.weekday())


@unittest.skipUnless(os.getenv("WEEKLY_MINIO_TEST") == "1",
                     "set WEEKLY_MINIO_TEST=1 for local MinIO")
class MinioStateTests(unittest.TestCase):
    def setUp(self):
        from pipeline.minio.ingest_raw import client

        self.s3 = client()
        self.store = ObjectStore(self.s3)
        self.state = WeeklyState(self.store)
        self.addCleanup(self.cleanup)
        self.cleanup()

    def cleanup(self):
        for week in (WEEK, WEEK - timedelta(days=7), WEEK - timedelta(days=14)):
            for key in (run_key(week), manual_key(week)):
                try:
                    self.s3.delete_object(Bucket=self.store.bucket, Key=key)
                except Exception:  # 없으면 그만이다
                    pass

    def test_absent_object_reads_as_none(self):
        """이게 예외로 터지면 타이머가 매 발화 실패한다."""
        self.assertIsNone(self.store.get(run_key(WEEK)))
        now, record, steps = self.state.load(WEEK)
        self.assertIsNone(record)
        self.assertEqual(steps, [])
        self.assertIsNotNone(now)

    def test_round_trip_keeps_korean_text(self):
        self.state.load(WEEK)
        self.state.begin(WEEK, claim_manual=False)
        self.state.step_start(WEEK, "bronze_downloads")
        self.state.step_finish(WEEK, "bronze_downloads", "FAILED",
                               error="입고기가 심링크를 거부했다")
        self.state.fail(WEEK, "bronze_downloads: 입고기가 심링크를 거부했다")

        fresh = WeeklyState(ObjectStore(self.s3))
        _, record, steps = fresh.load(WEEK)
        self.assertEqual(record.status, "FAILED")
        self.assertEqual(record.consecutive_failures, 1)
        self.assertEqual(record.last_error, "bronze_downloads: 입고기가 심링크를 거부했다")
        self.assertEqual(steps[0]["error_message"], "입고기가 심링크를 거부했다")

    def test_mailbox_is_a_separate_object(self):
        """백엔드는 우편함만 쓴다. 회차 객체가 없어도 요청이 살아 있어야 한다."""
        self.s3.put_object(
            Bucket=self.store.bucket, Key=manual_key(WEEK),
            Body=('{"requested_at": "'
                  + datetime.now(timezone.utc).isoformat() + '"}').encode("utf-8"),
            ContentType="application/json")
        _, record, _ = self.state.load(WEEK)
        self.assertIsNotNone(record)
        self.assertTrue(record.manual_pending)

    def test_weeks_listing_finds_stored_runs(self):
        """`weeks()` 가 CommonPrefixes 모양에 기대고 있다. 틀리면 정리가 조용히 멈춘다."""
        older = WEEK - timedelta(days=7)
        for week in (WEEK, older):
            state = WeeklyState(ObjectStore(self.s3))
            state.load(week)
            state.begin(week, claim_manual=False)
            state.succeed(week)

        listed = self.store.weeks()
        self.assertIn(WEEK, listed)
        self.assertIn(older, listed)
        # 최신순이어야 한다
        self.assertLess(listed.index(WEEK), listed.index(older))
        # 지금 회차는 지울 대상이 아니고, keep=0 이면 그 앞의 성공 회차가 걸린다
        self.assertIn(older, self.state.purgeable_weeks(WEEK, keep=0))
        self.assertNotIn(WEEK, self.state.purgeable_weeks(WEEK, keep=0))


if __name__ == "__main__":
    unittest.main()
