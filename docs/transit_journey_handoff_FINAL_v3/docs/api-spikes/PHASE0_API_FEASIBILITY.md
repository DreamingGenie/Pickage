# Phase 0 API Feasibility Report

> Working document — updated as spikes progress. See `../05_DECISION_LOG.md`
> (D-013 through D-019) for the underlying evidence entries this report
> summarizes. Raw samples referenced below live under
> `../../data/samples/` (gitignored; a curated subset will be added to
> `data/samples/examples/` for reviewers).

**Snapshot date:** 2026-08-21, ~23:45–00:00 KST (single-day, partly
night-time collection — see caveats per section).

## Summary verdict

| Area | Verdict | Confidence |
|---|---|---|
| Bus arrival (`getArrInfoByRouteAll`) | **GO** | High — real endpoint, real data, matches PoC expectations |
| Bus position (`getBusPosByRouteSt`) | **GO** | High — real endpoint (differs from team doc), real data |
| Bus arrival↔position vehId join | **GO** | ~10min/30s-interval run on route 753 (final): **100% join rate (2026/2026)**, 49 real `stopFlag` 0→1 transitions, ~19.8% duplicate `dataTm` ratio. Still 1 route, 1 night window — not yet generalized citywide |
| Subway realtime arrival | **GO** | High — real endpoint, real data |
| Subway realtime position | **GO** | High — real endpoint, real data |
| Subway arrival↔position trainNo join | **GO** (with a code fix) | Initial run showed 75% (6/8) and looked like a data/ID-stability problem; root-caused to our own fixed `0/20` pagination window against a line that actually has 46–53 active trains (D-023). Fixed the script to `0/100`; re-verification with the fix is the next step, not yet re-run |
| Mixed bus+subway route | **GO** | Was misdiagnosed as a key-registration BLOCKER (D-019); actual cause was our own URL typo (`getPathInfoByBusNSubList` → real path drops "List"). Fixed and confirmed live: 20 alternative routes for a real Seoul corridor, `routeId`s in the same domain as the realtime bus APIs |
| Historical bus section join | **NOT YET TESTED** | Pending |

## A. Bus Arrival — `getArrInfoByRouteAll`

- **Tested at:** 2026-08-21 23:46 KST, route 753 (`busRouteId=100100118`, resolved via `getBusRouteList`)
- **Calls:** 1 single-shot + a 20-poll/30s background run (~10 min) in progress
- **Observed schema:** matches checklist closely — `arrmsg1/2`, `vehId1/2`, `exps1/2`, `mkTm`, `arsId`, plus many congestion/occupancy fields (`kalCf*`, `neuCf*`, `avgCf*`) not in the original checklist, all `0` in this sample (unclear if unused at night or unpopulated generally — TO_VERIFY in daytime)
- **Identity:** `vehId1`/`vehId2` present, `0` when no bus assigned to that slot
- **Timestamp semantics:** `mkTm` is **call-level, not per-stop** — all 104 items in one response shared a single `mkTm` value. This differs from a naive per-stop-timestamp assumption.
- **Quality:** at 23:46 KST, 50/104 stop-entries showed `arrmsg1/2 = "운행종료"` (service ended), 54 showed live predictions — night-time route tail-off, expected for an off-peak snapshot, not a data defect
- **Rate limit implication:** dev tier documented as 1,000 calls/day per data.go.kr's page (see `../../scripts/spikes/README.md` for the interval-vs-budget table)
- **Main Use Case mapping:** feeds `PredictionSnapshot` (mode=BUS) in the canonical contract
- **Risks:** single night-time snapshot; daytime collection needed to see the API under real ridership load
- **Next decision:** proceed to a sustained (1h+) daytime collection window before computing real residuals

## B. Bus Position — `getBusPosByRouteSt`

