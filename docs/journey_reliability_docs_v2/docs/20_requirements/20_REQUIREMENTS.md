---
doc_id: JR-DOC-020
title: Functional Requirements
version: 1.1
status: REVIEW
owner: PM
last_updated: 2026-08-22
depends_on:
  - JR-DOC-010
  - JR-DOC-012
source_of_truth_for:
  - functional-requirements
supersedes: []
---

# Functional Requirements

## 표기

Priority:
- `MUST`: 현재 Minimum Release 핵심 필수
- `CLAIM_GATE`: 특정 capability를 “지원/검증됨”이라고 주장하려면 필수. 실패 시 해당 claim/scope를 내려야 함
- `SHOULD`: 일정 허용 시
- `COULD`: 후순위

모든 MUST/CLAIM_GATE는 Acceptance/Test와 연결되어야 한다.

---

## A. Journey Input / Route

### REQ-001 — Journey 입력
**Priority:** MUST

사용자는 최소 다음을 입력할 수 있어야 한다.
- origin
- destination
- target arrival datetime
- target reliability(optional)

미입력 target reliability는 `PD-014`에 따라 90%.

**Exception**
- 지원 geography 밖
- target이 과거
- route provider 결과 없음

**Refs:** F-001, BR-001~003, SCR-01

### REQ-002 — Structural Route 조회
**Priority:** MUST

시스템은 `SRC-SEOUL-005`를 이용해 route candidates를 조회한다. Minimum Release 선택 규칙은 provider order를 유지하면서 현재 지원범위에서 ID/leg를 해석 가능한 첫 candidate다. Reliability score로 route 순위를 다시 매기지 않는다.

**Must not**
- route provider 결과를 Reliability Ground Truth로 간주
- “가장 안전한 경로”라고 표현

**Refs:** PD-017, F-002, API-001

### REQ-003 — Demo Route A 고정 실행
**Priority:** MUST

실제 데모에서는 Route A를 선택/복구 가능해야 한다.

**Refs:** PD-006, AC-PROD-001

### REQ-004 — Cross-mode Route B realtime verification
**Priority:** CLAIM_GATE

Phase 0 Raw에 이미 존재하는 동일 OD의 Route B(`01A→3호선→147`)를 우선 사용해 `SUBWAY_TO_BUS`의 realtime ID/Transfer/Wait/Reforecast E2E를 검증한다.

새 OD 탐색은 Route B가 실제 운영상 사용할 수 없을 때만 PM Decision 후 수행한다.

**Refs:** PD-009, EVD-CROSS-001, AC-DATA-010

---

## B. Pre-trip Probability

### REQ-010 — Journey Analysis
**Priority:** MUST

선택 structural route에 대해 LegDistribution을 구성하고 final arrival distribution을 계산한다.

**Output**
- P50
- P90
- final on-time probability
- planned connection success probability(해당하는 경우)
- support/confidence
- fallback summary
- source freshness

**Refs:** MET-001~005, API-002, SCR-02

### REQ-011 — P50/P90 표시
**Priority:** MUST

P50/P90은 `42_PROBABILITY_CONTRACT.md` 의미와 동일하게 표시한다.

**Must not**
- P90을 “90% 확률로 정확히 해당 시각에 도착”이라고 설명

### REQ-012 — 정시 도착확률
**Priority:** MUST

`target_arrival_at` 이전 final arrival simulation 비율을 제공한다.

결과는 whole percent 수준으로 표시하되 내부 계산값은 더 높은 정밀도를 유지할 수 있다.

### REQ-013 — Planned Connection vs Final On-time 분리
**Priority:** MUST

계획한 connection 유지확률과 대체 service까지 포함한 final on-time을 별도 field/UI로 유지한다.

### REQ-014 — Recommended Departure
**Priority:** MUST if computable

`PD-018/019/026`의 selected-route conditional algorithm으로 계산한다.

- near-now: realtime candidate 가능
- future subway: verified timetable 또는 empirical headway
- future bus: time-conditioned empirical wait/headway

미래 특정 bus vehicle ID가 필수 전제면 안 된다.

**If unavailable**
- 임의 값을 제공하지 않음
- reason code와 함께 unavailable state 제공

### REQ-015 — Risk Leg
**Priority:** SHOULD

결과에 가장 큰 uncertainty/contribution을 가진 leg를 식별할 수 있다면 제공한다.

정의가 검증되기 전에는 heuristic label을 “원인”처럼 표현하지 않는다.

---

## C. Live Journey / Reforecast

### REQ-020 — Journey 시작
**Priority:** MUST

사용자가 분석 결과에서 Journey를 시작할 수 있다.

시작 시:
- selected route version
- analysis result version
- target
- current state

를 snapshot한다.

### REQ-021 — Live state
**Priority:** MUST

현재:
- active leg
- completed legs
- next transfer/wait
- latest source update

를 보여준다.

### REQ-022 — BUS_SKIPPED
**Priority:** MUST

사용자가 현재 candidate bus 미탑승을 확정할 수 있다.

시스템은:
1. 해당 candidate를 SKIPPED
2. 완료 history 고정
3. current time 고정
4. 다음 bus candidate
5. 남은 Journey Reforecast

를 수행한다.

### REQ-023 — BOARD_CONFIRMED
**Priority:** MUST

