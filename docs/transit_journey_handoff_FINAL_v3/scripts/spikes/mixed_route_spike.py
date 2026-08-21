"""Spike C — Bus+Subway mixed transit route collector.

STATUS: fixed a real URL bug (see docs/05_DECISION_LOG.md D-024,
superseding D-019's "key not registered" theory). The operation is
*named* `getPathInfoByBusNSubList` in the data.go.kr catalog, but the
official 활용가이드 (docs/../.. /"api & data"/서울특별시_대중교통환승경로
조회 서비스_활용가이드_20211116.docx, already in this repo) shows the
real Call Back URL drops the "List" suffix, and the auth param is
capitalized `ServiceKey`, not `serviceKey`:

    GET http://ws.bus.go.kr/api/rest/pathinfo/getPathInfoByBusNSub
        ?ServiceKey=...&startX=...&startY=...&endX=...&endY=...&resultType=json

Hitting the wrong (nonexistent) `...List` path apparently falls through
to the gateway's generic "등록되지 않은 서비스키" 401 instead of a 404 —
easy to misread as a registration problem when it's actually a URL typo.
Same "List" bug applies to `getLocationInfoList` -> real URL
`.../getLocationInfo`.

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

BASE_URL = "http://ws.bus.go.kr/api/rest/pathinfo/getPathInfoByBusNSub"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("start_x")
    parser.add_argument("start_y")
    parser.add_argument("end_x")
    parser.add_argument("end_y")
    args = parser.parse_args()

    service_key = require_key("DATA_GO_TRANSIT_PATH_KEY")
    params = {
        "ServiceKey": service_key,
        "startX": args.start_x,
        "startY": args.start_y,
        "endX": args.end_x,
        "endY": args.end_y,
        "resultType": "json",
    }
    sanitized_params = {k: v for k, v in params.items() if k != "ServiceKey"}

    try:
        resp = requests.get(BASE_URL, params=params, timeout=15)
        path = storage.record(
            storage.SpikeResult(
                provider="seoul_bus",
                api_name="getPathInfoByBusNSub",
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
                api_name="getPathInfoByBusNSub",
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
