"""주간 회차의 단계 정의.

여기에는 수집 로직이 없다. 기존 CLI 를 정해진 인자로 순서대로 부를 뿐이다.
이어받기도 각 CLI 가 이미 한다 — BigQuery 는 GCS 의 _MANIFEST.json, downloads 는
checkpoint.sqlite, 입고기는 _SUCCESS 와 객체 해시 대조. 그래서 실패한 회차는
같은 명령을 다시 부르기만 하면 된다.

⚠ **"다시 부르면 된다" 에는 구멍이 둘 있다.** 둘 다 수집기가 **종료 코드 0으로 끝나면서**
덜 받은 경우라, 종료 코드만 보면 성공으로 보인다.

1. BigQuery 는 누적 예산을 넘기면 `stopped_budget` 으로 남은 테이블을 포기하고 정상
   종료한다. 그래서 `depsdev_t2` 가 GCS 매니페스트를 T2_TABLES 와 **직접 대조**한다.
   모자라면 그 단계를 실패로 올려 다음 발화가 수집기를 다시 부르게 한다 — 이미 매니페스트가
   있는 테이블은 예산을 쓰기 전에 건너뛰므로(collect.py 의 `skipped_manifest_exists`)
   재시도마다 남은 것에 예산이 온전히 가고, 결국 수렴한다.
   **대조를 뒤 단계(`gcs_sync`)에 두면 안 된다** — 그러면 `depsdev_t2` 가 SUCCEEDED 로
   남아 다음 발화가 수집기를 건너뛰고, 같은 실패만 열 번 반복해 BLOCKED 로 간다.
2. npm 수집기는 요청 실패를 manifest 에 적고 정상 종료하는데, **그 작업은 다시 고르지
   않는다** — 작업 선택이 `status IN ('pending','retry')` 라 `failed` 는 대상이 아니다.
   지금은 `downloads_weekly` 가 그 수를 단계 detail 에 실어 **보이게만** 한다.
   재수집 경로는 수집기의 작업 선택을 바꿔야 해서 별도 이슈다 (S15P21A506-367).
"""
from __future__ import annotations

import json
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

# 한 회차에 GCS 로 올라와 있어야 하는 deps.dev 테이블. collect.py 의 TIERS["t2"] 와 같아야
# 하며, test_steps.py 가 두 목록이 어긋나지 않는지 검사한다. 위 종료 코드와 같은 이유로
# import 하지 않는다 — 그 모듈이 최상단에서 google.cloud 를 끌어온다.
T2_TABLES = ("requirements", "versions_min", "projects")


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


def _snapshot_tables(ctx: Context) -> tuple[list[str], list[str]]:
    """그 회차 스냅샷으로 GCS 에 올라온 테이블. (prefix 목록, 모자란 테이블) 을 준다.

    받을 목록을 코드에 적어 두고 그것만 내려받지는 않는다 — `TIERS['t2']` 가 바뀌면
    적어 둔 목록이 조용히 어긋난다. **실제로 올라간 것을 물어보고**, 그것을 T2_TABLES 와
    대조해 모자란 것만 이름으로 돌려준다.
    """
    pattern = f"{GCS_RAW}/*/snapshot={ctx.week_of.isoformat()}/_MANIFEST.json"
    try:
        listing = ctx.capture(["gcloud", "storage", "ls", pattern])
    except StepError as error:
        # 하나도 안 맞으면 gcloud 가 비0으로 끝난다("matched no objects"). 인증 실패도
        # 비0이라 여기서는 구별할 수 없으므로 **원문을 그대로 달고 올린다** — 빈 목록으로
        # 눙치면 인증이 끊긴 것이 "테이블이 모자라다" 로 둔갑한다.
        raise StepError(
            f"snapshot={ctx.week_of} 산출물을 GCS 에서 확인하지 못했다.\n{error}") from error
    prefixes = sorted({line.rsplit("/", 1)[0] for line in listing.splitlines() if line.strip()})
    tables = [p.rsplit("/", 2)[-2] for p in prefixes]
    return prefixes, [name for name in T2_TABLES if name not in tables]


def _incomplete(ctx: Context, missing: list[str]) -> StepError:
    """T2 가 덜 올라왔다. 무엇이 없는지와, 왜 성공처럼 보였는지를 함께 남긴다."""
    return StepError(
        f"snapshot={ctx.week_of} 의 T2 산출물이 모자라다 — 없는 테이블: "
        + ", ".join(missing) + "\n"
        "수집기가 누적 예산(collect.py 의 TIERS['t2'])에 걸려 stopped_budget 으로 멈추면 "
        "이렇게 되고, 그때도 종료 코드는 0이라 앞 단계만 보면 성공으로 보인다.\n"
        "다음 발화가 이어받는다 — 이미 매니페스트가 있는 테이블은 예산을 쓰기 전에 "
        "건너뛰므로 남은 것만 받는다.")


