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
import logging
import os
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import service_day, storage

log = logging.getLogger("collector.quota")

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_LEDGER_PATH = _REPO_ROOT / "data" / "quota_ledger.json"

# provider별 기본 한도와 자동 중단 상한
DEFAULT_LIMIT = 1000
DEFAULT_HARD_CAP = 950


class QuotaExceeded(RuntimeError):
    """상한에 도달해 호출을 거부했다."""


class LedgerCorrupted(RuntimeError):
    """원장을 읽을 수 없고 Bronze로도 복구할 수 없다. 기동을 중단한다."""


def counts_from_bronze(svc_date: str, bronze_dir: Path | None = None) -> dict[str, int]:
    """당일 Bronze 메타에서 원장 카운터를 재구성한다.

    원장이 유실·손상됐을 때의 복구 경로다. 카운터 키는 메타의
    `quota_pool`과 `key_id`를 이어 만든다(`bronze-v2` 이후 기록만 가능).

    **이 값은 하한이다.** 두 가지 이유로 실제보다 작을 수 있다.

      1. 재시도한 호출은 매 시도가 quota를 소모하지만 Bronze에는 마지막
         결과만 남는다. 그래서 기록 수만 세면 재시도분이 빠진다. 이를
         메우려고 `quota_seq_today`의 최댓값도 함께 본다 — 재시도 3회의
         마지막 결과에는 seq=3이 찍혀 있으므로 3회를 복원할 수 있다.
      2. 호출은 했으나 저장에 실패한 건(디스크 오류 등)은 셀 수 없다.

    하한이라는 성질은 안전한 방향이 아니다. 실제보다 적게 세면 상한을
    넘겨 호출할 수 있다. 그래서 복구는 자동으로 조용히 하지 않고 항상
    경고를 남긴다.
    """
    base = bronze_dir or storage.BRONZE_DIR
    if not base.exists():
        return {}

    tally: dict[str, int] = {}
    highest_seq: dict[str, int] = {}
    for meta_path in base.glob(f"**/service_date={svc_date}/*.meta.json"):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        pool_name = meta.get("quota_pool")
        kid = meta.get("key_id")
        if not pool_name or not kid:
            # bronze-v1 기록이거나 runner를 경유하지 않은 호출이다.
            continue
        counter = f"{pool_name}::{kid}"
        tally[counter] = tally.get(counter, 0) + 1
        seq = meta.get("quota_seq_today")
        if isinstance(seq, int):
            highest_seq[counter] = max(highest_seq.get(counter, 0), seq)

    return {
        counter: max(count, highest_seq.get(counter, 0))
        for counter, count in tally.items()
    }


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
    # 원장이 유실·손상됐을 때 Bronze 기록으로 카운터를 되살릴지. 테스트에서 끈다.
    rebuild_from_bronze: bool = True
    bronze_dir: Path | None = None
    _state: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._load()

    # ── 파일 입출력 ────────────────────────────────────────────────
    def _load(self) -> None:
        """원장을 읽는다. **읽기에 실패했을 때 조용히 0으로 리셋하지 않는다.**

        조용한 리셋이 위험한 이유는 카운터가 0이 되면 상한을 인식하지 못해
        그날 예산을 통째로 태우기 때문이다. provider가 하루 수집을 막으면
        그 하루는 backfill이 불가능해 영구 손실이다.

        그래서 세 경우를 구분한다.

          파일 없음 + Bronze도 비어 있음   첫 실행. 빈 원장으로 시작
          파일 없음 + Bronze에 당일 기록   원장만 유실됐다. 복구하고 경고
          파일 있음 + 파싱 실패            깨진 파일을 보존하고 복구 시도.
                                          복구 불가면 기동 중단
        """
        if not self.path.exists():
            self._state = self._recover("원장 파일이 없습니다.", must_recover=False)
            return
        try:
            self._state = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            backup = self._quarantine()
            self._state = self._recover(
                f"원장 파일을 파싱할 수 없습니다({exc}). {backup.name}으로 보존했습니다.",
                must_recover=True,
            )

    def _quarantine(self) -> Path:
        """깨진 원장을 지우지 않고 옆에 보존한다. 사후 분석에 필요하다."""
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = self.path.with_name(f"{self.path.name}.corrupt.{stamp}")
        try:
            os.replace(self.path, backup)
        except OSError:
            log.exception("깨진 원장을 보존하지 못했습니다: %s", self.path)
        return backup

    def _recover(self, reason: str, *, must_recover: bool) -> dict:
        """Bronze 기록에서 당일 카운터를 되살린다."""
        if not self.rebuild_from_bronze:
            if must_recover:
                raise LedgerCorrupted(f"{reason} 자동 복구가 비활성화되어 기동을 중단합니다.")
            return {}

        svc_date = self._today()
        counts = counts_from_bronze(svc_date, self.bronze_dir)
        if counts:
            log.warning(
                "%s 당일 Bronze 기록에서 카운터를 복원했습니다: %s. "
                "이 값은 **하한**입니다 — 저장에 실패한 호출은 셀 수 없으므로 "
                "실제 사용량이 더 클 수 있습니다. 오늘은 상한에 여유를 두고 운영하세요.",
                reason,
                counts,
            )
            return {svc_date: counts}

        if must_recover:
            raise LedgerCorrupted(
                f"{reason} 당일 Bronze에도 복원할 근거가 없어 기동을 중단합니다. "
                f"카운터를 0으로 되돌리면 일일 상한을 인식하지 못해 그날 예산을 "
                f"모두 태우고, 실시간 데이터는 backfill이 불가능해 하루가 영구 "
                f"손실됩니다. 오늘 호출이 실제로 없었다면 {self.path}를 직접 "
                f"삭제하고 다시 실행하세요."
            )
        log.info("%s 새 원장으로 시작합니다.", reason)
        return {}

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

    def exhaust(self, pool: Pool, now: datetime | None = None) -> None:
        """이 풀을 당일 소진 처리한다(카운트를 상한으로 올린다).

        provider가 "요청제한 초과"(HTTP 401)를 반환하면, 우리 원장이 아직 예산이
        남았다고 보더라도 그 키는 오늘 더 쓸 수 없다. provider의 일일 리셋 경계가
        우리 운행일 경계(04:00)와 달라(예: data.go.kr은 자정) 우리가 실제보다 적게
        세는 경우가 있기 때문이다. 이 표시로 rotation이 다음 키로 넘어간다.
        운행일이 바뀌면 자연히 리셋된다.
        """
        bucket = self._bucket(self._today(now))
        bucket[pool.counter_key] = max(int(bucket.get(pool.counter_key, 0)), pool.hard_cap)
        self._save()

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
