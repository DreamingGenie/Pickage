"""실시간 Bronze 수집기 패키지.

**Python 3.11 이상이 필요하다.** `common/targets.py`가 `targets.toml`을 읽을 때
표준 라이브러리 `tomllib`을 쓰는데, 이 모듈은 3.11에 추가됐다.

3.10 이하에서는 `pip install -r requirements.txt`가 **성공한 뒤** 실행 단계에서
`ModuleNotFoundError: No module named 'tomllib'`로 죽는다. 원인이 의존성 누락처럼
보여 디버깅에 시간이 걸리므로, import 시점에 무엇이 문제인지 먼저 알린다.

Ubuntu 22.04의 기본 파이썬이 3.10이라 홈서버 배포에서 실제로 걸리는 항목이다.
"""
from __future__ import annotations

import sys

MIN_PYTHON = (3, 11)

if sys.version_info < MIN_PYTHON:
    raise RuntimeError(
        f"collector는 Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} 이상이 필요합니다. "
        f"현재 {sys.version_info.major}.{sys.version_info.minor}."
        " targets.toml을 읽는 표준 라이브러리 tomllib이 3.11에 추가됐습니다."
        " 3.10 이하에서는 실행 도중 ModuleNotFoundError로 중단됩니다."
    )
