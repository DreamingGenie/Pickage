"""판정 규칙 시험 — 보고서 조각 → findings. 화면이 보여 주는 "정상/주의/문제" 가 여기서 정해진다."""
import unittest
from datetime import datetime, timedelta, timezone

from . import verdict

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)


def iso(delta: timedelta) -> str:
    return (NOW + delta).isoformat(timespec="seconds")


def kinds(findings, level=None):
    return [(f["level"], f["kind"], f["ref"]) for f in findings if level is None or f["level"] == level]


class WeeklyTest(unittest.TestCase):
    def report(self, runs, expected=None, stale_hours=26):
        return {"node": "data", "weekly": {"runs": runs, "expected": expected or {"missing": False}, "stale_running_hours": stale_hours}}

    def test_healthy_run_has_no_findings(self):
        out = verdict.evaluate(self.report([{"week_of": "2026-09-21", "status": "SUCCEEDED"}]), now=NOW)
        self.assertEqual(out, [])

    def test_missing_current_week_warn_then_bad_after_six_hours(self):
        ex = {"missing": True, "week_of": "2026-09-21", "window_open_at": iso(-timedelta(hours=2))}
        out = verdict.evaluate(self.report([], ex), now=NOW)
        self.assertEqual(kinds(out), [("warn", "weekly-missing", "expected:2026-09-21")])
        ex["window_open_at"] = iso(-timedelta(hours=7))
        out = verdict.evaluate(self.report([], ex), now=NOW)
        self.assertEqual(kinds(out), [("bad", "weekly-missing", "expected:2026-09-21")])
        self.assertIn("systemctl list-timers", out[0]["text"])

    def test_past_blocked_without_manual_is_bad_with_manual_is_warn(self):
        runs = [{"week_of": "2026-09-21", "status": "SUCCEEDED"},
                {"week_of": "2026-09-14", "status": "BLOCKED", "consecutive_failures": 10, "manual": {"pending": False}}]
        out = verdict.evaluate(self.report(runs), now=NOW)
        self.assertEqual(kinds(out), [("bad", "weekly-blocked", "2026-09-14")])
        self.assertIn("되살릴 길", out[0]["text"])
        runs[1]["manual"] = {"pending": True}
        out = verdict.evaluate(self.report(runs), now=NOW)
        self.assertEqual(kinds(out), [("warn", "weekly-blocked", "2026-09-14")])   # 수동 요청 미처리와 겹치지 않는다

    def test_latest_blocked_and_failed(self):
        out = verdict.evaluate(self.report([{"week_of": "2026-09-21", "status": "BLOCKED", "consecutive_failures": 10}]), now=NOW)
        self.assertEqual(kinds(out), [("bad", "weekly-blocked", "2026-09-21")])
        out = verdict.evaluate(self.report([{"week_of": "2026-09-21", "status": "FAILED", "consecutive_failures": 2}]), now=NOW)
        self.assertEqual(kinds(out), [("warn", "weekly-failed", "2026-09-21")])
        self.assertIn("10분 뒤", out[0]["text"])

    def test_past_failed_has_no_auto_retry(self):
        runs = [{"week_of": "2026-09-21", "status": "RUNNING", "started_at": iso(-timedelta(hours=1))},
                {"week_of": "2026-09-14", "status": "FAILED"}]
        out = verdict.evaluate(self.report(runs), now=NOW)
        self.assertEqual(kinds(out), [("warn", "weekly-failed", "2026-09-14")])
        self.assertIn("자동 재시도가 없습니다", out[0]["text"])

    def test_stale_running_uses_runner_threshold(self):
        run = {"week_of": "2026-09-21", "status": "RUNNING", "started_at": iso(-timedelta(hours=27))}
        self.assertEqual(kinds(verdict.evaluate(self.report([run]), now=NOW)), [("warn", "weekly-stale", "2026-09-21")])
        self.assertEqual(verdict.evaluate(self.report([run], stale_hours=30), now=NOW), [])       # 실행기 기준이 30h 면 아직 아니다

    def test_manual_pending_on_running(self):
        run = {"week_of": "2026-09-21", "status": "RUNNING", "started_at": iso(-timedelta(hours=1)), "manual": {"pending": True}}
        self.assertEqual(kinds(verdict.evaluate(self.report([run]), now=NOW)), [("warn", "weekly-manual", "2026-09-21")])


class CuratedTest(unittest.TestCase):
    def test_dispatcher_blocked_failed_stale(self):
        cur = {"dispatcher": {"status": "FAILED", "error": {"message": "no baseline"}},
               "runs": [{"snapshot": "2026-09-21", "status": "BLOCKED", "phase": "downloads", "stages": []},
                        {"snapshot": "2026-09-14", "status": "FAILED", "attempt": 2, "consecutive_failures": 2,
                         "next_retry_at": iso(timedelta(minutes=20)), "stages": [{"stage": "downloads", "status": "FAILED"}]},
                        {"snapshot": "2026-09-07", "status": "RUNNING", "started_at": iso(-timedelta(hours=40)), "stages": []},
                        {"snapshot": "2026-08-31", "status": "COMPLETE", "stages": []}]}
        out = verdict.evaluate({"node": "data", "curated": cur}, now=NOW)
        self.assertEqual(kinds(out), [("bad", "curated-blocked", "2026-09-21"),
                                      ("warn", "curated-dispatcher", "_dispatcher"),
                                      ("warn", "curated-failed", "2026-09-14"),
                                      ("warn", "curated-stale", "2026-09-07")])
        self.assertIn("다운로드 단계", out[0]["text"])
        self.assertIn("0.3시간 뒤", out[2]["text"])                                   # 미래 시각은 "뒤" 로


