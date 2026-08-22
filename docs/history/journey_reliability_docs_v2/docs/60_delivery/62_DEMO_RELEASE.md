---
doc_id: JR-DOC-062
title: Demo and Release Contract
version: 1.2
status: REVIEW
owner: PM
last_updated: 2026-08-22
depends_on:
  - JR-DOC-010
  - JR-DOC-061
  - JR-DOC-053
source_of_truth_for:
  - final-demo
  - release-preflight
  - claim-policy
supersedes: []
---

# Demo / Release

## 1. Primary Demo Story

목표:
멀티캠퍼스 역삼 약속시간 내 도착 가능성을 판단.

Route A:

```text
삼청동
→ ACCESS_WALK
→ BUS_WAIT
→ 01A
→ BUS_TO_SUBWAY
→ SUBWAY_WAIT
→ 3호선 안국→교대
→ SUBWAY_TO_SUBWAY
→ SUBWAY_WAIT
→ 2호선 교대→역삼
→ FINAL_WALK
→ 멀티캠퍼스 역삼
```

## 2. Current Evidence Constraints for Demo

- ACCESS point route: 297 m / 245 s VERIFIED
- BUS_TO_SUBWAY street: 143 m / 101 s VERIFIED, station internal UNMODELED
- 교대 3→2 Tier-0: OA-22521 144 s reference, uncertainty UNMODELED
- FINAL WALK: STATION_CENTER→POI 329 m / 300 s VERIFIED; exit-based 아님
- Route B source interoperability: VERIFIED, Reforecast code는 별도 acceptance 필요
- Subway/Bus probability maturity: 아직 CONDITIONAL

이 값은 **input/reference evidence**이지 final Journey probability 결과가 아니다.

## 3. Pre-trip Demo

사용자 입력:
- origin
- destination
- target arrival
- target reliability

보여줄 것:
- selected route
- real P50/P90
- real P(on-time)
- recommended departure if available
- support/confidence
- limitation

mock number 금지.

## 4. Reforecast Demo

가능하면 Main User Event를 같은 Demo OD의 **Route B**에서 짧게 증명한다. Route B의 구조 자체는 Phase 0 Raw에서 이미 확인됐다.

```text
01A
→ 3호선 안국→압구정
→ TRANSFER_SUBWAY_TO_BUS
→ BUS_WAIT(147)
→ BUS_SKIPPED
→ REFORECAST
```

Primary product demo는 Route A(`01A→3호선→2호선`)를 유지한다.

Route B의 realtime ID/Wait/Reforecast가 준비되지 않으면 `SUBWAY_TO_BUS Reliability E2E VERIFIED` 설명을 삭제한다. 단 structural route existence는 별도 Evidence로 설명할 수 있다.

## 5. Engineering Evidence

한 Journey/분석 결과에서:

```text
Raw
→ Observation
→ Actual
→ Residual
→ Distribution
→ Simulation
→ UI
```

의 artifact IDs를 보여준다.

## 6. Distributed Proof Segment

발표:
1. 실제 data volume 먼저
2. replay multiplier 명시
3. 1/2/4 worker 또는 stream worker proof
4. bottleneck/shuffle/state
5. optimization A/B
6. correctness

20x replay를 “서울 실시간 트래픽”이라고 부르지 않는다.

## 7. Allowed Claims

- `Demo Corridor에서 실제 API 연결을 검증했다.`
- `Route B의 SUBWAY→BUS 구조와 realtime source interoperability를 corridor-scoped로 검증했다.`
- `버스 01A에서 실제 Prediction/Position/Actual transition을 관측했다.`
- `Demo 지하철 node에서 train join을 확인했다.`
- `실제 관측 기반 distribution/fallback metadata를 Journey simulation에 연결했다.` — 실제 구현 후
- `현재 검증 범위는 COMPONENT_ONLY/CORRIDOR_REPLAY다.` — 실제 metadata와 일치할 때
- `일부 구간 uncertainty는 아직 모델링되지 않았다.`

## 8. Forbidden Claims

- `서울 전체에서 90% 정확하다.`
- `AI가 교통 지연을 정확히 예측한다.`
- `사용자가 버스를 못 탈 확률을 예측한다.`
- `TMAP walking time이 실제 walk distribution이다.`
- `P90=90% 확률로 그 시각에 도착한다.`
- `amplified replay가 실제 트래픽이다.`
- `Kafka/Flink 때문에 서비스가 반드시 필요했다` — volume proof 없이
- `SUBWAY_TO_BUS Reliability E2E 지원 완료` — Route B realtime E2E 미검증 시
- `전체 Journey 확률이 calibration되었다` — END_TO_END validation이 없을 때

## 9. Demo Preflight Checklist

### T-24h
- [ ] latest docs locked
- [ ] evidence snapshot frozen
- [ ] raw demo samples accessible
- [ ] provider quota check
- [ ] latest distribution
- [ ] validation_scope 확인
- [ ] ACCESS/BUS_TO_SUBWAY/FINAL WALK coordinate provenance 확인
- [ ] BUS_TO_SUBWAY internal `UNMODELED_UNCERTAINTY` 표시
- [ ] Recommended Departure가 HOLD이면 UI가 `AVAILABLE`을 만들지 않는지 확인
- [ ] Recommended Departure를 쓰면 future WAIT source 확인
- [ ] backup
- [ ] rollback artifact
- [ ] secret scan

### T-2h
- [ ] Web health
- [ ] API health
- [ ] collector health
- [ ] Kafka/Flink if live
- [ ] route provider
- [ ] TMAP if required live
- [ ] mobile viewport
- [ ] share if used

### T-15m
- [ ] actual demo input
- [ ] probability returns
- [ ] BUS_SKIPPED works
- [ ] Evidence Detail works
- [ ] no debug secret

## 10. Provider Outage During Demo

원칙:
**가짜 live result로 성공 시연하지 않는다.**

대응 순서:
1. retry
2. stale/last-success 상태를 명확히 표시
3. 사전 캡처 evidence/replay를 “recorded evidence”라고 명시하고 engineering proof로 전환
4. live provider outage 자체를 limitation으로 설명

## 11. Release Freeze

9/21 이후 신규 major feature 금지.

예외:
- critical bug
- security
- evidence correctness
- demo blocker

모든 예외는 Decision/Changelog 기록.
