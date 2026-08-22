# EVD-XFER-B2S-001 — 01A→안국 BUS_TO_SUBWAY Transfer

**Status: CONDITIONAL**

## Claim under test

The bus-alight → subway-entry leg of Route A's first transfer:
안국역6번출구.인사동문화의거리 (bus alight, `id=100000104`, raw coord
`126.98412712121268,37.57575695248874`) → 안국 3호선 mixed node
(`fid=03180`, raw coord `126.98546292770595,37.57648700828617`).

Per the execution contract, this transfer must be decomposed into:
1. street/exit-reachable part (computable via TMAP)
2. station internal entrance→platform part (NOT computable with any API
   in this package)

## What was done

Live TMAP pedestrian call between the two raw coordinates above.
Executed 2026-08-22 03:37 UTC.

## Result — part 1 (street part)

- HTTP 200
- `totalDistance` = **143 m**
- `totalTime` = **101 s**
- End point is the mixed-route API's representative node for 안국역
  (`fid=03180`), **not a confirmed station entrance or platform
  coordinate** — it is whatever point data.go.kr's mixed-route graph
  uses to represent the station in routing.

## Result — part 2 (station internal entrance→platform)

**UNMODELED_UNCERTAINTY.** No API in this package (TMAP, Seoul bus,
Seoul subway realtime, or the two OA file datasets) exposes a station's
internal entrance→platform walking distance/time. TMAP routes street
geometry only and stops at the station's mixed-route graph node. This
matches the execution contract's explicit expectation ("정확한
exit/platform coordinate source가 없으면 UNMODELED_UNCERTAINTY").

## Coordinate roles

| Point | Role | Source |
|---|---|---|
| Start | `BUS_STOP` | Phase 0 packaged mixed-route Raw (`tid=100000104`) |
| End | `STATION_CENTER` candidate (NOT a confirmed `STATION_EXIT`) | mixed-route graph node `fid=03180` |

## Why CONDITIONAL, not VERIFIED

The street-reachable part is a real, verified TMAP result (143 m / 101 s).
But the full BUS_TO_SUBWAY transfer time a rider actually experiences
also includes the unmeasured entrance→platform walk, which this package
has no data source for. Reporting 101 s as "the transfer time" would
silently understate it — exactly the failure mode `PD-028`
(`00_governance/02_DECISION_LOG.md`) prohibits.

## Artifact

- `raw/street_walk_bus_alight_to_subway_node_angguk.json`

## Reproduction

```bash
cd docs/journey_reliability_docs_v2/baseline/phase0/scripts/spikes
python tmap_walk_spike.py 126.98412712121268 37.57575695248874 126.98546292770595 37.57648700828617 \
  "01A_alight_안국역6번출구_BUS_STOP" "안국역_3호선_mixed_node_STATION_CENTER_candidate"
```

## Recommendation

If a production build needs this leg's full transfer time, it needs a
new evidence source (station internal-layout data or a fixed empirical
fallback constant per PD-028's `PLATFORM_REFERENCE` role) — not TMAP.
