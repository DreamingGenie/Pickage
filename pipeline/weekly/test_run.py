"""실행기의 접합부 시험. 단계 구현도 MinIO 도 없이 돈다.

여기서 덮는 것은 하나다 — **공급자 지연이 실패로 세어지지 않는가.**

steps.py 가 종료 코드 3을 StepNotReady 로 바꾸는 것은 test_steps 가 덮고, 유예가
언제 끝나는지는 test_schedule 이 덮는다. 둘을 잇는 코드는 run.py 에만 있고, 그게
깨지면 deps.dev 가 두 시간 늦는 것만으로 회차가 BLOCKED 가 된다. 그 상태를 알려 주는
알림이 없어서 **다음 주 화요일까지 아무도 모르고**, 그동안 다음 회차가 그 구멍을 메워
주지도 않는다 — 주간 모드는 week_of 에서 유도한 14일 창만 받는다. 사람이 알아채고 그
주차를 다시 돌려야 하는데, npm 개별 호출의 구간 상한이 18개월이라 그마저도 무한하지 않다.

시각을 주입하지 않고 회차 날짜로 유예 전후를 가른다 — 먼 미래 주차는 유예가 남아 있고,
지난 주차는 유예가 끝나 있다. 실제 snapshot_grace_expired 를 그대로 태우게 된다.
"""
import json
import unittest
from datetime import date, datetime, timedelta, timezone

from . import run as runner
from .schedule import current_week_of
from .state import (CorruptState, ObjectStore, WeeklyState, blank, manual_key,
                    run_key)
from .steps import StepError, StepNotReady
from .test_state import FakeS3

FUTURE = date(2099, 1, 1)
FUTURE_WEEK = FUTURE - timedelta(days=FUTURE.weekday())   # 유예가 아직 남아 있다
PAST_WEEK = date(2026, 9, 7)                              # 유예가 끝난 지 오래다


class _Harness:
    """open_store 와 HANDLERS 를 갈아 끼우고 결과 문서를 돌려준다."""

    def __init__(self, test, error):
        self.s3 = FakeS3()
        test.enterContext(_patch(runner, "open_store", lambda bucket=None: ObjectStore(self.s3)))
        test.enterContext(_patch(runner, "HANDLERS",
                                 {step: self._raise for step in runner.STEPS}))
        self.error = error

    def _raise(self, context):
        if self.error is None:
            return {"ok": True}      # error 를 주지 않으면 단계는 멀쩡히 끝난다
        raise self.error

    def document(self, week):
        import json
        return json.loads(self.s3.objects[run_key(week)].decode("utf-8"))


class _patch:
    def __init__(self, module, name, value):
        self.module, self.name, self.value = module, name, value

    def __enter__(self):
        self.original = getattr(self.module, self.name)
        setattr(self.module, self.name, self.value)
        return self.value

    def __exit__(self, *_):
        setattr(self.module, self.name, self.original)
        return False


class ProviderDelayTest(unittest.TestCase):
    def test_delay_inside_grace_is_not_a_failure(self):
        harness = _Harness(self, StepNotReady("파티션이 아직 없다"))
        code = runner.main(["--force", "--week-of", FUTURE_WEEK.isoformat()])

        self.assertEqual(code, 0, "기다리는 중에는 실패 종료 코드를 내면 안 된다")
        document = harness.document(FUTURE_WEEK)
        self.assertEqual(document["status"], "PENDING")
        self.assertEqual(document["consecutive_failures"], 0)
        first = document["steps"][0]
        self.assertEqual(first["status"], "SKIPPED")
        self.assertEqual(first["detail"], {"reason": "source_not_ready"})

    def test_delay_past_grace_becomes_a_failure(self):
        """무한정 기다리지는 않는다. 유예를 넘기면 사람이 볼 일이다."""
        harness = _Harness(self, StepNotReady("파티션이 아직 없다"))
        code = runner.main(["--force", "--week-of", PAST_WEEK.isoformat()])

        self.assertEqual(code, 1)
        document = harness.document(PAST_WEEK)
        self.assertEqual(document["status"], "FAILED")
        self.assertEqual(document["consecutive_failures"], 1)
        self.assertEqual(document["steps"][0]["status"], "FAILED")

    def test_real_failure_still_counts(self):
        """기다려도 해결되지 않는 중단은 그대로 실패다."""
        harness = _Harness(self, StepError("행 수가 맞지 않는다"))
        code = runner.main(["--force", "--week-of", FUTURE_WEEK.isoformat()])

        self.assertEqual(code, 1)
        document = harness.document(FUTURE_WEEK)
        self.assertEqual(document["status"], "FAILED")
        self.assertEqual(document["consecutive_failures"], 1)
        self.assertEqual(document["last_error"],
                         "depsdev_t2: 행 수가 맞지 않는다")


