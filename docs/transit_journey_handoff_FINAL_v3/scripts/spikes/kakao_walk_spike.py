"""Spike — Kakao Mobility Walking Directions API (access-time / final-walk leg).

STATUS: TO_VERIFY. Added per PM decisions Q2/Q3 (docs/05_DECISION_LOG.md
D-039/D-040): Journey "arrival" now includes the final walk to the actual
destination, and access/walking time should come from a real routing API
(Kakao Map) rather than user input or a fixed demo value.

IMPORTANT — this is NOT covered by the P0-1 "Seoul data only" principle
(D-040): it is a routing/geometry utility, not a transit reliability data
source, so it is fine to use a non-Seoul, non-government provider here.

KNOWN RISK (found via WebSearch/WebFetch before this key ever existed —
see docs/05_DECISION_LOG.md D-042): Kakao Mobility's own documentation at
https://developers.kakaomobility.com/affiliate/walking/directions
describes this as a "partner-only" API requiring a prior partnership
agreement - a plain Kakao Developers REST API key may NOT be sufficient
on its own, unlike the Local API (place search) which works with any
REST key. Do not assume success from the docs; this script exists to
find out for real, exactly like the mixed-route "...List" 401 saga
(D-019/D-024) taught us to.

Documented pattern (per Kakao Mobility Developers docs):
    GET https://apis-navi.kakaomobility.com/affiliate/walking/v1/directions
        ?origin=<lon,lat>&destination=<lon,lat>[&waypoints=...][&priority=DISTANCE|MAIN_STREET]
        Header: Authorization: KakaoAK <REST_API_KEY>

Usage:
    python kakao_walk_spike.py <origin_lon> <origin_lat> <dest_lon> <dest_lat>
"""
from __future__ import annotations

import argparse

import requests

from common import storage
from common.env import require_key

BASE_URL = "https://apis-navi.kakaomobility.com/affiliate/walking/v1/directions"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("origin_lon")
    parser.add_argument("origin_lat")
    parser.add_argument("dest_lon")
    parser.add_argument("dest_lat")
    args = parser.parse_args()

    service_key = require_key("KAKAO_MAP_REST_API_KEY")
    params = {
        "origin": f"{args.origin_lon},{args.origin_lat}",
        "destination": f"{args.dest_lon},{args.dest_lat}",
    }
    headers = {"Authorization": f"KakaoAK {service_key}"}
    # Nothing secret in params themselves, but the Authorization header
    # must never be logged/stored - storage.record only ever receives params.

    try:
        resp = requests.get(BASE_URL, params=params, headers=headers, timeout=15)
        path = storage.record(
            storage.SpikeResult(
                provider="kakao_mobility",
                api_name="walking_directions",
                request_params_sanitized=params,
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
                provider="kakao_mobility",
                api_name="walking_directions",
                request_params_sanitized=params,
                http_status=None,
                raw_payload=None,
                error_code=type(exc).__name__,
                error_body=str(exc),
            )
        )
        print(f"request failed: {exc}")


if __name__ == "__main__":
    main()
