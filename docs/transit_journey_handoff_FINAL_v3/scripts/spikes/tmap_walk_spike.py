"""Spike — TMAP (SK Open API) Pedestrian Route API (access-time / final-walk leg).

STATUS: VERIFIED / GO (see docs/05_DECISION_LOG.md D-045). Kakao Mobility's
walking-directions API turned out to be BLOCKED - a partner-only product,
confirmed with a real 403 "permission denied" (D-043). This TMAP endpoint
is the replacement and it works: real GeoJSON pedestrian route returned
(HTTP 200, turn-by-turn geometry, totalDistance/totalTime).

GOTCHA (D-045): the first real call with a freshly-generated appKey
returned `403 INVALID_API_KEY` even though the key itself was valid.
Root cause: SK Open API separates "create an app (get an appKey)" from
"subscribe to a specific product" - the pedestrian-route product must be
subscribed to individually from the app's dashboard
(openapi.sk.com > Products > TMAP > TMAP 기능 > 경로 > 경로 안내 >
보행자 경로 안내) before that same appKey will work for this endpoint.
After subscribing, the identical key succeeded with no new key needed.

Same P0-1 note as kakao_walk_spike.py: this is a routing/geometry utility
for the WALK leg (Q2/D-039, Q3/D-040), not a transit reliability data
source, so it is not subject to the "Seoul data only" principle.

Documented pattern (per SK Open API docs found via WebSearch):
    POST https://apis.openapi.sk.com/tmap/routes/pedestrian?version=1
        Header: appKey: <TMAP_APP_KEY>
        Header: Accept: application/json
        Body (JSON): startX, startY, endX, endY, startName, endName (required)
                      passList, angle, speed, searchOption, sort, ... (optional)

Usage:
    python tmap_walk_spike.py <start_lon> <start_lat> <end_lon> <end_lat> [start_name] [end_name]
"""
from __future__ import annotations

import argparse

import requests

from common import storage
from common.env import require_key

BASE_URL = "https://apis.openapi.sk.com/tmap/routes/pedestrian"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("start_lon")
    parser.add_argument("start_lat")
    parser.add_argument("end_lon")
    parser.add_argument("end_lat")
    parser.add_argument("start_name", nargs="?", default="출발지")
    parser.add_argument("end_name", nargs="?", default="도착지")
    args = parser.parse_args()

    app_key = require_key("TMAP_APP_KEY")
    query_params = {"version": "1"}
    body = {
        "startX": args.start_lon,
        "startY": args.start_lat,
        "endX": args.end_lon,
        "endY": args.end_lat,
        "startName": args.start_name,
        "endName": args.end_name,
    }
    headers = {
        "appKey": app_key,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    sanitized_params = {**query_params, "body": body}

    try:
        resp = requests.post(BASE_URL, params=query_params, json=body, headers=headers, timeout=15)
        path = storage.record(
            storage.SpikeResult(
                provider="tmap",
                api_name="routes_pedestrian",
                request_params_sanitized=sanitized_params,
                http_status=resp.status_code,
                raw_payload=resp.text,
            )
        )
        print(f"saved {path.name} ({len(resp.text)} bytes)")
        print(f"HTTP {resp.status_code}")
        print(resp.text[:2000])
    except requests.RequestException as exc:
        storage.record(
            storage.SpikeResult(
                provider="tmap",
                api_name="routes_pedestrian",
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
