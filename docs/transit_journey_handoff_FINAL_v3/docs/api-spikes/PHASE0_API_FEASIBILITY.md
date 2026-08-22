# Phase 0 API Feasibility Report

> Working document — updated as spikes progress. See `../05_DECISION_LOG.md`
> (D-013 through D-034) for the underlying evidence entries this report
> summarizes. Raw samples referenced below live under
> `../../data/samples/` (gitignored; a curated subset will be added to
> `data/samples/examples/` for reviewers).

**Snapshot dates:** 2026-08-21 ~23:45–00:00 KST (night) and 2026-08-22
~08:35–09:10 KST (daytime) — two collection windows, see caveats per
section. Daytime pass re-verified the demo corridor and cross-checked
its subway stations; it did not re-verify bus arrival/position or the
citywide subway coverage question.

## Summary verdict

| Area | Verdict | Confidence |
|---|---|---|
| Bus arrival (`getArrInfoByRouteAll`) | **GO** | High — real endpoint, real data, matches PoC expectations |
| Bus position (`getBusPosByRouteSt`) | **GO** | High — real endpoint (differs from team doc), real data |
| Bus arrival↔position vehId join | **GO** | Night run (route 753, 30s interval, ~10min): **100% (2026/2026)**, 49 `stopFlag` 0→1 transitions, ~19.8% duplicate `dataTm`. Daytime re-run (D-035, 20s interval, ~7min): **100% (3831/3831)** held, 39 transitions, congestion field observed populated for the first time. Still 1 route — not yet generalized citywide |
| Subway realtime arrival | **GO** | High — real endpoint, real data |
| Subway realtime position | **GO** | High — real endpoint, real data |
| Subway arrival↔position trainNo join | **GO on Line 1 & Line 3, CONDITIONAL on Line 2** | Line 1/시청 re-measured after the pagination fix: 75%→**91.7% (11/12)**. Line 3 (안국/교대, demo corridor stations, daytime): **100% (4/4 each)**. Line 2/강남 is split by station code: `1002000222` and `1002000221`(역삼) both **100%**, but `1002000201` shows a persistent, still-unexplained **54.5% (6/11)** gap that survived a subwayId-filter fix ruling out cross-line name collision (D-032/D-033) |
| Mixed bus+subway route | **GO** | Was misdiagnosed as a key-registration BLOCKER (D-019); actual cause was our own URL typo. Fixed and confirmed live, including genuine bus+subway mixed legs (D-029). **Demo Corridor locked: 삼청동↔역삼역 (D-030), re-verified stable in daytime (D-031), and its subway leg stations all show 100% Ground Truth join (D-034)** |
| Historical bus section join | **DROPPED (PM decision)** | OA-21217 turns out to be a weekly/monthly ZIP file download, not a pollable OpenAPI as assumed, with a service-termination notice on its page. PM decided to drop it as a baseline candidate rather than pursue file-based ingestion (D-028) |

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
- **Sustained run (~10 min, 30s interval, route 753, night, final numbers):** 100% vehId join rate (2026/2026 arrival vehId references matched a position vehId), 49 real `stopFlag` 0→1 transitions observed across 13 distinct vehicles, transition width mostly 20–40s (consistent with ~30s polling + real dwell time), ~19.8% (51/257) duplicate `dataTm` per-vehicle observation ratio — see `docs/05_DECISION_LOG.md` D-020 and `scripts/spikes/analyze_samples.py bus 100100118`
- **Daytime re-run (~7 min, 20s interval, route 753 — D-035):** join rate held at **100% (3831/3831)** with a larger reference count than the night run (higher daytime service frequency), 39 `stopFlag` 0→1 transitions across 15 vehicles. **`congetion` was observed non-zero for the first time** (values like `0`, `3`) — resolves the night sample's open question of whether the field is populated at all; it is, just not at low night-time ridership.
- **Risks:** one route; call budget (D-020's ~17% duplicate rate at 30s interval) needs revisiting against the 1,000/day cap at sustained daytime polling frequency
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
- **Sustained run, Line 1/시청 (~15 min total across two sessions):** trainNo join rate first measured **6/8 (75%)** — traced to our own fixed `0/20` pagination window against a line with 46–53 active trains (D-023). Fixed to `0/100` and re-ran: join rate improved to **11/12 (91.7%)**. Exactly one train (`5166`) stayed unmatched all session despite appearing in arrival 4 times — cause unknown, not explained by pagination this time.
- **Sustained run, Line 2/강남 (~7.5 min, night):** join rate **6/11 (54.5%)** at station code `1002000201` — notably *not* a pagination artifact here: Line 2's `totalCount` was only 16–18 (well under the `0/100` range, `selectedCount == totalCount` every poll), yet 5 trains never appeared in position.
- **Daytime re-investigation of the Line 2 gap (D-032/D-033):** could not directly reproduce/refute the `1002000201` gap — that exact station/platform code simply never reappeared across 14 daytime polls of "강남" (name-search returns a rotating subset of matching platform codes, not a fixed deterministic set — itself a newly-documented API quirk). Did confirm a *separate*, real phenomenon: "강남" name-search also returns 신분당선 (Sinbundang Line, `subwayId=1077`) trains that structurally can never match a Line-2-only position feed. Added a subwayId filter to `analyze_samples.py` (D-033) so this cross-line case is now reported as "not polled for this line," not a false 0%-join. Re-running the filtered tool against the *original* night dataset confirmed the `1002000201` gap is **not** explained by this cross-line issue — all 11 of its arrival trains really are `subwayId=1002` (D-032/D-033). **Root cause still open.**
- **Demo corridor subway stations, daytime (D-034):** 안국역(Line 3) 4/4, 교대역 Line-3-side 4/4, 역삼역(Line 2) 5/5 — **100% join at every corridor-relevant station**, no gap reproduced here at all.
- **Actual arrival rule candidate — richer than first observed, and now confirmed on 3 lines:** sustained collection surfaced state codes `{0,1,2,3,4,5,99}`, not just the `{0,1,2,99}` seen in the single snapshot. The ordered progression `99 → {5,4,3,2} → 0 → 1 → 2` was observed on **Line 1** (trains 0704, 0825), **Line 2** (trains 6513, 4515, 6508), and **Line 3** (trains 3065, 3057 — D-034) — the same relative code ordering held across three independent lines. Formalized as `../data-contract/SUBWAY_ACTUAL_RULE_V0.md`, status CONDITIONAL.
- **Timestamp semantics:** `recptnDt` (arrival) and `recptnDt`/`lastRecptnDt` (position) are per-train, not per-call — unlike bus arrival's call-level `mkTm`
- **Risks:** the `1002000201` gap is real, reproduced in the original session, and not explained by any of the four hypotheses tested so far (pagination D-023, geography D-027, direction D-027, cross-line naming D-032/D-033). It is *not* citywide (three other station codes across three lines are all 100%), which makes it stranger, not safer — do not treat trainNo join as citywide-reliable until this specific symptom is understood
- **Next decision:** `SUBWAY_ACTUAL_RULE_V0.md` is usable now for the demo corridor (all its stations are clean). Next session: rule out train-ID-reuse/dispatch-pattern hypotheses specific to `1002000201` rather than re-testing already-ruled-out causes

## F. Mixed Bus+Subway Route — `getPathInfoByBusNSub`

- **Tested at:** 2026-08-21 23:50 KST (failed) and 2026-08-22 (fixed, succeeded)
- **First result:** HTTP 401 `등록되지 않은 서비스키` — initially misdiagnosed as a key-registration gap (D-019) since all 5 `DATA_GO_*` keys were confirmed byte-identical (one account-wide key), so it looked like this one service just hadn't been approved yet
- **Real root cause (D-024):** a **URL typo in our own code**. The data.go.kr catalog *names* the operation `getPathInfoByBusNSubList`, but the official 활용가이드 document (already sitting in this repo at `docs/api & data/서울특별시_대중교통환승경로 조회 서비스_활용가이드_20211116.docx` — extracted directly from its docx/zip/xml to confirm) shows the real Call Back URL drops the "List" suffix (`getPathInfoByBusNSub`), and the auth parameter is capitalized `ServiceKey`, not `serviceKey`. Requesting the nonexistent `...List` path apparently falls through to the gateway's generic 401 instead of a 404, which reads exactly like an unapproved key even when the key is fine.
- **Fixed and verified:** corrected `mixed_route_spike.py` to the real URL + param casing + `resultType=json`. Real call for 서울역↔강남역 (coords 126.972559,37.554648 → 127.027610,37.498095) returned HTTP 200 with **20 alternative routes**, each a multi-leg `pathList` with `routeId`/`routeNm`/stop names/coordinates
- **ID mapping:** returned bus `routeId` values (e.g. `100100023`) are in the same numeric domain as `getArrInfoByRouteAll`/`getBusPosByRouteSt`/`getBusRouteList` — a real, positive signal for joinability, though not yet directly cross-queried against those APIs
- **Gap (resolved):** the 서울역↔강남역 test happened to return bus-only alternatives. Testing 4 more candidate corridors confirmed the API does return genuine mixed legs (`railLinkList` populated) — it was just that one pair, not a capability gap (D-029).
- **Demo Corridor decided (D-030):** PM specified destination = 역삼역, start flexible. Picked **삼청동 ↔ 역삼역** (3호선 안국역→교대역 subway leg, ~50min total, one of 24 mixed-leg alternatives for this pair). Sample saved at `data/samples/examples/seoul_bus/demo_corridor_samcheong_yeoksam/`.
- **Daytime re-verification (D-031):** identical coordinate re-call reproduced the exact same top alternative — same legs, same `time=50`, same `distance=16542` — the API returns a stable optimal route across night/day for this corridor.
- **Subway leg station cross-check (D-034):** polled 안국역/교대역(Line 3)/역삼역(Line 2) directly — all three joined trainNo at 100%. Also found that this API's own station codes (안국=`03180`, 교대=`03300`) are a **different ID space** from the realtime APIs' `statnId` (안국=`1003000328`, 교대=`1003000340`) — no direct equivalence, a coordinate- or name-based crosswalk table would be needed to join the two APIs in production (noted in `../data-contract/ID_MAPPING.md`).
- **Next decision:** **GO**, corridor locked and its subway leg Ground Truth-verified. Spike E's remaining open piece is the bus leg (교대역/역삼역 vicinity local bus, per the alternate `pathList` legs) and an actual end-to-end walk through Route→Leg Distribution→Monte Carlo once Phase 0 formally closes

## G. Historical Bus Section Join

- **Tested at:** 2026-08-22, via WebSearch + WebFetch (no API call — this dataset isn't one)
- **Result:** OA-21217 is **not a pollable OpenAPI** the way the other six are. It's distributed as weekly/monthly ZIP file downloads (26–169MB, CSV), with a vague claim that "Sheet/Open API provide the most recent 30 days" that this session couldn't pin down to an actual service name or endpoint. The data.seoul.go.kr page for it also carries a **service termination notice**.
- **Interpretation:** **PIVOT**, not a code problem. Team handoff (`01_PROJECT_HANDOFF.md` section 13.1) assumed this could feed a "historical bus section average + realtime correction" baseline via simple API calls — that assumption needs PM re-evaluation. Either confirm the dataset is still alive and pursue file-based ingestion instead of polling, or drop it as a baseline source.
- **Next decision:** flag to PM (see Decision Log D-025). Do not build collector code around this until its status is confirmed.

## Open items carried to next session

1. **The `1002000201` (강남/Line 2) join-rate gap is still unresolved.** Four hypotheses ruled out so far: pagination (D-023), geographic coverage and direction (D-027), cross-line name collision (D-032/D-033). Next hypotheses to try: train-ID reuse/dispatch patterns specific to that platform code, or whether `realtimePosition` structurally under-reports one direction of a two-way platform pairing. Could not even attempt daytime reproduction this session because that exact station code never appeared in 14 daytime polls (D-032) — worth polling for a longer window or more repetitions to catch it again.
2. ~~Extend subway sampling to a third line~~ — done: Line 3 (안국/교대, demo corridor stations) tested daytime, 100% join, no gap reproduced there (D-034). The gap looks isolated to one specific station/platform code, not "Line 2" or "loop lines" broadly.
3. ~~Follow up on data.go.kr registration for the mixed-route service~~ — resolved (D-024). ~~Get PM's demo corridor pick~~ — resolved (D-030): 삼청동↔역삼역, re-verified stable in daytime (D-031). ~~Cross-check the 안국역/교대역/역삼역 station IDs against realtime subway APIs~~ — done, all 100% join (D-034); found the mixed-route API's station codes are a different ID space from realtime `statnId`s, a crosswalk is needed for production joins.
4. ~~Historical bus section join~~ — resolved: PM decided to drop it as a baseline candidate (D-028). Historical baseline needs a different source (e.g. accumulating our own realtime bus data over time)
5. ~~Bus arrival/position daytime run~~ — done (D-035): route 753, 100% join (3831/3831), and `congetion` observed non-zero for the first time. Citywide subway coverage (beyond the demo corridor's 3 stations and 강남) is still open.
6. Nine representative raw samples are curated into `data/samples/examples/` (bus route/arrival/position, subway arrival/position on both Line 1 and Line 2, the original mixed-route 401 bug, and the fixed mixed-route success) and committed to git for reviewers
7. `SUBWAY_ACTUAL_RULE_V0.md` (`../data-contract/SUBWAY_ACTUAL_RULE_V0.md`) is drafted and CONDITIONAL — safe for the demo corridor, not yet citywide. Bump to v1 once item 1 above gets a root cause.
8. **New hypothesis for the `1002000201` gap (D-036):** across 30 daytime "강남" name-search polls this session, `1002000201` never appeared once (only `1002000222` and occasionally Sinbundang's `1077000687` did) — but it appeared repeatedly throughout the original night session. This weakens the "pure random subset" reading of the station-name-search quirk (`STATION_NAME_AMBIGUITY` in `QUALITY_FLAGS.md`) in favor of a time-of-day-dependent pattern. Next session: re-poll 강남 late at night again to confirm `1002000201` reappears, then investigate what's schedule-specific about it (`lstcarAt`, direction-specific service frequency).
