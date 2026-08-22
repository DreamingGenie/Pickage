---
doc_id: JR-DOC-060
title: WBS and Risk Register
version: 1.2
status: REVIEW
owner: PM
last_updated: 2026-08-22
depends_on:
  - JR-DOC-010
  - JR-DOC-022
  - JR-DOC-043
  - JR-DOC-050
source_of_truth_for:
  - schedule
  - team-plan
  - risk-register
  - scope-cut
supersedes: []
---

# WBS / Risk

## 1. Team

| Role | Primary responsibility |
|---|---|
| PM / Team Lead | scope, decision, requirement, probability contract review, QA, integration, final docs/demo |
| UI/UX + AI | IA/screen, evidence/confidence UX, optional evidence-grounded explanation |
| Full-stack (FE focus) | responsive Web, frontend state, API integration, share |
| BE-1 Bus | bus collector, actual/residual, bus distribution |
| BE-2 Subway/Journey | subway collector, actual/residual, crosswalk, Journey Engine |
| BE-3 Infra | EC2, Kafka/Flink/Spark, storage, CI/CD, observability, benchmark |

Journey Probability는 PM + BE-1 + BE-2가 공동 review한다.

---

# 2. Critical Path

```text
Evidence maturity
→ Canonical schema
→ Probability vertical slice
→ Web E2E
→ Streaming migration
→ Distributed proof
→ Freeze
→ Final
```

실시간 수집은 전체 기간 동안 병렬 지속.

---

# 3. Schedule

## 8/22 — Phase 1 Evidence Complete + Reconciliation

완료:
- Route B realtime source interoperability
- ACCESS/FINAL WALK point routes
- BUS_TO_SUBWAY street component
- 교대 official transfer rows
- Bus future WAIT source feasibility
- Route A station×line train join reconfirmation
- first volume profile

미완료/Conditional:
- Subway 1h target (quota로 22~33분 usable)
- 역삼 Actual 0건
- 01A target-leg residual artifact
- BUS_TO_SUBWAY station internal time
- OA-22522 current validity
- true latency/lateness

## 8/22–8/26 — Phase 2 Evidence + Canonical Schema

- collector timestamp instrumentation 수정
- quota-aware subway station×line sustained run
- 01A target-leg Prediction→Actual ResidualEvent
- Bus WAIT event-unit/headway 분석
- OA-22522 current-validity 확인
- BUS_TO_SUBWAY internal access source/fallback 조사
- `ENT-*` schema code화
- Actual/Residual parser

## 8/26–9/1 — Probability Vertical Slice

- low-support/fallback-aware LegDistribution
- fixed-seed Monte Carlo
- P50/P90/P(on_time) **UNVALIDATED/COMPONENT_ONLY** 결과
- BUS_SKIPPED state/reforecast logic
- Recommended Departure interface + unavailable path

**Gate:** mock probability가 아니라 실제 artifact를 읽되, mature/calibrated claim은 하지 않는 Route A vertical slice.

## 9/2–9/8 — UX/Product Vertical Slice

- S01~S05/06
- API contract implementation
- live Journey state
- Reforecast delta
- support/freshness/validation-scope UX
- mobile

## 9/9–9/14 — Streaming/Data Architecture

- 실제 repaired timestamp profile 반영
- Kafka/Flink
- Bronze/Silver/Gold
- replay
- observability
- failure semantics

## 9/15–9/20 — Distributed Proof

- stream 1x/5x/20x
- Flink failure/recovery
- Spark 1/2/4 worker
- 2+ optimization A/B
- correctness

## 9/21–9/24 — Integration Freeze

- no major feature
- QA
- data/evidence snapshot
- docs reconciliation
- release candidate

## 9/25–9/28 — Final

- demo preflight
- final benchmark
- report
- presentation
- rehearsal
- backup/rollback verification

---

# 4. Scope Cut Order

지연 시 먼저 제거:

1. Generative AI explanation
2. LightGBM
3. Share polish
4. Route B의 장기 probability maturity(단 smoke proof 보호)
5. 부가 분석 dashboard
6. citywide search/coverage
7. advanced live-headway transfer model

보호:

- Raw Evidence
- Bus/Subway Actual/Residual
- Route A
- Probability vertical slice
- BUS_SKIPPED Reforecast
- support honesty
- Web E2E
- distributed correctness proof

---

# 5. Risk Register

