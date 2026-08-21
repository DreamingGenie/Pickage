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

- `ARRIVAL_STATE_CODE` — `arvlCd` takes values `0` (entering/진입), `1`
  (arrived/도착), `2` (departed/출발), `99` (en route, with either a
  countdown or a station-count message in `arvlMsg2`). Treat this as an
  ordered state machine, not a boolean "arrived or not."
- `TRAIN_LEVEL_TIMESTAMP` — `recptnDt` differs per train within one
  response (unlike bus arrival's call-level `mkTm`).

## Subway Position (`realtimePosition`)

- `TRAIN_STATUS_CODE` — `trainSttus` observed values `1` and `2` so far;
  meaning not yet confirmed against arrival's `arvlCd` semantics — TO_VERIFY.

## Mixed Route

- `UNAUTHORIZED_SERVICE_KEY` — HTTP 401,
  `"등록되지 않은 서비스키"`. This is a registration-state flag on the
  credential, not a data-quality flag on any response — surfaced here so
  the collector can distinguish "key not approved for this service" from
  a transient auth failure and avoid retry-storming it.

## Still to characterize (needs sustained collection)

- Duplicate source-snapshot ratio across polls (same `mkTm`/`recptnDt`
  repeated with no new data)
- Expired-on-receipt ratio (ETA already in the past when received)
- Empty-response rate
- HTTP/business-error rate under load
