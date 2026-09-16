"""주간 수집 한 회차. 사람이 인자를 주지 않아도 돌아간다.

    python -m pipeline.weekly.run

할 일이 없으면 아무것도 하지 않고 0으로 끝난다. 그래서 타이머를 촘촘히 걸어도 헛돌지 않고,
실패한 회차는 다음 발화에서 이어받는다. 판정 순서는 비용 순서이기도 하다 — MinIO 객체를
한 번 읽고 끝나는 경우가 대부분이고, BigQuery 는 실제로 실행할 때만 건드린다(Snapshots
조회는 쿼리당 최소 과금 10 MB다).

**판정을 컨테이너 안에서 하는 것이 의도다.** 호스트 스크립트는 잠금을 걸고 이걸 부르기만
한다. 유예·26시간 회수·BLOCKED·우편함 판정을 셸로 옮기면 읽을 수 없는 물건이 된다.

종료 코드를 스케줄러가 본다. 0 = 할 일이 없었거나 끝까지 갔다, 1 = 단계가 실패했다.
"""
from __future__ import annotations

import argparse
import sys
import traceback
from datetime import date, datetime, timezone
from pathlib import Path

from .schedule import (KEEP_WEEKS, MAX_CONSECUTIVE_FAILURES, SNAPSHOT_GRACE,
                       STALE_RUNNING, STEPS, current_week_of, decide, download_run,
                       snapshot_grace_expired, window_end, window_start)
from .state import BUCKET, CorruptState, WeeklyState, open_store
from .steps import HANDLERS, Context, StepError, StepNotReady, purge_week

ROOT = Path(__file__).resolve().parents[2]

# Windows 기본 콘솔 인코딩(cp949)은 이 파일이 찍는 한글·기호를 감당하지 못해서, 줄 하나 때문에
# 프로세스가 UnicodeEncodeError 로 죽는다. 특히 출력을 파일로 돌릴 때 걸린다.
# pipeline/collectors/bigquery/collect.py 가 같은 이유로 같은 줄을 쓰고 있다.
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")


def parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--week-of", type=date.fromisoformat,
                        help="회차(그 주 월요일). 생략하면 지금이 속한 주")
    parser.add_argument("--only", choices=STEPS, help="이 단계만 실행 (진단용)")
    parser.add_argument("--force", action="store_true",
                        help="수집 창·직전 상태를 무시하고 모든 단계를 다시 실행")
    parser.add_argument("--dry-run", action="store_true",
                        help="단계를 실제로 돌리지 않고 상태 전이만 기록")
    parser.add_argument("--max-failures", type=int, default=MAX_CONSECUTIVE_FAILURES,
                        help="연속 실패가 이 값에 닿으면 BLOCKED 로 멈춘다")
    parser.add_argument("--keep-weeks", type=int, default=KEEP_WEEKS,
                        help="회차가 끝난 뒤 남겨 둘 지난 회차 수. 그보다 오래된 SUCCEEDED "
                             "회차의 로컬 산출물을 지운다. 음수면 정리하지 않는다")
    parser.add_argument("--python", default=sys.executable, help="수집기를 돌릴 인터프리터")
    parser.add_argument("--minio-workers", type=int, default=4)
    parser.add_argument("--bucket", default=BUCKET,
                        help="상태 객체를 둘 버킷. 기본값을 바꿀 일은 시험뿐이다")
    return parser.parse_args(argv)


def _say(message: str) -> None:
    print("[weekly] " + message, flush=True)


def main(argv: list[str] | None = None) -> int:
    args = parse(argv)
    week_of = args.week_of or current_week_of(datetime.now(timezone.utc))
    if week_of.weekday() != 0:
        _say(f"회차는 월요일이어야 한다: {week_of} ({week_of:%A})")
        return 2

    state = WeeklyState(open_store(args.bucket), max_failures=args.max_failures)

    now, record, steps = state.load(week_of)
    decision = decide(record, week_of, now, force=args.force, max_failures=args.max_failures)
    _say(f"{week_of} — {decision.reason}")
    if not decision.run:
        return 0

    state.begin(week_of, claim_manual=decision.claim_manual)
    if decision.claim_manual:
        _say("수동 실행 요청을 집어 갔다. 연속 실패 횟수를 0으로 되돌린다")

    try:
        return _execute(state, args, week_of, now, steps)
    except CorruptState:
        # 손상된 상태 객체는 사람이 고쳐야 한다. 여기서 fail() 로 덮어쓰면 증거가 사라지고,
        # 반쯤 유효한 문서가 남아 다음 판정이 더 꼬인다.
        raise
    except Exception as error:
        return _abandon(state, week_of, error)


