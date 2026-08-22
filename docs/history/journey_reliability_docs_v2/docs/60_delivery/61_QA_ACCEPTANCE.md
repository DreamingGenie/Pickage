---
doc_id: JR-DOC-061
title: QA and Acceptance
version: 1.2
status: REVIEW
owner: PM/QA
last_updated: 2026-08-22
depends_on:
  - JR-DOC-020
  - JR-DOC-022
  - JR-DOC-043
  - JR-DOC-053
source_of_truth_for:
  - acceptance-criteria
  - test-scenarios
supersedes: []
---

# QA / Acceptance

## A. Data

### AC-DATA-001 Bus collection
Route A 01A raw collection을 재현한다.

### AC-DATA-002 Bus join
Arrival↔Position `vehId` join metric을 재현한다.

### AC-DATA-003 Bus Actual
실제 `stopFlag 0→1` ActualArrivalInterval이 생성된다.

### AC-DATA-004 Bus Residual
복수 PredictionSnapshot과 Actual interval을 연결해 residual lower/mid/upper 생성.

### AC-DATA-005 Subway live join
Demo stations의 arrival↔position train join이 재현된다.

### AC-DATA-006 Subway Actual
실제 `arvlCd=1` 기반 ActualArrivalInterval sample이 최소 존재한다.

**주의:** “존재”는 mature distribution 충분성을 뜻하지 않는다.

### AC-DATA-007 Crosswalk
Route A 4 node mapping artifact가 versioned.

### AC-DATA-008 Final WALK
역삼역→멀티캠퍼스 역삼 TMAP raw result가 재현된다.

### AC-DATA-009 Transfer
교대 3→2 static source 또는 explicit fallback이 versioned.

### AC-DATA-010 Route B structural evidence
Phase 0 packaged Raw에서 `01A→3호선→147`의 SUBWAY→BUS 구조가 재현된다.

### AC-DATA-011 Route B realtime E2E
압구정 subway node, 147 route/stop, BUS_WAIT가 realtime source와 연결된다.

### AC-DATA-012 Source time
source_generated_at과 received_at 분리.

### AC-DATA-013 Data quality
duplicate/out-of-order/error/profile 보고서 존재.

### AC-DATA-014 Demo ACCESS_WALK
Demo origin coordinate→춘추문 bus stop의 TMAP point route/time과 coordinate roles가 저장된다.

### AC-DATA-015 BUS_TO_SUBWAY transfer
01A 안국 하차정류장→안국 boarding point의 street/internal component source 또는 explicit fallback/limitation이 존재한다.

### AC-DATA-016 Future WAIT source
- Subway timetable 또는 empirical headway source가 Demo station IDs와 연결되거나 unavailable 판정
- Bus future empirical wait/headway feasibility가 측정됨

### AC-DATA-017 Bus target-leg ResidualEvent
01A target leg/target stop에 대해 실제 PredictionSnapshot↔ActualArrivalInterval 매칭으로 residual lower/mid/upper가 생성된다. Traverse-time sample만으로 대체하지 않는다.

### AC-DATA-018 Subway multi-line isolation
교대 등 multi-line station metric이 `subwayId × statnId`로 분리되며 line-mixed join/Actual 집계가 없다.

### AC-DATA-019 Collector timing validity
`requested_at`/`received_at`이 실제 HTTP boundary에서 캡처되고 Phase 0/1 near-zero harness artifact가 새 latency profile에 섞이지 않는다.

### AC-DATA-020 Quota accounting
HTTP 200 quota payload가 success로 숨겨지지 않고 provider quota error로 별도 계측되며 planned call budget이 일일 한도를 넘지 않는다.

---

## B. Probability

### AC-PROB-001 LegDistribution
모든 future leg가 distribution/reference + fallback metadata를 가진다.

### AC-PROB-002 No fake uncertainty
WALK/static transfer의 unmodeled uncertainty가 limitation에 존재.

### AC-PROB-003 Monte Carlo
2k~5k 범위 simulation이 final arrival distribution을 생성.

### AC-PROB-004 P50/P90
실제 run result로 생성.

### AC-PROB-005 On-time
target 이전 arrival 비율 계산.

### AC-PROB-006 Connection separation
planned success와 final on-time 별도.

### AC-PROB-007 Recommended departure
selected-route conditional service re-evaluation을 사용.

### AC-PROB-008 BUS_SKIPPED
completed history 고정 + skipped branch 제거 + next bus reforecast.

### AC-PROB-009 Reproducibility
fixed fixture/seed regression.

### AC-PROB-010 Validation
hold-out/rolling validation artifact 존재.

### AC-PROB-011 Validation scope honesty
component-only 검증이면 JourneyResult가 `COMPONENT_ONLY`이며 `END_TO_END calibrated` claim이 없다.

### AC-PROB-012 Monte Carlo error distinction
simulation finite-N error와 model/data uncertainty가 별도 metadata/문서로 구분된다.

---

## C. Product

### AC-PROD-001 Input→Result
SCR-01→SCR-02 E2E.

### AC-PROD-002 Journey Start
SCR-02→SCR-03.

