# SUBWAY_SUSTAINED — Route A Subway Sustained Collection (EV-08)

**Status: CONDITIONAL** (real sustained data collected and analyzed;
effective window shorter than the 1-hour target due to a real daily
quota exhaustion — see below)

## Target

Route A stations: 안국3, 교대3, 교대2, 역삼2, ≥1 hour, per EV-08.

## What was launched (2026-08-22, local time)

| Process | Command | Started |
|---|---|---|
| 안국 arrival | `subway_arrival_spike.py 안국 --interval 15 --count 240` | 12:41:28 |
| 교대 arrival | `subway_arrival_spike.py 교대 --interval 15 --count 240` | 12:52:39 (relaunched — see incident note) |
| 역삼 arrival | `subway_arrival_spike.py 역삼 --interval 15 --count 240` | 12:52:39 (relaunched) |
| Line 3 position | `subway_position_spike.py 3호선 --interval 15 --count 240` | 12:52:39 (relaunched) |
| Line 2 position | `subway_position_spike.py 2호선 --interval 15 --count 240` | 12:52:39 (relaunched) |

**Incident note (batching bug):** the first launch attempt batched all
5 `nohup ... &` commands in one shell call with only the first prefixed
by `cd`; the other 4 inherited the wrong working directory and exited
immediately with `FileNotFoundError` (kept in this folder's `.log`
files as an honest record, not deleted). Relaunched correctly ~11
minutes later via per-command subshells. 안국 arrival ran the full
original window; the other four have ~11 fewer minutes of coverage.

**Incident note (daily quota):** `SEOUL_SUBWAY_REALTIME_KEY` is shared
across all 5 concurrent pollers (3 arrival + 2 position). Running them
concurrently at 15 s intervals hit the documented 1,000-calls/day dev
quota (`ERROR-337`) partway through, at **04:14:30–04:14:46 UTC**
(≈33 min after 안국 started, ≈22 min after the other four restarted) —
consistent with Phase 0's own "Call budget" warning in
`baseline/phase0/scripts/spikes/README.md`. All 5 collectors correctly
kept polling and correctly recorded the quota-error responses as
Bronze-contract samples (not silently dropped) for the remainder of
their runs; **no data was fabricated to fill the post-quota gap.**

## Result — polls / success / quota / error (from `metrics_raw.json`)

| Station/line | polls | success | quota_exceeded | error |
|---|---|---|---|---|
| 안국 arrival | 241 | 133 | 108 | 0 |
| 교대 arrival | 240 | 88 | 152 | 0 |
| 역삼 arrival | 240 | 88 | 152 | 0 |
| Line 3 position | 241 | 88 | 153 | 0 |
| Line 2 position | 240 | 88 | 152 | 0 |

Zero transport/HTTP errors — every non-success poll was a clean,
well-formed `ERROR-337` quota response, not a network failure.

## Result — real, effective coverage (pre-quota window)

- 안국: 133 successful polls, 532 arrival rows, 16 distinct trains,
  53 `arvlCd=1` ("arrived") sightings, 11 real actual-arrival intervals
  (25–315 s range, median 190 s)
- 교대: 88 successful polls, 704 rows (both line-nodes combined —
  this station's name search returns both), 24 distinct trains
  (12 on 3호선 + 12 on 2호선 after correct per-line splitting), 40
  `arvlCd=1` sightings
- 역삼: 88 successful polls, 352 rows, 11 distinct trains, 0
  `arvlCd=1` sightings in this window (no train happened to reach
  "arrived" state at 역삼 2호선 during the ~22 real-data minutes
  available — a real absence, not a bug)

Full per-station `arvlCd` distributions, duplicate/out-of-order counts,
and `ActualArrivalInterval` widths are in `derived/metrics_raw.json`.

## Result — train join (`btrainNo` ↔ `trainNo`), corrected

**An analysis bug was caught and fixed during this session**: 교대's
name-search arrival response returns rows for BOTH its Line 2 node and
Line 3 node in one payload. The first pass joined all of 교대's trains
against a single line's position feed without splitting by `subwayId`
first, producing a spurious ~55% "join rate" that looked like a real
data-quality gap. After splitting arrival rows by `subwayId` before
joining:

| Station / line | arrival trains (that line only) | joined | rate |
|---|---|---|---|
| 안국 / 3호선 | 16 | 16 | **100%** |
| 교대 / 3호선 | 12 | 12 | **100%** |
| 교대 / 2호선 | 12 | 12 | **100%** |
| 역삼 / 2호선 | 11 | 11 | **100%** |

All four Route A station/line joins are **100%** in this session's
real data — consistent with `ID_MAPPING.md`'s existing Line 3/역삼
claims, and now also confirms 교대(both nodes) at 100% with a larger
sample than the Phase 0 4/4 spot-check.

## Result — `statnId` crosswalk confirmed live

| Station | Line | Confirmed `statnId` |
|---|---|---|
| 안국 | 3호선 | `1003000328` |
| 교대 | 3호선 | `1003000340` |
| 교대 | 2호선 | `1002000223` |
| 역삼 | 2호선 | `1002000221` |

See `EVD-SCHED-001/README.md` for why 교대/3호선's code breaks the
naive OA-22522 `SI_ID`→`statnId` pattern that holds for the other 3
stations.

## Why CONDITIONAL, not VERIFIED

The join/crosswalk claims are cleanly VERIFIED (100%, real data). But
the ≥1-hour sustained-collection *target* itself was not met — real
usable data covers roughly 22–33 minutes per station before the shared
key's daily quota was exhausted. The headway/interval statistics above
are real but drawn from a shorter window than specified, so treat
`p90`/`max` interval widths as under-sampled (few data points at the
tails) rather than a mature distribution.

## Artifacts

- `derived/metrics_raw.json` — full computed metrics
- `log_*.log` — collector stdout, including both incidents
- Raw samples remain in
  `baseline/phase0/data/samples/seoul_subway/.../2026-08-22/`
  (gitignored bulk storage; not duplicated wholesale into this repo)

## Reproduction

```bash
python evidence/phase1/_scripts/analyze_subway_sustained.py
```

## Recommendation for a real Phase 2 run

Either request separate keys per concurrent poller, or serialize the 5
pollers' combined request rate to stay under 1,000/day, or negotiate a
higher-tier quota — this is not a code problem, it is the documented
dev-tier limit being hit exactly as Phase 0 warned it would if run at
short intervals.
