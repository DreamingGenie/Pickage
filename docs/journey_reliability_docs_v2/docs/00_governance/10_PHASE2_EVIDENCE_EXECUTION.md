---
doc_id: JR-DOC-090
title: Phase 2 Evidence and Vertical Slice Execution Contract
version: 1.0
status: LOCKED
owner: PM/Data
last_updated: 2026-08-22
depends_on:
  - JR-DOC-000
  - JR-DOC-002
  - JR-DOC-003
  - JR-DOC-041
  - JR-DOC-042
  - JR-DOC-043
source_of_truth_for:
  - phase2-evidence-work-order
  - probability-vertical-slice-entry
supersedes:
  - JR-DOC-009
---

# Phase 2 Evidence + Probability Vertical Slice Execution Contract

## 1. 목적

Phase 1에서 source/ID/일부 Actual feasibility는 크게 닫혔다.
Phase 2는 **남은 measurement gap을 실제 데이터로 닫으면서**, 동시에 canonical schema와 Actual/Residual/engine logic의 vertical slice를 구현하는 단계다.

전체 Web/Kafka/Flink/Spark로 자동 확장하지 않는다.

## 2. 가장 먼저 읽을 것

1. `00_MASTER_INDEX.md`
2. `02_DECISION_LOG.md`의 PD-031~PD-040
3. `03_EVIDENCE_REGISTER.md`
4. `../../evidence/phase1/PHASE1_EVIDENCE_VALIDATION_REPORT.md`
5. `../40_data_probability/40_DATA_CONTRACT.md`
6. `../40_data_probability/41_OBSERVATION_ACTUAL_RESIDUAL.md`
7. `../40_data_probability/42_PROBABILITY_CONTRACT.md`
8. `../40_data_probability/43_VALIDATION_PLAN.md`
9. `../60_delivery/61_QA_ACCEPTANCE.md`

## 3. 허용되는 구현

- `ENT-*` canonical DTO/JSON Schema/Pydantic 등 1개 정본 구현
- Raw→Observation parser
- Bus/Subway ActualArrivalInterval
- Prediction→Actual ResidualEvent
- fixed-seed Journey Engine logic fixture
- BUS_SKIPPED state transition/reforecast logic fixture
- evidence/metrics analysis scripts

## 4. 아직 금지

- calibrated Journey probability 완성 claim
- Web App 전체 구현
- Kafka/Flink/Spark 전체 구축
- LightGBM/AI
- citywide 일반화
- arbitrary support threshold
- stale OA-22522를 current truth로 사용
- 181 polling snapshots를 181 independent bus headways로 사용

## 5. EV2-01 — Collector Timestamp Repair

Phase 0/1 harness는 `requested_at`/`received_at`을 HTTP 종료 후 거의 동시에 기록해 실제 network latency를 잃었다.

수정:
- `requested_at`: HTTP send 직전
- `received_at`: response bytes 수신 직후
- provider row time은 별도 `source_generated_at`

실험:
- bus Arrival/Position
- subway Arrival/Position
- 최소 짧은 smoke window

산출:
- request round-trip latency p50/p95/p99
- `received_at - source_generated_at`은 source time 의미가 맞는 API에서만 계산
- bus Arrival `mkTm`, Position `dataTm`, subway `recptnDt`를 같은 의미로 강제하지 않음

현재 `0 ms` Phase 1 값은 절대 baseline으로 사용하지 않는다.

## 6. EV2-02 — Quota-aware Subway Sustained Collection

목표:
Route A 4 station×line을 line별로 분리해 Actual evidence를 늘린다.

필수 rule:
- 교대 name-search rows를 `subwayId`로 분리
- same key 총 call budget 사전 계산
- quota 회피용 key rotation 금지

권장 cadence 설계 예시는 **예시일 뿐 고정값 아님**:
- arrival poll을 position보다 자주
- position은 join validation에 필요한 수준으로 낮은 cadence
- 총 1,000/day 이하 + smoke/retry headroom 확보

반드시 산출:
- 안국3 / 교대3 / 교대2 / 역삼2 별
  - success/quota/error
  - distinct trains
  - join numerator/denominator
  - `arvlCd=1` sightings
  - ActualArrivalInterval count/width
  - Prediction→Actual match count
- multiple windows 가능하면 window별 분리

역삼 0건을 임의 보간하지 않는다.

