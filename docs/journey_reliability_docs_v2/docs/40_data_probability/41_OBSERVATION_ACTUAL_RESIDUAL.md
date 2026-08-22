---
doc_id: JR-DOC-041
title: Observation Actual Residual Contract
version: 1.2
status: REVIEW
owner: Data
last_updated: 2026-08-22
depends_on:
  - JR-DOC-003
  - JR-DOC-040
source_of_truth_for:
  - prediction-actual-residual-rules
  - data-quality-rules
supersedes: []
---

# Observation → Actual → Residual Contract

## 1. Bronze

모든 호출은 성공/실패와 무관하게 가능한 범위에서 저장:

```text
provider
api_name
request_id
request_params_sanitized
requested_at
received_at
http_status
raw_payload
raw_payload_hash
collector_version
error_code
error_body
```

Silver parser가 실패해도 Raw를 잃지 않는다.

---

# 2. Bus Prediction

Source:
`SRC-SEOUL-003 getArrInfoByRouteAll`

Verified fields:
- `busRouteId`
- `vehId1/vehId2`
- `mkTm`
- stop-level arrival prediction fields

`mkTm`은 **한 response 내 call-level 공통 source time**.

### Canonical key

Prediction slot마다:
`route_id + target stop context + vehicle_id + source_generated_at`

`vehId=0`/no vehicle는 real vehicle prediction으로 생성하지 않는다.

---

# 3. Bus Actual

Source:
`SRC-SEOUL-004 getBusPosByRouteSt`

Actual candidate:
같은 `vehId`의 연속 observation에서 `stopFlag: 0 → 1`.

### Rule Version
`BUS_ACTUAL_RULE_V1_CANDIDATE`

### Interval

```text
lower_exclusive_at = previous source time
upper_inclusive_at = first stopFlag=1 source time
```

현재 Phase 0에서 실제 transition이 관측되었으므로
“transition 미관측”이라는 legacy OBSERVATION_CONTRACT 문장은 superseded다.

Phase 0 D-048의 54 transition은 **01A route-level multi-stop transition count**다. Phase 1에서 춘추문→안국 target range traverse-time 11건을 추가 확보했지만 이것도 ResidualEvent가 아니다. target-leg PredictionSnapshot→ActualArrivalInterval→ResidualEvent는 Phase 2에서 별도 생성한다(`PD-036`).

### Quality guard

- same route/vehId
- source time non-decreasing
- interval width valid
- duplicate source event 제거
- out-of-order 별도 flag

---

# 4. Bus Residual

Prediction arrival:
`predicted_arrival_at = prediction_source_time + eta`

Residual interval:

```text
residual_lower = actual_lower - predicted_arrival
residual_mid   = actual_mid   - predicted_arrival
residual_upper = actual_upper - predicted_arrival
```

Sign:
- positive: actual later than predicted
- negative: actual earlier than predicted

interval uncertainty를 midpoint 하나로 파괴하지 않는다.

---

# 5. Subway Prediction

Source:
`SRC-SEOUL-001 realtimeStationArrival`

Canonical identity:
`subwayId + statnId + btrainNo`

Observed state:
`arvlCd`

Source time:
`recptnDt`

---

# 6. Subway Actual

Current corridor-scoped candidate:

### Rule Version
`SUBWAY_ACTUAL_RULE_V0`

Key:
`(subwayId, statnId, btrainNo)`

Trigger:
이전 observation에서 `arvlCd != 1`,
이후 최초 `arvlCd == 1`.

Interval:

```text
(previous_observation_source_time, first_arrival_state_source_time]
```

### Status
`CONDITIONAL`

이유:
- Route A station×line 4개에서 trainNo join은 Phase 1 live sample로 100% 재확인
- 실제 ActualArrivalInterval은 안국 11, 교대 name-search combined 6, 역삼 0으로 관측됐으나 usable window가 quota로 22~33분에 그침
- 교대는 multi-line station이므로 이후 Actual metric을 `subwayId × statnId`로 분리해야 함
- 특정 Line2 code `1002000201` join gap root cause는 Route A와 별개로 미해결

Citywide rule로 승격하지 않는다.

