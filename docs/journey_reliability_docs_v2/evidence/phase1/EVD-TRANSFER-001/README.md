# EVD-TRANSFER-001 — 교대 3→2 Static Transfer Row

**Status: VERIFIED (real rows found in both official datasets) — with a contract conflict flagged**

## Claim under test

A real, sourced row exists for the 교대역 3호선→2호선 transfer in
OA-22521 (서울교통공사_서울 도시철도 환승정보) and/or OA-13290
(서울교통공사_환승역거리 소요시간 정보).

## What was done

Downloaded both datasets live from data.seoul.go.kr (2026-08-22, with
user permission — see download log) and filtered for 교대 rows.

- OA-22521 file: `서울교통공사_수도권 도시철도 환승 데이터_20250317.csv` (0.08 MB, dataset last updated 2025-03-17 per site listing)
- OA-13290 file: `서울교통공사_환승역거리 소요시간 정보_20250331.csv` (< 0.01 MB, dataset last updated 2025-03-31)

Both files are CP949-encoded (not UTF-8) — noted for anyone re-parsing
the raw CSVs directly.

## Result — OA-22521 (door/car-specific rows)

4 real rows for 교대(3호선, code `0330`) → 교대(2호선, code `0223`)
(`고유번호` 178–181), varying only by alighting car/door and boarding
direction (강남 방면 / 서초 방면):

| from car-door | to car-door | to direction | 소요시간 |
|---|---|---|---|
| 7-4 | 1-2 | 강남 방면 | 02:24 |
| 4-2 | 1-2 | 강남 방면 | 02:24 |
| 8-3 | 1-2 | 서초 방면 | 02:24 |
| 3-2 | 1-2 | 서초 방면 | 02:24 |

All four car/door variants give the same **02:24 (144 s)**.

## Result — OA-13290 (station-level reference)

| 호선 | 환승역명 | 환승노선 | 환승거리 | 환승소요시간 |
|---|---|---|---|---|
| 2 | 교대 | 3호선 | 75 m | 01:03 |
| 3 | 교대 | 2호선 | 75 m | 01:03 |

75 m ÷ 1.2 m/s ≈ 62.5 s ≈ **01:03 (63 s)** — matches the dataset's own
documented 1.2 m/s walking-speed formula (Source Register §4).

## Contract conflict found

**OA-22521's real door-to-door time (144 s) is 2.3x OA-13290's
generic distance-based reference time (63 s) for the same physical
transfer.** Both are official 서울교통공사 datasets, both dated 2025,
neither is stale relative to the other. This is not a data error on our
part — it reflects that OA-13290's number is a straight-line/walking-
speed formula from a station-to-station distance, while OA-22521's
number is a real measured door-specific path that likely includes
stairs/escalators/corridor turns 75 m of straight-line distance does
not capture.

**Recommendation:** use OA-22521's 02:24 as the reference `TRANSFER`
leg duration for 교대 3→2 (it is the more operationally realistic,
door-specific value), and treat OA-13290's 01:03 as a lower-bound/
sanity-check figure only — not as an alternate candidate to average
against. Do not silently pick one without recording both, since a
future re-check against a different transfer's rows may show a smaller
gap.

## Artifacts

- `raw/OA-22521_수도권도시철도환승데이터_20250317.csv` (full dataset, CP949)
- `raw/OA-13290_환승역거리소요시간정보_20250331.csv` (full dataset, CP949)
- `derived/oa22521_seocho_rows_preview.txt`, `derived/oa13290_seocho_rows_preview.txt`

## Reproduction

Both files were downloaded via browser from:
- https://data.seoul.go.kr/dataList/OA-22521/F/1/datasetView.do
- https://data.seoul.go.kr/dataList/OA-13290/F/1/datasetView.do

Parse with `encoding='cp949'` (not UTF-8/CP949 auto-detect fails
silently and produces mojibake).
