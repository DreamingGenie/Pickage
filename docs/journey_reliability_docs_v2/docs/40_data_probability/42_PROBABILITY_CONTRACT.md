---
doc_id: JR-DOC-042
title: Journey Probability Contract
version: 1.2
status: REVIEW
owner: PM/Data/Backend
last_updated: 2026-08-22
depends_on:
  - JR-DOC-040
  - JR-DOC-041
  - JR-DOC-021
source_of_truth_for:
  - journey-probability-math
  - recommended-departure
  - reforecast
  - distribution-composition
supersedes: []
---

# Journey Probability Contract

## 1. 목적

각 교통구간의 “지연 확률”을 단순 더하거나 곱하지 않는다.

전체 Journey의 상태/connection을 simulation하고,
최종 도착시각 분포에서 사용자 metric을 계산한다.

---

# 2. Journey Composition

Canonical:

```text
ACCESS_WALK
+ WAIT(mode_1)
+ TRANSIT_RIDE(mode_1)
+ TRANSFER(mode_1→mode_2)
+ WAIT(mode_2)
+ TRANSIT_RIDE(mode_2)
+ ...
+ FINAL_WALK
```

Route A:

```text
ACCESS_WALK
+ BUS_WAIT
+ BUS_RIDE
+ TRANSFER_BUS_TO_SUBWAY
+ SUBWAY_WAIT
+ SUBWAY_3_RIDE
+ TRANSFER_SUBWAY_TO_SUBWAY
+ SUBWAY_WAIT
+ SUBWAY_2_RIDE
+ FINAL_WALK
```

---

# 3. Leg Distribution Policy

## 3.1 Empirical first

실측 sample이 충분한 경우:
- empirical sample
- empirical quantile
- streaming quantile structure

를 우선.

## 3.2 Sparse fallback

fallback은 mode별 독립 설계.

Bus 예시 계층:

```text
route × pair × time bucket
→ route × pair
→ route × broader time
→ route
→ corridor/global supported bus pool
```

실제 hierarchy는 데이터 profile 후 version.

Subway도 line/direction/station-pair/time/lead-time을 이용하되
support가 없는 조합에 임의 정규분포를 넣지 않는다.

## 3.3 WALK

현재:
`TMAP DETERMINISTIC_POINT`

- point time 사용 가능
- variance는 **UNMODELED**
- Journey result는 `PARTIAL_MODEL`

임의 ±20% 같은 분포를 넣지 않는다.

## 3.4 Transfer decomposition

### SUBWAY_TO_SUBWAY — Route A 교대 3→2 Tier-0

Phase 1 official rows:
- OA-22521: 4개 door/direction row 모두 **144 s**
- OA-13290: 75 m / **63 s**

`PD-031`에 따라 runtime Tier-0 reference는 **144 s**를 사용한다.
63 s는 geometric/1.2m/s sanity reference일 뿐, 평균하거나 확률적으로 섞지 않는다.
둘 다 personal empirical distribution이 아니므로 `uncertainty_model=UNMODELED`다.

### BUS_TO_SUBWAY / SUBWAY_TO_BUS

가능한 경우 다음을 분리한다.

```text
street component (TMAP point)
+ station internal access/egress component (official/static/fixed fallback)
```

Route A BUS_TO_SUBWAY는 street 143 m/101 s까지 VERIFIED됐으나 station-internal entrance→platform이 없다.
따라서 전체 transfer는 `PARTIAL/UNMODELED_UNCERTAINTY`로 유지한다.

어느 component도 empirical distribution이 아니면 variance는 `UNMODELED` 또는 `PARTIAL`로 유지한다.
station center 좌표를 출구/승강장처럼 사용하지 않는다.

---

# 4. Correlation

독립 가정이 특히 위험한 경우:
- 같은 train의 연속 역 delay
- 같은 bus trajectory의 인접 section time
- 같은 route의 shared congestion condition

## 4.1 Tier-0 구현정책

가능하면 **section을 여러 개 독립 sample해 합산하지 않고, 제품 Leg 전체(A→B)의 직접 관측 duration distribution을 사용한다.**

