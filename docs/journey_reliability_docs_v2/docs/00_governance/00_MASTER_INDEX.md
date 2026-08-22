---
doc_id: JR-DOC-000
title: Master Index
version: 1.1
status: LOCKED
owner: PM
last_updated: 2026-08-22
depends_on:
  - JR-DOC-001
source_of_truth_for:
  - documentation-index
  - documentation-gates
supersedes: []
---

# Master Index

## 1. Current Project Status

| Area | Status |
|---|---|
| Product concept | LOCKED |
| Phase 0 API/Data feasibility | Demo OD / Route A 기준 GO; citywide not validated |
| Route A structural path | VERIFIED |
| Route B `SUBWAY_TO_BUS` structural path | VERIFIED from packaged Phase 0 Raw |
| Route B realtime ID/WAIT/Reforecast E2E | TO_VERIFY |
| Bus 01A actual evidence | CONDITIONAL; 15분 route-level transition summary, target-leg maturity 부족 |
| Subway Actual distribution | INSUFFICIENT DATA; sustained completed-arrival 추가 필요 |
| ACCESS/BUS_TO_SUBWAY/FINAL WALK exact pair | TO_VERIFY |
| Future WAIT sources | TO_VERIFY (`EVD-SCHED-001`, `EVD-WAIT-001`) |
| Probability Engine | Contract drafted; implementation not verified |
| Web App | implementation evidence 없음 |
| Distributed Proof | NOT_STARTED |
| Final deadline | 2026-09-28 |

## 2. Read Order

1. `01_DOCUMENT_CONSTITUTION.md`
2. `02_DECISION_LOG.md`
3. `03_EVIDENCE_REGISTER.md`
4. `04_SOURCE_REGISTER.md`
5. `05_GLOSSARY.md`
6. `06_TRACEABILITY_MATRIX.md`
7. `08_IMPLEMENTATION_STATUS.md`
8. `09_PHASE1_EVIDENCE_EXECUTION.md`
9. `../10_product/10_SERVICE_PLAN.md`
10. `../10_product/11_SCOPE_AND_SOURCE_POLICY.md`
11. `../10_product/12_USER_JOURNEY_AND_STATE.md`
12. `../20_requirements/20_REQUIREMENTS.md`
13. `../20_requirements/21_BUSINESS_RULES.md`
14. `../20_requirements/22_NFR.md`
15. `../30_ux/30_IA.md`
16. `../30_ux/31_SCREEN_SPEC.md`
17. `../40_data_probability/40_DATA_CONTRACT.md`
18. `../40_data_probability/41_OBSERVATION_ACTUAL_RESIDUAL.md`
19. `../40_data_probability/42_PROBABILITY_CONTRACT.md`
20. `../40_data_probability/43_VALIDATION_PLAN.md`
21. `../50_architecture/50_SYSTEM_ARCHITECTURE.md`
22. `../50_architecture/51_STREAMING_STORAGE_CONTRACT.md`
23. `../50_architecture/52_API_CONTRACT.md`
24. `../50_architecture/53_SECURITY_OPERATIONS.md`
25. `../60_delivery/60_WBS_RISK.md`
26. `../60_delivery/61_QA_ACCEPTANCE.md`
27. `../60_delivery/62_DEMO_RELEASE.md`
28. `99_PACKAGE_VALIDATION.md`

## 3. Gate Status

### D0 Documentation Foundation — PASS
- Decision/Evidence/Implementation 상태축 분리
- Phase 0 baseline archive 동봉
- Source policy / Glossary / Traceability
- v1.1 internal contradiction reconciliation
- Route A/B semantics 정리

### D1 Product Contract — PASS
- Service Plan
- Scope/Source
- Journey/State
- Route selection / WAIT source / validation claim policy

### D2 Requirement Contract — REVIEW
- Requirements/BR/NFR 작성 완료
- 팀/개발자 review 필요

### D3 UX Contract — REVIEW
- IA/Screen 작성 완료
- UI/UX 담당 review 필요

### D4 Data & Probability — REVIEW + Evidence blockers
- canonical entities/math/validation 작성
- Phase 1 Evidence 후 status 승격

### D5 Architecture & Operations — REVIEW + profiling needed
- logical contract 작성
- actual volume/server spec/benchmark 전 최종 LOCK 금지

### D6 Delivery — REVIEW + implementation tracking
- WBS/Risk/QA/Demo 작성
- 구현 진행과 함께 `08_IMPLEMENTATION_STATUS.md` 갱신

## 4. Current Evidence Blockers

### Critical for Route A Probability
1. `EVD-ACCESS-001`: demo origin→춘추문 ACCESS_WALK
2. `EVD-XFER-B2S-001`: 01A→안국 BUS_TO_SUBWAY decomposition
3. `EVD-DEST-001`: 역삼→멀티캠퍼스 FINAL_WALK
4. `EVD-TRANSFER-001`: 교대 3→2 static transfer row
5. Demo Subway `arvlCd=1` Actual sample
6. 01A target-leg/multi-window residual maturity

### Critical for Recommended Departure
7. `EVD-SCHED-001`: Subway timetable / future WAIT compatibility
8. `EVD-WAIT-001`: Bus future empirical WAIT/headway feasibility

### Critical for `SUBWAY_TO_BUS` Reliability claim
9. `EVD-CROSS-002`: Route B realtime station/route/stop/WAIT/Reforecast E2E

### Architecture evidence
10. actual raw volume/lateness/state profile

## 5. Key Final-Review Corrections

- 과거 “Route B reverse부터 탐색” 방침 제거: same-OD Phase 0 Raw에 `01A→3호선→147` SUBWAY→BUS 대안이 이미 존재.
- `EVD-CROSS-001`을 structural VERIFIED로 승격, realtime E2E는 `EVD-CROSS-002`로 분리.
- Phase 0 D-048의 `54 transition`을 target leg의 54 residual로 과장하지 않도록 수정.
- TMAP generic success와 실제 Demo ACCESS/FINAL/TRANSFER pair 검증을 분리.
- Future Recommended Departure가 exact future bus vehicle ID를 요구하지 않도록 WAIT source contract 수정.
- station center/exit/platform coordinate provenance를 정식 계약화.
- Monte Carlo Wilson interval을 simulation sampling error로만 정의; model uncertainty와 분리.
- component calibration과 whole-Journey calibration claim을 분리.
- Collector→Bronze Raw 보존을 Kafka downstream과 독립시킴.
- Phase 0 result baseline을 패키지에 포함해 Evidence path가 실제로 해석 가능하도록 수정.

## 6. Freeze Rule

`LOCKED` 문서를 바꾸려면:

`Evidence/Problem → Decision → impacted docs → Traceability → docs lint → Changelog`

순서를 따른다.
