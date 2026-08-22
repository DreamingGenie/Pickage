# Phase 1 Evidence Validation Report

**Executed:** 2026-08-22, 03:37–04:55 UTC (12:37–13:55 KST)
**Executor:** Claude Code agent, per
`docs/journey_reliability_docs_v2/docs/00_governance/09_PHASE1_EVIDENCE_EXECUTION.md`
**Canonical `LOCKED` documents were not modified.** All findings below are
proposals for the document owners to apply through the Freeze Rule
(`00_MASTER_INDEX.md` §6).

---

## 1. Executive Summary

Ten evidence items (EV-01 through EV-10) were executed against real,
live external APIs and two newly downloaded official Seoul open-data
files — no fabricated numbers. Six items reached a clean **VERIFIED**
status this round (EV-01/`EVD-CROSS-002`, EV-02/`EVD-ACCESS-001`,
EV-04/`EVD-DEST-001`, EV-05/`EVD-TRANSFER-001`, EV-07/`EVD-WAIT-001`,
and the subway ID crosswalk inside EV-08). Four remain **CONDITIONAL**
(EV-03/`EVD-XFER-B2S-001`, EV-06/`EVD-SCHED-001`, EV-08 sustained
coverage, EV-09 target-leg residual) for reasons documented per item
below — mostly real environmental limits (a shared API daily quota,
schedule-data staleness, high real-world traffic variance), not
execution failures.

Two genuine cross-source **contract conflicts** were found and are
flagged for PM/Data decision in §14. One methodology bug in this
session's own analysis (a train-join computation that mixed two
subway lines together) was caught and corrected before being reported
— see `SUBWAY_SUSTAINED/README.md` for the honest before/after.

No Web App, backend, Kafka/Flink/Spark, or probability-engine
implementation was built, per the execution contract's prohibitions.

## 2. Execution Environment

- Platform: Windows 11, Git Bash + PowerShell, Python 3.12.0,
  `requests 2.34.2`, `python-dotenv 1.2.2`
- Outbound network access confirmed to all required hosts
  (`data.seoul.go.kr`, `ws.bus.go.kr`, `swopenAPI.seoul.go.kr`,
  `apis.openapi.sk.com`) before starting
- Real API keys (already present in
  `docs/journey_reliability_docs_v2/.env`, gitignored) were copied —
  **with explicit user permission**, requested and granted mid-session
  — into `baseline/phase0/scripts/spikes/.env.local` (also gitignored)
  so the existing Phase 0 spike harness could make live calls.
  No secret value was ever printed to a log, this report, or any
  evidence artifact.
- Two official Seoul open-data CSV files were downloaded from
  `data.seoul.go.kr` — **with explicit user permission**, requested
  and granted mid-session — in addition to the OA-22521 file already
  anticipated by the execution contract:
  - OA-22521 (0.08 MB), OA-13290 (<0.01 MB), OA-22522 (43.69 MB)
- All raw samples use the inherited Phase 0 Bronze-contract writer
  (`common/storage.py`) — sha256-hashed payload, `requested_at`/
  `received_at`, sanitized params (no secret ever embedded)

## 3. Evidence Status Summary

| ID | Status | Scope/support | Artifact |
|---|---|---|---|
| `EVD-CROSS-002` (EV-01) | **VERIFIED** | Route B corridor, live E2E + 1h sustained 147 | `evidence/phase1/EVD-CROSS-002/`, `EVD-WAIT-001/` |
| `EVD-ACCESS-001` (EV-02) | **VERIFIED** | Demo origin→춘추문, 1 real TMAP call | `evidence/phase1/EVD-ACCESS-001/` |
| `EVD-XFER-B2S-001` (EV-03) | **CONDITIONAL** | Street part only; station-internal part `UNMODELED_UNCERTAINTY` | `evidence/phase1/EVD-XFER-B2S-001/` |
| `EVD-DEST-001` (EV-04) | **VERIFIED** (as `STATION_CENTER`, not exit) | 역삼→멀티캠퍼스, 2 real calls (geocode + route) | `evidence/phase1/EVD-DEST-001/` |
| `EVD-TRANSFER-001` (EV-05) | **VERIFIED** | Real rows in both OA-22521 and OA-13290 — **conflicting values, both real** | `evidence/phase1/EVD-TRANSFER-001/` |
| `EVD-SCHED-001` (EV-06) | **CONDITIONAL** | Real 43.69 MB timetable ingested; schedule freshness unverified (~11mo old) | `evidence/phase1/EVD-SCHED-001/` |
| `EVD-WAIT-001` (EV-07) | **VERIFIED** (feasibility) | 1h real 147 + 01A wait-candidate samples | `evidence/phase1/EVD-WAIT-001/` |
| Subway sustained (EV-08) | **CONDITIONAL** | Real data, but daily quota hit at ~22–33 min, not the 1h target | `evidence/phase1/SUBWAY_SUSTAINED/` |
| Bus 01A extended (EV-09) | **CONDITIONAL** | Real 1h data, zero errors; target-leg variance still too wide | `evidence/phase1/BUS_01A_EXTENDED/` |
| Volume/Lateness (EV-10) | **CONDITIONAL** | Real volume measured; lateness metric `NOT_AVAILABLE` from this harness | `evidence/phase1/VOLUME_LATENESS/` |

