# ID Mapping

> Identity fields actually confirmed by live Spike calls (see
> `../05_DECISION_LOG.md` D-013–D-019), not the team doc's original
> candidates. Where a field name differs from what the checklist assumed,
> the checklist's name is noted as superseded.

## Bus

| Concept | Field | Source API | Status |
|---|---|---|---|
| Route | `busRouteId` (9-digit internal id, e.g. `100100118` for route 753) | arrival, position, route master — consistent across all three | VERIFIED |
| Route (public number) | `busRouteNm`/`busRouteAbrv` (e.g. `753`) | route master (`getBusRouteList`) | VERIFIED — resolve via `resolve_bus_route.py` before calling arrival/position |
| Vehicle | `vehId` | arrival (`vehId1`/`vehId2`) direct-matches position (`vehId`) | VERIFIED — 100% join rate (2026/2026) over a ~10min sustained run, route 753 |
| Stop | `arsId` (arrival), `sectionId`/`lastStnId` (position) | arrival vs position | **NOT YET cross-checked** — arrival exposes `arsId`, position exposes `sectionId`/`lastStnId`, no confirmed direct equivalence yet |

Superseded: checklist assumed `nextStId` on position — this field does not
exist in the real response (D-014).

## Subway

| Concept | Field | Source API | Status |
|---|---|---|---|
| Line | `subwayId` (e.g. `1001` = Line 1, `1032` = another line) | arrival, position — consistent | VERIFIED |
| Station | `statnId` | arrival, position | VERIFIED (same station, same id, across both calls at 시청) |
| Train | `btrainNo` (arrival) / `trainNo` (position) | sustained runs at 시청/Line 1 and 강남/Line 2 | **VERIFIED, GO on Line 1** (91.7% join, 11/12, after fixing a pagination bug) — **CONDITIONAL on Line 2** (54.5%, 6/11; not explained by pagination this time, cause open per D-026) |
| Destination station | `bstatnId`/`bstatnNm` (arrival) / `statnTid`/`statnTnm` (position) | both present, not yet cross-checked for consistency | TO_VERIFY |

## Mixed route

Working (D-024) — real call returned bus `routeId` values (e.g.
`100100023`) in the same numeric domain as `getArrInfoByRouteAll`/
`getBusPosByRouteSt`/`getBusRouteList`, though not yet directly
cross-queried to prove the join. No subway leg (`railLinkList` populated)
observed yet in the one corridor tested — station/line ID mapping against
the realtime subway APIs is still open, pending a demo corridor that
actually forces a bus+subway transfer.

## Historical bus section (OA-21217)

**DROPPED (D-028)** — this turned out to be a weekly/monthly ZIP file
download, not a pollable OpenAPI, and its data.seoul.go.kr page shows a
service-termination notice. PM decided to drop it as a baseline
candidate; no ID mapping work needed here.
