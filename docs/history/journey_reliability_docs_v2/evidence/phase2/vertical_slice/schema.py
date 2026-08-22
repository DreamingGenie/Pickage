"""Canonical entity DTOs for the Phase 2 probability vertical slice.

One canonical Pydantic implementation of the ENT-0xx entities defined in
docs/40_data_probability/40_DATA_CONTRACT.md (JR-DOC-040). Field names and
enums mirror that document exactly so this module has no independent
"design" authority - the Markdown contract stays the source of truth and
this is its runnable projection (10_PHASE2_EVIDENCE_EXECUTION.md section 3,
"ENT-* canonical DTO ... 1개 정본 구현").

Not implemented here: full Silver/Gold storage, versioning/immutability
enforcement (section 8 of the contract) - this is a vertical-slice fixture,
not a production data layer.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class CoordinateSource(str, Enum):
    USER_INPUT = "USER_INPUT"
    ROUTE_PROVIDER = "ROUTE_PROVIDER"
    SEOUL_MASTER = "SEOUL_MASTER"
    TMAP = "TMAP"
    MANUAL_VERIFIED = "MANUAL_VERIFIED"


class CoordinateRole(str, Enum):
    ORIGIN_POINT = "ORIGIN_POINT"
    BUS_STOP = "BUS_STOP"
    STATION_CENTER = "STATION_CENTER"
    STATION_EXIT = "STATION_EXIT"
    PLATFORM_REFERENCE = "PLATFORM_REFERENCE"
    POI = "POI"


class Mode(str, Enum):
    WALK = "WALK"
    BUS = "BUS"
    SUBWAY = "SUBWAY"


class GeoPoint(BaseModel):
    lat: float
    lon: float
    label: Optional[str] = None
    coordinate_source: CoordinateSource
    coordinate_role: CoordinateRole


class NodeNamespace(str, Enum):
    SEOUL_BUS_STOP = "SEOUL_BUS_STOP"
    SEOUL_SUBWAY_REALTIME = "SEOUL_SUBWAY_REALTIME"
    SEOUL_MIXED_ROUTE = "SEOUL_MIXED_ROUTE"
    TMAP_POI = "TMAP_POI"
    INTERNAL = "INTERNAL"


class NodeRef(BaseModel):
    node_namespace: NodeNamespace
    provider_node_id: Optional[str] = None
    name: Optional[str] = None
    mode: Mode
    line_or_route_id: Optional[str] = None
    coordinate: Optional[GeoPoint] = None
    mapping_version: Optional[str] = None


# --- ENT-001 Observation (Bronze->Silver boundary) ---------------------


class ObservationMode(str, Enum):
    BUS = "BUS"
    SUBWAY = "SUBWAY"
    WALK = "WALK"
    ROUTE = "ROUTE"
    SUPPORT = "SUPPORT"


class Observation(BaseModel):
    observation_id: str
    provider: str
    api_name: str
    mode: ObservationMode
    entity_type: str
    entity_key: str
    source_generated_at: Optional[datetime] = None
    requested_at: datetime
    received_at: datetime
    payload_hash: str
    raw_ref: str
    collector_version: str
    quality_flags: list[str] = Field(default_factory=list)
    schema_version: str = "phase2-v1"

    @property
    def request_latency_sec(self) -> float:
        return (self.received_at - self.requested_at).total_seconds()


# --- ENT-002 PredictionSnapshot -----------------------------------------


class PredictionSnapshot(BaseModel):
    prediction_id: str
    mode: Mode
    route_or_line_id: str
    vehicle_or_train_id: Optional[str] = None
    target_node_id: str
    predicted_arrival_at: Optional[datetime] = None
    eta_seconds: Optional[int] = None
    source_generated_at: datetime
    received_at: datetime
    observation_id: str
    quality_flags: list[str] = Field(default_factory=list)


# --- ENT-003 ActualArrivalInterval --------------------------------------


class ActualArrivalInterval(BaseModel):
    actual_id: str
    mode: Mode
    route_or_line_id: str
    vehicle_or_train_id: str
    node_id: str
    lower_exclusive_at: datetime
    upper_inclusive_at: datetime
    midpoint_at: datetime
    interval_width_sec: float
    trigger_rule_version: str
    source_observation_ids: list[str] = Field(default_factory=list)
    quality_flags: list[str] = Field(default_factory=list)


# --- ENT-004 ResidualEvent ----------------------------------------------


class ResidualContext(BaseModel):
    time_bucket: Optional[str] = None
    weekday_type: Optional[str] = None
    route_or_line: str
    node_pair: Optional[str] = None


class ResidualEvent(BaseModel):
    residual_id: str
    prediction_id: str
    actual_id: str
    lead_time_sec: Optional[float] = None
    residual_lower_sec: float
    residual_mid_sec: float
    residual_upper_sec: float
    context: ResidualContext
    quality_flags: list[str] = Field(default_factory=list)
    validation_group_id: str  # anti-leakage group key (PredictionSnapshot's Actual event)


# --- ENT-010 LegDistribution ---------------------------------------------


class DistributionKind(str, Enum):
    EMPIRICAL_SAMPLES = "EMPIRICAL_SAMPLES"
    QUANTILE_MODEL = "QUANTILE_MODEL"
    DETERMINISTIC_POINT = "DETERMINISTIC_POINT"
    STATIC_REFERENCE = "STATIC_REFERENCE"


class ConfidenceLabel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INSUFFICIENT = "INSUFFICIENT"


class UncertaintyCoverage(str, Enum):
    MODELED = "MODELED"
    PARTIAL = "PARTIAL"
    UNMODELED = "UNMODELED"


class ValidationScope(str, Enum):
    UNVALIDATED = "UNVALIDATED"
    COMPONENT_ONLY = "COMPONENT_ONLY"
    CORRIDOR_REPLAY = "CORRIDOR_REPLAY"
    END_TO_END = "END_TO_END"


class Quantiles(BaseModel):
    p10: Optional[float] = None
    p50: Optional[float] = None
    p90: Optional[float] = None


class LegDistribution(BaseModel):
    distribution_id: str
    leg_id: str
    distribution_kind: DistributionKind
    sample_count: Optional[int] = None
    observation_start_at: Optional[datetime] = None
    observation_end_at: Optional[datetime] = None
    value_semantics: str = "DURATION_SECONDS"
    quantiles_sec: Quantiles = Field(default_factory=Quantiles)
    samples_ref: Optional[str] = None
    fallback_level: Optional[str] = None
    confidence_label: ConfidenceLabel
    uncertainty_coverage: UncertaintyCoverage
    rule_version: str
    artifact_version: str
    validation_scope: ValidationScope


# --- ENT-012 JourneyState / ENT-013 UserEvent ----------------------------


class JourneyStateEnum(str, Enum):
    PRE_TRIP_READY = "PRE_TRIP_READY"
    ACTIVE = "ACTIVE"
    REFORECASTING = "REFORECASTING"
    ARRIVED = "ARRIVED"
    ABORTED = "ABORTED"


class JourneyState(BaseModel):
    journey_id: str
    route_candidate_id: str
    active_leg_id: Optional[str] = None
    state: JourneyStateEnum
    completed_leg_ids: list[str] = Field(default_factory=list)
    user_events: list[str] = Field(default_factory=list)
    state_version: int
    updated_at: datetime


class UserEventType(str, Enum):
    BUS_SKIPPED = "BUS_SKIPPED"
    BOARD_CONFIRMED = "BOARD_CONFIRMED"
    TRANSFER_MISSED = "TRANSFER_MISSED"


class UserEvent(BaseModel):
    event_id: str
    journey_id: str
    event_type: UserEventType
    occurred_at: datetime
    target_service_id: Optional[str] = None
    idempotency_key: str
    source: str = "USER"


# --- ENT-014 JourneySimulationRun / ENT-015 JourneyResultSnapshot -------


class JourneySimulationRun(BaseModel):
    simulation_run_id: str
    journey_id: Optional[str] = None
    route_candidate_id: str
    input_state_version: Optional[int] = None
    seed: int
    n_requested: int
    n_executed: int
    engine_version: str
    distribution_versions: list[str] = Field(default_factory=list)
    route_version: str
    wait_source_versions: list[str] = Field(default_factory=list)
    started_at: datetime
    completed_at: datetime


class RecommendedDepartureStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NOT_COMPUTED = "NOT_COMPUTED"


class ModelCoverage(str, Enum):
    FULL = "FULL"
    PARTIAL = "PARTIAL"


class JourneyResultSnapshot(BaseModel):
    result_id: str
    journey_id: Optional[str] = None
    simulation_run_id: str
    target_arrival_at: datetime
    p50_arrival_at: Optional[datetime] = None
    p90_arrival_at: Optional[datetime] = None
    on_time_probability: Optional[float] = None
    planned_connection_success_probability: Optional[float] = None
    recommended_departure_at: Optional[datetime] = None
    recommended_departure_status: RecommendedDepartureStatus
    confidence_label: ConfidenceLabel
    validation_scope: ValidationScope
    model_coverage: ModelCoverage
    fallback_summary: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    calculated_at: datetime
    result_version: int = 1


# --- Data Quality flags (41_OBSERVATION_ACTUAL_RESIDUAL.md section 8) --

DQ_FLAGS = {
    "DQ-001": "SOURCE_TIME_MISSING",
    "DQ-002": "DUPLICATE_SOURCE_EVENT",
    "DQ-003": "OUT_OF_ORDER_EVENT",
    "DQ-004": "UNMATCHED_VEHICLE",
    "DQ-005": "UNMATCHED_TRAIN",
    "DQ-006": "CROSSWALK_MISSING",
    "DQ-007": "ACTUAL_INTERVAL_TOO_WIDE",
    "DQ-008": "STALE_OBSERVATION",
    "DQ-009": "SERVICE_ENDED",
    "DQ-010": "NO_VEHICLE_ASSIGNED",
    "DQ-011": "LOW_SUPPORT",
    "DQ-012": "FALLBACK_USED",
    "DQ-013": "UNMODELED_UNCERTAINTY",
    "DQ-014": "PROVIDER_ERROR",
    "DQ-015": "PARTIAL_MODEL",
    "DQ-016": "COORDINATE_ROLE_UNKNOWN",
    "DQ-017": "WAIT_SOURCE_MISSING",
    "DQ-018": "CROSS_LEG_DEPENDENCE_UNMODELED",
    "DQ-019": "VALIDATION_SCOPE_LIMITED",
    "DQ-020": "PROVIDER_QUOTA_EXCEEDED",
    "DQ-021": "TIMESTAMP_INSTRUMENTATION_INVALID",
    "DQ-022": "MULTILINE_STATION_NOT_SPLIT",
}
