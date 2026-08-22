# Observation Contract

> How raw API responses map onto the Bronze storage contract from
> `../01_PROJECT_HANDOFF.md` section 9, annotated with what live Spike
> calls actually confirmed. The canonical `PredictionSnapshot` /
> `ActualArrivalInterval` / `ResidualEvent` schemas in that document
> (section 10) are still design candidates — this file only fixes the
> parts that real data has already settled.

## Bronze fields (implemented in `../../scripts/spikes/common/storage.py`)

Every spike script already writes: `provider, api_name, request_id,
requested_at, received_at, http_status, request_params_sanitized,
raw_payload, raw_payload_hash, source_timestamp, collector_version,
error_code, error_body`. `source_timestamp` is currently left `null` by
the spike scripts (they store the full raw payload; per-item timestamp
extraction is a parsing step for the Silver layer, not something the
Bronze writer should do).

## `source_generated_at` semantics — confirmed per API

This is the field most likely to be gotten wrong if assumed uniform
across providers. Confirmed from real samples:

| API | Timestamp field | Granularity | Evidence |
|---|---|---|---|
| Bus arrival (`getArrInfoByRouteAll`) | `mkTm` | **Per call** — every item (stop) in one response shares the same value | 104-item sample, 1 unique `mkTm` |
| Bus position (`getBusPosByRouteSt`) | `dataTm` | **Per vehicle** — differs by a few seconds between vehicles in the same response | 13-item sample, distinct `dataTm` per item |
| Subway arrival (`realtimeStationArrival`) | `recptnDt` | **Per train** — differs between items in the same response | 서울역/시청 samples, distinct `recptnDt` per item |
| Subway position (`realtimePosition`) | `recptnDt` (+ `lastRecptnDt` date-only) | **Per train** | Line 1 sample, distinct `recptnDt` per item |

Implication: a Silver-layer normalizer cannot use one "response received
→ one timestamp" rule for bus arrival the way it can for the other
three. Bus arrival's real observation unit is the response batch, not
the individual stop prediction, for timestamp purposes (each stop
prediction is still a distinct observation for join purposes — only the
timestamp is shared).

## Actual-arrival candidate rules — status

- **Bus**: `stopFlag` 0→1 transition (checklist's original candidate) —
  both values observed in one snapshot, transition not yet observed
  across polls. Still the leading candidate, not yet confirmed.
- **Subway**: `arvlCd` state sequence `99 → {5,4,3,2} → 0 → 1 → 2`
  (richer than the checklist's original `0→1→2`/`99` candidate — see
  D-021), confirmed with the same relative ordering on three independent
  lines (1, 2, 3 — D-034). `arvlCd=1` (도착/arrived) is the Actual event
  trigger. **Drafted as `SUBWAY_ACTUAL_RULE_V0.md`, status CONDITIONAL** —
  safe for the demo corridor's stations (all 100% join), but one Line 2
  station/platform code (`1002000201`) has a persistent, unexplained
  ~45% non-join rate (D-026/D-032/D-033) that blocks calling this
  citywide-reliable yet.

## Duplicate / empty / error — not yet characterized

All single-snapshot smoke tests so far returned HTTP 200 with non-empty
bodies. Duplicate-snapshot ratio, empty-response rate, and error rate
under sustained polling are open — see `QUALITY_FLAGS.md` "still to
characterize."
