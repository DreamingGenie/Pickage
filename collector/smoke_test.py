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

import json

from .common import service_day, storage
from .common.storage import BUSINESS_ERROR, HTTP_ERROR, OK, TRANSPORT_ERROR
from .sources import seoul_bus, seoul_subway

SAMPLE_KEY = "sample"

# 과거 스파이크가 보존한 실제 버스 응답. 키 없이 파서를 검증하는 데 쓴다.
_FIXTURE_ROOT = (
    Path(__file__).resolve().parent.parent
    / "docs" / "history" / "journey_reliability_docs_v2" / "baseline" / "phase0"
    / "data" / "samples" / "examples" / "seoul_bus"
)


def _bus_fixtures(api_name: str) -> list[bytes]:
    """보존된 샘플에서 해당 API의 원문 payload만 뽑아낸다."""
    out: list[bytes] = []
    for path in sorted(_FIXTURE_ROOT.glob(f"{api_name}/*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        raw = record.get("raw_payload")
        if raw:
            out.append(raw.encode("utf-8"))
    return out


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

    print("\n3-2. 정상 경로 — 열차 위치 (OA-12601)")
    r3b = seoul_subway.position(SAMPLE_KEY, "1호선", start=0, end=5)
    storage.record(r3b, bronze_dir)
    results.append(_check(
        "outcome=OK",
        r3b.outcome == OK,
        f"code={r3b.business_code}, rows={r3b.row_count}, {len(r3b.payload or b''):,} bytes",
    ))

    print("\n3-3. 버스 — 인증 실패 경로 (실제 키 없이 확인 가능한 범위)")
    rb = seoul_bus.position("INVALID+TEST/KEY==", "100100118", start_ord=1, end_ord=110)
    storage.record(rb, bronze_dir)
    results.append(_check(
        "무효 키 → HTTP_ERROR",
        rb.http_status == 401 and rb.outcome == HTTP_ERROR,
        f"http={rb.http_status}, outcome={rb.outcome}",
    ))
    results.append(_check(
        "URL 인코딩된 키도 마스킹됨",
        "INVALID" not in rb.request_url_masked and "serviceKey=***" in rb.request_url_masked,
        rb.request_url_masked.split("?")[1][:48] + "...",
    ))

    print("\n3-4. 버스 — 보존된 실제 응답으로 파싱 검증")
    for name, expect_code, min_rows in [
        ("getBusPosByRouteSt", "0", 1),
        ("getArrInfoByRouteAll", "0", 1),
    ]:
        for raw in _bus_fixtures(name):
            v = seoul_bus.judge(raw)
            results.append(_check(
                f"{name} ({len(raw):,}b) → code={v.business_code}, rows={v.row_count}",
                v.ok and v.business_code == expect_code and (v.row_count or 0) >= min_rows,
            ))

    for raw in _bus_fixtures("getPathInfoByBusNSubList"):
        v = seoul_bus.judge(raw)
        results.append(_check(
            "인증 실패 JSON을 업무 성공으로 오판하지 않음",
            not v.ok,
            f"ok={v.ok}, code={v.business_code}",
        ))

    print("\n3-5. 버스 업무코드 재시도 판정")
    for code, expected in [("0", False), ("1", True), ("2", False), ("6", True), ("8", False)]:
        results.append(_check(
            f"headerCd={code} 재시도={expected}",
            seoul_bus.is_retryable(code) is expected,
        ))

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
