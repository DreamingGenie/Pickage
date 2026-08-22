---
doc_id: JR-DOC-099
title: Package Validation
version: 2.2
status: LOCKED
owner: PM
last_updated: 2026-08-22
depends_on:
  - JR-DOC-000
  - JR-DOC-001
  - JR-DOC-003
  - JR-DOC-090
source_of_truth_for:
  - package-validation
supersedes: []
---

# Package Validation

## 1. Validation scope

이 문서는 Phase 1 Evidence reconciliation 이후 canonical package의 정합성을 검증한다.

검증 범위:
- canonical Markdown frontmatter / ID / reference / link
- Phase 0 baseline Raw의 Route A/B assertion
- Phase 1 report + evidence artifact 동봉 여부
- Phase 1 Evidence status와 Decision reconciliation
- Evidence feasibility와 product implementation의 분리
- Bus 54 transition / 11 traverse sample의 scope 오인 방지
- Subway station×line 분리와 quota limitation
- 교대 3→2 두 공식 source 의미 충돌과 canonical Decision
- WAIT polling snapshot의 serial dependence
- collector timestamp instrumentation 문제
- Recommended Departure / Probability Gate
- Architecture profile 과장 방지
- Phase 2 work-order 존재
- secret file/value 기본 검사

## 2. Automated documentation lint

```text
Markdown files: 31
doc_ids: 31
PD: 40
EVD: 33
SRC: 14
REQ: 31
BR: 53
NFR: 32
SCR: 6
API: 9
ENT: 18
DQ: 22
ADR: 8
RISK: 25
AC: 54
TST: 13
F: 22

RESULT: PASS
```

## 3. Final semantic/package checks

```text
Checks: 46
RESULT: PASS
```

상세 검사는 `scripts/final_package_check.py`를 실행하면 재현된다.

주요 PASS 항목:
- `EVD-CROSS-002 VERIFIED`는 Route B source interoperability claim으로만 유지되고 Reforecast 구현과 분리됨
- `EVD-ACCESS-001 VERIFIED`
- `EVD-XFER-B2S-001 CONDITIONAL`
- `EVD-DEST-001 VERIFIED`는 `STATION_CENTER` 기반임을 유지
- `EVD-TRANSFER-001 VERIFIED`; `PD-031`이 144 s를 Tier-0 reference로 선택하고 63 s는 sanity reference로 분리
- `EVD-SCHED-001 CONDITIONAL`
- `EVD-WAIT-001 VERIFIED feasibility`; 181 snapshot을 iid headway로 사용하지 않음
- `EVD-VOLUME-001 CONDITIONAL`; Phase 1의 near-zero timestamp를 실제 latency로 사용하지 않음
- `EVD-OPS-001 VERIFIED`; shared subway quota exhaustion을 운영정책에 반영
- 01A target-range 11건은 traverse-time이지 ResidualEvent가 아님
- Probability Vertical Slice는 `CONDITIONAL GO`, user-facing Recommended Departure는 `HOLD`

## 4. Gate interpretation

- D0 Documentation Foundation: **PASS**
- D1 Product Contract: **PASS**
- D2 Requirements: **REVIEW**
- D3 UX: **REVIEW**
- D4 Data/Probability: **REVIEW / CONDITIONAL GO for implementation**
- D5 Architecture/Ops: **REVIEW / profiling incomplete**
- D6 Delivery: **REVIEW / implementation tracking**

Execution gate:
- G1.5 Evidence Maturity: **CONDITIONAL PASS**
- Probability Vertical Slice: **CONDITIONAL GO**
- Recommended Departure user-facing `AVAILABLE`: **HOLD**

## 5. Remaining blockers

1. 01A target-leg `PredictionSnapshot → ActualArrivalInterval → ResidualEvent` 실측 artifact
2. Subway station×line Actual/Residual multi-window maturity, 특히 역삼 Actual 0건 보강
3. BUS_TO_SUBWAY station entrance→platform 시간 source 또는 explicit unmodeled/fallback policy 유지
4. OA-22522 current-validity 확인 또는 대체 future Subway WAIT source
5. collector timestamp instrumentation 수정 후 true latency/lateness profile
6. quota-aware subway sustained collection
7. event-based Bus WAIT/headway unit 및 dependence 검증
8. support calibration용 independent window 확대

Precision enhancement:
- 역삼역 실제 `STATION_EXIT` 기반 FINAL_WALK 재검증

## 6. Current work order

완료된 Phase 1 contract:
`09_PHASE1_EVIDENCE_EXECUTION.md` — `SUPERSEDED`

다음 Agent 작업 정본:
`10_PHASE2_EVIDENCE_EXECUTION.md` — `LOCKED`

Phase 2는 Evidence gap을 닫으면서 canonical schema / Actual / Residual / fixed-seed engine vertical slice까지만 허용한다. Web/Kafka/Flink/Spark/ML/AI로 자동 확장하지 않는다.

## 7. Manifest policy

`MANIFEST_SHA256.txt`는 최종 파일 고정 후 생성하고 manifest 자신은 목록에서 제외한다.
최종 ZIP 재추출 후 `docs_lint.py`, `final_package_check.py`, `validate_manifest.py`를 모두 다시 실행한다.
