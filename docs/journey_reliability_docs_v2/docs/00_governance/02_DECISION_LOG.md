---
doc_id: JR-DOC-002
title: Normalized Decision Log
version: 1.1
status: LOCKED
owner: PM
last_updated: 2026-08-22
depends_on:
  - JR-DOC-001
source_of_truth_for:
  - product-decisions
supersedes:
  - legacy result.zip/docs/05_DECISION_LOG.md as product-decision SoT
---

# Normalized Decision Log

> Phase 0의 기존 `D-xxx`에는 Decision과 Evidence가 섞여 있었다.
> 이 문서는 **제품/정책 결정만** 정규화한다.
> 실제 관측 사실은 `03_EVIDENCE_REGISTER.md`가 정본이다.

| ID | Status | Decision | Reason | Evidence / legacy_ref | Owner |
|---|---|---|---|---|---|
| PD-001 | FIXED | 핵심 제품은 버스·지하철 전체 Journey의 도착시간 분포, 목표시각 내 도착확률, 권장 출발시각, 이동 중 Reforecast를 제공하는 Web App이다. | Main Use Case | legacy D-001/D-003 | PM |
| PD-002 | FIXED | 원천 ETA를 대체하지 않고 Prediction→Actual→Residual 기반 Reliability layer를 만든다. | 데이터 정직성/차별점 | legacy D-004 + Phase 0 | PM/Data |
| PD-003 | FIXED | Transit Reliability Core source는 **서울시/서울교통공사 제공 AND 서울 행정구역**을 기본 조건으로 한다. | MVP 범위 통제 | legacy D-002/D-041 | PM |
| PD-004 | FIXED | TMAP은 Transit reliability source가 아니라 WALK routing utility 예외로 허용한다. | 실제 목적지까지 계산 필요 | legacy D-040/D-045 | PM |
| PD-005 | FIXED | 최종 도착 경계는 목적 정류장/역이 아니라 실제 약속장소까지의 마지막 WALK 완료 시점이다. | 사용자 의사결정과 일치 | legacy D-039 | PM |
| PD-006 | FIXED | Demo OD는 삼청동 demo coordinate → 멀티캠퍼스 역삼이며, Primary Route A는 실제 mixed-route 상위 경로 `01A → 3호선(안국→교대) → 2호선(교대→역삼)`을 사용한다. | Phase 0 실제 응답/ID 검증이 가장 강함 | EVD-ROUTE-003 | PM |
| PD-007 | FIXED | `BUS_TO_SUBWAY`, `SUBWAY_TO_BUS`, `SUBWAY_TO_SUBWAY`를 1급 TransferType으로 모델링한다. | modal-order 독립 Journey Engine | v1.1 design | PM/Planner |
| PD-008 | FIXED | Transfer는 다음 boarding point까지의 이동만, Wait는 차량/열차 대기만 담당한다. | 시간 중복 방지 | v1.1 design | PM/Planner |
| PD-009 | FIXED | `SUBWAY_TO_BUS` 검증은 새 OD를 먼저 찾지 않고, **같은 삼청동→역삼 OD의 Phase 0 실제 대안 경로(Route B: 01A→3호선→147 계열)**를 우선 사용한다. | 이미 실제 Raw에 cross-mode path가 존재해 범위 확장을 줄일 수 있음 | EVD-CROSS-001 | PM/Planner |
| PD-010 | SUPERSEDED | “두 번째 SUBWAY→BUS 경로를 추가하지 않는다.” | Cross-mode product contract와 충돌 | PD-009가 대체 | PM/Planner |
| PD-011 | FIXED | `BUS_SKIPPED`는 승차실패 확률모델의 결과가 아니라 사용자 확정 Event로 처리한다. | user-level boarding-failure GT 부족 | legacy D-007 | PM |
| PD-012 | FIXED | 미래 희귀 사고 발생확률 예측은 Minimum Release에서 제외한다. 현재 발생 사건은 context로만 활용 가능하다. | 장기 incident history 부족 | legacy D-006 | PM/Data |
| PD-013 | FIXED | Probability baseline은 empirical/statistical method가 우선이며 LightGBM은 hold-out 검증에서 이득이 있을 때만 승격한다. | 불필요한 ML 방지 | legacy D-005 | PM/Data |
| PD-014 | FIXED | 기본 목표 정시확률 `p*=90%`. 사용자 지정이 있으면 지정값을 사용한다. | deadline 의사결정 기본값 | legacy D-050 | PM |
| PD-015 | FIXED | Monte Carlo 운영 범위는 2,000~5,000으로 두되, 실행 N은 convergence와 **simulation sampling error** 기준으로 범위 안에서 선택한다. | legacy D-050을 검증계약과 정합화 | legacy D-050 | PM/Data |
| PD-016 | FIXED | Tier-0 missed connection은 고정 safety/transfer buffer 정책으로 시작하고, 실제 headway/transfer evidence가 충분할 때만 upgrade한다. | 실시간 headway/transfer GT 부족 | legacy D-049 | PM |
| PD-017 | FIXED | Minimum Release는 route optimizer가 아니다. Route provider의 대안 목록 중 **provider order를 유지하면서 현재 지원범위에서 ID/leg가 해석 가능한 첫 candidate**를 분석 대상으로 선택한다. | 신뢰도 제품과 경로최적화 제품의 범위 분리 | D0 reconciliation | PM/Planner |
| PD-018 | FIXED | Recommended Departure는 **선택된 structural route 조건부** 결과다. 후보 출발시각마다 해당 시간대의 Wait/Service availability model을 다시 평가하며 동일 분포를 단순 시간 이동하지 않는다. | 대중교통 대기/서비스가 시간대에 따라 불연속적으로 변함 | D0 reconciliation | PM/Planner |
| PD-019 | FIXED | Recommended Departure 탐색은 monotonicity를 전제한 binary search를 정확성 기본계약으로 사용하지 않는다. candidate time grid/coarse-to-fine을 기본으로 한다. | discrete service 특성 | D0 reconciliation | PM/Planner |
| PD-020 | FIXED | Minimum Support 숫자는 임의 `n`으로 선결정하지 않고 down-sampling/bootstrap/coverage stability로 calibration한다. | small-N honesty | D0 reconciliation | PM/Data |
| PD-021 | FIXED | WALK/정적 Transfer에 실제 변동성 분포가 없으면 `UNMODELED_UNCERTAINTY`를 명시한다. 임의 variance를 empirical distribution처럼 만들지 않는다. | Probability honesty | D0 reconciliation | PM/Data |
| PD-022 | FIXED | TMAP/Kakao 등 외부 utility는 Transit Reliability 모델의 학습/실측 신뢰도 label로 사용하지 않는다. | Source policy 경계 | PD-003/PD-004 | PM |
| PD-023 | FIXED | Citywide 정확도/SLA/crosswalk 완성은 Minimum Release 범위 밖이다. | Phase 0 evidence scope | Phase 0 | PM |
| PD-024 | FIXED | Final Demo 숫자는 실제 pipeline result만 허용한다. illustrative 숫자는 구조 설명에만 사용한다. | 평가 신뢰성 | Honesty principle | PM |
| PD-025 | FIXED | 현재 계정에서 data.go.kr 서울 버스 관련 credential은 동일 key이므로 `DATA_GO_BUS_API_KEY` 하나로 관리한다. 값이 서비스별로 갈리면 다시 분리한다. | 중복 secret 입력 제거 | legacy D-046 | PM/Infra |
| PD-026 | FIXED | PRE_TRIP의 future Wait는 **정확한 미래 vehicle ID를 필수로 하지 않는다.** near-now는 realtime candidate를 사용하고, 미래 candidate time은 검증된 timetable 또는 time-conditioned empirical headway/wait distribution을 사용한다. | 버스는 미래 특정 vehicle을 안정적으로 열거할 근거가 없고 지하철 timetable source는 별도 검증 필요 | D0 final review | PM/Data |
| PD-027 | FIXED | Tier-0 correlation은 가능하면 **whole-leg empirical duration**을 직접 사용해 내부 section 독립합산을 피한다. 서로 다른 mode/vehicle 간 잔여 상관은 evidence가 없으면 모델링하지 않고 limitation으로 남긴다. | 구현 가능성과 과도한 독립가정 방지의 균형 | D0 final review | PM/Data |
| PD-028 | FIXED | WALK/Transfer 계산의 모든 endpoint는 좌표의 의미와 출처(`ORIGIN_POINT`, `BUS_STOP`, `STATION_CENTER`, `STATION_EXIT`, `PLATFORM_REFERENCE`, `POI`)를 기록한다. station center와 exit를 조용히 동일시하지 않는다. | 몇십~수백 m 차이가 transfer/final WALK를 바꿀 수 있음 | D0 final review | PM/Data |
| PD-029 | FIXED | `SUBWAY_TO_BUS` capability는 **구조적 mixed-route 존재**와 **realtime ID/Wait/Reforecast E2E**를 분리해 판정한다. 구조는 Phase 0 Raw에서 VERIFIED, E2E는 추가 Evidence 전까지 CONDITIONAL/TO_VERIFY다. | “경로 존재”와 “Reliability 계산 가능”의 구분 | EVD-CROSS-001/EVD-CROSS-002 | PM/Planner |
| PD-030 | FIXED | Full-Journey probability의 “calibrated” claim은 실제/재구성 가능한 journey-level hold-out 검증을 통과한 경우에만 사용한다. leg-level calibration만으로 whole-journey calibration을 주장하지 않는다. | component correctness ≠ journey probability calibration | D0 final review | PM/Data |

## Superseded 기록

- 과거의 “SUBWAY→BUS 추가 검증 없음” 정책은 `PD-010 SUPERSEDED`.
- 최신 cross-mode 전략은 `PD-009`와 `PD-029`.
