# Subway Actual Ground Truth Rule — v0

> Checklist F deliverable (`../03_API_SPIKE_CHECKLIST.md`). This is the
> first version of the rule for turning `realtimeStationArrival`'s
> `arvlCd` sequence into an `ActualArrivalInterval` event. Status:
> **CONDITIONAL** — see "Known gap" below before treating this as
> citywide-reliable. Evidence trail: `../05_DECISION_LOG.md`
> D-016 through D-034.

## Rule

For a given `(subwayId, statnId, btrainNo)`, treat the first poll where
`arvlCd` transitions **into `1` (도착/arrived)** as the Actual arrival
event for that train at that station.

```
event.actual_arrival_at ∈ (t_prev, t_curr]
  where arvlCd(t_prev) != 1 and arvlCd(t_curr) == 1
```

The interval is **censored, not a point estimate** — the true arrival
time lies somewhere between the last non-`1` poll and the first `1`
poll, with width bounded by the polling interval. Do not report a
single timestamp without the interval; report the *interval*, per
project principle 5 (`../02_AGENT_CONTINUATION_PROMPT.md`).

## Observed state set (superseded checklist assumption)

The original checklist section F candidate assumed a 4-state sequence
(전역출발→진입→도착→출발, i.e. `arvlCd ∈ {0,1,2,99}` only). Sustained
polling found a richer set:

```
arvlCd ∈ {0, 1, 2, 3, 4, 5, 99}
```

- `99` — en route, far from the target station; `arvlMsg2` carries a
  countdown ("N분 M초 후") or a station-count message
- `5, 4, 3, 2` — descending "N stations away" / closer countdown states
  (exact per-code semantics not individually confirmed — inferred from
  ordering, not from an official field dictionary)
- `0` — entering (진입)
- `1` — arrived (도착) — **the Actual event trigger**
- `2` — departed (출발) *(note: `2` appears to serve double duty as both
  a "stations away" countdown value and a terminal "departed" value in
  different positions in the sequence — this ambiguity is unresolved,
  see Risks)*

## Ordered progression (cross-line confirmed)

The same relative ordering was observed independently on **Line 1**
(trains 0704, 0825 — D-021), **Line 2** (trains 6513, 4515, 6508 —
D-021/D-026), and **Line 3** (trains 3065 at 안국역, 3057 at 교대역—
D-034):

```
99 → {5, 4, 3, 2, ...} → 0 → 1 → 2
```

Three independent lines producing the same ordering is the strongest
evidence so far that this is a real state machine and not
station/line-specific noise.

## Coverage (trainNo join rate) — per station, this session

| Station | statnId | subwayId | Join rate | Note |
|---|---|---|---|---|
| 시청 | 1001000132 | 1001 (Line 1) | 11/12 (91.7%) | 1 train (5166) never joined all session — cause unknown |
| 강남 | 1002000201 | 1002 (Line 2) | 6/11 (54.5%) | **Unresolved gap** — not pagination (D-023 fix applied), not a Sinbundang name-collision artifact (D-033 confirmed same-line) |
| 강남 | 1002000222 | 1002 (Line 2) | 9/9 → 11/11 → 4/4 (100% every run) | Same line, different platform/direction code as above — clean |
| 안국 | 1003000328 | 1003 (Line 3) | 4/4 (100%) | Demo corridor origin-side subway station |
| 교대 | 1003000340 | 1003 (Line 3) | 4/4 (100%) | Demo corridor transfer station, Line 3 side |
| 역삼 | 1002000221 | 1002 (Line 2) | 5/5 (100%) | Demo corridor destination |

## Interval width

Not yet separately tabulated across a large sample — the sequences
recorded in `../05_DECISION_LOG.md` (D-021, D-026, D-034) show
transitions typically spanning one to a few poll intervals (12–15s
polling used this session), consistent with real dwell-time-scale
transitions rather than noise. A dedicated interval-width histogram is
still open work.

## Contradictions / false repeats

None observed yet in this session's samples — no train was seen
regressing from a higher-progress code back to `99`, and no
`arvlCd=1` was seen repeating for the same train at the same station
across multiple non-consecutive polls in a way that would suggest a
stale/duplicate business record.

## Train ID instability

- 시청/Line 1, train `5166`: appeared in `realtimeStationArrival` 4
  times across the session but was never once seen in
  `realtimePosition` for Line 1, at any polling window. Cause unknown.
- The unresolved 강남/`1002000201` gap (5 of 11 trains never joined,
  D-026) is the more serious instance of the same symptom, still open.

## Line-specific failure

**Yes — this rule is not yet citywide-safe.** Line 2 at station code
`1002000201` shows a real, reproducible ~45% non-join rate that
survived every hypothesis tested so far (pagination, cross-line name
collision, geographic coverage, direction/updnLine — see D-026/D-027).
The *same* line, a different station/platform code (`1002000222`), and
a *different* line entirely (Line 3, this session's D-034) show clean
100% joins. This means the gap is not simply "Line 2 is unreliable" —
it is narrower and stranger than that, and still unexplained.

## Verdict

**CONDITIONAL, v0.** Usable now for the Demo Corridor's specific
stations (안국/교대/역삼 all 100% in this session) — Spike E can proceed
on the rule as stated. **Do not** generalize this rule as
citywide-reliable, and do not build alerting/SLA logic around join
rate until the `1002000201`-style gap has a root cause (next session:
rule out dispatch/train-ID-reuse patterns specific to that platform
code, since geography/direction/pagination/cross-line-naming are all
ruled out).

## Next version triggers

Bump to v1 when either:
1. The `1002000201` gap gets a confirmed root cause, or
2. A second unrelated station reproduces the same "same line, same
   pagination-correct totalCount, still ~50% gap" symptom (which would
   suggest a real systemic cause rather than one anomalous
   station/platform code)
