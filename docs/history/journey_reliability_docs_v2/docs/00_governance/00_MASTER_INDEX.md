---
doc_id: JR-DOC-000
title: Master Index
version: 1.2
status: LOCKED
owner: PM
last_updated: 2026-08-22
depends_on:
  - JR-DOC-001
  - JR-DOC-002
  - JR-DOC-003
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
| Phase 1 Evidence reconciliation | **APPLIED** — `evidence/phase1/PHASE1_EVIDENCE_VALIDATION_REPORT.md` 반영 |
| Route A structural path | VERIFIED |
| Route B `SUBWAY_TO_BUS` structural path | VERIFIED from Phase 0 Raw |
| Route B realtime station/route/stop/WAIT source interoperability | **VERIFIED, corridor-scoped** (`EVD-CROSS-002`) |
| Route B `BUS_SKIPPED` Reforecast implementation | NOT_STARTED; Evidence feasibility와 product implementation을 구분 |
| Bus 01A target-leg evidence | **CONDITIONAL** — 실제 traverse 11건(100~1,223 s), Prediction→Actual residual artifact는 아직 없음 |
| Subway Route A train join | **VERIFIED for 4 station×line nodes only**; citywide 아님 |
| Subway Actual | **CONDITIONAL** — 안국 11 interval, 교대 name-search combined 6 interval, 역삼 0; quota로 usable window 22~33분 |
| ACCESS WALK | VERIFIED point route: 297 m / 245 s |
| BUS_TO_SUBWAY | **CONDITIONAL** — street 143 m / 101 s VERIFIED, station-internal access UNMODELED |
| FINAL WALK | VERIFIED point route: STATION_CENTER→POI 329 m / 300 s; exit-based 아님 |
| 교대 3→2 Transfer | 공식 row VERIFIED; Tier-0 reference **OA-22521 144 s**, OA-13290 63 s는 geometric sanity reference |
| Future Bus WAIT source | VERIFIED feasibility; serial polling snapshots는 iid sample 아님 |
| Future Subway WAIT source | CONDITIONAL — OA-22522 ingest 가능, file date 2025-09-30의 current validity 미검증 |
| Volume profile | CONDITIONAL — session 약 53 MB/h; true lateness는 baseline harness timestamp 결함으로 NOT_AVAILABLE |
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
8. `../../evidence/phase1/PHASE1_EVIDENCE_VALIDATION_REPORT.md`
9. `10_PHASE2_EVIDENCE_EXECUTION.md`
10. `../10_product/10_SERVICE_PLAN.md`
11. `../10_product/11_SCOPE_AND_SOURCE_POLICY.md`
12. `../10_product/12_USER_JOURNEY_AND_STATE.md`
13. `../20_requirements/20_REQUIREMENTS.md`
14. `../20_requirements/21_BUSINESS_RULES.md`
15. `../20_requirements/22_NFR.md`
16. `../30_ux/30_IA.md`
17. `../30_ux/31_SCREEN_SPEC.md`
18. `../40_data_probability/40_DATA_CONTRACT.md`
19. `../40_data_probability/41_OBSERVATION_ACTUAL_RESIDUAL.md`
20. `../40_data_probability/42_PROBABILITY_CONTRACT.md`
21. `../40_data_probability/43_VALIDATION_PLAN.md`
22. `../50_architecture/50_SYSTEM_ARCHITECTURE.md`
23. `../50_architecture/51_STREAMING_STORAGE_CONTRACT.md`
24. `../50_architecture/52_API_CONTRACT.md`
25. `../50_architecture/53_SECURITY_OPERATIONS.md`
26. `../60_delivery/60_WBS_RISK.md`
27. `../60_delivery/61_QA_ACCEPTANCE.md`
28. `../60_delivery/62_DEMO_RELEASE.md`
29. `99_PACKAGE_VALIDATION.md`

`09_PHASE1_EVIDENCE_EXECUTION.md`는 완료된 historical execution contract다.

## 3. Documentation Gate Status

### D0 Documentation Foundation — PASS
- Decision/Evidence/Implementation 상태축 분리
- Phase 0 baseline + Phase 1 evidence archive 동봉
- Source policy / Glossary / Traceability
- Phase 1 Freeze Rule reconciliation 완료

### D1 Product Contract — PASS
- Service Plan
- Scope/Source
- Journey/State
- Phase 1 Evidence에 맞춘 Route A/B 및 WAIT/Transfer limitation 반영

### D2 Requirement Contract — REVIEW
- Requirements/BR/NFR 작성 완료
- 팀/개발자 review 필요

