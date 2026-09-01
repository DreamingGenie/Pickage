"""실시간 수집 스케줄러 (Jira 98).

**단일 프로세스 단일 스레드**로 모든 대상을 자기 주기에 맞춰 호출한다.
멀티프로세스로 나누지 않은 이유가 설계의 핵심이다.

  quota 원장(`data/quota_ledger.json`)은 파일이고 파일 락이 없다. 대상마다
  프로세스를 띄우면 `consume()`이 서로 덮어써서 당일 카운터가 실제보다 작게
  집계된다. 그러면 상한 950을 넘겨 호출하고 provider가 그날 수집을 막는다.
  한 프로세스 안에서 순차 호출하면 이 경쟁이 아예 발생하지 않는다.

멀티스레드도 쓰지 않는다. 대상이 5개 내외이고 주기가 120~300초인데 호출 1회는
수십~수백 ms다. 동시성으로 얻을 게 없고 원장 경쟁만 생긴다.

운영 원칙 네 가지.

  1. **지나간 슬롯은 따라잡지 않는다.** 노트북 절전·프로세스 중단으로 슬롯을
     놓치면 그만큼을 몰아서 호출하지 않고 버린다. 실시간 데이터는 지난 시점을
     받을 수 없어 따라잡기가 무의미하고, quota만 태운다.
  2. **한 대상의 예외가 전체를 멈추지 않는다.** 호출·기록 예외를 대상 단위로
     잡고 로그만 남기고 계속 돈다.
  3. **재시도 무의미 오류가 반복되면 그 대상을 당일 중단한다.** OA-15799가
     ERROR-340을 반환하는데 180초마다 호출하면 181바이트 오류를 받으며 하루
     480회를 태운다.
  4. **잔여 예산이 얇아지면 재시도부터 끊는다.** 수동 검증용 호출을 남긴다.
"""
from __future__ import annotations

import heapq
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..sources import registry
from . import runner, service_day, storage
from .quota import Pool, QuotaExceeded, QuotaLedger
from .storage import BUSINESS_ERROR, HTTP_ERROR, OK, TRANSPORT_ERROR
from .targets import Settings, Target, budget_report

log = logging.getLogger("collector.scheduler")

# 대기 중에도 정지 신호와 운행일 전환을 이 간격으로 확인한다.
_MAX_TICK_SECONDS = 5.0
# 완전한 바쁜 대기를 막는 최소 sleep.
_MIN_TICK_SECONDS = 0.05


@dataclass
class TargetState:
    """대상 1건의 실행 상태와 당일 집계."""

    target: Target
    # key rotation: (인증키, 그 키의 quota 풀) 쌍의 목록. 앞에서부터 잔여가
    # 남은 키를 골라 쓴다. 한 키가 소진되면 다음 팀원 키로 자동으로 넘어간다.
    keypools: list[tuple[str, Pool]]
    next_due: float = 0.0
    last_ok_at: float | None = None
    consecutive_permanent: int = 0
    disabled_reason: str | None = None
    stall_warned: bool = False
    quota_warned: bool = False
    retry_off_warned: bool = False

    calls: int = 0
    ok: int = 0
    business_error: int = 0
    http_error: int = 0
    transport_error: int = 0
    exceptions: int = 0
    rows: int = 0
    payload_bytes: int = 0

    def reset_day(self) -> None:
        """운행일이 바뀌면 당일 집계와 당일 한정 중단을 초기화한다."""
        self.consecutive_permanent = 0
        self.disabled_reason = None
        self.stall_warned = False
        self.quota_warned = False
        self.retry_off_warned = False
        self.calls = self.ok = self.business_error = 0
        self.http_error = self.transport_error = self.exceptions = 0
        self.rows = self.payload_bytes = 0


