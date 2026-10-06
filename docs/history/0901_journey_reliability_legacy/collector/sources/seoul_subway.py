"""서울 지하철 실시간 계열 어댑터 (Jira 95).

- OA-15799 실시간 도착정보(일괄) `realtimeStationArrival/ALL`  — 정규 수집 대상
- OA-12601 실시간 열차 위치정보 `realtimePosition`             — 정규 수집 대상
- OA-12764 실시간 도착정보(역별) `realtimeStationArrival`      — 검증·예비 전용

세 API는 `SEOUL_SUBWAY_REALTIME_KEY` 1개의 1일 1,000회 한도를 **공유**한다
(인증키 단위 한도). 예산 배분은 docs/DATA_PLATFORM_PLAN_260826.md 5-3절 참조.

키 대신 `sample`을 넣으면 공개 샘플 응답으로 스모크 테스트할 수 있다.
샘플 키는 반환 행 수가 제한되며 역별 조회는 범위 0/5까지만 허용한다.
"""
from __future__ import annotations

import json
import re
import urllib.parse

from ..common.http_client import Verdict, fetch
from ..common.storage import CollectionResult

BASE = "http://swopenAPI.seoul.go.kr/api/subway"

# 서울 지하철 실시간 API 공통 성공 업무코드
_SUCCESS_CODE = "INFO-000"
# 조건에 맞는 행이 없음. 오류가 아니라 정상적인 빈 결과다.
_NO_RESULT_CODE = "INFO-200"

# 재시도해도 결과가 달라지지 않는 오류. quota만 소모하므로 즉시 중단한다.
# ERROR-340은 2026-08-26 실호출에서 처음 관측됐으며 분석 문서의 코드표에 없다.
# 일괄(ALL) 서비스에 대한 인증키 권한이 없을 때 반환된다.
PERMANENT_ERRORS = {
    "ERROR-300",  # 필수값 누락
    "ERROR-301",  # TYPE 오류
    "ERROR-310",  # 서비스명 오류
    "ERROR-331",  # 시작 인덱스 오류
    "ERROR-332",
    "ERROR-333",
    "ERROR-334",  # 종료 인덱스 오류
    "ERROR-335",  # 샘플 키 제한 초과
    "ERROR-336",  # 요청 건수 1,000건 초과
    "ERROR-340",  # 해당 인증키로 사용할 수 없는 서비스
}


def is_retryable(business_code: str | None) -> bool:
    """재시도가 의미 있는 오류인지. quota 원장(Jira 97)이 참조한다."""
    if business_code is None:
        return True  # 파싱 실패 등 원인 불명은 제한적 재시도 허용
    return business_code not in PERMANENT_ERRORS

_XML_CODE = re.compile(rb"<code>([^<]+)</code>")
_XML_TOTAL = re.compile(rb"<(?:list_)?total(?:Count)?>(\d+)</(?:list_)?total(?:Count)?>")


def judge(payload: bytes) -> Verdict:
    """원문에서 업무코드와 행 수를 뽑아 성공 여부를 판정한다.

    HTTP 200이어도 업무코드가 오류인 경우가 실제로 존재한다
    (예: ERROR-336 조회 건수 초과). 이중 판정이 필요한 이유다.
    """
    stripped = payload.lstrip()
    if stripped.startswith(b"{"):
        try:
            body = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return Verdict(business_code=None, ok=False, message=f"JSON 파싱 실패: {exc}")

        # 서울 지하철 API는 envelope 형태가 두 가지다.
        #   성공/무결과: {"errorMessage": {"code": "INFO-000", ...}, "realtimeArrivalList": [...]}
        #   업무 오류  : {"status": 500, "code": "ERROR-336", "message": "...", "total": 0}
        # 두 번째 형태를 놓치면 업무코드가 유실되므로 top-level도 함께 본다.
        header = body.get("errorMessage") or {}
        code = header.get("code") or body.get("code")
        message = header.get("message") or body.get("message")
        rows = body.get("realtimeArrivalList") or body.get("realtimePositionList") or []
        row_count = len(rows) if isinstance(rows, list) and rows else header.get("total") or body.get("total")
        return Verdict(
            business_code=code,
            row_count=row_count if isinstance(row_count, int) else None,
            ok=code in (_SUCCESS_CODE, _NO_RESULT_CODE),
            message=message,
        )

    code_match = _XML_CODE.search(payload)
    total_match = _XML_TOTAL.search(payload)
    code = code_match.group(1).decode("utf-8") if code_match else None
    return Verdict(
        business_code=code,
        row_count=int(total_match.group(1)) if total_match else None,
        ok=code in (_SUCCESS_CODE, _NO_RESULT_CODE),
        message=None,
    )


def arrival_all(key: str, fmt: str = "json", **kw) -> CollectionResult:
    """OA-15799 — 전 역 도착정보를 1회 호출로 가져온다."""
    url = f"{BASE}/{key}/{fmt}/realtimeStationArrival/ALL"
    return fetch(
        source_key="subway_arrival_all",
        provider="seoul_open_data",
        endpoint="realtimeStationArrival/ALL",
        url=url,
        secret=key,
        judge=judge,
        payload_ext=fmt,
        **kw,
    )


def position(
    key: str, line_name: str, start: int = 0, end: int = 1000, fmt: str = "json", **kw
) -> CollectionResult:
    """OA-12601 — 노선별 열차 위치.

    조회 범위 기본값은 공식 1회 한도인 0/1000이다. `sample` 키는 반환 행이
    5건으로 제한되어 0/1000을 `ERROR-336`으로 거절하므로, 스모크 테스트에서는
    0/5로 호출한다.
    """
    url = (
        f"{BASE}/{key}/{fmt}/realtimePosition/{start}/{end}/"
        f"{urllib.parse.quote(line_name)}"
    )
    return fetch(
        source_key="subway_position",
        provider="seoul_open_data",
        endpoint="realtimePosition",
        url=url,
        secret=key,
        judge=judge,
        payload_ext=fmt,
        partition=f"line={line_name}",
        **kw,
    )


def arrival_station(
    key: str, station_name: str, start: int = 0, end: int = 20, fmt: str = "json", **kw
) -> CollectionResult:
    """OA-12764 — 역별 도착정보. 정규 수집이 아니라 검증·예비 전용이다.

    역 수만큼 호출이 곱해져 공유 quota 안에 들어올 수 없다.
    """
    url = (
        f"{BASE}/{key}/{fmt}/realtimeStationArrival/{start}/{end}/"
        f"{urllib.parse.quote(station_name)}"
    )
    return fetch(
        source_key="subway_arrival_station",
        provider="seoul_open_data",
        endpoint="realtimeStationArrival",
        url=url,
        secret=key,
        judge=judge,
        payload_ext=fmt,
        partition=f"station={station_name}",
        **kw,
    )
