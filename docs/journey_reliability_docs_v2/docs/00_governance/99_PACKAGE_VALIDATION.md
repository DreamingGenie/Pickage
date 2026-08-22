---
doc_id: JR-DOC-099
title: Package Validation
version: 2.1
status: LOCKED
owner: PM
last_updated: 2026-08-22
depends_on:
  - JR-DOC-000
  - JR-DOC-001
  - JR-DOC-003
  - JR-DOC-009
source_of_truth_for:
  - package-validation
supersedes: []
---

# Package Validation

## 1. Automated documentation lint

```text
Markdown files: 30
doc_ids: 30
PD: 30
EVD: 30
SRC: 14
REQ: 31
BR: 49
NFR: 30
SCR: 6
API: 9
ENT: 18
DQ: 19
ADR: 8
RISK: 21
AC: 50
TST: 10
F: 22

RESULT: PASS
```

## 2. Final semantic/package checks

`Final semantic/package checks: 23 / 23 PASS`

검사 항목:
- required canonical files / Phase 0 selected baseline 존재
- README의 canonical `09_PHASE1_EVIDENCE_EXECUTION.md` 경로
- `.env.example` secret value 비어 있음
- packaged Phase 0 Raw에서 Route A `01A→3호선→2호선` 재확인
- 같은 Raw에서 Route B `01A→3호선→147` structural `SUBWAY_TO_BUS` 재확인
- 54 route-level transition을 target-leg residual 54건으로 오인하지 않는 계약
- `EVD-CROSS-001 VERIFIED` vs `EVD-CROSS-002 TO_VERIFY` 분리
- ACCESS / BUS_TO_SUBWAY / FINAL WALK / 교대 transfer / timetable / future WAIT blocker 명시
- Recommended Departure의 time-conditioned service availability/WAIT 재평가
- future bus exact vehicle ID를 correctness prerequisite로 두지 않음
- Monte Carlo Wilson interval을 finite-N sampling error로 제한
- whole-leg Tier-0 correlation policy
- validation scope ladder
- Collector→immutable Bronze Raw와 Kafka publish 경로 분리
- 이전 package의 잘못된 validation artifact 제거

## 3. Manual reconciliation completed

- [x] Decision / Evidence / Implementation 상태축 분리
- [x] superseded Corridor B 결정 충돌 제거
- [x] TMAP을 Transit Reliability core가 아닌 external WALK utility 예외로 명시
- [x] route optimization과 selected-route Reliability scope 분리
- [x] Recommended Departure의 service-discrete semantics 정정
- [x] arbitrary Minimum Support threshold 금지 + calibration plan
- [x] WALK/static transfer unmodeled uncertainty 명시
- [x] Subway component validation과 whole-Journey calibration claim 분리
- [x] coordinate role/provenance contract 추가
- [x] API/Entity/REQ/BR/NFR/AC/TST/Feature traceability 구축
- [x] Risk/QA/Demo no-mock 정책 정리

## 4. Gate interpretation

- D0 Documentation Foundation: **PASS**
- D1 Product Contract: **PASS**
- D2 Requirements: **REVIEW**
- D3 UX: **REVIEW**
- D4 Data/Probability: **REVIEW + Evidence blockers**
- D5 Architecture/Ops: **REVIEW + profiling needed**
- D6 Delivery: **REVIEW + implementation evidence needed**

`REVIEW`는 빈 문서라는 뜻이 아니라 실제 Evidence/구현/담당자 review 전에는 LOCK하면 안 되는 계약이라는 뜻이다.

## 5. Remaining Evidence blockers

1. `EVD-CROSS-002`: same-OD Route B realtime station/route/stop/WAIT/Reforecast E2E
2. `EVD-ACCESS-001`: Demo origin→춘추문 ACCESS_WALK actual pair
3. `EVD-XFER-B2S-001`: 01A 하차→안국 3호선 BUS_TO_SUBWAY decomposition
4. `EVD-DEST-001`: 역삼 endpoint→멀티캠퍼스 역삼 FINAL_WALK actual pair
5. `EVD-TRANSFER-001`: 교대 3→2 official static row
6. `EVD-SCHED-001`: OA-22522 timetable actual ingest/ID interoperability
7. `EVD-WAIT-001`: future bus WAIT/headway support
8. Demo subway completed-arrival/Prediction→Actual maturity
9. 01A target-leg/multi-window residual maturity
10. actual volume/lateness profile

이 항목은 문서의 빈칸을 임의 숫자나 가정으로 채워 해결하지 않는다.

## 6. Manifest policy

`MANIFEST_SHA256.txt`는 모든 최종 파일이 고정된 뒤 생성하며 **manifest 자신은 목록에서 제외**한다. 따라서 self-hash 불일치가 발생하지 않는다. `scripts/validate_manifest.py`로 검증한다.
