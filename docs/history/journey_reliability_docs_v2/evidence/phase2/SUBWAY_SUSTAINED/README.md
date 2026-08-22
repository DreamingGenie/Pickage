# SUBWAY_SUSTAINED (Phase 2) — EV2-02 Quota-Coordinated Sustained Collection

**Status: CONDITIONAL, worse real-world coverage than Phase 1** — this round's
own real data, not a repeat of the old number.

## What changed vs Phase 1 (PD-033 fix actually applied)

Phase 1's `SUBWAY_SUSTAINED` run used **5 independent concurrent processes**
against one shared `SEOUL_SUBWAY_REALTIME_KEY`. This round used a single
coordinated process (`_scripts/subway_sustained_coordinated.py`) that
round-robins all 5 corridor targets (안국/교대/역삼 arrival, 2호선/3호선
position) sequentially with one countable call budget, exactly the PD-033
fix. That part of EV2-02 is genuinely done — the collection design is no
longer the risk it was.

## What actually happened

Launched 2026-08-22 05:49:37 UTC, `--interval 20 --duration-min 30
--max-calls 900`. Manually force-stopped at ~06:08 UTC (`run.log`'s last
entry is 06:08:17) once it was clear the run could not produce more usable
data (see below) — the remaining ~22 minutes of the 30-minute budget would
only have added more duplicate `ERROR-337` calls, not evidence.

**The daily quota was already effectively exhausted before this round
started**, not by this round's own calls:

| Target | Calls this round | `INFO-000` (success) | `ERROR-337` (quota) |
|---|---|---|---|
| 안국 arrival | 58 | **2** | 56 |
| 교대 arrival | 57 | 0 | 57 |
| 역삼 arrival | 57 | 0 | 57 |
| 2호선 position | 57 | 0 | 57 |
| 3호선 position | 57 | 0 | 57 |

(Totals include this session's earlier single-poll smoke test against 안국,
which is why 안국 arrival's count is slightly higher than the other
targets.) Only **2 real successful calls** landed all round (안국 arrival, at
05:45:49 and 06:00:17 UTC — the second one ~15 minutes after the first,
with `ERROR-337` in between), each returning 4 real trains. That is not
enough data to observe a single `arvlCd` state transition, so **zero new
`ActualArrivalInterval` samples were produced this round** — see
`../vertical_slice_result.json`, `subway_station_line."안국/3호선"`.

## A bug this round's own analysis caught (documented, not hidden)

`subway_sustained_coordinated.py`'s first version only checked
`payload.errorMessage.code` for a quota/business error, matching the
*success* response shape. `ERROR-337`'s actual response shape is flat -
`{"status":500,"code":"ERROR-337","message":"..."}` - with no
`errorMessage` wrapper at all. The auto-stop-on-quota-error logic in the
script therefore never fired, and the loop ran its full budget logging
"saved ..." for every call without ever surfacing that ~98% of them were
silent failures. Fixed in the committed version of the script (checks
both shapes) - flagged here as the same class of lesson as Phase 1's own
train-join bug: **verify the actual error response shape live, don't
assume the documented/success shape covers the error case.**

## What this means for PD-033 / EV2-02

- The *design* fix (one coordinated process, no independent concurrent
  pollers on the same key) is real and should stay.
- The *quota* itself is the unresolved variable: this session's quota
  usage carried over from earlier same-`calendar day` work (this
  project's own Phase 1 run, executed earlier the same 2026-08-22), and a
  coordinated single process cannot create budget that already do not
  exist. **A shared 1,000-calls/day key means a second same-day
  collection attempt can start with near-zero budget left, independent of
  how well-behaved that second attempt's own code is.**
- The intermittent success (one call ~15 min after the first) is real but
  its mechanism is not verified here - it could be a secondary
  per-minute/per-second limiter layered under the daily cap, a delayed
  counter reconciliation, or something else. Not enough evidence exists
  in this round to characterize it; flagged as an open question rather
  than a guess.

## Proposed follow-up (not executed this round)

- Re-run this exact script (`--interval 20 --duration-min 60 --max-calls
  900`) at the start of a calendar day with no prior same-day usage, to
  measure real coverage under the PD-033-compliant design in isolation
  from same-day carryover.
- Or request a quota-tier increase for `SEOUL_SUBWAY_REALTIME_KEY`
  (already flagged as a real option in `00_MASTER_INDEX.md` framing of
  PD-033).

## Artifacts

- `run.log` — the coordinated collector's own round-by-round log
- Raw samples: `baseline/phase0/data/samples/seoul_subway/{realtimeStationArrival,realtimePosition}/2026-08-22/` (gitignored bulk; not copied into this evidence folder given how little of it is usable — the 2 real successes are referenced by timestamp above, not duplicated as files)
- `../_scripts/subway_sustained_coordinated.py` — the collector, with the `_quota_error_code` fix