@dataclass
class Scheduler:
    settings: Settings
    ledger: QuotaLedger
    # key_env → 인증키 목록. 목록이 2개 이상이면 key rotation이 작동한다.
    keys: dict[str, list[str]]
    dry_run: bool = False
    stop: threading.Event = field(default_factory=threading.Event)
    clock: object = time.monotonic

    def __post_init__(self) -> None:
        self.states: list[TargetState] = []
        self.started_at = self.clock()
        self.service_date = _today()
        self._skipped_no_key: list[str] = []

        for target in self.settings.enabled():
            env = target.spec.key_env
            keys = self.keys.get(env) or []
            if not keys:
                # 키가 없는 대상만 건너뛴다. 버스 키가 없어도 지하철은 돌아야 한다.
                self._skipped_no_key.append(f"{target.name}({env})")
                continue
            # 키별 hard_cap(운영/개발 혼용). key_caps 미지정이면 default_hard_cap.
            caps = self.settings.caps_for(env, len(keys))
            keypools = [
                (k, registry.make_pool(target.spec, k, cap))
                for k, cap in zip(keys, caps)
            ]
            self.states.append(TargetState(target=target, keypools=keypools))

    # ── 기동 ──────────────────────────────────────────────────────────
    def log_plan(self) -> None:
        """기동 시 수집 계획과 예산을 로그로 남긴다."""
        log.info("운행일 %s 기준으로 시작합니다. 대상 %d건.", self.service_date, len(self.states))
        for state in self.states:
            t = state.target
            log.info(
                "  %-28s %-22s %4d초 (%.0f회/일) params=%s",
                t.name,
                t.spec.name,
                t.interval_seconds,
                t.calls_per_day,
                t.params or "{}",
            )
        if self._skipped_no_key:
            log.warning("키가 없어 건너뛴 대상: %s", ", ".join(self._skipped_no_key))

        key_counts = {env: len(keys) for env, keys in self.keys.items()}
        for env, n in sorted(key_counts.items()):
            if n > 1:
                log.info("key rotation: %s 키 %d개 → 하루 예산 %d배", env, n, n)

        for pool_name, calls, cap, over in budget_report(self.settings, key_counts):
            used = self._pool_used(pool_name)
            level = log.warning if over else log.info
            level(
                "예산 %-34s %.0f회/일 / 유효상한 %d (당일 사용 %d)%s",
                pool_name,
                calls,
                cap,
                used,
                self._oversub_note(calls, cap) if over else "",
            )
        if self.dry_run:
            log.warning("dry-run: 호출은 하되 Bronze에 기록하지 않습니다(quota는 소모됩니다).")

    def _oversub_note(self, calls: float, cap: int) -> str:
        """유효상한을 넘긴 풀의 예상 소진 시각을 계산해 안내한다.

        폴링은 하루 종일 같은 주기로 돌므로, calls/day가 상한보다 크면 운행일
        시작(기본 04:00 KST)으로부터 `cap/calls × 24h` 뒤에 소진된다. 이건
        설정 오류가 아니라 **의도된 오버구독**일 수 있다(늦은 밤 저운행 구간을
        일부 포기하고 낮 관측을 촘촘히 하는 선택). 그래서 줄이라고 강요하지
        않고 예상 소진 시각만 알린다.

        실제 소진은 재시도·전송실패가 quota를 먹어 이보다 앞당겨질 수 있다.
        각 키가 상한에 가까워지면 retry_reserve가 재시도를 끊어 오버슈트를
        제한하지만, 특정 키가 자주 실패하면 그만큼 일찍 바닥난다.
        """
        if calls <= 0:
            return "  ** 초과 **"
        hours = cap / calls * 24.0
        start = service_day.SERVICE_DAY_BOUNDARY_HOUR
        minute = int((start * 60 + hours * 60) % (24 * 60))
        clock = f"{minute // 60:02d}:{minute % 60:02d}"
        return f"  ** 유효상한 초과(오버구독) — 예상 소진 ~{clock} KST, 이후 다음 운행일까지 그 풀은 건너뜀 **"

    def _pool_used(self, pool_name: str) -> int:
        return sum(
            count
            for key, count in self.ledger.snapshot().items()
            if key.startswith(f"{pool_name}::")
        )

    # ── 실행 ──────────────────────────────────────────────────────────
    def run_once(self) -> int:
        """활성 대상을 순서대로 1회씩 호출한다. 설정·키 검증용이다."""
        self.log_plan()
        for state in self.states:
            self._run_target(state)
        self._emit_summary("1회 실행 완료")
        return 0 if all(s.ok for s in self.states) else 1

    def run(self) -> int:
        """정지 신호가 올 때까지 상시 수집한다."""
        self.log_plan()
        if not self.states:
            log.error("실행할 대상이 없습니다. targets.toml과 .env.local을 확인하세요.")
            return 2

        heap: list[tuple[float, int]] = []
        now = self.clock()
        for index, state in enumerate(self.states):
            # 기동 직후 동시 호출을 피해 대상별로 시작 시각을 흩뿌린다.
            state.next_due = now + index * self.settings.stagger_seconds
            heapq.heappush(heap, (state.next_due, index))

        next_heartbeat = now + self.settings.heartbeat_seconds

        while not self.stop.is_set():
            self._roll_service_date()

            now = self.clock()
            if now >= next_heartbeat:
                self._heartbeat()
                next_heartbeat = now + self.settings.heartbeat_seconds

            due, index = heap[0]
            wait = due - now
            if wait > 0:
                tick = min(wait, next_heartbeat - now, _MAX_TICK_SECONDS)
                if self.stop.wait(max(tick, _MIN_TICK_SECONDS)):
                    break
                continue

            heapq.heappop(heap)
            state = self.states[index]
            self._run_target(state)
            state.next_due = self._advance(due, state)
            heapq.heappush(heap, (state.next_due, index))

        self._emit_summary("정지 신호를 받아 종료합니다")
        return 0

    def _advance(self, due: float, state: TargetState) -> float:
        """다음 실행 시각을 계산한다. 지나간 슬롯은 버린다."""
        interval = state.target.interval_seconds
        nxt = due + interval
        now = self.clock()
        if nxt > now:
            return nxt
        missed = int((now - nxt) // interval) + 1
        log.warning(
            "%s: 슬롯 %d개를 건너뜁니다(절전·중단 또는 호출 지연). "
            "실시간 데이터는 따라잡기가 불가능하므로 몰아서 호출하지 않습니다.",
            state.target.name,
            missed,
        )
        return nxt + missed * interval

    def _active_keypool(self, state: TargetState) -> tuple[str, Pool, int] | None:
        """잔여가 남은 첫 (키, 풀)과 그 잔여를 고른다. 전부 소진이면 None.

        앞 키부터 소진하고 다음 키로 넘어가는 방식이라, 팀원 키가 있어도 내 키를
        먼저 다 쓴다. 이게 의도다 — 어느 키가 얼마나 쓰였는지 원장에서 명확하고,
        키 소유자별 사용량을 나중에 정산·설명하기 쉽다.
        """
        for key, pool in state.keypools:
            remaining = self.ledger.remaining(pool)
            if remaining > 0:
                return key, pool, remaining
        return None

    def _run_target(self, state: TargetState) -> None:
        target = state.target
        if state.disabled_reason:
            return

        picked = self._active_keypool(state)
        if picked is None:
            if not state.quota_warned:
                pools = ", ".join(p.counter_key for _, p in state.keypools)
                log.warning(
                    "%s: 모든 키의 일일 상한 도달(%s). 운행일이 바뀔 때까지 건너뜁니다.",
                    target.name,
                    pools,
                )
                state.quota_warned = True
            return
        key, pool, remaining = picked

        attempts = target.max_attempts
        if remaining <= self.settings.retry_reserve:
            attempts = 1
            if target.max_attempts > 1 and not state.retry_off_warned:
                log.warning(
                    "%s: 현재 키 잔여 %d회가 예비분 %d회 이하입니다. 재시도를 중단하고 1회만 시도합니다.",
                    target.name,
                    remaining,
                    self.settings.retry_reserve,
                )
                state.retry_off_warned = True

        try:
            result = runner.collect(
                target.spec.fn,
                key,
                ledger=self.ledger,
                pool=pool,
                business_check=target.spec.business_check,
                max_attempts=attempts,
                **target.call_kwargs(),
            )
        except QuotaExceeded as exc:
            log.warning("%s: %s", target.name, exc)
            state.quota_warned = True
            return
        except Exception:
            # 어댑터·네트워크 계층의 예상 못한 예외로 수집 전체가 멈추면 안 된다.
            state.calls += 1
            state.exceptions += 1
            log.exception("%s: 수집 중 예외가 발생했습니다.", target.name)
            return

        # provider가 "요청제한 초과"(HTTP 401)를 반환하면 이 키는 오늘 소진된 것이다.
        # 우리 원장은 예산이 남았다고 볼 수 있으나(리셋 경계 불일치), provider 신호를
        # 믿고 이 키의 풀을 소진 처리해 rotation이 다음 키로 넘어가게 한다. 원문은
        # 아래에서 그대로 저장한다(증거 보존).
        if result.outcome == HTTP_ERROR and result.http_status == 401:
            self.ledger.exhaust(pool)
            if not state.quota_warned:
                log.warning(
                    "%s: 키 %s 요청제한 초과(HTTP 401). 이 키를 당일 소진 처리하고 다음 키로 넘어갑니다. "
                    "(provider 리셋 경계가 운행일 04:00과 다를 수 있음)",
                    target.name,
                    pool.counter_key,
                )

        state.calls += 1
        state.rows += result.row_count or 0
        state.payload_bytes += len(result.payload or b"")

        if not self.dry_run:
            try:
                storage.record(result)
            except OSError:
                # 디스크가 차거나 권한이 없어도 프로세스는 살아 있어야 한다.
                log.exception("%s: Bronze 기록에 실패했습니다.", target.name)

        self._account(state, result)

    def _account(self, state: TargetState, result) -> None:
        target = state.target
        if result.outcome == OK:
            state.ok += 1
            state.last_ok_at = self.clock()
            state.consecutive_permanent = 0
            state.stall_warned = False
            log.info(
                "%-28s OK   code=%-9s rows=%-5s %7d bytes %6.0f ms",
                target.name,
                result.business_code,
                result.row_count,
                len(result.payload or b""),
                result.latency_ms,
            )
            return

        if result.outcome == BUSINESS_ERROR:
            state.business_error += 1
            retryable = target.spec.business_check(result.business_code)
            log.warning(
                "%-28s 업무오류 code=%s retryable=%s msg=%s",
                target.name,
                result.business_code,
                retryable,
                (result.error_body or "")[:120],
            )
            if not retryable:
                state.consecutive_permanent += 1
                if state.consecutive_permanent >= self.settings.permanent_error_limit:
                    state.disabled_reason = (
                        f"재시도 무의미 업무오류 {result.business_code} "
                        f"{state.consecutive_permanent}회 연속"
                    )
                    log.error(
                        "%s: %s. 당일 수집을 중단합니다. "
                        "설정이나 인증키 권한을 확인하고 targets.toml에서 enabled를 조정하세요.",
                        target.name,
                        state.disabled_reason,
                    )
            return

        if result.outcome == HTTP_ERROR:
            state.http_error += 1
            log.warning(
                "%-28s HTTP오류 status=%s %s",
                target.name,
                result.http_status,
                result.error_body or "",
            )
            return

        if result.outcome == TRANSPORT_ERROR:
            state.transport_error += 1
            log.warning(
                "%-28s 전송실패 %s %s",
                target.name,
                result.error_code,
                (result.error_body or "")[:160],
            )

    # ── 관측 ──────────────────────────────────────────────────────────
    def _roll_service_date(self) -> None:
        today = _today()
        if today == self.service_date:
            return
        self._emit_summary(f"운행일 {self.service_date} 마감")
        self.service_date = today
        for state in self.states:
            state.reset_day()
        log.info("운행일이 %s로 바뀌었습니다. quota 카운터와 당일 중단을 초기화합니다.", today)

    def _heartbeat(self) -> None:
        """상태 요약과 수집 중단 감지."""
        now = self.clock()
        alive = sum(1 for s in self.states if not s.disabled_reason)
        log.info(
            "상태: 대상 %d/%d 활성 · 호출 %d · 성공 %d · quota %s",
            alive,
            len(self.states),
            sum(s.calls for s in self.states),
            sum(s.ok for s in self.states),
            self.ledger.snapshot() or "{}",
        )
        for state in self.states:
            if state.disabled_reason or state.quota_warned or state.stall_warned:
                continue
            threshold = state.target.interval_seconds * self.settings.stall_factor
            since = now - (state.last_ok_at if state.last_ok_at is not None else self.started_at)
            if since > threshold:
                log.warning(
                    "%s: %.0f초 동안 성공 응답이 없습니다(주기 %d초 x %.1f 초과). 수집이 멈췄는지 확인하세요.",
                    state.target.name,
                    since,
                    state.target.interval_seconds,
                    self.settings.stall_factor,
                )
                state.stall_warned = True

    def _emit_summary(self, headline: str) -> None:
        log.info("=== %s (운행일 %s) ===", headline, self.service_date)
        log.info(
            "%-28s %6s %6s %6s %6s %6s %8s %12s",
            "대상", "호출", "성공", "업무", "HTTP", "전송", "행", "바이트",
        )
        for state in self.states:
            log.info(
                "%-28s %6d %6d %6d %6d %6d %8d %12d%s",
                state.target.name,
                state.calls,
                state.ok,
                state.business_error,
                state.http_error,
                state.transport_error,
                state.rows,
                state.payload_bytes,
                f"  [중단: {state.disabled_reason}]" if state.disabled_reason else "",
            )
        log.info("quota 사용: %s", self.ledger.snapshot() or "{}")
        disk = _bronze_bytes(self.service_date)
        if disk is not None:
            log.info("Bronze 당일 용량: %.1f MB", disk / 1024 / 1024)


def _today() -> str:
    return service_day.service_date(datetime.now(timezone.utc))


def _bronze_bytes(svc_date: str) -> int | None:
    """당일 Bronze 디렉터리 용량. 실패하면 None."""
    try:
        base: Path = storage.BRONZE_DIR
        return sum(
            p.stat().st_size
            for p in base.glob(f"**/service_date={svc_date}/*")
            if p.is_file()
        )
    except OSError:
        return None
