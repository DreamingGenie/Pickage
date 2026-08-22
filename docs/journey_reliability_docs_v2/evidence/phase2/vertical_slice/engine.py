"""Fixed-seed Journey Engine fixture + BUS_SKIPPED reforecast fixture.

Scope per 10_PHASE2_EVIDENCE_EXECUTION.md section 12 (Vertical Slice Gate):
this is a deterministic/fixed-seed simulation FIXTURE, not a calibrated
probability product (PD-030/PD-040 explicitly forbid that claim here). It
demonstrates the pipeline shape:

    LegDistribution[] -> Monte Carlo sample -> JourneySimulationRun
                       -> JourneyResultSnapshot

For each leg: if real empirical samples are available, resample with
replacement (bootstrap) from them; otherwise use the leg's single point
value (STATIC_REFERENCE / DETERMINISTIC_POINT) with
UncertaintyCoverage.UNMODELED carried through untouched (PD-021 - no
invented variance for WALK/static legs that have none).
"""
from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta

from schema import (
    ConfidenceLabel,
    DistributionKind,
    JourneyResultSnapshot,
    JourneySimulationRun,
    JourneyState,
    JourneyStateEnum,
    LegDistribution,
    ModelCoverage,
    RecommendedDepartureStatus,
    UncertaintyCoverage,
    UserEvent,
    UserEventType,
    ValidationScope,
)


class JourneyLegPlan:
    def __init__(self, leg_id: str, distribution: LegDistribution, samples_sec: list[float] | None = None):
        self.leg_id = leg_id
        self.distribution = distribution
        self.samples_sec = samples_sec or []

    def draw(self, rng: random.Random) -> float:
        if self.distribution.distribution_kind == DistributionKind.EMPIRICAL_SAMPLES and self.samples_sec:
            return rng.choice(self.samples_sec)
        if self.distribution.quantiles_sec.p50 is not None:
            return self.distribution.quantiles_sec.p50
        return 0.0


def simulate_journey(
    route_candidate_id: str,
    legs: list[JourneyLegPlan],
    start_at: datetime,
    target_arrival_at: datetime,
    seed: int,
    n_requested: int = 2000,
) -> tuple[JourneySimulationRun, JourneyResultSnapshot]:
    rng = random.Random(seed)
    started_at = datetime.now(start_at.tzinfo)

    totals_sec: list[float] = []
    for _ in range(n_requested):
        total = sum(leg.draw(rng) for leg in legs)
        totals_sec.append(total)

    totals_sec.sort()
    n = len(totals_sec)
    p50_sec = totals_sec[n // 2]
    p90_sec = totals_sec[min(n - 1, int(n * 0.9))]

    p50_arrival_at = start_at + timedelta(seconds=p50_sec)
    p90_arrival_at = start_at + timedelta(seconds=p90_sec)

    on_time = sum(1 for t in totals_sec if start_at + timedelta(seconds=t) <= target_arrival_at) / n

    unmodeled_legs = [leg.leg_id for leg in legs if leg.distribution.uncertainty_coverage == UncertaintyCoverage.UNMODELED]
    insufficient_legs = [leg.leg_id for leg in legs if leg.distribution.confidence_label == ConfidenceLabel.INSUFFICIENT]
    low_legs = [leg.leg_id for leg in legs if leg.distribution.confidence_label == ConfidenceLabel.LOW]

    overall_confidence = ConfidenceLabel.HIGH
    for leg in legs:
        order = [ConfidenceLabel.INSUFFICIENT, ConfidenceLabel.LOW, ConfidenceLabel.MEDIUM, ConfidenceLabel.HIGH]
        if order.index(leg.distribution.confidence_label) < order.index(overall_confidence):
            overall_confidence = leg.distribution.confidence_label

    model_coverage = ModelCoverage.PARTIAL if unmodeled_legs else ModelCoverage.FULL

    completed_at = datetime.now(start_at.tzinfo)
    run = JourneySimulationRun(
        simulation_run_id=f"sim-{route_candidate_id}-{uuid.uuid4().hex[:8]}",
        route_candidate_id=route_candidate_id,
        seed=seed,
        n_requested=n_requested,
        n_executed=n,
        engine_version="phase2-vertical-slice-engine-v1",
        distribution_versions=[leg.distribution.distribution_id for leg in legs],
        route_version="ROUTE_A-corridor_a-v1",
        wait_source_versions=[
            leg.distribution.distribution_id for leg in legs if "wait" in leg.leg_id.lower()
        ],
        started_at=started_at,
        completed_at=completed_at,
    )

    limitations = []
    if unmodeled_legs:
        limitations.append(f"UNMODELED_UNCERTAINTY legs (point value only, no variance): {unmodeled_legs}")
    if insufficient_legs:
        limitations.append(f"INSUFFICIENT sample-count legs: {insufficient_legs}")
    if low_legs:
        limitations.append(f"LOW sample-count legs: {low_legs}")
    limitations.append("cross-leg/cross-mode residual dependence not modeled (DQ-018, PD-027)")
    limitations.append(
        "leg-level empirical fit only - no journey-level hold-out calibration has been run (PD-030)"
    )

    result = JourneyResultSnapshot(
        result_id=f"result-{run.simulation_run_id}",
        simulation_run_id=run.simulation_run_id,
        target_arrival_at=target_arrival_at,
        p50_arrival_at=p50_arrival_at,
        p90_arrival_at=p90_arrival_at,
        on_time_probability=on_time,
        recommended_departure_status=RecommendedDepartureStatus.INSUFFICIENT_DATA,
        confidence_label=overall_confidence,
        validation_scope=ValidationScope.COMPONENT_ONLY,
        model_coverage=model_coverage,
        fallback_summary=[leg.leg_id for leg in legs if leg.distribution.fallback_level],
        limitations=limitations,
        calculated_at=completed_at,
    )
    return run, result


# --- BUS_SKIPPED state transition / reforecast fixture --------------------


def apply_bus_skipped(
    state: JourneyState,
    skipped_leg_id: str,
    occurred_at: datetime,
) -> tuple[JourneyState, UserEvent]:
    """PD-011: BUS_SKIPPED is a user-confirmed Event, not a model output.

    Deterministic state transition only: ACTIVE -> REFORECASTING, bump
    state_version, append the event. The caller re-runs simulate_journey()
    on the remaining legs with a fresh start_at to actually reforecast -
    this function does not itself touch any LegDistribution.
    """
    event = UserEvent(
        event_id=f"evt-{uuid.uuid4().hex[:8]}",
        journey_id=state.journey_id,
        event_type=UserEventType.BUS_SKIPPED,
        occurred_at=occurred_at,
        target_service_id=skipped_leg_id,
        idempotency_key=f"{state.journey_id}:{skipped_leg_id}:BUS_SKIPPED",
    )
    new_state = state.model_copy(
        update={
            "state": JourneyStateEnum.REFORECASTING,
            "state_version": state.state_version + 1,
            "user_events": state.user_events + [event.event_id],
            "updated_at": occurred_at,
        }
    )
    return new_state, event
