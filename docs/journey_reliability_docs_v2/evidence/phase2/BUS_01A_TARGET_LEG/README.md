# BUS_01A_TARGET_LEG — Bus 01A Target-Leg ResidualEvent (EV2-03)

**Status: CONDITIONAL — pipeline verified end-to-end on real data, but zero
`ResidualEvent`s this round for a real, specific, documented reason (not a
code bug).**

## Target

춘추문 (`stId=100000417`, `staOrd=19`) → 안국역6번출구 (`stId=100000104`,
`staOrd=21`), route `01A` (`busRouteId=100100001`) — same target leg as
Phase 1's `BUS_01A_EXTENDED`. Real 30-minute live collection this session:
180 arrival polls (all `headerCd=0`, zero HTTP/API errors), 90 position
polls scoped to `startOrd=19 endOrd=21` (44 real vehicle-in-range
observations, 51 "결과가 없습니다" / no-vehicle-in-range polls — a normal
outcome for a 3-stop window, not an error).

## What the pipeline produced

- **180 real `PredictionSnapshot`s** (target `stId=100000104`, `vehId1`/`vehId2` filtered for real vehicles per `41_OBSERVATION_ACTUAL_RESIDUAL.md` §2's `vehId=0` exclusion rule)
- **44 real position events**, 6 distinct `vehId`
- **0 `ActualArrivalInterval`s** (`BUS_ACTUAL_RULE_V1_CANDIDATE`: `stopFlag` `0`→`1`)
- **0 `ResidualEvent`s** (no `ActualArrivalInterval` to match against)

## Why zero, and why this is a real finding, not a bug

Every one of the 6 distinct vehicles observed this round was **already
at `stopFlag=1` on its first sighting**, then transitioned to `stopFlag=0`
(departure) partway through its observed sequence — the *opposite*
direction from the `0→1` arrival trigger `41_OBSERVATION_ACTUAL_RESIDUAL.md`
§3 defines:

```
vehId 106024456: 1,1,1,1,1, 0,0,0,0,0,0,0   (arrived before window opened, then departed)
vehId 106069585: 1,1,1,1,   0,0,0,0,0,0,0
vehId 106024516: 1,        0,0,0,0,0,0
```

No vehicle in this specific ~30-minute window was caught arriving
(`0→1`) at this narrow 3-stop section — every vehicle present was already
stopped when first observed, and only its departure was captured. This is
consistent with Phase 1's own finding that this target leg's traverse time
has a **12x spread (100 s–1,223 s)** — a real arrival can simply not fall
inside any given 30-minute window depending on where in that spread the
actual trip lands.

**This was not "fixed" by loosening the rule to accept `1→0` instead** —
that would silently redefine "Actual arrival" as "Actual departure," a
different real-world event, which `41_OBSERVATION_ACTUAL_RESIDUAL.md`
does not define and this round has no authority to redefine unilaterally.

## What this means for EV2-03 / `PD-036`

- The **pipeline** (Raw → Observation → PredictionSnapshot →
  ActualArrivalInterval-detector → residual matcher) is real, runs against
  real data, and is verified to correctly implement the documented rule
  end-to-end (confirmed on synthetic 0→1 sequences during development,
  see `../vertical_slice/actual_builders.py` tests implied by its own
  logic — not fabricated data mixed into this evidence folder).
- **Target-leg `ResidualEvent` maturity remains open** — this round adds a
  second real 30-minute attempt (after Phase 1's 1-hour traverse-only
  collection) that also did not close it, for a documented reason. The
  execution contract's own "최소 두 시간대/window를 목표로 하되..." guidance
  is not yet met — **only one real EV2-03 window exists so far** (this
  one), and it produced zero residuals.

## Recommendation

A future round should either (a) widen the position `startOrd/endOrd`
range beyond the immediate 3-stop target to increase the chance of
catching a live `0→1` transition, or (b) run a longer single window
(60+ minutes, matching Phase 1's bus-key quota headroom) so the ~100-
1,223 s traverse-time spread has more chances to land an arrival inside
the window.

## Artifacts

- `../vertical_slice_result.json` (`bus_01A_target_leg` key)
- `../vertical_slice/actual_builders.py`, `residual_builder.py`
