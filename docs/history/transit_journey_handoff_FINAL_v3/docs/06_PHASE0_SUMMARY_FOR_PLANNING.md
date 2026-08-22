# Phase 0 Summary — Input for Final 기획서 (Planning Document)

> **목적:** 이 파일 하나만 있으면 Phase 0(API/Data Feasibility)의 모든 결론을
> 다른 대화(Claude.ai, ChatGPT 등)에 붙여넣어 최종 기획서 초안 작업을 시작할
> 수 있도록 압축 정리한 것. 세부 근거/원본 데이터는 각 섹션 끝에 표시된
> 파일 경로를 참고. 이 파일은 그 파일들을 대체하지 않으며, 그 파일들이
> 진실의 원천(source of truth)이다 — 여기 요약과 원본이 다르면 원본을
> 따른다.
>
> **작성일:** 2026-08-22. **작성 기준:** Decision Log D-001~D-050.

---

## 1. 제품 한 줄 정의

서울시가 제공하는 버스·지하철 실시간 데이터를 이용해, 대중교통 전체
여정의 소요시간 불확실성을 계산하고, 출발 전에는 목표 정시 도착확률에
따른 권장 출발시각을, 이동 중에는 실제 진행상황을 반영한 정시 도착확률을
갱신해 주는 반응형 Web App.

핵심은 "ETA를 더 정확히 맞히는 것"이 아니라 다음 두 질문에 답하는 것:
- **출발 전:** 목표 시각까지 늦지 않으려면 언제 출발해야 하는가?
- **이동 중:** 지금까지 실제로 발생한 상황을 반영하면 정시 도착확률은 얼마인가?

철학: 기존 ETA/운행 신호를 대체하지 않는다. 정확도 단일값보다
**calibration과 uncertainty honesty**(관측수/support/confidence를 숨기지
않음)를 우선한다.

*(근거: `01_PROJECT_HANDOFF.md` §1~2, P0-4)*

---

## 2. PM 확정 결정 (전부 답변 완료)

| # | 질문 | 결정 | 근거 |
|---|---|---|---|
| Q1 | Demo Corridor | **삼청동 ↔ 역삼역** (도착지 고정, 출발지 무관). 3호선 안국역→교대역 subway leg 경유, 총 소요 50분 | D-030, 야간/주간 안정성 재검증 D-031 |
| Q2 | Arrival Boundary(도착의 정의) | **목적 정류장/승강장이 아니라 마지막 도보(실제 약속 장소)까지 포함** | D-039 |
| Q3 | Access Time(접근시간 계산방식) | **실제 지도/경로 API(TMAP)로 계산한 값 사용** — 사용자 입력/고정값 아님 | D-040, D-045 |
| Q4 | Support Geography("서울시 데이터"의 범위) | **제공기관 AND 지리적 서울 행정구역, 둘 다 만족해야 함**(교집합). 예외 허용하되 MVP 범위는 안전하게 좁게 유지 | D-041 |
| — | 환승 실패 판정 규칙 | **Tier-0은 고정 버퍼 방식**(실시간 headway 아님) — 지하철 두 구간이 아직 실제 interval 데이터 0건이라 실시간 판정 근거 없음 | D-049 |
| — | Monte Carlo 기본값 | **N=2000~5000, 기본 목표확률 p*=90%** | D-050 |

*(근거: `01_PROJECT_HANDOFF.md` §18, `05_DECISION_LOG.md` D-030/D-039~D-041/D-049~D-050)*

---

## 3. API Feasibility — 검증된 사실 (VERIFIED / GO / BLOCKED)

### 3.1 핵심 교통 데이터 (서울시 제공, P0-1 대상)

