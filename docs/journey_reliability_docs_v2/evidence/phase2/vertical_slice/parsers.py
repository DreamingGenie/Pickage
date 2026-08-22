"""Raw -> canonical Observation/PredictionSnapshot parsers (EV2 vertical slice).

Bronze source: baseline/phase0/scripts/spikes/common/storage.py SpikeResult
JSON records (bus payloads are XML text inside raw_payload; subway payloads
are JSON text inside raw_payload - both providers' own quirk, not ours).

Field mapping follows docs/40_data_probability/41_OBSERVATION_ACTUAL_RESIDUAL.md
sections 2 and 5 exactly:
  - Bus prediction (SRC-SEOUL-003 getArrInfoByRouteAll): busRouteId, stId,
    staOrd, vehId1/vehId2, exps1/exps2, mkTm (call-level source time)
  - Subway prediction (SRC-SEOUL-001 realtimeStationArrival): subwayId,
    statnId, btrainNo, arvlCd, barvlDt (ETA seconds), recptnDt (source time,
    Asia/Seoul local, naive in the raw payload)
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from schema import Mode, Observation, ObservationMode, PredictionSnapshot

KST = timezone(timedelta(hours=9))  # Korea has no DST; fixed offset avoids a tzdata dependency

_ITEM_RE = re.compile(r"<itemList>(.*?)</itemList>", re.DOTALL)
_FIELD_RE = re.compile(r"<([a-zA-Z0-9_]+)>(.*?)</\1>")


def _parse_xml_items(payload: str) -> list[dict]:
    items = []
    for m in _ITEM_RE.finditer(payload):
        block = m.group(1)
        items.append({k: v for k, v in _FIELD_RE.findall(block)})
    return items


def iter_raw_records(directory: Path) -> Iterator[dict]:
    """Yield Bronze SpikeResult dicts from a data/samples/<provider>/<api>/<date>/ dir, requested_at order."""
    files = sorted(directory.glob("*.json"))
    for fp in files:
        with fp.open(encoding="utf-8") as f:
            yield json.load(f)


def _observation_id(record: dict) -> str:
    return f"obs-{record['provider']}-{record['api_name']}-{record['request_id']}"


# --- Bus -----------------------------------------------------------------


def bus_arrival_observation_and_predictions(
    record: dict, target_st_id: str | None = None
) -> tuple[Observation | None, list[PredictionSnapshot]]:
    if record.get("http_status") != 200 or not record.get("raw_payload"):
        return None, []
    payload = record["raw_payload"]
    items = _parse_xml_items(payload)
    if target_st_id is not None:
        items = [it for it in items if it.get("stId") == target_st_id]
    if not items:
        return None, []

    obs_id = _observation_id(record)
    mk_tm_raw = items[0].get("mkTm")  # "YYYY-MM-DD HH:MM:SS.f", call-level common source time
    source_generated_at = None
    if mk_tm_raw:
        try:
            source_generated_at = datetime.strptime(mk_tm_raw, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=KST)
        except ValueError:
            pass

    observation = Observation(
        observation_id=obs_id,
        provider=record["provider"],
        api_name=record["api_name"],
        mode=ObservationMode.BUS,
        entity_type="bus_arrival_prediction",
        entity_key=record["request_params_sanitized"].get("busRouteId", ""),
        source_generated_at=source_generated_at,
        requested_at=datetime.fromisoformat(record["requested_at"]),
        received_at=datetime.fromisoformat(record["received_at"]),
        payload_hash=record["raw_payload_hash"],
        raw_ref=str(record.get("request_id", "")),
        collector_version=record.get("collector_version", "unknown"),
    )

    predictions: list[PredictionSnapshot] = []
    for it in items:
        for slot in ("1", "2"):
            veh_id = it.get(f"vehId{slot}")
            if not veh_id or veh_id == "0":
                continue  # PD (41_OBSERVATION...) : vehId=0/no vehicle -> not a real prediction
            eta_raw = it.get(f"exps{slot}")
            try:
                eta_seconds = int(eta_raw) if eta_raw not in (None, "") else None
            except ValueError:
                eta_seconds = None
            predictions.append(
                PredictionSnapshot(
                    prediction_id=f"pred-{obs_id}-{it.get('stId')}-{slot}",
                    mode=Mode.BUS,
                    route_or_line_id=it.get("busRouteId", ""),
                    vehicle_or_train_id=veh_id,
                    target_node_id=it.get("stId", ""),
                    eta_seconds=eta_seconds,
                    source_generated_at=source_generated_at or observation.received_at,
                    received_at=observation.received_at,
                    observation_id=obs_id,
                )
            )
    return observation, predictions


def bus_position_events(record: dict) -> list[dict]:
    """Return raw {vehId, routeId, sectionId, sectOrd, stopFlag, dataTm(datetime)} rows."""
    if record.get("http_status") != 200 or not record.get("raw_payload"):
        return []
    items = _parse_xml_items(record["raw_payload"])
    out = []
    for it in items:
        data_tm_raw = it.get("dataTm")  # "YYYYMMDDHHMMSS"
        try:
            data_tm = datetime.strptime(data_tm_raw, "%Y%m%d%H%M%S").replace(tzinfo=KST)
        except (TypeError, ValueError):
            continue
        out.append(
            {
                "vehId": it.get("vehId"),
                "routeId": it.get("routeId"),
                "sectionId": it.get("sectionId"),
                "sectOrd": it.get("sectOrd"),
                "stopFlag": it.get("stopFlag"),
                "dataTm": data_tm,
                "observation_id": _observation_id(record),
            }
        )
    return out


# --- Subway ----------------------------------------------------------------


def subway_arrival_observation_and_predictions(
    record: dict,
) -> tuple[Observation | None, list[PredictionSnapshot]]:
    if record.get("http_status") != 200 or not record.get("raw_payload"):
        return None, []
    try:
        payload = json.loads(record["raw_payload"])
    except json.JSONDecodeError:
        return None, []
    items = payload.get("realtimeArrivalList") or []
    if not items:
        return None, []

    obs_id = _observation_id(record)
    observation = Observation(
        observation_id=obs_id,
        provider=record["provider"],
        api_name=record["api_name"],
        mode=ObservationMode.SUBWAY,
        entity_type="subway_arrival_prediction",
        entity_key=record["request_params_sanitized"].get("station", ""),
        requested_at=datetime.fromisoformat(record["requested_at"]),
        received_at=datetime.fromisoformat(record["received_at"]),
        payload_hash=record["raw_payload_hash"],
        raw_ref=str(record.get("request_id", "")),
        collector_version=record.get("collector_version", "unknown"),
    )

    predictions: list[PredictionSnapshot] = []
    for it in items:
        recptn_raw = it.get("recptnDt")
        try:
            source_generated_at = datetime.strptime(recptn_raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
        except (TypeError, ValueError):
            continue
        try:
            eta_seconds = int(it.get("barvlDt")) if it.get("barvlDt") not in (None, "") else None
        except ValueError:
            eta_seconds = None
        predictions.append(
            PredictionSnapshot(
                prediction_id=f"pred-{obs_id}-{it.get('statnId')}-{it.get('btrainNo')}",
                mode=Mode.SUBWAY,
                route_or_line_id=it.get("subwayId", ""),
                vehicle_or_train_id=it.get("btrainNo"),
                target_node_id=it.get("statnId", ""),
                eta_seconds=eta_seconds,
                source_generated_at=source_generated_at,
                received_at=observation.received_at,
                observation_id=obs_id,
                quality_flags=(["arvlCd=" + str(it.get("arvlCd"))]),
            )
        )
    return observation, predictions


def subway_arrival_state_events(record: dict) -> list[dict]:
    """Return raw {subwayId, statnId, btrainNo, arvlCd, recptnDt(datetime)} rows for Actual detection."""
    if record.get("http_status") != 200 or not record.get("raw_payload"):
        return []
    try:
        payload = json.loads(record["raw_payload"])
    except json.JSONDecodeError:
        return []
    out = []
    for it in payload.get("realtimeArrivalList") or []:
        try:
            recptn_dt = datetime.strptime(it["recptnDt"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
        except (KeyError, ValueError):
            continue
        out.append(
            {
                "subwayId": it.get("subwayId"),
                "statnId": it.get("statnId"),
                "btrainNo": it.get("btrainNo"),
                "arvlCd": it.get("arvlCd"),
                "recptnDt": recptn_dt,
                "observation_id": _observation_id(record),
            }
        )
    return out