def depsdev_t2(ctx: Context) -> dict:
    """deps.dev 주간 증분을 BigQuery 에서 GCS 로.

    --snap 을 회차 날짜로 못 박는다. 생략하면 "Snapshots 최신"이라 수요일에 재시작했는데
    그 사이 새 스냅샷이 나오면 조용히 다른 주를 받는다.

    그 대가로 **아직 안 올라온 주**를 지정하는 경우가 생긴다. 그건 실패가 아니라 "아직" 이라
    수집기가 전용 종료 코드로 알려 주고(EXIT_SNAPSHOT_NOT_READY), 여기서 StepNotReady 로
    바꿔 올린다 — 회차의 연속 실패 횟수를 올리지 않는다. 실패로 세면 공급자가 두 시간
    늦는 것만으로 BLOCKED 가 되어 사람을 부르게 된다.
    """
    result = ctx.run("depsdev_t2", [
        ctx.python, "pipeline/collectors/bigquery/collect.py",
        "--tier", "t2", "--snap", ctx.week_of.isoformat(),
    ], not_ready_code=SNAPSHOT_NOT_READY_EXIT)
    if ctx.dry_run:
        return result
    # ⚠ 종료 코드 0이 "다 받았다" 가 아니다. 예산에 걸려 멈춰도 0으로 끝난다.
    #   **이 대조가 여기 있어야 한다** — 뒤 단계로 미루면 이 단계가 SUCCEEDED 로 남아
    #   다음 발화가 수집기를 건너뛰고, 같은 실패를 열 번 반복해 BLOCKED 가 된다.
    prefixes, missing = _snapshot_tables(ctx)
    if missing:
        raise _incomplete(ctx, missing)
    result["tables"] = [p.rsplit("/", 2)[-2] for p in prefixes]
    return result


def gcs_sync(ctx: Context) -> dict:
    """그 회차 스냅샷만 GCS 에서 내려받는다.

    raw 전체를 rsync 하면 T1 백필(projects 229 스냅샷)까지 따라와 31 GB 가 된다.
    받을 테이블 목록을 여기 적어 두지 않는 이유는 TIERS['t2'] 가 바뀌면 어긋나기 때문이다 —
    그 회차에 실제로 올라간 것을 물어본다.
    """
    if ctx.dry_run:
        return {"dry_run": True, "snapshot": ctx.week_of.isoformat()}
    # depsdev_t2 가 이미 대조했지만 여기서도 본다 — `--only gcs_sync` 로 이 단계만 돌릴 수
    # 있고, 목록은 어차피 받아야 해서 비용이 0이다. 규칙은 한 군데(_snapshot_tables)다.
    prefixes, missing = _snapshot_tables(ctx)
    if missing:
        raise _incomplete(ctx, missing)
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
    if not ctx.dry_run:
        result.update(_downloads_tasks(root, download_run(ctx.week_of)))
    return result


def _downloads_tasks(root: Path, run: str) -> dict:
    """수집기 manifest 의 작업 상태 요약을 단계 detail 에 싣는다.

    ⚠ **`failed` 가 0이 아니면 그 작업들은 자동으로 다시 수집되지 않는다.** 수집기의 작업
    선택이 `status IN ('pending','retry')` 라 `failed` 는 다시 고르지 않고, 그래도 종료
    코드는 0이다. 지금 할 수 있는 것은 **눈에 보이게 하는 것**뿐이라 회차 객체에 실어
    둔다 — 운영 API 로 조회하면 그 주에 몇 건이 빠졌는지 보인다.
    재수집 경로는 수집기를 고쳐야 해서 별도 이슈다 (S15P21A506-367).

    **읽기 실패는 단계를 실패시키지 않는다.** 이건 보고용이고, 수집 자체는 이미 끝났다.
    여기서 터뜨리면 23시간짜리 잡이 요약 한 줄 때문에 실패로 기록된다.
    """
    path = root / "raw" / f"run={run}" / "manifest.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        return {"tasks_error": f"{type(error).__name__}: {error}"}
    counts = document.get("tasks_by_status") or {}
    summary = {"tasks_by_status": counts,
               "packages_done": document.get("packages_done"),
               "packages_not_found": document.get("packages_not_found")}
    if counts.get("failed"):
        summary["failed_tasks"] = (document.get("failed_tasks") or [])[:20]
    return summary


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
