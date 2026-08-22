---
doc_id: JR-DOC-009
title: Phase 1 Evidence Execution Contract
version: 1.0
status: LOCKED
owner: PM/Data
last_updated: 2026-08-22
depends_on:
  - JR-DOC-002
  - JR-DOC-003
  - JR-DOC-004
  - JR-DOC-041
  - JR-DOC-042
  - JR-DOC-043
source_of_truth_for:
  - phase1-evidence-work-order
supersedes: []
---

# Phase 1 Evidence Execution Contract

## 1. Agent에게 줄 가장 짧은 지시

VS Code Agent가 이 package와 기존 repo를 볼 수 있다면 아래 한 문장으로 시작한다.

```text
먼저 journey_reliability_docs_v2/docs/00_governance/00_MASTER_INDEX.md와
journey_reliability_docs_v2/docs/00_governance/09_PHASE1_EVIDENCE_EXECUTION.md를 읽고,
정본 문서는 임의 수정하지 않은 채 Phase 1 Evidence 검증만 수행해.
끝나면 repo root에 PHASE1_EVIDENCE_VALIDATION_REPORT.md와 evidence/phase1/를 만들고 멈춰.
```

`transit_journey_handoff_FINAL_v3/`가 repo에 있으면 원본 PDF/과거 handoff 참고용으로만 사용한다.
이번 package의 `baseline/phase0/`가 **실제 result.zip에서 가져온 Phase 0 실행 baseline**이다.

## 2. 금지

- 전체 Web App/Backend 구현
- Kafka/Flink/Spark 구축
- LightGBM/AI 구현
- 정본 `LOCKED` 문서 직접 수정
- secret 출력/commit
- 임의 probability/support/variance 생성
- citywide 일반화
- Phase 0 summary만 보고 Raw와 다른 사실 생성

## 3. Evidence 우선순위

### EV-01 — `EVD-CROSS-002` Route B realtime E2E

새 reverse OD 탐색부터 하지 않는다.

먼저 packaged Phase 0 Raw:
`baseline/phase0/data/samples/examples/seoul_bus/demo_corridor_samcheong_yeoksam/160402_b6021bab94ac.json`

의 실제 대안:

```text
01A 춘추문→안국역6번출구
→ 3호선 안국→압구정
→ 147 압구정역4번출구→역삼역6번출구
```

를 사용한다.

검증:
- 압구정 mixed code `03260` ↔ realtime station ID
- bus `147 routeId=100100026` ↔ realtime route
- 압구정역4번출구 stop ID/coordinate ↔ realtime bus source
- `TRANSFER_SUBWAY_TO_BUS`
- `BUS_WAIT`
- `BUS_SKIPPED`를 넣을 수 있는 next-service state

구조적 route 존재는 이미 `EVD-CROSS-001 VERIFIED`; 이번 목표는 E2E interoperability다.

### EV-02 — `EVD-ACCESS-001` Demo ACCESS_WALK

Demo origin coordinate:
`126.9809, 37.5825`

Route A first boarding stop:
- 춘추문
- mixed stop ID `100000417`
- route raw coordinate `126.97965309715137, 37.58308213227146`

TMAP 실제 호출로 point route/time을 저장.
좌표 role/source 기록.

### EV-03 — `EVD-XFER-B2S-001` 01A→안국 BUS_TO_SUBWAY

Actual route nodes:
- bus alight: `안국역6번출구.인사동문화의거리`, ID `100000104`, route raw coord `126.98412712121268,37.57575695248874`
- subway mixed node: 안국 3호선 `03180`, route raw station coord `126.98546292770595,37.57648700828617`

목표는 **TMAP 한번 호출로 전체 platform transfer가 검증됐다고 만들지 않는 것**이다.

반드시 구분:
1. street/exit까지 계산 가능한 part
2. station internal entrance→platform part

정확한 exit/platform coordinate source가 없으면 `UNMODELED_UNCERTAINTY` 또는 fixed fallback candidate로 보고.

### EV-04 — `EVD-DEST-001` FINAL_WALK

역삼 2호선 endpoint→멀티캠퍼스 역삼(서울 강남구 테헤란로 212).

반드시 기록:
- start coordinate의 role (`STATION_CENTER`인지 exit인지)
- coordinate source
- end POI coordinate source
- TMAP totalDistance/totalTime
- sanitized raw/hash

