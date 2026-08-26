"""운행일(service_date) 변환.

자정을 넘겨 운행하는 대중교통 데이터를 어느 날짜에 귀속시킬지 결정한다.
2026-08-26 새벽 1시에 도착한 열차는 2026-08-25 운행일 소속이다.

경계 시각 기본값은 04:00 KST다. 이 값은 provider별 확인 후 확정해야 하며
(Jira: 운행일 규칙 정의 이슈), 확정 전까지는 원문 시각을 그대로 보존하고
이 함수는 파티션 키 계산에만 사용한다.

파티션 키를 달력 날짜로 잡으면 나중에 전면 재적재가 필요하므로,
Bronze 첫 적재 시점부터 이 함수를 쓴다.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))

# 운행일 경계 시각(KST). 이 시각 이전은 전날 운행일로 귀속한다.
SERVICE_DAY_BOUNDARY_HOUR = 4


def to_kst(dt: datetime) -> datetime:
    """tz-aware datetime을 KST로 변환한다. naive면 UTC로 간주한다."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(KST)


def service_date(dt: datetime, boundary_hour: int = SERVICE_DAY_BOUNDARY_HOUR) -> str:
    """관측 시각을 운행일 문자열(YYYY-MM-DD)로 변환한다."""
    kst = to_kst(dt)
    if kst.hour < boundary_hour:
        kst = kst - timedelta(days=1)
    return kst.strftime("%Y-%m-%d")


def service_date_from_iso(iso_text: str, boundary_hour: int = SERVICE_DAY_BOUNDARY_HOUR) -> str:
    """ISO8601 문자열을 운행일로 변환한다."""
    return service_date(datetime.fromisoformat(iso_text), boundary_hour)


def parse_hhmm_over24(value: str) -> tuple[int, int, int, int]:
    """`25:10:00` 같은 24시 이상 표기를 (일수보정, 시, 분, 초)로 분해한다.

    OA-22522 열차운행시각표에 24시 이상 행이 4,475건 존재한다.
    반환한 일수보정만큼 운행일 다음 날로 넘어간다.
    """
    parts = value.strip().split(":")
    if len(parts) == 2:
        parts.append("00")
    hour, minute, second = (int(p) for p in parts)
    day_offset, hour = divmod(hour, 24)
    return day_offset, hour, minute, second