| ID | Risk | Trigger | Prob. | Impact | Owner | Prevention | Fallback / Decision |
|---|---|---|---|---|---|---|---|
| RISK-001 | Subway actual sample 부족 | Phase 1 usable window 22~33분, 역삼 Actual 0건 | H | H | BE-2 | quota-aware multi-window station×line collection | empirical claim 보류; LOW/INSUFFICIENT + fallback/limitation |
| RISK-002 | Route B source interoperability drift | Phase 1에서는 join VERIFIED지만 provider ID/schema 변경 | L/M | M | PM/BE | demo preflight + evidence fixture | source claim 재검증; product Reforecast와 분리 |
| RISK-003 | Bus 01A target-leg 표본/정의 부족 | 11 traverse samples만 있고 residual artifact 없음 | H | H | BE-1 | multi-window Prediction→Actual ResidualEvent 수집 | Bus Reliability claim 축소; LOW/INSUFFICIENT |
| RISK-004 | TMAP final WALK 실패 | provider error/quota | L/M | M | BE/Infra | subscription/quota preflight | validated cached demo pair only if policy documented; otherwise unavailable |
| RISK-005 | 교대 transfer official source 의미 차이 | OA-22521 144 s vs OA-13290 63 s | M | M | BE-2/PM | PD-031로 OA-22521 reference 고정 | 두 값 평균 금지; source semantics 문서화 |
| RISK-006 | 2호선 join anomaly 확산 | demo station에서도 join gap | L/M | H | BE-2 | continuous join metrics | scope shrink / affected station drop |
| RISK-007 | Probability calibration 실패 | holdout coverage poor | M | H | Data/PM | baseline-first validation | confidence 낮춤; product claim 축소; ML로 억지 보정 금지 |
| RISK-008 | Recommended departure subway source currentness 부족 | OA-22522 file date 2025-09-30 | H | H | BE-2/PM | latest official file/effective-date/live comparison | `AVAILABLE` HOLD; core P(on_time) near-now 유지 |
| RISK-009 | Kafka/Flink complexity가 E2E 지연 | stream work가 core blocking | M | H | Infra/PM | vertical slice first | core single-process E2E 보호 후 proof 분리 |
| RISK-010 | Flink state duplication/loss | failure test mismatch | M | H | Infra | deterministic keys/checkpoint/dedupe | demo claims 축소; recovery fix |
| RISK-011 | Spark 4 worker가 느림 | overhead > gain | M | L/M | Infra/Data | report crossover | 실패로 숨기지 않고 crossover 설명 |
| RISK-012 | External API quota | realtime subway shared key가 Phase 1에서 실제 `ERROR-337` 소진 | H | H | Infra | shared call-budget coordinator, quota increase request, backoff | lower cadence/serialized collection; key rotation 우회 금지 |
| RISK-013 | EC2 장애 | node down | L/M | H | Infra | health/backup/restore | restore/secondary service plan |
| RISK-014 | Secret leak | CI/log/repo detected | L | Critical | Infra/PM | secret scan/masking | rotate immediately, invalidate artifacts |
| RISK-015 | 문서/코드 contract drift | REQ/API/schema mismatch | M | H | PM | docs lint + contract tests | freeze, reconcile before merge |
| RISK-016 | Demo provider outage | preflight failure | M | H | PM/Infra | demo preflight + evidence snapshot | live unavailable를 정직하게 표시; fake result 금지 |
| RISK-017 | Scope expansion | 신규 source/feature 요구 | H | H | PM | change control | Scope Cut/PD 필요 |
| RISK-018 | H100 미제공 | resource unavailable | M | L | AI | core independent | AI optional drop |
| RISK-019 | Future WAIT distribution 과대 support | 20초 polling snapshots를 iid sample로 오인 | H | H | Data/PM | event-unit/headway 정의 + dependence analysis | raw snapshot n 대신 effective/event support 사용 |
| RISK-020 | Station center/exit 혼용으로 WALK/Transfer 편향 | 좌표 provenance 없음 | M | H | Data/BE | coordinate role 강제 | 해당 leg fallback/limitation, 임의 보정 금지 |
| RISK-021 | Whole-Journey calibration 근거 부족 | component metrics만 존재 | H | M/H | PM/Data | validation scope 분리 | `COMPONENT_ONLY`로 공개, calibrated claim 금지 |
| RISK-022 | Collector timestamp 계측 결함 | requested/received가 HTTP 종료 후 함께 생성 | H | H | Infra/Data | PD-037 instrumentation repair | latency/watermark/TTL 결정 HOLD |
| RISK-023 | Multi-line station 집계 오류 | 교대 rows를 line 분리 없이 join/Actual 집계 | M | H | BE-2/Data | `subwayId×statnId` key 강제 + test | 잘못된 metric 폐기/재계산 |
| RISK-024 | FINAL_WALK station-center 편향 | 실제 출구와 center 차이 | M | M | PM/Data | exit provenance 추가 검증 | 300 s를 STATION_CENTER reference로만 표시 |
| RISK-025 | BUS_TO_SUBWAY internal access 누락 | street 101 s만으로 transfer 전체를 사용 | H | H | PM/Data | official/internal source 탐색 | `UNMODELED_UNCERTAINTY`, FULL claim 금지 |

Prob.는 현재 정성 L/M/H이며 수치 risk probability가 아니다.

---

# 6. Decision Deadlines

| Topic | Deadline | If unresolved |
|---|---|---|
| Route B source interoperability | RESOLVED | EVD-CROSS-002 VERIFIED; product Reforecast는 별도 Gate |
| Final WALK point route | RESOLVED | EVD-DEST-001; STATION_CENTER limitation 유지 |
| 교대 transfer reference | RESOLVED | PD-031: OA-22521 144 s |
| Subway station×line Actual maturity | 8/29 | empirical claim 보류; Phase 2 multi-window |
| BUS_TO_SUBWAY internal access | 8/29 | PARTIAL_MODEL/UNMODELED 유지 |
| Subway timetable current validity | 9/1 | Recommended Departure `AVAILABLE` HOLD |
| Support Rule candidate | 9/3 | LOW/INSUFFICIENT conservative |
| ML promotion | 9/10 | baseline 유지 |
| Security TTL/share | 9/14 | share feature cut 가능 |
| Repaired latency/lateness profile + partition/watermark | 9/14 | benchmark-based minimal config |
| Scope freeze | 9/21 | 신규 기능 금지 |

---

# 7. Daily PM Check

- new Evidence?
- new Decision?
- blocked critical path?
- actual data collection healthy?
- document/code mismatch?
- scope change?
- demo-critical external dependency?

모든 yes는 관련 ID로 기록.
