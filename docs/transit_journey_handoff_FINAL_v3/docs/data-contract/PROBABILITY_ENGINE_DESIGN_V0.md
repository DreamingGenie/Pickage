# Journey Probability Engine — Design Proposal v0 (Demo Corridor)

> **Status: DESIGN PROPOSAL, NOT IMPLEMENTED.** No Monte Carlo code exists
> yet. This document exists so the Probability Engine — the one part of
> Phase 0 explicitly reserved for joint PM + Reliability + Backend design
> (`01_PROJECT_HANDOFF.md` 3.2) — gets a review pass before anyone writes
> simulation code, rather than a solo agent inventing the math unsupervised.
> Everything below is either (a) already established in
> `01_PROJECT_HANDOFF.md` sections 10–11, restated here scoped to the
> actual demo corridor, or (b) marked `OPEN QUESTION` for PM/team decision.
> Nothing here should be read as decided.

## 1. Scope

The fixed corridor only: **삼청동 ↔ 역삼역** (D-030), destination-anchored
per PM's Q2 answer (arrival = actual destination, not the transit stop —
D-039). This document does not propose anything for citywide coverage.

## 2. Leg composition (per the corridor's top mixed-route alternative, D-031/D-047)

```
WALK   (access: origin → 무교동 bus stop)               [TMAP, D-045]
BUS    01A leg (무교동 → 안국로터리6번출구, busRouteId=100100001)  [D-038]
WALK   (transfer: bus stop → 안국역)                     [TMAP, OPEN QUESTION below]
SUBWAY 3호선 안국역 → 교대역 (statnId 1003000328 → 1003000340)     [D-034]
WALK   (transfer: 교대역 3호선 승강장 → 2호선 승강장)         [TMAP or fixed same-station transfer time, OPEN QUESTION]
SUBWAY 2호선 교대역 → 역삼역 (statnId 1002000223 → 1002000221)     [D-034]
WALK   (final: 역삼역 → actual destination)               [TMAP, D-045/D-039]
```

This is a 7-leg composition (4 WALK + 1 BUS + 2 SUBWAY), not the
3-leg (BUS→SUBWAY→SUBWAY) view the mixed-route API itself returns —
the extra WALK legs come from Q2/Q3 (D-039/D-040) extending scope
beyond the transit-only response.

**OPEN QUESTION (PM/team):** should in-station subway-to-subway
transfers (교대역 3호선→2호선) be modeled as a WALK leg queried from
TMAP, or as a fixed/looked-up transfer-time constant? TMAP's pedestrian
API expects real coordinates and may not model "inside paid-area
transfer corridor" walks realistically (it's built for street-level
routing). Needs a decision before implementation — do not assume TMAP
covers this well without testing it specifically for this transfer.

## 3. Per-leg distribution readiness — current state (honest inventory)

| Leg | Actual-rule method | Data depth so far | Ready for real quantiles? |
|---|---|---|---|
| BUS 01A | `stopFlag` 0→1 transition, residual = actual − predicted (proven methodology, D-020/D-035 on route 753) | Only ~6 polls / 12 vehicles observed on 01A itself (D-038) — a smoke test, not sustained collection | **No** — methodology is proven, but not on this specific route with enough volume for empirical quantiles |
| SUBWAY 3호선 안국→교대 | `arvlCd` state machine (`SUBWAY_ACTUAL_RULE_V0.md`) | A few polls only (D-034), same-day smoke test | **No** — rule validity confirmed here, but no sustained interval-width sample |
| SUBWAY 2호선 교대→역삼 | Same rule | Same as above (D-034), plus the unresolved Line 2 station-code gap (D-026/D-032/D-036) still open for *other* Line 2 stations, though not this leg's stations | **No**, and carries the general Line 2 caveat until D-036 resolves |
| WALK legs (×4) | TMAP pedestrian route API, single point estimate per call (D-045) | One real call per leg tested | **Point estimate only** — TMAP does not return a distribution/percentiles, just one route's time. A variance model is needed (see §5) |

