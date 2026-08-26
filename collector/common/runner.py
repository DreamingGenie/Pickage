"""quota를 소모하며 재시도까지 수행하는 수집 실행기 (Jira 94 재시도 항목 + 97).

재시도는 공짜가 아니라 **quota를 소모**한다. 그래서 재시도 정책과 quota 원장을
분리하지 않고 여기서 함께 다룬다. 재시도 폭주로 오전에 한도를 태우면 그날
하루치 수집이 통째로 사라진다.

재시도 판정은 세 단계다.

  1. 전송 실패 → 재시도 (일시적 네트워크 문제일 수 있음)
  2. HTTP 오류 → 5xx만 재시도. 4xx는 같은 요청을 다시 보내도 결과가 같다
  3. 업무 오류 → provider가 판정한다. 예를 들어 `ERROR-340`(권한 없음)이나
     `headerCd=2`(잘못된 질의)는 재시도해도 quota만 태운다
"""
from __future__ import annotations

from typing import Callable

from .quota import Pool, QuotaExceeded, QuotaLedger, sleep_backoff
from .storage import BUSINESS_ERROR, HTTP_ERROR, OK, TRANSPORT_ERROR, CollectionResult

BusinessRetryCheck = Callable[[str | None], bool]


def should_retry(result: CollectionResult, business_check: BusinessRetryCheck | None) -> bool:
    """이 결과를 재시도할 가치가 있는지 판정한다."""
    if result.outcome == OK:
        return False
    if result.outcome == TRANSPORT_ERROR:
        return True
    if result.outcome == HTTP_ERROR:
        return bool(result.http_status and 500 <= result.http_status < 600)
    if result.outcome == BUSINESS_ERROR:
        return business_check(result.business_code) if business_check else False
    return False


def collect(
    source_fn: Callable[..., CollectionResult],
    *args,
    ledger: QuotaLedger,
    pool: Pool,
    business_check: BusinessRetryCheck | None = None,
    max_attempts: int = 3,
    sleep: Callable[[int], float] = sleep_backoff,
    **kwargs,
) -> CollectionResult:
    """quota를 소모하며 1회 수집한다. 실패 시 정책에 따라 재시도한다.

    `source_fn`은 `quota_seq_today`와 `quota_pool`을 키워드로 받아야 한다.
    두 값은 Bronze 메타에 기록되어 원장이 유실됐을 때 카운터를 되살리는
    근거가 된다(`quota.counts_from_bronze`). 어댑터는 `**kw`로 받아
    `http_client.fetch()`에 그대로 넘기면 된다.

    quota는 **호출 직전에** 기록한다. 응답을 받은 뒤 기록하면 프로세스가
    중간에 죽었을 때 실제로 소모한 호출이 원장에서 누락된다.

    상한에 도달하면 `QuotaExceeded`를 던진다. 첫 시도에서 던져지면 호출 자체가
    일어나지 않고, 재시도 도중이면 마지막 결과를 반환한다.
    """
    last: CollectionResult | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            seq = ledger.consume(pool)
        except QuotaExceeded:
            if last is None:
                raise
            return last

        result = source_fn(
            *args, quota_seq_today=seq, quota_pool=pool.name, **kwargs
        )
        if result.outcome == OK:
            return result

        last = result
        if not should_retry(result, business_check):
            return result
        if attempt < max_attempts:
            sleep(attempt)

    return last  # type: ignore[return-value]
