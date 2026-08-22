---
doc_id: JR-DOC-060
title: WBS and Risk Register
version: 1.1
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

## 8/22–8/25 — D0/D1 + Evidence Maturity

문서:
- governance
- Service Plan
- Scope/Source
- User Journey

실험:
- Route B `SUBWAY_TO_BUS` realtime E2E (`EVD-CROSS-002`)
- Subway 1h+
- Bus 01A target-leg + multi-window
- Demo ACCESS_WALK (`EVD-ACCESS-001`)
- 01A→안국 BUS_TO_SUBWAY transfer (`EVD-XFER-B2S-001`)
- Final WALK (`EVD-DEST-001`)
- 교대 transfer row (`EVD-TRANSFER-001`)
- OA-22522 future subway WAIT (`EVD-SCHED-001`)
- Bus empirical future WAIT/headway (`EVD-WAIT-001`)

완료 증거:
- EVD-CROSS-002
- EVD-ACCESS-001
- EVD-XFER-B2S-001
- EVD-DEST-001
- EVD-TRANSFER-001
- EVD-SCHED-001 / EVD-WAIT-001
- subway actual sample

## 8/26–8/29 — D2/D4 Contract Freeze

- Requirements/BR/NFR review
- canonical schema
- actual/residual parser
- support profile
- validation fixture

## 8/30–9/3 — Probability Vertical Slice

- Bus distribution
- Subway empirical/fallback
- WALK/static limitation
- Monte Carlo
- P50/P90/P(on-time)
- recommended departure
- BUS_SKIPPED

**Gate:** mock probability 없이 Route A result 1개.

## 9/4–9/8 — UX/Product Vertical Slice

- S01~S05/06
- API contract implementation
- live Journey state
- Reforecast delta
- support/freshness UX
- mobile

## 9/9–9/14 — Streaming/Data Architecture

- Kafka
- Flink state matching
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
| RISK-001 | Subway actual sample 부족 | 1h+에도 usable actual/residual 부족 | M | H | BE-2 | sustained multi-window collection | broader/fixed fallback + limitation; empirical claim 금지 |
| RISK-002 | Route B realtime ID/stop 연결 실패 | 기존 Raw structural path는 있으나 station/route/stop join 불가 | M | M/H | PM/BE | 같은 OD 01A→3호선→147을 먼저 검증 | cross-mode claim 축소; 새 OD는 PM 승인 후 1개만 |
| RISK-003 | Bus 01A 표본 편향 | single time window dominance | H | M | BE-1 | 다른 시간대 수집 | LOW confidence + broader fallback |
| RISK-004 | TMAP final WALK 실패 | provider error/quota | L/M | M | BE/Infra | subscription/quota preflight | validated cached demo pair only if policy documented; otherwise unavailable |
| RISK-005 | 교대 transfer static row 불일치/부재 | source row 없음 | M | M | BE-2/PM | OA-22521/13290 둘 다 check | explicit fixed fallback + unmodeled uncertainty |
| RISK-006 | 2호선 join anomaly 확산 | demo station에서도 join gap | L/M | H | BE-2 | continuous join metrics | scope shrink / affected station drop |
| RISK-007 | Probability calibration 실패 | holdout coverage poor | M | H | Data/PM | baseline-first validation | confidence 낮춤; product claim 축소; ML로 억지 보정 금지 |
| RISK-008 | Recommended departure source 부족 | future WAIT/service-availability source 부족 | M | H | BE-2/PM | timetable/support source Spike | feature unavailable state; P(on-time) core 유지 |
| RISK-009 | Kafka/Flink complexity가 E2E 지연 | stream work가 core blocking | M | H | Infra/PM | vertical slice first | core single-process E2E 보호 후 proof 분리 |
| RISK-010 | Flink state duplication/loss | failure test mismatch | M | H | Infra | deterministic keys/checkpoint/dedupe | demo claims 축소; recovery fix |
| RISK-011 | Spark 4 worker가 느림 | overhead > gain | M | L/M | Infra/Data | report crossover | 실패로 숨기지 않고 crossover 설명 |
| RISK-012 | External API quota | 429/limit near demo | M | H | Infra | call budget/backoff/cache | collection window 조정, pre-collected evidence, live claim 제한 |
| RISK-013 | EC2 장애 | node down | L/M | H | Infra | health/backup/restore | restore/secondary service plan |
| RISK-014 | Secret leak | CI/log/repo detected | L | Critical | Infra/PM | secret scan/masking | rotate immediately, invalidate artifacts |
| RISK-015 | 문서/코드 contract drift | REQ/API/schema mismatch | M | H | PM | docs lint + contract tests | freeze, reconcile before merge |
| RISK-016 | Demo provider outage | preflight failure | M | H | PM/Infra | demo preflight + evidence snapshot | live unavailable를 정직하게 표시; fake result 금지 |
| RISK-017 | Scope expansion | 신규 source/feature 요구 | H | H | PM | change control | Scope Cut/PD 필요 |
| RISK-018 | H100 미제공 | resource unavailable | M | L | AI | core independent | AI optional drop |
| RISK-019 | Future WAIT source 부족 | timetable/headway ID/data 부족 | M | H | Data/PM | OA-22522 + empirical bus headway 검증 | Recommended Departure unavailable, core P(on-time) near-now 유지 |
| RISK-020 | Station center/exit 혼용으로 WALK/Transfer 편향 | 좌표 provenance 없음 | M | H | Data/BE | coordinate role 강제 | 해당 leg fallback/limitation, 임의 보정 금지 |
| RISK-021 | Whole-Journey calibration 근거 부족 | component metrics만 존재 | H | M/H | PM/Data | validation scope 분리 | `COMPONENT_ONLY`로 공개, calibrated claim 금지 |

Prob.는 현재 정성 L/M/H이며 수치 risk probability가 아니다.

---

# 6. Decision Deadlines

| Topic | Deadline | If unresolved |
|---|---|---|
| Route B realtime E2E | 8/25 | `SUBWAY_TO_BUS` claim CONDITIONAL/제거 |
| Final WALK | 8/25 | final destination probability limitation |
| 교대 transfer | 8/25 | fixed fallback |
| Subway actual data | 8/29 | empirical claim 보류 |
| ACCESS/BUS_TO_SUBWAY/FINAL WALK provenance | 8/29 | PARTIAL_MODEL limitation |
| Future WAIT/timetable feasibility | 9/1 | Recommended Departure unavailable 허용 |
| Support Rule candidate | 9/3 | LOW/INSUFFICIENT conservative |
| ML promotion | 9/10 | baseline 유지 |
| Security TTL/share | 9/14 | share feature cut 가능 |
| Architecture partition/watermark | 9/14 | benchmark-based minimal config |
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
