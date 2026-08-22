---
doc_id: JR-DOC-010
title: Journey Reliability Service Plan
version: 2.2
status: LOCKED
owner: PM
last_updated: 2026-08-22
depends_on:
  - JR-DOC-002
  - JR-DOC-003
  - JR-DOC-004
  - JR-DOC-005
source_of_truth_for:
  - product-definition
  - value-proposition
  - minimum-release-scope
  - success-definition
supersedes: []
---

# Journey Reliability Service Plan v2.2

## 1. Executive Summary

### 1.1 한 줄 정의

서울 내 버스·지하철 복합 여정에서 단일 예상 소요시간 대신 **실제 관측에 근거한 도착시간 불확실성**을 계산해, 출발 전에는 목표 정시확률에 따른 권장 출발시각을, 이동 중에는 실제 사건을 반영한 정시 도착확률을 갱신하는 반응형 Web App.

### 1.2 사용자가 답을 얻어야 하는 질문

**출발 전**
> 약속시간까지 늦지 않으려면 언제 출발해야 하는가?

**이동 중**
> 지금까지 실제로 발생한 상황을 반영하면 이제 제시간에 도착할 가능성은 어느 정도인가?

### 1.3 현재 프로젝트 판정

**Demo Corridor-level Data Feasibility: GO**

실제 확인된 것:
- 서울 버스 Prediction/Position 호출과 `vehId` direct join
- bus `stopFlag` Actual transition
- Route A 01A target range 실제 traverse-time 11건
- 지하철 Arrival/Position 호출
- Route A 4개 station×line의 `btrainNo↔trainNo` join 100% 재확인
- 실제 `arvlCd=1` 및 일부 ActualArrivalInterval 발생
- mixed bus+subway Route A/B 구조
- Route B 압구정 subway→147 realtime station/route/stop/WAIT source interoperability
- Demo ACCESS WALK 297 m/245 s
- BUS→SUBWAY street component 143 m/101 s
- FINAL WALK STATION_CENTER→POI 329 m/300 s
- 교대 3→2 공식 transfer rows: OA-22521 144 s, OA-13290 63 s
- Bus future WAIT source feasibility

아직 확인/완료되지 않은 것:
- 실제 Journey Probability Engine 결과
- 01A target-leg Prediction→Actual residual artifact와 multi-window maturity
- 충분한 subway Actual/residual distribution: Phase 1 usable window 22~33분, 역삼 Actual 0건
- 안국 station-internal entrance→platform time
- OA-22522 timetable의 2026-08 current validity
- `SUBWAY_TO_BUS`의 BUS_SKIPPED/Reforecast product implementation
- Web App E2E
- true source/collector lateness profile
- 분산처리 benchmark/failure/correctness
- citywide 일반화

따라서 제품 설명에 “서울 전체 정시확률 서비스 완성”을 사용하지 않는다.

---

## 2. Problem

기존 교통정보는 보통 “3분 후 도착”, “총 50분”과 같은 point estimate를 중심으로 한다.

그러나 약속·출근·시험·면접 등 deadline이 있는 이동에서 사용자는 평균값보다 **tail risk와 회복 가능성**을 판단해야 한다.

예:
- 평소 50분이지만 오늘 60분을 넘길 가능성은?
- 첫 버스를 보내면 09:30 이전 도착확률이 얼마나 바뀌는가?
- 환승을 놓쳐도 다음 차량으로 회복 가능한가?
- 안전하게 도착하려면 평균보다 얼마 일찍 나가야 하는가?

제품 문제를 “ETA 정확도 경쟁”으로 정의하지 않는다.

문제는 **대중교통 Journey uncertainty를 사용자 의사결정 단위로 변환하지 못하는 것**이다.

---

## 3. Product Positioning

### 3.1 이 서비스가 아닌 것

- 새 교통관제 ETA provider
- 최단경로 엔진
- 서울 전체 이동시간을 정확히 예언하는 AI
- 사고 발생확률 예측기
- 개인 승차가능성 예측기

### 3.2 이 서비스인 것

기존 서울 교통 API의 경로/ETA/상태를 입력으로 사용하고,
실제 관측 오차와 이동시간 변동성을 누적해 **선택된 Journey의 신뢰도 층**을 제공한다.

