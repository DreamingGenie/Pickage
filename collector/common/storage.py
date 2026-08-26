"""Bronze 계층 기록기.

규약은 collector/BRONZE_CONTRACT.md를 따른다. 요약하면

    data/bronze/<source_key>/service_date=YYYY-MM-DD/
        <UTC timestamp>_<request_id>.<ext>        원문 그대로
        <UTC timestamp>_<request_id>.meta.json    수집 메타

출처: docs/history/journey_reliability_docs_v2/baseline/phase0/scripts/spikes/common/storage.py
(COLLECTOR_VERSION spike-v1-ev2-01)

원본 대비 변경한 것:
  1. 파티션 키를 달력 날짜 → 운행일(service_date)로 교체
  2. 원문을 메타 JSON 안의 문자열이 아니라 별도 파일로 분리
     (OA-15799는 1회 2.8MB이며, JSON 문자열로 감싸면 이스케이프로 커지고
      파싱 비용이 커진다)
  3. HTTP 상태와 업무코드를 분리 판정하는 outcome 필드 추가
     (검증 중 HTTP 200 + ERROR-336이 성공으로 기록되는 것을 실제로 관측함)
  4. payload_bytes / row_count / business_code / quota_seq_today 추가
  5. request_url을 마스킹해 보존 (인증키가 URL path에 들어가는 provider 대응)

원본에서 유지한 것:
  - requested_at / received_at을 기본값 없는 필수 인자로 두어, 응답 수신 후
    두 값을 동시에 찍는 과거 버그(PD-037 / EV2-01)를 구조적으로 막는다.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import service_day

COLLECTOR_VERSION = "bronze-v2"

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BRONZE_DIR = _REPO_ROOT / "data" / "bronze"

# outcome 값
OK = "OK"                          # HTTP 성공 + 업무코드 성공
BUSINESS_ERROR = "BUSINESS_ERROR"  # HTTP 성공이지만 업무코드가 오류
HTTP_ERROR = "HTTP_ERROR"          # HTTP 상태 자체가 실패
TRANSPORT_ERROR = "TRANSPORT_ERROR"  # 연결 실패·타임아웃 등 응답 없음


@dataclass
class CollectionResult:
    """수집 1회의 결과. requested_at/received_at은 기본값이 없다(의도적)."""

    source_key: str
    provider: str
    endpoint: str
    requested_at: str
    received_at: str
    request_url_masked: str
    http_status: int | None
    payload: bytes | None
    payload_ext: str = "txt"
    business_code: str | None = None
    row_count: int | None = None
    outcome: str = OK
    error_code: str | None = None
    error_body: str | None = None
    quota_seq_today: int | None = None
    # 어떤 인증키로 호출했는지. 값 자체는 넣지 않는다(quota.key_id 해시 앞 8자리).
    key_id: str | None = None
    # 이 호출이 차감된 quota 원장 풀 이름. runner를 경유하지 않으면 None.
    quota_pool: str | None = None
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    @property
    def latency_ms(self) -> float:
        started = datetime.fromisoformat(self.requested_at)
        ended = datetime.fromisoformat(self.received_at)
        return (ended - started).total_seconds() * 1000


def now_iso() -> str:
    """UTC ISO8601. 호출 직전과 응답 직후에 각각 따로 부른다."""
    return datetime.now(timezone.utc).isoformat()


def _sha256(payload: bytes | None) -> str | None:
    return hashlib.sha256(payload).hexdigest() if payload is not None else None


def record(result: CollectionResult, bronze_dir: Path | None = None) -> Path:
    """원문과 메타를 Bronze에 기록하고 메타 파일 경로를 반환한다."""
    base = bronze_dir or BRONZE_DIR
    requested_dt = datetime.fromisoformat(result.requested_at)
    svc_date = service_day.service_date(requested_dt)
    stamp = requested_dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")[:-4] + "Z"
    stem = f"{stamp}_{result.request_id}"

    out_dir = base / result.source_key / f"service_date={svc_date}"
    out_dir.mkdir(parents=True, exist_ok=True)

    payload_path: Path | None = None
    if result.payload is not None:
        payload_path = out_dir / f"{stem}.{result.payload_ext}"
        payload_path.write_bytes(result.payload)

    meta = {
        "source_key": result.source_key,
        "provider": result.provider,
        "endpoint": result.endpoint,
        "request_id": result.request_id,
        "service_date": svc_date,
        "request_url": result.request_url_masked,
        "requested_at": result.requested_at,
        "received_at": result.received_at,
        "latency_ms": round(result.latency_ms, 3),
        "http_status": result.http_status,
        "business_code": result.business_code,
        "outcome": result.outcome,
        "row_count": result.row_count,
        "payload_file": payload_path.name if payload_path else None,
        "payload_bytes": len(result.payload) if result.payload is not None else None,
        "payload_sha256": _sha256(result.payload),
        "collector_version": COLLECTOR_VERSION,
        "quota_seq_today": result.quota_seq_today,
        "key_id": result.key_id,
        "quota_pool": result.quota_pool,
        "error_code": result.error_code,
        "error_body": result.error_body,
    }

    meta_path = out_dir / f"{stem}.meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta_path


def load_meta(meta_path: Path) -> dict[str, Any]:
    return json.loads(meta_path.read_text(encoding="utf-8"))
