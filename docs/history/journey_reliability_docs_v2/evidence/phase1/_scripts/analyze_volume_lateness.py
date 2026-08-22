"""Phase 1 analysis: EV-10 volume/lateness profile from this session's real collection.

Scans every Bronze-contract sample written today across all providers
and computes byte/observation volume and requested_at->received_at
latency (the only latency this harness can measure — no provider in
this package exposes a true source_generated_at, see README caveat).

Usage:
    python analyze_volume_lateness.py
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SAMPLES = ROOT / "docs" / "journey_reliability_docs_v2" / "baseline" / "phase0" / "data" / "samples"
OUT = Path(__file__).resolve().parents[1] / "VOLUME_LATENESS" / "derived"
OUT.mkdir(parents=True, exist_ok=True)


def iter_samples():
    for provider_dir in SAMPLES.iterdir():
        if not provider_dir.is_dir() or provider_dir.name == "examples":
            continue  # Phase 0 archived examples, not this session's new collection
        for api_dir in provider_dir.iterdir():
            if not api_dir.is_dir():
                continue
            for day_dir in api_dir.iterdir():
                if not day_dir.is_dir():
                    continue
                for f in day_dir.glob("*.json"):
                    try:
                        d = json.loads(f.read_text(encoding="utf-8"))
                    except Exception:
                        continue
                    yield provider_dir.name, api_dir.name, d


def main() -> None:
    per_key_bytes = defaultdict(int)
    per_key_count = defaultdict(int)
    latencies_ms = []
    negative_lateness = 0
    active_keys = set()
    error_count = 0

    for provider, api, d in iter_samples():
        key = f"{provider}/{api}"
        active_keys.add(key)
        per_key_count[key] += 1
        payload = d.get("raw_payload") or ""
        per_key_bytes[key] += len(payload.encode("utf-8"))
        if d.get("error_code") is not None:
            error_count += 1
            continue
        try:
            req = datetime.fromisoformat(d["requested_at"])
            recv = datetime.fromisoformat(d["received_at"])
        except Exception:
            continue
        delta_ms = (recv - req).total_seconds() * 1000
        latencies_ms.append(delta_ms)
        if delta_ms < 0:
            negative_lateness += 1

    total_obs = sum(per_key_count.values())
    total_bytes = sum(per_key_bytes.values())

    summary = {
        "total_samples": total_obs,
        "total_raw_bytes": total_bytes,
        "error_count": error_count,
        "active_keys": sorted(active_keys),
        "active_key_count": len(active_keys),
        "per_key_counts": dict(per_key_count),
        "per_key_bytes": dict(per_key_bytes),
        "collector_side_latency_ms_note": (
            "This is requested_at->received_at (collector round-trip), NOT "
            "received_at-source_generated_at. No API in this package exposes "
            "a true provider-side generation timestamp for every response, "
            "so the execution contract's exact 'received_at-source_generated_at' "
            "metric is NOT_AVAILABLE as specified; this is the closest real, "
            "measured proxy and is reported as such rather than substituted silently."
        ),
        "negative_lateness_count": negative_lateness,
        "collector_latency_near_zero_caveat": (
            "The inherited Phase 0 storage.SpikeResult dataclass stamps both "
            "requested_at and received_at via the same default_factory call at "
            "SpikeResult construction time, which happens AFTER requests.get()/"
            "post() already returned. So collector_latency_ms here measures "
            "~0 not because the network round-trip was instant, but because "
            "this harness never captured a pre-request timestamp. This is a "
            "harness limitation inherited from Phase 0, not a real finding "
            "about API speed."
        ),
    }
    if latencies_ms:
        s = sorted(latencies_ms)
        summary["collector_latency_ms"] = {
            "min": s[0],
            "p50": statistics.median(s),
            "p95": s[int(len(s) * 0.95) - 1] if len(s) >= 20 else s[-1],
            "p99": s[int(len(s) * 0.99) - 1] if len(s) >= 100 else s[-1],
            "max": s[-1],
        }

    (OUT / "volume_lateness_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
