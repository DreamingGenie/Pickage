# EVD-WAIT-001 — Bus Future WAIT/Headway Feasibility

**Status: VERIFIED (feasibility) — as a same-poll empirical distribution, not a future-vehicle prediction**

## Claim under test

Realtime position/arrival observations for bus 01A and Route B's 147,
over a sustained window, can produce a time-conditioned headway/wait
sample — without predicting a specific future vehicle ID.

## What was done

~1 hour of sustained collection (2026-08-22), 20 s cadence, zero
HTTP/API errors on `DATA_GO_BUS_API_KEY`:

- `bus_arrival_spike.py 100100026 --interval 20 --count 180` (147)
- `bus_position_spike.py 100100026 41 48 --interval 20 --count 180` (147)
- (01A's equivalent run is analyzed under `BUS_01A_EXTENDED/`)

## Result — 147, WAIT candidate (`exps1`, 181 samples/stop)

| Stop | n | min (s) | p50 (s) | p90 (s) | max (s) |
|---|---|---|---|---|---|
| 압구정역4번출구 (122000005) | 181 | 1 | 253 | 806 | 1061 |
| 역삼역6번출구 (122000179) | 181 | 1 | 239 | 759 | 1099 |

## Result — 147, vehId transitions (real buses passing, ~1 hour)

| Stop | distinct `vehId1` | transitions |
|---|---|---|
| 압구정역4번출구 | 8 | 7 |
| 역삼역6번출구 | 9 | 8 |

7–9 real, distinct vehicles rotated through the "next bus" slot at each
stop over the hour — a genuine headway-relevant signal.

## Result — 147, position congestion/target-leg

- `congetion` values: `3` (192 rows), `4` (152 rows)
- 9 distinct vehicles crossed the 압구정→역삼 ord range (41→48); 8
  target-leg traverse-time samples, **180 s–1103 s** (median 962 s)

## Feasibility verdict

**Yes, a time-conditioned empirical wait/headway sample is
constructible from this real data**, per stop:
1. `exps1`/`exps2` give a continuous same-poll "seconds until next bus"
   series — 181 real points per stop this hour, not a single snapshot.
2. `vehId1` transitions (7–9 per stop/hour) give a real count of
   distinct buses cycling through, usable to convert the exps series
   into discrete headway events (gap between one `vehId1`'s exit and
   the next `vehId1`'s entry).
3. At no point does this require guessing which specific future
   vehicle ID will serve a rider — the distribution is over elapsed
   seconds, conditioned on time-of-day/stop, matching the execution
   contract's constraint.

## Limitation

- One hour, one time-of-day window, one weekday — not yet a
  time-bucketed (e.g. AM peak vs midday) distribution; that requires
  multiple collection rounds at different times, which is future work
  (`08_IMPLEMENTATION_STATUS.md` should track this, not this evidence
  item).
- `exps1` is itself the provider's own prediction, not an independent
  ground-truth wait time — treating it as "the" wait sample inherits
  whatever prediction error data.go.kr's ETA model has. A stricter
  ground-truth wait would need to be derived from real arrival events
  only (`BUS_SKIPPED`-aware), which needs a longer/multi-session
  collection to accumulate enough real arrival transitions.

## Artifacts

- `log_arrival_147.log`, `log_position_147.log`
- `derived/metrics_raw.json`

## Reproduction

```bash
python docs/journey_reliability_docs_v2/evidence/phase1/_scripts/analyze_bus_extended.py
```