| API | 상태 | 비고 |
|---|---|---|
| 버스 도착정보 (`getArrInfoByRouteAll`) | **GO** | 실제 endpoint, 실제 데이터 확인 |
| 버스 위치정보 (`getBusPosByRouteSt`) | **GO** | 팀 원 문서가 가정한 `getBusPosByRtid` 계열 아님 (D-011) |
| 버스 arrival↔position vehId join | **GO** | 100% join rate, 야간(D-020)·주간(D-035) 둘 다. 혼잡도 필드(`congetion`, 오탈자 그대로)는 주간에만 실값 관측 |
| 지하철 실시간 도착 (`realtimeStationArrival`) | **GO** | |
| 지하철 실시간 위치 (`realtimePosition`) | **GO** | |
| 지하철 arrival↔position trainNo join | **GO (1·3호선), CONDITIONAL (2호선)** | 1호선 91.7%, 3호선(demo corridor 역들) 100%. 2호선은 station code별로 갈림 — 강남역 특정 코드(`1002000201`)만 54.5% gap, 원인 미상 (아래 §5 참고) |
| 버스+지하철 통합 경로 (`getPathInfoByBusNSub`) | **GO** | 최초 401 에러는 URL 오타 때문이었음(`...List` 접미사 존재하면 안 됨, D-024). 실제 mixed(버스+지하철) 경로 반환 확인(D-029) |
| 서울시 노선별 구간 평균 운행시간 (OA-21217, historical) | **DROPPED (PM 결정)** | 실시간 폴링 API 아니라 대용량 ZIP 파일 배포 방식, 서비스 종료 안내 있음(D-025/D-028) |

### 3.2 도보/접근시간 데이터 (P0-1 대상 아님, 별도 유틸리티)

| Provider | 상태 | 비고 |
|---|---|---|
| 카카오모빌리티 도보 길찾기 | **BLOCKED** | `403 permission denied` — 제휴사 전용 API, 일반 REST 키로는 불가 (D-043) |
| TMAP(SK Open API) 보행자 경로 | **GO** | 실제 GeoJSON 경로 수신 확인. **주의**: 앱키 발급과 상품 구독이 분리된 구조라 "보행자 경로 안내" 상품을 별도 구독해야 동작함 (D-045) |

*(근거: `05_DECISION_LOG.md` D-011~D-024, D-029, D-035, D-043, D-045; `api-spikes/PHASE0_API_FEASIBILITY.md`)*

---

## 4. ID Mapping / Crosswalk

- **버스**: mixed-route API의 `routeId`가 realtime API(`getArrInfoByRouteAll`/`getBusPosByRouteSt`)의 `busRouteId`와 **동일** — crosswalk 불필요, 직접 조인 가능 (D-038)
- **지하철**: mixed-route API의 station 코드(`fid`/`tid`)가 realtime API의 `statnId`와 **다른 ID 공간** — crosswalk 필요. Demo Corridor의 4개 station-node(안국/교대 3호선측/교대 2호선측/역삼) 전부에 대해 **수작업 crosswalk 표 완성**(D-047). 단, 이건 이 corridor 전용이며 citywide 범용 crosswalk 서비스는 아직 없음

*(근거: `data-contract/ID_MAPPING.md`, D-034, D-038, D-047)*

---

## 5. 알려진 리스크 / 미해결 항목

1. **강남역 `1002000201` join gap** (54.5%, 2호선). Pagination(D-023)·지리/방향(D-027)·교차노선명(D-032/D-033) 4개 가설 전부 기각. 최신 가설은 시간대 의존성(D-036) — 주간 44회 폴링에서 이 station code 자체가 아예 안 나타남. Demo corridor 역들은 영향 없음(전부 100%). Citywide subway actual rule을 "안전하다"고 하기 전에 반드시 해결 필요
2. **지하철 leg 실제 interval(도착 이벤트) 표본이 아직 0건.** ~15분 지속수집으로 join 신뢰도는 재확인했지만(D-048) 그 시간 안에 실제 도착(`arvlCd=1`)까지 캡처된 열차가 없었음 — 최소 1시간 이상 수집 필요
3. **버스 01A leg는 첫 실제 residual 표본(54개 전이) 확보**했지만 아직 단일 15분 창 — route 753이 썼던 시간/일 단위 규모는 아님
4. **지하철 환승 도보(교대역 3호선↔2호선) 모델링 미결정** — TMAP으로 계산할지 고정값을 쓸지. TMAP은 지상 도보용으로 설계돼 있어 유료구역 내 환승 통로를 잘 모델링할지 불확실, 미검증
5. **Citywide 일반화는 전부 미착수** — 지금까지 검증된 모든 것은 이 Demo Corridor(삼청동↔역삼역)와 두 개 버스/지하철 노선에 한정됨

