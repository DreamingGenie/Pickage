"""EV2-03 + Vertical Slice Gate orchestration: Raw -> Observation -> Actual
-> Residual -> LegDistribution -> deterministic Journey simulation ->
BUS_SKIPPED reforecast, all against this session's real Phase 2 samples.

Usage:
    python run_vertical_slice.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from actual_builders import build_bus_actual_intervals, build_subway_actual_intervals
from distribution_builder import build_empirical_leg_distribution, build_static_reference_distribution
from engine import JourneyLegPlan, apply_bus_skipped, simulate_journey
from parsers import (
    bus_arrival_observation_and_predictions,
    bus_position_events,
    iter_raw_records,
    subway_arrival_observation_and_predictions,
    subway_arrival_state_events,
)
from residual_builder import build_residual_events
from schema import JourneyState, JourneyStateEnum, ValidationScope

KST = timezone(timedelta(hours=9))
JR_DOCS = Path(__file__).resolve().parents[3]  # .../journey_reliability_docs_v2
SAMPLES = JR_DOCS / "baseline" / "phase0" / "data" / "samples"
TODAY = "2026-08-22"

BUS_01A_ROUTE = "100100001"
BUS_01A_TARGET_ST_ID = "100000104"  # 안국역6번출구 (target leg destination stop, per Phase 1 BUS_01A_EXTENDED/README.md)

SUBWAY_TARGETS = [
    ("1003", "1003000328", "안국/3호선"),
    ("1003", "1003000340", "교대/3호선"),
    ("1002", "1002000223", "교대/2호선"),
    ("1002", "1002000221", "역삼/2호선"),
]


def load_bus(route_id: str, target_st_id: str | None):
    predictions = []
    for rec in iter_raw_records(SAMPLES / "seoul_bus" / "getArrInfoByRouteAll" / TODAY):
        params = rec.get("request_params_sanitized", {})
        if params.get("busRouteId") != route_id:
            continue
        _obs, preds = bus_arrival_observation_and_predictions(rec, target_st_id=target_st_id)
        predictions.extend(preds)

    position_events = []
    for rec in iter_raw_records(SAMPLES / "seoul_bus" / "getBusPosByRouteSt" / TODAY):
        params = rec.get("request_params_sanitized", {})
        if params.get("busRouteId") != route_id:
            continue
        position_events.extend(bus_position_events(rec))

    return predictions, position_events


def load_subway():
    all_predictions = []
    all_state_events = []
    for station_name in ["안국", "교대", "역삼"]:
        d = SAMPLES / "seoul_subway" / "realtimeStationArrival" / TODAY
        for rec in iter_raw_records(d):
            params = rec.get("request_params_sanitized", {})
            if params.get("station") != station_name:
                continue
            _obs, preds = subway_arrival_observation_and_predictions(rec)
            all_predictions.extend(preds)
            all_state_events.extend(subway_arrival_state_events(rec))
    return all_predictions, all_state_events


def main() -> None:
    report: dict = {}

    # --- EV2-03: bus 01A target-leg residual ---
    bus_preds, bus_pos_events = load_bus(BUS_01A_ROUTE, BUS_01A_TARGET_ST_ID)
    bus_actuals = build_bus_actual_intervals(bus_pos_events, BUS_01A_ROUTE)
    bus_residuals = build_residual_events(bus_preds, bus_actuals, route_or_line="01A")

    report["bus_01A_target_leg"] = {
        "predictions": len(bus_preds),
        "position_events": len(bus_pos_events),
        "actual_intervals": len(bus_actuals),
        "residual_events": len(bus_residuals),
        "residual_mid_samples_sec": [r.residual_mid_sec for r in bus_residuals],
        "lead_time_samples_sec": [r.lead_time_sec for r in bus_residuals],
    }

    # --- EV2-02: subway actual intervals per station x line ---
    subway_preds, subway_state_events = load_subway()
    subway_actuals_all = build_subway_actual_intervals(subway_state_events)

    subway_by_key = {}
    for subway_id, statn_id, label in SUBWAY_TARGETS:
        preds_here = [p for p in subway_preds if p.route_or_line_id == subway_id and p.target_node_id == statn_id]
        actuals_here = [
            a for a in subway_actuals_all if a.route_or_line_id == subway_id and a.node_id == statn_id
        ]
        residuals_here = build_residual_events(preds_here, actuals_here, route_or_line=label)
        distinct_trains = {p.vehicle_or_train_id for p in preds_here}
        subway_by_key[label] = {
            "predictions": len(preds_here),
            "distinct_trains": len(distinct_trains),
            "actual_intervals": len(actuals_here),
            "residual_events": len(residuals_here),
            "residual_mid_samples_sec": [r.residual_mid_sec for r in residuals_here],
        }
    report["subway_station_line"] = subway_by_key

    # --- LegDistribution artifacts for a demo Route A simulation ---
    access_walk = build_static_reference_distribution(
        "ACCESS_WALK", 245.0, "TMAP-point-EV-02", "single live TMAP call, demo origin->춘추문"
    )
    bus_target_leg = build_empirical_leg_distribution(
        "TRANSIT_RIDE_01A",
        [abs(s) for s in report["bus_01A_target_leg"]["residual_mid_samples_sec"]] or [400.0],
        None,
        None,
        "BUS_ACTUAL_RULE_V1_CANDIDATE+RESIDUAL",
        validation_scope=ValidationScope.COMPONENT_ONLY,
    )
    transfer_303 = build_static_reference_distribution(
        "TRANSFER_교대_3to2", 144.0, "OA-22521-PD-031", "door-specific official transfer row"
    )
    subway_ride = build_static_reference_distribution(
        "TRANSIT_RIDE_subway", 600.0, "structural-placeholder", "not the object of this vertical slice run"
    )
    final_walk = build_static_reference_distribution(
        "FINAL_WALK", 300.0, "TMAP-point-EV-04", "역삼 STATION_CENTER -> 멀티캠퍼스 POI"
    )

    legs = [
        JourneyLegPlan("ACCESS_WALK", access_walk),
        JourneyLegPlan("TRANSIT_RIDE_01A", bus_target_leg, samples_sec=[abs(s) for s in report["bus_01A_target_leg"]["residual_mid_samples_sec"]] or [400.0]),
        JourneyLegPlan("TRANSFER_교대_3to2", transfer_303),
        JourneyLegPlan("TRANSIT_RIDE_subway", subway_ride),
        JourneyLegPlan("FINAL_WALK", final_walk),
    ]

    start_at = datetime(2026, 8, 22, 8, 30, 0, tzinfo=KST)
    target_arrival_at = datetime(2026, 8, 22, 9, 0, 0, tzinfo=KST)
    run, result = simulate_journey(
        route_candidate_id="ROUTE_A-corridor_a",
        legs=legs,
        start_at=start_at,
        target_arrival_at=target_arrival_at,
        seed=42,
        n_requested=2000,
    )
    report["journey_simulation"] = {
        "simulation_run_id": run.simulation_run_id,
        "seed": run.seed,
        "n_executed": run.n_executed,
        "p50_arrival_at": result.p50_arrival_at.isoformat() if result.p50_arrival_at else None,
        "p90_arrival_at": result.p90_arrival_at.isoformat() if result.p90_arrival_at else None,
        "on_time_probability": result.on_time_probability,
        "confidence_label": result.confidence_label.value,
        "validation_scope": result.validation_scope.value,
        "model_coverage": result.model_coverage.value,
        "limitations": result.limitations,
    }

    # --- BUS_SKIPPED reforecast fixture demo ---
    state = JourneyState(
        journey_id="demo-journey-1",
        route_candidate_id="ROUTE_A-corridor_a",
        active_leg_id="TRANSIT_RIDE_01A",
        state=JourneyStateEnum.ACTIVE,
        state_version=1,
        updated_at=start_at,
    )
    new_state, event = apply_bus_skipped(state, "TRANSIT_RIDE_01A", start_at + timedelta(minutes=3))
    remaining_legs = legs[2:]  # after the skipped 01A leg: transfer, subway ride, final walk
    reforecast_start = start_at + timedelta(minutes=3)
    _run2, result2 = simulate_journey(
        route_candidate_id="ROUTE_A-corridor_a",
        legs=remaining_legs,
        start_at=reforecast_start,
        target_arrival_at=target_arrival_at,
        seed=42,
        n_requested=2000,
    )
    report["bus_skipped_reforecast_demo"] = {
        "state_before": state.state.value,
        "state_after": new_state.state.value,
        "state_version_before": state.state_version,
        "state_version_after": new_state.state_version,
        "event_id": event.event_id,
        "reforecast_on_time_probability": result2.on_time_probability,
        "reforecast_p90_arrival_at": result2.p90_arrival_at.isoformat() if result2.p90_arrival_at else None,
    }

    out_path = Path(__file__).resolve().parent.parent / "vertical_slice_result.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"wrote {out_path}")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
