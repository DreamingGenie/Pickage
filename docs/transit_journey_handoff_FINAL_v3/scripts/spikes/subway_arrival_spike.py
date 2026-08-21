"""Spike B (part 1) — Subway real-time arrival collector.

STATUS: VERIFIED (see docs/05_DECISION_LOG.md D-016). Confirmed live with
a real key: HTTP 200, code=INFO-000. Real response fields match the
checklist closely, plus extras (trainLineNm, arvlMsg3, ordkey, subwayList,
statnList, trnsitCo). Observed arvlCd values: 0=entering, 1=arrived,
2=departed, 99=en route (see D-018).

Confirmed pattern:
    GET http://swopenAPI.seoul.go.kr/api/subway/<KEY>/json/realtimeStationArrival/<startIndex>/<endIndex>/<stationName>

Checklist fields to inspect (docs/03_API_SPIKE_CHECKLIST.md section D):
  - subwayId, updnLine, statnId, statnNm, barvlDt, btrainNo, btrainSttus,
    bstatnId, bstatnNm, recptnDt, arvlMsg2, arvlCd, lstcarAt
  - whether recptnDt repeats across polls

Usage:
    python subway_arrival_spike.py <역명, e.g. 서울역> [--interval S] [--count N]
"""
from __future__ import annotations

import argparse
import time
import urllib.parse

import requests

from common import storage
from common.env import require_key

BASE_URL_TEMPLATE = "http://swopenAPI.seoul.go.kr/api/subway/{key}/json/realtimeStationArrival/0/20/{station}"


def poll_once(service_key: str, station_name: str) -> None:
    url = BASE_URL_TEMPLATE.format(
        key=service_key, station=urllib.parse.quote(station_name)
    )
    sanitized_params = {"station": station_name, "range": "0/20"}

    try:
        resp = requests.get(url, timeout=10)
        path = storage.record(
            storage.SpikeResult(
                provider="seoul_subway",
                api_name="realtimeStationArrival",
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
                api_name="realtimeStationArrival",
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
    parser.add_argument("station_name")
    parser.add_argument("--interval", type=int, default=15)
    parser.add_argument("--count", type=int, default=1)
    args = parser.parse_args()

    service_key = require_key("SEOUL_SUBWAY_REALTIME_KEY")

    for i in range(args.count):
        poll_once(service_key, args.station_name)
        if i < args.count - 1:
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