*(근거: D-023, D-026, D-027, D-032~D-036, D-044, D-048)*

---

## 6. Probability Engine — 설계 초안 (구현 안 됨, 문서만)

**Leg 구성** (7개: WALK 4 + BUS 1 + SUBWAY 2):
```
WALK(접근) → BUS 01A → WALK(환승) → SUBWAY 3호선(안국→교대)
→ WALK(환승, 미결정 §5-4) → SUBWAY 2호선(교대→역삼) → WALK(최종)
```

**Monte Carlo 로직** (`01_PROJECT_HANDOFF.md` §11 그대로):
- 시뮬레이션마다 전체 여정을 끝까지 진행, 환승 실패 시 다음 차량 선택
- `P(on_time) = count(final_arrival <= target) / N`
- **계획 환승 성공확률**과 **최종 정시 도착확률**을 분리해서 보고
- 권장 출발시각은 `P(arrival<=target|depart_time) >= p*`를 만족하는 가장 늦은 시각 (binary search / time grid)

**Fallback 계층** (데이터 준비 안 된 leg용):
- Tier 0: WALK leg는 TMAP 단일 추정치 + placeholder variance, `fallback_level` 필드로 명시
- Tier 1: 실제 sustained collection 완료되면 버스/지하철도 empirical quantile로 승격

**왜 아직 구현 안 했는가**: `01_PROJECT_HANDOFF.md` §3.2가 Journey Engine을
"PM+Reliability+Backend 공동 계약"으로 설계하라고 명시. 확률/통계 설계
오류는 티가 잘 안 나는 위험 지점이라, 설계 문서 리뷰 → 데이터 준비 →
구현 순서를 지킴.

*(전체 문서: `data-contract/PROBABILITY_ENGINE_DESIGN_V0.md`)*

---

## 7. 이 다음에 남은 것 (기획서에 반영할 로드맵)

원래 일정(`01_PROJECT_HANDOFF.md` §19) 기준:

- **Phase 0A/0B (API/Data Feasibility)** — 이 문서 기준 **사실상 완료**
- **G2: Probability Engine** (원래 일정 9/1~9/7) — 설계는 끝났고 구현 시작 가능. 선행 조건: §5의 지하철 interval 데이터 추가 수집(1시간+), §6의 남은 open question(지하철 환승 도보 모델링) 결정
- **Product Integration** (9/8~9/14) — Web UI, 미착수
- **분산처리 Proof** (9/15~9/21) — Kafka/Flink/Spark 벤치마크, 미착수
- **Scope Freeze / Final** (9/22~9/28)

---

## 8. 참고 파일 전체 목록 (세부 근거)

| 파일 | 내용 |
|---|---|
| `01_PROJECT_HANDOFF.md` | 전체 기준 문서 — 원칙, Use Case, Data Contract, Probability 수학, 일정 |
| `05_DECISION_LOG.md` | D-001~D-050 전체 의사결정/증거 이력 |
| `api-spikes/PHASE0_API_FEASIBILITY.md` | API별 상세 Feasibility 판정 |
| `data-contract/ID_MAPPING.md` | ID 매핑/crosswalk 상세 |
| `data-contract/OBSERVATION_CONTRACT.md` | timestamp/관측 단위 계약 |
| `data-contract/QUALITY_FLAGS.md` | 데이터 품질 플래그 목록 |
| `data-contract/SUBWAY_ACTUAL_RULE_V0.md` | 지하철 Actual 판정 규칙 v0 |
| `data-contract/PROBABILITY_ENGINE_DESIGN_V0.md` | 확률엔진 설계 초안 전문 |
| `03_API_SPIKE_CHECKLIST.md` | Phase 0 체크리스트 (검증 완료 항목 체크됨) |
