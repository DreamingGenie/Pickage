"""MinIO 의 완료 포인터를 지켜보다 바뀌면 유사도 결과를 게시한다.

    python -m pipeline.similar_package.watch \
        --docker-container pickage-app-postgres-1 --database pickage

app 노드에서 상시로 돈다. 하는 일은 셋뿐이다 — 포인터를 읽고, 이미 게시한 것과
같은지 보고, 다르면 load.py 를 부른다. DB 에 쓰는 것은 load.py 이고 이 파일은
"언제 부를 것인가" 만 담당한다 (S15P21A506-371).

data 노드가 app 을 호출하지 않는다. 핸드오프가 MinIO 객체라서 두 노드가 서로를
부를 필요가 없고, 그게 방식 C 로 나눈 값어치다 (deploy/prod/README.md). 그래서
app 이 data:9000 으로 읽으러 간다 — 이 포트는 Spark executor 용으로 이미 열려 있어
새 인바운드 규칙이 없다.

평상시 비용은 60초마다 객체 하나 GET 이다. 새 산출물이 없으면 그걸로 끝난다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.similar_package.load import (  # noqa: E402
    DATASET, RESULT_BUCKET, RUN_PATTERN, list_runs,
)

# 완료 포인터. ai-collect 가 회차 업로드를 모두 마친 뒤 마지막에 쓴다.
POINTER_KEY = "_current.json"
# 게시할 것이 없을 때 다시 볼 때까지의 기본 간격
DEFAULT_INTERVAL = 60.0
# 게시에 실패했을 때는 같은 실패를 분당 한 번씩 반복하지 않는다
BACKOFF_START = 60.0
BACKOFF_MAX = 1800.0
WINDOW_PATTERN = re.compile(r"([0-2]\d):([0-5]\d)-([0-2]\d):([0-5]\d)\Z")

_stop = False


# 표준출력에 시각과 함께 한 줄 남긴다. 컨테이너 로그가 유일한 기록이다.
def log(message: str) -> None:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%H:%M:%S")
    print(f"{stamp} {message}", flush=True)


# SIGTERM 을 받으면 자던 것을 깨워 깔끔히 끝낸다. docker stop 이 10초 뒤 죽이기 전에.
def request_stop(signum, frame) -> None:
    global _stop
    _stop = True
    log("종료 요청을 받았다. 진행 중인 게시를 마치고 끝낸다")


# 중간에 깨어날 수 있는 sleep. 종료 요청이 오면 바로 돌아온다.
def nap(seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while not _stop and time.monotonic() < deadline:
        time.sleep(min(1.0, deadline - time.monotonic()))


# 적재를 허용하는 시간대인지 본다. 창을 주지 않으면 항상 참이다.
#
# 적재 자체는 30만 행이라 수십 초고, 잡는 락이 SHARE ROW EXCLUSIVE 라 SELECT 를
# 막지 않는다. 그래도 사용자 트래픽과 디스크를 다투고 싶지 않을 때 쓴다.
def in_window(window: str | None, now: dt.time | None = None) -> bool:
    if not window:
        return True
    match = WINDOW_PATTERN.fullmatch(window)
    if not match:
        raise SystemExit("--window 는 HH:MM-HH:MM 형태로 준다 (예: 02:00-06:00)")
    start = dt.time(int(match.group(1)), int(match.group(2)))
    end = dt.time(int(match.group(3)), int(match.group(4)))
    now = now or dt.datetime.now().time()
    if start <= end:
        return start <= now < end
    return now >= start or now < end  # 자정을 넘는 창


# 완료 포인터를 읽는다. 아직 포인터를 쓰지 않는 회차를 위해 목록 훑기로 물러선다.
def latest_run(s3) -> tuple[str, str] | None:
    try:
        body = s3.get_object(Bucket=RESULT_BUCKET, Key=POINTER_KEY)["Body"].read()
    except Exception:
        # ai-collect 에 포인터 게시가 들어가기 전이거나 아직 한 회차도 안 돈 상태다.
        # 목록을 훑는 예전 경로로 물러서되, 그 사실을 로그에 남긴다.
        runs = list_runs(s3)
        if not runs:
            return None
        log(f"포인터가 없다 — 목록에서 고른다: {runs[-1]}")
        return runs[-1], ""
    pointer = json.loads(body)
    run = pointer.get("run_path") or ""
    if not RUN_PATTERN.fullmatch(run):
        raise SystemExit(f"포인터의 run_path 가 형식에 맞지 않는다: {run!r}")
    return run, pointer.get("manifest_sha256") or ""


# 지금 DB 에 게시되어 있는 실행을 읽는다. (run_prefix, manifest_sha256)
def published(psql: list[str]) -> tuple[str, str]:
    query = (f"SELECT coalesce(e.run_prefix, ''), coalesce(c.manifest_sha256, '') "
             f"FROM public.etl_dataset_current c "
             f"JOIN public.etl_load_execution e ON e.execution_id = c.execution_id "
             f"WHERE c.dataset = '{DATASET}'")
    done = subprocess.run(psql + ["-t", "-A", "-F", "|", "-c", query],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    if done.returncode != 0:
        raise RuntimeError(f"게시 상태를 읽지 못했다: {done.stderr.strip()[:300]}")
    line = (done.stdout or "").strip()
    if not line:
        return "", ""
    prefix, _, sha = line.partition("|")
    return prefix.strip(), sha.strip()


# 게시가 필요한지 판단한다. 필요 없으면 이유를 돌려준다.
#
# 내용 해시가 양쪽에 다 있으면 그것으로 본다 — 같은 경로에 다른 산출물이 다시
# 올라온 경우까지 잡힌다. 포인터에 해시가 없는 옛 형식이면 경로로 본다.
def needs_publish(run: str, sha: str, done_prefix: str, done_sha: str) -> str | None:
    if sha and done_sha:
        return None if sha == done_sha else "새 산출물"
    if run == done_prefix:
        return None
    return "새 산출물"


# load.py 를 별도 프로세스로 부른다. 실패해도 이 감시자는 살아 있어야 한다.
def publish(run: str, sha: str, args) -> bool:
    # 같은 산출물을 다시 돌리면 같은 execution_id 가 나오게 만든다. load.py 의
    # 재실행 경로와 etl_load_execution 의 UNIQUE 가 그 위에서 맞물린다.
    suffix = f"-{sha[:12]}" if sha else ""
    execution_id = f"{DATASET}-{run.replace('/', '-').replace('=', '')}{suffix}"
    command = [sys.executable, "-m", "pipeline.similar_package.load",
               "--run", run, "--execution-id", execution_id,
               "--database", args.database, "--db-user", args.db_user]
    if args.docker_container:
        command += ["--docker-container", args.docker_container]
    else:
        command += ["--psql", args.psql]
    if args.allow_gate_skip:
        command.append("--allow-gate-skip")
    if args.verify_only:
        command.append("--verify-only")

    log(f"게시 시작  {run}  execution_id={execution_id}")
    done = subprocess.run(command, cwd=ROOT)
    if done.returncode == 0:
        log(f"게시 완료  {run}")
        return True
    log(f"게시 실패  {run}  (load.py 종료코드 {done.returncode})")
    return False


# 한 바퀴 돈다. 게시했으면 True.
def tick(s3, psql: list[str], args) -> bool:
    latest = latest_run(s3)
    if latest is None:
        log("적재할 수 있는 실행이 없다")
        return False
    run, sha = latest
    done_prefix, done_sha = published(psql)
    reason = needs_publish(run, sha, done_prefix, done_sha)
    if reason is None:
        return False
    if not in_window(args.window):
        log(f"{reason}: {run} — 적재 창({args.window}) 밖이라 기다린다")
        return False
    if args.dry_run:
        log(f"{reason}: {run} — --dry-run 이라 게시하지 않는다 "
            f"(현재 게시본 {done_prefix or '없음'})")
        return False
    return publish(run, sha, args)


# 포인터를 지켜보다 바뀌면 게시한다.
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL,
                        help="포인터를 다시 볼 때까지의 간격(초)")
    parser.add_argument("--once", action="store_true", help="한 번만 보고 끝낸다")
    parser.add_argument("--dry-run", action="store_true",
                        help="무엇을 게시할지만 출력한다. load.py 를 부르지 않는다")
    parser.add_argument("--window", default=None,
                        help="적재를 허용할 시간대 HH:MM-HH:MM (기본: 제한 없음)")
    parser.add_argument("--allow-gate-skip", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--docker-container", help="로컬 PostgreSQL 컨테이너 이름")
    target.add_argument("--psql", help="psql 실행 파일 경로")
    parser.add_argument("--database", required=True)
    parser.add_argument("--db-user", default="postgres")
    args = parser.parse_args(argv)

    in_window(args.window)  # 형식이 틀렸으면 여기서 멈춘다

    from pipeline.minio.ingest_raw import client
    from pipeline.similar_package.load import psql_command

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    s3 = client()
    psql = psql_command(args)
    log(f"감시 시작  s3://{RESULT_BUCKET}/{POINTER_KEY}  간격 {args.interval:.0f}초"
        + (f"  창 {args.window}" if args.window else ""))

    backoff = 0.0
    while not _stop:
        try:
            tick(s3, psql, args)
            backoff = 0.0
        except Exception as error:  # 감시자는 어떤 실패에도 살아남아야 한다
            backoff = min(max(backoff * 2, BACKOFF_START), BACKOFF_MAX)
            log(f"오류: {error} — {backoff:.0f}초 뒤 다시 시도")
        if args.once:
            return 0
        nap(backoff or args.interval)
    return 0


if __name__ == "__main__":
    sys.exit(main())