## 4. Route B realtime E2E (`EVD-CROSS-002`)

**VERIFIED.** Every ID in the Route B alternative
(`01A 춘추문→안국역6번출구 → 3호선 안국→압구정 → 147 압구정역4번출구→역삼역6번출구`)
resolves against a live feed:

- Bus leg: mixed-route `fid=122000005`/`tid=122000179` join **exactly**
  against live `stId` in `getArrInfoByRouteAll` — no crosswalk needed,
  confirmed with real `vehId` cross-references between arrival and
  position responses.
- Subway leg: 안국 (`statnId=1003000328`, already known) and
  **압구정 (`statnId=1003000336`, new this session)** both resolve live
  on `subwayId=1003` (Line 3), matching the mixed-route leg's
  `routeNm=3호선`.
- Sustained 1-hour collection on 147 (`EVD-WAIT-001/`) confirmed real
  `BUS_WAIT` sample distributions and 7–9 real `vehId1` transitions
  per stop, closing the `BUS_SKIPPED`/`BUS_WAIT` feasibility question
  that was open at the start of this execution.

Full detail: `evidence/phase1/EVD-CROSS-002/README.md`,
`evidence/phase1/EVD-WAIT-001/README.md`.

## 5. ACCESS_WALK (`EVD-ACCESS-001`)

**VERIFIED.** Live TMAP call, demo origin (`126.9809,37.5825`) →
춘추문 (`126.97965309715137,37.58308213227146`):
**297 m, 245 s.** Coordinate roles recorded (`ORIGIN_POINT`→`BUS_STOP`).
Full detail: `evidence/phase1/EVD-ACCESS-001/README.md`.

## 6. BUS_TO_SUBWAY Transfer (`EVD-XFER-B2S-001`)

**CONDITIONAL.** Street part (bus alight → subway mixed-route node):
live TMAP call, **143 m, 101 s.** The station internal
entrance→platform part is **`UNMODELED_UNCERTAINTY`** — no API in this
package exposes it, and this report does not invent a number for it,
per `PD-028`'s explicit prohibition on silently equating
`STATION_CENTER` with a real transfer time. Full detail:
`evidence/phase1/EVD-XFER-B2S-001/README.md`.

## 7. FINAL_WALK (`EVD-DEST-001`)

**VERIFIED, explicitly as a `STATION_CENTER`-based estimate, not an
exit-based one** (no documented exit for this leg exists anywhere in
the product docs). Live TMAP geocode of "서울특별시 강남구 테헤란로 212"
→ entrance point `127.039533,37.501331`; live TMAP route from 역삼역's
mixed-route node → **329 m, 300 s.** Full detail:
`evidence/phase1/EVD-DEST-001/README.md`.

## 8. 교대 3→2 Transfer (`EVD-TRANSFER-001`)

**VERIFIED — with a contract conflict.** Real rows found in both
official datasets:

- OA-22521 (door-specific, 4 car/door variants): **02:24** consistently
- OA-13290 (station-distance-based, 75 m ÷ 1.2 m/s): **01:03**

**These are both real, both 2025-dated, both official 서울교통공사
sources — and 2.3x apart.** See §14/§16 for the proposed resolution
(use OA-22521's value; keep OA-13290's as a sanity-check floor, not an
alternate candidate). Full detail:
`evidence/phase1/EVD-TRANSFER-001/README.md`.

## 9. Subway timetable / future WAIT (`EVD-SCHED-001`)

