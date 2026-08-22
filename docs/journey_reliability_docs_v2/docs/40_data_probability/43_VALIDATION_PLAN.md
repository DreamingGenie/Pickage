---
doc_id: JR-DOC-043
title: Probability and Data Validation Plan
version: 1.1
status: LOCKED
owner: Data/PM
last_updated: 2026-08-22
depends_on:
  - JR-DOC-042
  - JR-DOC-041
source_of_truth_for:
  - validation-protocol
  - support-calibration
  - ml-promotion-gate
supersedes: []
---

# Validation Plan

## 1. 검증을 하나의 accuracy 숫자로 합치지 않는다

| Layer | Question |
|---|---|
| Data Validity | Actual/Residual을 믿고 계산할 수 있는가 |
| Identity Correctness | vehicle/train/node가 올바르게 연결되는가 |
| Distribution Quality | P50/P90가 hold-out에서 의미 있는 coverage를 갖는가 |
| Probability Calibration | 80%라 한 결과가 장기적으로 80% 수준으로 발생하는가 |
| Support Stability | small-N 결과가 표본 변화에 과민하지 않은가 |
| Reforecast Correctness | observed history를 다시 randomize하지 않는가 |
| Product Comprehension | 사용자가 P90/확률/confidence를 혼동하지 않는가 |
| Distributed Correctness | scale-out/optimization 후 논리 결과가 보존되는가 |

---

# 2. Validation Scope Ladder

검증수준을 단계적으로 올린다.

## V0 Engine Logic
synthetic/deterministic fixture로 state transition, transfer miss, BUS_SKIPPED, idempotency를 검증한다. 실제 calibration claim은 하지 않는다.

## V1 Component Hold-out
Bus/Subway의 Prediction→Actual/Travel Time distribution을 시간순 hold-out으로 검증한다.

## V2 Corridor Replay
동일 시간대에 관측된 실제 service/arrival sequence를 가능한 범위에서 재구성해 Route A Journey를 replay한다. 이 단계는 component를 합성한 corridor-level backtest이며, 실제 사용자 이동 outcome과 동일하다고 과장하지 않는다.

## V3 End-to-End Journey
독립적인 실제 Journey 시작/도착 outcome을 모아 P(on_time) calibration을 직접 검증한다.

Minimum Release에서 V3가 없으면 result의 `validation_scope`를 `END_TO_END`로 설정하지 않는다.

---

# 3. Split Policy

random row split을 기본으로 쓰지 않는다.

시간 누수를 막기 위해:

```text
Train: earlier time blocks
Validation: later time block
Test: latest held-out time block
```

데이터가 충분해지면 rolling-origin backtest.

동일 실제 arrival event의 여러 prediction snapshot이 train/test 양쪽으로 섞여 leakage가 생기지 않게 group split한다.

---

# 4. Baseline

최소 비교:

### B0 Provider Point Baseline
원천 ETA를 그대로 사용.

### B1 Empirical Residual Baseline
조건부 empirical residual.

### B2 Hierarchical Fallback
support-aware broader group.

ML은 B1/B2 이후.

---

# 5. Quantile Metrics

## 5.1 Pinball Loss

P50/P90별 pinball loss.

## 5.2 Empirical Coverage

예:
P90 prediction interval/bound가 hold-out actual을 약 90% 포함하는지.

정확한 tolerance는 데이터 규모를 보고 설정.

## 5.3 Sharpness

coverage만 맞추려고 지나치게 넓은 interval을 만드는지 확인.

coverage와 함께 본다.

---

# 6. On-time Probability

`V3 END_TO_END` 또는 명시적으로 정의된 `V2 CORRIDOR_REPLAY` outcome이 충분할 때만 final Journey P(on_time)의 calibration metric을 계산한다.

Leg-level outcome으로 whole-Journey Brier score를 대신하지 않는다.

## 6.1 Brier Score

```text
mean((p_i - y_i)^2)
```

## 6.2 Reliability Diagram

predicted probability bin vs observed frequency.

## 6.3 Calibration Error

ECE 또는 bin-wise absolute gap 후보.

bin 수/방식은 sample size에 따라 정하며 고정 rule version을 남긴다.

---

# 7. Lead-time Validation

Prediction reliability는 lead time에 따라 다르므로 최소 다음 축을 분리한다.

- near-arrival
- mid lead
- long lead

bucket boundary는 실제 distribution/profile 후 결정.

모든 lead time을 하나로 합쳐 “정확도”라고 말하지 않는다.

---

# 8. Support Calibration

## 목적
`LOW_SUPPORT` threshold를 데이터에서 결정.

## 절차

