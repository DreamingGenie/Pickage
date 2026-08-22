# EVD-WAIT-002 — Bus WAIT Event-Unit Analysis (EV2-04)

**Status: CONDITIONAL** — PD-034's dependence claim is now quantified with
a real number, but the "distinct vehId1 turnover" event definition itself
turned out to have a real, previously-unconsidered flaw at this specific
stop.

## Target

147 boarding stop, `stId=122000005` (`staOrd=41` — the same node used as
the mixed-route `fid` join for Route B in `EVD-CROSS-002`). Real 30-minute
live collection this session (90 arrival polls, 20 s interval,
`collector_version=spike-v1-ev2-01`).

## 1. Raw snapshot series: dependence, quantified

`exps1` (candidate ETA seconds) lag-1 autocorrelation across the 90-poll
series: **0.77**. This is the first real number behind Phase 1's/`PD-034`'s
qualitative claim that 20-second `exps1` snapshots are not independent
headway samples — 0.77 is high serial correlation, consistent with the
same physical vehicle's approach being re-observed on most consecutive
polls.

`exps1` median across the whole series: **5 seconds** — the target stop is
almost always showing an imminent arrival, consistent with §"a real,
if awkward, finding" below.

## 2. Event-based headway: a real problem with the simple definition

Distinct-`vehId1`-turnover events (poll-to-poll `vehId1` change) produced
**6 turnover events**, real wall-clock gaps:
`[20.08, 20.08, 20.10, 20.06, 20.07, 20.07]` seconds — **median 20.08 s**.

**This is not a real headway distribution — it is (very close to) the poll
interval itself (20 s).** That is a red flag, not a result: it means
`vehId1` at this specific stop is reassigning to a *different* candidate
vehicle on nearly every single poll, rather than the same vehicle
persisting across several polls before a real headway gap to the next one.
Combined with the `exps1` median of 5 seconds above, the likely explanation
is that `stId=122000005` sits very close to route 147's dispatch/staging
point, where multiple buses are simultaneously "about to depart" and the
API's "next predicted vehicle" slot flips between them administratively —
not the same thing as a passenger-relevant vehicle-arrival headway.

**This is a real methodological finding, not a data problem**: a
"distinct vehId1 turnover = one headway event" definition, applied naively,
can be dominated by dispatch-list churn at a terminal-adjacent stop rather
than measuring real inter-arrival gaps. `43_VALIDATION_PLAN.md` §8.0's
"support count 전에 무엇이 한 sample인지 정의한다" instruction is *more*
right than this round's fixture-level implementation managed to satisfy —
the sample-unit definition itself needs stop-topology awareness (e.g.
exclude/relabel stops within N meters of a known dispatch point) before
it is trustworthy, not just "count vehId1 changes."

## 3. Recommendation for `43_VALIDATION_PLAN.md`

- Do **not** use this round's 20.08 s "median event headway" as a real
  147 boarding-stop headway value — it is a measurement artifact of stop
  topology, not a passenger-relevant number.
- A better event definition for a future round: only count a turnover as
  a real arrival/departure event when the *previous* vehId's `exps1`
  actually reached (near) 0 before the change, not merely "the identifier
  in the vehId1 slot changed."
- Re-run this analysis at a stop known NOT to be near a terminal/dispatch
  point (e.g. mid-route) as a comparison baseline.

## Artifacts

- `derived/wait_semantics.json`
- `../_scripts/analyze_wait_semantics.py`