**CONDITIONAL.** OA-22522 (532,832 rows, real download) confirms:
station identity for all 4 Route A stations, `DAY`/`SAT`/`END`
weektags, a real headway distribution (e.g. 안국 Line 3 DOWN: 192
scheduled trains/day, median 330 s headway), and confirms the
24-hour-rollover parsing risk is real (4,475 rows, 0.8%, use `≥24:00`
notation). Blocked from VERIFIED by: (a) the file is dated
2025-09-30 — an ~11-month staleness gap against "today"; (b) one
station's `SI_ID`→realtime-`statnId` crosswalk needed live
cross-checking (see §11 — now resolved and documented). Full detail:
`evidence/phase1/EVD-SCHED-001/README.md`.

## 10. Bus future WAIT/headway (`EVD-WAIT-001`)

**VERIFIED as a feasibility claim.** 1 real hour of 147 + 01A
collection, zero API/HTTP errors, produced 181 real `exps1`
WAIT-candidate samples per stop (147: median 239–253 s; 01A: median
190–240 s) and 7–9 real distinct-vehicle transitions per stop —
demonstrating a time-conditioned empirical distribution is
constructible without predicting any specific future vehicle ID. Full
detail: `evidence/phase1/EVD-WAIT-001/README.md`.

## 11. Subway Sustained Collection

**CONDITIONAL.** Real ~22–33-minute effective windows per station
(not the full 1-hour target) because `SEOUL_SUBWAY_REALTIME_KEY` is
shared across all 5 concurrent pollers and hit the documented
1,000-calls/day dev quota (`ERROR-337`) at 04:14:30–04:14:46 UTC — this
is exactly the risk Phase 0's own README warned about, now confirmed
in practice. Within that real window:

- 100% `btrainNo`↔`trainNo` join for all 4 station/line pairs
  (안국/3호선, 교대/3호선, 교대/2호선, 역삼/2호선) — **after correcting
  an analysis bug** that had mixed 교대's two line-nodes together and
  produced a spurious ~55% figure; see the README for the honest
  before/after.
- Live-confirmed `statnId` crosswalk for all 4 stations, including
  resolving 교대/3호선's `1003000340` (confirmed correct — the naive
  `SI_ID`/10 pattern from OA-22522 does NOT hold for this one station).
- Real `arvlCd` distributions and `ActualArrivalInterval` samples
  (11 at 안국, 6 at 교대, 0 at 역삼 in-window) — under-sampled at the
  tails given the shortened window.

Full detail: `evidence/phase1/SUBWAY_SUSTAINED/README.md`.

## 12. Bus 01A Target-leg/Extended Collection

**CONDITIONAL.** Real full 1-hour collection, **zero errors** (the
bus key had adequate quota headroom, unlike the subway key). 11 real
target-leg (춘추문→안국) traverse-time samples: **100 s–1,223 s**
(12x spread) — this confirms, rather than resolves,
`00_MASTER_INDEX.md`'s existing "target-leg maturity 부족" concern.
This is the **first target-leg-specific support this project has**;
Phase 0's "54 transition" figure was explicitly route-level and is not
directly comparable (see `00_MASTER_INDEX.md` §5, already corrected
there). Full detail: `evidence/phase1/BUS_01A_EXTENDED/README.md`.

## 13. Volume/Lateness Profile

**CONDITIONAL.** Real measured volume: 1,930 samples, ~61.8 MB, over
~70 real minutes (~1,650 polls/hour, ~53 MB/hour combined across 6
active provider/API keys this session). `getArrInfoByRouteAll` alone
is 94% of raw bytes (whole-route payload for a 1-2-stop need — a real,
measurable inefficiency worth a product/architecture note). The
contract's specific `received_at - source_generated_at` lateness
metric is **`NOT_AVAILABLE`**: no API in this package exposes that
field generically, and the harness's own timestamp fields
(`requested_at`/`received_at`) are stamped at the same post-response
instant (a Phase 0 harness limitation, not a real 0 ms finding) — this
is reported honestly as unavailable rather than substituted silently.
Full detail: `evidence/phase1/VOLUME_LATENESS/README.md`.

## 14. Contract Conflicts Found

1. **교대 3→2 transfer time: OA-22521 (02:24, door-specific) vs
   OA-13290 (01:03, distance-based) — 2.3x apart, both official, both
   2025-dated.** Neither document currently in this package picks one.
   See §16 for the proposed resolution.
2. **This session's own analysis bug** (train-join computed without
   splitting 교대's two line-nodes by `subwayId` first) produced a
   spurious ~55% join-rate figure before being caught and corrected —
   flagged here as a process learning, not a data conflict: any future
   Phase 2 collector reusing "join by station name" logic for a
   multi-line station must split by `subwayId`/line first.
