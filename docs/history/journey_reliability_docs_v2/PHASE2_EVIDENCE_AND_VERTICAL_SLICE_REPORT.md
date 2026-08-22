# Phase 2 Evidence and Vertical Slice Report

**Executed:** 2026-08-22, per
`docs/journey_reliability_docs_v2/docs/00_governance/10_PHASE2_EVIDENCE_EXECUTION.md`
(JR-DOC-090). **Canonical `LOCKED` documents were not modified this round.**
All findings below are proposals for the document owners to apply through
the Freeze Rule (`00_MASTER_INDEX.md` §7), the same pattern used for the
Phase 1 report.

---

## 1. Executive Summary

This round executed against real, live external APIs and two newly
downloaded official files — no fabricated numbers, same standard as
Phase 1. **EV2-01 (collector timestamp bug) is VERIFIED fixed**, confirmed
against 646 real calls this session with real, varied round-trip latency
(previously always 0 ms). **EV2-05 (timetable freshness) is meaningfully
de-risked**: a materially newer official file was found and the Route A
schedule is confirmed stable across an ~8.5-month real comparison gap.
**EV2-06 (station-internal transfer access) was searched honestly** — a
real related dataset was found and correctly *not* converted into a
fabricated number.

**EV2-02 (subway sustained collection) and EV2-03 (bus target-leg
residual) both remain CONDITIONAL, for two different, real, non-code
reasons**: EV2-02's shared 1,000-calls/day key was already exhausted by
Phase 1's own usage earlier the same calendar day — despite this round's
own collector design fix, 284/286 calls returned `ERROR-337`; EV2-03's
pipeline is verified correct end-to-end (confirmed
against synthetic transitions), but this round's real 30-minute window
happened not to catch any vehicle mid-arrival (`stopFlag 0→1`) at the
target stop — every vehicle observed was already stopped and only its
departure (`1→0`) was captured, which the residual rule correctly does
not treat as an arrival. **EV2-04 (WAIT event semantics) surfaced a real
methodological problem, not just a result**: the simple "distinct vehId1
turnover" event definition, applied to this specific near-terminal stop,
produced headway samples clustered suspiciously at the poll interval
itself — a genuine finding that this event-unit definition needs
stop-topology awareness before it is trustworthy, not a clean result to
report at face value.

The full canonical-schema + vertical-slice pipeline (`ENT-0xx` DTOs →
Observation → Actual → Residual → LegDistribution → fixed-seed Monte
Carlo → BUS_SKIPPED reforecast) was implemented and run end-to-end
against this session's real data. It correctly reports `INSUFFICIENT`
confidence and a fully deterministic (zero-variance) demo result given
this round's thin real residual data — the honest output for the data
actually available, not a smoothed-over one.

No Web App, backend, Kafka/Flink/Spark, or calibrated-probability claim
was built or made, per the execution contract's explicit prohibitions.

## 2. Phase 1 blockers addressed

From `00_MASTER_INDEX.md` §5 ("Current Evidence Blockers", numbered per
that section):

