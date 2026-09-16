"""상태 계층 시험. 실제 MinIO 없이 돈다 — 가짜 S3 가 메모리 dict 하나다.

여기서 덮는 것은 **저장소를 오가며 뜻이 바뀌지 않는가**다. 직렬화 왕복, 우편함 소비,
BLOCKED 전이, 지울 회차 고르기. 이전 구현에서 이 규칙들은 SQL 안에 있어서 실제
PostgreSQL 없이는 드러나지 않았고, 그래서 통합 시험 하나가 34초를 먹었다.
"""
import json
import unittest
from datetime import date, datetime, timedelta, timezone

from .schedule import STEPS
from .state import (CorruptState, ObjectStore, WeeklyState, blank, coverage,
                    manual_key, run_key)

WEEK = date(2026, 9, 21)          # 월요일
NOW = datetime(2026, 9, 22, 1, 0, tzinfo=timezone.utc)


class _Body:
    def __init__(self, data): self.data = data
    def read(self): return self.data
    def __enter__(self): return self
    def __exit__(self, *_): return False


class _NotFound(Exception):
    """botocore ClientError 의 모양만 흉내 낸다 — state._missing() 이 보는 것은 이 dict 다."""

    response = {"Error": {"Code": "NoSuchKey"},
                "ResponseMetadata": {"HTTPStatusCode": 404}}


class FakeS3:
    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.puts = 0

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise _NotFound()
        return {"Body": _Body(self.objects[Key])}

    def put_object(self, Bucket, Key, Body, ContentType=None):
        self.puts += 1
        self.objects[Key] = Body

    def list_objects_v2(self, Bucket, Prefix, Delimiter=None, ContinuationToken=None):
        prefixes = set()
        for key in self.objects:
            if not key.startswith(Prefix):
                continue
            rest = key[len(Prefix):]
            if Delimiter and Delimiter in rest:
                prefixes.add(Prefix + rest.split(Delimiter, 1)[0] + Delimiter)
        return {"CommonPrefixes": [{"Prefix": p} for p in sorted(prefixes)],
                "IsTruncated": False}


def build(s3=None, clock=None, **kwargs):
    s3 = s3 or FakeS3()
    state = WeeklyState(ObjectStore(s3), clock=clock or (lambda: NOW), **kwargs)
    return s3, state


def stored(s3, week=WEEK):
    return json.loads(s3.objects[run_key(week)].decode("utf-8"))


class LoadTest(unittest.TestCase):
    def test_absent_week_has_no_record(self):
        _, state = build()
        now, record, steps = state.load(WEEK)
        self.assertEqual(now, NOW)
        self.assertIsNone(record)
        self.assertEqual(steps, [])

    def test_mailbox_alone_counts_as_a_run(self):
        """한 번도 돌지 않은 주에 건 수동 요청이 무시되면 안 된다.

        이전 구현에서는 백엔드가 요청을 쓸 때 회차 행까지 만들었다(INSERT ON CONFLICT).
        지금 백엔드는 우편함 객체 하나만 쓰므로, 여기서 None 을 돌려주면 그 요청은
        수집 창이 열릴 때까지 조용히 묻힌다.
        """
        s3, state = build()
        s3.objects[manual_key(WEEK)] = json.dumps(
            {"requested_at": NOW.isoformat()}).encode()
        _, record, _ = state.load(WEEK)
        self.assertIsNotNone(record)
        self.assertTrue(record.manual_pending)

    def test_round_trip_preserves_record(self):
        s3, state = build()
        state.load(WEEK)
        state.begin(WEEK, claim_manual=False)
        state.fail(WEEK, "bronze_downloads: 무너졌다")

        # 새 프로세스가 같은 객체를 읽는 상황이다 — 저장된 JSON 만으로 회차가 복원돼야 한다.
        _, fresh = build(s3)
        _, record, _ = fresh.load(WEEK)
        self.assertEqual(record.week_of, WEEK)
        self.assertEqual(record.status, "FAILED")
        self.assertEqual(record.consecutive_failures, 1)
        self.assertEqual(record.started_at, NOW)
        self.assertEqual(record.last_error, "bronze_downloads: 무너졌다")


class ManualRequestTest(unittest.TestCase):
    def test_claim_resets_failures_and_stamps(self):
        s3, state = build()
        state.load(WEEK)
        state.begin(WEEK, claim_manual=False)
        for _ in range(3):
            state.fail(WEEK, "실패")
        self.assertEqual(stored(s3)["consecutive_failures"], 3)

        state.load(WEEK)
        state.begin(WEEK, claim_manual=True)
        document = stored(s3)
        self.assertEqual(document["consecutive_failures"], 0)
        self.assertEqual(document["manual_claimed_at"], NOW.isoformat())

    def test_claimed_request_stops_being_pending(self):
        s3, state = build()
        requested = NOW - timedelta(minutes=5)
        s3.objects[manual_key(WEEK)] = json.dumps(
            {"requested_at": requested.isoformat()}).encode()
        state.load(WEEK)
        state.begin(WEEK, claim_manual=True)

        _, record, _ = state.load(WEEK)
        self.assertFalse(record.manual_pending)