exit가 확인되지 않으면 station-center result임을 숨기지 않는다.

### EV-05 — `EVD-TRANSFER-001` 교대 3→2

OA-22521 / OA-13290에서 실제 row 확인.

기록:
- 실제 column
- from/to line
- time/distance
- 하차/승차 위치 있으면 해당 값
- file/version/date

row가 없으면 숫자를 만들지 않는다.

### EV-06 — `EVD-SCHED-001` Subway future WAIT

OA-22522 timetable을 실제 ingest해:
- 안국3 / 교대3 / 교대2 / 역삼2 station identity 연결
- DAY/SAT/END
- direction
- arrival/departure time
- 24시 초과 표현 parsing

을 확인한다.

목표: Recommended Departure에서 future subway WAIT source로 사용할 수 있는지 판정.

### EV-07 — `EVD-WAIT-001` Bus future WAIT/headway

01A와 가능하면 Route B 147에 대해 realtime position/arrival 연속 관측에서 time-conditioned headway/wait sample을 만들 수 있는지 검증.

미래 특정 bus vehicle ID를 예측하려 하지 않는다.

결과:
- headway sample count
- window/time bucket
- candidate wait distribution feasibility
- limitation

### EV-08 — Subway sustained collection

Route A:
- 안국3
- 교대3
- 교대2
- 역삼2

최소 1시간 목표, quota 확인 후 실행.

필수 metrics:
- polls/success/error/empty
- duplicate/out-of-order
- arrival/position counts
- train join numerator/denominator/rate
- `arvlCd` counts
- `arvlCd=1` count
- ActualArrivalInterval count
- interval width min/p50/p90/max
- Prediction→Actual match count

### EV-09 — Bus 01A target-leg + extended collection

Phase 0의 54 transition은 route-level multi-stop count임을 기억한다.

이번에는:
- 춘추문→안국 target leg residual
- longer / different-time windows

을 구분해 계산.

필수:
- old/new/combined support
- vehId join
- transition
- target-leg actual/residual
- interval width
- congestion/isFullFlag
- duplicate/out-of-order/error

### EV-10 — Volume/Lateness

실제 새 수집 결과로:
- raw bytes/hour
- compressed bytes/hour 가능하면
- observations/hour
- normalized events/hour
- active keys
- actual/residual events/hour
- `received_at-source_generated_at` p50/p95/p99/max
- negative lateness/out-of-order

이번 round에서는 partition/watermark/TTL을 확정하지 않는다.

## 4. 저장 구조

```text
evidence/phase1/
├─ EVD-CROSS-002/
├─ EVD-ACCESS-001/
├─ EVD-XFER-B2S-001/
├─ EVD-DEST-001/
├─ EVD-TRANSFER-001/
├─ EVD-SCHED-001/
├─ EVD-WAIT-001/
├─ SUBWAY_SUSTAINED/
├─ BUS_01A_EXTENDED/
└─ VOLUME_LATENESS/
```

각 폴더:
- `README.md`
- sanitized `raw/`
- `derived/`
- `metrics.json`
- `reproduction.md`
- secret-free log 가능

## 5. 최종 보고서

repo root:
`PHASE1_EVIDENCE_VALIDATION_REPORT.md`

필수 목차:
1. Executive Summary
2. Execution Environment
3. Evidence Status Summary
4. Route B realtime E2E
5. ACCESS_WALK
6. BUS_TO_SUBWAY Transfer
7. FINAL_WALK
8. 교대 3→2 Transfer
9. Subway timetable / future WAIT
10. Bus future WAIT/headway
11. Subway Sustained Collection
12. Bus 01A Target-leg/Extended Collection
13. Volume/Lateness Profile
14. Contract Conflicts Found
15. Proposed Evidence Register Updates
16. Proposed Decision Changes
17. Documents Impacted
18. Remaining Blockers
19. Gate Recommendation
20. What Must NOT Be Built Yet

각 Evidence는 `VERIFIED | CONDITIONAL | FAILED | TO_VERIFY` + scope/support/artifact/limitation을 가진다.

## 6. 종료

보고서를 만들면 멈춘다.
Probability/Web/Distributed 구현으로 자동 진행하지 않는다.
