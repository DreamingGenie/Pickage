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

**Bus leg: joins directly, no crosswalk needed.** The demo corridor's
bus leg (route `01A`) has `routeId=100100001` in the mixed-route
response, and `resolve_bus_route.py 01A` independently resolves to the
exact same `busRouteId=100100001` — confirmed identical, not just
"same numeric domain" (D-038). `getArrInfoByRouteAll`/
`getBusPosByRouteSt` can be called directly with this ID.

**Subway leg: does NOT join directly, crosswalk needed.** Subway legs
(`railLinkList` populated) confirmed present in later corridor tests
(D-029), and the demo corridor's subway leg was directly cross-checked
against the realtime APIs (D-034) — **but the station identifiers do
not match directly**:

| Station | subwayId | Mixed-route API code (`fid`/`tid`) | Mixed-route coords (`fx,fy`/`tx,ty`) | Realtime API `statnId` |
|---|---|---|---|---|
| 안국 | 1003 (Line 3) | `03180` | `126.98546,37.57649` | `1003000328` |
| 교대 (3호선 side) | 1003 (Line 3) | `03300` | `127.01379,37.49309` | `1003000340` |
| 교대 (2호선 side) | 1002 (Line 2) | `02230` | `127.01437,37.49385` | `1002000223` |
| 역삼 | 1002 (Line 2, destination) | `02210` | `127.03650,37.50064` | `1002000221` |

**No shared ID space, but a full manual crosswalk for the demo
corridor's 4 station-nodes is now built** (D-047) — every node on the
locked route (안국 → 교대 → 역삼) has a confirmed `fid`/`tid` ↔
`statnId` pair, each independently verified live against the realtime
arrival API (D-034/D-047; 교대의 두 codes were both seen in a single
"교대" name-search response, confirming they're the same physical
station's two line-specific nodes). **This is still a hand-built,
corridor-specific table, not a general station-name/coordinate-based
crosswalk service** — building the latter (e.g. nearest-station-by-
coordinate lookup against a full station master) is still open work
for citywide coverage beyond this one corridor.

## Historical bus section (OA-21217)

**DROPPED (D-028)** — this turned out to be a weekly/monthly ZIP file
download, not a pollable OpenAPI, and its data.seoul.go.kr page shows a
service-termination notice. PM decided to drop it as a baseline
candidate; no ID mapping work needed here.
