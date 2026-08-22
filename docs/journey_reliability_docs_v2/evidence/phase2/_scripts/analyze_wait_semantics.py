"""EV2-04 — Bus WAIT event semantics: 147 boarding stop (stId=122000005, staOrd=41).

PD-034: Phase 1's 181 `exps1` 20-second poll snapshots are NOT 181
independent headway samples (heavy serial dependence - the same physical
vehicle is re-observed on almost every poll). This script builds the two
things EV2-04 asks for and keeps them explicitly separate:

  1. raw snapshot series: every poll's exps1 (candidate ETA-to-arrival in
     seconds) for the target stop, in poll order - and its lag-1
     autocorrelation, to make the dependence quantitative rather than
     asserted.
  2. event-based headway: distinct vehId1 turnover at the same stop
     (an "event" = the poll where vehId1 changes from the previous poll),
     with the real wall-clock gap between turnovers as the headway sample.

Usage:
    python analyze_wait_semantics.py
"""
from __future__ import annotations

import json
import re
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

VS_DIR = Path(__file__).resolve().parent.parent / "vertical_slice"
sys.path.insert(0, str(VS_DIR))
from parsers import iter_raw_records  # noqa: E402

KST = timezone(timedelta(hours=9))
TARGET_ST_ID = "122000005"
ROUTE_ID = "100100026"  # 147

SAMPLES_DIR = (
    Path(__file__).resolve().parents[3]  # .../journey_reliability_docs_v2
    / "baseline" / "phase0" / "data" / "samples" / "seoul_bus" / "getArrInfoByRouteAll" / "2026-08-22"
)


def _extract(payload: str, st_id: str) -> dict | None:
    for m in re.finditer(r"<itemList>(.*?)</itemList>", payload, re.DOTALL):
        block = m.group(1)
        sid = re.search(r"<stId>(.*?)</stId>", block)
        route = re.search(r"<busRouteId>(.*?)</busRouteId>", block)
        if sid and sid.group(1) == st_id and route and route.group(1) == ROUTE_ID:
            fields = {k: v for k, v in re.findall(r"<([a-zA-Z0-9_]+)>(.*?)</\1>", block)}
            return fields
    return None


def lag1_autocorr(series: list[float]) -> float | None:
    n = len(series)
    if n < 3:
        return None
    mean = statistics.mean(series)
    num = sum((series[i] - mean) * (series[i + 1] - mean) for i in range(n - 1))
    den = sum((x - mean) ** 2 for x in series)
    if den == 0:
        return None
    return num / den


def main() -> None:
    raw_series = []  # (poll_time, exps1, vehId1)
    for record in iter_raw_records(SAMPLES_DIR):
        if record.get("http_status") != 200 or not record.get("raw_payload"):
            continue
        item = _extract(record["raw_payload"], TARGET_ST_ID)
        if not item:
            continue
        try:
            exps1 = int(item.get("exps1", ""))
        except ValueError:
            continue
        poll_time = datetime.fromisoformat(record["received_at"])
        raw_series.append((poll_time, exps1, item.get("vehId1")))

    raw_series.sort(key=lambda t: t[0])

    exps1_values = [e for _, e, _ in raw_series]
    autocorr = lag1_autocorr([float(v) for v in exps1_values])

    # event-based: distinct vehId1 turnover
    turnovers = []
    prev_veh = None
    prev_time = None
    for poll_time, exps1, veh in raw_series:
        if prev_veh is not None and veh != prev_veh and veh not in (None, "0", ""):
            if prev_time is not None:
                turnovers.append((poll_time - prev_time).total_seconds())
        if veh not in (None, "0", ""):
            prev_veh = veh
            prev_time = poll_time

    result = {
        "target_stop": {"route": ROUTE_ID, "stId": TARGET_ST_ID},
        "raw_snapshot_series": {
            "n_polls": len(raw_series),
            "exps1_lag1_autocorrelation": autocorr,
            "exps1_median_sec": statistics.median(exps1_values) if exps1_values else None,
            "note": "each poll re-observes the SAME approaching vehicle repeatedly; "
                    "high lag-1 autocorrelation here is expected and is exactly why "
                    "these are not independent headway samples (PD-034).",
        },
        "event_based_headway": {
            "n_turnover_events": len(turnovers),
            "headway_samples_sec": turnovers,
            "median_headway_sec": statistics.median(turnovers) if turnovers else None,
        },
    }

    out_dir = Path(__file__).resolve().parent.parent / "EVD-WAIT-002"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "derived").mkdir(exist_ok=True)
    out_path = out_dir / "derived" / "wait_semantics.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"wrote {out_path}")
    print(json.dumps({k: v for k, v in result.items()}, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
