# EVD-SCHED-001 — Subway Timetable / Future WAIT Source

**Status: CONDITIONAL**

## Claim under test

OA-22522 (서울교통공사_서울 도시철도 열차운행시각표) can identify 안국3,
교대3, 교대2, 역삼2 by station code, and provides DAY/SAT/END,
direction, and arrival/departure time fields usable as a future
`SUBWAY_WAIT` source candidate.

## What was done

Downloaded the live file (43.69 MB, 2026-08-22, with user permission):
`서울교통공사_도시철도열차운행시각표(250930).csv` — 532,832 rows.
Filtered for the four Route A station/line pairs and computed real
headway statistics.

## Result — station identity (`SI_ID`)

| Line | Station | `SI_ID` | rows (all weektags) |
|---|---|---|---|
| 3 | 안국 | `0318` | 1,118 |
| 3 | 교대 | `0330` | 1,118 |
| 2 | 교대 | `0223` | 1,554 |
| 2 | 역삼 | `0221` | 1,554 |

**Crosswalk observed:** each `SI_ID` equals the mixed-route API's
station code (`fid`/`tid`) with the trailing zero dropped — `0318` ↔
`03180`, `0223` ↔ `02230`, `0221` ↔ `02210`. This holds for 3 of 4
stations. **교대(3호선) is a confirmed exception**: the naive pattern
predicts SI_ID `0330` ↔ statnId `...330`, but the sustained live
collection this session (`SUBWAY_SUSTAINED/derived/metrics_raw.json`,
100% train-join confirmed) shows 교대(3호선)'s real realtime `statnId`
is **`1003000340`** — matching `ID_MAPPING.md`'s existing value, not
the pattern's prediction. So `ID_MAPPING.md` was correct; the /10
pattern is a useful heuristic for 3 of these 4 stations but not a
guaranteed rule and must not be trusted uncross-checked for any station
not already live-verified.

## Result — WEEKTAG / INOUTTAG / rollover

- `WEEKTAG` values present: `''` (blank), `DAY`, `SAT`, `END` — matches
  the execution contract's expectation.
- `INOUTTAG` uses **`UP`/`DOWN` for Line 3** but **`IN`/`OUT` for Line
  2** — an internal vocabulary inconsistency in the source file itself,
  not an error in our parsing. Any consumer must map per-line, not
  assume one enum across lines.
- 4,475 of 532,832 rows (0.8%) carry a `STT`/`EDT` value ≥ `24:00:00`
  (next-day rollover notation) — confirms the execution contract's
  concern that 24h+ parsing must be handled; a naive `HH:MM:SS` parser
  will break on ~1 row in 120.

## Result — headway feasibility (DAY weektag)

| Line/Station/Direction | scheduled trains | headway min/median/max (s) | mean (s) | service window |
|---|---|---|---|---|
| 3 / 안국 / DOWN | 192 | 180 / 330 / 1380 | 363.6 | 05:34–24:51 |
| 2 / 역삼 / IN | 240 | 120 / 270 / 990 | 288.7 | 05:45–24:55 |

A real, non-trivial headway distribution (not a single fixed number)
is directly computable from this file per station/line/direction/
weektag — this is the core requirement for using it as a future
`SUBWAY_WAIT` candidate source.

## Why CONDITIONAL, not VERIFIED

1. **Freshness unverified.** The file is dated 2025-09-30; "today" in
   this execution is 2026-08-22 — an ~11-month gap. Seoul subway
   timetables do change (seasonal/annual adjustments); this package has
   no mechanism to confirm the schedule is still in effect.
2. The 교대(3호선) `SI_ID` vs realtime `statnId` mismatch above is not
   yet resolved to a single crosswalk row (see SUBWAY_SUSTAINED
   evidence for the live cross-check).
3. This establishes **schedule-based** WAIT feasibility only — it does
   not by itself validate that scheduled times track real (delayed/
   early) trains closely enough to be useful for a "Recommended
   Departure" feature; that requires comparing scheduled `STT` against
   the real-time arrival stream, which is out of scope for this
   evidence item (see `SUBWAY_SUSTAINED` for the live-stream side).

## Artifacts

- `raw/OA-22522_도시철도열차운행시각표_20250930.csv` (43.69 MB, full file, UTF-8-BOM)
- `derived/route_a_stations_summary.txt`
- `derived/headway_analysis.txt`

## Reproduction

Downloaded via browser from
https://data.seoul.go.kr/dataList/OA-22522/F/1/datasetView.do →
파일내려받기. Parse with `encoding='utf-8-sig'` (BOM-prefixed UTF-8,
unlike the two OA transfer datasets which are CP949).
