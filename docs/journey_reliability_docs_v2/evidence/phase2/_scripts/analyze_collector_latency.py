"""EV2-01 — request round-trip latency (received_at - requested_at) from
this session's real Phase 2 samples, now that both fields are captured at
the actual request boundary (PD-037 fix).

Usage:
    python analyze_collector_latency.py
"""
from __future__ import annotations

import json
import statistics
from datetime import datetime
from pathlib import Path

JR_DOCS = Path(__file__).resolve().parents[3]  # .../journey_reliability_docs_v2
SAMPLES = JR_DOCS / "baseline" / "phase0" / "data" / "samples"
TODAY = "2026-08-22"

TARGETS = [
    ("seoul_bus", "getArrInfoByRouteAll"),
    ("seoul_bus", "getBusPosByRouteSt"),
    ("seoul_subway", "realtimeStationArrival"),
    ("seoul_subway", "realtimePosition"),
]


def percentile(sorted_vals: list[float], p: float) -> float | None:
    if not sorted_vals:
        return None
    idx = min(len(sorted_vals) - 1, int(len(sorted_vals) * p))
    return sorted_vals[idx]


def main() -> None:
    report = {}
    for provider, api in TARGETS:
        d = SAMPLES / provider / api / TODAY
        if not d.exists():
            continue
        latencies = []
        collector_versions = set()
        for fp in d.glob("*.json"):
            with fp.open(encoding="utf-8") as f:
                rec = json.load(f)
            if rec.get("collector_version"):
                collector_versions.add(rec["collector_version"])
            if not rec.get("requested_at") or not rec.get("received_at"):
                continue
            req = datetime.fromisoformat(rec["requested_at"])
            rec_at = datetime.fromisoformat(rec["received_at"])
            latencies.append((rec_at - req).total_seconds())
        latencies.sort()
        report[f"{provider}/{api}"] = {
            "n": len(latencies),
            "collector_versions": sorted(collector_versions),
            "p50_sec": percentile(latencies, 0.50),
            "p95_sec": percentile(latencies, 0.95),
            "p99_sec": percentile(latencies, 0.99),
            "min_sec": latencies[0] if latencies else None,
            "max_sec": latencies[-1] if latencies else None,
            "zero_latency_count": sum(1 for v in latencies if v == 0.0),
        }

    out_path = Path(__file__).resolve().parent.parent / "EV2-01_COLLECTOR_TIMESTAMP" / "derived" / "latency_summary.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out_path}")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
