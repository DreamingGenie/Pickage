"""key_id 기록과 원장 손상 복구 검증. 네트워크 호출 없음."""
from __future__ import annotations

import io
import json
import logging
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, r"C:\git\S15P21A506")

from collector.common import service_day, storage
from collector.common.quota import (
    LedgerCorrupted,
    Pool,
    QuotaLedger,
    counts_from_bronze,
    key_id,
)
from collector.common.storage import OK, CollectionResult

out = io.TextIOWrapper(open(1, "wb", closefd=False), encoding="utf-8", errors="replace")
logging.basicConfig(level=logging.WARNING, stream=out, format="    LOG %(levelname)s %(message)s")

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{('  -> ' + detail) if detail else ''}", file=out)


TODAY = service_day.service_date(datetime.now(timezone.utc))


def write_record(bronze: Path, *, pool_name, kid, seq, source="subway_position"):
    now = storage.now_iso()
    r = CollectionResult(
        source_key=source, provider="test", endpoint="e",
        requested_at=now, received_at=storage.now_iso(),
        request_url_masked="http://x/***", http_status=200,
        payload=b"x", payload_ext="json", business_code="INFO-000",
        row_count=1, outcome=OK, quota_seq_today=seq,
        key_id=kid, quota_pool=pool_name,
    )
    return storage.record(r, bronze_dir=bronze)


# ── 1. 메타에 key_id / quota_pool이 기록되는가 ─────────────────────────
print("\n1. 메타 필드 기록", file=out)
with tempfile.TemporaryDirectory() as td:
    bronze = Path(td) / "bronze"
    meta_path = write_record(bronze, pool_name="seoul_subway_realtime", kid="abc12345", seq=7)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    check("key_id 기록", meta.get("key_id") == "abc12345", str(meta.get("key_id")))
    check("quota_pool 기록", meta.get("quota_pool") == "seoul_subway_realtime", str(meta.get("quota_pool")))
    check("collector_version 상향", meta.get("collector_version") == "bronze-v3", str(meta.get("collector_version")))

# ── 2. 샘플키가 메타에서 구분되는가 ────────────────────────────────────
print("\n2. 샘플키 판별 (URL 휴리스틱 없이)", file=out)
check("실키는 8자리 해시", len(key_id("real-secret-value")) == 8, key_id("real-secret-value"))
check("샘플키는 sample", key_id("sample") == "sample")
check("키 없으면 none", key_id(None) == "none")
check("키가 다르면 id도 다름", key_id("A") != key_id("B"))

# ── 3. Bronze에서 카운터 재구성 ────────────────────────────────────────
print("\n3. Bronze -> 카운터 재구성", file=out)
with tempfile.TemporaryDirectory() as td:
    bronze = Path(td) / "bronze"
    P = "seoul_subway_realtime"
    for seq in (1, 2, 3):
        write_record(bronze, pool_name=P, kid="k1", seq=seq)
    write_record(bronze, pool_name="data_go_bus::getBusPosByRouteSt", kid="k2", seq=1)
    counts = counts_from_bronze(TODAY, bronze)
    check("풀별로 집계", set(counts) == {f"{P}::k1", "data_go_bus::getBusPosByRouteSt::k2"}, str(counts))
    check("기록 수만큼 복원", counts.get(f"{P}::k1") == 3, str(counts))

    # 재시도 보정: 3회 시도(seq 1,2,3) 중 마지막 결과만 저장된 상황
    bronze2 = Path(td) / "bronze2"
    write_record(bronze2, pool_name=P, kid="k1", seq=3)
    c2 = counts_from_bronze(TODAY, bronze2)
    check("재시도분을 seq 최댓값으로 보정", c2.get(f"{P}::k1") == 3, f"{c2} (기록 1건인데 3으로 복원)")

    # bronze-v1 기록(필드 없음)은 세지 않는다
    bronze3 = Path(td) / "bronze3"
    write_record(bronze3, pool_name=None, kid=None, seq=5)
    check("v1 기록은 복원 근거로 쓰지 않음", counts_from_bronze(TODAY, bronze3) == {}, str(counts_from_bronze(TODAY, bronze3)))

# ── 4. 원장 손상 -> 조용한 리셋 금지 ───────────────────────────────────
print("\n4. 원장 손상 처리", file=out)
with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    bronze = tmp / "bronze"
    P = "seoul_subway_realtime"
    for seq in (1, 2, 3, 4, 5):
        write_record(bronze, pool_name=P, kid="k1", seq=seq)

    # 4-a. 깨진 원장 + Bronze 있음 -> 복구 + 깨진 파일 보존
    led_path = tmp / "ledger.json"
    led_path.write_text("{ 이건 JSON이 아니다", encoding="utf-8")
    led = QuotaLedger(path=led_path, bronze_dir=bronze)
    pool = Pool(P, "k1")
    check("손상 원장을 0으로 리셋하지 않음", led.used(pool) == 5, f"used={led.used(pool)} (기대 5)")
    corrupt = list(tmp.glob("ledger.json.corrupt.*"))
    check("깨진 파일을 보존", len(corrupt) == 1, str([p.name for p in corrupt]))
    check("원문 내용이 그대로 남음", corrupt and "이건 JSON이 아니다" in corrupt[0].read_text(encoding="utf-8"))

    # 4-b. 깨진 원장 + Bronze 없음 -> 기동 중단
    led2_path = tmp / "ledger2.json"
    led2_path.write_text("!!!", encoding="utf-8")
    try:
        QuotaLedger(path=led2_path, bronze_dir=tmp / "empty")
        check("복구 불가 시 예외", False, "예외가 나지 않음")
    except LedgerCorrupted as exc:
        check("복구 불가 시 LedgerCorrupted", True, str(exc)[:70] + "...")

    # 4-c. 원장 파일 없음 + Bronze 있음 -> 유실로 보고 복구
    led3 = QuotaLedger(path=tmp / "absent.json", bronze_dir=bronze)
    check("원장 유실 시 Bronze로 복구", led3.used(pool) == 5, f"used={led3.used(pool)}")

    # 4-d. 원장 파일 없음 + Bronze 없음 -> 첫 실행, 예외 없음
    led4 = QuotaLedger(path=tmp / "absent2.json", bronze_dir=tmp / "empty")
    check("첫 실행은 조용히 0", led4.used(pool) == 0)

# ── 5. 복구 후 정상 동작 ───────────────────────────────────────────────
print("\n5. 복구된 원장이 상한을 지키는가", file=out)
with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    bronze = tmp / "bronze"
    P = "seoul_subway_realtime"
    for seq in range(1, 949):
        write_record(bronze, pool_name=P, kid="k1", seq=seq)
    led_path = tmp / "ledger.json"
    led_path.write_text("broken", encoding="utf-8")
    led = QuotaLedger(path=led_path, bronze_dir=bronze)
    pool = Pool(P, "k1", hard_cap=950)
    check("복구된 사용량 948", led.used(pool) == 948, f"used={led.used(pool)}")
    led.consume(pool); led.consume(pool)
    try:
        led.consume(pool)
        check("복구 후에도 상한 950에서 차단", False, "차단되지 않음")
    except Exception as exc:
        check("복구 후에도 상한 950에서 차단", type(exc).__name__ == "QuotaExceeded", type(exc).__name__)

print("\n" + "=" * 60, file=out)
print(f"통과 {len(PASS)}건 / 실패 {len(FAIL)}건", file=out)
if FAIL:
    print("실패: " + ", ".join(FAIL), file=out)
out.flush()
sys.exit(1 if FAIL else 0)
