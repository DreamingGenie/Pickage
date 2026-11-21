"""downloads 수집기가 실패한 작업을 다시 받는가 (S15P21A506-367).

  .venv-bq/Scripts/python.exe -m unittest discover -s pipeline/collectors/downloads -v

npm API 는 부르지 않는다. `requests.Session` 자리에 URL 별로 응답을 정해 둔 가짜를 끼우고
`time.sleep` 을 없앤 뒤 `main()` 을 실제 인자로 돌린다. 체크포인트·manifest 는 임시 폴더의 진짜 파일이다.

이 시험이 깨지면 알게 되는 것:
  - 실패한 작업이 다시 끝 상태가 됐다 — 같은 run 을 다시 돌려도 그 패키지의 그 구간은 영영 비어 있다.
    주간 회차는 종료 코드 0 으로 끝나 SUCCEEDED 가 되므로 아무도 모른다.
  - 다시 받은 작업이 시도 횟수를 물려받아 첫 오류에 바로 포기한다
  - 실패가 남았는데 --max-failed 가 0 이 아닌 종료 코드를 내지 않는다
"""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import collect  # noqa: E402

END = "2026-09-13"
START = "2026-08-31"   # 주간 창 = 끝에서 13일 전


class Response:
    def __init__(self, status, body=None, text=""):
        self.status_code, self._body, self.text = status, body, text

    def json(self):
        return self._body


def ok(name):
    return Response(200, {"package": name, "start": START, "end": END,
                          "downloads": [{"downloads": 5, "day": START}]})


class FakeSession:
    """패키지 이름이 URL 끝에 오므로 이름으로 대본을 고른다. 대본이 떨어지면 마지막 응답을 되풀이한다."""

    def __init__(self, scripts):
        self.scripts = {k: list(v) for k, v in scripts.items()}
        self.calls = []
        self.headers = {}

    def get(self, url, timeout=None):
        name = url.rsplit("/", 1)[-1]
        self.calls.append(name)
        script = self.scripts[name]
        return script.pop(0) if len(script) > 1 else script[0]


class Harness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.targets = os.path.join(self.tmp, "targets.csv")
        # 스코프 패키지 둘 — 벌크로 묶이지 않고 작업 하나씩이 된다.
        with open(self.targets, "w", encoding="utf-8") as f:
            f.write("rank,name,status\n1,@a/one,\n2,@a/two,\n")

    def run_collect(self, scripts, *extra):
        session = FakeSession(scripts)
        argv = ["collect.py", "--targets", self.targets, "--run", "t", "--mode", "weekly",
                "--end", END, "--out", self.tmp, *extra]
        code = 0
        with mock.patch.object(collect.requests, "Session", lambda: session), \
                mock.patch.object(collect.time, "sleep", lambda s: None), \
                mock.patch.object(collect, "UA_CONTACT", "test@example.invalid"), \
                mock.patch.object(sys, "argv", argv), \
                redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            try:
                collect.main()
            except SystemExit as e:
                code = e.code
        return session, code

    def statuses(self):
        db = sqlite3.connect(os.path.join(self.tmp, "run=t", "checkpoint.sqlite"))
        try:
            return dict(db.execute("SELECT names, status FROM tasks").fetchall())
        finally:
            db.close()

    def status_of(self, name):
        return next(v for k, v in self.statuses().items() if name in k)

    def manifest(self):
        with open(os.path.join(self.tmp, "run=t", "manifest.json"), encoding="utf-8") as f:
            return json.load(f)


ONE, TWO = "@a%2Fone", "@a%2Ftwo"


class FailedTasksAreRetried(Harness):
    def test_rerun_picks_up_tasks_the_last_run_gave_up_on(self):
        """수집기를 다시 실행하는 것이 복구 수단이다. 예전에는 failed 를 고르지 않아 복구가 없었다."""
        _, code = self.run_collect({ONE: [ok("@a/one")], TWO: [Response(400, text="bad")]}, "--failed-passes", "0")
        self.assertEqual((code, self.status_of("@a/two")), (0, "failed"))

        session, _ = self.run_collect({ONE: [ok("@a/one")], TWO: [ok("@a/two")]}, "--failed-passes", "0")
        self.assertEqual(self.status_of("@a/two"), "done")
        # 끝난 작업은 다시 부르지 않는다. 다시 부르면 23시간짜리 회차가 재실행마다 처음부터 돈다.
        self.assertEqual(session.calls, [TWO])

    def test_end_of_run_pass_recovers_a_transient_failure_in_the_same_run(self):
        """5xx 네 번에 포기한 작업이 같은 실행의 끝에서 풀려 있으면 받는다."""
        down = Response(503, text="down")
        session, code = self.run_collect({ONE: [ok("@a/one")], TWO: [down, down, down, down, ok("@a/two")]})
        self.assertEqual((code, self.status_of("@a/two")), (0, "done"))
        self.assertEqual(session.calls.count(TWO), 5)
        self.assertEqual(self.manifest()["tasks_by_status"], {"done": 2})

    def test_retried_task_gets_a_fresh_attempt_budget(self):
        """시도 횟수를 물려받으면 다시 도는 바퀴가 첫 5xx 에 바로 포기해, 다시 도는 의미가 없다."""
        down = Response(503, text="down")
        session, _ = self.run_collect({ONE: [ok("@a/one")], TWO: [down] * 6 + [ok("@a/two")]})
        # 첫 바퀴 4번 + 끝 바퀴에서 5xx 두 번을 더 견디고 세 번째에 받는다.
        self.assertEqual(session.calls.count(TWO), 7)
        self.assertEqual(self.status_of("@a/two"), "done")


class ExitCode(Harness):
    def test_default_exit_code_stays_zero_but_manifest_names_what_is_missing(self):
        """주간 실행기는 이 종료 코드를 보고 단계를 닫는다. 기본 동작을 바꾸면 영구 실패 하나가 회차를 막는다."""
        _, code = self.run_collect({ONE: [ok("@a/one")], TWO: [Response(400, text="bad")]})
        self.assertEqual(code, 0)
        m = self.manifest()
        self.assertEqual(m["tasks_by_status"], {"done": 1, "failed": 1})
        self.assertEqual(len(m["failed_tasks"]), 1)

    def test_max_failed_turns_leftover_failures_into_a_nonzero_exit(self):
        scripts = {ONE: [ok("@a/one")], TWO: [Response(400, text="bad")]}
        _, code = self.run_collect(scripts, "--max-failed", "0")
        self.assertEqual(code, collect.EXIT_FAILED_TASKS)
        _, code = self.run_collect(scripts, "--max-failed", "1")
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
