---
doc_id: JR-DOC-007
title: Documentation Changelog
version: 1.0
status: LOCKED
owner: PM
last_updated: 2026-08-22
depends_on: []
source_of_truth_for: []
supersedes: []
---

# Changelog

## 2026-08-22 — Documentation v2 Foundation

- v1.1의 Decision/Evidence/Implementation 상태 혼용을 분리.
- v1.1 `legacy decision 051`과 `legacy decision 056` 충돌을 정규화: Route B 없음 정책은 `PD-010 SUPERSEDED`, 최신은 `PD-009`.
- 마지막 “네 가지/세 가지” 편집 오류 제거.
- TMAP과 “서울시 데이터만” 충돌을 `PD-003/004/022`로 명시적 해결.
- Route Candidate policy 추가: Minimum Release는 선택 structural route 1개에 대한 reliability.
- Recommended Departure를 selected-route conditional로 정의하고 service candidate를 재평가하도록 변경.
- binary search를 기본 계약에서 제거.
- Minimum Support threshold를 empirical calibration 대상으로 변경.
- WALK/정적 Transfer의 미모델링 uncertainty를 숨기지 않는 정책 추가.
- Legacy `D-xxx`의 Evidence를 `EVD-*`로 분리.

## 2026-08-22 — Final Package Review

- Phase 0 selected evidence를 `baseline/phase0/`에 포함해 패키지를 self-contained하게 만들었다.
- Phase 0 raw mixed-route response를 재검토해 동일 OD 안에 `01A → 3호선 → 147`의 자연스러운 `SUBWAY_TO_BUS` alternative가 이미 존재함을 확인했다. 구조적 존재는 `EVD-CROSS-001 VERIFIED`, realtime E2E interoperability는 `EVD-CROSS-002 TO_VERIFY`로 분리했다.
- 기존 “reverse corridor부터 탐색” 계획을 폐기하고 동일 OD Route B를 우선 검증 대상으로 변경했다.
- 01A의 54건 `stopFlag 0→1`은 노선 전체 여러 정류장의 transition support이며 특정 춘추문→안국 target-leg residual 54건으로 해석하지 않도록 수정했다.
- TMAP Phase 0 성공은 generic walking API feasibility만 검증한 것으로 제한하고, Demo `ACCESS_WALK`, `BUS_TO_SUBWAY`, `FINAL_WALK`를 별도 Evidence blocker로 분리했다.
- Recommended Departure에서 미래 exact vehicle/train ID를 필수 전제로 제거하고, 미래 bus는 empirical wait/headway, subway는 timetable/empirical headway를 사용할 수 있는 time-conditioned WAIT contract로 수정했다.
- Correlation Tier-0를 whole-leg empirical duration 우선으로 구체화하고, cross-leg dependence가 미모델링이면 limitation을 남기도록 했다.
- Monte Carlo Wilson interval은 finite-N simulation error만 측정하며 model/data uncertainty 또는 calibration confidence가 아님을 명시했다.
- Validation scope를 `UNVALIDATED / COMPONENT_ONLY / CORRIDOR_REPLAY / END_TO_END`로 분리했다.
- Coordinate provenance role을 추가하고 station center/exit/platform의 묵시적 동일시를 금지했다.
- Collector가 Kafka와 별개로 immutable Bronze Raw를 보존하도록 architecture를 정정했다.
- `08_IMPLEMENTATION_STATUS.md`, `09_PHASE1_EVIDENCE_EXECUTION.md`를 추가해 구현 상태와 Agent 실증 작업을 canonical하게 관리하도록 했다.
- package manifest와 validation report를 최종 생성 순서에 맞춰 재구축한다.