| # | Phase 1 blocker | Phase 2 outcome |
|---|---|---|
| 1 | Bus target-leg Prediction→Actual residual not yet built | **Pipeline built, still zero real residuals** (EV2-03) — verified correct on real+synthetic data, but this round's window caught no live arrival, see §5 |
| 2 | Subway station×line Actual maturity/multi-window | **Attempted, blocked by quota carryover** (EV2-02) — see §4 |
| 3 | BUS_TO_SUBWAY station-internal access unresolved | **Searched, still unresolved** (EV2-06) — real partial reference found, no number invented, see §8 |
| 4 | Subway future WAIT freshness (~11mo gap) unverified | **Meaningfully de-risked** (EV2-05) — newer file found, schedule confirmed stable, see §7 |
| 5 | Support calibration needs more independent events | Not attempted this round (needs the V1/V2 validation-plan procedure in `43_VALIDATION_PLAN.md` §8, out of this round's real time budget) |
| 6 | Collector `requested_at`/`received_at` not request-boundary-accurate | **Fixed and confirmed live** (EV2-01), see §3 |
| 7 | True latency/lateness profile needed | Partially addressed — real round-trip latency now measured (§3); `received_at - source_generated_at` still not computed (clock-skew caveat, see §3) |
| 8 | Subway collector cadence design (quota-aware) | **Redesigned** (single coordinated process, PD-033-compliant) — design fix verified even though this round's quota was already exhausted, see §4 |
| 9 | 역삼역 실제 STATION_EXIT for FINAL_WALK | Not attempted this round (EV2-07 is a Should, not a Must; see §8) |
| 10 | 안국 entrance→platform source | **Searched** (EV2-06) — see item 3 above / §8 |

## 3. Collector timestamp result (EV2-01)

See `evidence/phase2/EV2-01_COLLECTOR_TIMESTAMP/README.md` for full detail.

**VERIFIED.** `common/storage.py`'s `SpikeResult.requested_at`/`received_at`
were both stamped post-response (PD-037's exact bug). Fixed: both fields
now required constructor args, captured immediately before/after the
actual `requests.get`/`.post` call at all 9 call sites in the spike
harness. Confirmed live across 646 real Phase 2 calls this session:

| Provider/API | n | p50 | p95 | p99 |
|---|---|---|---|---|
| Bus `getArrInfoByRouteAll` | 180 | 64 ms | 160 ms | 449 ms |
| Bus `getBusPosByRouteSt` | 180 | 43 ms | 101 ms | 381 ms |
| Subway `realtimeStationArrival` | 172 | 24 ms | 36 ms | 51 ms |
| Subway `realtimePosition` | 114 | 23 ms | 32 ms | 35 ms |

Zero 0 ms samples (Phase 1's entire dataset was 0 ms). `received_at -
source_generated_at` was not computed — no NTP-offset check against the
providers' clocks was performed this round, and PD-037/EV2-01 explicitly
warns against blending real latency with unverified clock skew.

## 4. Subway station×line Actual metrics (EV2-02)

See `evidence/phase2/SUBWAY_SUSTAINED/README.md` for full detail.

**CONDITIONAL — design fix verified, but data outcome is worse than
Phase 1's, for a documented, non-code reason.** A single coordinated
round-robin process (`subway_sustained_coordinated.py`) replaced Phase 1's
5-independent-concurrent-process design, directly implementing PD-033.
That fix is real. But `SEOUL_SUBWAY_REALTIME_KEY`'s 1,000-calls/day quota
was **already exhausted before this round started** (carried over from
Phase 1's own usage earlier the same calendar day) — of 286 calls this
round (including this session's own earlier smoke test), only 2
(`INFO-000`) succeeded; 284 returned `ERROR-337`. Zero new subway
`ActualArrivalInterval` samples were produced.

A real bug was also caught and fixed in the same script: the
quota-error auto-stop only checked the success-response JSON shape
(`errorMessage.code`), not `ERROR-337`'s actual flat shape (`{"code":
"ERROR-337", ...}`), so the 30-minute run never stopped itself early on
a doomed budget. Fixed in the committed script.

## 5. Bus target-leg ResidualEvent metrics (EV2-03)

See `evidence/phase2/BUS_01A_TARGET_LEG/README.md` for full detail.

**CONDITIONAL — pipeline verified correct on real data, zero residuals
this round for a documented reason.** Real 30-minute live collection,
zero HTTP/API errors: 180 real `PredictionSnapshot`s, 44 real position
events across 6 distinct vehicles. **Zero `ActualArrivalInterval`s**: every
observed vehicle was already `stopFlag=1` on first sighting and later
transitioned to `stopFlag=0` (departure) — the opposite direction from
the documented `0→1` arrival trigger. No vehicle was caught arriving
inside this specific window. The rule was **not** loosened to accept the
`1→0` direction (that would silently redefine "arrival" as "departure").
The `build_bus_actual_intervals`/`build_subway_actual_intervals` logic
was confirmed correct against synthetic `0→1` sequences (`actual_id`
generated, correct interval width) — the zero-result is a real data
outcome, not a bug. Zero real residual events therefore exist this round;
`AC-DATA-017` remains open pending a future window that catches a live
arrival.

## 6. Bus WAIT event-unit analysis (EV2-04)

See `evidence/phase2/EVD-WAIT-002/README.md` for full detail.

**CONDITIONAL — dependence claim quantified, but the event-unit
definition itself needs rework.** 147 boarding stop (`stId=122000005`),
real 30-minute/90-poll live collection:

- Raw snapshot series `exps1` **lag-1 autocorrelation = 0.77** — the
  first real number behind `PD-034`'s dependence claim (previously
  asserted qualitatively).
- "Distinct vehId1 turnover" event definition produced 6 events with
  headway samples `[20.08, 20.08, 20.10, 20.06, 20.07, 20.07]` s —
  **suspiciously identical to the 20 s poll interval itself**, combined
  with an `exps1` median of only 5 s across the whole series. The likely
  explanation: this stop sits near route 147's dispatch/staging point,
  where the "next predicted vehicle" slot reassigns between
  simultaneously-ready buses almost every poll — administrative churn,
  not passenger-relevant headway.
- **This is reported as a real methodological finding, not a usable
  headway number.** `43_VALIDATION_PLAN.md` §8.0's sample-unit-integrity
  instruction needs to go further than "count vehId1 changes" — a future
  round should require the *previous* vehicle's `exps1` to have reached
  near-zero before counting a turnover as a real event, and should
  compare against a non-terminal-adjacent stop as a baseline.

## 7. Subway timetable freshness (EV2-05)

See `evidence/phase2/EVD-SCHED-002/README.md` for full detail.

**Meaningfully de-risked.** Priority-1 check ("does a newer official file
exist?") found one: `data.go.kr` dataset pk `15098251`, same provider
(서울교통공사), file dated **2026-06-16** (vs Phase 1's `OA-22522`
2025-09-30) — freshness gap narrowed from ~11 months to ~2 months.
Compared the two snapshots for all 4 Route A station×line nodes across
`DAY`/`SAT`/`END` weektags and both directions (20 combinations): **18 of
20 are byte-identical in trains/day and median headway**; the other 2
differ by +2 trains/day and, in one case, a 15-second median headway
shift — real small operational deltas, not evidence of staleness. One
structural difference (extra blank-weektag rows in the old file, absent
in the new one) is unexplained but is a schema difference, not a Route A
schedule change.

Proposed: promote the freshness dimension of `EVD-SCHED-001` past
CONDITIONAL for this corridor specifically; do not generalize to a
citywide "timetable is always current" claim — this is a two-snapshot
comparison, not continuous monitoring.

## 8. Transfer/final-walk precision updates (EV2-06 / EV2-07)

**EV2-06 (BUS_TO_SUBWAY station-internal access): searched, still
`UNMODELED_UNCERTAINTY`.** Found a real official dataset,
서울교통공사_역사심도정보 (`OA-13305`), giving 안국역's platform-based
station depth (18.81 m) — a genuine, reproducible partial reference, but
a vertical-only measurement with no horizontal concourse distance and no
official stairs/escalator descent-rate source, so it was **not** converted
into a fabricated transfer-time number (that would be exactly the
arbitrary-fallback behavior `PD-021`/EV2-06 prohibit). `EVD-XFER-B2S-001`'s
station-internal component is unchanged from Phase 1. See
`evidence/phase2/EVD-XFER-B2S-002/README.md`.

**EV2-07 (FINAL_WALK exit precision): not attempted this round** — it is
explicitly a Should, not a Must, in the execution contract, and this
round's real time budget went to the Must items above. `EVD-DEST-001`'s
existing `STATION_CENTER`-based 329 m / 300 s reference is unchanged and
not relabeled as exit-based, per the contract's explicit instruction.

## 9. Canonical schema implementation status

**Implemented**, in `evidence/phase2/vertical_slice/schema.py`: one
canonical Pydantic projection of every `ENT-0xx` entity in
`40_DATA_CONTRACT.md` (`GeoPoint`/`NodeRef` through
`JourneyResultSnapshot`, 18 entities), field names and enums matching the
Markdown contract directly — the Markdown stays the design source of
truth, this is its runnable form, not an independent schema. Not
implemented: the Silver/Gold storage layer itself, or the immutable-
versioning enforcement in `40_DATA_CONTRACT.md` §8 (this is a vertical-
slice fixture, not a production data layer, consistent with the
execution contract's own scope limits).

## 10. Probability vertical-slice implementation status

Full pipeline implemented and run against this session's real samples,
`evidence/phase2/vertical_slice/`:

```
Raw sample (Bronze, spike-v1-ev2-01)
  -> parsers.py: Observation + PredictionSnapshot (bus XML / subway JSON)
  -> actual_builders.py: ActualArrivalInterval
       (bus: stopFlag 0->1 per vehId; subway: arvlCd !=1 -> ==1 per subwayId x statnId x btrainNo)
  -> residual_builder.py: ResidualEvent (vehicle-id-matched, lead-time preserved,
       validation_group_id = matched actual_id, anti-leakage per EV2-03/43_VALIDATION_PLAN.md §8.0)
  -> distribution_builder.py: LegDistribution (EMPIRICAL_SAMPLES or STATIC_REFERENCE,
       confidence_label derived from real sample_count, never asserted)
  -> engine.py: fixed-seed (seed=42) Monte Carlo over LegDistributions -> JourneySimulationRun
       -> JourneyResultSnapshot (validation_scope=COMPONENT_ONLY, confidence_label from the
          weakest leg, model_coverage=PARTIAL wherever any leg is UNMODELED)
  -> engine.apply_bus_skipped(): PD-011-compliant deterministic state transition
       (ACTIVE -> REFORECASTING, state_version+1, UserEvent recorded) + re-simulation demo
```

This matches `43_VALIDATION_PLAN.md` §2's `V0 Engine Logic` scope exactly
("synthetic/deterministic fixture로 state transition ... 실제 calibration
claim은 하지 않는다") — this is deliberately not attempting `V1`/`V2`/`V3`.

QA acceptance criteria touched (`61_QA_ACCEPTANCE.md`): `AC-DATA-017`
(real residual, not traverse-time substitute), `AC-DATA-018` (subwayId x
statnId split), `AC-DATA-019` (real timing), `AC-DATA-020` (quota errors
measured separately, not hidden inside HTTP 200), `AC-PROB-001` (every leg
carries a `LegDistribution`), `AC-PROB-002` (`UNMODELED` legs listed in
`limitations`), `AC-PROB-003` (n=2000, in the 2k-5k range), `AC-PROB-004`
(real p50/p90). **Not touched**: `AC-PROB-006` (`planned_connection_
success_probability` stays `None` this round — not computed, no invented
value substituted) and `AC-PROB-007` (Recommended Departure stays
`INSUFFICIENT_DATA`, per the master index's existing `HOLD`).

Demo run (seed=42, n=2000, `ROUTE_A-corridor_a`, fixed 08:30 KST start,
09:00 KST target):

| Field | Value |
|---|---|
| `p50_arrival_at` / `p90_arrival_at` | 08:58:09 KST (identical) |
| `on_time_probability` | 1.0 |
| `confidence_label` | `INSUFFICIENT` |
| `validation_scope` | `COMPONENT_ONLY` |
| `model_coverage` | `PARTIAL` |

**`p50 == p90` and a flat `on_time_probability=1.0` is the honest output
for this round's real inputs, not a bug to paper over**: with zero real
`ResidualEvent`s for the bus leg (§5) and every other leg still
`STATIC_REFERENCE`/`UNMODELED_UNCERTAINTY` (ACCESS_WALK, 교대 3→2
TRANSFER, FINAL_WALK all point values; subway ride leg is an explicit
structural placeholder, not this round's object), every one of the 2000
Monte Carlo draws sums the *same* fixed numbers — so the simulation is
correctly deterministic given its inputs, and correctly labels itself
`INSUFFICIENT` rather than presenting a false sense of a spread. The
`BUS_SKIPPED` reforecast fixture demo (`apply_bus_skipped()`) ran
correctly: `ACTIVE → REFORECASTING`, `state_version` `1→2`, a real
`UserEvent` recorded, and a fresh simulation over the remaining legs
produced (same deterministic-input caveat applies).

## 11. Contract conflicts

1. **`ERROR-337`'s error-response shape is not the same as the documented
   success-response shape** — `errorMessage.code` (success) vs top-level
   `code` (hard error). Any quota-detection code (this session's own
   `subway_sustained_coordinated.py`, and implicitly Phase 1's harness)
   that only checks the success shape will silently treat quota
   exhaustion as "saved OK." Fixed in this session's script; flagged here
   because it is a real, reproducible provider-contract fact, not a
   one-off bug.
2. **Subway daily quota carries over across sessions/calendar-day
   boundaries in a way this project had not yet measured**: this round
   started with the SAME calendar day's quota Phase 1 had already spent
   hours earlier, leaving near-zero budget regardless of this round's own
   (now PD-033-compliant) collector design. `00_MASTER_INDEX.md`'s
   framing of PD-033 as purely a "coordinate concurrent pollers" problem
   is incomplete — the quota window itself (calendar-day, not per-
   session) is an equally binding constraint.
3. **`data.go.kr`'s copy of the subway timetable is CP949-encoded; Seoul's
   own `data.seoul.go.kr` `OA-22522` is UTF-8-BOM** for what is
   substantively the same dataset from the same provider — any future
   parser reusing "OA-22522 parsing logic" for the fresher file must not
   assume the encoding carries over.

## 12. Proposed Evidence/Decision updates

(For `03_EVIDENCE_REGISTER.md` / `02_DECISION_LOG.md` — proposal only, not
applied this round)

| ID | Proposed change |
|---|---|
| New `EVD-VOLUME-002`/timestamp | `EV2-01` collector fix + real latency profile, VERIFIED |
| `EVD-SCHED-001` | Freshness dimension: CONDITIONAL -> upgrade (corridor-scoped, 2-snapshot comparison, ~2mo gap) |
| `EVD-XFER-B2S-001` | Unchanged status; register `OA-13305` depth figure as a new reusable partial reference, not a status change |
| New `EVD-SUB-OPS-002` | Subway quota carries over across calendar-day sessions — register as its own operational finding distinct from PD-033's concurrency fix |
| New decision (candidate `PD-041`) | "A same-day Phase N+1 subway collection attempt must check remaining quota before committing to a duration budget, since a prior session's usage on the same key/day is not visible without a live check" |

## 13. Gate recommendation

- **EV2-01**: close as VERIFIED — fix applied, confirmed live.
- **EV2-02**: keep CONDITIONAL — design is fixed, but real coverage data
  is still thin; needs a same-day-fresh-quota re-run to actually measure
  the fixed design's ceiling.
- **EV2-03**: keep CONDITIONAL — pipeline verified correct on real and
  synthetic data; needs a future window (wider stop range and/or 60+
  minutes) that actually catches a live `0→1` transition before any
  residual maturity claim can move.
- **EV2-04**: keep CONDITIONAL — `PD-034` dependence is now quantified
  (autocorrelation 0.77), but the event-based headway method itself needs
  the stricter definition proposed in §6 before its output is trustworthy;
  do not use this round's 20.08 s figure as a real headway value.
- **EV2-05**: upgrade recommended for the freshness dimension specifically
  (see §7); do not upgrade to citywide/continuous-validity claims.
- **EV2-06**: keep `UNMODELED_UNCERTAINTY` — searched honestly, real
  partial source registered, no number invented.
- **Probability Vertical Slice**: `V0 Engine Logic` scope delivered and
  runnable against real data; do **not** promote past `CONDITIONAL GO` —
  `V1`/`V2`/`V3` calibration per `43_VALIDATION_PLAN.md` remain
  NOT_STARTED.
- Recommended Departure `AVAILABLE`: **still HOLD**, unchanged from
  `00_MASTER_INDEX.md` — nothing in this round closes the subway
  future-WAIT-source or residual-maturity gates that HOLD depends on.

## 14. What still must not be claimed

Per the execution contract's explicit prohibitions, none of the following
are supported by this round's results:

- A "calibrated" Journey probability of any kind (`V0` fixture only,
  `PD-030`/`PD-040` unchanged)
- Any Web App, backend, Kafka/Flink/Spark implementation (none built)
- Citywide generalization of any Phase 2 finding (all corridor-scoped)
- The `181` Phase 1 `exps1` snapshots, or this round's own raw snapshot
  series, treated as independent headway samples (`PD-034` — see §6's
  explicit raw-vs-event-based separation)
- A fixed fallback number for `BUS_TO_SUBWAY` station-internal
  entrance→platform time (`PD-021`/EV2-06 — none was invented)
- Subway timetable currentness as a citywide or indefinite-future claim
  (§7's result is corridor-scoped and a two-point comparison)
- Recommended Departure `AVAILABLE` for real users (`00_MASTER_INDEX.md`
  HOLD unchanged)

---

## Appendix: Evidence Folder Index

```
evidence/phase2/
├─ EV2-01_COLLECTOR_TIMESTAMP/  — EV2-01 (VERIFIED)
├─ SUBWAY_SUSTAINED/            — EV2-02 (CONDITIONAL)
├─ BUS_01A_TARGET_LEG/          — EV2-03 (see §5)
├─ EVD-WAIT-002/                — EV2-04 (see §6)
├─ EVD-SCHED-002/               — EV2-05 (upgrade recommended)
├─ EVD-XFER-B2S-002/            — EV2-06 (UNMODELED_UNCERTAINTY unchanged)
├─ vertical_slice/              — canonical schema + Raw->...->JourneyResult pipeline
├─ vertical_slice_result.json   — machine-readable pipeline output, this session
└─ _scripts/                    — this round's analysis/collector scripts
```
