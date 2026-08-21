"""Spike A (part 2) — Bus Position collector.

DECISION LOG NOTE (see docs/05_DECISION_LOG.md D-011): the team's original
checklist assumed `getBusPosByRtid`/`getBusPosByRtidList`. The endpoint
actually documented live on data.go.kr service 15000332 is:

    GET http://ws.bus.go.kr/api/rest/buspos/getBusPosByRouteSt
        ?serviceKey=...&busRouteId=<9-digit id>&startOrd=<int>&endOrd=<int>

startOrd/endOrd (stop sequence range) are required — not just busRouteId.
Use resolve_bus_route.py / the route master API to find a route's stop
count if startOrd=1 / endOrd=<last stop> is not already known.

STATUS: VERIFIED (see docs/05_DECISION_LOG.md D-013/D-014). Real fields
observed: busType, congetion (sic — real API typo, not ours), dataTm,
isFullFlag, lastStnId, plainNo, posX/posY, routeId, sectDist, sectOrd,
sectionId, stopFlag, tmX/tmY, vehId. `nextStId`/`nextStTm`/`rtDist` from
the checklist are NOT present in the response.

Checklist fields to inspect (docs/03_API_SPIKE_CHECKLIST.md section B):
  - vehId, sectOrd, sectionId, stopFlag, nextStId, nextStTm, dataTm
  - vehId1/vehId2 (arrival) vs vehId (position) join rate — CONFIRMED
    direct match on first live sample (route 753, vehId 111033105)

Usage:
    python bus_position_spike.py <busRouteId> <startOrd> <endOrd> [--interval S] [--count N]
"""
from __future__ import annotations

import argparse
import time

import requests

from common import storage
from common.env import require_key

BASE_URL = "http://ws.bus.go.kr/api/rest/buspos/getBusPosByRouteSt"


def poll_once(service_key: str, bus_route_id: str, start_ord: str, end_ord: str) -> None:
    params = {
        "serviceKey": service_key,
        "busRouteId": bus_route_id,
        "startOrd": start_ord,
        "endOrd": end_ord,
    }
    sanitized_params = {k: v for k, v in params.items() if k != "serviceKey"}

    try:
        resp = requests.get(BASE_URL, params=params, timeout=10)
        path = storage.record(
            storage.SpikeResult(
                provider="seoul_bus",
                api_name="getBusPosByRouteSt",
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
                api_name="getBusPosByRouteSt",
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
    parser.add_argument("bus_route_id")
    parser.add_argument("start_ord")
    parser.add_argument("end_ord")
    parser.add_argument("--interval", type=int, default=30)
    parser.add_argument("--count", type=int, default=1)
    args = parser.parse_args()

    service_key = require_key("DATA_GO_BUS_POSITION_KEY")

    for i in range(args.count):
        poll_once(service_key, args.bus_route_id, args.start_ord, args.end_ord)
        if i < args.count - 1:
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
