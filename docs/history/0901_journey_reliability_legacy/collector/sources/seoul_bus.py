"""서울 버스 실시간 계열 어댑터 (Jira 96).

- `getBusPosByRouteSt` 버스 위치정보조회 (data.go.kr 15000332)
- `getArrInfoByRouteAll` 버스 도착정보조회 (data.go.kr 15000314)

두 API는 data.go.kr `DATA_GO_BUS_API_KEY` 하나를 쓰지만 **상세기능마다
1,000회/일 독립 quota**이며 지하철 키와도 별도 풀이다. 노선별 호출이라
호출량이 노선 수만큼 곱해진다.

    대상 노선 수 × (86,400 ÷ 폴링 주기 초) ≤ 950

지하철과 달리 공개 `sample` 키가 없어 정상 경로는 실제 키가 있어야 검증된다.
인증 실패 경로(HTTP 401 JSON)는 키 없이도 확인할 수 있다.

응답 계약 (분석 문서 기준)
  - 성공/실패는 HTTP 상태와 `msgHeader.headerCd`를 **함께** 봐야 한다.
  - `itemCount`는 신뢰하지 않는다. `itemCount=0`인데 `itemList`가 1개인
    사례가 실제로 관측됐다. 배열 원소를 직접 센다.
  - 게이트웨이 오류코드(`01`,`04`,`05`,`10`,`12`,`20`,`22`,`23`)와
    제공기관 업무코드(`0`~`8`)는 서로 다른 계층이다.
"""
from __future__ import annotations

import json
import re
import urllib.parse

from ..common.http_client import Verdict, fetch
from ..common.storage import CollectionResult

BASE_POSITION = "http://ws.bus.go.kr/api/rest/buspos/getBusPosByRouteSt"
BASE_POSITION_RTID = "http://ws.bus.go.kr/api/rest/buspos/getBusPosByRtid"
BASE_ARRIVAL = "http://ws.bus.go.kr/api/rest/arrive/getArrInfoByRouteAll"

SUCCESS_CODE = "0"

# 제공기관 업무코드. 값은 (의미, 재시도 가치 있음) 이다.
HEADER_CODES: dict[str, tuple[str, bool]] = {
    "0": ("정상", False),
    "1": ("시스템 오류", True),
    "2": ("잘못된 질의", False),
    "3": ("정류소 없음", False),
    "4": ("노선 없음", False),
    "5": ("잘못된 위치 좌표", False),
    "6": ("실시간 정보 조회 불가", True),
    "7": ("노선 검색 결과 없음", False),
    "8": ("서비스 종료", False),
}

_XML_HEADER_CD = re.compile(rb"<headerCd>([^<]*)</headerCd>")
_XML_HEADER_MSG = re.compile(rb"<headerMsg>([^<]*)</headerMsg>")
_XML_ITEM = re.compile(rb"<itemList>")


def is_retryable(header_cd: str | None) -> bool:
    """제한된 재시도가 의미 있는 업무코드인지. quota 원장(Jira 97)이 참조한다."""
    if header_cd is None:
        return False
    return HEADER_CODES.get(header_cd, ("", False))[1]


def judge(payload: bytes) -> Verdict:
    """`headerCd`로 업무 성공 여부를 판정하고 `itemList` 원소를 직접 센다."""
    stripped = payload.lstrip()

    if stripped.startswith(b"{"):
        try:
            body = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return Verdict(business_code=None, ok=False, message=f"JSON 파싱 실패: {exc}")

        # 인증 오류는 업무 XML이 아니라 게이트웨이 JSON으로 돌아온다.
        if "msgHeader" not in body and "msgBody" not in body:
            code = str(body.get("returnReasonCode") or body.get("resultCode") or "GATEWAY")
            return Verdict(
                business_code=code,
                ok=False,
                message=str(body.get("returnAuthMsg") or body.get("resultMsg") or body)[:200],
            )

        header = body.get("msgHeader") or {}
        code = str(header.get("headerCd")) if header.get("headerCd") is not None else None
        items = (body.get("msgBody") or {}).get("itemList")
        # 단건이면 dict, 복수면 list, 없으면 None으로 온다.
        if isinstance(items, list):
            row_count = len(items)
        elif isinstance(items, dict):
            row_count = 1
        else:
            row_count = 0
        return Verdict(
            business_code=code,
            row_count=row_count,
            ok=code == SUCCESS_CODE,
            message=header.get("headerMsg"),
        )

    code_match = _XML_HEADER_CD.search(payload)
    msg_match = _XML_HEADER_MSG.search(payload)
    code = code_match.group(1).decode("utf-8") if code_match else None
    return Verdict(
        business_code=code,
        row_count=len(_XML_ITEM.findall(payload)),
        ok=code == SUCCESS_CODE,
        message=msg_match.group(1).decode("utf-8") if msg_match else None,
    )


