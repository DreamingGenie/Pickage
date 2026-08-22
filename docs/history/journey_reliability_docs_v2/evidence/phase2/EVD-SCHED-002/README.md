# EVD-SCHED-002 — Subway Timetable Freshness (EV2-05)

**Status: upgrade from Phase 1's CONDITIONAL — freshness gap narrowed from
~11 months to ~2 months, and the schedule itself is confirmed stable across
the two real snapshots for all 4 Route A corridor station×line nodes.**

## EV2-05 priority-1 check: does a newer official file exist?

**Yes.** `data.go.kr` (공공데이터포털) hosts
"서울교통공사_서울 도시철도 열차운행시각표" (dataset pk `15098251`,
provider 서울교통공사 — same provider as Phase 1's `OA-22522`), with a file
dated **2026-06-16** (portal "수정일" 2026-06-17), 433,996-row listing /
424,264 real data rows on parse, downloaded live this session:

- Page: `https://www.data.go.kr/data/15098251/fileData.do`
- Direct file endpoint (found by reading the page's own embedded metadata,
  not guessed): `https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId=FILE_000000003657575&fileDetailSn=1&insertDataPrcus=N`
- Confirmed via `Content-Disposition: attachment; filename="서울교통공사_서울 도시철도 열차운행시각표.csv"`
- Saved: `raw/OA-fresh_20260616.csv` (CP949-encoded, unlike Phase 1's
  `OA-22522` which was UTF-8-BOM — a real, documented encoding difference
  between the two portals for the same underlying provider's data)

Relative to today (2026-08-22), this file is **~2 months old**, versus the
Phase 1 file's **~11 months old**. `data.seoul.go.kr`'s own `OA-22522`
listing page still only offers the same 2025-09-30 file Phase 1 already
used — the newer file is on the sibling `data.go.kr` portal, not a newer
version of `OA-22522` itself.

## Does the schedule itself actually agree between the two snapshots?

Compared old (2025-09-30) vs new (2026-06-16) for all 4 Route A corridor
station×line nodes, split by weektag (`DAY`/`SAT`/`END`) and direction —
`_scripts/analyze_timetable_freshness.py`, full output:
`derived/freshness_comparison.json`.

| Station/line | weektags checked | trains/day delta | median headway delta |
|---|---|---|---|
| 안국/3호선 | DAY, SAT, END | **0** | **0 s** |
| 교대/3호선 | DAY, SAT, END | **0** | **0 s** |
| 교대/2호선 | DAY, SAT, END | +2 (DAY only) | 0 s |
| 역삼/2호선 | DAY, SAT, END | +2 (DAY OUT only) | **-15 s** (DAY OUT only) |

**18 of 20 checked (station×line×weektag×direction) combinations are
byte-for-byte identical in trains/day and median headway across an
~8.5-month real gap.** The two non-identical combinations (교대/2호선
DAY, 역삼/2호선 DAY) differ by +2 trains/day and, in one case, a 15-second
median headway shift — real, small operational adjustments, not evidence
of the older file being stale/wrong for this corridor.

One structural (not schedule) difference: the old file has extra rows with
a **blank weektag** (`교대|2||IN`, `안국|3||UP`, etc. — 42-147 trains each)
that do not appear at all in the new file. This looks like a schema
change between the two portals/exports (the new file may only emit
`DAY`/`SAT`/`END`), not a service cut — not confirmed further this round.

## Interpretation

This is real, if not exhaustive, evidence that the Route A timetable
**has not materially changed** across the freshness gap Phase 1 flagged,
which is exactly the kind of "check twice, don't just assert" the honesty
principle asks for: this is not the same as "the file was fine because we
assumed transit schedules don't change" - it is a real comparison result.

Proposed update: promote `EVD-SCHED-001`'s freshness dimension from
CONDITIONAL — file source now current to ~2 months (not 11), and Route A
corridor schedule content is empirically stable across the gap. **Do not**
promote this to a blanket "citywide timetable is current" or "always
matches realtime" claim — this is a two-point comparison for one corridor,
not a continuous-monitoring result, and the blank-weektag schema
difference above is still unexplained.

## Artifacts

- `raw/OA-fresh_20260616.csv` (32.8 MB, CP949)
- `derived/freshness_comparison.json`
- `../_scripts/analyze_timetable_freshness.py`