사용자는 현재 candidate 탑승을 확정할 수 있다.

### REQ-024 — TRANSFER_MISSED
**Priority:** SHOULD

Tier-0 fixed buffer 또는 user confirmation으로 connection miss를 기록하고 next candidate로 전환한다.

### REQ-025 — Reforecast delta
**Priority:** MUST

Reforecast 후:
- previous probability
- new probability
- delta percentage point
- P50/P90 change
- reason code

를 반환한다.

AI 설명은 optional이며 deterministic reason code보다 우선하지 않는다.

---

## C-2. WALK / Transfer / Wait Source Integrity

### REQ-026 — Coordinate provenance
**Priority:** MUST

ACCESS/TRANSFER/FINAL WALK의 모든 endpoint는 coordinate value뿐 아니라 coordinate role/source를 저장한다.

최소 role:
`ORIGIN_POINT | BUS_STOP | STATION_CENTER | STATION_EXIT | PLATFORM_REFERENCE | POI`

station center를 exit로 암묵 변환하지 않는다.

### REQ-027 — BUS_TO_SUBWAY decomposition
**Priority:** MUST for Route A correctness

01A 하차정류장→안국 boarding point의 Transfer는 street walk와 station internal access가 구분되어야 한다.

두 component 중 하나가 미검증이면 fallback/`UNMODELED_UNCERTAINTY`를 표시한다.

### REQ-028 — Future WAIT source
**Priority:** MUST for Recommended Departure

future candidate time의 Bus/Subway WAIT는 source가 명확해야 한다.

- realtime exact candidate
- timetable
- empirical headway/wait

중 하나를 기록하고, 해당 source가 없는 mode/time은 Recommended Departure를 unavailable로 둘 수 있다.

## D. Evidence / Confidence

### REQ-030 — Support 표시
**Priority:** MUST

JourneyResult는 최소:
- sample_count 또는 support summary
- observation window
- fallback level
- confidence label
- model/rule version
- validation scope (`COMPONENT_ONLY | CORRIDOR_REPLAY | END_TO_END`)

을 제공한다.

### REQ-031 — Unmodeled uncertainty 표시
**Priority:** MUST

WALK/static transfer처럼 variance가 모델링되지 않은 leg가 있으면 결과 metadata와 상세 UI에 이를 표시한다.

### REQ-032 — Freshness 표시
**Priority:** MUST

마지막 성공 source update와 data freshness state를 제공한다.

### REQ-033 — Unsupported 처리
**Priority:** MUST

지원 범위/ID mapping/Evidence가 부족하면:
- unsupported/no-data로 종료 가능
- mock/fabricated probability 금지

### REQ-034 — Evidence trace
**Priority:** MUST for engineering/demo

JourneyResult에서 사용된:
- source version
- distribution artifact version
- simulation run id

를 통해 Raw evidence chain을 추적할 수 있어야 한다.

---

## E. Share

### REQ-040 — Share Snapshot
**Priority:** SHOULD

사용자는 결과의 축약 Snapshot을 공유할 수 있다.

포함:
- destination
- target time
- current expected arrival summary
- on-time probability
- calculated_at

제외:
- precise origin
- raw transit identifiers
- API keys
- internal debugging metadata

보안/TTL은 `53_SECURITY_OPERATIONS.md`.

---

## F. Error / Recovery

### REQ-050 — Provider error
**Priority:** MUST

외부 API 실패 시:
- 마지막 성공값을 무조건 현재값처럼 사용하지 않음
- stale 여부 표시
- retry 가능
- 분석 불가능하면 명시적 fail

### REQ-051 — Partial data
**Priority:** MUST

일부 leg에만 empirical distribution이 있고 나머지가 fallback이면 전체 결과는 생성 가능하되 `PARTIAL_MODEL` 상태를 가져야 한다.

### REQ-052 — No fake fallback
**Priority:** MUST

분포가 없는 leg에 arbitrary Gaussian/percentage variance를 자동 생성하지 않는다.

### REQ-053 — Idempotent user event
**Priority:** MUST

같은 `BUS_SKIPPED` request가 재전송되어도 동일 event를 중복 적용하지 않는다.

---

## G. Operational / Admin

### REQ-060 — Data collection status
**Priority:** SHOULD

운영자/개발자는 collector별:
- last success
- error count
- sample count
- lag

를 확인할 수 있어야 한다.

### REQ-061 — Evidence package export
**Priority:** SHOULD

최종 demo/보고를 위해 한 Journey ID의 evidence references를 export할 수 있어야 한다.

---

# Requirement Open Items

| Item | Status | Resolution Gate |
|---|---|---|
| Risk-leg formal definition | OPEN | D4 Validation |
| Share token exact TTL | OPEN | D5 Security |
| Freshness thresholds | OPEN | D5 Observability profile |
| TRANSFER_MISSED exact buffer values | OPEN | D4 data/validation |
| Route A ACCESS_WALK exact pair | OPEN | Phase 1 Evidence |
| Route A BUS_TO_SUBWAY internal access source | OPEN | Phase 1 Evidence |
| OA-22522 timetable ID interoperability | OPEN | Phase 1 Evidence |
| Bus future wait/headway model support | OPEN | Phase 1 Evidence |
| User-selectable reliability options beyond 90% | OPEN | D3 UX review |