class WeekArgumentTest(unittest.TestCase):
    def test_non_monday_is_rejected(self):
        """회차 식별과 run_id 규약이 월요일에 묶여 있다."""
        self.assertEqual(runner.main(["--week-of", "2026-09-15"]), 2)


if __name__ == "__main__":
    unittest.main()


class AbandonTest(unittest.TestCase):
    """단계 **밖에서** 터졌을 때 회차를 RUNNING 으로 버려 두지 않는다.

    버려 두면 다음 발화부터 decide() 가 "다른 실행이 진행 중" 으로 판단해
    STALE_RUNNING(26시간) 동안 아무것도 하지 않는다. 화요일 창에 걸리면 그 주 갱신이
    하루 늦는데, 로그에는 "진행 중" 만 찍혀서 정상처럼 보인다.
    """

    def test_storage_failure_lands_as_failed(self):
        # 단계는 멀쩡히 끝나는데 **결과를 기록하는 쪽**이 터진다. 저장소가 재시도 창을
        # 넘겨 죽어 있는 경우다.
        harness = _Harness(self, None)
        calls = {"n": 0}

        def explode(self, week_of, step, status, **kwargs):
            calls["n"] += 1
            raise RuntimeError("PUT 실패")

        self.enterContext(_patch(runner.WeeklyState, "step_finish", explode))
        # --dry-run 을 쓰지 않는다. 이제 그 옵션은 상태 객체에 아무것도 쓰지 않으므로
        # 여기서 보려는 "버려진 회차가 FAILED 로 내려앉는가" 를 확인할 수 없다.
        # 단계는 _Harness 가 HANDLERS 를 갈아 끼워 이미 가짜다.
        code = runner.main(["--force", "--keep-weeks", "-1",
                            "--week-of", FUTURE_WEEK.isoformat()])

        self.assertEqual(code, 1)
        self.assertEqual(calls["n"], 1, "첫 단계 기록에서 터져야 한다")
        document = harness.document(FUTURE_WEEK)
        # RUNNING 으로 버려 두지 않는다 — 그러면 26시간 잠긴다.
        self.assertEqual(document["status"], "FAILED")
        self.assertIn("실행기 중단", document["last_error"])

    def test_corrupt_state_is_not_overwritten(self):
        # 손상은 사람이 고쳐야 한다. fail() 로 덮어쓰면 증거가 사라진다.
        harness = _Harness(self, None)
        self.enterContext(_patch(runner.WeeklyState, "step_start", _raise_corrupt))
        with self.assertRaises(CorruptState):
            runner.main(["--force", "--keep-weeks", "-1",
                         "--week-of", FUTURE_WEEK.isoformat()])
        self.assertEqual(harness.document(FUTURE_WEEK)["status"], "RUNNING")


def _raise_corrupt(self, *args, **kwargs):
    raise CorruptState("회차 객체에 status 가 없다")


class DryRunTest(unittest.TestCase):
    """드라이런이 운영 회차를 건드리지 않는가. **그리고 판정은 끝까지 흉내 내는가.**

    앞을 놓치면 드라이런 한 번에 그 주 수집이 통째로 건너뛰어진다 — 돌리지도 않은 6단계가
    SUCCEEDED 로 적히고 decide() 가 "이미 끝났다" 로 본다. 운영 README 의 설치 절차가
    타이머를 켜기 전에 드라이런을 돌리게 하므로 그 절차가 곧 사고 경로였다.

    뒤를 놓치면 드라이런이 쓸모없어진다. 실행기는 마지막에 저장소를 다시 읽어 회차가
    끝났는지 보는데, 쓴 것이 안 보이면 늘 "남은 단계가 있다" 로 끝난다.
    """

    def test_nothing_is_written_but_the_decision_completes(self):
        harness = _Harness(self, None)
        staged = {}
        original = runner.StagedStore
        self.enterContext(_patch(runner, "StagedStore",
                                 lambda inner: staged.setdefault("it", original(inner))))

        code = runner.main(["--force", "--dry-run", "--keep-weeks", "-1",
                            "--week-of", PAST_WEEK.isoformat()])

        self.assertEqual(code, 0)
        self.assertEqual(harness.s3.objects, {}, "운영 객체에 쓰면 안 된다")
        document = staged["it"].staged[run_key(PAST_WEEK)]
        self.assertEqual(document["status"], "SUCCEEDED", "판정은 끝까지 가야 한다")