3. **`SI_ID`(OA-22522)→realtime `statnId` crosswalk is not a reliable
   arithmetic pattern** — holds for 3 of 4 Route A stations but not
   교대/3호선. Any future station added to this project must be
   live-cross-checked, not inferred from the pattern.
4. **Source Register's own OA-22521 URL is stale**
   (`04_SOURCE_REGISTER.md` §3 lists `/L/1/datasetView.do`; the live,
   working path today is `/F/1/datasetView.do`) — a minor doc-accuracy
   fix, not a data conflict, listed here since it was discovered during
   the same live-navigation work.

## 15. Proposed Evidence Register Updates

(For `03_EVIDENCE_REGISTER.md` — proposal only, not applied)

| ID | Proposed new status | Proposed new claim/scope | Proposed artifact |
|---|---|---|---|
| `EVD-CROSS-002` | TO_VERIFY → **VERIFIED** | Route B E2E interoperability + sustained skip/wait behavior confirmed live | `evidence/phase1/EVD-CROSS-002/`, `EVD-WAIT-001/` |
| `EVD-ACCESS-001` | TO_VERIFY → **VERIFIED** | Demo origin→춘추문, 297m/245s | `evidence/phase1/EVD-ACCESS-001/` |
| `EVD-XFER-B2S-001` | TO_VERIFY → **CONDITIONAL** | Street part 143m/101s VERIFIED; station-internal part `UNMODELED_UNCERTAINTY` | `evidence/phase1/EVD-XFER-B2S-001/` |
| `EVD-DEST-001` | TO_VERIFY → **VERIFIED** | 역삼(`STATION_CENTER` candidate)→멀티캠퍼스, 329m/300s | `evidence/phase1/EVD-DEST-001/` |
| `EVD-TRANSFER-001` | TO_VERIFY → **VERIFIED** | Real rows in both OA-22521 (02:24) and OA-13290 (01:03) — conflict flagged, not resolved to one number | `evidence/phase1/EVD-TRANSFER-001/` |
| `EVD-SCHED-001` | TO_VERIFY → **CONDITIONAL** | Real ingest + crosswalk done; freshness (~11mo) unverified | `evidence/phase1/EVD-SCHED-001/` |
| `EVD-WAIT-001` | TO_VERIFY → **VERIFIED** (feasibility) | 1h real 147+01A wait-candidate samples, no future-vehicle prediction | `evidence/phase1/EVD-WAIT-001/` |
| `EVD-SUB-003` | CONDITIONAL → **VERIFIED** (for the 4 corridor stations specifically) | 100% join re-confirmed on a larger real sample this session (after an analysis-bug fix) | `evidence/phase1/SUBWAY_SUSTAINED/` |
| `EVD-SUB-005` | CONDITIONAL (unchanged) | `arvlCd=1` count now 53 (안국)/40 (교대)/0 (역삼) in a ~25min real window — still not enough for a stable residual distribution | `evidence/phase1/SUBWAY_SUSTAINED/` |
| `EVD-BUS-008` | CONDITIONAL (unchanged, scope corrected) | Now has real target-leg-specific support (11 samples, 100-1223s) distinct from the old route-level 54-transition figure | `evidence/phase1/BUS_01A_EXTENDED/` |

**New evidence IDs to register** (not previously in
`03_EVIDENCE_REGISTER.md`):

- `EVD-VOLUME-001`: real volume profile (1,930 samples/61.8MB/~70min);
  lateness metric `NOT_AVAILABLE` — `evidence/phase1/VOLUME_LATENESS/`

## 16. Proposed Decision Changes

(For `02_DECISION_LOG.md` — proposal only)

1. **Adopt OA-22521's door-specific 02:24 as the reference 교대 3→2
   `TRANSFER` leg duration**; retain OA-13290's 01:03 as a documented
   lower-bound sanity check, not an alternate candidate to blend.
2. **Do not trust the OA-22522 `SI_ID`/10 pattern uncross-checked** for
   any station beyond the 4 already live-verified in this session.
3. **A production sustained-collection design must not share one API
   key across N concurrent pollers at a shared daily quota** without
   either separate keys, a coordinated shared rate budget, or a
   higher-tier quota — this session's ~22-33min real coverage (vs the
   1h target) is the concrete, reproduced cost of not doing so.
4. **`EVD-XFER-B2S-001`'s station-internal entrance→platform time
   should be tracked as an explicit `UNMODELED_UNCERTAINTY` /
   `PLATFORM_REFERENCE`-fallback item**, not silently folded into the
   street-walk number, until a real source for it is found.

