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

    for train_no, series in train_arvlcd.items():
        series_sorted = sorted(set(series), key=lambda t: t[0])
        codes = [c for _, c in series_sorted]
        print(f"  train {train_no}: {series_sorted}")

    position_train_nos = set()
    for sample in position_samples:
        raw = sample.get("raw_payload") or ""
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            continue
        for item in data.get("realtimePositionList", []):
            position_train_nos.add(item.get("trainNo"))

    arrival_train_nos = set(train_arvlcd.keys())
    overlap = arrival_train_nos & position_train_nos
    print(f"trainNo join at this station: {len(overlap)}/{len(arrival_train_nos)} "
          f"arrival trains also seen in position ({sorted(overlap)})")


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
