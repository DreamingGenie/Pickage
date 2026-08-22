"""One-off Phase 1 helper: TMAP full-address geocoding for EV-04 destination.

Not part of the Phase 0 spike harness; reuses its common/storage + env
modules by adding that directory to sys.path. Records the raw response
using the same Bronze-contract writer as the other spikes so it lands in
baseline/phase0/data/samples/tmap/fullAddrGeo/<date>/ alongside everything
else, and is then copied into evidence/phase1/EVD-DEST-001/raw/.

Usage:
    python tmap_geocode.py "<full address>"
"""
from __future__ import annotations

import sys
from pathlib import Path

SPIKES_DIR = Path(__file__).resolve().parents[3] / "docs" / "journey_reliability_docs_v2" / "baseline" / "phase0" / "scripts" / "spikes"
sys.path.insert(0, str(SPIKES_DIR))

import requests
from common import storage
from common.env import require_key

BASE_URL = "https://apis.openapi.sk.com/tmap/geo/fullAddrGeo"


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python tmap_geocode.py \"<full address>\"")
        sys.exit(1)
    full_addr = sys.argv[1]

    app_key = require_key("TMAP_APP_KEY")
    params = {
        "version": "1",
        "addressFlag": "F00",
        "fullAddr": full_addr,
        "coordType": "WGS84GEO",
        "format": "json",
    }
    headers = {"appKey": app_key, "Accept": "application/json"}
    sanitized_params = dict(params)

    requested_at = storage.now_iso()
    try:
        resp = requests.get(BASE_URL, params=params, headers=headers, timeout=15)
        received_at = storage.now_iso()
        path = storage.record(
            storage.SpikeResult(
                provider="tmap",
                api_name="fullAddrGeo",
                request_params_sanitized=sanitized_params,
                http_status=resp.status_code,
                raw_payload=resp.text,
                requested_at=requested_at,
                received_at=received_at,
            )
        )
        print(f"saved {path}")
        print(f"HTTP {resp.status_code}")
        print(resp.text[:3000])
    except requests.RequestException as exc:
        received_at = storage.now_iso()
        storage.record(
            storage.SpikeResult(
                provider="tmap",
                api_name="fullAddrGeo",
                request_params_sanitized=sanitized_params,
                http_status=None,
                raw_payload=None,
                requested_at=requested_at,
                received_at=received_at,
                error_code=type(exc).__name__,
                error_body=str(exc),
            )
        )
        print(f"request failed: {exc}")


if __name__ == "__main__":
    main()
