"""수집기 secret 로딩.

`collector/.env.local`(gitignored, 절대 커밋 금지)을 읽어 논리 이름으로 키를 노출한다.
실제 값은 어디에도 출력하거나 로깅하지 않는다.

출처: docs/history/journey_reliability_docs_v2/baseline/phase0/scripts/spikes/common/env.py
변경: 경로를 collector/ 기준으로 조정하고 안내 문구를 현재 구조에 맞춤.
"""
from __future__ import annotations

import os
import re
import sys
import urllib.parse
from pathlib import Path

from dotenv import load_dotenv

_COLLECTOR_ROOT = Path(__file__).resolve().parent.parent
_ENV_LOCAL = _COLLECTOR_ROOT / ".env.local"
load_dotenv(_ENV_LOCAL)


class MissingSecretError(RuntimeError):
    pass


def require_key(name: str) -> str:
    """이름에 해당하는 환경변수를 반환한다. 값 자체는 절대 메시지에 넣지 않는다."""
    value = os.environ.get(name)
    if not value:
        raise MissingSecretError(
            f"{name}이(가) 설정되지 않았습니다. collector/.env.example을 "
            f"collector/.env.local로 복사하고 {name} 값을 채우세요. "
            f"값 자체는 로컬에만 두고 채팅·커밋·로그에 붙여넣지 않습니다."
        )
    return value


def optional_key(name: str, default: str | None = None) -> str | None:
    """없어도 되는 환경변수. sample 키로 스모크 테스트할 때 사용."""
    return os.environ.get(name) or default


_PERCENT_ENCODED = re.compile(r"%[0-9A-Fa-f]{2}")


def looks_url_encoded(value: str) -> bool:
    """이미 퍼센트 인코딩된 키인지 추정한다.

    data.go.kr은 인증키를 `인코딩키`와 `디코딩키` 두 형태로 제공한다.
    이 수집기는 요청을 만들 때 키를 다시 인코딩하므로 **디코딩키**를 넣어야 한다.
    인코딩키를 넣으면 이중 인코딩되어 HTTP 401이 나는데, 원인이 키 자체 문제로
    보여 디버깅에 시간이 걸린다. 그래서 미리 경고한다.
    """
    return bool(_PERCENT_ENCODED.search(value))


def warn_if_encoded(name: str, value: str) -> None:
    """인코딩키로 보이면 stderr에 경고한다. 값 자체는 출력하지 않는다."""
    if looks_url_encoded(value):
        print(
            f"[경고] {name}이(가) 이미 URL 인코딩된 값으로 보입니다(%XX 포함). "
            f"data.go.kr은 인코딩키와 디코딩키를 함께 제공하는데, 이 수집기는 "
            f"요청 시 키를 다시 인코딩하므로 **디코딩키**를 넣어야 합니다. "
            f"인코딩키를 쓰면 이중 인코딩으로 HTTP 401이 납니다.",
            file=sys.stderr,
        )


def redact(value: str, keep: int = 4) -> str:
    """앞4...뒤4 형태로 마스킹. 우발적 로깅 대비용."""
    if not value:
        return ""
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}...{value[-keep:]}"


def mask_in_text(text: str, secret: str) -> str:
    """URL 등 임의 문자열에 섞인 secret을 마스킹한다.

    두 가지 형태를 모두 지운다.

    1. 원문 그대로 — 서울 열린데이터광장 계열은 인증키가 URL **path**에
       들어가므로 query param을 제거하는 것만으로는 마스킹되지 않는다.
    2. URL 인코딩된 형태 — data.go.kr 계열은 키가 query string에 들어가며
       `+`나 `%2F` 같은 문자를 포함해 퍼센트 인코딩된다. 원문만 치환하면
       인코딩된 키가 그대로 메타에 남는다.
    """
    if not secret or not text:
        return text
    masked = text.replace(secret, "***")
    encoded = urllib.parse.quote(secret, safe="")
    if encoded != secret:
        masked = masked.replace(encoded, "***")
    # urlencode는 공백을 '+'로 바꾸므로 quote_plus 형태도 함께 지운다.
    plus_encoded = urllib.parse.quote_plus(secret)
    if plus_encoded not in (secret, encoded):
        masked = masked.replace(plus_encoded, "***")
    return masked
