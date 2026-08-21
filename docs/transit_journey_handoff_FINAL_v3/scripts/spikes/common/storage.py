"""Bronze-contract sample writer for Phase 0 API spikes.

Implements the raw-sample fields required by
docs/01_PROJECT_HANDOFF.md section 9.1 (Raw를 버리지 않는다) and the
per-endpoint storage rules in docs/03_API_SPIKE_CHECKLIST.md.

Never put a secret key value inside request_params — callers must strip
it before calling record().
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

COLLECTOR_VERSION = "spike-v0"

DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "samples"


@dataclass
class SpikeResult:
    provider: str
    api_name: str
    request_params_sanitized: dict[str, Any]
    http_status: int | None
    raw_payload: str | None
    source_timestamp: str | None = None
    error_code: str | None = None
    error_body: str | None = None
    requested_at: str = field(default_factory=lambda: _now_iso())
    received_at: str = field(default_factory=lambda: _now_iso())
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _payload_hash(raw_payload: str | None) -> str | None:
    if raw_payload is None:
        return None
    return hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()


def record(result: SpikeResult) -> Path:
    """Write one Bronze-contract sample to data/samples/<provider>/<api>/<date>/."""
    requested_dt = datetime.fromisoformat(result.requested_at)
    day = requested_dt.strftime("%Y-%m-%d")
    hhmmss = requested_dt.strftime("%H%M%S")

    out_dir = DATA_DIR / result.provider / result.api_name / day
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{hhmmss}_{result.request_id}.json"

    record_dict = {
        "provider": result.provider,
        "api_name": result.api_name,
        "request_id": result.request_id,
        "requested_at": result.requested_at,
        "received_at": result.received_at,
        "http_status": result.http_status,
        "request_params_sanitized": result.request_params_sanitized,
        "raw_payload": result.raw_payload,
        "raw_payload_hash": _payload_hash(result.raw_payload),
        "source_timestamp": result.source_timestamp,
        "collector_version": COLLECTOR_VERSION,
        "error_code": result.error_code,
        "error_body": result.error_body,
    }

    out_path.write_text(json.dumps(record_dict, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path
