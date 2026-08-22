"""Phase 1 analysis: compute EV-08 required metrics from sustained subway collection.

Reads every raw sample written under
baseline/phase0/data/samples/seoul_subway/{realtimeStationArrival,realtimePosition}/2026-08-22/
and computes, per station (arrival) and per line (position):
  - polls/success/error/empty
  - duplicate/out-of-order (by recptnDt not going strictly forward)
  - arrival row counts, arvlCd distribution (incl. arvlCd==1)
  - train join: btrainNo (arrival) vs trainNo (position), numerator/denominator/rate
  - ActualArrivalInterval: consecutive arvlCd==1 sightings of the same btrainNo at the
    same station -> interval between them (proxy for actual headway), width min/p50/p90/max
  - Prediction->Actual match: a btrainNo seen with arvlCd in {0,99} in an earlier poll
    later seen with arvlCd==1 at the same station

Usage:
    python analyze_subway_sustained.py
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # journey_reliability_docs_v2/
SAMPLES = ROOT / "baseline" / "phase0" / "data" / "samples" / "seoul_subway"
OUT = Path(__file__).resolve().parents[1] / "SUBWAY_SUSTAINED" / "derived"
OUT.mkdir(parents=True, exist_ok=True)

STATIONS = ["안국", "교대", "역삼"]
LINES = ["3호선", "2호선"]


def load_samples(api_name: str, keyword: str) -> list[dict]:
    base = SAMPLES / api_name
    out = []
    if not base.exists():
        return out
    for day_dir in base.iterdir():
        for f in sorted(day_dir.glob("*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            params = d.get("request_params_sanitized", {})
            if keyword in (params.get("station") or params.get("line") or ""):
                out.append(d)
    return out


def parse_dt(s: str) -> datetime | None:
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def analyze_arrival(station: str) -> dict:
    samples = load_samples("realtimeStationArrival", station)
    polls = len(samples)
    success = 0
    error = 0
    quota_exceeded = 0
    quota_first_ts = None
    empty = 0
    arvl_counts: dict[str, int] = defaultdict(int)
    total_rows = 0
    recptn_by_poll = []
    per_train_sightings: dict[str, list[tuple[datetime, str]]] = defaultdict(list)

    for s in samples:
        if s.get("error_code") is not None or s.get("http_status") != 200:
            error += 1
            continue
        payload = s.get("raw_payload")
        if payload is None:
            error += 1
            continue
        try:
            raw = json.loads(payload)
        except Exception:
            error += 1
            continue
        if raw.get("code") == "ERROR-337" or "realtimeArrivalList" not in raw:
            quota_exceeded += 1
            if quota_first_ts is None:
                quota_first_ts = s.get("received_at")
            continue
        success += 1
        rows = raw.get("realtimeArrivalList") or []
        if not rows:
            empty += 1
            continue
        total_rows += len(rows)
        poll_recptn = None
        for row in rows:
            code = str(row.get("arvlCd"))
            arvl_counts[code] += 1
            btrain = row.get("btrainNo")
            recptn = row.get("recptnDt")
            dt = parse_dt(recptn) if recptn else None
            if dt and btrain:
                per_train_sightings[btrain].append((dt, code))
            if dt:
                poll_recptn = dt
        if poll_recptn:
            recptn_by_poll.append(poll_recptn)

    duplicate = 0
    out_of_order = 0
    for i in range(1, len(recptn_by_poll)):
        if recptn_by_poll[i] == recptn_by_poll[i - 1]:
            duplicate += 1
        elif recptn_by_poll[i] < recptn_by_poll[i - 1]:
            out_of_order += 1

    # First-seen arvlCd==1 ("arrived") timestamp per distinct train — the actual
    # arrival event for that train, not a repeated in-state sighting.
    first_arrival_by_train: dict[str, datetime] = {}
    pred_to_actual_matches = 0
    for btrain, sightings in per_train_sightings.items():
        sightings.sort(key=lambda x: x[0])
        arvl1_times = [dt for dt, code in sightings if code == "1"]
        if arvl1_times:
            first_arrival_by_train[btrain] = arvl1_times[0]
        codes_seen = {code for _, code in sightings}
        if "1" in codes_seen and (codes_seen & {"0", "99"}):
            pred_to_actual_matches += 1

    # ActualArrivalInterval = gap between successive DIFFERENT trains' first
    # arrival event at this station (a real train-to-train headway, not
    # dwell-time-in-state noise from polling the same train repeatedly).
    ordered_firsts = sorted(first_arrival_by_train.values())
    actual_intervals = [
        (ordered_firsts[i] - ordered_firsts[i - 1]).total_seconds()
        for i in range(1, len(ordered_firsts))
        if (ordered_firsts[i] - ordered_firsts[i - 1]).total_seconds() > 0
    ]

    result = {
        "station": station,
        "polls": polls,
        "success": success,
        "error": error,
        "quota_exceeded_count": quota_exceeded,
        "quota_first_exceeded_at": quota_first_ts,
        "empty": empty,
        "total_arrival_rows": total_rows,
        "duplicate_recptn": duplicate,
        "out_of_order_recptn": out_of_order,
        "arvlCd_counts": dict(arvl_counts),
        "arvlCd_1_count": arvl_counts.get("1", 0),
        "distinct_trains_seen": len(per_train_sightings),
        "prediction_to_actual_match_count": pred_to_actual_matches,
        "actual_arrival_interval_count": len(actual_intervals),
    }
    if actual_intervals:
        s = sorted(actual_intervals)
        result["actual_arrival_interval_seconds"] = {
            "min": s[0],
            "p50": statistics.median(s),
            "p90": s[int(len(s) * 0.9) - 1] if len(s) >= 10 else s[-1],
            "max": s[-1],
        }
    return result


def analyze_position(line: str) -> dict:
    samples = load_samples("realtimePosition", line)
    polls = len(samples)
    success = 0
    error = 0
    quota_exceeded = 0
    quota_first_ts = None
    total_rows = 0
    train_nos = set()
    for s in samples:
        if s.get("error_code") is not None or s.get("http_status") != 200 or s.get("raw_payload") is None:
            error += 1
            continue
        try:
            raw = json.loads(s["raw_payload"])
        except Exception:
            error += 1
            continue
        if raw.get("code") == "ERROR-337" or "realtimePositionList" not in raw:
            quota_exceeded += 1
            if quota_first_ts is None:
                quota_first_ts = s.get("received_at")
            continue
        success += 1
        rows = raw.get("realtimePositionList") or []
        total_rows += len(rows)
        for row in rows:
            tn = row.get("trainNo")
            if tn:
                train_nos.add(tn)
    return {
        "line": line,
        "polls": polls,
        "success": success,
        "error": error,
        "quota_exceeded_count": quota_exceeded,
        "quota_first_exceeded_at": quota_first_ts,
        "total_position_rows": total_rows,
        "distinct_trains_seen": len(train_nos),
    }, train_nos


def main() -> None:
    arrival_results = {st: analyze_arrival(st) for st in STATIONS}
    position_results = {}
    position_train_sets = {}
    for line in LINES:
        res, trains = analyze_position(line)
        position_results[line] = res
        position_train_sets[line] = trains

    # A station name search (e.g. "교대") can return arrival rows for BOTH
    # of that station's line-specific nodes in one response (교대 has a
    # Line 2 side and a Line 3 side). Joining against a single line's
    # position feed requires filtering arrival rows to that line's
    # subwayId FIRST — otherwise the other line's trains dilute the join
    # rate and make it look worse than it is.
    SUBWAY_ID_TO_LINE = {"1002": "2호선", "1003": "3호선"}

    join = {}
    statn_ids_seen: dict[str, set[str]] = defaultdict(set)
    for st, ares in arrival_results.items():
        btrains_by_line: dict[str, set[str]] = defaultdict(set)
        samples = load_samples("realtimeStationArrival", st)
        for s in samples:
            if s.get("raw_payload") is None:
                continue
            try:
                raw = json.loads(s["raw_payload"])
            except Exception:
                continue
            for row in raw.get("realtimeArrivalList") or []:
                btrain = row.get("btrainNo")
                subway_id = row.get("subwayId")
                line_name = SUBWAY_ID_TO_LINE.get(subway_id)
                statn_id = row.get("statnId")
                if statn_id:
                    statn_ids_seen[f"{st}__{line_name or subway_id}"].add(statn_id)
                if btrain and line_name:
                    btrains_by_line[line_name].add(btrain)

        for line, trains in position_train_sets.items():
            btrains = btrains_by_line.get(line, set())
            if not btrains:
                continue
            overlap = btrains & trains
            join[f"{st}__{line}"] = {
                "arrival_distinct_trains_on_this_line": len(btrains),
                "position_distinct_trains": len(trains),
                "joined_trains": len(overlap),
                "join_rate_vs_arrival": (len(overlap) / len(btrains)) if btrains else None,
            }

    out = {
        "arrival": arrival_results,
        "position": position_results,
        "train_join": join,
        "statnId_crosswalk_observed": {k: sorted(v) for k, v in statn_ids_seen.items()},
    }
    (OUT / "metrics_raw.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2)[:3000])


if __name__ == "__main__":
    main()