### D3 UX Contract — REVIEW
- IA/Screen 작성 완료
- UI/UX 담당 review 필요

### D4 Data & Probability — REVIEW / **CONDITIONAL GO for implementation**
Phase 1에서 실제 source/ID/일부 Actual이 확보되어 canonical schema, Actual/Residual pipeline, engine logic 구현은 시작할 수 있다.
다만 mature/calibrated probability claim은 아직 금지한다.

### D5 Architecture & Operations — REVIEW + profiling incomplete
- 실제 volume 첫 profile은 생겼음
- true lateness/state-size/production cadence는 아직 부족
- partition/watermark/TTL freeze 금지

### D6 Delivery — REVIEW + implementation tracking
- WBS/Risk/QA/Demo 작성
- 구현 결과와 함께 status 갱신

## 4. Execution Gate Recommendation

### G1.5 Evidence Maturity — **CONDITIONAL PASS**
다음은 실제로 닫힘:
- Route B realtime source interoperability
- ACCESS WALK
- Final WALK point route
- 교대 official transfer rows
- Bus future WAIT source feasibility
- Route A 4 station×line train join

다음은 여전히 제한:
- BUS_TO_SUBWAY station internal access
- Subway completed-arrival maturity
- 01A Prediction→Actual residual maturity
- Subway timetable current validity
- true lateness measurement

### Probability Vertical Slice — **CONDITIONAL GO**
허용:
- canonical schema 코드화
- Bus/Subway Actual/Residual parser
- deterministic state/reforecast logic
- low-support/fallback를 명시한 engine fixture

금지:
- “calibrated Journey probability 완성” claim
- small-N을 숨긴 production-style 숫자
- stale timetable을 현재 future WAIT truth로 고정

### Recommended Departure — **HOLD for user-facing availability**
Bus WAIT feasibility는 확보했지만 Subway future WAIT source currentness가 미확정이다.
엔진 interface/`UNAVAILABLE` path는 구현 가능하나 실제 사용자 `AVAILABLE` 결과는 source Gate 후 승격한다.

## 5. Current Evidence Blockers

### Critical for Probability Evidence
1. **Bus target leg Prediction→Actual residual**: 현재 11건은 traverse-time sample이지 residual artifact가 아님.
2. **Subway station×line Actual maturity**: 교대 actual metric을 line별로 분리하고 역삼 actual을 확보해야 함; multi-window 필요.
3. **BUS_TO_SUBWAY station internal access**: source/fallback 결정 전 `UNMODELED_UNCERTAINTY` 유지.
4. **Subway future WAIT freshness**: OA-22522 2025-09-30 file의 2026-08 현재 유효성 확인 또는 대체 empirical source 필요.
5. **Support calibration**: 더 많은 independent event/window가 쌓인 뒤 수행.

### Critical for Architecture Profiling
6. Collector `requested_at`을 HTTP 전, `received_at`을 응답 직후 찍도록 instrumentation 수정.
7. provider/API별 true latency/lateness 및 state-size profile 재수집.
8. Subway 1,000 calls/day shared-budget를 준수하는 collector cadence 설계.

### Precision Enhancements, not immediate blockers
9. 역삼역 실제 `STATION_EXIT`을 고정해 FINAL_WALK 재실행.
10. 안국 entrance→platform 공식/실측 source 탐색.

## 6. Phase 1 Reconciliation Notes

- `EVD-CROSS-002`는 **realtime source interoperability/WAIT feasibility**를 VERIFIED로 승격했지만, Reforecast product code가 구현됐다는 뜻은 아니다.
- Phase 1의 01A `11 traverse samples`를 residual 11건으로 부르지 않는다.
- 181개의 `exps1` polling snapshots는 강하게 serial-correlated할 수 있으므로 181 independent headways로 취급하지 않는다.
- 교대 name-search는 2·3호선을 함께 반환한다. `subwayId`로 분리하지 않은 join/Actual 통계는 무효다.
- OA-22521 144 s와 OA-13290 63 s는 둘 다 공식값이지만 의미가 다르다. Demo Tier-0 transfer는 PD-031에 따라 144 s를 사용한다.
- Phase 1 volume profile의 `0 ms` collector latency는 harness artifact다. 실제 latency 증거가 아니다.

## 7. Freeze Rule

`LOCKED` 문서를 바꾸려면:

`Evidence/Problem → Decision → impacted docs → Traceability → docs lint → Changelog`

순서를 따른다.