class ManualElsewhereTest(unittest.TestCase):
    """지난 회차의 수동 실행 요청을 집어 가는가.

    타이머는 이번 주만 본다. 그래서 주가 넘어가면 지난 회차의 요청이 **영원히 읽히지
    않는다** — BLOCKED 를 푸는 유일한 수단이 그 요청이므로 회차를 되살릴 방법이 없어진다.
    그동안 백엔드는 200 과 manual_pending=true 를 돌려주므로 요청한 사람은 모른다.
    """

    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.current = current_week_of(self.now)
        self.previous = self.current - timedelta(days=7)

    def _ask(self, harness, week):
        harness.s3.objects[manual_key(week)] = json.dumps(
            {"requested_at": self.now.isoformat()}).encode("utf-8")

    def test_previous_week_request_is_claimed(self):
        harness = _Harness(self, None)
        # 이번 주는 할 일이 없다.
        done = blank(self.current)
        done["status"] = "SUCCEEDED"
        harness.s3.objects[run_key(self.current)] = json.dumps(done).encode("utf-8")
        self._ask(harness, self.previous)

        self.assertEqual(runner.main(["--keep-weeks", "-1"]), 0)

        document = harness.document(self.previous)
        self.assertEqual(document["status"], "SUCCEEDED")
        self.assertIsNotNone(document["manual_claimed_at"], "집어 간 표시가 남아야 한다")

    def test_this_week_comes_first(self):
        """러너는 한 번에 한 회차만 돈다. 이번 주가 밀리면 안 된다."""
        harness = _Harness(self, None)
        self._ask(harness, self.current)
        self._ask(harness, self.previous)

        self.assertEqual(runner.main(["--keep-weeks", "-1"]), 0)

        self.assertIn(run_key(self.current), harness.s3.objects)
        self.assertNotIn(run_key(self.previous), harness.s3.objects)


class ForceTest(unittest.TestCase):
    """--force 가 지우는 범위.

    안 지우면: 강제 재실행이 중간에 실패했을 때 뒤 단계의 옛 SUCCEEDED 가 남고, 다음
    발화가 그것을 건너뛴다 — 새로 받은 상류 산출물 위에 **이전 회차의 입고 결과가
    최신인 척** 남는다.

    너무 지우면: `--force --only` 가 앞 단계 기록까지 날려 다음 발화가 23시간짜리 수집을
    처음부터 다시 돈다.
    """

    def _done(self, harness, week):
        document = blank(week)
        document["status"] = "SUCCEEDED"
        document["steps"] = [{"step": name, "status": "SUCCEEDED", "attempt_count": 1,
                              "started_at": None, "finished_at": None,
                              "error_message": None, "detail": {}}
                             for name in runner.STEPS]
        harness.s3.objects[run_key(week)] = json.dumps(document).encode("utf-8")

    def _steps(self, harness, week):
        return {item["step"]: item["status"] for item in harness.document(week)["steps"]}

    def test_failure_does_not_leave_stale_success_downstream(self):
        harness = _Harness(self, None)
        self._done(harness, PAST_WEEK)
        second = runner.STEPS[1]
        self.enterContext(_patch(
            runner, "HANDLERS",
            {name: (_boom if name == second else (lambda ctx: {"ok": True}))
             for name in runner.STEPS}))

        self.assertEqual(runner.main(["--force", "--keep-weeks", "-1",
                                      "--week-of", PAST_WEEK.isoformat()]), 1)

        left = self._steps(harness, PAST_WEEK)
        self.assertEqual(left[runner.STEPS[0]], "SUCCEEDED")
        self.assertEqual(left[second], "FAILED")
        for name in runner.STEPS[2:]:
            self.assertNotIn(name, left, f"{name}: 옛 성공이 남으면 다음 발화가 건너뛴다")

    def test_only_does_not_clear_the_other_steps(self):
        harness = _Harness(self, None)
        self._done(harness, PAST_WEEK)
        last = runner.STEPS[-1]

        self.assertEqual(runner.main(["--force", "--only", last, "--keep-weeks", "-1",
                                      "--week-of", PAST_WEEK.isoformat()]), 0)

        left = self._steps(harness, PAST_WEEK)
        self.assertEqual(len(left), len(runner.STEPS), "앞 단계 기록까지 지우면 안 된다")
        self.assertEqual(harness.document(PAST_WEEK)["status"], "SUCCEEDED")


def _boom(ctx):
    raise StepError("행 수가 맞지 않는다")
