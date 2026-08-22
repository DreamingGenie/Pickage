# Quality Flags

> Flags actually observed in live Spike samples so far (see
> `../05_DECISION_LOG.md`). This is not the full set the eventual
> collector needs — it's what a handful of real snapshots have already
> shown, so the Bronze pipeline can start handling them from day one
> instead of discovering them later.

## Bus Arrival (`getArrInfoByRouteAll`)

- `SERVICE_ENDED` — `arrmsg1`/`arrmsg2` contains `"운행종료"`. Observed on
  50/104 stop-entries in a 23:46 KST snapshot (route tail-off, not an
  error). Must not be treated as a missing/error value — it's a valid
  business state.
- `NO_VEHICLE_ASSIGNED` — `vehId1`/`vehId2` = `"0"` when no bus is
  currently predicted for that slot.
- `CALL_LEVEL_TIMESTAMP` — `mkTm` is shared across every item in one
  response (not per-stop). Do not treat repeated `mkTm` across items
  within a single call as a duplicate-polling signal — that comparison
  only makes sense across separate calls.

## Bus Position (`getBusPosByRouteSt`)

- `STOP_FLAG_STATE` — `stopFlag` observed values `0` and `1` in one
  snapshot; `1` is the current best candidate for "at a stop" per the
  checklist's actual-arrival rule, but the transition has not yet been
  observed across polls (needs the sustained collection run).
- `MISSING_FIELD` — `nextStId`, `nextStTm`, and a generic `rtDist` do not
  exist in the real response despite being in the team checklist; do not
  build downstream logic assuming they're present.
- `FIELD_TYPO` — the real field is `congetion`, not `congestion`. Parse
  it as-is.

## Subway Arrival (`realtimeStationArrival`)

- `ARRIVAL_STATE_CODE` — `arvlCd` takes values `{0,1,2,3,4,5,99}`, richer
  than first observed: `99` (en route, countdown/station-count message
  in `arvlMsg2`), `5/4/3/2` (descending "stations away" countdown,
  individual code semantics not confirmed beyond ordering), `0`
  (entering/진입), `1` (arrived/도착 — the Actual-event trigger). Ordered
  progression `99 → {5,4,3,2} → 0 → 1 → 2` confirmed cross-line (Lines
  1, 2, 3 — see `SUBWAY_ACTUAL_RULE_V0.md`). Treat as an ordered state
  machine, not a boolean "arrived or not."
- `TRAIN_LEVEL_TIMESTAMP` — `recptnDt` differs per train within one
  response (unlike bus arrival's call-level `mkTm`).
- `STATION_NAME_AMBIGUITY` — querying by station display name (e.g.
  "강남") can return multiple distinct `(statnId, subwayId)` pairs when
  more than one line's station shares that name (Line 2's 강남 vs
  Sinbundang Line's 강남, `subwayId` 1002 vs 1077 — D-032/D-033). Worse,
  repeated identical-parameter calls do not reliably return the same set
  of matching station codes every time (D-032 observed one of two known
  Line 2 강남 codes across 14 consecutive daytime polls, never both) —
  do not assume a name-search response enumerates every matching
  physical station/platform on every call.

## Subway Position (`realtimePosition`)

- `TRAIN_STATUS_CODE` — `trainSttus` observed values `1` and `2` so far;
  meaning not yet confirmed against arrival's `arvlCd` semantics — TO_VERIFY.

## Mixed Route

- `UNAUTHORIZED_SERVICE_KEY` — HTTP 401,
  `"등록되지 않은 서비스키"`. This is a registration-state flag on the
  credential, not a data-quality flag on any response — surfaced here so
  the collector can distinguish "key not approved for this service" from
  a transient auth failure and avoid retry-storming it.
- `DISJOINT_STATION_ID_SPACE` — this API's own station/stop codes
  (`fid`/`tid`, e.g. 안국=`03180`) are **not** the same identifiers as
  the realtime subway APIs' `statnId` (안국=`1003000328` — D-034). Do
  not assume these can be joined as literal strings; a crosswalk
  (name/line or coordinate based) is required.

## Still to characterize (needs sustained collection)

- Duplicate source-snapshot ratio across polls (same `mkTm`/`recptnDt`
  repeated with no new data)
- Expired-on-receipt ratio (ETA already in the past when received)
- Empty-response rate
- HTTP/business-error rate under load