### AC-PROD-003 Reforecast
BUS_SKIPPED→SCR-04.

### AC-PROD-004 Evidence
support/fallback/freshness 확인 가능.

### AC-PROD-005 Error
provider error/stale/unsupported/no-data 화면.

### AC-PROD-006 Mobile
핵심 flow mobile viewport horizontal overflow 0.

### AC-PROD-007 No mock
runtime user result에 hard-coded probability 없음.

### AC-PROD-008 Share
feature 유지 시 privacy contract 통과.

---

## D. Security/Ops

### AC-SEC-001
repo secret scan critical 0.

### AC-SEC-002
frontend bundle key 0.

### AC-SEC-003
log key masking.

### AC-SEC-004
HTTPS deployed route.

### AC-SEC-005
backup/restore smoke.

### AC-SEC-006
rollback procedure.

---

## E. Distributed

### AC-DIST-001 Stream benchmark
1x/5x/20x replay 결과.

### AC-DIST-002 Worker participation
실제 multi-worker task evidence.

### AC-DIST-003 Flink failure
TaskManager failure→recovery.

### AC-DIST-004 Lost/Duplicate
logical event/result 비교.

### AC-DIST-005 Spark scale
1/2/4 worker runtime.

### AC-DIST-006 Shuffle
actual shuffle/spill/skew metric.

### AC-DIST-007 Optimization
최소 2 A/B.

### AC-DIST-008 Correctness
optimization 전후 count/checksum/statistical result tolerance.

---

# Test Scenarios

## TST-E2E-001 Pre-trip
Given Route A valid input  
When analyze  
Then real result + support metadata.

## TST-E2E-002 BUS_SKIPPED
Given BUS_WAIT with candidate  
When skip  
Then probability version increments and skipped candidate removed.

## TST-E2E-003 Low Support
Given sparse distribution  
Then fallback/low-support visible.

## TST-E2E-004 Provider Error
Given realtime provider unavailable  
Then no fake fresh result.

## TST-E2E-005 Unsupported
Given out-of-scope route  
Then probability absent.

## TST-E2E-006 SUBWAY_TO_BUS
Given packaged Phase 0 Route B (`01A→3호선→147`) and completed realtime mappings  
Then canonical sequence contains `SUBWAY_RIDE → TRANSFER_SUBWAY_TO_BUS → BUS_WAIT → BUS_RIDE`.

## TST-DATA-001 Duplicate
Duplicate raw/canonical event does not emit duplicate residual.

## TST-DATA-002 Out of Order
Late event follows documented state/watermark behavior.

## TST-PROB-001 BUS_SKIPPED invariant
Given completed legs and a current bus candidate  
When `BUS_SKIPPED` occurs  
Then completed durations stay fixed, skipped candidate is removed, next WAIT begins at/after event time, and result version increments.

## TST-PROB-005 Departure Candidate Change
Different departure candidates re-evaluate time-conditioned WAIT/service availability where the fixture requires it; the engine must not implement this as a simple distribution time-shift.

## TST-PROB-002 Repeat Event Idempotency
Given the same UserEvent `idempotencyKey` twice  
Then Journey state/result changes only once.

## TST-PROB-003 Connection Recovery
Given a planned connection miss  
When a next feasible service exists  
Then simulation can continue and final on-time is computed independently of planned-success.

## TST-PROB-004 Future WAIT source
Given a future departure candidate  
Then bus/subway WAIT source is `TIMETABLE` or `EMPIRICAL_HEADWAY` (or result is unavailable), not an invented future vehicle ID.

## TST-DATA-003 Coordinate provenance
Given a WALK/Transfer leg  
Then both endpoints carry coordinate role/source and station-center→exit coercion does not occur silently.

## TST-DATA-004 Multi-line Station Isolation
Given 교대 arrival payload containing Line 2 and Line 3 rows  
When join/Actual metrics are computed  
Then rows are split by `subwayId × statnId` and each line metric is calculated independently.

## TST-DATA-005 Collector Timestamp Boundary
Given a live HTTP collector call  
Then `requested_at < received_at` reflects actual request boundary capture and is not assigned only after response construction.

## TST-DATA-006 Bus WAIT Sample Unit
Given consecutive 20-second `exps1` snapshots for the same vehicle  
Then they are not counted as independent headway events; event/headway unit is explicit.

## TST-DIST-001 Flink Kill
Kill worker, record recovery/loss/duplicate.

## TST-DIST-002 Spark Worker Matrix
1/2/4 worker actual task participation.

---

# Release Blocking

Critical block:
- AC-DATA-003/004/017
- AC-DATA-006/018 or explicit subway fallback claim downgrade approved
- AC-DATA-014/015 for Route A time-boundary integrity
- AC-DATA-016 or Recommended Departure unavailable policy
- AC-DATA-019/020 before architecture latency/quota decisions
- AC-PROB-003~008
- AC-PROD-001~007
- AC-SEC-001/002
- AC-DIST core set agreed by PM

Route B realtime E2E failure does not automatically kill Route A core product, but `SUBWAY_TO_BUS Reliability E2E VERIFIED` claim must be removed or scope-downgraded by PM Decision.