class EventsTest(unittest.TestCase):
    def test_discovery_disconnect_and_full(self):
        ev = {"discovery": {"pending": True, "attempts": 3, "error": "refused"},
              "buckets": {"pickage-raw": {"connected": False, "error": "reset"}, "pickage-curated": {"connected": True}},
              "held": 20000, "max_events": 20000, "full": True, "dropped": 12}
        out = verdict.evaluate({"node": "data", "minio": {"events": ev}}, now=NOW)
        self.assertEqual(kinds(out), [("warn", "events-discovery", "_discovery"),
                                      ("warn", "events-disconnected", "pickage-raw"),
                                      ("warn", "events-full", "_buffer")])
        self.assertIn("12건", out[2]["text"])

    def test_full_by_count_even_without_flag(self):
        ev = {"buckets": {}, "held": 5, "max_events": 5}
        self.assertEqual(kinds(verdict.evaluate({"node": "data", "minio": {"events": ev}}, now=NOW)), [("warn", "events-full", "_buffer")])


class LocalTest(unittest.TestCase):
    def test_disk_thresholds_and_log_threshold(self):
        local = {"paths": [{"label": "/a", "missing": True},
                           {"label": "/b", "disk": {"total": 100, "used": 95}},
                           {"label": "/c", "disk": {"total": 100, "used": 85}},
                           {"label": "/d", "disk": {"total": 100, "used": 50}}],
                 "logs": [{"path": "/x.log", "error_lines": 1}, {"path": "/y.log", "error_lines": 0}],
                 "error_min_lines": 1}
        out = verdict.evaluate({"node": "data", "local": local}, now=NOW)
        self.assertEqual(kinds(out), [("bad", "disk-free", "/b"), ("warn", "disk-missing", "/a"),
                                      ("warn", "disk-free", "/c"), ("warn", "log-error", "/x.log")])
        local["error_min_lines"] = 2
        self.assertNotIn("log-error", [f["kind"] for f in verdict.evaluate({"node": "data", "local": local}, now=NOW)])
        local["error_min_lines"] = 0                                                   # 0 = 올리지 않는다
        self.assertNotIn("log-error", [f["kind"] for f in verdict.evaluate({"node": "data", "local": local}, now=NOW)])


class DockerTest(unittest.TestCase):
    def container(self, name, state, **extra):
        return {"name": name, "state": state, "exit_code": 0, "oom_killed": False, "health": None, "log": {"error_lines": 0, "since_hours": 6}, **extra}

    def test_states(self):
        cs = [self.container("paused", "paused"), self.container("created", "created"), self.container("dead", "dead"),
              self.container("restart", "restarting"), self.container("exit0", "exited"), self.container("exit1", "exited", exit_code=1,
              finished_at=iso(-timedelta(hours=1))), self.container("run", "running", health="healthy"), self.container("weird", "frobnicating"),
              self.container("removing", "removing"), self.container("oom", "exited", exit_code=137, oom_killed=True),
              self.container("sick", "running", health="unhealthy")]
        out = verdict.evaluate({"node": "app", "docker": {"containers": cs, "error_min_lines": 3}}, now=NOW)
        self.assertEqual(kinds(out, "bad"), [("bad", "container", "paused"), ("bad", "container", "dead"), ("bad", "container", "restart"),
                                             ("bad", "container-oom", "oom"), ("bad", "container-health", "sick")])
        self.assertEqual(kinds(out, "warn"), [("warn", "container", "created"), ("warn", "container", "exit1"),
                                              ("warn", "container", "weird"), ("warn", "container", "oom")])
        self.assertIn("1.0시간 전", next(f["text"] for f in out if f["ref"] == "exit1"))

    def test_log_threshold_for_containers(self):
        two = self.container("api", "running", log={"error_lines": 2, "since_hours": 6})
        five = self.container("api", "running", log={"error_lines": 5, "since_hours": 6})
        self.assertEqual(verdict.evaluate({"node": "app", "docker": {"containers": [two], "error_min_lines": 3}}, now=NOW), [])
        out = verdict.evaluate({"node": "app", "docker": {"containers": [five], "error_min_lines": 3}}, now=NOW)
        self.assertEqual(kinds(out), [("warn", "log-error", "api")])
        self.assertIn("error_ignore_pattern", out[0]["text"])


class ShapeTest(unittest.TestCase):
    def test_report_errors_and_ordering_and_worst(self):
        report = {"node": "data", "errors": [{"section": "docker", "message": "socket"}],
                  "weekly": {"runs": [{"week_of": "2026-09-21", "status": "BLOCKED"}], "expected": {}},
                  "local": {"logs": [{"path": "/x.log", "error_lines": 3}], "error_min_lines": 1}}
        out = verdict.evaluate(report, now=NOW)
        self.assertEqual([f["level"] for f in out], ["bad", "warn", "warn"])           # 빨간 것이 먼저
        self.assertEqual(out[1]["section"], "node-data")                                # 보고서 절 실패는 노드 줄로
        self.assertEqual(verdict.worst(out), "bad")
        self.assertEqual(verdict.worst([]), "ok")
        self.assertEqual(verdict.worst([{"level": "warn"}]), "warn")
        for f in out:
            self.assertEqual(set(f), {"level", "kind", "section", "ref", "text"})

    def test_empty_report_is_fine(self):
        self.assertEqual(verdict.evaluate({"node": "app"}, now=NOW), [])


if __name__ == "__main__":
    unittest.main()
