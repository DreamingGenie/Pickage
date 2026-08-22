"""EV2-02 — Quota-coordinated subway sustained collector.

PD-033 fix: Phase 1's SUBWAY_SUSTAINED run used 5 independent concurrent
processes hitting the same SEOUL_SUBWAY_REALTIME_KEY and reproduced
ERROR-337 (shared 1,000 calls/day quota) after ~22-33 real minutes,
instead of the intended 1 hour.

This script is a single process, single round-robin loop over all 5
Route A corridor targets (안국/교대/역삼 arrival name-search + 2호선/3호선
position), so the whole run consumes one coordinated, countable call
budget instead of 5 uncoordinated ones. It stops itself on:
  - a provider quota/business error (ERROR-337 or any errorMessage.code
    that is not INFO-000), tagged DQ-020 PROVIDER_QUOTA_EXCEEDED
  - reaching --max-calls (safety ceiling, default leaves quota headroom
    for other same-day work instead of spending 1000/1000)
  - reaching --duration-min wall-clock budget

Usage:
    python subway_sustained_coordinated.py --interval 20 --duration-min 30 --max-calls 900
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
from pathlib import Path

SPIKES_DIR = (
    Path(__file__).resolve().parents[3]  # .../journey_reliability_docs_v2
    / "baseline" / "phase0" / "scripts" / "spikes"
)
sys.path.insert(0, str(SPIKES_DIR))

import requests
from common import storage
from common.env import require_key

ARRIVAL_URL = "http://swopenAPI.seoul.go.kr/api/subway/{key}/json/realtimeStationArrival/0/20/{station}"
POSITION_URL = "http://swopenAPI.seoul.go.kr/api/subway/{key}/json/realtimePosition/0/{end}/{line}"

ARRIVAL_TARGETS = ["안국", "교대", "역삼"]
POSITION_TARGETS = [("2호선", 100), ("3호선", 100)]


def _quota_error_code(raw_payload: str) -> str | None:
    try:
        payload = json.loads(raw_payload)
    except (json.JSONDecodeError, TypeError):
        return None
    # Success responses nest the code under errorMessage.code; hard provider
    # errors (e.g. ERROR-337 daily quota) return it at the TOP level instead
    # (discovered live this session - Phase 1's own quota-check code only
    # checked the nested form and so never actually detected the quota hit
    # it happened to log around).
    code = payload.get("errorMessage", {}).get("code") or payload.get("code")
    if code and code != "INFO-000":
        return code
    return None


def poll_arrival(service_key: str, station_name: str, log: list[str]) -> str | None:
    url = ARRIVAL_URL.format(key=service_key, station=urllib.parse.quote(station_name))
    sanitized_params = {"station": station_name, "range": "0/20"}
    requested_at = storage.now_iso()
    try:
        resp = requests.get(url, timeout=10)
        received_at = storage.now_iso()
        quota_code = _quota_error_code(resp.text)
        path = storage.record(
            storage.SpikeResult(
                provider="seoul_subway",
                api_name="realtimeStationArrival",
                request_params_sanitized=sanitized_params,
                http_status=resp.status_code,
                raw_payload=resp.text,
                requested_at=requested_at,
                received_at=received_at,
                error_code=quota_code,
            )
        )
        log.append(f"[{time.strftime('%H:%M:%S')}] arrival/{station_name} saved {path.name}"
                    + (f" QUOTA_ERROR={quota_code}" if quota_code else ""))
        return quota_code
    except requests.RequestException as exc:
        received_at = storage.now_iso()
        storage.record(
            storage.SpikeResult(
                provider="seoul_subway",
                api_name="realtimeStationArrival",
                request_params_sanitized=sanitized_params,
                http_status=None,
                raw_payload=None,
                requested_at=requested_at,
                received_at=received_at,
                error_code=type(exc).__name__,
                error_body=str(exc),
            )
        )
        log.append(f"[{time.strftime('%H:%M:%S')}] arrival/{station_name} request failed: {exc}")
        return None


def poll_position(service_key: str, line_name: str, end_ord: int, log: list[str]) -> str | None:
    url = POSITION_URL.format(key=service_key, end=end_ord, line=urllib.parse.quote(line_name))
    sanitized_params = {"line": line_name, "range": f"0/{end_ord}"}
    requested_at = storage.now_iso()
    try:
        resp = requests.get(url, timeout=10)
        received_at = storage.now_iso()
        quota_code = _quota_error_code(resp.text)
        path = storage.record(
            storage.SpikeResult(
                provider="seoul_subway",
                api_name="realtimePosition",
                request_params_sanitized=sanitized_params,
                http_status=resp.status_code,
                raw_payload=resp.text,
                requested_at=requested_at,
                received_at=received_at,
                error_code=quota_code,
            )
        )
        log.append(f"[{time.strftime('%H:%M:%S')}] position/{line_name} saved {path.name}"
                    + (f" QUOTA_ERROR={quota_code}" if quota_code else ""))
        return quota_code
    except requests.RequestException as exc:
        received_at = storage.now_iso()
        storage.record(
            storage.SpikeResult(
                provider="seoul_subway",
                api_name="realtimePosition",
                request_params_sanitized=sanitized_params,
                http_status=None,
                raw_payload=None,
                requested_at=requested_at,
                received_at=received_at,
                error_code=type(exc).__name__,
                error_body=str(exc),
            )
        )
        log.append(f"[{time.strftime('%H:%M:%S')}] position/{line_name} request failed: {exc}")
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=int, default=20, help="seconds between full round-robin rounds")
    parser.add_argument("--duration-min", type=float, default=30.0, help="wall-clock budget in minutes")
    parser.add_argument("--max-calls", type=int, default=900, help="hard safety ceiling on total calls this run")
    args = parser.parse_args()

    service_key = require_key("SEOUL_SUBWAY_REALTIME_KEY")

    out_log = Path(__file__).resolve().parent.parent / "SUBWAY_SUSTAINED" / "run.log"
    out_log.parent.mkdir(parents=True, exist_ok=True)

    started = time.time()
    deadline = started + args.duration_min * 60
    total_calls = 0
    log_lines: list[str] = [f"started {time.strftime('%Y-%m-%d %H:%M:%S')} "
                             f"interval={args.interval}s duration_min={args.duration_min} max_calls={args.max_calls}"]

    stop_reason = "duration_reached"
    while True:
        if time.time() >= deadline:
            stop_reason = "duration_reached"
            break
        if total_calls >= args.max_calls:
            stop_reason = "max_calls_reached"
            break

        round_start = time.time()
        quota_hit = False
        for station in ARRIVAL_TARGETS:
            if total_calls >= args.max_calls:
                break
            code = poll_arrival(service_key, station, log_lines)
            total_calls += 1
            if code:
                quota_hit = True
                stop_reason = f"quota_error:{code}"
                break
        if not quota_hit:
            for line_name, end_ord in POSITION_TARGETS:
                if total_calls >= args.max_calls:
                    break
                code = poll_position(service_key, line_name, end_ord, log_lines)
                total_calls += 1
                if code:
                    quota_hit = True
                    stop_reason = f"quota_error:{code}"
                    break

        out_log.write_text("\n".join(log_lines) + "\n", encoding="utf-8")

        if quota_hit:
            break

        elapsed_this_round = time.time() - round_start
        sleep_left = max(0.0, args.interval - elapsed_this_round)
        if time.time() + sleep_left >= deadline:
            break
        time.sleep(sleep_left)

    total_elapsed_min = (time.time() - started) / 60
    log_lines.append(
        f"stopped {time.strftime('%Y-%m-%d %H:%M:%S')} reason={stop_reason} "
        f"total_calls={total_calls} elapsed_min={total_elapsed_min:.1f}"
    )
    out_log.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    print(f"done: reason={stop_reason} total_calls={total_calls} elapsed_min={total_elapsed_min:.1f}")


if __name__ == "__main__":
    main()
