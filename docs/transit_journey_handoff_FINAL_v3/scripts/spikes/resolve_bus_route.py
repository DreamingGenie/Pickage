"""Look up a bus route's internal busRouteId from its public route number.

Endpoint confirmed live on data.go.kr's overview page for service 15000193
(base path only, exact response fields TO_VERIFY with a real key):

    GET http://ws.bus.go.kr/api/rest/busRouteInfo/getBusRouteList
        ?serviceKey=...&strSrch=<route number, e.g. 753>

Usage:
    python resolve_bus_route.py 753
"""
from __future__ import annotations

import sys

import requests

from common import storage
from common.env import require_key

BASE_URL = "http://ws.bus.go.kr/api/rest/busRouteInfo/getBusRouteList"


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python resolve_bus_route.py <route-number, e.g. 753>")
        sys.exit(1)
    route_number = sys.argv[1]

    service_key = require_key("DATA_GO_BUS_ROUTE_KEY")
    params = {"serviceKey": service_key, "strSrch": route_number}
    sanitized_params = {k: v for k, v in params.items() if k != "serviceKey"}

    resp = requests.get(BASE_URL, params=params, timeout=10)

    path = storage.record(
        storage.SpikeResult(
            provider="seoul_bus",
            api_name="getBusRouteList",
            request_params_sanitized=sanitized_params,
            http_status=resp.status_code,
            raw_payload=resp.text,
        )
    )
    print(f"Saved raw sample: {path}")
    print(resp.text[:2000])


if __name__ == "__main__":
    main()
