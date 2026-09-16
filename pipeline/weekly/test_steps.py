"""단계가 넘기는 경로 규약 시험.

여기가 깨지면 23시간 수집을 마친 **뒤** 마지막 단계에서 죽는다. 드라이런은 CLI 를 아예
부르지 않아 이 계약을 검증하지 못하므로, 규칙 자체를 여기서 못 박는다.
"""
import ast
import json
import re
import shutil
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from pipeline.weekly.steps import (SNAPSHOT_NOT_READY_EXIT, T2_TABLES, Context, StepError,
                                   StepNotReady, _downloads_tasks, depsdev_t2, gcs_sync,
                                   purge_week)

WEEK = date(2026, 9, 21)


def context() -> Context:
    return Context(root=Path("C:/repo"), python="python", week_of=WEEK)


class ExecutionDirTests(unittest.TestCase):
    """pipeline/downloads/load.py 의 가드를 그대로 옮겨 온 회귀 시험."""

    def test_execution_dir_is_outside_the_source_root(self):
        ctx = context()
        source_root = ctx.weekly_root
        work_dir = ctx.execution_dir
        # load.py: if work_dir == source_root or source_root in work_dir.parents: raise
        self.assertNotEqual(work_dir, source_root)
        self.assertNotIn(source_root, work_dir.parents,
                         "--work-dir 가 --source-root 안이면 입고기가 거부한다. "
                         "보고서 파일이 source_root 안에 생기면 input.py 의 "
                         "'unknown regular file must be classified' 에도 걸린다")

    def test_execution_dir_is_per_week(self):
        other = Context(root=Path("C:/repo"), python="python", week_of=WEEK.replace(day=14))
        self.assertNotEqual(context().execution_dir, other.execution_dir)

    def test_weekly_root_is_per_week(self):
        # 백필과 루트를 공유하면 주간 갱신마다 6,200만 행을 다시 올린다.
        self.assertIn(WEEK.isoformat(), context().weekly_root.as_posix())

    def test_logs_stay_inside_the_source_root(self):
        # .log 는 입고기가 분류해 주므로 회차 루트 안에 둔다. 밖으로 옮길 이유가 없다.
        ctx = context()
        self.assertIn(ctx.weekly_root, ctx.log_dir.parents)