## 7. EV2-03 — Bus 01A Target-leg Prediction→Actual Residual

Phase 1의 11건 traverse duration은 residual이 아니다.

목표:
춘추문→안국 또는 destination stop Actual에 대해 실제 Arrival prediction snapshots를 `vehId`로 매칭해:

```text
PredictionSnapshot
→ ActualArrivalInterval
→ ResidualEvent(lower/mid/upper)
```

를 생성한다.

반드시:
- lead time 보존
- same vehicle 여러 snapshot 허용
- 한 Actual event의 snapshots가 validation split 양쪽으로 leakage되지 않게 group id 기록
- 최소 두 시간대/window를 목표로 하되, sample count를 maturity threshold로 임의 고정하지 않음

## 8. EV2-04 — Bus WAIT Event Semantics

Phase 1 `exps1` 181개는 20초 반복 snapshot이다.

목표:
- distinct `vehId1` turnover
- 실제 stop arrival/Actual event
- headway between vehicle events

를 중심으로 independent-ish event unit을 만든다.

분석:
- raw snapshot series의 autocorrelation/dependence를 확인
- event-based headway distribution과 snapshot wait distribution을 분리
- PRE_TRIP에서 어느 것을 사용할지 Validation Plan에 제안

## 9. EV2-05 — Subway Timetable Current-validity

OA-22522 parsing feasibility는 확보됐다.
현재 blocker는 2025-09-30 snapshot이 2026-08 현재 유효한지 여부다.

확인 우선순위:
1. 동일 공식 source의 더 최신 파일/공지 존재 여부
2. 현재 공개 timetable effective date 확인
3. 불가하면 제한된 live window에서 scheduled time vs realtime sequence 비교

결과가 불충분하면 `EVD-SCHED-001 CONDITIONAL` 유지하고 Recommended Departure `AVAILABLE`을 열지 않는다.

추가 parser rule:
- line별 direction vocabulary (`UP/DOWN`, `IN/OUT`)
- `>=24:00:00` rollover
- `SI_ID`→realtime `statnId` 산술 추정 금지

## 10. EV2-06 — BUS_TO_SUBWAY Internal Access

현재 street 143 m / 101 s는 VERIFIED지만 station entrance→platform이 없다.

공식 서울 source 또는 재현 가능한 fixed/reference source를 우선 탐색한다.
없으면:
- `UNMODELED_UNCERTAINTY` 유지
- 임의 60/90/120 s fallback 생성 금지

이 blocker는 Probability engine logic 구현 자체를 막지 않지만 FULL model claim을 막는다.

## 11. EV2-07 — FINAL_WALK Exit Precision (Should)

현재 329 m / 300 s는 STATION_CENTER-based reference다.
실제 역삼역 exit source가 명확히 검증되면 가장 적합한 exit→멀티캠퍼스 TMAP을 새 Evidence로 만든다.

검증 전 기존 300 s를 exit-based로 relabel하지 않는다.

## 12. Vertical Slice Implementation Gate

EV2와 병렬로 다음을 구현할 수 있다.

```text
Raw fixture/live sample
→ canonical Observation
→ ActualArrivalInterval
→ ResidualEvent
→ low-support LegDistribution artifact
→ deterministic/fixed-seed Journey simulation
→ BUS_SKIPPED state reforecast
```

초기 결과는:
- `validation_scope=UNVALIDATED` 또는 `COMPONENT_ONLY`
- `confidence=LOW/INSUFFICIENT`
- unmodeled WALK/transfer limitation

을 허용해야 한다.

## 13. 종료 산출물

repo root:
- `PHASE2_EVIDENCE_AND_VERTICAL_SLICE_REPORT.md`
- `evidence/phase2/`

보고서 최소 목차:
1. Executive Summary
2. Phase 1 blockers addressed
3. Collector timestamp result
4. Subway station×line Actual metrics
5. Bus target-leg ResidualEvent metrics
6. Bus WAIT event-unit analysis
7. Subway timetable freshness
8. Transfer/final-walk precision updates
9. Canonical schema implementation status
10. Probability vertical-slice implementation status
11. Contract conflicts
12. Proposed Evidence/Decision updates
13. Gate recommendation
14. What still must not be claimed

완료 후 Web/Kafka/Flink/Spark로 자동 진행하지 않는다.