def _execute(state: WeeklyState, args, week_of: date, now: datetime,
             steps: list[dict]) -> int:
    """`begin()` 뒤의 본체. 여기서 터지는 것은 `main()` 이 FAILED 로 내려놓는다."""
    context = Context(root=ROOT, python=args.python, week_of=week_of,
                      dry_run=args.dry_run, minio_workers=args.minio_workers)
    _say(f"downloads 창 {window_start(week_of)}~{window_end(week_of)}, "
         f"run={download_run(week_of)}")

    finished = {item["step"]: item.get("status") for item in steps}
    selected = [args.only] if args.only else list(STEPS)
    failure: str | None = None
    deferred: str | None = None

    for step in selected:
        if finished.get(step) == "SUCCEEDED" and not args.force:
            _say(f"{step}: 이미 끝났다 (건너뜀)")
            continue
        _say(f"{step}: 시작")
        state.step_start(week_of, step)
        try:
            detail = HANDLERS[step](context)
        except StepNotReady as error:
            # 원천이 아직 준비되지 않았다. 실패가 아니라 "아직" 이므로 연속 실패 횟수를
            # 올리지 않는다 — 올리면 공급자가 두 시간 늦는 것만으로 BLOCKED 가 된다.
            # 다만 영원히 기다리지는 않는다. 창이 열린 뒤 유예 시간을 넘기면 사람이 볼 일이다.
            if snapshot_grace_expired(week_of, now):
                failure = (f"{step}: 원천이 유예 시간({SNAPSHOT_GRACE}) 안에 준비되지 않았다\n"
                           f"{error}")
                state.step_finish(week_of, step, "FAILED", error=failure)
                _say(f"{step}: 유예 시간을 넘겼다. 실패로 올린다")
                break
            deferred = step
            state.step_finish(week_of, step, "SKIPPED", detail={"reason": "source_not_ready"})
            break
        except StepError as error:
            failure = f"{step}: {error}"
            state.step_finish(week_of, step, "FAILED", error=str(error))
            _say(f"{step}: 실패")
            break
        except Exception as error:  # 예상 못 한 것도 회차 상태에 남긴다
            failure = f"{step}: {type(error).__name__}: {error}"
            state.step_finish(week_of, step, "FAILED", error=failure)
            _say(f"{step}: 실패 ({type(error).__name__})")
            break
        state.step_finish(week_of, step, "SUCCEEDED", detail=detail)
        _say(f"{step}: 끝")

    if failure:
        status, count = state.fail(week_of, failure)
        _say(f"회차 {status} (연속 {count}회). {failure.splitlines()[0]}")
        if status == "BLOCKED":
            _say("자동 재시도를 멈춘다. 수동 실행 요청이 오면 다시 시작한다")
        return 1

    if deferred:
        state.pause(week_of)
        _say(f"{deferred}: 원천이 아직 준비되지 않았다. 실패로 세지 않고 다음 발화에 다시 본다 "
             f"(유예 {SNAPSHOT_GRACE} 까지)")
        return 0

    # --only 로 한 단계만 돌렸을 수도 있으므로, 끝났는지는 저장된 단계 상태로 판정한다.
    _, _, steps = state.load(week_of)
    done = {item["step"] for item in steps if item.get("status") == "SUCCEEDED"}
    if set(STEPS) <= done:
        state.succeed(week_of)
        _say(f"회차 완료 — {len(STEPS)}단계 전부 성공")
        _purge(state, context, week_of, args)
        return 0
    state.pause(week_of)
    _say("남은 단계: " + ", ".join(s for s in STEPS if s not in done))
    return 0


def _abandon(state: WeeklyState, week_of: date, error: Exception) -> int:
    """단계 **밖에서** 터진 것. 대개 상태 저장소 쓰기 실패다.

    그대로 두면 문서가 RUNNING 인 채 남고, 다음 발화부터 `decide()` 가 "다른 실행이 진행
    중이다" 로 판단해 **STALE_RUNNING(26시간) 동안 아무것도 하지 않는다.** 화요일 창에
    걸리면 그 주 갱신이 하루 늦는다.

    그래서 한 번 더 시도해 FAILED 로 내려놓는다. 저장소가 잠깐 흔들린 경우라면 이것으로
    다음 발화가 바로 이어받는다 (boto3 가 이미 5회 재시도하므로, 여기까지 온 것은 그
    창을 넘긴 경우다). 그것마저 실패하면 고칠 방법이 없으므로 **무엇이 일어나는지 로그에
    분명히 적는다** — 26시간 동안 조용한 것이 정상으로 보이면 안 된다.
    """
    detail = f"{type(error).__name__}: {error}"
    _say(f"실행기가 단계 밖에서 중단됐다 — {detail}")
    traceback.print_exc()
    try:
        status, count = state.fail(week_of, "실행기 중단: " + detail)
        _say(f"회차 {status} (연속 {count}회). 다음 발화가 이어받는다")
    except Exception as second:
        _say(f"상태도 기록하지 못했다 ({type(second).__name__}). 회차가 RUNNING 으로 남아 "
             f"다음 발화는 {STALE_RUNNING} 동안 이 회차를 건너뛴다 — "
             f"먼저 상태 저장소를 살릴 것")
    return 1


def _purge(state: WeeklyState, context: Context, week_of: date, args) -> None:
    """지난 회차의 로컬 산출물을 치운다.

    회차가 끝난 뒤에만, 그리고 실패해도 회차 성공을 되돌리지 않는다 — 데이터는 이미
    Bronze 에 있고, 청소가 안 됐다고 수집을 실패로 표시하면 다음 발화가 23시간짜리 잡을
    다시 돌린다.
    """
    if args.keep_weeks < 0:
        return
    try:
        weeks = state.purgeable_weeks(week_of, args.keep_weeks)
    except Exception as error:  # 목록을 못 읽어도 회차는 성공이다
        _say(f"정리 대상 조회 실패: {error}")
        return
    if not weeks:
        return
    if args.dry_run:
        _say("정리 예정(dry-run): " + ", ".join(str(w) for w in weeks))
        return
    for week in weeks:
        try:
            removed = purge_week(context, week)
        except Exception as error:
            _say(f"정리 실패({week}): {error}")
            return
        if removed:
            _say(f"정리 {week}: {len(removed)}개 경로")


if __name__ == "__main__":
    raise SystemExit(main())
