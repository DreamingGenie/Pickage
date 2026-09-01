"""표준 출력 인코딩 보정.

Windows에서 파이썬 출력이 콘솔이 아니라 **파이프·파일로 넘어가면** 인코딩이
로케일 기본값(한국어 Windows는 cp949)으로 정해진다. cp949로 표현할 수 없는
문자가 한 글자라도 섞이면 `UnicodeEncodeError`로 그 줄이 아니라 프로세스 전체가
죽는다. 실제로 `smoke_test.py`가 em-dash(U+2014) 한 글자 때문에 진단 출력
도중에 중단됐다.

로그 한 줄 때문에 수집이 멈추는 것은 곤란하므로, 진입점에서 한 번 호출해
UTF-8 + errors="replace"로 바꿔 둔다. 실제 콘솔에 붙어 있을 때는 Windows가
이미 UTF-16으로 처리하므로 이 호출이 아무것도 바꾸지 않는다.
"""
from __future__ import annotations

import sys


def use_utf8() -> None:
    """stdout/stderr를 UTF-8로 재설정한다. 실패해도 조용히 넘어간다."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            # 이미 닫힌 스트림이거나 재설정할 수 없는 래퍼일 수 있다.
            pass
