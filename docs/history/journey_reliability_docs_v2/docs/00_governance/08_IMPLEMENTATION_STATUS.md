---
doc_id: JR-DOC-008
title: Implementation Status Register
version: 1.1
status: REVIEW
owner: PM/Tech Lead
last_updated: 2026-08-22
depends_on:
  - JR-DOC-001
  - JR-DOC-020
  - JR-DOC-003
source_of_truth_for:
  - implementation-status
supersedes: []
---

# Implementation Status Register

> Evidence feasibility와 product implementation을 분리한다.

## 상태값

`NOT_STARTED | IN_PROGRESS | IMPLEMENTED | TESTED | RELEASED | UNKNOWN`

## Current Baseline

| Component | Status | Evidence / Code Path | Note |
|---|---|---|---|
| Phase 0 Spike scripts | IMPLEMENTED | `baseline/phase0/scripts/spikes/` | historical evidence harness |
| Phase 1 Evidence collection | **TESTED** | `evidence/phase1/PHASE1_EVIDENCE_VALIDATION_REPORT.md` | 10 evidence work-items 실행; 일부 CONDITIONAL |
| Route B realtime source interoperability | **TESTED** | `evidence/phase1/EVD-CROSS-002/`, `EVD-WAIT-001/` | source/ID/WAIT feasibility; Reforecast product code 아님 |
| Demo WALK point routes | **TESTED** | `EVD-ACCESS-001/`, `EVD-XFER-B2S-001/`, `EVD-DEST-001/` | BUS→SUBWAY internal access는 미측정 |
| Canonical schema (`ENT-*`) | NOT_STARTED | — | 계약만 존재; Phase 2부터 code화 가능 |
| Bus Actual/Residual pipeline | NOT_STARTED | — | Actual concept evidence는 있으나 target-leg residual artifact 미생성 |
| Bus Reliability baseline | NOT_STARTED | — | `EVD-BUS-010` low-support traverse sample + multi-window residual 필요 |
| Subway Actual/Residual pipeline | NOT_STARTED | — | 실제 Actual interval은 존재, line-specific maturity/Residual 미완료 |
| Future Bus WAIT model | NOT_STARTED | `EVD-WAIT-001` source feasibility TESTED | event-based/dependence-aware distribution 구현 필요 |
| Future Subway WAIT model | NOT_STARTED | `EVD-SCHED-001 CONDITIONAL` | current timetable validity Gate |
| Journey Probability Engine | NOT_STARTED | — | `PD-040`에 따라 CONDITIONAL GO for implementation |
| Recommended Departure | NOT_STARTED | — | interface/unavailable path 가능; user-facing AVAILABLE은 HOLD |
| BUS_SKIPPED Reforecast | NOT_STARTED | — | source feasibility ≠ engine implementation |
| Web SCR-01~06 | NOT_STARTED | — | UX contract only |
| Internal API API-001~009 | NOT_STARTED | — | API contract only |
| Kafka/Flink pipeline | NOT_STARTED | — | architecture target only |
| Spark benchmark | NOT_STARTED | — | distributed proof later |
| Security/Operations | NOT_STARTED | — | policy drafted; deploy proof 없음 |

## Update Rule

- `IMPLEMENTED`: 코드가 존재하고 basic run 가능
- `TESTED`: 관련 AC/TST가 실제 통과
- `RELEASED`: 배포 환경에서 acceptance 통과

문서 계획 또는 Evidence feasibility만으로 product component status를 올리지 않는다.
