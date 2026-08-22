"""Spike B (part 2) — Subway real-time train position collector.

STATUS: VERIFIED (see docs/05_DECISION_LOG.md D-016/D-017/D-023).
Confirmed live with a real key. `trainNo` here direct-matched `btrainNo`
from realtimeStationArrival for the same station (시청/Line 1) — the
project's most critical open risk.

IMPORTANT — pagination: the response reports `totalCount` (Line 1 was
seen fluctuating 46-53 active trains). Requesting a fixed `0/20` window,
as an earlier version of this script did, silently truncates the fleet
and produces a spurious join-rate gap that looks like a data-quality
problem but isn't one (see D-023). Default range here is `0/100` to
comfortably exceed any single line's fleet; a production collector
should read `totalCount` from the response and adjust its own range
rather than hardcoding a ceiling.

Confirmed pattern:
    GET http://swopenAPI.seoul.go.kr/api/subway/<KEY>/json/realtimePosition/<startIndex>/<endIndex>/<lineName>

Checklist fields to inspect (docs/03_API_SPIKE_CHECKLIST.md section E):
  - train number field, line, direction, current station/position,
    train status sequence, destination, source timestamp
  - join rate against realtimeStationArrival's btrainNo

Usage:
    python subway_position_spike.py <호선명, e.g. 1호선> [--interval S] [--count N] [--end-ord N]
"""
from __future__ import annotations

import argparse
import time
import urllib.parse

import requests

from common import storage
from common.env import require_key

BASE_URL_TEMPLATE = "http://swopenAPI.seoul.go.kr/api/subway/{key}/json/realtimePosition/0/{end}/{line}"


def poll_once(service_key: str, line_name: str, end_ord: int) -> None:
    url = BASE_URL_TEMPLATE.format(
        key=service_key, end=end_ord, line=urllib.parse.quote(line_name)
    )
    sanitized_params = {"line": line_name, "range": f"0/{end_ord}"}

    requested_at = storage.now_iso()
    try:
        resp = requests.get(url, timeout=10)
        received_at = storage.now_iso()
        path = storage.record(
            storage.SpikeResult(
                provider="seoul_subway",
                api_name="realtimePosition",
                request_params_sanitized=sanitized_params,
                http_status=resp.status_code,
                raw_payload=resp.text,
                requested_at=requested_at,
                received_at=received_at,
            )
        )
        print(f"[{time.strftime('%H:%M:%S')}] saved {path.name} ({len(resp.text)} bytes)")
    except requests.RequestException as exc:
        received_at = storage.now_iso()
        storage.record(
            storage.SpikeResult(
                provider="seoul_subway",
                api_name="realtimePosition",
                request_params_sanitized=sanitized_params,
                http_status=None,
                raw_payload=None,
                requested_at=requested_at,
                received_at=received_at,
                error_code=type(exc).__name__,
                error_body=str(exc),
            )
        )
        print(f"[{time.strftime('%H:%M:%S')}] request failed: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("line_name")
    parser.add_argument("--interval", type=int, default=15)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--end-ord", type=int, default=100,
                         help="upper bound of the index range; must exceed the line's totalCount (D-023)")
    args = parser.parse_args()

    service_key = require_key("SEOUL_SUBWAY_REALTIME_KEY")

    for i in range(args.count):
        poll_once(service_key, args.line_name, args.end_ord)
        if i < args.count - 1:
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
