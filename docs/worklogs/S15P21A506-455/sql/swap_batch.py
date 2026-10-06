"""날짜 묶음 단위로 파티션을 교체하는 드라이버.

명령서 2절은 날짜마다 교체·확인·제거를 손으로 친다. 229일이면 약 690개 명령이라
사람이 감당하기 어렵고, 중간에 한 줄을 빠뜨리면 조용히 어긋난다.
이 스크립트가 그 순서를 대신 친다. **새 SQL 을 만들지 않는다** — 명령서와 똑같은
docker/psql 호출만 쓰고, SQL 은 옆의 네 파일을 그대로 넘긴다.

한 묶음이 하는 일:

    2.1 계획 만들기      build_reload_plan.py
    2.2 적재             historical_db_reload --publish
    날짜마다 최근 것부터:
        2.3 교체         partition-swap.sql
        2.4 확인         부모를 통해 그 날짜를 조회해 새 파티션의 행 수·합계와 대조
        2.5 제거         partition-swap-drop-old.sql

어느 단계든 실패하거나 값이 어긋나면 **즉시 멈춘다.** 마지막 날짜·단계·출력 요약을
`driver-status.json` 에 남기고 0 이 아닌 코드로 끝난다. 뒤 날짜는 손대지 않는다.

이미 끝난 날짜는 건너뛴다. 판단 기준은 교체 영수증이다.

    영수증 없음              -> 교체부터
    영수증 있고 미제거       -> 확인·제거만
    영수증 있고 제거됨       -> 건너뜀

그래서 같은 명령을 다시 쳐도 안전하다. 적재기도 `--resume` 로 완료 날짜를 다시
넣지 않고 DB 값을 재검증한다.

실행 (worktree 안에서, DOCKER_HOST 를 걸어 둔 채):

    python docs/worklogs/S15P21A506-455/sql/swap_batch.py --batch 1 ...

전체 인자는 `--help` 를 볼 것. 운영 기본값은 두지 않는다 — 전부 명시해야 한다.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
SQL_FILES = ("partition-swap-setup.sql", "partition-swap.sql", "partition-swap-drop-old.sql")


class Stop(Exception):
    """단계 실패. 호출자가 상태를 남기고 멈춘다."""

    def __init__(self, step: str, day: str | None, detail: str):
        super().__init__(f"[{step}] {day or '-'}: {detail}")
        self.step, self.day, self.detail = step, day, detail


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Driver:
    def __init__(self, args):
        self.a = args
        self.root = Path(args.output).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.progress = self.root / "driver-progress.jsonl"
        self.status = self.root / "driver-status.json"

    # ---------------------------------------------------------------- 기록
    def event(self, phase: str, **fields):
        row = {"at": _now(), "phase": phase, **fields}
        with self.progress.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        self.status.write_text(json.dumps(row, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
        print(f"[{row['at'][11:19]}] {phase} " +
              " ".join(f"{k}={v}" for k, v in fields.items() if k != "output"), flush=True)

    # ---------------------------------------------------------------- 실행
    def run(self, command: list[str], *, step: str, day: str | None = None,
            timeout: int | None = None) -> str:
        done = subprocess.run(command, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
        if done.returncode != 0:
            tail = (done.stderr or done.stdout or "").strip().splitlines()
            raise Stop(step, day, "\n".join(tail[-12:]) or f"exit {done.returncode}")
        return done.stdout

    def psql(self, sql: str, *, step: str, day: str | None = None) -> list[str]:
        """명령서와 같은 형태의 한 줄 조회. 값만 돌려준다."""
        command = ["docker", "exec", "-i", self.a.container, "psql",
                   "-U", self.a.user, "-d", self.a.database,
                   "-v", "ON_ERROR_STOP=1", "-t", "-A", "-c", sql]
        out = self.run(command, step=step, day=day)
        return [line.strip() for line in out.splitlines() if line.strip()]

    def psql_file(self, name: str, variables: dict[str, str], *, step: str,
                  day: str | None = None) -> str:
        command = ["docker", "exec", "-i", self.a.container, "psql",
                   "-U", self.a.user, "-d", self.a.database, "-v", "ON_ERROR_STOP=1"]
        for key, value in variables.items():
            command += ["-v", f"{key}={value}"]
        command += ["-f", f"/tmp/vd455-{name}"]
        return self.run(command, step=step, day=day)

    def copy_sql(self):
        for name in SQL_FILES:
            self.run(["docker", "cp", str(HERE / name),
                      f"{self.a.container}:/tmp/vd455-{name}"], step="COPY_SQL")

    # ---------------------------------------------------------------- 달력
    def calendar(self) -> list[str]:
        """계산 회차가 고정한 달력을 읽는다. 최근 날짜가 앞이다."""
        run_dir = Path(self.a.run_dir).resolve()
        prepared = Path(json.loads((run_dir / "input_location.json").read_text(
            encoding="utf-8"))["prepared_dir"])
        manifest = json.loads((prepared / "input_manifest.json").read_text(encoding="utf-8"))
        days = [row["snapshot_at"] for row in manifest["calendar"]]
        if len(days) != len(set(days)):
            raise Stop("CALENDAR", None, "달력에 중복 날짜가 있습니다")
        return sorted(days, reverse=True)

    def pick_days(self) -> list[str]:
        if self.a.dates:
            days = sorted(set(self.a.dates), reverse=True)
            known = set(self.calendar())
            missing = [d for d in days if d not in known]
            if missing:
                raise Stop("CALENDAR", None, "달력에 없는 날짜: " + ", ".join(missing))
            return days
        days = self.calendar()
        start = (self.a.batch - 1) * self.a.batch_size
        if start >= len(days):
            raise Stop("CALENDAR", None,
                       f"묶음 {self.a.batch} 는 달력({len(days)}일) 밖입니다")
        return days[start:start + self.a.batch_size]

    # ---------------------------------------------------------------- 상태
    def receipts(self, days: list[str]) -> dict[str, bool]:
        """날짜별 (교체됨, 제거됨). 영수증 표가 아직 없으면 빈 값."""
        exists = self.psql(
            f"SELECT to_regclass('{self.a.bak}.swap_receipt') IS NOT NULL;", step="STATE")
        if not exists or exists[0] != "t":
            return {}
        wanted = ",".join(f"'{d}'" for d in days)
        rows = self.psql(
            f"SELECT snapshot_at, (old_dropped_at IS NOT NULL) FROM {self.a.bak}.swap_receipt "
            f"WHERE snapshot_at IN ({wanted}) ORDER BY snapshot_at;", step="STATE")
        out = {}
        for row in rows:
            day, dropped = row.split("|")
            out[day] = dropped == "t"
        return out

    def staged_totals(self, day: str) -> tuple[int, int]:
        """새 파티션의 행 수와 합계. 교체 전에 재어 교체 후와 대조한다."""
        child = f"{self.a.schema}.d{day.replace('-', '')}"
        rows = self.psql(
            f"SELECT count(*) || '|' || coalesce(sum(dependents_count),0) FROM {child};",
            step="VERIFY", day=day)
        count, total = rows[0].split("|")
        return int(count), int(total)

    def served_totals(self, day: str) -> tuple[int, int]:
        """부모를 통해 그 날짜를 조회한 값. 명령서 2.4 와 같은 질의다."""
        rows = self.psql(
            f"SELECT count(*) || '|' || coalesce(sum(dependents_count),0) "
            f"FROM {self.a.parent} WHERE snapshot_at = '{day}';",
            step="VERIFY", day=day)
        count, total = rows[0].split("|")
        return int(count), int(total)

    # ---------------------------------------------------------------- 단계
    def plan_and_load(self, days: list[str]):
        job = self.root / f"job-{days[-1]}_{days[0]}"
        config = job / "config.json"
        if not config.exists():
            self.event("PLAN", dates=len(days), first=days[0], last=days[-1])
            command = [sys.executable, "-B", str(HERE / "build_reload_plan.py"),
                       "--run-dir", self.a.run_dir,
                       "--run-manifest-sha256", self.a.run_manifest_sha256,
                       "--schema", self.a.schema,
                       "--container", self.a.container,
                       "--user", self.a.user,
                       "--database", self.a.database,
                       "--minimum-disk-gib", str(self.a.minimum_disk_gib),
                       "--output", str(job)]
            for day in days:
                command += ["--date", day]
            out = self.run(command, step="PLAN")
            self.event("PLAN_DONE", summary=json.loads(out).get("expected_rows"))
        else:
            self.event("PLAN_REUSED", config=str(config))

        self.event("LOAD", dates=len(days))
        started = time.monotonic()
        self.run([sys.executable, "-B", "-m",
                  "pipeline.version_dependents.historical_db_reload",
                  "--config", str(config), "--publish", "--resume"], step="LOAD")
        self.event("LOAD_DONE", seconds=round(time.monotonic() - started, 1))

    def swap_one(self, day: str, dropped: bool | None):
        if dropped is True:
            self.event("SKIP", day=day, reason="이미 제거까지 끝난 날짜")
            return

        expected = None
        if dropped is None:
            expected = self.staged_totals(day)
            self.event("SWAP", day=day, rows=expected[0])
            out = self.psql_file("partition-swap.sql", {
                "sch": self.a.schema, "bak": self.a.bak, "day": day,
                "cmp": self.a.cmp, "parent": self.a.parent}, step="SWAP", day=day)
            tail = [l for l in out.splitlines() if l.strip()][-1:]
            self.event("SWAP_DONE", day=day, output=out, summary=tail[0] if tail else "")
        else:
            self.event("SWAP_REUSED", day=day, reason="교체는 끝났고 제거만 남음")
            expected = self.staged_totals(day)

        served = self.served_totals(day)
        if served != expected:
            raise Stop("VERIFY", day,
                       f"부모 조회가 새 파티션과 다릅니다: 조회 {served} / 기대 {expected}")
        if served[0] == 0:
            raise Stop("VERIFY", day, "그 날짜의 행이 0 입니다")
        self.event("VERIFY_OK", day=day, rows=served[0], sum=served[1])

        self.psql_file("partition-swap-drop-old.sql", {
            "bak": self.a.bak, "day": day, "parent": self.a.parent},
            step="DROP", day=day)
        self.event("DROP_DONE", day=day)

    # ---------------------------------------------------------------- 본체
    def main(self) -> int:
        try:
            days = self.pick_days()
            self.event("BATCH_START", dates=len(days), first=days[0], last=days[-1],
                       parent=self.a.parent, schema=self.a.schema)
            self.copy_sql()
            # 설정은 CREATE ... IF NOT EXISTS 뿐이라 묶음마다 다시 쳐도 안전하다.
            # 첫 묶음에서 백업 스키마가 없으면 교체가 SET SCHEMA 에서 실패하므로
            # 사람이 1.5 절을 빠뜨리지 않도록 드라이버가 직접 친다.
            self.psql_file("partition-swap-setup.sql",
                           {"bak": self.a.bak, "parent": self.a.parent}, step="SETUP")
            self.event("SETUP_OK", bak=self.a.bak)
            state = self.receipts(days)
            todo = [d for d in days if state.get(d) is not True]
            if not todo:
                self.event("BATCH_COMPLETE", dates=0, note="전부 이미 끝난 날짜")
                return 0
            self.plan_and_load(todo)
            for day in days:
                self.swap_one(day, state.get(day))
            self.event("BATCH_COMPLETE", dates=len(days), first=days[0], last=days[-1])
            return 0
        except Stop as stop:
            self.event("FAILED", step=stop.step, day=stop.day, detail=stop.detail)
            print(f"\n멈췄습니다 — 단계 {stop.step}, 날짜 {stop.day or '-'}\n{stop.detail}\n"
                  f"상태: {self.status}", file=sys.stderr)
            return 1
        except subprocess.TimeoutExpired as error:
            self.event("FAILED", step="TIMEOUT", day=None, detail=str(error))
            return 1


def batch_schema(base: str, batch: int) -> str:
    """묶음마다 스테이징 스키마를 따로 쓴다 (S15P21A506-481).

    적재기 inspect_target 은 스키마에 저장된 계획과 새 계획을 비교해, 날짜가 다른
    두 번째 묶음을 같은 스키마로는 거부한다. 그래서 `_bNN` 을 붙인다 — 2026-09-25
    운영에서 손으로 쓰던 이름(`vd193_reload_455_b01`)과 같은 모양이다.
    이미 `_bNN` 이 붙어 있으면 번호가 묶음과 같을 때만 받아 준다. 옛 명령을 그대로
    복사해 `--batch 2 --schema …_b01` 을 치면 같은 거부가 다시 나기 때문이다.
    """
    suffix = f"_b{batch:02d}"
    matched = re.search(r"_b(\d+)$", base)
    if matched is None:
        return base + suffix
    if int(matched.group(1)) != batch:
        raise SystemExit(f"--schema {base} 의 묶음 번호가 --batch {batch} 와 다릅니다. "
                         f"접미사를 빼고 주면 드라이버가 {suffix} 를 붙입니다.")
    return base


def parse(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--run-manifest-sha256", required=True)
    ap.add_argument("--schema", required=True,
                    help="vd193_reload_ 로 시작하는 스테이징 스키마. --batch 면 드라이버가 _bNN 을 붙인다")
    ap.add_argument("--bak", required=True, help="vd455_backup_ 로 시작하는 백업 스키마")
    ap.add_argument("--parent", required=True, help="교체 대상 부모. 운영은 public.package_version_snapshot")
    ap.add_argument("--container", required=True)
    ap.add_argument("--user", required=True)
    ap.add_argument("--database", required=True)
    ap.add_argument("--output", required=True, help="job 과 진행 기록을 둘 폴더")
    ap.add_argument("--minimum-disk-gib", type=int, default=20)
    ap.add_argument("--cmp", choices=("full", "sample", "none"), default="full")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--batch", type=int, help="1 부터. 최근 날짜가 묶음 1 이다")
    group.add_argument("--date", action="append", dest="dates", help="날짜를 직접 지정. 반복")
    ap.add_argument("--batch-size", type=int, default=10)
    args = ap.parse_args(argv)
    if args.batch is not None:
        args.schema = batch_schema(args.schema, args.batch)
    return args


if __name__ == "__main__":
    sys.exit(Driver(parse()).main())
