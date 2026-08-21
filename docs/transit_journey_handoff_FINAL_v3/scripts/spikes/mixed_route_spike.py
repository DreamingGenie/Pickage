"""Spike C — Bus+Subway mixed transit route collector.

STATUS: BLOCKED (see docs/05_DECISION_LOG.md D-019). Both operations on
this endpoint (getPathInfoByBusNSubList and the simpler
getLocationInfoList) returned HTTP 401 "등록되지 않은 서비스키" with the
real DATA_GO_TRANSIT_PATH_KEY — not a code/param bug, the key is not
approved/registered for THIS specific data.go.kr service (15000414) yet,
even though the bus arrival/position keys worked fine. Apply separately
for this service on data.go.kr before retrying.

Endpoint confirmed live from data.go.kr service 15000414:
    GET http://ws.bus.go.kr/api/rest/pathinfo/getPathInfoByBusNSubList
        ?serviceKey=...&startX=...&startY=...&endX=...&endY=...

The listing page documents four operations: getLocationInfoList (POI
search), getPathInfoByBusList, getPathInfoBySubwayList,
getPathInfoByBusNSubList (bus+subway mixed — the one this project needs).
Exact param names for X/Y coordinates are TO_VERIFY against the actual
response; adjust once a real key confirms the schema.

Checklist to fill in (docs/03_API_SPIKE_CHECKLIST.md section G):
  - alternative routes returned?
  - bus route id / stop id present and joinable with bus master?
  - subway line/station id present and joinable with realtime subway API?
  - walking/transfer time fields?
  - static vs realtime timing?

Usage:
    python mixed_route_spike.py <startX> <startY> <endX> <endY>
"""
from __future__ import annotations

import argparse

import requests

from common import storage
from common.env import require_key

BASE_URL = "http://ws.bus.go.kr/api/rest/pathinfo/getPathInfoByBusNSubList"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("start_x")
    parser.add_argument("start_y")
    parser.add_argument("end_x")
    parser.add_argument("end_y")
    args = parser.parse_args()

    service_key = require_key("DATA_GO_TRANSIT_PATH_KEY")
    params = {
        "serviceKey": service_key,
        "startX": args.start_x,
        "startY": args.start_y,
        "endX": args.end_x,
        "endY": args.end_y,
    }
    sanitized_params = {k: v for k, v in params.items() if k != "serviceKey"}

    try:
        resp = requests.get(BASE_URL, params=params, timeout=15)
        path = storage.record(
            storage.SpikeResult(
                provider="seoul_bus",
                api_name="getPathInfoByBusNSubList",
                request_params_sanitized=sanitized_params,
                http_status=resp.status_code,
                raw_payload=resp.text,
            )
        )
        print(f"saved {path.name} ({len(resp.text)} bytes)")
        print(resp.text[:2000])
    except requests.RequestException as exc:
        storage.record(
            storage.SpikeResult(
                provider="seoul_bus",
                api_name="getPathInfoByBusNSubList",
                request_params_sanitized=sanitized_params,
                http_status=None,
                raw_payload=None,
                error_code=type(exc).__name__,
                error_body=str(exc),
            )
        )
        print(f"request failed: {exc}")


if __name__ == "__main__":
    main()
