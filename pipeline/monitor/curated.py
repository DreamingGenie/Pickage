"""Curated 전처리 회차 요약 — raw → Curated 디스패처가 남기는 상태를 읽어 화면용으로 줄인다.

S15P21A506-372 의 `pipeline.preprocessing.orchestration.dispatcher` 는 주간 수집이 끝난 뒤 같은
타이머에서 돌며 흔적을 셋 남긴다 (전부 `pickage-curated`).

    _ops/preprocessing/<날짜>/status.json          회차 상태 — RUNNING·COMPLETE·FAILED·BLOCKED·WAITING_INPUT,
                                                   attempt·consecutive_failures·next_retry_at·error
    _ops/preprocessing/_dispatcher/status.json     디스패처 자체 — TICK_FINISHED(+exit_code) 또는 연결·baseline 오류
    depsdev/v1/curated-bundle/_current.json        완료된 최신 bundle 포인터 (snapshot·run_prefix·manifest_sha256)
    depsdev/v1/curated-bundle/snapshot=S/run_id=R/status.json
                                                   실행기 상태 — 6단계(snapshot → … → dependents) 각각의 status·attempt

읽기만 한다. 판정(무엇이 BLOCKED 인가)은 디스패처가 status 에 적은 것을 그대로 보여 준다 —
여기서 다시 계산하면 화면과 실행기가 어긋난다. 단계 순서는 실행기가 status.json 에 넣은 순서(STAGES)
그대로다. 그 모듈을 import 하지 않는 이유: 이 브랜치가 없는 체크아웃에서도 모니터는 떠야 한다.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

OPS = "_ops/preprocessing"
BUNDLE = "depsdev/v1/curated-bundle"
DISPATCHER = "_dispatcher"
ERROR_SHOWN = 600       # 화면에 싣는 오류 길이. 전문은 status.json·events/ 에 있다


def _trim(text, limit: int = ERROR_SHOWN):
    if not text:
        return None
    text = str(text)
    return text if len(text) <= limit else "…" + text[-limit:]


def _missing(error: Exception) -> bool:
    response = getattr(error, "response", None)
    if isinstance(response, dict):
        code = response.get("Error", {}).get("Code")
        return code in ("NoSuchKey", "404", "NotFound")
    return False


def _get_json(s3, bucket: str, key: str):
    """없으면 None. JSON 이 아니면 {"_error": …} — 조용히 비우지 않는다."""
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
    except Exception as error:
        if _missing(error):
            return None
        raise
    with response["Body"] as stream:
        body = stream.read().decode("utf-8")
    try:
        return json.loads(body)
    except ValueError:
        return {"_error": "JSON 이 아니다"}


def _snapshots(s3, bucket: str) -> list[str]:
    """`_ops/preprocessing/` 바로 아래 디렉터리 이름 — 날짜들과 `_dispatcher`. 최신순. LIST 한 번(페이지)."""
    found = []
    token = None
    while True:
        request = {"Bucket": bucket, "Prefix": OPS + "/", "Delimiter": "/"}
        if token:
            request["ContinuationToken"] = token
        page = s3.list_objects_v2(**request)
        for item in page.get("CommonPrefixes", []) or []:
            name = item["Prefix"].rstrip("/").rsplit("/", 1)[-1]
            if name != DISPATCHER:
                found.append(name)
        if not page.get("IsTruncated"):
            break
        token = page.get("NextContinuationToken")
    return sorted(found, reverse=True)


def _error_of(document: dict | None) -> dict | None:
    error = (document or {}).get("error")
    if not error:
        return None
    if isinstance(error, dict):
        return {"type": error.get("type"), "message": _trim(error.get("message"))}
    return {"type": None, "message": _trim(error)}


def summarize(snapshot: str, state: dict | None, run_state: dict | None, current: dict | None) -> dict:
    """디스패처 상태 + 실행기 상태 → 표 한 줄. 실행기 상태가 없으면 단계는 빈 목록이다."""
    state = state or {}
    row = {
        "snapshot": snapshot,
        "run_id": state.get("run_id"),
        "status": state.get("status") or "NONE",
        "attempt": state.get("attempt") or 0,
        "consecutive_failures": state.get("consecutive_failures") or 0,
        "started_at": state.get("started_at"),
        "finished_at": state.get("finished_at"),
        "next_retry_at": state.get("next_retry_at"),
        "updated_at": state.get("updated_at"),
        "error": _error_of(state),
        "is_current": bool(current and current.get("snapshot") == snapshot),
        "phase": (run_state or {}).get("phase"),
        "stages": [],
    }
    stages = (run_state or {}).get("stages")
    if isinstance(stages, dict):
        row["stages"] = [{
            "stage": name,
            "status": (item or {}).get("status"),
            "attempt": (item or {}).get("attempt") or 0,
            "started_at": (item or {}).get("started_at"),
            "finished_at": (item or {}).get("finished_at"),
            "action": (item or {}).get("action"),          # REVERIFIED = 지난 시도의 결과를 검증해 재사용
            "error": _error_of(item if isinstance(item, dict) else None),
        } for name, item in stages.items()]
    return row


def collect(s3, *, bucket: str, max_runs: int, now: datetime) -> dict:
    snapshots = _snapshots(s3, bucket)                                   # LIST 1
    current = _get_json(s3, bucket, f"{BUNDLE}/_current.json")          # GET 1
    dispatcher = _get_json(s3, bucket, f"{OPS}/{DISPATCHER}/status.json")   # GET 1
    runs = []
    for snapshot in snapshots[:max_runs]:                                # 회차당 GET 2
        state = _get_json(s3, bucket, f"{OPS}/{snapshot}/status.json")
        run_state = None
        run_id = (state or {}).get("run_id")
        if run_id:
            run_state = _get_json(s3, bucket, f"{BUNDLE}/snapshot={snapshot}/run_id={run_id}/status.json")
        runs.append(summarize(snapshot, state, run_state, current))
    return {
        "listed_at": now.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "bucket": bucket,
        "snapshots_total": len(snapshots),
        "current": ({"snapshot": current.get("snapshot"), "run_prefix": current.get("run_prefix")}
                    if isinstance(current, dict) and "_error" not in current else None),
        "dispatcher": ({"status": dispatcher.get("status"), "exit_code": dispatcher.get("exit_code"),
                        "error": _error_of(dispatcher), "updated_at": dispatcher.get("updated_at") or dispatcher.get("at")}
                       if isinstance(dispatcher, dict) else None),
        "runs": runs,
    }