Route A 예:
- BUS_RIDE: 춘추문→안국 버스 leg whole-duration distribution 우선
- SUBWAY_3_RIDE: 안국→교대 whole-leg duration 우선
- SUBWAY_2_RIDE: 교대→역삼 whole-leg duration 우선

이렇게 하면 같은 vehicle/train 안의 section correlation을 임의 독립합산하는 오류를 줄일 수 있다.

## 4.2 Whole-leg가 부족할 때

Subway 후보:
1. current delay/state condition
2. continuation/delay increment
3. trajectory/block bootstrap

Bus 후보:
1. direct A→B empirical
2. section composition이 필요하면 같은 simulation에서 shared route-state/context

## 4.3 Cross-leg dependence

서로 다른 mode/vehicle 사이의 잔여 상관(예: 광역 교통상황 공통 충격)은 현재 Evidence가 부족하다.
Tier-0에서는 명시적으로 모델링하지 않되 `CROSS_LEG_DEPENDENCE_UNMODELED` limitation을 남긴다.

**독립이라고 검증되었다고 주장하지 않는다.**


# 5. Boarding Feasibility

Transfer와 Wait 분리.

후보 vehicle/train `j`를 탈 수 있는 조건:

```text
arrival_at_boarding_point + safety_buffer
<= candidate_departure_at
```

Tier-0 safety/transfer buffer는 `PD-016`.

정확 buffer 값은 실제 source/운영 검토 후 rule version으로 고정.

후보 service를 exact ID로 구성할 수 없는 미래 PRE_TRIP 구간에서는 검증된 timetable 또는 empirical wait/headway distribution으로 WAIT를 sample한다. 즉 exact future bus vehicle ID는 correctness 전제가 아니다.

Phase 1 `EVD-WAIT-001`은 source feasibility를 증명하지만 20초 polling `exps1` snapshots는 serial-correlated하다. Distribution build에서는 `PD-034`에 따라 vehicle arrival/headway event 또는 dependence-aware sample unit을 사용한다.

---

# 6. Monte Carlo

한 simulation `s`:

1. 현재 Journey state를 읽는다.
2. 완료 leg는 실제 fixed duration/state 사용.
3. future access/wait/ride/transfer 입력을 sample/reference.
4. boarding candidate feasibility 판정.
5. miss면 next feasible candidate.
6. 목적지까지 진행.
7. final arrival `A_s` 저장.

N번 반복.

## 6.1 On-time

목표 `T`:

```math
P_on_time = (1/N) * Σ I(A_s <= T)
```

## 6.2 P50/P90

```text
P50 = Q_0.50({A_s})
P90 = Q_0.90({A_s})
```

## 6.3 Planned Connection Success

계획 candidate를 모두 지킨 simulation의 비율.

## 6.4 Final On-time

connection miss 이후 recovery까지 포함해 target 이전 도착한 비율.

둘은 독립 metric이다.

---

# 7. Monte Carlo N

PM 범위:
`2,000 <= N <= 5,000`

## Runtime rule proposal

1. N=2,000에서 시작 가능
2. on-time indicator의 Wilson 95% interval half-width를 계산해 **Monte Carlo sampling error만** 추정
3. 사용자 표시 정밀도에 비해 simulation sampling noise가 크면 N을 증가
4. 최대 5,000
5. 5,000에서도 불안정하면 `SIMULATION_PRECISION_LIMIT` limitation 기록

최종 half-width acceptance threshold는 G2 benchmark에서 고정한다.

이 interval은 **모델/데이터 uncertainty의 confidence interval이 아니다.** 모델 calibration/support는 별도 Validation 결과로 관리한다.

**주의:** D-050의 2k~5k 범위를 유지하면서 N을 근거 없이 2,500 같은 상수로 고정하지 않는다.

---

# 8. Recommended Departure

## 8.1 정의

선택 structural route `R`, 목표시각 `T`, 목표확률 `p*`에 대해:

```text
latest d
such that
P(A <= T | depart=d, route=R) >= p*
```

## 8.2 중요한 조건

`depart=d`가 바뀌면:
- time-conditioned WAIT source
- service availability
- ride distribution/context
- connection feasibility

