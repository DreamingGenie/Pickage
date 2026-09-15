"""주간 회차 날짜 규약과 판정 시험.

여기가 깨지면 같은 주를 두 번 받거나 한 주를 통째로 건너뛴다. 둘 다 조용히 일어나고,
건너뛴 주는 **다음 회차가 메우지 않는다** — 주간 모드는 week_of 에서 유도한 14일 창만
받기 때문이다. 사람이 알아채고 그 주차를 다시 돌려야 한다.
"""
import unittest
from datetime import date, datetime, timedelta, timezone

from pipeline.weekly import schedule as s

UTC = timezone.utc
# 2026-09-21 은 월요일이다. 이 파일의 모든 예는 그 주를 쓴다.
WEEK = date(2026, 9, 21)


def utc(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


class WeekOfTests(unittest.TestCase):
    def test_monday_belongs_to_its_own_week(self):
        self.assertEqual(s.current_week_of(utc(2026, 9, 21, 0, 0)), WEEK)

    def test_sunday_belongs_to_the_previous_monday(self):
        self.assertEqual(s.current_week_of(utc(2026, 9, 27, 23, 59)), WEEK)

    def test_week_is_decided_in_utc_not_local_time(self):
        # 월요일 08:00 KST = 일요일 23:00 UTC. deps.dev 스냅샷 날짜가 UTC 이므로 지난 주다.
        monday_morning_kst = datetime(2026, 9, 21, 8, 0, tzinfo=s.KST)
        self.assertEqual(s.current_week_of(monday_morning_kst), date(2026, 9, 14))

    def test_naive_datetime_is_refused(self):
        with self.assertRaises(ValueError):
            s.current_week_of(datetime(2026, 9, 21, 0, 0))


class WindowTests(unittest.TestCase):
    def test_run_day_is_tuesday(self):
        self.assertEqual(s.run_day(WEEK), date(2026, 9, 22))

    def test_window_ends_on_the_sunday_before_the_snapshot(self):
        # 화 10:00 KST(= 01:00 UTC)에 npm 이 확정한 마지막 날. 수집기 기본값(utcnow-2일)과 같다.
        self.assertEqual(s.window_end(WEEK), date(2026, 9, 20))

    def test_window_is_fourteen_days(self):
        self.assertEqual(s.window_start(WEEK), date(2026, 9, 7))
        self.assertEqual((s.window_end(WEEK) - s.window_start(WEEK)).days + 1, 14)

    def test_consecutive_weeks_overlap_by_seven_days(self):
        previous = WEEK - timedelta(days=7)
        self.assertEqual(s.window_end(previous), date(2026, 9, 13))
        overlap = s.window_end(previous) - s.window_start(WEEK)
        self.assertEqual(overlap.days + 1, 7)

    def test_window_opens_tuesday_ten_kst(self):
        self.assertFalse(s.window_open(WEEK, datetime(2026, 9, 22, 9, 59, tzinfo=s.KST)))
        self.assertTrue(s.window_open(WEEK, datetime(2026, 9, 22, 10, 0, tzinfo=s.KST)))

    def test_window_stays_open_later_in_the_week(self):
        self.assertTrue(s.window_open(WEEK, utc(2026, 9, 24, 3, 0)))

    def test_window_is_closed_on_the_snapshot_monday(self):
        # 스냅샷은 월요일 21:01 UTC 에 나온다. 그 전에 받으러 가면 파티션이 없다.
        self.assertFalse(s.window_open(WEEK, utc(2026, 9, 21, 23, 0)))


class SnapshotGraceTests(unittest.TestCase):
    """공급자 지연을 언제까지 기다리고 언제 실패로 올리는가.

    너무 짧으면 deps.dev 가 두 시간 늦는 것만으로 사람을 부르고(알림도 없어서 한 주를
    통째로 놓친다), 너무 길면 진짜 고장을 며칠 뒤에 안다.
    """

    def test_grace_is_measured_from_the_window_not_from_the_first_try(self):
        # 타이머가 멈춰 있다가 늦게 깨어났다고 유예가 늘어나면 안 된다.
        self.assertEqual(s.window_open_at(WEEK),
                         datetime(2026, 9, 22, 10, 0, tzinfo=s.KST))

    def test_inside_the_grace_we_keep_waiting(self):
        self.assertFalse(s.snapshot_grace_expired(WEEK, datetime(2026, 9, 22, 21, 59, tzinfo=s.KST)))

    def test_after_the_grace_it_becomes_a_failure(self):
        # 화 10:00 KST + 12h = 화 22:00 KST
        self.assertTrue(s.snapshot_grace_expired(WEEK, datetime(2026, 9, 22, 22, 0, tzinfo=s.KST)))

    def test_grace_length_is_twelve_hours(self):
        self.assertEqual(s.SNAPSHOT_GRACE, timedelta(hours=12))


class IdentifierTests(unittest.TestCase):
    def test_download_run_is_derived_from_the_week_not_today(self):
        self.assertEqual(s.download_run(WEEK), "2026-09-22")

    def test_bronze_run_ids_are_deterministic(self):
        self.assertEqual(s.bronze_run_id(WEEK, "bronze"), "bronze-weekly-20260921")
        self.assertEqual(s.bronze_run_id(WEEK, "downloads"), "downloads-weekly-20260921")

    def test_unknown_source_is_refused(self):
        with self.assertRaises(ValueError):
            s.bronze_run_id(WEEK, "curated")


class ManualPendingTests(unittest.TestCase):
    def record(self, **kwargs):
        return s.RunRecord(week_of=WEEK, status=kwargs.pop("status", "FAILED"), **kwargs)

    def test_no_request_is_not_pending(self):
        self.assertFalse(self.record().manual_pending)

    def test_unclaimed_request_is_pending(self):
        self.assertTrue(self.record(manual_request_at=utc(2026, 9, 22, 2)).manual_pending)

    def test_request_after_the_last_claim_is_pending(self):
        self.assertTrue(self.record(manual_request_at=utc(2026, 9, 22, 5),
                                    manual_claimed_at=utc(2026, 9, 22, 2)).manual_pending)

    def test_claimed_request_is_not_pending(self):
        self.assertFalse(self.record(manual_request_at=utc(2026, 9, 22, 2),
                                     manual_claimed_at=utc(2026, 9, 22, 5)).manual_pending)


class DecideTests(unittest.TestCase):
    OPEN = datetime(2026, 9, 22, 11, 0, tzinfo=s.KST)
    CLOSED = datetime(2026, 9, 22, 9, 0, tzinfo=s.KST)

    def record(self, status, **kwargs):
        return s.RunRecord(week_of=WEEK, status=status, **kwargs)

    def test_no_record_before_the_window_does_nothing(self):
        self.assertFalse(s.decide(None, WEEK, self.CLOSED).run)

    def test_no_record_after_the_window_runs(self):
        self.assertTrue(s.decide(None, WEEK, self.OPEN).run)

    def test_finished_week_is_left_alone(self):
        self.assertFalse(s.decide(self.record("SUCCEEDED"), WEEK, self.OPEN).run)

    def test_manual_request_reruns_a_finished_week(self):
        decision = s.decide(
            self.record("SUCCEEDED", manual_request_at=utc(2026, 9, 23)), WEEK, self.OPEN)
        self.assertTrue(decision.run)
        self.assertTrue(decision.claim_manual)

    def test_a_live_run_is_not_disturbed(self):
        record = self.record("RUNNING", started_at=utc(2026, 9, 22, 1))
        self.assertFalse(s.decide(record, WEEK, utc(2026, 9, 22, 20)).run)

    def test_a_run_that_stopped_long_ago_is_recovered(self):
        record = self.record("RUNNING", started_at=utc(2026, 9, 22, 1))
        self.assertTrue(s.decide(record, WEEK, utc(2026, 9, 23, 4)).run)

    def test_running_without_a_start_time_is_recovered(self):
        self.assertTrue(s.decide(self.record("RUNNING"), WEEK, self.OPEN).run)

    def test_blocked_waits_for_a_person(self):
        record = self.record("BLOCKED", consecutive_failures=10)
        decision = s.decide(record, WEEK, self.OPEN)
        self.assertFalse(decision.run)
        self.assertIn("10", decision.reason)

    def test_manual_request_releases_blocked(self):
        record = self.record("BLOCKED", consecutive_failures=10,
                             manual_request_at=utc(2026, 9, 23))
        decision = s.decide(record, WEEK, self.OPEN)
        self.assertTrue(decision.run)
        self.assertTrue(decision.claim_manual)

    def test_failed_run_resumes_inside_the_window(self):
        self.assertTrue(s.decide(self.record("FAILED"), WEEK, self.OPEN).run)

    def test_failed_run_waits_for_the_window(self):
        self.assertFalse(s.decide(self.record("FAILED"), WEEK, self.CLOSED).run)

    def test_manual_request_ignores_the_window(self):
        record = self.record("FAILED", manual_request_at=utc(2026, 9, 22))
        self.assertTrue(s.decide(record, WEEK, self.CLOSED).run)

    def test_force_ignores_everything_but_a_live_run(self):
        self.assertTrue(s.decide(self.record("SUCCEEDED"), WEEK, self.CLOSED, force=True).run)
        self.assertTrue(s.decide(None, WEEK, self.CLOSED, force=True).run)

    def test_force_does_not_push_aside_a_live_run(self):
        # 밀어내면 같은 checkpoint.sqlite 를 두 프로세스가 쓰고 같은 IP 에서 npm 을 두 배로
        # 두드린다. flock 은 셸 래퍼에만 있어 python -m 직접 실행은 이 판정이 유일한 방어다.
        record = self.record("RUNNING", started_at=utc(2026, 9, 22, 1))
        self.assertFalse(s.decide(record, WEEK, utc(2026, 9, 22, 20), force=True).run)

    def test_force_still_recovers_a_dead_run(self):
        record = self.record("RUNNING", started_at=utc(2026, 9, 22, 1))
        self.assertTrue(s.decide(record, WEEK, utc(2026, 9, 23, 4), force=True).run)


if __name__ == "__main__":
    unittest.main()