### 3.3 차별화 출력

단일:
`예상 50분`

대신:

- P50 도착시각
- P90 도착시각
- 목표시각 내 도착확률
- 목표 신뢰도 기준 권장 출발시각
- 계획 연결 성공확률
- 최종 정시확률
- 현재 support/fallback
- 실제 사건 이후 변화량

---

## 4. Target User / Job

### Primary Job

시간 약속이 있는 서울 대중교통 이용자가
**빠른 경로**가 아니라 **늦지 않을 가능성을 이해하고 출발시각을 결정**할 수 있어야 한다.

### Secondary Job

이동 중 계획이 깨졌을 때
“이미 늦었나?”를 감으로 판단하지 않고 현재 상태를 반영한 남은 Journey 결과를 확인한다.

### 사용하지 않는 Persona 가정

특정 연령·직업·거주지를 제품 truth로 고정하지 않는다.
Demo Persona는 사용자 흐름 설명용이다.

---

## 5. Product Principles

1. **Evidence before model** — 데이터 연결이 증명되기 전 기능을 확정 결과처럼 말하지 않는다.
2. **Uncertainty honesty** — support/fallback/unmodeled uncertainty를 숨기지 않는다.
3. **Conditional truth** — “이 경로 기준”, “현재 관측 기준”처럼 조건을 명시한다.
4. **Observation beats assumption** — 팀 문서와 live API가 충돌하면 live evidence 우선.
5. **Baseline before ML** — empirical baseline보다 나아야 ML을 사용한다.
6. **No fake precision** — 작은 표본에 소수점 확률을 붙이지 않는다.
7. **User event is fact** — `BUS_SKIPPED` 같은 실제 사건은 예측하지 않고 상태로 확정한다.
8. **Completed history stays fixed** — Reforecast에서 이미 끝난 이동을 다시 난수화하지 않는다.

---

## 6. Scope

### 6.1 Minimum Release In

- Responsive Web App
- 서울 내 검증 Demo OD/Route 중심
- BUS + SUBWAY mixed journey
- `BUS_TO_SUBWAY`
- `SUBWAY_TO_BUS` contract + 실제 대안 Route B의 realtime E2E proof
- `SUBWAY_TO_SUBWAY`
- ACCESS/FINAL WALK
- PRE_TRIP analysis
- IN_TRIP Reforecast
- P50/P90
- on-time probability
- p*=90% recommended departure
- planned connection success vs final on-time 분리
- support/fallback/freshness 표시
- 실제 Raw→UI probability trace
- distributed engineering proof

### 6.2 Out

- 전국/수도권 전체 지원
- TAGO
- citywide station resolver 완성
- citywide accuracy/SLA
- 미래 희귀 사고 probability
- 개인별 버스 탑승 실패 probability
- 네이티브 앱
- 로그인/소셜 그래프
- push notification
- route optimization/route ranking product
- mandatory LightGBM
- probability를 생성하는 generative AI

---

## 7. Route Policy

Minimum Release는 **경로 탐색 제품이 아니다.**

`SRC-SEOUL-005`가 반환한 route alternatives의 **provider order를 유지**하고, 현재 지원범위에서 ID/leg를 해석할 수 있는 첫 candidate를 분석 대상으로 선택한다. Reliability score로 route order를 다시 정하지 않는다.

Primary Demo는 Phase 0에서 반복 재현된 **Route A**를 사용한다. Route B는 같은 OD의 cross-mode 검증용 대안이며 일반 사용자에게 route-comparison 제품으로 노출하지 않아도 된다.

경로 간:
- “가장 신뢰도 높은 경로”
- “가장 빠른 경로 vs 안전한 경로 비교”
- 자동 경로 최적화

는 Next Step이다.

따라서 사용자 문구도 다음과 같이 제한한다.

**허용**
> 이 경로를 기준으로 09:30 전 도착확률은 87%입니다.

**금지**
> 서울에서 가장 안전한 경로입니다.

---

## 8. Primary Evidence Route A

### 목적지

멀티캠퍼스 역삼  
서울특별시 강남구 테헤란로 212