1. 충분한 high-support pool 선택
2. sample size를 단계적으로 down-sample
3. 각 n에서 bootstrap resampling
4. P50/P90 variability 계산
5. hold-out coverage variability 계산
6. calibration metric variability 계산
7. 결과가 안정되기 시작하는 n 구간 탐색
8. operational simplicity를 고려해 threshold 후보 선택
9. separate test period에서 재검증
10. `SUPPORT_RULE_V1` freeze

## 금지
2/4와 5000/10000의 같은 50%를 같은 evidence로 취급.

---

# 9. Monte Carlo Convergence

## Offline test

동일 Journey fixture, seed family로:

```text
N = 500, 1000, 2000, 3000, 5000
```

비교:
- P(on_time)
- P50
- P90
- runtime

## Selection

PD-015의 운영 범위 2k~5k 안에서
결과 변화와 runtime trade-off를 보고 N rule 결정.

On-time indicator에는 Wilson interval을 같이 계산해 **finite-N Monte Carlo sampling error**를 분리한다.
이 interval을 model/data uncertainty 또는 calibration confidence interval로 해석하지 않는다.

---

# 10. Reforecast Tests

## BUS_SKIPPED invariant (`TST-PROB-001`)

Given:
- completed legs
- bus wait state
- candidate A

When:
- BUS_SKIPPED(A)

Then:
- completed durations unchanged
- A selected count = 0
- next candidate used
- simulation start time >= event time
- result_version increments

## Repeat-event invariant (`TST-PROB-002`)

same idempotency key twice → result/state가 두 번 변경되지 않음.

## Connection-recovery scenario (`TST-PROB-003`)

planned connection miss sample이 final on-time success가 될 수 있음.

planned success <=? final on-time과 수학적으로 항상 단순 대소관계라고 강제하지 않고 target/context를 실제 simulation에서 확인한다.

---

# 11. Route/Departure Validation

Recommended Departure에서 candidate depart time을 바꿨을 때
실제 candidate service set이 바뀌는 fixture를 만든다.

검증:
- same distribution shift로 구현되어 있지 않음
- near-now realtime vs future timetable/empirical WAIT source가 구분됨
- future bus에 exact vehicle ID가 없어도 empirical wait model로 계산 가능하거나 unavailable 처리
- latest satisfying candidate를 선택
- no feasible candidate/source → unavailable

---

# 12. WALK / Transfer Limitation Validation

WALK/static transfer가 deterministic point인 동안:

- `UNMODELED_UNCERTAINTY`가 JourneyResult에 반드시 포함
- Evidence UI에 표시
- P90가 “모든 이동 uncertainty를 완전 포함”한다고 설명되지 않음
- WALK/Transfer endpoint의 coordinate role/source가 존재
- `STATION_CENTER`를 `STATION_EXIT`/`PLATFORM_REFERENCE`로 무근거 승격하지 않음
- BUS_TO_SUBWAY street/internal component가 분리되거나 limitation 존재

---

# 13. ML Promotion Gate

LightGBM Quantile 후보는 동일 held-out split에서 baseline과 비교.

필수:
- P50/P90 pinball loss
- empirical coverage
- calibration guardrail
- low-support segment
- inference latency/ops cost

Promotion 조건:
1. primary loss 개선이 반복 split/rolling window에서 일관
2. calibration/coverage가 실질적으로 악화되지 않음
3. low-support 또는 conditional modeling에서 명확한 추가 가치
4. serving complexity 수용 가능
5. evidence를 발표/문서에 재현 가능

하나라도 불명확하면 baseline 유지.

---

# 14. Data Gate Before Claim

### Bus mature claim 전
- multiple time windows
- residual count
- interval widths
- join/dedupe/out-of-order

### Subway empirical claim 전
- actual `arvlCd=1` events
- Prediction↔Actual matching
- interval width
- held-out coverage

### Recommended Departure claim 전
- `EVD-SCHED-001` 또는 대체 subway future WAIT source
- `EVD-WAIT-001` bus future WAIT/headway feasibility
- candidate-time별 WAIT/source 재평가 fixture

### Whole-Journey calibrated claim 전
- `validation_scope=END_TO_END`를 뒷받침하는 실제 독립 Journey outcome 필요
- V1 component calibration만으로 승격 금지

### Citywide claim 전
별도 citywide validation 필요. Minimum Release에서는 수행하지 않는다.

---

# 15. Validation Artifact

각 run:

```yaml
validation_run_id:
data_snapshot:
code_version:
rule_version:
train_window:
validation_window:
test_window:
metrics:
segment_metrics:
support_profile:
limitations:
decision:
```

`decision`:
`GO | CONDITIONAL | HOLD | FAIL`
