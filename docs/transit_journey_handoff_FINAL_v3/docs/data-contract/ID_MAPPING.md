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
| Train | `btrainNo` (arrival) / `trainNo` (position) | sustained runs at 시청/Line 1, 강남/Line 2, and 안국·교대·역삼/Line 3 & 2 | **VERIFIED, GO on Line 1** (91.7%, 11/12) **and Line 3** (100%, 안국·교대 4/4 each, D-034) — **CONDITIONAL on Line 2**: one station/platform code (`1002000201`) shows a persistent 54.5% (6/11) gap not explained by pagination, geography, direction, or cross-line naming (D-026/D-027/D-032/D-033); two *other* Line 2 codes (`1002000222`, `1002000221`/역삼) are 100% clean. See `SUBWAY_ACTUAL_RULE_V0.md` |
| Destination station | `bstatnId`/`bstatnNm` (arrival) / `statnTid`/`statnTnm` (position) | both present, not yet cross-checked for consistency | TO_VERIFY |

## Mixed route

Working (D-024) — real call returned bus `routeId` values (e.g.
`100100023`) in the same numeric domain as `getArrInfoByRouteAll`/
`getBusPosByRouteSt`/`getBusRouteList`, though not yet directly
cross-queried to prove the join. Subway legs (`railLinkList` populated)
confirmed present in later corridor tests (D-029), and the demo
corridor's subway leg was directly cross-checked against the realtime
APIs (D-034) — **but the station identifiers do not match directly**:

| Station | Mixed-route API code (`fid`/`tid`) | Realtime API `statnId` |
|---|---|---|
| 안국 | `03180` | `1003000328` |
| 교대 (3호선 side) | `03300` | `1003000340` |

**No shared ID space.** To actually join a mixed-route response's
subway leg to the realtime arrival/position APIs in production, a
crosswalk table (built from station name + line, or coordinates) is
needed — this is not yet built. TO_VERIFY/TO_BUILD before Spike E's
vertical slice can programmatically pull realtime data for whatever
subway leg a route response returns.

## Historical bus section (OA-21217)

**DROPPED (D-028)** — this turned out to be a weekly/monthly ZIP file
download, not a pollable OpenAPI, and its data.seoul.go.kr page shows a
service-termination notice. PM decided to drop it as a baseline
candidate; no ID mapping work needed here.