을 다시 구성한다.

Near-now는 realtime candidate를 사용할 수 있다. 미래 시각은:
- Subway: verified timetable 또는 empirical headway
- Bus: time-conditioned empirical wait/headway

를 기본 후보로 한다.

같은 total-time distribution을 단순 `d`만큼 shift하지 않는다.

## 8.3 탐색

대중교통 service는 discrete하므로 확률 함수가 매끄럽거나 strict monotonic이라고 전제하지 않는다.

따라서 correctness contract:
- candidate departure grid 또는 coarse-to-fine
- 각 candidate에서 service availability/WAIT model 재평가
- 조건 만족 후보 중 가장 늦은 시각 선택

binary search는 monotonicity가 실험으로 확인되고 정확성을 보존할 때만 optimization으로 사용할 수 있다.

## 8.4 결과 문구

`이 경로 기준 90% 권장 출발`

route-global 표현 금지.

## 8.5 Unavailable

다음이면 unavailable 가능:
- future WAIT/service availability source 부족
- critical leg distribution insufficient
- target window 내 feasible departure 없음

---

# 9. Reforecast

현재 state `S_t`에서:

```text
P(final arrival | observed history H_t, current state S_t)
```

를 다시 계산한다.

## BUS_SKIPPED

고정:
- completed subway/bus/walk
- transfer completed
- current time
- skipped bus fact

제거:
- skipped bus branch

재계산:
- next bus wait
- future ride/transfer
- final arrival

---

# 10. Confidence / Support

Probability와 confidence는 분리.

Journey confidence는 가장 약한 leg를 무조건 그대로 복사하는 단순 min rule로 확정하지 않는다.

초기 policy:
- leg별 support/fallback metadata 유지
- Journey에 `fallback_summary`, `limitations`
- label mapping은 `43_VALIDATION_PLAN.md`에서 calibration 후 version

---

# 11. Support Threshold

사전 `n=30` 같은 값 금지.

절차:
1. high-support historical window 확보
2. down-sample size별 quantile variability
3. bootstrap confidence interval
4. hold-out empirical coverage
5. 안정화 지점 후보 도출
6. mode/condition별 threshold version

support rule:
`SUPPORT_RULE_V1`은 calibration 완료 후 생성.

---

# 12. ML Promotion

LightGBM Quantile은 다음 역할만 가능:
- conditional travel-time/residual quantile
- sparse generalization

최종 on-time probability를 직접 black-box label로 대체하지 않는다.

Promotion은 `43_VALIDATION_PLAN.md` 통과 시.

---

# 13. Validation Scope

결과의 validation level을 분리한다.

```text
UNVALIDATED
COMPONENT_ONLY
CORRIDOR_REPLAY
END_TO_END
```

- `COMPONENT_ONLY`: Bus/Subway leg distribution의 hold-out 성능만 검증
- `CORRIDOR_REPLAY`: 동일 corridor의 실제 관측 service sequence로 Journey 결과를 replay/backtest
- `END_TO_END`: 독립적인 실제 Journey outcome과 P(on_time)을 비교

**Component calibration만으로 final Journey P(on_time)이 calibrated라고 주장하지 않는다.**

---

# 14. Reproducibility

각 result는:
- engine version
- distribution versions
- rule versions
- seed
- N
- state version

을 기록한다.

fixed seed fixture로 regression 가능해야 한다.

---

# 15. Known Limitations

- WALK uncertainty unmodeled
- static transfer variance unmodeled
- subway empirical sample maturity 부족
- citywide station/train behavior 미검증
- route alternatives reliability comparison 없음
- cross-mode/vehicle 간 잔여 correlation 일부 미모델링
- future Bus WAIT **source feasibility는 검증됐으나 event-unit/multi-window distribution maturity 미검증**
- future Subway WAIT timetable의 current validity 미검증
- 01A target-leg Prediction→Actual residual artifact 미생성
- whole-Journey END_TO_END calibration 미검증

이 limitation은 모델이 좋아졌다고 자동 삭제하지 않고 Evidence로 해소한다.
