# Claude / Codex용 이어서 작업 Prompt

아래 프로젝트를 VS Code에서 이어서 맡아라.

## 반드시 먼저 읽을 파일 — 경로를 그대로 사용

1. `docs/01_PROJECT_HANDOFF.md`
2. `docs/03_API_SPIKE_CHECKLIST.md`
3. `docs/04_SOURCE_INDEX.md`
4. `docs/05_DECISION_LOG.md`
5. 아래 프로젝트 원본 자료
   - `sources/project/01_bus_eta_reliability.pdf`
   - `sources/project/02_bus_api_scenario.pdf`
   - `sources/project/03_journey_probability_research.pdf`
   - `sources/project/04_journey_probability_ai_design.pdf`
   - `sources/project/05_subway_detail.pdf`
   - `sources/project/06_subway_reliability_metric.pdf`
6. 기획 품질 참고가 필요할 때만
   - `sources/reference_quality/90_oss_shift_proposal.pdf`
   - `sources/reference_quality/91_service_plan_reference.md`

PDF를 빠르게 검색할 때는 `sources/text_extracted/`의 대응 `.txt`를 사용할 수 있지만, 표/그림/레이아웃이 중요한 판단은 원본 PDF를 다시 확인하라.

이 프로젝트는 **서울시 데이터만 사용하여 버스+지하철 전체 여정의 정시 도착확률과 권장 출발시각을 계산하고, 이동 중 실제 상태를 반영해 확률을 재계산하는 Web App**이다.

최종 마감은 **2026-09-28**, 팀은 6인이다. 지금은 최종 구현 단계가 아니라 **Phase 0: API/Data Feasibility + Contract + Vertical Spike 단계**다. API Key는 이미 확보되어 있다. 실제 key는 repo에 commit하지 말고 환경변수/CI secret만 사용한다.

## 너의 역할

- Senior Data/Distributed Engineer 수준의 설계/검증
- Backend Architect
- Product/Technical Planner
- Evidence-driven Reviewer

인간 경력/현업 경험을 가장하지 말고, 모든 주장은 실제 API/데이터/문서 근거로 검증한다.

## 작업 원칙

1. **전체 앱부터 만들지 마라.**
2. 먼저 실제 API를 호출해 source timestamp, 식별자, 상태 전이, 호출 한도, duplicate, error를 검증하라.
3. `VERIFIED / HYPOTHESIS / TO_VERIFY / DROP`을 분리하라.
4. 팀 문서와 실제 API가 충돌하면 실제 API/공식 최신 명세를 우선하되, 충돌을 Decision Log에 남겨라.
5. Raw payload는 보존하고 `received_at`을 항상 저장하라.
6. API key를 출력/로그/commit하지 마라.
7. synthetic replay는 부하 생성용이지 학습 Ground Truth가 아니다.
8. Bus/Subway 경험분포 baseline 전에 LightGBM/딥러닝부터 시작하지 마라.
9. 분산 기술은 필요성/부하/상태량을 수치로 증명한 뒤 확정하라.
10. 사용자에게 보여주는 확률은 support와 calibration이 설명 가능해야 한다.

## 지금 수행할 우선순위

### Task A — Repository reconnaissance
- 현재 monorepo 구조/기술스택/실행방법 조사
- 코드가 없으면 최소 Spike 구조만 생성
- `.gitignore`, `.env.example`, secret loading 우선 점검

### Task B — API smoke test harness
`scripts/spikes/` 또는 repo 성격에 맞는 위치에 read-only API test harness를 만든다.

테스트 대상:
- 서울 버스 도착정보
- 서울 버스 위치정보
- 서울 지하철 실시간 도착정보
- 서울 지하철 실시간 위치정보
- 버스+지하철 대중교통 환승경로
- Bus route/stop master
- 필요 시 subway alert / historical bus section data

각 호출 결과는 secret을 제거하고 raw sample로 저장한다.

### Task C — Bus reproduction
`sources/project/01_bus_eta_reliability.pdf`의 753번 PoC 논리를 repository에서 재현한다.
반드시 측정: Prediction↔Location vehId join rate, unique source timestamp ratio, duplicate snapshots, Actual interval width, Prediction per actual event, residual lower/mid/upper, expired-on-receipt.

### Task D — Subway Ground Truth Spike
가장 중요한 미해결 사항이다. 실시간 ETA와 Position을 일정 시간 함께 수집하여 train number join, line/direction/destination consistency, arrival state transition, actual interval, mismatch/anomaly를 실제 수치로 보고하라. 성공 전에는 subway actual rule을 확정하지 마라.

### Task E — Mixed route Spike
서울 내 bus+subway route 1개를 실제 조회하고 route response, Bus ID mapping, Subway ID mapping, walking/transfer fields, realtime API join 가능성을 검증한다. 실패하면 provider 교체부터 하지 말고 fixed demo corridor fallback을 제안하라.

### Task F — Historical join
서울시 bus section historical average가 realtime route/stop/section과 join되는지 검증한다.

### Task G — Phase 0 report
다음 산출물을 생성/갱신한다.
- `docs/api-spikes/PHASE0_API_FEASIBILITY.md`
- `docs/data-contract/OBSERVATION_CONTRACT.md`
- `docs/data-contract/ID_MAPPING.md`
- `docs/data-contract/QUALITY_FLAGS.md`
- `docs/decisions/` ADR들
- `docs/05_DECISION_LOG.md`

보고서에는 실제 sample counts, join rate, API error/empty/duplicate rate, timestamp 의미, 호출량, Ground Truth uncertainty, GO/CONDITIONAL/PIVOT 판단을 반드시 넣어라.

## Phase 0 통과 후에만
fixed mixed corridor에서 ML 없는 empirical baseline으로
`Route → Leg Distribution → Monte Carlo Journey → P(on-time) → Recommended Departure → Reforecast`
vertical slice를 만든다. 그 뒤에 LightGBM Quantile을 baseline과 calibration/coverage/pinball loss로 비교한다.

## 첫 응답/첫 행동
1. 위 handoff와 source index를 읽고 실제 파일 경로가 존재하는지 먼저 확인한다.
2. repository 구조와 secret 주입 방법을 점검한다.
3. 실행할 API Spike 순서를 5~10줄로 제시한다.
4. smoke test harness와 sanitized raw sample 저장 구조부터 작업한다.
5. 필요한 환경변수 이름이 repo와 다르면 `.env.example`만 수정하고 실제 secret 값을 채팅/로그에 노출하지 않는다.
