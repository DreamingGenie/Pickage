---
doc_id: JR-DOC-011
title: Scope and Source Policy
version: 1.2
status: LOCKED
owner: PM
last_updated: 2026-08-22
depends_on:
  - JR-DOC-002
  - JR-DOC-004
source_of_truth_for:
  - source-eligibility
  - geography-scope
  - corridor-policy
  - route-policy
supersedes: []
---

# Scope & Source Policy

## 1. Geography

Minimum Release의 제품/데모 범위는 서울 행정구역으로 제한한다.

서울 외 구간이 route response에 섞이거나 source semantics가 불확실하면 자동 지원 범위로 확장하지 않는다.

## 2. Transit Reliability Source

기본 허용 조건:

`Provider is Seoul public transit authority` **AND** `journey segment is in Seoul geography`

예:
- 서울 버스 실시간
- 서울 지하철 실시간
- 서울교통공사 static transfer data

## 3. External Utility Exception

TMAP은 허용한다.

이유:
- Transit Reliability 데이터가 아님
- 출발지→탑승점, 역/정류장→실제 목적지 WALK 계산용 utility
- D-040에서 core-data-only 정책의 예외로 PM 결정됨

### 금지

TMAP/Kakao 등 외부 utility를:
- Bus ETA residual GT
- Subway delay GT
- transit model label

로 사용하지 않는다.

## 4. WALK 정책

현재 TMAP은 point estimate만 제공한다.

따라서:
- `walk_time_point_sec`로 저장
- `uncertainty_model=UNMODELED`
- `fallback_level=WALK_POINT_ESTIMATE`
- probability result에 partial uncertainty limitation을 전달

실측 walk distribution이 없는 상태에서 고정 % variance를 임의로 만들지 않는다.

### 4.1 Station access/egress boundary

TMAP street routing과 지하철 내부 이동을 같은 source로 취급하지 않는다.

- `BUS_TO_SUBWAY`: bus stop→station entrance/exit street part + entrance→platform internal part
- `SUBWAY_TO_BUS`: platform→exit internal part + exit→bus stop street part
- `SUBWAY_TO_SUBWAY`: official transfer reference 우선

Phase 1에서 안국 bus stop→mixed subway node의 street part는 143 m/101 s로 VERIFIED됐다. 그러나 node role은 `STATION_CENTER` candidate이고 entrance→platform internal part는 미측정이므로 **전체 BUS_TO_SUBWAY time은 CONDITIONAL**이다.

모든 endpoint는 `PD-028`의 coordinate role/source를 기록한다. station center를 station exit로 조용히 사용하지 않는다.

## 5. Static Transfer Policy

교대 3→2 Phase 1 official rows:
- OA-22521: 4개 door/direction row 모두 **144 s**
- OA-13290: 75 m / **63 s**

`PD-031`에 따라 Tier-0 runtime reference는 OA-22521 144 s를 사용한다.
OA-13290 63 s는 geometric/1.2m/s sanity reference로 보관하며 평균하거나 랜덤 후보로 섞지 않는다.

Static time은 개인 walking distribution이 아니다.
`uncertainty_model=UNMODELED` 또는 이후 별도 calibration.

## 6. Route Policy

### Minimum Release

- Route provider가 반환한 candidate 중 **선택된 structural route 1개** 분석
- Primary Demo는 Route A 고정
- 같은 Demo OD의 Route B는 `SUBWAY_TO_BUS` cross-mode proof만 수행

### Out

- multiple route reliability ranking
- route Pareto frontier
- fastest vs safest automatic recommendation
- citywide route optimization

## 7. Recommended Departure Scope

Recommended Departure는 selected structural route에 conditional하다. 미래 후보시각은 exact vehicle ID가 아니라 검증된 timetable 또는 time-conditioned empirical wait/headway를 사용할 수 있다.

UI label:
`이 경로 기준 90% 권장 출발`

글로벌 표현 금지:
`가장 안전한 출발시간`

## 8. Incident

현재 incident source는 support context 후보.

Minimum Release에서:
- 이미 발생한 incident를 context/notice로 반영 가능
- 미래 incident 발생확률을 모델링하지 않음

## 9. Congestion

Bus `congetion` field는 사용할 수 있는 observed context이다.

하지만:
- 개인 boarding success
- 실제 차내 체감 혼잡
- “버스를 못 탈 확률”

과 동일하지 않다.

## 10. Wait Source Policy

### Near-now / In-trip
realtime Arrival/Position에서 현재 candidate service를 식별할 수 있으면 사용한다.

### Future pre-trip / Recommended Departure
- Subway: `SRC-SEOUL-011` timetable 또는 검증된 empirical headway
- Bus: time-conditioned empirical headway/wait가 기본 후보

미래 특정 bus vehicle ID를 정확히 예측할 수 있다는 가정을 두지 않는다.

`EVD-WAIT-001`은 Bus source feasibility VERIFIED다. 그러나 `EVD-SCHED-001`은 dated timetable의 current validity가 CONDITIONAL이므로 **user-facing Recommended Departure는 HOLD/unavailable 가능**하다.


## 11. Coverage Label

모든 result는 내부적으로 최소 다음을 가진다.

```text
coverage_scope:
  corridor_id
  supported_modes
  evidence_scope
  citywide_validated: false
```

Minimum Release에서 `citywide_validated=true`를 사용하지 않는다.
