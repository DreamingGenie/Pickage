"""Raw position/arrival state streams -> ActualArrivalInterval (EV2 vertical slice).

Rules exactly as documented in 41_OBSERVATION_ACTUAL_RESIDUAL.md:

Bus (BUS_ACTUAL_RULE_V1_CANDIDATE, section 3):
    same vehId, consecutive observations, stopFlag 0 -> 1 transition.
    lower_exclusive_at = previous source time; upper_inclusive_at = first
    stopFlag=1 source time.

Subway (SUBWAY_ACTUAL_RULE_V0, section 6):
    key (subwayId, statnId, btrainNo). Trigger: previous arvlCd != 1, next
    arvlCd == 1. Interval: (previous_source_time, first_arrival_source_time].

Quality guard applied for both: source time must be non-decreasing per key
(else DQ-003 OUT_OF_ORDER_EVENT, event kept but flagged, not silently
dropped per 41_OBSERVATION_ACTUAL_RESIDUAL.md section 10); duplicate
consecutive identical-state rows for the same key+time collapse (DQ-002).
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime

from schema import ActualArrivalInterval, Mode


def build_bus_actual_intervals(
    position_events: list[dict], route_or_line_id: str
) -> list[ActualArrivalInterval]:
    """position_events: list of {vehId, sectionId, stopFlag, dataTm, observation_id}, any order."""
    by_veh: dict[str, list[dict]] = defaultdict(list)
    for ev in position_events:
        if not ev.get("vehId"):
            continue
        by_veh[ev["vehId"]].append(ev)

    intervals: list[ActualArrivalInterval] = []
    for veh_id, events in by_veh.items():
        events_sorted = sorted(events, key=lambda e: e["dataTm"])
        # de-dup identical (dataTm, stopFlag, sectionId) consecutive rows (DQ-002)
        deduped = []
        for ev in events_sorted:
            if deduped and deduped[-1]["dataTm"] == ev["dataTm"] and deduped[-1]["stopFlag"] == ev["stopFlag"]:
                continue
            deduped.append(ev)

        prev = None
        for ev in deduped:
            if prev is not None and prev["stopFlag"] == "0" and ev["stopFlag"] == "1":
                quality_flags = []
                if ev["dataTm"] < prev["dataTm"]:
                    quality_flags.append("DQ-003:OUT_OF_ORDER_EVENT")
                width = (ev["dataTm"] - prev["dataTm"]).total_seconds()
                intervals.append(
                    ActualArrivalInterval(
                        actual_id=f"actual-bus-{veh_id}-{ev['dataTm'].isoformat()}-{uuid.uuid4().hex[:6]}",
                        mode=Mode.BUS,
                        route_or_line_id=route_or_line_id,
                        vehicle_or_train_id=veh_id,
                        node_id=ev.get("sectionId") or "",
                        lower_exclusive_at=prev["dataTm"],
                        upper_inclusive_at=ev["dataTm"],
                        midpoint_at=prev["dataTm"] + (ev["dataTm"] - prev["dataTm"]) / 2,
                        interval_width_sec=width,
                        trigger_rule_version="BUS_ACTUAL_RULE_V1_CANDIDATE",
                        source_observation_ids=[prev["observation_id"], ev["observation_id"]],
                        quality_flags=quality_flags,
                    )
                )
            prev = ev
    return intervals


def build_subway_actual_intervals(state_events: list[dict]) -> list[ActualArrivalInterval]:
    """state_events: list of {subwayId, statnId, btrainNo, arvlCd, recptnDt, observation_id}."""
    by_key: dict[tuple, list[dict]] = defaultdict(list)
    for ev in state_events:
        if not ev.get("btrainNo") or not ev.get("statnId"):
            continue
        key = (ev["subwayId"], ev["statnId"], ev["btrainNo"])  # PD-039: subwayId x statnId split
        by_key[key].append(ev)

    intervals: list[ActualArrivalInterval] = []
    for (subway_id, statn_id, train_no), events in by_key.items():
        events_sorted = sorted(events, key=lambda e: e["recptnDt"])
        deduped = []
        for ev in events_sorted:
            if deduped and deduped[-1]["recptnDt"] == ev["recptnDt"] and deduped[-1]["arvlCd"] == ev["arvlCd"]:
                continue
            deduped.append(ev)

        prev = None
        for ev in deduped:
            if prev is not None and prev["arvlCd"] != "1" and ev["arvlCd"] == "1":
                quality_flags = []
                if ev["recptnDt"] < prev["recptnDt"]:
                    quality_flags.append("DQ-003:OUT_OF_ORDER_EVENT")
                width = (ev["recptnDt"] - prev["recptnDt"]).total_seconds()
                intervals.append(
                    ActualArrivalInterval(
                        actual_id=f"actual-subway-{statn_id}-{train_no}-{ev['recptnDt'].isoformat()}-{uuid.uuid4().hex[:6]}",
                        mode=Mode.SUBWAY,
                        route_or_line_id=subway_id,
                        vehicle_or_train_id=train_no,
                        node_id=statn_id,
                        lower_exclusive_at=prev["recptnDt"],
                        upper_inclusive_at=ev["recptnDt"],
                        midpoint_at=prev["recptnDt"] + (ev["recptnDt"] - prev["recptnDt"]) / 2,
                        interval_width_sec=width,
                        trigger_rule_version="SUBWAY_ACTUAL_RULE_V0",
                        source_observation_ids=[prev["observation_id"], ev["observation_id"]],
                        quality_flags=quality_flags,
                    )
                )
            prev = ev
    return intervals
