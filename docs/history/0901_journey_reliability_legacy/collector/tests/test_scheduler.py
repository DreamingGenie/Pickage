"""스케줄러 로직 검증. 네트워크 호출도 quota 소모도 없다.

어댑터 함수를 가짜로 바꿔 아래 5가지를 확인한다.
  1. 정상 경로 — Bronze에 원문·메타가 기록되고 집계가 맞는다
  2. 재시도 무의미 업무오류 연속 발생 시 당일 중단
  3. quota 상한 도달 시 호출 건너뛰기
  4. retry_reserve 이하로 떨어지면 재시도 1회로 축소
  5. 지나간 슬롯을 몰아서 호출하지 않음
"""
from __future__ import annotations

import io
import logging
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, r"C:\git\S15P21A506")

from collector.common import storage
from collector.common.quota import QuotaLedger
from collector.common.scheduler import Scheduler
from collector.common.storage import BUSINESS_ERROR, OK, CollectionResult
from collector.common.targets import Settings, Target
from collector.sources.registry import SourceSpec

out = io.TextIOWrapper(open(1, "wb", closefd=False), encoding="utf-8", errors="replace")
logging.basicConfig(level=logging.WARNING, stream=out, format="    LOG %(levelname)s %(message)s")

PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{('  — ' + detail) if detail else ''}", file=out)


# ── 가짜 어댑터 ────────────────────────────────────────────────────────
calls: list[dict] = []


def make_fn(outcome: str, code: str, *, rows: int = 3, payload: bytes = b"<r/>"):
    def fn(key, quota_seq_today=None, fmt="xml", **params):
        calls.append({"key": key, "seq": quota_seq_today, "fmt": fmt, **params})
        now = storage.now_iso()
        return CollectionResult(
            source_key="fake",
            provider="test",
            endpoint="fake",
            requested_at=now,
            received_at=storage.now_iso(),
            request_url_masked="http://example.test/***",
            http_status=200,
            payload=payload,
            payload_ext="xml",
            business_code=code,
            row_count=rows,
            outcome=outcome,
            error_code=None if outcome == OK else code,
            error_body=None if outcome == OK else "가짜 오류",
            quota_seq_today=quota_seq_today,
        )

    return fn


def spec_for(fn, *, retryable: bool) -> SourceSpec:
    return SourceSpec(
        name="fake-source",
        key_env="FAKE_KEY",
        pool_name="fake_pool",
        fn=fn,
        business_check=lambda code: retryable,
        default_fmt="xml",
        required_params=("route",),
    )


def target_for(spec: SourceSpec, *, interval=120, attempts=2, cap=950) -> Target:
    return Target(
        name="fake_target",
        spec=spec,
        interval_seconds=interval,
        params={"route": "R1"},
        enabled=True,
        max_attempts=attempts,
        hard_cap=cap,
    )


def settings_for(target: Target, **kw) -> Settings:
    base = dict(
        retry_reserve=0,
        stagger_seconds=0.0,
        heartbeat_seconds=9999.0,
        stall_factor=3.0,
        permanent_error_limit=3, default_hard_cap=target.hard_cap, key_caps={},
        targets=(target,),
    )
    base.update(kw)
    return Settings(**base)


def new_scheduler(target, settings, tmp: Path, *, dry_run=False) -> Scheduler:
    storage.BRONZE_DIR = tmp / "bronze"
    ledger = QuotaLedger(path=tmp / "ledger.json")
    return Scheduler(
        settings=settings, ledger=ledger, keys={"FAKE_KEY": ["k"]}, dry_run=dry_run
    )


# ── 1. 정상 경로 ───────────────────────────────────────────────────────
print("\n1. 정상 경로 — Bronze 기록과 집계", file=out)
with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    calls.clear()
    spec = spec_for(make_fn(OK, "0"), retryable=False)
    tgt = target_for(spec)
    sch = new_scheduler(tgt, settings_for(tgt), tmp)
    st = sch.states[0]
    sch._run_target(st)

    check("어댑터가 1회 호출됨", len(calls) == 1, f"calls={len(calls)}")
    check("params가 전달됨", calls and calls[0].get("route") == "R1", str(calls[:1]))
    check("quota_seq_today가 주입됨", calls and calls[0]["seq"] == 1, str(calls[:1]))
    check("집계 ok=1", st.ok == 1 and st.calls == 1, f"ok={st.ok} calls={st.calls}")
    check("행/바이트 누적", st.rows == 3 and st.payload_bytes == 4, f"rows={st.rows} bytes={st.payload_bytes}")
    written = list((tmp / "bronze").rglob("*.meta.json"))
    check("Bronze에 메타 기록", len(written) == 1, f"files={len(written)}")
    check("원장에 1회 기록", sch.ledger.used(st.keypools[0][1]) == 1, str(sch.ledger.snapshot()))

