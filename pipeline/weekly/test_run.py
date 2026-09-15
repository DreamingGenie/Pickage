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
import unittest
from datetime import date, timedelta

from . import run as runner
from .state import ObjectStore, WeeklyState, run_key
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
