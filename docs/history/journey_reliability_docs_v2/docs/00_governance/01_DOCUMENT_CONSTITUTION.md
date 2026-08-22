---
doc_id: JR-DOC-001
title: Document Constitution
version: 1.0
status: LOCKED
owner: PM
last_updated: 2026-08-22
depends_on: []
source_of_truth_for:
  - documentation-governance
  - status-semantics
  - id-namespace
  - change-control
supersedes:
  - DOCUMENTATION_MASTER_PLAN.md
---

# Document Constitution

## 1. 목적

모든 기획·설계·검증 문서를 Markdown 정본으로 유지하면서 누락, 중복 정의, 내부 모순, 근거 없는 확정을 방지한다.

목표는 문서의 길이가 아니라 다음 체인의 양방향 추적성이다.

`사용자 출력 → 정책 → 요구사항 → 계산 → 데이터 → API → 처리/저장 → UI → 검증 → 데모`

## 2. 한 사실 한 정본

같은 정책이나 계산식을 여러 문서에서 재정의하지 않는다.

- 제품 정책: `02_DECISION_LOG.md`, `10_SERVICE_PLAN.md`, `21_BUSINESS_RULES.md`
- 실제 데이터/API 증거: `03_EVIDENCE_REGISTER.md`
- 외부 소스: `04_SOURCE_REGISTER.md`
- 용어: `05_GLOSSARY.md`
- 확률 수학: `42_PROBABILITY_CONTRACT.md`
- 검증법: `43_VALIDATION_PLAN.md`
- 내부 API: `52_API_CONTRACT.md`
- 보안/운영: `53_SECURITY_OPERATIONS.md`

하위 문서가 상위 정책을 바꾸지 않는다.

## 3. 세 상태축 분리

### 3.1 Decision Status
`PROPOSED | FIXED | SUPERSEDED | REJECTED`

### 3.2 Evidence Status
`VERIFIED | CONDITIONAL | TO_VERIFY | FAILED | NOT_APPLICABLE`

### 3.3 Implementation Status
`NOT_STARTED | IN_PROGRESS | IMPLEMENTED | TESTED | RELEASED`

“설계되어 있음”, “구현되어 있음”, “실데이터로 검증됨”을 `지원됨`이라는 한 단어로 합치지 않는다.

## 4. Source-of-Truth

### 데이터/API 사실
1. 재현 가능한 Raw/Spike
2. 현재 공식 제공기관 문서
3. Evidence Register
4. 팀 조사문서
5. 가정

### 제품 결정
1. 최신 `FIXED` Decision
2. Service Plan
3. Requirements/UX/Architecture
4. 과거 문서

### 구현 상태
1. 현재 코드/배포
2. 테스트/CI 결과
3. Implementation status 기록
4. 계획

코드가 기획과 다르면 코드를 자동 정답으로 간주하지 않는다. `CONTRACT_MISMATCH`로 기록하고 수정 결정을 만든다.

## 5. 전역 ID

| Prefix | 의미 |
|---|---|
| PD | Product Decision |
| EVD | Evidence |
| SRC | Source |
| F | Feature |
| REQ | Functional Requirement |
| BR | Business Rule |
| NFR | Non-functional Requirement |
| SCR | Screen |
| API | Internal API |
| ENT | Entity |
| MET | Metric |
| DQ | Data Quality Rule |
| ADR | Architecture Decision |
| RISK | Risk |
| AC | Acceptance Criterion |
| TST | Test |

삭제된 ID는 재사용하지 않는다.

## 6. 변경 절차

1. 문제 발견
2. 정본 확인
3. 새 Decision 필요 여부 판단
4. `PROPOSED` Decision 추가
5. Evidence 연결
6. PM 승인/기각
7. 영향 문서 수정
8. Traceability 갱신
9. docs lint
10. Changelog

`SUPERSEDED` 기록은 삭제하지 않는다.

## 7. Anti-Hallucination 규칙

- 확인하지 않은 API field를 기억으로 추가하지 않는다.
- 근거 없는 threshold/TPS/latency/coverage를 수치화하지 않는다.
- 실제 결과와 예시 숫자를 구분한다.
- `VERIFIED`에는 Evidence ID가 필요하다.
- `TBD`에는 해결 Gate가 필요하다.
- 실제 Demo probability를 hard-code하지 않는다.
- 한 corridor 결과를 서울 전체 결과로 표현하지 않는다.

예시 숫자를 사용할 때는 반드시 `ILLUSTRATIVE ONLY`라고 표시한다.

## 8. 문서 Gate

`D0 Foundation → D1 Product → D2 Requirements → D3 UX → D4 Data/Probability → D5 Architecture/Ops → D6 Delivery`

후속 Gate 문서는 앞 Gate 정본과 충돌해서는 안 된다.