**Conclusion: no leg on this corridor has enough real data yet for a
genuine empirical P10/P50/P90.** The next concrete *data* task (not
implementation) is a sustained (hour-scale) collection window
specifically on route `01A` and these two subway legs, mirroring what
D-020/D-035 already did for route 753. Building simulation code before
that data exists would mean feeding it fabricated distributions —
exactly what the project's Honesty principle (P0-4, section 20
"Honesty") forbids.

## 4. Monte Carlo mechanics (restating `01_PROJECT_HANDOFF.md` §11, scoped to this corridor)

Per simulation run:

```
1. Sample WALK access time (origin → bus stop)
2. Sample BUS 01A wait + travel time to 안국역-adjacent stop
3. Sample WALK transfer time (bus stop → 안국역 entrance)
4. Sample SUBWAY 3호선 travel time (안국 → 교대)
5. Sample WALK/transfer time (교대역 3호선→2호선 platform)
6. If planned 2호선 train is missed (headway-based feasibility check):
   choose next feasible train per MVP rule [OPEN QUESTION, see below]
7. Sample SUBWAY 2호선 travel time (교대 → 역삼)
8. Sample WALK final time (역삼역 → destination)
9. Sum all legs → one simulated total journey time
10. Repeat N times
```

Then, per §11.1–11.3:

```
P(on_time) = count(simulated_arrival <= target_arrival) / N
```

Report **both**:
- planned-transfer-success probability (no missed connections)
- final on-time probability (missed connections recovered via next vehicle)

Recommended departure: binary search / time-grid over depart_time such
that `P(arrival <= target | depart_time) >= p*` for a user-chosen `p*`.

**OPEN QUESTIONS for PM/team before implementation:**
- What determines "missed transfer" for the bus→subway and
  subway→subway legs? A fixed minimum transfer buffer? Live headway
  from the realtime position feed? This wasn't decided in Q1–Q4 and
  isn't obvious from existing data alone.
- Default `N` (simulation count) — no number has been chosen; pick
  based on how stable `P(on_time)` is at that N, not an arbitrary round
  number.
- Default `p*` if the user doesn't specify one (the handoff mentions
  80/90/95% as examples in section 16, not a decided default).

## 5. Handling legs with no real distribution yet (fallback tiers)

Per `01_PROJECT_HANDOFF.md` §13.1's hierarchical fallback concept,
applied here rather than blocking on full data collection:

- **Tier 0 (current, honest-but-weak):** WALK legs use TMAP's single
  point estimate with a placeholder variance (e.g., a fixed
  percentage) — must be flagged `fallback_level=WALK_POINT_ESTIMATE`
  in the `LegDistribution` record so the UI/output never hides that
  this isn't a real empirical spread (P0-4 honesty requirement).
- **Tier 1 (once sustained collection exists):** BUS/SUBWAY legs use
  real empirical residual quantiles from route-753-proven methodology,
  applied to `01A` and the two subway legs specifically.
- Do not silently blend a Tier-0 point estimate into the same output
  format as a Tier-1 empirical quantile without the `fallback_level`
  field making the difference visible — this is exactly the
  "support/confidence 숨기지 않음" acceptance criterion (section 20
  Honesty).

## 6. What this document is NOT

- Not a schema change proposal (the existing `LegDistribution`/
  `JourneyResult` contracts in section 10 already fit this, with the
  `WALK` mode already added per D-039).
- Not a claim that any of the above has been implemented or tested.
- Not a final architecture — Kafka/Flink/Spark are out of scope for a
  fixed-corridor first slice per the handoff's own sequencing (build
  the vertical slice first, distributed-proof later).

## 7. Suggested next steps, in order

1. PM/team review of the two `OPEN QUESTION` items above (transfer
   handling, missed-connection rule) — these are product/data
   judgment calls, not something to infer from code.
2. Sustained (1h+) real data collection on route `01A` and the two
   subway legs (mirrors D-020/D-035's proven approach) — a *data* task,
   safe to do without further design sign-off.
3. Only after both: implement the Tier-0 vertical slice (fallback
   WALK + whatever real BUS/SUBWAY quantiles exist by then) and
   compute a first real `P(on_time)` for this corridor.
