# BUS_01A_EXTENDED — Bus 01A Target-Leg + Extended Collection (EV-09)

**Status: CONDITIONAL** (real 1-hour data collected cleanly, zero
errors; target-leg residual maturity still insufficient — high
variance, consistent with the Master Index's pre-existing concern)

## Target

01A route (`busRouteId=100100001`), target leg 춘추문 (`stId=100000417`,
`staOrd=19`) → 안국역6번출구.인사동문화의거리 (`stId=100000104`,
`staOrd=21`) — both `staOrd` confirmed live via a single arrival poll
(`raw/bus01A_arrival_snapshot_staOrd_lookup.json`), used to scope the
position collector to `startOrd=19 endOrd=21`.

## What was launched (2026-08-22, local time)

| Process | Command | Started |
|---|---|---|
| Arrival | `bus_arrival_spike.py 100100001 --interval 20 --count 180` | 12:41:38 |
| Position | `bus_position_spike.py 100100001 19 21 --interval 20 --count 180` | 12:52:39 (relaunched — same batching incident as `SUBWAY_SUSTAINED`) |

`DATA_GO_BUS_API_KEY` (a different, shared account-level key per D-013)
had enough quota headroom for the full ~1-hour run — **zero HTTP/API
errors across 361 total polls**, unlike the subway side.

## Result — polls / errors

- Arrival: 181 polls, 181 success, 0 error, 25 duplicate `mkTm`
  (repeated source snapshot — a real Ground-Truth-cadence signal,
  matching Phase 0's own note that `mkTm` can repeat across polls), 0
  out-of-order
- Position: 180 polls, 180 success, 0 error

## Result — target-leg vehId transitions (real, ~1 hour)

| Stop | distinct `vehId1` seen | transitions |
|---|---|---|
| 춘추문 (100000417) | 10 | 9 |
| 안국역6번출구 (100000104) | 8 | 7 |

## Result — target-leg traverse time (real, from position `sectOrd` 19→21 crossings)

11 vehicles observed crossing the target leg's ord range:

- **min 100 s, median 682 s, max 1223 s**

## Result — WAIT candidate (`exps1`, 181 samples per stop, 20 s cadence, 1 hour)

| Stop | n | min (s) | p50 (s) | p90 (s) | max (s) |
|---|---|---|---|---|---|
| 춘추문 | 181 | 2 | 190 | 464 | 732 |
| 안국역6번출구 | 181 | 1 | 240 | 502 | 624 |

## Congestion / fullness

`congetion` (sic, real API field name) values seen: `3` (338 rows),
`4` (65), `5` (9) — `isFullFlag` was `0` (not full) for all 412
position rows this hour.

## Interpretation — target-leg residual maturity still insufficient

The Master Index (`00_MASTER_INDEX.md` §1) already flags 01A target-leg
maturity as insufficient; **this session's real data confirms that
concern rather than resolving it**: an 11-sample traverse-time range of
100 s–1223 s (12x spread) for a nominally 2-stop leg is too wide to
treat as a stable residual distribution yet. This is a genuine finding,
not a collection failure — it says the target leg's actual travel time
is highly variable at this time of day/traffic condition, and more
data across more time windows (as the execution contract's EV-09 asks
for: "longer / different-time windows") is needed before this residual
can be trusted for a probability model.

## Old/new/combined support

This session's ~1 hour of new collection is additive to, and clearly
separated from, Phase 0's archived "54 transition" figure
(`00_MASTER_INDEX.md` §5), which was explicitly a route-level
multi-stop count, not this target leg. **Combined support across both
collection rounds is 11 target-leg traverse samples (this session) +
0 directly comparable Phase 0 target-leg samples** (Phase 0 did not
isolate this specific 2-stop leg) — so there is no prior data to merge
with; this session's 11 samples are the first target-leg-specific
support this project has.

## Artifacts

- `raw/bus01A_arrival_snapshot_staOrd_lookup.json`
- `derived/metrics_raw.json`
- `log_*.log`

## Reproduction

```bash
python evidence/phase1/_scripts/analyze_bus_extended.py
```
