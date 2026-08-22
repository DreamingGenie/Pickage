---
doc_id: JR-DOC-005
title: Glossary
version: 1.1
status: LOCKED
owner: PM
last_updated: 2026-08-22
depends_on:
  - JR-DOC-002
source_of_truth_for:
  - terminology
supersedes: []
---

# Glossary

| Term | Canonical meaning |
|---|---|
| Demo OD / Corridor | 삼청동 demo origin coordinate와 멀티캠퍼스 역삼을 잇는 제품 검증 범위. 그 안에 여러 structural route가 존재할 수 있음 |
| Route A | Demo OD의 Primary structural route: `01A → 3호선(안국→교대) → 2호선(교대→역삼)` |
| Route B | 같은 Demo OD의 Secondary cross-mode structural route: Phase 0 Raw에 존재하는 `01A → 3호선(안국→압구정) → 147 bus` 계열. `SUBWAY_TO_BUS` E2E 검증용 |
| Journey | 실제 origin부터 실제 destination까지 이어지는 ordered leg sequence |
| Structural Route | 정류장/역/노선/환승 순서를 정의한 topology. 특정 미래 차량번호를 반드시 포함하지 않음 |
| Service Candidate | 특정 시각/상태에서 실제 탑승 가능한 bus/train 후보. realtime ID, timetable service 또는 empirical wait model이 source일 수 있음 |
| Leg | `ACCESS_WALK`, `WAIT`, `TRANSIT_RIDE`, `TRANSFER`, `FINAL_WALK` 중 하나 |
| Transfer | 한 mode/line에서 다음 boarding point까지 이동하는 물리적 이동. 다음 차량 대기시간 제외 |
| Wait | boarding point 도착 후 다음 vehicle/train을 기다리는 시간 |
| Prediction Snapshot | 원천 API가 특정 시각에 제공한 ETA/상태 관측 |
| Actual Arrival Interval | polling 사이에서 실제 도착이 발생한 것으로 판정한 시간구간 |
| Residual | `Actual - Predicted`; Actual interval이면 lower/mid/upper 보존 |
| Reliability | 특정 조건의 travel/arrival uncertainty를 실측과 명시적 fallback으로 설명하는 분포/품질 정보 |
| LegDistribution | 한 Leg의 duration uncertainty 또는 deterministic/reference input과 support/fallback metadata |
| P50 | simulated final-arrival distribution의 50 percentile |
| P90 | simulated final-arrival distribution의 90 percentile. “90% 확률로 정확히 그 시각”이 아님 |
| On-time Probability | `P(final_arrival <= target_arrival)` |
| Planned Connection Success | 원래 계획한 connection을 그대로 지킨 simulation 비율 |
| Final On-time | miss 이후 대체 service까지 포함해 target 이전 도착한 simulation 비율 |
| Recommended Departure | **선택된 route 조건에서**, 시간대별 Wait/Service model을 재평가해 목표 `p*`를 만족하는 가장 늦은 후보 출발시각 |
| Reforecast | 완료된 사실을 고정하고 남은 Journey uncertainty만 다시 계산 |
| Support | 결과를 뒷받침하는 관측수·기간·조건 coverage |
| Fallback | exact condition support 부족 시 더 넓은 실측 group 또는 fixed/reference input을 사용하는 것 |
| Calibration | 예측확률/분위수와 실제 hold-out outcome의 일치 정도. component calibration과 journey calibration을 구분 |
| Validation Scope | 결과가 `COMPONENT_ONLY`, `CORRIDOR_REPLAY`, `END_TO_END` 중 어디까지 검증됐는지 나타내는 범위 |
| Evidence | 재현 가능한 Raw/실험/공식 source로 뒷받침된 주장 |
