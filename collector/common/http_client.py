"""수집 HTTP 호출 골격.

provider와 무관한 부분만 담당한다.
  - requested_at을 호출 직전, received_at을 응답 직후에 각각 기록
  - 원문을 가공 없이 바이트 그대로 보존
  - HTTP 상태와 업무코드를 분리 판정
  - 인증키 마스킹
  - 실패 응답도 Bronze에 저장(성공만 남기면 장애 구간과 무데이터를 구분할 수 없다)

업무코드 판정은 provider마다 다르므로 `judge` 콜러블을 주입받는다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import requests

from . import storage
from .env import mask_in_text
from .storage import (
    BUSINESS_ERROR,
    HTTP_ERROR,
    OK,
    TRANSPORT_ERROR,
    CollectionResult,
)


@dataclass
class Verdict:
    """원문에서 뽑아낸 업무 수준 판정."""

    business_code: str | None = None
    row_count: int | None = None
    ok: bool = True
    message: str | None = None


Judge = Callable[[bytes], Verdict]


def _no_judge(_: bytes) -> Verdict:
    return Verdict()


def fetch(
    *,
    source_key: str,
    provider: str,
    endpoint: str,
    url: str,
    secret: str | None = None,
    judge: Judge | None = None,
    payload_ext: str = "txt",
    timeout: float = 20.0,
    quota_seq_today: int | None = None,
) -> CollectionResult:
    """1회 호출하고 CollectionResult를 만든다. 저장은 호출자가 record()로 한다."""
    judge = judge or _no_judge
    masked_url = mask_in_text(url, secret) if secret else url

    requested_at = storage.now_iso()
    try:
        resp = requests.get(url, timeout=timeout)
        received_at = storage.now_iso()
    except requests.RequestException as exc:
        received_at = storage.now_iso()
        return CollectionResult(
            source_key=source_key,
            provider=provider,
            endpoint=endpoint,
            requested_at=requested_at,
            received_at=received_at,
            request_url_masked=masked_url,
            http_status=None,
            payload=None,
            payload_ext=payload_ext,
            outcome=TRANSPORT_ERROR,
            error_code=type(exc).__name__,
            error_body=str(exc),
            quota_seq_today=quota_seq_today,
        )

    payload = resp.content

    if not resp.ok:
        return CollectionResult(
            source_key=source_key,
            provider=provider,
            endpoint=endpoint,
            requested_at=requested_at,
            received_at=received_at,
            request_url_masked=masked_url,
            http_status=resp.status_code,
            payload=payload,
            payload_ext=payload_ext,
            outcome=HTTP_ERROR,
            error_code=f"HTTP_{resp.status_code}",
            error_body=resp.reason,
            quota_seq_today=quota_seq_today,
        )

    verdict = judge(payload)
    return CollectionResult(
        source_key=source_key,
        provider=provider,
        endpoint=endpoint,
        requested_at=requested_at,
        received_at=received_at,
        request_url_masked=masked_url,
        http_status=resp.status_code,
        payload=payload,
        payload_ext=payload_ext,
        business_code=verdict.business_code,
        row_count=verdict.row_count,
        outcome=OK if verdict.ok else BUSINESS_ERROR,
        error_code=None if verdict.ok else verdict.business_code,
        error_body=None if verdict.ok else verdict.message,
        quota_seq_today=quota_seq_today,
    )
