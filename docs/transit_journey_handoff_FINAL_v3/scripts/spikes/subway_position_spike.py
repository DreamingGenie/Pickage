"""Spike B (part 2) — Subway real-time train position collector.

STATUS: HYPOTHESIS / TO_VERIFY (see subway_arrival_spike.py docstring for
why). Assumed pattern, same API family as station arrival:

    GET http://swopenAPI.seoul.go.kr/api/subway/<KEY>/json/realtimePosition/<startIndex>/<endIndex>/<lineName>

Checklist fields to inspect (docs/03_API_SPIKE_CHECKLIST.md section E):
  - train number field, line, direction, current station/position,
    train status sequence, destination, source timestamp
  - join rate against realtimeStationArrival's btrainNo

Usage:
    python subway_position_spike.py <호선명, e.g. 1호선> [--interval S] [--count N]
"""
from __future__ import annotations

import argparse
import time
import urllib.parse

import requests

from common import storage
from common.env import require_key

BASE_URL_TEMPLATE = "http://swopenAPI.seoul.go.kr/api/subway/{key}/json/realtimePosition/0/20/{line}"


def poll_once(service_key: str, line_name: str) -> None:
    url = BASE_URL_TEMPLATE.format(key=service_key, line=urllib.parse.quote(line_name))
    sanitized_params = {"line": line_name, "range": "0/20"}

    try:
        resp = requests.get(url, timeout=10)
        path = storage.record(
            storage.SpikeResult(
                provider="seoul_subway",
                api_name="realtimePosition",
                request_params_sanitized=sanitized_params,
                http_status=resp.status_code,
                raw_payload=resp.text,
            )
        )
        print(f"[{time.strftime('%H:%M:%S')}] saved {path.name} ({len(resp.text)} bytes)")
    except requests.RequestException as exc:
        storage.record(
            storage.SpikeResult(
                provider="seoul_subway",
                api_name="realtimePosition",
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
    parser.add_argument("line_name")
    parser.add_argument("--interval", type=int, default=15)
    parser.add_argument("--count", type=int, default=1)
    args = parser.parse_args()

    service_key = require_key("SEOUL_SUBWAY_REALTIME_KEY")

    for i in range(args.count):
        poll_once(service_key, args.line_name)
        if i < args.count - 1:
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
