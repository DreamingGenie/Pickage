from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


COLLECTOR_VERSION = "jr-collector-v2"
SCHEMA_VERSION = "jr-observation-v1"
VALIDATOR_VERSION = "jr-validator-v2"


class CheckStatus(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    NOT_EVALUATED = "NOT_EVALUATED"


class AggregateVerdict(StrEnum):
    USABLE = "USABLE"
    CONDITIONAL = "CONDITIONAL"
    UNUSABLE = "UNUSABLE"


class Purpose(StrEnum):
    CONTRACT_SMOKE = "CONTRACT_SMOKE"
    STRUCTURE = "STRUCTURE"
    REALTIME_FEATURE = "REALTIME_FEATURE"
    ACTUAL_LABEL = "ACTUAL_LABEL"
    HISTORICAL_DISTRIBUTION = "HISTORICAL_DISTRIBUTION"
    HISTORICAL_MODEL = "HISTORICAL_MODEL"
    EXTERNAL_COVARIATE = "EXTERNAL_COVARIATE"
    INCIDENT_FEATURE = "INCIDENT_FEATURE"


@dataclass(frozen=True)
class ValidationScope:
    source_id: str
    provider: str
    endpoint: str
    purpose: Purpose
    target: str
    window_started_at: str
    window_ended_at: str
    adapter_version: str = COLLECTOR_VERSION
    schema_version: str = SCHEMA_VERSION
    policy_version: str = "provider-policy-v1"
    profile_version: str = "UNPROFILED"
    evidence_mode: str = "LIVE"

    def key(self) -> str:
        return "|".join(
            (
                self.source_id,
                self.provider,
                self.endpoint,
                self.purpose.value,
                self.target,
                self.window_started_at,
                self.window_ended_at,
                self.adapter_version,
                self.schema_version,
                self.policy_version,
                self.profile_version,
                self.evidence_mode,
            )
        )


@dataclass
class HttpExchange:
    exchange_id: str
    source_id: str
    safe_endpoint: str
    safe_params: dict[str, Any]
    requested_at: str
    headers_received_at: str | None
    body_completed_at: str
    http_status: int | None
    content_type: str | None
    body: bytes
    body_sha256: str
    body_bytes: int
    attempts: int
    elapsed_ms: float
    transport_error: str | None = None
    retry_after: str | None = None
    retry_history: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ParsedBatch:
    source_id: str
    rows: list[dict[str, Any]]
    business_code: str | None
    business_message: str | None
    declared_count: int | None
    parse_error: str | None
    response_format: str | None


@dataclass
class QualityCheck:
    code: str
    name: str
    status: CheckStatus
    message: str
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class PurposeEligibility:
    purpose: Purpose
    verdict: AggregateVerdict
    reason_codes: list[str]
    message: str


@dataclass
class ValidationReport:
    report_id: str
    run_id: str
    scope: ValidationScope
    verdict: AggregateVerdict
    checks: list[QualityCheck]
    eligibility: list[PurposeEligibility]
    metrics: dict[str, Any]
    evaluated_at: str
    limitations: list[str] = field(default_factory=list)
    manifest_sha256: str | None = None
    validator_version: str = VALIDATOR_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CollectionItem:
    exchange: HttpExchange
    batch: ParsedBatch


@dataclass
class CollectionRun:
    run_id: str
    source_id: str
    target: str
    started_at: str
    ended_at: str
    params: dict[str, Any]
    items: list[CollectionItem]
    evidence_mode: str = "LIVE"
    report: ValidationReport | None = None
    failure_code: str | None = None
    failure_message: str | None = None

    def to_summary(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "source_id": self.source_id,
            "evidence_mode": self.evidence_mode,
            "target": self.target,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "observation_count": len(self.items),
            "http_statuses": [item.exchange.http_status for item in self.items],
            "row_count": sum(len(item.batch.rows) for item in self.items),
            "status": "FAILED" if self.failure_code else "COMPLETE",
            "failure_code": self.failure_code,
            "failure_message": self.failure_message,
            "report": self.report.to_dict() if self.report else None,
        }