- **Tested at:** same session, `busRouteId=100100118`, `startOrd=1`, `endOrd=110`
- **Observed schema (real, from raw item):** `busType, congetion (sic), dataTm, isFullFlag, lastStnId, plainNo, posX, posY, routeId, sectDist, sectOrd, sectionId, stopFlag, tmX, tmY, vehId`
- **Deviation from team checklist:** `nextStId`/`nextStTm`/generic `rtDist` are **not present** in the real response. `congetion` is the API's actual (misspelled) field name for congestion — must be parsed as-is, not "corrected"
- **Identity:** `vehId` present for all 13 active vehicles in this snapshot
- **Join test:** arrival's `vehId1=111033105` found directly in this position response's vehId set — **the core Spike A hypothesis reproduced on the first live try**
- **Sustained run (~10 min, 30s interval, route 753, final numbers):** 100% vehId join rate (2026/2026 arrival vehId references matched a position vehId), 49 real `stopFlag` 0→1 transitions observed across 13 distinct vehicles, transition width mostly 20–40s (consistent with ~30s polling + real dwell time), ~19.8% (51/257) duplicate `dataTm` per-vehicle observation ratio — see `docs/05_DECISION_LOG.md` D-020 and `scripts/spikes/analyze_samples.py bus 100100118`
- **Risks:** one route, one ~10-minute night-time window; call budget (D-020's ~17% duplicate rate at 30s interval) needs revisiting at other times of day and against the 1,000/day cap
- **Next decision:** **GO** — Spike A's completion criterion (raw→normalized→actual interval→residual reproducible by one script) is met for this route/window. Repeat across more routes/times before citywide generalization

## C. Bus Route Master — `getBusRouteList`

- **Tested at:** same session, `strSrch=753`
- **Result:** resolved `busRouteId=100100118`, `busRouteNm=753`, `stStationNm=구산동`, `edStationNm=상도동`, `term=12`(min), `length=49.2`(km)
- **Note:** `itemCount` field in the header reported `0` despite one real item being returned — likely a header field that doesn't count `itemList` the way its name suggests; TO_VERIFY if this matters for multi-result searches

## D/E. Subway Realtime Arrival/Position

- **Tested at:** 2026-08-21 23:48–23:50 KST, stations 서울역/시청, line 1호선
- **Result:** **both endpoints work with the commonly-documented `swopenAPI.seoul.go.kr` URL pattern** — this was the project's single biggest unknown (team doc marked it HYPOTHESIS/NOT_PROVIDED) and it resolved cleanly on the first real call
- **Observed arrival schema:** matches checklist plus `trainLineNm`, `arvlMsg3`, `ordkey`, `subwayList`, `statnList`, `trnsitCo`; wrapped in an `errorMessage{status,code,message,total}` envelope
- **Observed position schema:** `subwayId, subwayNm, statnId, statnNm, trainNo, lastRecptnDt, recptnDt, updnLine, statnTid, statnTnm, trainSttus, directAt, lstcarAt`
- **Identity / join:** `btrainNo` (arrival) and `trainNo` (position) matched directly for trains `0224`, `0823`, `0825` at 시청 station, Line 1 — **direct confirmation of the project's top-risk join**, on the first snapshot
- **Sustained run (~7.5 min, 15s interval, 시청/Line 1):** trainNo join rate first measured **6/8 (75%)** — but this was a **false alarm**, not a real ID-stability problem. Root cause: our `realtimePosition` call used a fixed `0/20` index range, while Line 1's real `totalCount` fluctuated 46–53 active trains during the window — the two unmatched trains (`5166`, `0226`, confirmed same `subwayId=1001`, not a different line) were simply outside the requested page. Fixed `subway_position_spike.py` to request `0/100` by default (see D-023) and confirmed with one call: `selectedCount == totalCount == 42`, full fleet returned. A sustained re-run to get a real fixed join-rate % (not just "pagination no longer truncates") is still pending.
- **Actual arrival rule candidate — richer than first observed:** sustained collection surfaced state codes `{0,1,2,3,4,5,99}`, not just the `{0,1,2,99}` seen in the single snapshot. Two trains (`0704`, `0825`) showed a clean ordered progression `99 → 5 → 3 → 1 → 2` over ~8 minutes — a real, reproducible state machine, richer than checklist section F's assumed `전역출발→진입→도착→출발` 4-state sequence
- **Timestamp semantics:** `recptnDt` (arrival) and `recptnDt`/`lastRecptnDt` (position) are per-train, not per-call — unlike bus arrival's call-level `mkTm`
- **Risks:** one station, one line, one ~7.5-minute window, and the join rate needs re-measuring now that the pagination bug is fixed. Do **not** finalize `SUBWAY_ACTUAL_RULE_V0.md` yet — the `{0,1,2,3,4,5,99}` code meanings for `3`/`4`/`5` are inferred from ordering, not documented anywhere official
- **Next decision:** re-run the sustained collection with the fixed `--end-ord` default, confirm join rate approaches 100% once pagination is no longer truncating the fleet, then extend to a second line to check whether `3`/`4`/`5` hold the same relative meaning there

## F. Mixed Bus+Subway Route — `getPathInfoByBusNSub`

- **Tested at:** 2026-08-21 23:50 KST (failed) and 2026-08-22 (fixed, succeeded)
- **First result:** HTTP 401 `등록되지 않은 서비스키` — initially misdiagnosed as a key-registration gap (D-019) since all 5 `DATA_GO_*` keys were confirmed byte-identical (one account-wide key), so it looked like this one service just hadn't been approved yet
- **Real root cause (D-024):** a **URL typo in our own code**. The data.go.kr catalog *names* the operation `getPathInfoByBusNSubList`, but the official 활용가이드 document (already sitting in this repo at `docs/api & data/서울특별시_대중교통환승경로 조회 서비스_활용가이드_20211116.docx` — extracted directly from its docx/zip/xml to confirm) shows the real Call Back URL drops the "List" suffix (`getPathInfoByBusNSub`), and the auth parameter is capitalized `ServiceKey`, not `serviceKey`. Requesting the nonexistent `...List` path apparently falls through to the gateway's generic 401 instead of a 404, which reads exactly like an unapproved key even when the key is fine.
- **Fixed and verified:** corrected `mixed_route_spike.py` to the real URL + param casing + `resultType=json`. Real call for 서울역↔강남역 (coords 126.972559,37.554648 → 127.027610,37.498095) returned HTTP 200 with **20 alternative routes**, each a multi-leg `pathList` with `routeId`/`routeNm`/stop names/coordinates
- **ID mapping:** returned bus `routeId` values (e.g. `100100023`) are in the same numeric domain as `getArrInfoByRouteAll`/`getBusPosByRouteSt`/`getBusRouteList` — a real, positive signal for joinability, though not yet directly cross-queried against those APIs
- **Gap:** this particular corridor returned bus-only alternatives — no leg had a populated `railLinkList`, so a genuine bus+subway mixed leg hasn't been observed yet. Needs a corridor better suited to forcing a transfer, which ties into the PM's still-open Demo Corridor decision (`01_PROJECT_HANDOFF.md` section 18, Q1)
- **Next decision:** **GO** for using this as the route candidate provider. Once PM picks a demo corridor (Q1), re-test with real Seoul coordinates for it and confirm a mixed leg with `railLinkList` populated, then check subway station IDs there against the realtime subway APIs

## G. Historical Bus Section Join

Not yet tested this session.

## Open items carried to next session

1. Re-run the sustained subway position collection with the fixed `--end-ord 100` default and re-measure the trainNo join rate (expect it to approach 100%, not yet confirmed under sustained load)
2. Extend subway sampling to a second line to check whether `arvlCd` codes `3`/`4`/`5` hold the same relative meaning there
3. ~~Follow up on data.go.kr registration for the mixed-route service~~ — resolved (D-024): was a URL typo, not a registration gap. Remaining: get PM's demo corridor pick (Q1) and re-test mixed_route_spike.py against it to confirm an actual bus+subway leg with populated `railLinkList`
4. Historical bus section join (Spike D / Task F) not started — need to confirm the actual OpenAPI service name for OA-21217 (data.seoul.go.kr's catalog page didn't expose it; candidate table name `tpss_route_section_speedh` is unconfirmed)
5. Run bus/subway collection during a daytime window — all data so far is from a single 23:45–00:00 KST night window; ridership, congestion-field population (`avgCf1` etc. were all `0` at night), and call-volume patterns likely differ substantially in daytime
6. Six representative raw samples are already curated into `data/samples/examples/` (bus route/arrival/position, subway arrival/position, and the blocked mixed-route 401) and committed to git for reviewers
