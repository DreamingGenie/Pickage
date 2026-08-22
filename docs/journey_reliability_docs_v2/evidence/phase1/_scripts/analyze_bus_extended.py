"""Phase 1 analysis: compute EV-09 (01A target-leg) and EV-07 (147 wait/headway)
metrics from the extended bus collection.

Usage:
    python analyze_bus_extended.py
"""
from __future__ import annotations

import json
import statistics
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # journey_reliability_docs_v2/
SAMPLES = ROOT / "baseline" / "phase0" / "data" / "samples" / "seoul_bus"
OUT_01A = Path(__file__).resolve().parents[1] / "BUS_01A_EXTENDED" / "derived"
OUT_147 = Path(__file__).resolve().parents[1] / "EVD-WAIT-001" / "derived"
OUT_01A.mkdir(parents=True, exist_ok=True)
OUT_147.mkdir(parents=True, exist_ok=True)


def load_arrival(route_id: str) -> list[dict]:
    base = SAMPLES / "getArrInfoByRouteAll"
    out = []
    if not base.exists():
        return out
    for day_dir in base.iterdir():
        for f in sorted(day_dir.glob("*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            if d.get("request_params_sanitized", {}).get("busRouteId") == route_id:
                out.append(d)
    return out


def load_position(route_id: str) -> list[dict]:
    base = SAMPLES / "getBusPosByRouteSt"
    out = []
    if not base.exists():
        return out
    for day_dir in base.iterdir():
        for f in sorted(day_dir.glob("*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            if d.get("request_params_sanitized", {}).get("busRouteId") == route_id:
                out.append(d)
    return out


def parse_mktm(s: str) -> datetime | None:
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S.%f")
    except Exception:
        return None


def analyze_arrival_target_stops(route_id: str, target_st_ids: set[str]) -> dict:
    samples = load_arrival(route_id)
    polls = len(samples)
    success = sum(1 for s in samples if s.get("http_status") == 200 and s.get("error_code") is None)
    error = polls - success
    mktm_seq = []
    per_stop_veh_snapshots: dict[str, list[tuple[datetime, str, str, str, str]]] = defaultdict(list)
    # (poll_time, vehId1, exps1, congestion-like flag if present, raw)

    for s in samples:
        if s.get("raw_payload") is None:
            continue
        try:
            root = ET.fromstring(s["raw_payload"])
        except ET.ParseError:
            continue
        mk = root.findtext(".//mkTm")
        dt = parse_mktm(mk) if mk else None
        if dt:
            mktm_seq.append(dt)
        for item in root.findall(".//itemList"):
            st_id = item.findtext("stId")
            if st_id in target_st_ids:
                v1 = item.findtext("vehId1")
                v2 = item.findtext("vehId2")
                e1 = item.findtext("exps1")
                e2 = item.findtext("exps2")
                if dt:
                    per_stop_veh_snapshots[st_id].append((dt, v1, e1, v2, e2))

    duplicate = 0
    out_of_order = 0
    for i in range(1, len(mktm_seq)):
        if mktm_seq[i] == mktm_seq[i - 1]:
            duplicate += 1
        elif mktm_seq[i] < mktm_seq[i - 1]:
            out_of_order += 1

    # Distinct vehId sequence per stop (vehId1 track) -> transitions = count of
    # times vehId1 changes to a NEW value (a bus has passed/been replaced as
    # "next bus").
    # exps1 = seconds-until-arrival prediction for the immediate next bus,
    # sampled every poll -> a real, sustained WAIT-candidate sample (not a
    # future-vehicle-ID prediction, just an elapsed-seconds distribution).
    wait_samples_by_stop = {}
    for st_id, snaps in per_stop_veh_snapshots.items():
        exps1_vals = []
        for _, _, e1, _, _ in snaps:
            if e1 is not None:
                try:
                    exps1_vals.append(int(e1))
                except ValueError:
                    pass
        if exps1_vals:
            s = sorted(exps1_vals)
            wait_samples_by_stop[st_id] = {
                "sample_count": len(s),
                "seconds_min": s[0],
                "seconds_p50": statistics.median(s),
                "seconds_p90": s[int(len(s) * 0.9) - 1] if len(s) >= 10 else s[-1],
                "seconds_max": s[-1],
            }

    transitions_by_stop = {}
    for st_id, snaps in per_stop_veh_snapshots.items():
        snaps.sort(key=lambda x: x[0])
        seq = [v1 for _, v1, _, _, _ in snaps if v1]
        transitions = sum(1 for i in range(1, len(seq)) if seq[i] != seq[i - 1])
        distinct_veh = len(set(seq))
        transitions_by_stop[st_id] = {
            "polls_with_data": len(snaps),
            "distinct_vehId1_seen": distinct_veh,
            "vehId1_transitions": transitions,
        }

    return {
        "route_id": route_id,
        "wait_candidate_exps1_seconds_by_stop": wait_samples_by_stop,
        "polls": polls,
        "success": success,
        "error": error,
        "duplicate_mkTm": duplicate,
        "out_of_order_mkTm": out_of_order,
        "target_stop_transitions": transitions_by_stop,
    }


def analyze_position(route_id: str, target_sect_range: tuple[int, int]) -> dict:
    samples = load_position(route_id)
    polls = len(samples)
    success = sum(1 for s in samples if s.get("http_status") == 200 and s.get("error_code") is None)
    error = polls - success
    total_rows = 0
    congestion_counts: dict[str, int] = defaultdict(int)
    full_flag_counts: dict[str, int] = defaultdict(int)
    veh_sightings: dict[str, list[tuple[datetime, int]]] = defaultdict(list)

    for s in samples:
        if s.get("raw_payload") is None:
            continue
        try:
            root = ET.fromstring(s["raw_payload"])
        except ET.ParseError:
            continue
        received = s.get("received_at")
        dt = None
        if received:
            try:
                dt = datetime.fromisoformat(received.replace("Z", "+00:00"))
            except Exception:
                dt = None
        for item in root.findall(".//itemList"):
            total_rows += 1
            cong = item.findtext("congetion")
            full = item.findtext("isFullFlag")
            if cong is not None:
                congestion_counts[cong] += 1
            if full is not None:
                full_flag_counts[full] += 1
            veh = item.findtext("vehId")
            sect_ord = item.findtext("sectOrd")
            if veh and sect_ord and dt:
                try:
                    so = int(sect_ord)
                except ValueError:
                    continue
                if target_sect_range[0] <= so <= target_sect_range[1]:
                    veh_sightings[veh].append((dt, so))

    # Target-leg residual: for each vehicle seen crossing the target ord
    # range, the elapsed time between its first and last sighting in-range
    # is a real observed dwell/traverse time for that leg (a residual proxy,
    # not a route-level multi-stop count — see BUS_01A_EXTENDED/README.md).
    target_leg_times = []
    for veh, sightings in veh_sightings.items():
        sightings.sort(key=lambda x: x[0])
        if len(sightings) >= 2:
            span = (sightings[-1][0] - sightings[0][0]).total_seconds()
            if span > 0:
                target_leg_times.append(span)

    result = {
        "route_id": route_id,
        "polls": polls,
        "success": success,
        "error": error,
        "total_position_rows": total_rows,
        "congestion_counts": dict(congestion_counts),
        "isFullFlag_counts": dict(full_flag_counts),
        "distinct_vehicles_in_target_range": len(veh_sightings),
        "target_leg_traverse_time_samples": len(target_leg_times),
    }
    if target_leg_times:
        s = sorted(target_leg_times)
        result["target_leg_traverse_seconds"] = {
            "min": s[0],
            "p50": statistics.median(s),
            "max": s[-1],
        }
    return result


def main() -> None:
    out = {
        "01A_arrival_target_leg": analyze_arrival_target_stops("100100001", {"100000417", "100000104"}),
        "01A_position_target_leg": analyze_position("100100001", (19, 21)),
        "147_arrival_wait": analyze_arrival_target_stops("100100026", {"122000005", "122000179"}),
        "147_position": analyze_position("100100026", (41, 48)),
    }
    (OUT_01A / "metrics_raw.json").write_text(
        json.dumps({"01A_arrival_target_leg": out["01A_arrival_target_leg"], "01A_position_target_leg": out["01A_position_target_leg"]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUT_147 / "metrics_raw.json").write_text(
        json.dumps({"147_arrival_wait": out["147_arrival_wait"], "147_position": out["147_position"]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(out, ensure_ascii=False, indent=2)[:4000])


if __name__ == "__main__":
    main()