### Transit 구조

`삼청동 → 01A → 안국 → 3호선 → 교대 → 2호선 → 역삼 → Final WALK → 멀티캠퍼스 역삼`

### 역할

- 가장 깊은 Actual/Residual/Probability 검증
- Product E2E
- Demo primary story
- distributed trace source

### 현재 Evidence 한계

- Bus 01A: target range traverse-time 11건은 확보됐지만 Prediction→Actual residual이 아니며 single-window/고분산이다.
- Subway: Route A 4 node join은 VERIFIED지만 usable window가 quota로 22~33분이었고 역삼 `arvlCd=1`/Actual interval은 0건이다.
- Demo ACCESS_WALK은 VERIFIED point estimate지만 walking variance는 미모델링이다.
- 01A→안국 BUS_TO_SUBWAY street component는 143 m/101 s로 VERIFIED, entrance→platform은 `UNMODELED_UNCERTAINTY`다.
- FINAL_WALK은 329 m/300 s로 VERIFIED하되 **STATION_CENTER 기반**이며 실제 station exit 기반이 아니다.
- 교대 3→2 공식 row는 VERIFIED; Tier-0 reference는 PD-031에 따라 OA-22521 144 s를 사용한다.
- OA-22522 timetable ingest는 가능하지만 current validity가 미검증이다.

---

## 9. Secondary Cross-Mode Route B

### 목적

제품 엔진이 `SUBWAY_TO_BUS`를 실제 공개 경로와 realtime source에 연결할 수 있다는 Evidence를 만든다.

### Phase 0에서 이미 VERIFIED인 구조

새 OD를 찾기 전에 같은 삼청동→역삼 OD의 실제 mixed-route 대안을 사용한다. Phase 0 Raw에는 다음 대안이 존재한다.

```text
01A 춘추문→안국역6번출구
→ 3호선 안국→압구정
→ 147 압구정역4번출구→역삼역6번출구
```

해당 raw의 provider value는 `time=52`, `distance=13048`이며, 이 값은 Reliability Ground Truth가 아니라 route-provider metadata다.

### Phase 1에서 추가 VERIFIED된 것

- 압구정 3호선 realtime `statnId=1003000336`
- `147 routeId=100100026` realtime route
- 압구정역4번출구/역삼역6번출구 bus stop ID exact join
- 147 1시간 realtime WAIT source/vehicle turnover feasibility

따라서 Route B의 **structural + realtime source interoperability는 VERIFIED**다.

아직 남은 것:
- subway alight→bus boarding point의 실제 Transfer duration decomposition
- `BUS_SKIPPED` state mutation
- next candidate selection
- Journey Probability Reforecast 구현/테스트

즉 **source feasibility와 product Reforecast implementation을 분리한다.**

Route B는 Route A 수준의 장기 probability maturity를 요구하지 않고 cross-mode contract의 secondary proof로 사용한다.


## 10. Main User Journey

### Pre-trip

1. 사용자가 출발지, 목적지, 목표 도착시각을 입력한다.
2. 시스템이 지원 가능한 structural route를 얻는다.
3. 현재 Evidence/Distribution으로 Journey simulation을 수행한다.
4. P50/P90/P(on-time)을 제공한다.
5. p*=90%를 만족하는 recommended departure가 계산 가능하면 제공한다.
6. support/fallback/unmodeled uncertainty를 같이 표시한다.

### In-trip

1. 사용자가 Journey를 시작한다.
2. 완료된 leg와 현재 state를 업데이트한다.
3. user event 또는 실시간 상태 변화가 발생한다.
4. 완료된 부분은 fixed.
5. 남은 Journey만 다시 계산한다.
6. 변경 전/후 확률과 이유를 보여준다.

---

## 11. Key Event: BUS_SKIPPED

`BUS_SKIPPED`는 다음을 의미한다.

- 시스템이 “혼잡해서 못 탈 확률”을 계산한 것이 아님
- 사용자가 실제로 해당 bus를 타지 않았다고 확정
- 기존 candidate branch 제거
- 현재시각 고정
- 다음 feasible bus부터 Wait/남은 Journey 재평가

