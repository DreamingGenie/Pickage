# Phase 0 API Spike Harness

Read-only smoke-test scripts for the Phase 0 API/Data Feasibility spike
described in `../../docs/01_PROJECT_HANDOFF.md` and
`../../docs/02_AGENT_CONTINUATION_PROMPT.md`. Everything here is scoped
inside `docs/transit_journey_handoff_FINAL_v3/` by design — nothing outside
this folder is touched.

## Status: code ready, not yet run

No real API key exists anywhere in this repo or environment. These scripts
are written and ready, but **none have been executed against the live
APIs yet** — that requires you to supply real key values locally (never
in chat).

## One-time setup

```bash
cd docs/transit_journey_handoff_FINAL_v3/scripts/spikes
pip install -r requirements.txt
cp ../../templates/.env.example .env.local   # gitignored, stays local
# edit .env.local and fill in the real key VALUES yourself — do not
# paste them into chat or a commit
```

Which variable goes with which script:

| Script | Env var |
|---|---|
| `resolve_bus_route.py`, part of route master lookups | `DATA_GO_BUS_ROUTE_KEY` |
| `bus_arrival_spike.py` | `DATA_GO_BUS_ARRIVAL_KEY` |
| `bus_position_spike.py` | `DATA_GO_BUS_POSITION_KEY` |
| `subway_arrival_spike.py`, `subway_position_spike.py` | `SEOUL_SUBWAY_REALTIME_KEY` |
| `mixed_route_spike.py` | `DATA_GO_TRANSIT_PATH_KEY` |

## Endpoints — VERIFIED vs HYPOTHESIS

Confirmed live from the official data.go.kr listing pages:

| API | Base URL | Status |
|---|---|---|
| Bus arrival (`getArrInfoByRouteAll`) | `http://ws.bus.go.kr/api/rest/arrive/getArrInfoByRouteAll` | VERIFIED (spec page) |
| Bus position | `http://ws.bus.go.kr/api/rest/buspos/getBusPosByRouteSt` | VERIFIED (spec page) — **differs from the team doc's assumed `getBusPosByRtid`**, see Decision Log D-011 |
| Bus route master | `http://ws.bus.go.kr/api/rest/busRouteInfo/getBusRouteList` | VERIFIED base path, response fields TO_VERIFY |
| Mixed bus+subway route | `http://ws.bus.go.kr/api/rest/pathinfo/getPathInfoByBusNSubList` | VERIFIED base path, param names TO_VERIFY |
| Subway realtime arrival | `http://swopenAPI.seoul.go.kr/api/subway/<key>/json/realtimeStationArrival/...` | **HYPOTHESIS** — data.seoul.go.kr's catalog page didn't expose the spec; this is the commonly documented URL convention for this API family, unconfirmed by an actual response |
| Subway realtime position | `http://swopenAPI.seoul.go.kr/api/subway/<key>/json/realtimePosition/...` | **HYPOTHESIS**, same caveat |

First live run of each script is the actual verification step. Update the
table above and `../docs/05_DECISION_LOG.md` with what really comes back.

## Suggested run order

1. `python resolve_bus_route.py 753` — get the internal `busRouteId` for
   route 753 (same route as the existing PoC in
   `sources/project/01_bus_eta_reliability.pdf`, so results are directly
   comparable).
2. `python bus_arrival_spike.py <busRouteId> --interval 30 --count 5` — a
   handful of polls first, inspect the saved JSON in `../../data/samples/`
   before committing to a long run.
3. `python bus_position_spike.py <busRouteId> <startOrd> <endOrd> --interval 30 --count 5`
4. `python subway_arrival_spike.py 서울역 --interval 15 --count 5`
5. `python subway_position_spike.py 1호선 --interval 15 --count 5`
6. `python mixed_route_spike.py <startX> <startY> <endX> <endY>` — one-shot
7. Once each single-shot smoke test looks sane, re-run bus/subway arrival +
   position in the background over a longer window (hour+) to get actual
   arrival intervals, per Spike A/B in the project handoff.

## Call budget (dev-tier accounts, 1,000 req/day per data.go.kr service page)

| Poll interval | Calls/day (one endpoint, 24h) |
|---|---|
| 5s | 17,280 |
| 10s | 8,640 |
| 15s | 5,760 |
| 30s | 2,880 |
| 60s | 1,440 |
| 90s | 960 |

At the documented 1,000/day dev cap, only ~90s+ polling fits a full 24h
single-endpoint run — but the project handoff explicitly warns that
lengthening the interval widens the actual-arrival interval and degrades
Ground Truth quality (section 7.2). This is a real tension to raise with
the team/PM once dev quotas are confirmed vs production quotas.

**Open question:** whether `data.go.kr` issues one shared key/quota across
all bus services on the same account, or an independent 1,000/day budget
per service — the project handoff flags this as unconfirmed
(`docs/01_PROJECT_HANDOFF.md` section 6.1). Confirm before scheduling a
24h collector.

## Where samples land

`docs/transit_journey_handoff_FINAL_v3/data/samples/<provider>/<api>/<yyyy-mm-dd>/<hhmmss>_<request-id>.json`

This whole `data/samples/` tree is gitignored (see `../../.gitignore`) —
bulk collection stays local. When writing the Phase 0 report, copy a small
number of representative samples into `data/samples/examples/` and
`git add -f` them so reviewers can see real evidence without the repo
carrying every poll.
