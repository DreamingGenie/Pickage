"""수집기 골격 스모크 테스트 (Jira 94 완료 판단용).

실제 인증키 없이 공개 `sample` 키로 전 경로를 검증한다.

    python -m collector.smoke_test

확인하는 것:
  1. 정상 경로 — HTTP 200 + INFO-000이 outcome=OK로 저장되는가
  2. 업무 오류 경로 — HTTP 200 + ERROR-336이 outcome=BUSINESS_ERROR로 구분되는가
  3. 전송 실패 경로 — 응답이 없어도 Bronze에 기록이 남는가
  4. 타임스탬프 — requested_at과 received_at이 실제 왕복 시간만큼 벌어지는가
  5. 마스킹 — 저장된 request_url에 인증키가 남지 않는가
  6. 파티션 — 운행일 경계가 올바르게 적용되는가
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime
from pathlib import Path

from .common import service_day, storage
from .common.storage import BUSINESS_ERROR, OK, TRANSPORT_ERROR
from .sources import seoul_subway

SAMPLE_KEY = "sample"


def _check(label: str, passed: bool, detail: str = "") -> bool:
    mark = "PASS" if passed else "FAIL"
    print(f"  [{mark}] {label}" + (f" — {detail}" if detail else ""))
    return passed


def run(bronze_dir: Path) -> bool:
    results: list[bool] = []

    print("\n1. 정상 경로 — 일괄 도착 (OA-15799)")
    r = seoul_subway.arrival_all(SAMPLE_KEY)
    meta_path = storage.record(r, bronze_dir)
    results.append(_check("outcome=OK", r.outcome == OK, f"outcome={r.outcome}, code={r.business_code}"))
    results.append(_check("행 수 기록됨", bool(r.row_count), f"row_count={r.row_count}"))
    results.append(_check("원문 파일 분리 저장", meta_path.with_suffix("").with_suffix(".json").exists()
                          or any(meta_path.parent.glob("*.json")), f"dir={meta_path.parent.name}"))

    meta = storage.load_meta(meta_path)
    results.append(_check("payload_bytes 기록", bool(meta["payload_bytes"]), f"{meta['payload_bytes']:,} bytes"))
    results.append(_check("sha256 기록", bool(meta["payload_sha256"]), meta["payload_sha256"][:16] + "..."))

    print("\n2. 업무 오류 경로 — 역별 조회 범위 초과 (ERROR-336 유도)")
    r2 = seoul_subway.arrival_station(SAMPLE_KEY, "서울", start=0, end=20)
    storage.record(r2, bronze_dir)
    results.append(_check(
        "HTTP 200인데 outcome=BUSINESS_ERROR",
        r2.http_status == 200 and r2.outcome == BUSINESS_ERROR,
        f"http={r2.http_status}, outcome={r2.outcome}, code={r2.business_code}",
    ))
    results.append(_check(
        "오류 envelope에서도 업무코드 추출",
        r2.business_code == "ERROR-336",
        f"code={r2.business_code}",
    ))

    print("\n3. 정상 경로 — 역별 조회 허용 범위 (0/5)")
    r3 = seoul_subway.arrival_station(SAMPLE_KEY, "서울", start=0, end=5)
    storage.record(r3, bronze_dir)
    results.append(_check("outcome=OK", r3.outcome == OK, f"code={r3.business_code}, rows={r3.row_count}"))

    print("\n4. 전송 실패 경로 — 존재하지 않는 호스트")
    from .common.http_client import fetch
    r4 = fetch(
        source_key="smoke_unreachable",
        provider="test",
        endpoint="none",
        url="http://invalid.localhost.test/none",
        timeout=3,
    )
    p4 = storage.record(r4, bronze_dir)
    results.append(_check("outcome=TRANSPORT_ERROR", r4.outcome == TRANSPORT_ERROR, f"{r4.error_code}"))
    results.append(_check("응답 없어도 Bronze 기록 남음", p4.exists()))

    print("\n5. 타임스탬프 분리")
    results.append(_check(
        "requested_at != received_at",
        r.requested_at != r.received_at and r.latency_ms > 0,
        f"latency={r.latency_ms:.1f}ms",
    ))

    print("\n6. 인증키 마스킹")
    real_key_url = seoul_subway.arrival_all("MY-SECRET-KEY-1234")
    results.append(_check(
        "URL에 키가 남지 않음",
        "MY-SECRET-KEY-1234" not in real_key_url.request_url_masked,
        real_key_url.request_url_masked[:70] + "...",
    ))

    print("\n7. 운행일 경계 (04:00 KST)")
    cases = [
        ("2026-08-26T01:30:00+09:00", "2026-08-25", "새벽 1시 30분 → 전날"),
        ("2026-08-26T03:59:00+09:00", "2026-08-25", "경계 직전 → 전날"),
        ("2026-08-26T04:00:00+09:00", "2026-08-26", "경계 정각 → 당일"),
        ("2026-08-26T23:00:00+09:00", "2026-08-26", "밤 11시 → 당일"),
        ("2026-08-25T19:00:00+00:00", "2026-08-26", "UTC 입력도 KST 기준 판정"),
    ]
    for iso, expected, label in cases:
        got = service_day.service_date(datetime.fromisoformat(iso))
        results.append(_check(label, got == expected, f"{iso} → {got}"))

    print("\n8. 24시 이상 표기 분해")
    for value, expected in [("25:10:00", (1, 1, 10, 0)), ("23:59:00", (0, 23, 59, 0)), ("24:00", (1, 0, 0, 0))]:
        got = service_day.parse_hhmm_over24(value)
        results.append(_check(f"{value} → {got}", got == expected))

    passed, total = sum(results), len(results)
    print(f"\n{'=' * 56}\n결과: {passed}/{total} 통과\n{'=' * 56}")
    return passed == total


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        ok = run(Path(tmp))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
