# EVD-CROSS-002 — Route B (`SUBWAY_TO_BUS`) Realtime E2E

**Status: VERIFIED** (structural interoperability + sustained
skip/wait behavior both confirmed with real data — see `EVD-WAIT-001/`
for the ~1-hour 147 sustained collection that resolved the
`BUS_SKIPPED`/`BUS_WAIT` feasibility question below)

## Claim under test

The demo corridor's `SUBWAY→BUS` alternative —
`01A 춘추문→안국역6번출구 → 3호선 안국→압구정 → 147 압구정역4번출구→역삼역6번출구`
(packaged Phase 0 Raw:
`baseline/phase0/data/samples/examples/seoul_bus/demo_corridor_samcheong_yeoksam/160402_b6021bab94ac.json`)
— is realtime-interoperable: every ID in the structural path resolves
against a live prediction/position feed.

`EVD-CROSS-001` already covers structural existence (VERIFIED). This
evidence item is about E2E ID interoperability + live behavior.

## What was done (live calls, 2026-08-22 03:38–03:40 UTC)

1. `getArrInfoByRouteAll` for bus 147 (`busRouteId=100100026`)
2. `getBusPosByRouteSt` for the same route, `startOrd=41 endOrd=48`
3. `realtimeStationArrival` for 압구정 and 안국 (name search)
4. `realtimePosition` for 3호선

## Result — bus leg (direct ID join, no crosswalk needed)

| Mixed-route field | Live arrival field | Match |
|---|---|---|
| `fid=122000005` (압구정역4번출구) | `stId=122000005`, `staOrd=41`, `arsId=23105` | ✅ exact |
| `tid=122000179` (역삼역6번출구) | `stId=122000179`, `staOrd=48`, `arsId=23282` | ✅ exact |

Real live predictions at 압구정역4번출구: two next buses, `exps1=464s`
(~7m48s), `exps2=589s` (~9m35s) — a genuine `BUS_WAIT` candidate
snapshot (single point-in-time, not yet a distribution — see
`EVD-WAIT-001`).

`vehId` cross-join confirmed real and live: vehicle `110052281` appears
in both the arrival response (as `vehId1` at 역삼역6번출구, staOrd 48)
and the position response (`sectOrd=47`, i.e. one section before that
stop) — consistent, not coincidental.

## Result — subway leg (crosswalk needed — new finding this session)

| Station | Mixed-route code | Realtime `statnId` (confirmed live) |
|---|---|---|
| 안국 | `03180` | `1003000328` (already known from `ID_MAPPING.md`) |
| 압구정 | `03260` | **`1003000336`** ← new, confirmed this session via live name search, `subwayId=1003` (Line 3) matches the mixed-route leg's `routeNm=3호선` |

Real live train seen at 안국 during this call: train `3135`,
`arvlCd=0` ("진입", entering), 상행 방향, "…3호선방면" — a genuine live
train, not a cached/stale response (`recptnDt` matches call time).

## `TRANSFER_SUBWAY_TO_BUS` / `BUS_WAIT` / `BUS_SKIPPED` feasibility

- Both sides of the transfer (subway arrival at 압구정, bus arrival at
  압구정역4번출구) are independently pollable by the crosswalked IDs
  above — E2E interoperability is real, not assumed.
- `BUS_WAIT`: real `exps1`/`exps2` fields give a same-poll 2-bus-ahead
  wait candidate; a distribution requires sustained polling (delegated
  to `EVD-WAIT-001`).
- `BUS_SKIPPED`/`BUS_WAIT` over time: **confirmed with the ~1-hour
  sustained 147 collection** (`EVD-WAIT-001/`) — 7–9 real, distinct
  `vehId1` transitions per stop over the hour, plus 181 real `exps1`
  WAIT-candidate samples per stop (median 239–253 s). See
  `EVD-WAIT-001/README.md` for the full distribution and limitations.

## Why VERIFIED

The single-shot calls above proved every ID resolves and both feeds
are live and mutually consistent (structural E2E). The sustained
147 collection then confirmed real behavior over time — distinct
vehicles rotating through the "next bus" slot and a genuine WAIT
sample — closing the gap that made this CONDITIONAL earlier in this
same execution.

## Artifacts

- `raw/bus147_arrival_snapshot.json`
- `raw/bus147_position_snapshot.json`
- `raw/subway_arrival_apgujeong_snapshot.json`
- `raw/subway_arrival_angguk_snapshot.json`
- `raw/subway_position_line3_snapshot.json`

## Reproduction

```bash
cd docs/journey_reliability_docs_v2/baseline/phase0/scripts/spikes
python bus_arrival_spike.py 100100026 --count 1
python bus_position_spike.py 100100026 41 48 --count 1
python subway_arrival_spike.py 압구정 --count 1
python subway_arrival_spike.py 안국 --count 1
python subway_position_spike.py 3호선 --count 1
```
