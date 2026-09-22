"""주간 수집 회차 요약 — `_ops/weekly/<week_of>/run.json` 을 읽어 화면용으로 줄인다.

읽기만 한다. 판정 규칙(우편함이 아직 안 집어 갔는가)은 `pipeline.weekly.schedule` 의 것을
그대로 부른다 — 여기서 따로 판정하면 화면과 실행기가 어긋난다(그 함수의 docstring).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from pipeline.weekly.schedule import current_week_of, is_manual_pending, window_open, window_open_at
from pipeline.weekly.state import ObjectStore, manual_key, run_key

ERROR_SHOWN = 600       # 화면에 싣는 실패 메시지 길이. 전문은 run.json 과 단계 로그에 있다


def _moment(value) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _trim(text, limit: int):
    if not text:
        return None
    text = str(text)
    return text if len(text) <= limit else "…" + text[-limit:]


def summarize(week: date, document: dict | None, manual: dict | None) -> dict:
    requested = _moment((manual or {}).get("requested_at"))
    claimed = _moment((document or {}).get("manual_claimed_at"))
    row = {
        "week_of": week.isoformat(),
        # 회차 객체가 없는데 우편함만 있는 주 — 다음 발화가 집어 간다.
        "status": (document or {}).get("status") or ("REQUESTED" if requested else "NONE"),
        "manual": {"requested_at": (manual or {}).get("requested_at"),
                   "claimed_at": (document or {}).get("manual_claimed_at"),
                   "pending": is_manual_pending(requested, claimed)},
    }
    if not document:
        return row
    row.update({
        "started_at": document.get("started_at"),
        "finished_at": document.get("finished_at"),
        "updated_at": document.get("updated_at"),
        "consecutive_failures": document.get("consecutive_failures") or 0,
        "coverage": document.get("coverage") or {},
        "last_error": _trim(document.get("last_error"), ERROR_SHOWN),
        "steps": [{
            "step": item.get("step"),
            "status": item.get("status"),
            "attempt_count": item.get("attempt_count") or 0,
            "started_at": item.get("started_at"),
            "finished_at": item.get("finished_at"),
            "error_message": _trim(item.get("error_message"), ERROR_SHOWN),
            "detail": item.get("detail") or {},
        } for item in document.get("steps") or []],
    })
    return row


def collect(s3, *, bucket: str, max_runs: int, now: datetime) -> dict:
    store = ObjectStore(s3, bucket)
    weeks = store.weeks()                      # 최신순, LIST 한 번
    with_manual = set(store.manual_weeks())    # 우편함이 있는 주만, LIST 한 번
    runs = []
    for week in weeks[:max_runs]:
        document = store.get(run_key(week))
        manual = store.get(manual_key(week)) if week in with_manual else None
        runs.append(summarize(week, document, manual))
    # 이번 주 회차가 "아예 시작 안 한" 것을 본다. run.json 은 실행기가 begin() 할 때 생기므로 타이머가
    # 멎었거나 begin() 전에 죽었으면 이번 주 객체가 아예 없고, runs[0] 은 지난주 SUCCEEDED 그대로다 —
    # 그러면 화면은 계속 초록이고 downloads_through 만 조용히 낡는다. 주간 배치에서 제일 흔한 고장은
    # "실패" 가 아니라 "아무 일도 안 일어남" 이다. 판정 규칙은 새로 만들지 않고 실행기의 창 함수를 그대로 쓴다.
    this_week = current_week_of(now)
    opened = window_open(this_week, now)
    expected = {
        "week_of": this_week.isoformat(),
        "window_open_at": window_open_at(this_week).astimezone(timezone.utc).isoformat(timespec="seconds"),
        "window_open": opened,
        "present": this_week in weeks,           # run.json 이든 우편함이든 그 주 객체가 하나라도 있는가
        "missing": opened and this_week not in weeks,
    }
    return {"listed_at": now.astimezone(timezone.utc).isoformat(timespec="seconds"),
            "bucket": bucket, "weeks_total": len(weeks), "expected": expected, "runs": runs}
