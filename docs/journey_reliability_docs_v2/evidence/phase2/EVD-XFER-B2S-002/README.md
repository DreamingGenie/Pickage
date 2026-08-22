# EVD-XFER-B2S-002 — BUS_TO_SUBWAY Station-Internal Access Search (EV2-06)

**Status: still `UNMODELED_UNCERTAINTY` for the actual transfer time — this
round found a real, reproducible partial reference, not a source for a walk
time.**

## What was searched

Official 서울/서울교통공사 sources for an entrance→platform walk time or
distance at 안국역 (the station-internal component
`EVD-XFER-B2S-001`/`00_MASTER_INDEX.md`'s "1. Station internal
entrance→platform walk time" blocker is about). No dataset providing a
direct entrance→platform walking time or horizontal concourse distance was
found on `data.seoul.go.kr`.

## What was found instead: 서울교통공사_역사심도정보 (`OA-13305`)

A real official dataset gives **station depth**, not entrance→platform
walk time: `지반고`(ground level) − `레일면고`(rail level) = station depth,
in two variants (rail-based, platform-based). Downloaded live this session
(most recent file, `20241104`, POST to
`//datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do` with
`infId=OA-13305&seq=11&infSeq=1`, confirmed via
`Content-Disposition: ...역사심도정보_20241104.csv`):

**안국역 (Line 3): platform-based depth = 18.81 m** (`raw/station_depth_20241104.csv` row 71).

## Why this is NOT converted into a transfer-time number

- It is a **vertical** measurement only — no horizontal concourse/corridor
  distance from any specific entrance is in this dataset, and 안국역 has
  multiple numbered entrances with different horizontal distances to the
  platform.
- Converting a vertical depth into a walk time requires a stairs/escalator
  descent-rate assumption that no official source in this package
  provides. Inventing one (e.g. "assume X m/s down stairs") is exactly the
  arbitrary-fallback behavior `10_PHASE2_EVIDENCE_EXECUTION.md` EV2-06 and
  `PD-021` prohibit — a made-up constant would look like real data once
  it's baked into a `point_time_sec` field.

**Conclusion: `EVD-XFER-B2S-001`'s `station_internal_time_source` stays
`NONE` / `uncertainty_model=UNMODELED`, unchanged from Phase 1.** This
search closes the "did we actually look" question for EV2-06 (yes, found a
related official dataset, assessed it, and it is real but insufficient by
itself) without inventing a number to fill the gap.

## Reusable artifact

`OA-13305` (역사심도정보) is registered here as a genuine, reproducible
partial source — if a future round finds an official horizontal-distance
or stairs/escalator-rate source, this depth figure could combine with it
into a real (not fabricated) entrance→platform estimate. Until then it
stays a standalone geometric fact, not a travel-time claim.

## Artifacts

- `raw/station_depth_20241104.csv` (15 KB, CP949, 서울교통공사_역사심도정보)
- `derived/anguk_depth_row.txt` (extracted 안국 row)
