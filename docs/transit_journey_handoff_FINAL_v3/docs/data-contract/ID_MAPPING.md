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
| Vehicle | `vehId` | arrival (`vehId1`/`vehId2`) direct-matches position (`vehId`) | VERIFIED (1 snapshot; join-rate % pending sustained collection) |
| Stop | `arsId` (arrival), `sectionId`/`lastStnId` (position) | arrival vs position | **NOT YET cross-checked** — arrival exposes `arsId`, position exposes `sectionId`/`lastStnId`, no confirmed direct equivalence yet |

Superseded: checklist assumed `nextStId` on position — this field does not
exist in the real response (D-014).

## Subway

| Concept | Field | Source API | Status |
|---|---|---|---|
| Line | `subwayId` (e.g. `1001` = Line 1, `1032` = another line) | arrival, position — consistent | VERIFIED |
| Station | `statnId` | arrival, position | VERIFIED (same station, same id, across both calls at 시청) |
| Train | `btrainNo` (arrival) / `trainNo` (position) | direct match confirmed for trains 0224, 0823, 0825 at 시청/Line 1 | VERIFIED for 1 station/1 snapshot — **CONDITIONAL** until sustained collection confirms no reuse/collision |
| Destination station | `bstatnId`/`bstatnNm` (arrival) / `statnTid`/`statnTnm` (position) | both present, not yet cross-checked for consistency | TO_VERIFY |

## Mixed route

Blocked (D-019) — no ID mapping possible yet until the
`DATA_GO_TRANSIT_PATH_KEY` is approved for service 15000414.

## Historical bus section (OA-21217)

Not yet tested. The route/stop ID domain used by that historical dataset
vs the realtime `busRouteId`/`arsId` domain is unconfirmed — this is the
single biggest remaining unknown for Spike D (Task F).
