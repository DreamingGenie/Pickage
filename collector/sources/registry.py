"""수집 대상 종류 레지스트리 (Jira 95·96·98 공용).

CLI(`run_collector.py`)와 스케줄러(`run_scheduler.py`)가 어댑터 함수·quota
풀 이름·키 환경변수·재시도 판정을 **같은 정의**로 쓰게 하려고 한곳에 모았다.
이전에는 이 매핑이 CLI의 if/else 안에만 있어서, 스케줄러가 같은 분기를 다시
쓰면 두 경로가 어긋날 수 있었다(예: 지하철 세 API가 quota 풀을 공유한다는
규칙을 한쪽만 지키는 상황).

`pool_name`은 기존 원장(`data/quota_ledger.json`)의 카운터 키와 **글자 단위로
같아야** 한다. 바꾸면 그날 누적 호출 수가 0부터 다시 세어져 상한을 넘긴다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..common.quota import DEFAULT_HARD_CAP, Pool, key_id
from ..common.storage import CollectionResult
from . import seoul_bus, seoul_subway

# ── 키 환경변수 ────────────────────────────────────────────────────────
SUBWAY_KEY_ENV = "SEOUL_SUBWAY_REALTIME_KEY"
# 일괄 도착(OA-15799) 전용 키. 위치와 다른 키를 쓰면 위치 예산과 안 겹친다
# (한도는 인증키 단위라, 별도 키 = 별도 950/일).
SUBWAY_ARRIVAL_ALL_KEY_ENV = "SEOUL_SUBWAY_ARRIVAL_ALL_KEY"
BUS_KEY_ENV = "DATA_GO_BUS_API_KEY"

# ── quota 풀 이름 ─────────────────────────────────────────────────────
# 지하철 위치·역별: 인증키 1개의 한도를 공유하므로 풀이 하나다.
POOL_SUBWAY = "seoul_subway_realtime"
# 일괄 도착: 전용 키를 쓰므로 위치와 별개 풀로 집계한다.
POOL_SUBWAY_ARRIVAL_ALL = "seoul_subway_arrival_all"
# 버스: data.go.kr은 상세기능(엔드포인트)마다 독립 quota다.
POOL_BUS_POSITION = "data_go_bus::getBusPosByRouteSt"
POOL_BUS_ARRIVAL = "data_go_bus::getArrInfoByRouteAll"


class UnknownSource(KeyError):
    """설정에 등록되지 않은 source 이름이 들어왔다."""


class BadParams(ValueError):
    """source에 맞지 않는 파라미터가 들어왔다."""


@dataclass(frozen=True)
class SourceSpec:
    """수집 대상 1종의 정적 정의.

    `params`는 어댑터 함수의 **키워드 인자 이름 그대로** 쓴다. 별도 이름을
    두고 매핑 표를 만들면 어댑터 시그니처가 바뀔 때 표만 낡아 조용히 깨진다.
    """

    name: str
    key_env: str
    pool_name: str
    fn: Callable[..., CollectionResult]
    business_check: Callable[[str | None], bool]
    default_fmt: str
    required_params: tuple[str, ...] = ()
    optional_params: tuple[str, ...] = ()
    note: str = ""

    @property
    def allowed_params(self) -> tuple[str, ...]:
        return self.required_params + self.optional_params


SPECS: dict[str, SourceSpec] = {
    "subway-arrival-all": SourceSpec(
        name="subway-arrival-all",
        key_env=SUBWAY_ARRIVAL_ALL_KEY_ENV,
        pool_name=POOL_SUBWAY_ARRIVAL_ALL,
        fn=seoul_subway.arrival_all,
        business_check=seoul_subway.is_retryable,
        default_fmt="json",
        note="OA-15799. 1콜에 19노선 전부. arvlCd=1(도착)+recptnDt가 실제 도착 이벤트다. "
             "전용 키로 위치 예산과 분리. 2026-08-27 권한 활성 확인.",
    ),
    "subway-position": SourceSpec(
        name="subway-position",
        key_env=SUBWAY_KEY_ENV,
        pool_name=POOL_SUBWAY,
        fn=seoul_subway.position,
        business_check=seoul_subway.is_retryable,
        default_fmt="json",
        required_params=("line_name",),
        optional_params=("start", "end"),
        note="OA-12601. Actual(실제 도착 관측)의 주 경로다.",
    ),
    "subway-arrival-station": SourceSpec(
        name="subway-arrival-station",
        key_env=SUBWAY_KEY_ENV,
        pool_name=POOL_SUBWAY,
        fn=seoul_subway.arrival_station,
        business_check=seoul_subway.is_retryable,
        default_fmt="json",
        required_params=("station_name",),
        optional_params=("start", "end"),
        note="OA-12764. 역 수만큼 호출이 곱해져 정규 수집 대상이 아니다(검증·예비).",
    ),
    "bus-position": SourceSpec(
        name="bus-position",
        key_env=BUS_KEY_ENV,
        pool_name=POOL_BUS_POSITION,
        fn=seoul_bus.position,
        business_check=seoul_bus.is_retryable,
        default_fmt="xml",
        required_params=("bus_route_id",),
        optional_params=("start_ord", "end_ord"),
        note="15000332. stopFlag 0->1 전이의 유일한 원천이다.",
    ),
    "bus-arrival-all": SourceSpec(
        name="bus-arrival-all",
        key_env=BUS_KEY_ENV,
        pool_name=POOL_BUS_ARRIVAL,
        fn=seoul_bus.arrival_all,
        business_check=seoul_bus.is_retryable,
        default_fmt="xml",
        required_params=("bus_route_id",),
        note="15000314. 예측값이며 Actual 정답이 아니다.",
    ),
}


def names() -> list[str]:
    return list(SPECS)


def get(name: str) -> SourceSpec:
    try:
        return SPECS[name]
    except KeyError:
        raise UnknownSource(
            f"source '{name}'을(를) 모릅니다. 사용 가능: {', '.join(names())}"
        ) from None


def validate_params(spec: SourceSpec, params: dict) -> None:
    """설정 파일의 파라미터가 어댑터 시그니처에 맞는지 확인한다.

    오타를 조용히 넘기면 기본값으로 호출되어 엉뚱한 대상을 하루 종일 수집한다.
    그 호출은 quota를 소모하고 실시간이라 되돌릴 수 없다. 그래서 즉시 막는다.
    """
    missing = [p for p in spec.required_params if p not in params]
    if missing:
        raise BadParams(f"{spec.name}: 필수 파라미터 누락 {missing}")
    unknown = [p for p in params if p not in spec.allowed_params and p != "fmt"]
    if unknown:
        raise BadParams(
            f"{spec.name}: 알 수 없는 파라미터 {unknown}. "
            f"사용 가능: {list(spec.allowed_params) + ['fmt']}"
        )


def make_pool(spec: SourceSpec, key: str, hard_cap: int = DEFAULT_HARD_CAP) -> Pool:
    """이 source가 소모하는 quota 풀을 만든다.

    키가 다르면 카운터도 독립이다(팀원 키를 추가로 쓰는 경우).
    """
    return Pool(spec.pool_name, key_id(key), hard_cap=hard_cap)