# ── 2. 재시도 무의미 오류 연속 → 당일 중단 ─────────────────────────────
print("\n2. 재시도 무의미 업무오류 3회 연속 → 당일 중단", file=out)
with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    calls.clear()
    spec = spec_for(make_fn(BUSINESS_ERROR, "ERROR-340", rows=0), retryable=False)
    tgt = target_for(spec, attempts=1)
    sch = new_scheduler(tgt, settings_for(tgt, permanent_error_limit=3), tmp)
    st = sch.states[0]
    for _ in range(5):
        sch._run_target(st)

    check("3회에서 중단됨", st.disabled_reason is not None, str(st.disabled_reason))
    check("중단 후 추가 호출 없음", len(calls) == 3, f"calls={len(calls)} (기대 3)")
    check("quota도 3회만 소모", sch.ledger.used(st.keypools[0][1]) == 3, str(sch.ledger.snapshot()))
    st.reset_day()
    check("운행일 전환 시 중단 해제", st.disabled_reason is None)

# ── 3. quota 상한 도달 → 건너뛰기 ──────────────────────────────────────
print("\n3. quota 상한 도달 → 호출 건너뛰기", file=out)
with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    calls.clear()
    spec = spec_for(make_fn(OK, "0"), retryable=False)
    tgt = target_for(spec, attempts=1, cap=2)
    sch = new_scheduler(tgt, settings_for(tgt), tmp)
    st = sch.states[0]
    for _ in range(5):
        sch._run_target(st)

    check("상한 2회에서 멈춤", len(calls) == 2, f"calls={len(calls)} (기대 2)")
    check("원장이 상한을 넘지 않음", sch.ledger.used(st.keypools[0][1]) == 2, str(sch.ledger.snapshot()))

# ── 4. retry_reserve → 재시도 축소 ─────────────────────────────────────
print("\n4. 잔여가 retry_reserve 이하 → 재시도 1회로 축소", file=out)
with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    # 재시도 가치가 있는 오류로 두고, 예비분에 걸리면 시도가 1회로 줄어야 한다.
    calls.clear()
    spec = spec_for(make_fn(BUSINESS_ERROR, "1", rows=0), retryable=True)
    tgt = target_for(spec, attempts=3, cap=10)
    sch = new_scheduler(tgt, settings_for(tgt, retry_reserve=0), tmp)
    st = sch.states[0]
    sch._run_target(st)
    check("예비분 밖에서는 3회 시도", len(calls) == 3, f"calls={len(calls)} (기대 3)")

    calls.clear()
    sch2 = new_scheduler(tgt, settings_for(tgt, retry_reserve=8), tmp)
    st2 = sch2.states[0]
    sch2._run_target(st2)
    check("예비분 이내에서는 1회 시도", len(calls) == 1, f"calls={len(calls)} (기대 1)")

# ── 5. 지나간 슬롯 폐기 ────────────────────────────────────────────────
print("\n5. 지나간 슬롯을 몰아서 호출하지 않음", file=out)
with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    spec = spec_for(make_fn(OK, "0"), retryable=False)
    tgt = target_for(spec, interval=300)
    sch = new_scheduler(tgt, settings_for(tgt), tmp)
    st = sch.states[0]

    fake_now = [1000.0]
    sch.clock = lambda: fake_now[0]

    # 정상: due 1000, 지금 1000 → 다음은 1300
    check("정상 진행", sch._advance(1000.0, st) == 1300.0)

    # 절전 25분(1500초) 후 복귀: 슬롯 5개를 건너뛰고 미래 시각으로 점프해야 한다
    fake_now[0] = 2500.0
    nxt = sch._advance(1000.0, st)
    check("절전 복귀 시 미래로 점프", nxt > 2500.0, f"next={nxt}")
    check("정확히 다음 슬롯", nxt == 2800.0, f"next={nxt} (기대 2800)")

print("\n" + "=" * 60, file=out)
print(f"통과 {len(PASS)}건 / 실패 {len(FAIL)}건", file=out)
if FAIL:
    print("실패: " + ", ".join(FAIL), file=out)
out.flush()
sys.exit(1 if FAIL else 0)
