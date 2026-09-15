"""주간 회차의 단계 정의.

여기에는 수집 로직이 없다. 기존 CLI 를 정해진 인자로 순서대로 부를 뿐이다.
이어받기도 각 CLI 가 이미 한다 — BigQuery 는 GCS 의 _MANIFEST.json, downloads 는
checkpoint.sqlite, 입고기는 _SUCCESS 와 객체 해시 대조. 그래서 실패한 회차는
같은 명령을 다시 부르기만 하면 된다.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .schedule import bronze_run_id, download_run, window_end, window_start

GCS_RAW = "gs://oss-shift-a506-raw/raw"
# 추적되는 대상 목록(다운로드 순위 상위 10만). 입고기는 루트 레벨 CSV 를 요구하고 심링크를
# 거부하므로(_assert_no_symlink) 회차 루트로 복사해서 쓴다.
TARGETS_SOURCE = Path("datasets/targets/rank_top100k_20260902.csv")
# 로그 꼬리를 이만큼만 실패 메시지에 싣는다. 전문은 로그 파일에 남는다.
TAIL_BYTES = 4000


# collect.py 가 "그 주 스냅샷 파티션이 아직 없다" 로 끝낼 때의 종료 코드.
# pipeline/collectors/bigquery/collect.py 의 EXIT_SNAPSHOT_NOT_READY 와 같아야 하며,
# test_steps.py 가 두 값이 어긋나지 않는지 검사한다. 거기서 직접 import 하지 않는 이유는
# 그 모듈이 google.cloud 를 최상단에서 불러서 단위 시험이 그 의존성을 끌고 오기 때문이다.
SNAPSHOT_NOT_READY_EXIT = 3


class StepError(RuntimeError):
    """이 단계가 실패했다. 회차의 연속 실패 횟수가 오른다."""


class StepNotReady(RuntimeError):
    """아직 할 수 없다 — **실패가 아니다.**

    원천이 준비되지 않았을 뿐이라 기다리면 해결된다. 연속 실패 횟수를 올리지 않는다.
    이걸 실패로 세면 공급자가 두 시간 늦는 것만으로 회차가 BLOCKED 가 되어 사람을 부른다.
    """


@dataclass
class Context:
    root: Path
    python: str
    week_of: date
    dry_run: bool = False
    minio_workers: int = 4

    @property
    def data(self) -> Path:
        # pipeline/minio/ingest_raw.py 가 <repo>/data/raw 를 직접 본다. 여기만 바꿀 수 없다.
        return self.root / "data"

    @property
    def weekly_root(self) -> Path:
        """이 회차 전용 downloads 루트.

        입고기의 _select() 는 root/parquet/downloads 전체를 대상으로 잡는다 — 회차로 좁히지
        않는다. 백필과 같은 루트를 쓰면 매주 62M 행을 통째로 다시 올리게 되므로 회차마다
        루트를 가른다.
        """
        return self.data / "downloads-weekly" / self.week_of.isoformat()

    @property
    def log_dir(self) -> Path:
        # 로그는 회차 루트 안에 둬도 된다 — 입고기의 _excluded() 가 .log 를 "execution log" 로
        # 분류해 준다(백필 루트에도 backfill_*.log 가 있었다).
        return self.weekly_root / "logs"

    @property
    def execution_dir(self) -> Path:
        """입고 실행 보고서를 두는 곳. **회차 루트 밖이어야 한다.**

        pipeline/downloads/load.py 는 --work-dir 가 --source-root 안이면 거부한다(그 파일의
        `execution artifacts must be outside the source directory`). 이유가 있다 — 보고서를
        먼저 쓴 뒤 input.py::_select() 가 source_root 전체를 훑는데, 분류 규칙에 없는 파일을
        만나면 "unknown regular file must be classified" 로 멈춘다. .log 와 달리
        execution_report.json·input-manifest.json 에는 그 규칙이 없다.
        """
        return self.data / "downloads-weekly" / "_executions" / self.week_of.isoformat()

    def child_env(self) -> dict:
        merged = dict(os.environ)
        # 자식이 로그 파일로 리다이렉트될 때 Windows 기본 인코딩(cp949)에 걸려 죽지 않게 한다.
        merged.setdefault("PYTHONIOENCODING", "utf-8")
        return merged

    def run(self, step: str, args: list[str], *, not_ready_code: int | None = None) -> dict:
        """명령 하나를 돌리고 로그를 남긴다.

        종료 코드가 0이 아니면 StepError 다. 다만 ``not_ready_code`` 와 같으면
        StepNotReady — "아직" 이지 실패가 아니다.
        """
        if self.dry_run:
            return {"dry_run": True, "command": " ".join(args)}
        self.log_dir.mkdir(parents=True, exist_ok=True)
        log = self.log_dir / f"{step}.log"
        header = f"\n===== {step} :: {' '.join(args)} =====\n".encode("utf-8")
        with log.open("ab") as handle:
            handle.write(header)
            handle.flush()
            # 파이프가 아니라 파일로 보낸다. 23시간 동안 쏟아지는 출력을 파이프로 받으면
            # 읽어 주는 쪽이 없을 때 자식이 멈춘다.
            completed = subprocess.run(args, cwd=self.root, env=self.child_env(),
                                       stdout=handle, stderr=subprocess.STDOUT)
        if completed.returncode:
            if not_ready_code is not None and completed.returncode == not_ready_code:
                raise StepNotReady(_tail(log))
            raise StepError(f"{step} exited {completed.returncode}\n{_tail(log)}")
        return {"log": log.relative_to(self.root).as_posix(), "returncode": 0}

    def capture(self, args: list[str]) -> str:
        completed = subprocess.run(args, cwd=self.root, env=self.child_env(),
                                   capture_output=True, timeout=300)
        if completed.returncode:
            raise StepError(" ".join(args[:2]) + " failed: "
                            + completed.stderr.decode("utf-8", errors="replace")[-TAIL_BYTES:])
        return completed.stdout.decode("utf-8", errors="replace")


def _tail(path: Path) -> str:
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        handle.seek(max(0, handle.tell() - TAIL_BYTES))
        return handle.read().decode("utf-8", errors="replace")


def depsdev_t2(ctx: Context) -> dict:
    """deps.dev 주간 증분을 BigQuery 에서 GCS 로.

    --snap 을 회차 날짜로 못 박는다. 생략하면 "Snapshots 최신"이라 수요일에 재시작했는데
    그 사이 새 스냅샷이 나오면 조용히 다른 주를 받는다.

    그 대가로 **아직 안 올라온 주**를 지정하는 경우가 생긴다. 그건 실패가 아니라 "아직" 이라
    수집기가 전용 종료 코드로 알려 주고(EXIT_SNAPSHOT_NOT_READY), 여기서 StepNotReady 로
    바꿔 올린다 — 회차의 연속 실패 횟수를 올리지 않는다. 실패로 세면 공급자가 두 시간
    늦는 것만으로 BLOCKED 가 되어 사람을 부르게 된다.
    """
    return ctx.run("depsdev_t2", [
        ctx.python, "pipeline/collectors/bigquery/collect.py",
        "--tier", "t2", "--snap", ctx.week_of.isoformat(),
    ], not_ready_code=SNAPSHOT_NOT_READY_EXIT)


def gcs_sync(ctx: Context) -> dict:
    """그 회차 스냅샷만 GCS 에서 내려받는다.

    raw 전체를 rsync 하면 T1 백필(projects 229 스냅샷)까지 따라와 31 GB 가 된다.
    받을 테이블 목록을 여기 적어 두지 않는 이유는 TIERS['t2'] 가 바뀌면 어긋나기 때문이다 —
    그 회차에 실제로 올라간 것을 물어본다.
    """
    pattern = f"{GCS_RAW}/*/snapshot={ctx.week_of.isoformat()}/_MANIFEST.json"
    if ctx.dry_run:
        return {"dry_run": True, "pattern": pattern}
    listing = ctx.capture(["gcloud", "storage", "ls", pattern])
    prefixes = sorted({line.rsplit("/", 1)[0] for line in listing.splitlines() if line.strip()})
    if not prefixes:
        raise StepError(f"GCS 에 snapshot={ctx.week_of} 산출물이 없다: {pattern}")
    for prefix in prefixes:
        table = prefix.rsplit("/", 2)[-2]
        destination = ctx.data / "raw" / table / f"snapshot={ctx.week_of.isoformat()}"
        destination.mkdir(parents=True, exist_ok=True)
        ctx.run("gcs_sync", ["gcloud", "storage", "rsync", "-r", prefix, str(destination)])
    return {"tables": [p.rsplit("/", 2)[-2] for p in prefixes], "snapshot": ctx.week_of.isoformat()}


def downloads_weekly(ctx: Context) -> dict:
    """npm 다운로드 직전 14일. 창의 양 끝을 회차에서 계산해 재시작에 흔들리지 않게 한다."""
    root = ctx.weekly_root
    targets = root / TARGETS_SOURCE.name
    if not ctx.dry_run:
        root.mkdir(parents=True, exist_ok=True)
        if not targets.is_file():
            shutil.copyfile(ctx.root / TARGETS_SOURCE, targets)
    result = ctx.run("downloads_weekly", [
        ctx.python, "pipeline/collectors/downloads/collect.py",
        "--targets", str(targets),
        "--run", download_run(ctx.week_of),
        "--end", window_end(ctx.week_of).isoformat(),
        "--mode", "weekly",
        "--out", str(root / "raw"),
    ])
    result.update(window_start=window_start(ctx.week_of).isoformat(),
                  window_end=window_end(ctx.week_of).isoformat(),
                  run=download_run(ctx.week_of))
    return result


def downloads_parquet(ctx: Context) -> dict:
    root = ctx.weekly_root
    return ctx.run("downloads_parquet", [
        ctx.python, "pipeline/collectors/downloads/to_parquet.py",
        "--raw", str(root / "raw" / f"run={download_run(ctx.week_of)}"),
        "--out", str(root / "parquet"),
    ])


def bronze_depsdev(ctx: Context) -> dict:
    """deps.dev 원본을 MinIO Bronze 로.

    --dataset 을 주지 않는다 — 그 회차 스냅샷의 모든 테이블을 입고한다. (--dataset 선택지에는
    versions_min 이 빠져 있는데, 필터를 안 쓰면 그 제한을 타지 않는다.)
    """
    run_id = bronze_run_id(ctx.week_of, "bronze")
    result = ctx.run("bronze_depsdev", [
        ctx.python, "pipeline/minio/ingest_raw.py",
        "--snapshot", ctx.week_of.isoformat(),
        "--run-id", run_id,
        "--workers", str(ctx.minio_workers),
    ])
    result["run_id"] = run_id
    return result


def bronze_downloads(ctx: Context) -> dict:
    root = ctx.weekly_root
    run_id = bronze_run_id(ctx.week_of, "downloads")
    result = ctx.run("bronze_downloads", [
        ctx.python, "-m", "pipeline.downloads.load",
        "--source-root", str(root),
        "--source-run", download_run(ctx.week_of),
        "--run-id", run_id,
        "--target-name", TARGETS_SOURCE.name,
        "--work-dir", str(ctx.execution_dir),
    ])
    result["run_id"] = run_id
    return result


def purge_week(ctx: Context, week_of: date) -> list[str]:
    """지난 회차의 로컬 산출물을 지운다.

    MinIO 에 `_SUCCESS` 가 붙은 뒤로 로컬 사본은 사본일 뿐인데, 지우지 않으면 주당 약
    10 GB 씩 쌓인다. data 노드에서는 그 자리가 **MinIO 데이터와 같은 파티션**이라,
    채우면 수집만 멈추는 게 아니라 저장소가 통째로 선다.

    ⚠ **`data/raw` 에서는 그 주차 스냅샷만 건드린다.** 거기에는 T0·T1 백필(projects 229
    스냅샷, 2022년부터)이 같이 들어 있고 그건 BigQuery 50 GiB 를 다시 스캔해야 복구된다.
    그래서 호출자가 상태 객체에서 SUCCEEDED 로 확인한 주차만 넘기고(`state.py` 의
    `purgeable_weeks`), 여기서도 경로 이름에 그 날짜가 박혀 있는지 다시 본다.
    한 번의 실수가 되돌릴 수 없다.

    이 단계는 STEPS 에 넣지 않는다 — 청소가 실패했다고 수집까지 실패로 표시할 이유가 없다.
    """
    stamp = week_of.isoformat()
    data = ctx.data.resolve()
    targets = [ctx.data / "downloads-weekly" / stamp,
               ctx.data / "downloads-weekly" / "_executions" / stamp]
    raw = ctx.data / "raw"
    if raw.is_dir():
        targets += [table / f"snapshot={stamp}" for table in sorted(raw.iterdir()) if table.is_dir()]

    removed = []
    for path in targets:
        if path.is_symlink() or not path.is_dir():
            continue
        if stamp not in path.name:
            raise StepError(f"정리 대상 경로에 회차 날짜가 없다: {path}")
        if data not in path.resolve().parents:
            raise StepError(f"정리 대상이 data 디렉터리 밖이다: {path}")
        shutil.rmtree(path)
        removed.append(path.relative_to(ctx.root).as_posix())
    return removed


# 실행 순서. 뒤 단계는 앞 단계의 산출물을 읽으므로 순서를 바꾸지 않는다.
HANDLERS = {
    "depsdev_t2": depsdev_t2,
    "gcs_sync": gcs_sync,
    "downloads_weekly": downloads_weekly,
    "downloads_parquet": downloads_parquet,
    "bronze_depsdev": bronze_depsdev,
    "bronze_downloads": bronze_downloads,
}