---

# 7. Subway Residual

실제 provider ETA를 canonical predicted arrival로 만들 수 있는 field semantics를 final parser에서 재확인한 뒤 생성한다.

**금지:** `arvlMsg` 문자열을 임의 parse해 exact ETA truth처럼 사용.

actual sample 확보 전 “subway residual distribution exists”라고 문서화하지 않는다.

---

# 8. Data Quality Rules

| ID | Flag | 의미 |
|---|---|---|
| DQ-001 | `SOURCE_TIME_MISSING` | source timestamp 없음 |
| DQ-002 | `DUPLICATE_SOURCE_EVENT` | canonical identity+source time 중복 |
| DQ-003 | `OUT_OF_ORDER_EVENT` | source event time 역행 |
| DQ-004 | `UNMATCHED_VEHICLE` | bus prediction/position vehicle join 실패 |
| DQ-005 | `UNMATCHED_TRAIN` | subway arrival/position train join 실패 |
| DQ-006 | `CROSSWALK_MISSING` | mixed route node를 realtime node로 resolve 불가 |
| DQ-007 | `ACTUAL_INTERVAL_TOO_WIDE` | profile 후 정한 허용 interval보다 큼 |
| DQ-008 | `STALE_OBSERVATION` | NFR threshold 초과 |
| DQ-009 | `SERVICE_ENDED` | bus arrival의 운행종료 business state |
| DQ-010 | `NO_VEHICLE_ASSIGNED` | `vehId=0` 등 |
| DQ-011 | `LOW_SUPPORT` | support rule 미충족 |
| DQ-012 | `FALLBACK_USED` | fallback distribution/reference 사용 |
| DQ-013 | `UNMODELED_UNCERTAINTY` | WALK/static transfer variance 미모델링 |
| DQ-014 | `PROVIDER_ERROR` | 외부 provider error |
| DQ-015 | `PARTIAL_MODEL` | Journey 일부 leg만 modeled uncertainty |
| DQ-016 | `COORDINATE_ROLE_UNKNOWN` | station center/exit/platform 등 좌표 의미를 판정할 수 없음 |
| DQ-017 | `WAIT_SOURCE_MISSING` | future WAIT를 구성할 realtime/timetable/empirical source 없음 |
| DQ-018 | `CROSS_LEG_DEPENDENCE_UNMODELED` | cross-mode/vehicle 간 잔여 상관을 모델링하지 않음 |
| DQ-019 | `VALIDATION_SCOPE_LIMITED` | component 검증만 있고 corridor/end-to-end calibration 없음 |
| DQ-020 | `PROVIDER_QUOTA_EXCEEDED` | HTTP transport 성공 여부와 별개로 provider quota/error code 발생 |
| DQ-021 | `TIMESTAMP_INSTRUMENTATION_INVALID` | requested/received timing이 실제 request boundary를 측정하지 못함 |
| DQ-022 | `MULTILINE_STATION_NOT_SPLIT` | multi-line station observation을 `subwayId`로 분리하지 않은 집계 |

`DQ-007/008`의 numeric threshold는 실제 profile 전 TBD. `DQ-020`은 Phase 1 `ERROR-337` 같은 provider business error를 HTTP status와 독립적으로 기록한다.

---

# 9. Dedupe

Dedupe key를 raw payload hash 하나로만 정의하지 않는다.

권장 logical key:

Bus observation:
`api + route + vehicle/stop identity + source time`

Subway:
`api + subwayId + statnId + trainNo + source time + state`

최종 key는 parser sample profile 후 고정.

---

# 10. Out-of-order

Source event time 기준 state machine을 유지한다.

늦게 도착한 event를 무조건 drop하지 않는다.
watermark/allowed lateness 정책은 `51_STREAMING_STORAGE_CONTRACT.md`에서 측정 후 결정한다.

---

# 11. Acceptance

이 contract가 구현되었다고 말하려면:

- Bus 01A raw → actual interval → residual 최소 실제 sample
- Subway raw → actual interval 실제 sample
- interval width distribution
- join rate
- duplicate/out-of-order profile

가 재현 가능해야 한다.