이를 통해 원래 Main Use Case인:
`지하철 → 버스 환승 → 한 대 보냄 → 정시확률 재확인`
을 표현할 수 있다.

---

## 12. Recommended Departure 의미

권장 출발시각은 글로벌 최적 route 출발시각이 아니다.

정의:

> **현재 선택된 structural route를 기준으로**, 목표시각 이전 도착확률이 사용자의 목표 `p*` 이상이 되는 가장 늦은 출발 후보시각.

출발시각이 바뀌면 해당 시각의:
- Wait/Service availability model
- connection feasibility
- time-conditioned travel distribution

을 다시 평가한다.

**Near-now**에서는 realtime vehicle/train candidate를 사용할 수 있다. **미래 시각**에서는 정확한 미래 vehicle ID를 필수로 하지 않고, 검증된 지하철 timetable 또는 time-conditioned empirical headway/wait distribution을 사용한다.

동일 Journey distribution을 시간축으로 단순 이동하지 않는다.

계산 근거가 부족하면 “권장 출발시각 계산 불가”를 허용한다.

---

## 13. Evidence Confidence Product Policy

확률 숫자와 confidence를 같은 것으로 표현하지 않는다.

예:
- `정시 도착확률 82%`
- `근거 수준 낮음`

이 조합은 가능하다.

사용자에게 최소:
- 실측 기반 여부
- fallback 여부
- 마지막 업데이트
- 중요한 미모델링 uncertainty

를 전달한다.

---

## 14. Validation Claim Policy

Leg-level residual/quantile validation과 whole-Journey probability calibration을 같은 것으로 표현하지 않는다.

검증 범위는 최소 다음 중 하나로 기록한다.

- `COMPONENT_ONLY`: Bus/Subway/WALK/Transfer 개별 입력만 검증
- `CORRIDOR_REPLAY`: 실제 서비스 관측을 이용해 Corridor Journey를 replay/backtest
- `END_TO_END`: 독립적인 실제 Journey outcome으로 전체 P(on_time)을 검증

Minimum Release에서 `END_TO_END calibrated`라는 표현은 실제 해당 검증자료가 있을 때만 사용한다.

---

## 15. AI Role

### Core가 아님

AI는:
- P(on-time)
- P50/P90
- route
- Actual
- Residual

을 생성하지 않는다.

### Optional

실제 계산 결과와 근거 field를 이용한:
- “왜 확률이 바뀌었는가” 설명
- 운영 리포트 요약

만 후보로 둔다.

Evidence를 벗어난 원인 설명은 숨긴다.

---

## 16. Success Definition

### Product DONE

실제 Demo Corridor에서 사용자가:

`입력 → 실제 Probability 결과 → Journey 시작 → User Event → Reforecast → 결과 확인`

을 완료할 수 있다.

### Data DONE

한 실제 Journey 결과가:

`Raw → Observation → Actual → Residual → Distribution → Simulation → UI`

로 역추적된다.

### Engineering DONE

분산 처리 시연은:
- 실제 multi-worker 참여
- replay throughput
- failure recovery
- shuffle/state evidence
- optimization 전후 correctness

를 남긴다.

---

## 17. Failure Definition

다음 중 하나면 최종 “성공” 표현을 낮춘다.

- Subway Actual 표본 없이 지하철 empirical probability라고 주장
- mock probability를 실제 demo 결과로 사용
- Route B source interoperability만으로 `SUBWAY_TO_BUS Reforecast product가 구현 완료`라고 표현
- selected-route conditional 결과를 global route recommendation처럼 표현
- small-N/fallback을 숨김
- distributed benchmark에 실제 worker participation 증거가 없음
- leg-level calibration만으로 whole-Journey probability가 calibrated라고 주장

---

## 18. 한 문장 완료 정의

**사용자는 서울 내 검증된 mixed-mode Journey에서 실제 공개 교통 관측을 기반으로 한 도착시간 분포와 정시 도착확률을 확인하고, 목표 신뢰도를 만족하는 출발시각이 계산 가능한 경우 그 시각을 안내받으며, 이동 중 실제 사건이 발생하면 완료된 이동을 고정한 채 남은 Journey의 확률 변화를 다시 확인할 수 있다.**