class PurgeTests(unittest.TestCase):
    """정리가 지워서는 안 될 것을 지우지 않는지 본다.

    깨지면 `data/raw` 의 T1 백필(projects 229 스냅샷, 2022년부터)이 날아간다. 그건
    BigQuery 를 50 GiB 다시 스캔해야 복구되고, 파일을 지운 뒤에는 알아챌 방법도 없다.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.ctx = Context(root=self.tmp, python="python", week_of=WEEK)

    def touch(self, path: Path) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        (path / "part-00000.parquet").write_bytes(b"x")
        return path

    def test_removes_only_the_named_week(self):
        mine = self.touch(self.ctx.weekly_root)
        mine_exec = self.touch(self.ctx.execution_dir)
        mine_raw = self.touch(self.ctx.data / "raw" / "requirements" / f"snapshot={WEEK}")
        # 같은 테이블의 다른 스냅샷 = T1 백필. 절대 건드리면 안 된다.
        backfill = self.touch(self.ctx.data / "raw" / "requirements" / "snapshot=2022-05-09")
        other_week = self.touch(self.ctx.data / "downloads-weekly" / "2026-09-14")

        removed = purge_week(self.ctx, WEEK)

        self.assertFalse(mine.exists())
        self.assertFalse(mine_exec.exists())
        self.assertFalse(mine_raw.exists())
        self.assertTrue(backfill.exists(), "T1 백필 스냅샷을 지웠다")
        self.assertTrue(other_week.exists(), "다른 회차를 지웠다")
        self.assertEqual(len(removed), 3)

    def test_sweeps_every_table_under_raw(self):
        for table in ("requirements", "versions_min", "projects"):
            self.touch(self.ctx.data / "raw" / table / f"snapshot={WEEK}")

        self.assertEqual(len(purge_week(self.ctx, WEEK)), 3)

    def test_missing_paths_are_not_an_error(self):
        self.assertEqual(purge_week(self.ctx, WEEK), [])

    def test_running_twice_is_safe(self):
        self.touch(self.ctx.weekly_root)
        purge_week(self.ctx, WEEK)
        self.assertEqual(purge_week(self.ctx, WEEK), [])


class NotReadyTests(unittest.TestCase):
    """"아직" 과 "실패" 를 가르는 계약.

    깨지면 공급자가 두 시간 늦는 것만으로 회차가 BLOCKED 가 되어 사람을 부른다. 게다가
    BLOCKED 를 알려 주는 알림이 없어서, 주간 배치가 한 주를 통째로 놓친 것을 다음 주까지
    아무도 모른다.
    """

    def test_exit_code_matches_the_collector(self):
        # 수집기 쪽 값이 바뀌면 "아직" 이 "실패" 로 둔갑한다. import 로 묶을 수 없어서
        # (그 모듈이 google.cloud 를 최상단에서 부른다) 소스에서 직접 읽어 대조한다.
        source = (Path(__file__).resolve().parents[2]
                  / "pipeline/collectors/bigquery/collect.py").read_text(encoding="utf-8")
        found = re.search(r"^EXIT_SNAPSHOT_NOT_READY = (\d+)$", source, re.M)
        self.assertIsNotNone(found, "collect.py 에 EXIT_SNAPSHOT_NOT_READY 가 없다")
        self.assertEqual(int(found.group(1)), SNAPSHOT_NOT_READY_EXIT)

    def test_that_exit_code_becomes_not_ready(self):
        ctx = Context(root=Path(tempfile.mkdtemp()), python=sys.executable, week_of=WEEK)
        self.addCleanup(shutil.rmtree, ctx.root, True)
        with self.assertRaises(StepNotReady):
            ctx.run("depsdev_t2", [sys.executable, "-c", f"raise SystemExit({SNAPSHOT_NOT_READY_EXIT})"],
                    not_ready_code=SNAPSHOT_NOT_READY_EXIT)

    def test_other_exit_codes_are_still_failures(self):
        # 예산 초과·행 수 불일치는 전부 1이다. 그건 사람이 봐야 하므로 실패로 남아야 한다.
        ctx = Context(root=Path(tempfile.mkdtemp()), python=sys.executable, week_of=WEEK)
        self.addCleanup(shutil.rmtree, ctx.root, True)
        with self.assertRaises(StepError):
            ctx.run("depsdev_t2", [sys.executable, "-c", "raise SystemExit(1)"],
                    not_ready_code=SNAPSHOT_NOT_READY_EXIT)

    def test_without_the_option_every_nonzero_is_a_failure(self):
        ctx = Context(root=Path(tempfile.mkdtemp()), python=sys.executable, week_of=WEEK)
        self.addCleanup(shutil.rmtree, ctx.root, True)
        with self.assertRaises(StepError):
            ctx.run("gcs_sync", [sys.executable, "-c",
                                 f"raise SystemExit({SNAPSHOT_NOT_READY_EXIT})"])


if __name__ == "__main__":
    unittest.main()


class T2CompletenessTests(unittest.TestCase):
    """T2 가 덜 올라온 회차를 성공으로 보지 않는가.

    수집기는 누적 예산을 넘기면 남은 테이블을 포기하고 **종료 코드 0으로** 끝난다
    (collect.py 의 stopped_budget). 종료 코드만 보면 성공이라, 세 테이블 중 하나만 받은
    회차가 그대로 Bronze 에 입고되고 SUCCEEDED 로 닫힌다.

    ⚠ 대조가 **depsdev_t2 안에** 있어야 한다. gcs_sync 로 미루면 depsdev_t2 가 SUCCEEDED
    로 남아 다음 발화가 수집기를 건너뛰고, 같은 실패만 열 번 반복해 BLOCKED 로 간다.
    """

    def _ctx(self, tables):
        listing = "\n".join(
            f"gs://oss-shift-a506-raw/raw/{name}/snapshot={WEEK}/_MANIFEST.json"
            for name in tables)

        class Fake(Context):
            def run(self, step, args, **kwargs):
                return {"returncode": 0}

            def capture(self, args):
                if not listing:
                    raise StepError("gcloud storage ls failed: matched no objects")
                return listing

        return Fake(root=Path("C:/repo"), python="python", week_of=WEEK)

    def test_table_list_matches_the_collector(self):
        # 수집기 쪽 TIERS['t2'] 가 바뀌면 이 대조가 조용히 어긋난다. import 로 묶을 수
        # 없어서(google.cloud) 소스에서 직접 읽는다 — 종료 코드 대조와 같은 방식이다.
        source = (Path(__file__).resolve().parents[2]
                  / "pipeline/collectors/bigquery/collect.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        tiers = next(node.value for node in ast.walk(tree)
                     if isinstance(node, ast.Assign)
                     and any(getattr(t, "id", None) == "TIERS" for t in node.targets))
        found = {ast.literal_eval(key): ast.literal_eval(value)
                 for key, value in zip(tiers.keys, tiers.values)}
        self.assertEqual(tuple(found["t2"][0]), T2_TABLES)

    def test_missing_table_fails_the_collection_step(self):
        ctx = self._ctx(["requirements"])
        with self.assertRaises(StepError) as caught:
            depsdev_t2(ctx)
        message = str(caught.exception)
        self.assertIn("versions_min", message)
        self.assertIn("projects", message)
        self.assertIn("stopped_budget", message, "왜 성공처럼 보였는지 적어야 한다")

    def test_complete_snapshot_passes(self):
        result = depsdev_t2(self._ctx(list(T2_TABLES)))
        self.assertEqual(sorted(result["tables"]), sorted(T2_TABLES))

    def test_gcs_sync_uses_the_same_rule(self):
        """--only gcs_sync 로 이 단계만 돌릴 수 있다. 거기서도 같은 판정이어야 한다."""
        with self.assertRaises(StepError) as caught:
            gcs_sync(self._ctx(["requirements", "projects"]))
        self.assertIn("versions_min", str(caught.exception))

    def test_nothing_uploaded_keeps_the_original_message(self):
        """gcloud 는 인증 실패도 비0으로 끝난다. 빈 목록으로 눙치면 원인이 사라진다."""
        with self.assertRaises(StepError) as caught:
            depsdev_t2(self._ctx([]))
        self.assertIn("matched no objects", str(caught.exception))

    def test_dry_run_does_not_call_gcloud(self):
        ctx = self._ctx([])
        ctx.dry_run = True
        self.assertEqual(depsdev_t2(ctx), {"returncode": 0})


class DownloadsTaskSummaryTests(unittest.TestCase):
    """빠진 작업이 몇 건인지 회차 객체에 실리는가.

    npm 수집기는 요청 실패를 manifest 에 적고 **정상 종료한다.** 다시 실행해도 그 작업은
    다시 고르지 않는다(`status IN ('pending','retry')`). 재수집 경로는 별도 이슈이고
    (S15P21A506-367), 지금 할 수 있는 것은 **빠졌다는 사실을 보이게 하는 것**뿐이다.
    이 경로가 틀리면 그 사실이 조용히 사라진다 — 단계는 여전히 SUCCEEDED 다.

    경로 규약이 수집기와 갈리기 쉬운 자리다: collect.py 는 `--out` 아래
    `run=<run>/manifest.json` 에 쓰고, 여기서는 `--out` 을 `<weekly_root>/raw` 로 준다.
    """

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)

    def _write(self, run, document):
        target = self.root / "raw" / f"run={run}"
        target.mkdir(parents=True)
        (target / "manifest.json").write_text(json.dumps(document), encoding="utf-8")

    def test_counts_are_lifted_from_the_manifest(self):
        self._write("2026-09-22", {
            "tasks_by_status": {"done": 9, "failed": 2},
            "packages_done": 900, "packages_not_found": 11,
            "failed_tasks": [1, 2]})
        summary = _downloads_tasks(self.root, "2026-09-22")
        self.assertEqual(summary["tasks_by_status"], {"done": 9, "failed": 2})
        self.assertEqual(summary["packages_done"], 900)
        self.assertEqual(summary["failed_tasks"], [1, 2])

    def test_no_failures_means_no_failed_list(self):
        self._write("2026-09-22", {"tasks_by_status": {"done": 9},
                                   "packages_done": 900, "packages_not_found": 0,
                                   "failed_tasks": []})
        self.assertNotIn("failed_tasks", _downloads_tasks(self.root, "2026-09-22"))

    def test_missing_manifest_does_not_raise(self):
        """23시간짜리 잡이 요약 한 줄 때문에 실패로 기록되면 안 된다."""
        summary = _downloads_tasks(self.root, "2026-09-22")
        self.assertIn("tasks_error", summary)
