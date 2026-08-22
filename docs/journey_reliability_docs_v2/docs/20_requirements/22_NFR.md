---
doc_id: JR-DOC-022
title: Non-functional Requirements
version: 1.2
status: REVIEW
owner: PM/Infra
last_updated: 2026-08-22
depends_on:
  - JR-DOC-020
source_of_truth_for:
  - non-functional-requirements
supersedes: []
---

# Non-functional Requirements

> 근거 없는 숫자를 만들지 않기 위해 threshold가 필요한 항목은 측정 Gate를 둔다.

## Performance

### NFR-001 — Interactive analysis
Journey analysis는 Web interaction에 사용할 수 있는 수준이어야 한다.

**Threshold:** `TBD-after-first-vertical-slice`  
**Resolution:** G2 Probability benchmark에서 p50/p95 측정 후 고정.

### NFR-002 — Reforecast
UserEvent 후 Reforecast는 사용자에게 “즉시 갱신” 경험을 주는 수준이어야 한다.

**Threshold:** TBD  
**Resolution:** G3 Product integration.

### NFR-003 — Monte Carlo bounded cost
온라인 simulation은 `PD-015`의 2k~5k 범위를 넘기지 않는 것을 기본으로 한다.
범위 밖이 필요하면 ADR/Decision 필요.

## Freshness

### NFR-010 — Source freshness
각 source observation은 `source_generated_at`과 `received_at`을 보유한다.

### NFR-011 — Stale state
Provider별 stale threshold는 실제 polling interval/jitter profile 이후 설정한다.

**금지:** 현재 근거 없이 “30초면 stale” 같은 전역 수치 사용.

### NFR-012 — Quota budget
실시간 지하철 collector는 공유 일일 quota를 중앙 budget으로 관리한다. poller별 독립 loop가 총 quota를 초과하지 않도록 예상 call count를 시작 전에 계산하고, `ERROR-337` 등 provider quota code를 transport success와 분리해 계측한다.

## Reliability

### NFR-020 — Raw retention for replay
실제 Raw input은 parser/logic 변경 후 replay 가능한 형태로 보존한다.

### NFR-021 — Idempotency
UserEvent와 downstream residual generation은 retry가 중복 결과를 만들지 않아야 한다.

### NFR-022 — No silent partial failure
일부 source 실패를 정상 전체결과처럼 숨기지 않는다.

## Correctness

### NFR-030 — Deterministic regression
동일 fixture + fixed seed에서 동일/허용 tolerance 내 결과를 생성해야 한다.

### NFR-031 — Optimization correctness
Spark/Flink optimization 전후 logical output equivalence를 검증한다.

### NFR-032 — Time semantics
timezone은 Asia/Seoul 기준으로 명시적으로 처리하고 naive datetime 혼용을 금지한다.

### NFR-033 — Coordinate semantics
모든 좌표는 좌표계뿐 아니라 역할을 함께 기록해야 한다.

최소 role:
`ORIGIN_POINT | BUS_STOP | STATION_CENTER | STATION_EXIT | PLATFORM_REFERENCE | POI`

`STATION_CENTER`를 `STATION_EXIT` 또는 `PLATFORM_REFERENCE`로 묵시적으로 대체하지 않는다.

### NFR-034 — Validation provenance
사용자에게 노출되는 확률/신뢰도 결과는 최소 하나의 validation scope를 가져야 한다.

`UNVALIDATED | COMPONENT_ONLY | CORRIDOR_REPLAY | END_TO_END`

component-level calibration만으로 전체 Journey probability가 calibrated되었다고 주장하지 않는다.

## Observability

### NFR-040
Collector/API/stream job에 최소:
- success/error
- last success time
- event count
- lag/latency
- state/checkpoint health

관측이 가능해야 한다.

### NFR-041
Demo 직전 health를 한 화면/명령으로 확인 가능해야 한다.

### NFR-042 — Collector timestamp instrumentation
`requested_at`은 HTTP send 직전, `received_at`은 response 수신 직후 기록해야 한다. 두 값을 response 이후 한 시점에 생성한 harness 결과는 network latency/stream watermark 근거로 사용할 수 없다.

## Security

### NFR-050
API key는 frontend bundle/Git/repository 문서에 포함하지 않는다.

### NFR-051
로그에서 secret과 민감 query parameter를 마스킹한다.

### NFR-052
모든 외부/내부 Web 통신은 배포 환경에서 HTTPS를 사용한다.

## Privacy

### NFR-060
정확한 origin 좌표를 analytics/log에 불필요하게 남기지 않는다.

### NFR-061
공유 Snapshot은 origin 정밀좌표/raw identifiers를 포함하지 않는다.

### NFR-062
Journey/share retention 기간은 Release 전 확정한다.

**Threshold:** TBD  
**Resolution:** D5 Security Gate.

## Availability / Recovery

### NFR-070
외부 provider 장애 시 사용자에게 stale/error를 명확히 표시하고 retry/fallback 규칙을 따른다.

### NFR-071
EC2/service restart 후 Raw/stream state 복구 절차가 문서화되어야 한다.

### NFR-072
최종 Demo 전에 rollback path를 검증한다.

## Responsive / Accessibility

### NFR-080
핵심 S01~S05 flow는 mobile viewport에서 horizontal overflow 없이 사용 가능해야 한다.

### NFR-081
Probability는 색만으로 상태를 구분하지 않는다.

### NFR-082
시간/확률/근거 수준은 text label을 제공한다.

## Distributed Proof

### NFR-090
실제 load 필요성 주장과 benchmark용 amplified replay를 구분한다.

### NFR-091
Spark/Flink multi-worker proof는 실제 task participation 증거를 포함한다.

### NFR-092
Benchmark는 최소 throughput/latency 또는 runtime, shuffle/state, correctness를 함께 기록한다.
