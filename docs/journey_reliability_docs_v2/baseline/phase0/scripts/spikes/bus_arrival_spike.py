"""Spike A (part 1) — Bus Arrival prediction collector.

Endpoint confirmed live from data.go.kr service 15000314:
    GET http://ws.bus.go.kr/api/rest/arrive/getArrInfoByRouteAll
        ?serviceKey=...&busRouteId=<9-digit internal route id>

busRouteId is NOT the public route number (e.g. "753") — resolve it first
with resolve_bus_route.py.

Checklist fields to inspect once real samples land (see
docs/03_API_SPIKE_CHECKLIST.md section A):
  - vehId1/vehId2, exps1/exps2, mkTm, stId/staOrd
  - whether mkTm repeats across polls (duplicate source snapshot)
  - first/second bus semantics

Usage:
    python bus_arrival_spike.py <busRouteId> [--interval SECONDS] [--count N]
"""
from __future__ import annotations

import argparse
import time

import requests

from common import storage
from common.env import require_key

BASE_URL = "http://ws.bus.go.kr/api/rest/arrive/getArrInfoByRouteAll"


def poll_once(service_key: str, bus_route_id: str) -> None:
    params = {"serviceKey": service_key, "busRouteId": bus_route_id}
    sanitized_params = {k: v for k, v in params.items() if k != "serviceKey"}

    try:
        resp = requests.get(BASE_URL, params=params, timeout=10)
        path = storage.record(
            storage.SpikeResult(
                provider="seoul_bus",
                api_name="getArrInfoByRouteAll",
                request_params_sanitized=sanitized_params,
                http_status=resp.status_code,
                raw_payload=resp.text,
            )
        )
        print(f"[{time.strftime('%H:%M:%S')}] saved {path.name} ({len(resp.text)} bytes)")
    except requests.RequestException as exc:
        storage.record(
            storage.SpikeResult(
                provider="seoul_bus",
                api_name="getArrInfoByRouteAll",
                request_params_sanitized=sanitized_params,
                http_status=None,
                raw_payload=None,
                error_code=type(exc).__name__,
                error_body=str(exc),
            )
        )
        print(f"[{time.strftime('%H:%M:%S')}] request failed: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("bus_route_id", help="internal busRouteId (from resolve_bus_route.py)")
    parser.add_argument("--interval", type=int, default=30, help="seconds between polls")
    parser.add_argument("--count", type=int, default=1, help="number of polls (1 = single shot)")
    args = parser.parse_args()

    service_key = require_key("DATA_GO_BUS_API_KEY")

    for i in range(args.count):
        poll_once(service_key, args.bus_route_id)
        if i < args.count - 1:
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
