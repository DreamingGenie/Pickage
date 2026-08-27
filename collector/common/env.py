"""수집기 secret 로딩.

`collector/.env.local`(gitignored, 절대 커밋 금지)을 읽어 논리 이름으로 키를 노출한다.
실제 값은 어디에도 출력하거나 로깅하지 않는다.

출처: docs/history/journey_reliability_docs_v2/baseline/phase0/scripts/spikes/common/env.py
변경: 경로를 collector/ 기준으로 조정하고 안내 문구를 현재 구조에 맞춤.
"""
from __future__ import annotations

import os
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


def redact(value: str, keep: int = 4) -> str:
    """앞4...뒤4 형태로 마스킹. 우발적 로깅 대비용."""
    if not value:
        return ""
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}...{value[-keep:]}"


def mask_in_text(text: str, secret: str) -> str:
    """URL 등 임의 문자열에 섞인 secret을 마스킹한다.

    서울 열린데이터광장 계열은 인증키가 URL path에 들어가므로
    query param 제거만으로는 마스킹되지 않는다.
    """
    if not secret or not text:
        return text
    return text.replace(secret, "***")
