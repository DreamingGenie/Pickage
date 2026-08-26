"""quota 원장과 일일 호출 상한 (Jira 97).

호출 한도는 provider마다 집계 단위가 다르다.

  서울 열린데이터광장 지하철  인증키 1개당 1일 1,000회. **여러 API가 공유**한다.
  data.go.kr 버스              상세기능(엔드포인트)마다 1일 1,000회 독립.

따라서 카운터 키는 `(pool_name, key_id)` 쌍이다. `pool_name`은 지하철이면
인증키 단위 풀 이름 하나, 버스면 엔드포인트별 풀 이름이다.

키를 여러 개 쓰는 경우(`SEOUL_SUBWAY_REALTIME_KEY_2` 등) 키마다 독립 카운터를
잡는다. 키를 늘릴 때 코드를 고치지 않고 `.env.local`에만 추가하면 된다.

카운터는 운행일(service_date) 기준으로 리셋한다. 달력 날짜로 리셋하면 새벽
운행분이 다음 날 예산을 먹는다.

원장은 JSON 파일로 유지해 프로세스를 재시작해도 당일 카운트가 이어진다.
"""
from __future__ import annotations

import json
import os
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import service_day

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_LEDGER_PATH = _REPO_ROOT / "data" / "quota_ledger.json"

# provider별 기본 한도와 자동 중단 상한
DEFAULT_LIMIT = 1000
DEFAULT_HARD_CAP = 950


class QuotaExceeded(RuntimeError):
    """상한에 도달해 호출을 거부했다."""


@dataclass
class Pool:
    """하나의 quota 집계 단위."""

    name: str
    key_id: str
    limit: int = DEFAULT_LIMIT
    hard_cap: int = DEFAULT_HARD_CAP

    @property
    def counter_key(self) -> str:
        return f"{self.name}::{self.key_id}"


def key_id(secret: str | None) -> str:
    """키 값을 노출하지 않고 카운터를 구분할 식별자를 만든다."""
    if not secret:
        return "none"
    if secret == "sample":
        return "sample"
    import hashlib

    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:8]


@dataclass
class QuotaLedger:
    """운행일 단위 호출 원장. 파일에 즉시 반영한다."""

    path: Path = DEFAULT_LEDGER_PATH
    _state: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._load()

    # ── 파일 입출력 ────────────────────────────────────────────────
    def _load(self) -> None:
        if self.path.exists():
            try:
                self._state = json.loads(self.path.read_text(encoding="utf-8"))
                return
            except json.JSONDecodeError:
                pass
        self._state = {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._state, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    # ── 카운터 ────────────────────────────────────────────────────
    def _today(self, now: datetime | None = None) -> str:
        return service_day.service_date(now or datetime.now(timezone.utc))

    def _bucket(self, svc_date: str) -> dict:
        return self._state.setdefault(svc_date, {})

    def used(self, pool: Pool, now: datetime | None = None) -> int:
        return int(self._bucket(self._today(now)).get(pool.counter_key, 0))

    def remaining(self, pool: Pool, now: datetime | None = None) -> int:
        return max(0, pool.hard_cap - self.used(pool, now))

    def check(self, pool: Pool, now: datetime | None = None) -> None:
        """상한에 도달했으면 QuotaExceeded를 던진다."""
        if self.used(pool, now) >= pool.hard_cap:
            raise QuotaExceeded(
                f"{pool.counter_key}: 일일 상한 {pool.hard_cap}회에 도달했습니다. "
                f"운행일 {self._today(now)} 기준. 자동 호출을 중단합니다."
            )

    def consume(self, pool: Pool, now: datetime | None = None) -> int:
        """호출 1회를 기록하고 그날의 누적 순번을 반환한다.

        호출 **직전에** 부른다. 응답을 받은 뒤 기록하면 프로세스가 중간에
        죽었을 때 실제로 소모한 호출이 원장에 남지 않는다.
        """
        self.check(pool, now)
        svc = self._today(now)
        bucket = self._bucket(svc)
        seq = int(bucket.get(pool.counter_key, 0)) + 1
        bucket[pool.counter_key] = seq
        self._prune(svc)
        self._save()
        return seq

    def _prune(self, keep: str, days: int = 14) -> None:
        """오래된 운행일 버킷을 정리한다. 원장이 무한히 커지지 않게 한다."""
        if len(self._state) <= days:
            return
        for stale in sorted(self._state)[:-days]:
            if stale != keep:
                self._state.pop(stale, None)

    def snapshot(self, now: datetime | None = None) -> dict[str, int]:
        """오늘 운행일의 풀별 사용량."""
        return dict(self._bucket(self._today(now)))


def backoff_delay(attempt: int, base: float = 1.0, cap: float = 30.0) -> float:
    """지수 백오프 + 지터. attempt는 1부터 센다.

    지터를 넣는 이유는 여러 수집기가 동시에 실패했을 때 같은 시각에 재시도가
    몰리는 것을 막기 위해서다.
    """
    delay = min(cap, base * (2 ** (attempt - 1)))
    return delay * (0.5 + random.random() * 0.5)


def sleep_backoff(attempt: int, base: float = 1.0, cap: float = 30.0) -> float:
    delay = backoff_delay(attempt, base, cap)
    time.sleep(delay)
    return delay
