"""단계가 넘기는 경로 규약 시험.

여기가 깨지면 23시간 수집을 마친 **뒤** 마지막 단계에서 죽는다. 드라이런은 CLI 를 아예
부르지 않아 이 계약을 검증하지 못하므로, 규칙 자체를 여기서 못 박는다.
"""
import re
import shutil
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from pipeline.weekly.steps import (SNAPSHOT_NOT_READY_EXIT, Context, StepError, StepNotReady,
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
