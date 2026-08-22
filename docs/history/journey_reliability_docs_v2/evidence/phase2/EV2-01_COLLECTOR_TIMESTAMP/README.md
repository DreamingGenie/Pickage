# EV2-01 — Collector Timestamp Repair

**Status: VERIFIED (fix applied and confirmed live).**

## The bug (PD-037)

`baseline/phase0/scripts/spikes/common/storage.py`'s `SpikeResult`
defaulted `requested_at`/`received_at` to `field(default_factory=lambda:
_now_iso())` independently — both fields got the wall-clock time at
`SpikeResult(...)` construction, which happens **after** `requests.get(...)`
already returned. Phase 1's own volume/lateness analysis caught this
indirectly (`received_at - requested_at` was always ~0 ms), but never fixed
the root cause; this round does.

## The fix

- `SpikeResult.requested_at`/`received_at` are now **required constructor
  args with no default** — a caller that doesn't supply them fails loudly
  at call time instead of silently reproducing the bug.
- Every one of the 9 call sites in `baseline/phase0/scripts/spikes/`
  (`bus_arrival_spike.py`, `bus_position_spike.py`,
  `subway_arrival_spike.py`, `subway_position_spike.py`,
  `tmap_walk_spike.py`, `resolve_bus_route.py`, `mixed_route_spike.py`,
  `kakao_walk_spike.py`) plus `evidence/phase1/_scripts/tmap_geocode.py`
  now call `storage.now_iso()` immediately before `requests.get`/`.post`
  for `requested_at`, and again immediately after the call returns (in
  both the success and `except requests.RequestException` branches) for
  `received_at`.
- `COLLECTOR_VERSION` bumped to `spike-v1-ev2-01` so old (`spike-v0`) and
  new samples are distinguishable in any downstream analysis.

## Live confirmation

Real request round-trip latency (`received_at - requested_at`), this
session's own Phase 2 samples, all `collector_version=spike-v1-ev2-01`:

| Provider/API | n | p50 | p95 | p99 | min | max |
|---|---|---|---|---|---|---|
| Bus `getArrInfoByRouteAll` | 180 | 64 ms | 160 ms | 449 ms | 14 ms | 752 ms |
| Bus `getBusPosByRouteSt` | 180 | 43 ms | 101 ms | 381 ms | 5 ms | 384 ms |
| Subway `realtimeStationArrival` | 172 | 24 ms | 36 ms | 51 ms | 5 ms | 222 ms |
| Subway `realtimePosition` | 114 | 23 ms | 32 ms | 35 ms | 6 ms | 39 ms |

**Zero 0 ms samples across all 646 real calls** (Phase 1's entire dataset
was 0 ms). The bus arrival endpoint's noticeably higher p99 (449–752 ms
vs subway's <220 ms max) is itself a real, previously invisible signal —
`getArrInfoByRouteAll` returns the whole route's stops per call (documented
as 94% of Phase 1's raw bytes in `VOLUME_LATENESS`), so its larger response
size plausibly explains the higher tail latency; not confirmed against a
controlled single-stop comparison this round.

`received_at - source_generated_at` (the other half of PD-037/`EV2-01`)
was **not** computed this round: `mkTm`/`recptnDt` describe provider-side
generation time in the provider's own clock, and no NTP-offset check
between this machine's clock and the provider's was performed, so a naive
subtraction would silently blend real network+processing latency with
unverified clock skew. Flagged as a real remaining gap, not computed with
an unstated assumption.

## Artifacts

- `../_scripts/analyze_collector_latency.py`
- `derived/latency_summary.json`
- Fixed source: `baseline/phase0/scripts/spikes/common/storage.py`,
  `baseline/phase0/scripts/spikes/*_spike.py`,
  `baseline/phase0/scripts/spikes/resolve_bus_route.py`,
  `baseline/phase0/scripts/spikes/mixed_route_spike.py`,
  `evidence/phase1/_scripts/tmap_geocode.py`