## 17. Documents Impacted (proposal only — none edited)

- `03_EVIDENCE_REGISTER.md` — status/claim updates per §15
- `02_DECISION_LOG.md` — new decisions per §16
- `04_SOURCE_REGISTER.md` §3 — OA-22521 URL correction (`/L/1/` → `/F/1/`)
- `00_MASTER_INDEX.md` §1/§4 — several blockers in the "Current Evidence
  Blockers" list are now resolved (items 1-4, 9) or partially resolved
  (item 6, 5) per §15's status table
- `06_TRACEABILITY_MATRIX.md` — trace the new/updated evidence IDs
  above to their consuming requirements
- `08_IMPLEMENTATION_STATUS.md` — record that Phase 1 evidence
  execution ran and its real outcomes

## 18. Remaining Blockers

1. Station internal entrance→platform walk time (`EVD-XFER-B2S-001`) —
   no data source found; needs a new evidence source or an explicit
   fixed-fallback decision.
2. OA-22522 schedule freshness (~11 months old) unverified against
   current real-world subway timetables.
3. Subway sustained collection did not reach its 1-hour target due to
   the shared-key daily quota; a Phase 2 re-run needs either separate
   keys or a coordinated lower combined polling rate.
4. Bus 01A target-leg residual (100 s–1,223 s spread) is still too
   wide/immature for a probability model; needs more time-windows per
   the execution contract's own EV-09 instruction.
5. `EVD-SUB-005`'s `arvlCd=1` (completed-arrival) sample count is still
   thin (0-53 per station in the real window) — sustained completed-
   arrival collection remains insufficient per `00_MASTER_INDEX.md`'s
   pre-existing note, now with a real (if short) number instead of a
   summary-only historical one.
6. `EVD-WAIT-001`'s hour of data is a single time-of-day/weekday
   window — no AM-peak-vs-midday time-bucketing yet.

## 19. Gate Recommendation

- **D4 Data & Probability**: several of its Evidence blockers (§4 of
  `00_MASTER_INDEX.md`, items 1-4 and 9) can be marked resolved per
  this report's §15 — recommend the document owner review and, if
  agreed, run the Freeze Rule to promote D4 past "REVIEW + Evidence
  blockers." Items 6, 7, 8, 10 remain open per §18.
- **D5 Architecture & Operations**: still correctly gated — this
  report's real volume figures (§13) are a first data point, not a
  full profiling exercise; "actual/residual events/hour" and
  partition/watermark/TTL decisions remain explicitly out of this
  round's scope.
- Do **not** promote any gate to `LOCKED` based on this report alone —
  it is Phase 1 evidence, not a team/PM review.

## 20. What Must NOT Be Built Yet

Per the execution contract's explicit prohibitions, none of the
following were built and none should be started on the basis of this
report alone:

- Web App or backend implementation
- Kafka/Flink/Spark streaming infrastructure
- LightGBM/AI model implementation
- Any citywide generalization of the corridor-specific findings above
- A single "resolved" number for the 교대 3→2 transfer conflict
  (§14.1) without a PM/Data decision
- A fixed fallback value for the station-internal entrance→platform
  gap (§18.1) without a PM/Data decision

---

## Appendix: Evidence Folder Index

```
evidence/phase1/
├─ EVD-CROSS-002/       — Route B realtime E2E (VERIFIED)
├─ EVD-ACCESS-001/      — Demo ACCESS_WALK (VERIFIED)
├─ EVD-XFER-B2S-001/    — BUS_TO_SUBWAY transfer (CONDITIONAL)
├─ EVD-DEST-001/        — FINAL_WALK (VERIFIED)
├─ EVD-TRANSFER-001/    — 교대 3→2 static transfer (VERIFIED, conflict flagged)
├─ EVD-SCHED-001/       — Subway timetable (CONDITIONAL)
├─ EVD-WAIT-001/        — Bus future WAIT/headway (VERIFIED, feasibility)
├─ SUBWAY_SUSTAINED/    — EV-08 (CONDITIONAL)
├─ BUS_01A_EXTENDED/    — EV-09 (CONDITIONAL)
├─ VOLUME_LATENESS/     — EV-10 (CONDITIONAL)
└─ _scripts/            — this session's analysis scripts (not part of the
                           Phase 0 spike harness; reused its common/ modules)
```

Each folder's `README.md` is the authoritative per-item writeup;
`derived/metrics_raw.json` (where present) is the machine-readable
backing data; `raw/` holds curated Bronze-contract samples.
