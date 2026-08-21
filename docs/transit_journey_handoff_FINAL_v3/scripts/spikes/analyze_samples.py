"""Analyze accumulated data/samples/ to compute the Spike A/B completion
metrics: duplicate-snapshot ratio, and actual-arrival interval width from
state transitions (bus stopFlag 0->1, subway arvlCd 0/1/2 sequence).

Read-only. Does not call any API.

Usage:
    python analyze_samples.py bus <busRouteId>
    python analyze_samples.py subway <statnId>
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "samples"


def _load_samples(provider: str, api_name: str) -> list[dict]:
    root = DATA_DIR / provider / api_name
    samples = []
    if not root.exists():
        return samples
    for path in sorted(root.glob("**/*.json")):
        samples.append(json.loads(path.read_text(encoding="utf-8")))
    return samples


def _field(item: str, name: str) -> str | None:
    m = re.search(f"<{name}>(.*?)</{name}>", item)
    return m.group(1) if m else None


def analyze_bus(bus_route_id: str) -> None:
    arrival_samples = _load_samples("seoul_bus", "getArrInfoByRouteAll")
    position_samples = _load_samples("seoul_bus", "getBusPosByRouteSt")
    print(f"arrival samples: {len(arrival_samples)}, position samples: {len(position_samples)}")

    # Duplicate ratio for position dataTm per vehId across polls.
    veh_datatm: dict[str, list[str]] = defaultdict(list)
    veh_stopflag: dict[str, list[tuple[str, str]]] = defaultdict(list)  # (dataTm, stopFlag)
    for sample in position_samples:
        raw = sample.get("raw_payload") or ""
        for item in re.findall(r"<itemList>(.*?)</itemList>", raw, re.S):
            veh_id = _field(item, "vehId")
            data_tm = _field(item, "dataTm")
            stop_flag = _field(item, "stopFlag")
            if veh_id is None:
                continue
            veh_datatm[veh_id].append(data_tm)
            veh_stopflag[veh_id].append((data_tm, stop_flag))

    total_obs = sum(len(v) for v in veh_datatm.values())
    dup_obs = sum(len(v) - len(set(v)) for v in veh_datatm.values())
    print(f"position: {len(veh_datatm)} distinct vehIds, {total_obs} observations, "
          f"{dup_obs} duplicate dataTm within a vehicle's series")

    transitions = 0
    for veh_id, series in veh_stopflag.items():
        series_sorted = sorted(series, key=lambda t: t[0] or "")
        for (t0, f0), (t1, f1) in zip(series_sorted, series_sorted[1:]):
            if f0 == "0" and f1 == "1":
                transitions += 1
                print(f"  stopFlag 0->1 transition: vehId={veh_id} {t0} -> {t1}")
    print(f"observed stopFlag 0->1 transitions: {transitions}")

    # vehId join rate: arrival vehId1/2 seen in any position vehId.
    position_veh_ids = set(veh_datatm.keys())
    arrival_veh_refs = 0
    matched = 0
    for sample in arrival_samples:
        raw = sample.get("raw_payload") or ""
        for item in re.findall(r"<itemList>(.*?)</itemList>", raw, re.S):
            for name in ("vehId1", "vehId2"):
                v = _field(item, name)
                if v and v != "0":
                    arrival_veh_refs += 1
                    if v in position_veh_ids:
                        matched += 1
    rate = (matched / arrival_veh_refs * 100) if arrival_veh_refs else 0.0
    print(f"vehId join rate: {matched}/{arrival_veh_refs} ({rate:.1f}%)")


def analyze_subway(statn_id: str) -> None:
    arrival_samples = _load_samples("seoul_subway", "realtimeStationArrival")
    position_samples = _load_samples("seoul_subway", "realtimePosition")
    print(f"arrival samples: {len(arrival_samples)}, position samples: {len(position_samples)}")

    train_arvlcd: dict[str, list[tuple[str, str]]] = defaultdict(list)  # (recptnDt, arvlCd)
    train_subwayid: dict[str, str] = {}
    for sample in arrival_samples:
        raw = sample.get("raw_payload") or ""
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            continue
        for item in data.get("realtimeArrivalList", []):
            if item.get("statnId") != statn_id:
                continue
            train_arvlcd[item["btrainNo"]].append((item["recptnDt"], item["arvlCd"]))
            train_subwayid[item["btrainNo"]] = item.get("subwayId")

    for train_no, series in train_arvlcd.items():
        series_sorted = sorted(set(series), key=lambda t: t[0])
        codes = [c for _, c in series_sorted]
        print(f"  train {train_no} (subwayId={train_subwayid[train_no]}): {series_sorted}")

    # Position trainNo is only unique *within* a line — a name-based station
    # query (e.g. "강남") can return trains from multiple lines that share the
    # station's display name (e.g. 2호선 vs 신분당선 both stopping at "강남").
    # Those other-line trains can never appear in a position feed polled for
    # a single target line, so join rate must be computed per subwayId
    # instead of pooling all trainNos together (see docs/05_DECISION_LOG.md
    # D-032 — this exact pooling previously made a cross-line name collision
    # look like a same-line join gap).
    position_train_nos_by_line: dict[str, set[str]] = defaultdict(set)
    for sample in position_samples:
        raw = sample.get("raw_payload") or ""
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            continue
        for item in data.get("realtimePositionList", []):
            position_train_nos_by_line[item.get("subwayId")].add(item.get("trainNo"))

    arrival_by_line: dict[str, set[str]] = defaultdict(set)
    for train_no, subway_id in train_subwayid.items():
        arrival_by_line[subway_id].add(train_no)

    for subway_id, arrival_train_nos in sorted(arrival_by_line.items(), key=lambda kv: kv[0] or ""):
        position_train_nos = position_train_nos_by_line.get(subway_id, set())
        if not position_train_nos:
            print(f"  subwayId={subway_id}: no position samples polled for this line "
                  f"(cannot join {len(arrival_train_nos)} arrival trains - not a data-quality gap, "
                  f"just never collected)")
            continue
        overlap = arrival_train_nos & position_train_nos
        rate = len(overlap) / len(arrival_train_nos) * 100
        print(f"  subwayId={subway_id} trainNo join: {len(overlap)}/{len(arrival_train_nos)} "
              f"({rate:.1f}%) unmatched={sorted(arrival_train_nos - position_train_nos)}")

    all_arrival_train_nos = set(train_arvlcd.keys())
    all_position_train_nos = set().union(*position_train_nos_by_line.values()) if position_train_nos_by_line else set()
    overlap = all_arrival_train_nos & all_position_train_nos
    print(f"trainNo join at this station (all lines pooled, informational only): "
          f"{len(overlap)}/{len(all_arrival_train_nos)} ({sorted(overlap)})")


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    mode, key = sys.argv[1], sys.argv[2]
    if mode == "bus":
        analyze_bus(key)
    elif mode == "subway":
        analyze_subway(key)
    else:
        print("mode must be 'bus' or 'subway'")
        sys.exit(1)


if __name__ == "__main__":
    main()
