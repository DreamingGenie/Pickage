---
doc_id: JR-DOC-008
title: Implementation Status Register
version: 1.0
status: REVIEW
owner: PM/Tech Lead
last_updated: 2026-08-22
depends_on:
  - JR-DOC-001
  - JR-DOC-020
source_of_truth_for:
  - implementation-status
supersedes: []
---

# Implementation Status Register

> 이 문서는 “설계됨”과 “구현됨”을 섞지 않기 위한 상태 정본이다.
> 현재 패키지는 기획/계약과 Phase 0 Evidence를 담고 있으며, 실제 서비스 repo의 구현상태는 Agent/팀이 확인 후 갱신한다.

## 상태값

`NOT_STARTED | IN_PROGRESS | IMPLEMENTED | TESTED | RELEASED | UNKNOWN`

## Current Baseline

| Component | Status | Evidence / Code Path | Note |
|---|---|---|---|
| Phase 0 Spike scripts | IMPLEMENTED | `baseline/phase0/scripts/spikes/` | Evidence 수집용 legacy baseline |
| Phase 0 sample archive | TESTED | `baseline/phase0/data/samples/examples/` | selected samples only; sustained raw 일부는 package에 없음 |
| Canonical schema (`ENT-*`) | NOT_STARTED | — | 계약만 존재 |
| Phase 1 Evidence collection | NOT_STARTED | — | `09_PHASE1_EVIDENCE_EXECUTION.md` 수행 대상 |
| Bus Reliability baseline | NOT_STARTED | — | target-leg/multi-window Evidence 필요 |
| Subway Reliability baseline | NOT_STARTED | — | completed Actual sample 필요 |
| Future WAIT model | NOT_STARTED | — | EVD-SCHED-001/EVD-WAIT-001 필요 |
| Journey Probability Engine | NOT_STARTED | — | D4 contract 이후 vertical slice |
| Recommended Departure | NOT_STARTED | — | WAIT source Gate 필요 |
| BUS_SKIPPED Reforecast | NOT_STARTED | — | engine/state 구현 필요 |
| Web SCR-01~06 | NOT_STARTED | — | UX contract only |
| Internal API API-001~009 | NOT_STARTED | — | API contract only |
| Kafka/Flink pipeline | NOT_STARTED | — | architecture target only |
| Spark benchmark | NOT_STARTED | — | distributed proof later |
| Security/Operations | NOT_STARTED | — | policy drafted; deploy proof 없음 |

## Update Rule

- `IMPLEMENTED`: 코드가 존재하고 basic run 가능
- `TESTED`: 관련 AC/TST가 실제 통과
- `RELEASED`: 배포 환경에서 acceptance 통과

문서 계획만으로 status를 올리지 않는다.
