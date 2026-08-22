# VOLUME_LATENESS — Volume/Lateness Profile (EV-10)

**Status: CONDITIONAL** (real volume figures measured; the specified
lateness metric is `NOT_AVAILABLE` from this harness — see below, not
silently substituted)

Per the execution contract, partition/watermark/TTL are explicitly NOT
decided in this round — measurement only.

## Source data

This session's real new collection under
`baseline/phase0/data/samples/{seoul_subway,seoul_bus,tmap}/.../2026-08-22/`
(Phase 0's archived `examples/` subtree excluded — that is historical,
not this round's collection).

## Result — volume

| key | polls | raw bytes |
|---|---|---|
| `seoul_bus/getArrInfoByRouteAll` | 362 | 57,792,663 |
| `seoul_bus/getBusPosByRouteSt` | 361 | 422,869 |
| `seoul_subway/realtimePosition` | 481 | 2,464,025 |
| `seoul_subway/realtimeStationArrival` | 722 | 1,133,828 |
| `tmap/fullAddrGeo` | 1 | 959 |
| `tmap/routes_pedestrian` | 3 | 14,437 |
| **total** | **1,930** | **61,828,781 (~61.8 MB)** |

Collected over ~70 real minutes across this session (first call
03:37 UTC, last successful/quota-limited call ~04:52 UTC) →
**≈ 1,650 polls/hour, ≈ 53 MB/hour** combined across all 6 active
keys at this session's polling cadences (15–20 s intervals). Per-key
rates scale directly from the table above and each collector's known
interval.

`getArrInfoByRouteAll` dominates raw bytes (94% of total) because each
poll returns every stop on the route (~115 items for 01A, ~104 for
147), not just the 1–2 stops actually used — a real, measured
inefficiency of this endpoint's shape worth flagging for a production
collector design (filter client-side, or ask data.go.kr if a
per-stop-scoped variant exists).

Zero errors across all 1,930 samples in this file (the subway quota
errors are recorded under `SUBWAY_SUSTAINED`'s own samples, which are
excluded from `seoul_subway/*` counts here only in the sense that they
ARE counted as samples — `error_count: 0` reflects that `ERROR-337`
responses are well-formed HTTP 200 payloads, not transport errors; see
`SUBWAY_SUSTAINED/README.md` for the quota-specific breakdown).

## Result — lateness

**`received_at - source_generated_at`: `NOT_AVAILABLE`.** No API in
this package (TMAP, Seoul bus, Seoul subway realtime) exposes a
provider-side response-generation timestamp in every payload that this
harness can extract generically. Subway responses do carry `recptnDt`
per-row (used in `SUBWAY_SUSTAINED`'s own interval analysis), but that
is not the same as a request-level generation timestamp, and bus/TMAP
responses carry no equivalent field at all. Per the execution
contract's explicit instruction not to invent figures, this metric is
reported as unavailable rather than approximated from a different
field without saying so.

**`collector_latency_ms` (requested_at→received_at) measured ~0 for
all samples — this is a harness artifact, not a finding.** The
inherited Phase 0 `storage.SpikeResult` dataclass stamps both
timestamps from the same `default_factory` call made *after* the HTTP
request already completed, so this number cannot show real network
latency. Documented so nobody downstream mistakes "0 ms" for "the API
is instant."

**Negative lateness / out-of-order: 0** (meaningless here for the same
harness-artifact reason above — not a real absence-of-out-of-order
finding).

## Artifacts

- `derived/volume_lateness_summary.json`

## Reproduction

```bash
python docs/journey_reliability_docs_v2/evidence/phase1/_scripts/analyze_volume_lateness.py
```

## Recommendation for a real Phase 2 collector

If a true `source_generated_at`→`received_at` lateness metric is
needed, the collector itself must timestamp immediately before sending
the request (not after constructing the result object), and the
subway API's `recptnDt` should be treated as the closest thing to a
provider timestamp available today — but it is per-row, not
per-response, and bus/TMAP have no equivalent at all.