class FailureTest(unittest.TestCase):
    def test_blocks_at_threshold(self):
        s3, state = build(max_failures=3)
        state.load(WEEK)
        state.begin(WEEK, claim_manual=False)
        self.assertEqual(state.fail(WEEK, "x"), ("FAILED", 1))
        self.assertEqual(state.fail(WEEK, "x"), ("FAILED", 2))
        self.assertEqual(state.fail(WEEK, "x"), ("BLOCKED", 3))

    def test_error_is_truncated(self):
        s3, state = build()
        state.load(WEEK)
        state.begin(WEEK, claim_manual=False)
        state.fail(WEEK, "가" * 9000)
        self.assertEqual(len(stored(s3)["last_error"]), 4000)

    def test_success_clears_failure_trail(self):
        s3, state = build()
        state.load(WEEK)
        state.begin(WEEK, claim_manual=False)
        state.fail(WEEK, "한 번 실패")
        state.load(WEEK)
        state.begin(WEEK, claim_manual=False)
        state.succeed(WEEK)
        document = stored(s3)
        self.assertEqual(document["status"], "SUCCEEDED")
        self.assertEqual(document["consecutive_failures"], 0)
        self.assertIsNone(document["last_error"])


class StepTest(unittest.TestCase):
    def test_steps_are_kept_in_execution_order(self):
        """사람이 `mc cat` 으로 읽는 파일이라 실행 순서대로 보여야 한다."""
        s3, state = build()
        state.load(WEEK)
        state.begin(WEEK, claim_manual=False)
        for step in reversed(STEPS):
            state.step_start(WEEK, step)
        self.assertEqual([item["step"] for item in stored(s3)["steps"]], list(STEPS))

    def test_attempt_count_survives_resume(self):
        """이어받기로 같은 단계를 여러 번 시작하는 것이 정상이다."""
        s3, state = build()
        state.load(WEEK)
        state.begin(WEEK, claim_manual=False)
        state.step_start(WEEK, "depsdev_t2")
        state.step_finish(WEEK, "depsdev_t2", "FAILED", error="끊겼다")

        state.load(WEEK)
        state.step_start(WEEK, "depsdev_t2")
        state.step_finish(WEEK, "depsdev_t2", "SUCCEEDED", detail={"rows": 12})

        item = stored(s3)["steps"][0]
        self.assertEqual(item["attempt_count"], 2)
        self.assertEqual(item["status"], "SUCCEEDED")
        self.assertIsNone(item["error_message"])
        self.assertEqual(item["detail"], {"rows": 12})


class CoverageTest(unittest.TestCase):
    def test_window_ends_on_the_preceding_sunday(self):
        values = coverage(WEEK)
        self.assertEqual(values["depsdev_snapshot"], "2026-09-21")
        self.assertEqual(values["downloads_through"], "2026-09-20")
        self.assertEqual(values["downloads_window"], ["2026-09-07", "2026-09-20"])

    def test_blank_document_already_carries_coverage(self):
        """회차가 아직 시작되지 않아도 무엇을 담을 주인지는 정해져 있다."""
        self.assertEqual(blank(WEEK)["coverage"], coverage(WEEK))


class PurgeTest(unittest.TestCase):
    def _seed(self, s3, week, status):
        document = blank(week)
        document["status"] = status
        s3.objects[run_key(week)] = json.dumps(document).encode()

    def test_picks_only_finished_older_weeks(self):
        s3, state = build()
        self._seed(s3, date(2026, 8, 31), "SUCCEEDED")
        self._seed(s3, date(2026, 9, 7), "FAILED")      # 체크포인트가 남아 있어야 한다
        self._seed(s3, date(2026, 9, 14), "SUCCEEDED")
        self._seed(s3, WEEK, "RUNNING")                  # 지금 회차는 건드리지 않는다

        self.assertEqual(state.purgeable_weeks(WEEK, keep=1), [date(2026, 8, 31)])
        self.assertEqual(state.purgeable_weeks(WEEK, keep=2), [])

    def test_negative_keep_is_rejected(self):
        _, state = build()
        with self.assertRaises(ValueError):
            state.purgeable_weeks(WEEK, keep=-1)


if __name__ == "__main__":
    unittest.main()


class CorruptDocumentTest(unittest.TestCase):
    """빠진 값을 기본값으로 때우면 안 된다.

    status 를 None 으로 채우면 decide() 의 세 가드(RUNNING·SUCCEEDED·BLOCKED)를 전부
    빠져나가 "이어받기" 로 떨어진다. 이미 성공한 주를 23시간 들여 다시 받고 Bronze 에
    중복 업로드한다는 뜻이다.
    """

    def _load_with(self, payload):
        s3, state = build()
        s3.objects[run_key(WEEK)] = json.dumps(payload).encode()
        return state

    def test_missing_status_stops_instead_of_defaulting(self):
        state = self._load_with({"week_of": WEEK.isoformat()})
        with self.assertRaises(CorruptState):
            state.load(WEEK)

    def test_missing_week_of_stops(self):
        # 우편함 내용을 회차 경로에 잘못 쓴 경우가 이 모양이다.
        state = self._load_with({"requested_at": NOW.isoformat()})
        with self.assertRaises(CorruptState):
            state.load(WEEK)

    def test_message_names_what_is_missing(self):
        state = self._load_with({"status": "RUNNING"})
        with self.assertRaises(CorruptState) as caught:
            state.load(WEEK)
        self.assertIn("week_of", str(caught.exception))
