"""PredictionSnapshot + ActualArrivalInterval -> ResidualEvent (EV2-03/EV2 vertical slice).

Matching rule: same vehicle_or_train_id, predicted_arrival_at =
source_generated_at + eta_seconds, matched to the *next* ActualArrivalInterval
for that vehicle whose upper_inclusive_at is >= the prediction's
source_generated_at (the nearest upcoming real arrival that prediction could
plausibly describe). Every PredictionSnapshot that matches the same
ActualArrivalInterval shares that interval's actual_id as validation_group_id
- 41_OBSERVATION_ACTUAL_RESIDUAL.md's own residual formula (section 4) plus
10_PHASE2_EVIDENCE_EXECUTION.md EV2-03's explicit "그룹 id로 leakage 방지" rule.

Known limitation (documented, not silently smoothed over): for bus, the
ActualArrivalInterval.node_id is a Position sectionId, not the Arrival stId
used as PredictionSnapshot.target_node_id - the Data Contract has not
canonicalized that stop-level join citywide. This module only matches by
vehicle id and a plausible near-future time window, which is defensible at
component/corridor scope (the position collector itself was scoped via
startOrd/endOrd to the target-leg stop range) but is NOT a validated
stop-exact join - callers must keep this leg's validation_scope as
COMPONENT_ONLY, not CORRIDOR_REPLAY or END_TO_END.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import timedelta

from schema import ActualArrivalInterval, PredictionSnapshot, ResidualContext, ResidualEvent

MAX_LEAD_TIME_SEC = 20 * 60  # do not match a prediction to an actual event more than 20 min away
# (arbitrary-window honesty note: this bounds obviously-wrong cross-vehicle-cycle
#  matches, it is not a claimed maximum real headway; see report limitations)


def build_residual_events(
    predictions: list[PredictionSnapshot],
    actuals: list[ActualArrivalInterval],
    route_or_line: str,
) -> list[ResidualEvent]:
    actuals_by_vehicle: dict[str, list[ActualArrivalInterval]] = defaultdict(list)
    for a in actuals:
        actuals_by_vehicle[a.vehicle_or_train_id].append(a)
    for veh, lst in actuals_by_vehicle.items():
        lst.sort(key=lambda a: a.upper_inclusive_at)

    events: list[ResidualEvent] = []
    for pred in predictions:
        veh = pred.vehicle_or_train_id
        if not veh or pred.eta_seconds is None:
            continue
        candidates = actuals_by_vehicle.get(veh, [])
        predicted_arrival_at = pred.source_generated_at + timedelta(seconds=pred.eta_seconds)

        match = None
        for a in candidates:
            if a.upper_inclusive_at >= pred.source_generated_at:
                lead = (a.upper_inclusive_at - pred.source_generated_at).total_seconds()
                if lead <= MAX_LEAD_TIME_SEC:
                    match = a
                    break
        if match is None:
            continue

        lead_time_sec = (match.upper_inclusive_at - pred.source_generated_at).total_seconds()
        residual_lower = (match.lower_exclusive_at - predicted_arrival_at).total_seconds()
        residual_mid = (match.midpoint_at - predicted_arrival_at).total_seconds()
        residual_upper = (match.upper_inclusive_at - predicted_arrival_at).total_seconds()

        events.append(
            ResidualEvent(
                residual_id=f"resid-{pred.prediction_id}-{uuid.uuid4().hex[:6]}",
                prediction_id=pred.prediction_id,
                actual_id=match.actual_id,
                lead_time_sec=lead_time_sec,
                residual_lower_sec=residual_lower,
                residual_mid_sec=residual_mid,
                residual_upper_sec=residual_upper,
                context=ResidualContext(
                    weekday_type=None,
                    route_or_line=route_or_line,
                    node_pair=f"{pred.target_node_id}->{match.node_id}",
                ),
                quality_flags=(
                    ["DQ-006:CROSSWALK_MISSING(stop<->section not canonicalized)"]
                    if pred.mode.value == "BUS"
                    else []
                ),
                validation_group_id=match.actual_id,
            )
        )
    return events
