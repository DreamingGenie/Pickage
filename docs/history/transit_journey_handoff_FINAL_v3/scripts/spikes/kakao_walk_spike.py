"""Spike — Kakao Mobility Walking Directions API (access-time / final-walk leg).

STATUS: BLOCKED (see docs/05_DECISION_LOG.md D-043). Tested live with a
real Kakao Developers REST API key: HTTP 403
`{"code":-5,"msg":"permission denied"}`. This confirmed the risk flagged
in D-042 before ever having a key: Kakao Mobility's own documentation at
https://developers.kakaomobility.com/affiliate/walking/directions
describes this as a "partner-only" API requiring a prior partnership
agreement - a plain Kakao Developers REST API key is NOT sufficient,
unlike the Local API (place search) which works with any REST key.

This is NOT an IP-allowlist problem (Kakao Developers' optional "호출
허용 IP 주소" setting under [내 애플리케이션]>[앱 설정]>[플랫폼] is a
separate, unrelated security feature - leaving it blank allows any IP).
The 403 here is a hard product/partnership gate, unaffected by IP config.

Kept in the repo (not deleted) in case a Kakao Mobility partnership is
approved later - see kakao_walk_spike.py in that case. For now, see
tmap_walk_spike.py for the live alternative (D-044).

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