def _build(base: str, key: str, params: dict[str, str], fmt: str) -> str:
    query = {"serviceKey": key, **params}
    if fmt:
        query["resultType"] = fmt
    return f"{base}?{urllib.parse.urlencode(query)}"


def position(
    key: str,
    bus_route_id: str,
    start_ord: int = 1,
    end_ord: int = 200,
    fmt: str = "xml",
    **kw,
) -> CollectionResult:
    """15000332 — 노선별 차량 위치. `stopFlag 0→1` 전이의 원천이다.

    `startOrd`/`endOrd`는 선택이 아니라 필수다. 노선의 전체 정류장 수를
    모르면 노선 기본정보(OA-15262)나 노선 조회 API로 먼저 확인한다.

    분석 문서 결정에 따라 XML을 기본으로 둔다. JSON은 실제 키로 성공
    스모크 테스트를 통과한 뒤 전환한다.
    """
    url = _build(
        BASE_POSITION,
        key,
        {"busRouteId": bus_route_id, "startOrd": str(start_ord), "endOrd": str(end_ord)},
        fmt,
    )
    return fetch(
        source_key="bus_position",
        provider="data_go_kr",
        endpoint="getBusPosByRouteSt",
        url=url,
        secret=key,
        judge=judge,
        payload_ext=fmt,
        partition=f"route={bus_route_id}",
        **kw,
    )


def position_rtid(key: str, bus_route_id: str, fmt: str = "xml", **kw) -> CollectionResult:
    """15000332 getBusPosByRtid — 노선 전체 차량 위치(구간 지정 없음).

    getBusPosByRouteSt와 같은 위치정보조회 서비스지만 **별도 상세기능**이라
    quota가 독립이다(각 10,000/일). 그래서 이걸 두 번째 위치 소스로 쓰면
    위치 수집 노선 수를 배로 늘릴 수 있다. 응답 구조(msgHeader/itemList)는
    getBusPosByRouteSt와 동일해 같은 judge를 쓴다. `congetion`(혼잡도)도 포함된다.

    startOrd/endOrd가 없어 노선 전체 차량을 한 번에 준다.
    """
    url = _build(BASE_POSITION_RTID, key, {"busRouteId": bus_route_id}, fmt)
    return fetch(
        source_key="bus_position_rtid",
        provider="data_go_kr",
        endpoint="getBusPosByRtid",
        url=url,
        secret=key,
        judge=judge,
        payload_ext=fmt,
        partition=f"route={bus_route_id}",
        **kw,
    )


def arrival_all(key: str, bus_route_id: str, fmt: str = "xml", **kw) -> CollectionResult:
    """15000314 — 노선 전 정류장 도착 예정. 예측값이며 Actual 정답이 아니다.

    `exps*`는 예측, `term`은 계획 배차간격이다. 실제 도착·실제 배차간격의
    정답 데이터로 사용하지 않는다.
    """
    url = _build(BASE_ARRIVAL, key, {"busRouteId": bus_route_id}, fmt)
    return fetch(
        source_key="bus_arrival_all",
        provider="data_go_kr",
        endpoint="getArrInfoByRouteAll",
        url=url,
        secret=key,
        judge=judge,
        payload_ext=fmt,
        partition=f"route={bus_route_id}",
        **kw,
    )
