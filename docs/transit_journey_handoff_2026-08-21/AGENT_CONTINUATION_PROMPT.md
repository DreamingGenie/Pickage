# Claude / Codex용 이어서 작업 Prompt

아래 프로젝트를 VS Code에서 이어서 맡아라.

## 먼저 반드시 읽을 파일

1. `docs/01_PROJECT_HANDOFF.md`
2. `docs/03_API_SPIKE_CHECKLIST.md`
3. `docs/04_SOURCE_INDEX.md`
4. `docs/05_DECISION_LOG.md`
5. `sources/project/` 안의 프로젝트 PDF/문서
6. 기획 품질 참고가 필요할 때만 `sources/reference_quality/`

이 프로젝트는 **서울시 데이터만 사용하여 버스+지하철 전체 여정의 정시 도착확률과 권장 출발시각을 계산하고, 이동 중 실제 상태를 반영해 확률을 재계산하는 Web App**이다.

최종 마감은 **2026-09-28**, 팀은 6인이다. 지금은 최종 구현 단계가 아니라 **Phase 0: API/Data Feasibility + Contract + Vertical Spike 단계**다. API Key는 이미 확보되어 있다. 실제 key는 repo에 commit하지 말고 환경변수/CI secret만 사용한다.

## 너의 역할

너는 단순 코더가 아니라 다음 네 역할을 동시에 수행한다.

- Senior Data/Distributed Engineer
- Backend Architect
- Product/Technical Planner
- Evidence-driven Reviewer

그렇지만 인간 경력/현업 경험을 가장하지 말고, 모든 주장은 실제 API/데이터/문서 근거로 검증한다.

## 작업 원칙

1. **전체 앱부터 만들지 마라.**
2. 먼저 실제 API를 호출해 source timestamp, 식별자, 상태 전이, 호출 한도, duplicate, error를 검증하라.
3. `VERIFIED / HYPOTHESIS / TO_VERIFY / DROP`을 분리하라.
4. 팀 문서와 실제 API가 충돌하면 실제 API/공식 최신 명세를 우선하되, 충돌을 Decision Log에 남겨라.
5. Raw payload는 보존하고 `received_at`을 항상 저장하라.
6. API key를 출력/로그/commit하지 마라.
7. synthetic replay는 부하 생성용이지 학습 Ground Truth가 아니다.
8. Bus/Subway의 경험분포 baseline을 만들기 전에 LightGBM/딥러닝부터 시작하지 마라.
9. 분산 기술은 필요성/부하/상태량을 수치로 증명한 뒤 확정하라.
10. 사용자에게 보여주는 확률은 support와 calibration이 설명 가능해야 한다.

## 지금 수행할 우선순위

### Task A — Repository reconnaissance

- 현재 monorepo 구조/기술스택/실행방법을 조사한다.
- 현재 코드가 없다면 handoff의 권장 구조를 참고하되, 최소 Spike 구조만 만든다.
- `.gitignore`, `.env.example`, secret loading을 먼저 점검한다.

### Task B — API smoke test harness

`scripts/spikes/` 또는 적절한 위치에 **read-only API test harness**를 만든다.

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

기존 문서의 753번 PoC 논리를 repository에서 재현한다.

반드시 측정:

- Prediction↔Location vehId join rate
- unique source timestamp ratio
- duplicate snapshots
- Actual arrival interval width
- Prediction per actual event
- residual lower/mid/upper
- expired-on-receipt

### Task D — Subway Ground Truth Spike

가장 중요한 미해결 사항이다.

실시간 ETA와 Position을 일정 시간 함께 수집해:

- btrainNo/trainNo 계열 join
- 호선/방향/종착역 consistency
- arrival state transition
- actual interval
- mismatch/anomaly

를 실제 수치로 보고하라.

**성공 전에는 subway actual rule을 확정하지 마라.**

### Task E — Mixed route Spike

서울 내 bus+subway route 1개를 실제 조회하고:

- route response
- Bus ID mapping
- Subway ID mapping
- walking/transfer fields
- realtime API와의 join 가능성

을 검증한다.

실패하면 route provider를 교체하려 하지 말고 먼저 **fixed demo corridor fallback**을 제안하라.

### Task F — Historical join

서울시 bus section historical average가 realtime route/stop/section과 join되는지 검증한다.

### Task G — Phase 0 report

Spike 후 아래 파일을 생성/갱신한다.

- `docs/api-spikes/PHASE0_API_FEASIBILITY.md`
- `docs/data-contract/OBSERVATION_CONTRACT.md`
- `docs/data-contract/ID_MAPPING.md`
- `docs/data-contract/QUALITY_FLAGS.md`
- `docs/decisions/` ADR들
- `docs/05_DECISION_LOG.md`

보고서에서는 반드시:

- 실제 sample counts
- join rate
- API error/empty/duplicate rate
- timestamp 의미
- 호출량
- Ground Truth uncertainty
- GO / CONDITIONAL / PIVOT 판단

을 넣어라.

## 그 다음에만 진행할 것

Phase 0가 통과하면 fixed mixed corridor에서 ML 없는 empirical baseline으로:

`Route → Leg Distribution → Monte Carlo Journey → P(on-time) → Recommended Departure → Reforecast`

vertical slice를 만든다.

그 뒤에 LightGBM Quantile을 Baseline과 calibration/coverage/pinball loss로 비교한다.

## Agent의 커뮤니케이션 규칙

- 실제로 코드를 실행하고 결과가 있으면 결과를 요약하라.
- 실패를 숨기지 말고 raw evidence 위치를 말하라.
- 사용자 결정이 필요한 Scope 질문만 묻고, 기술적으로 스스로 검증 가능한 것은 먼저 검증하라.
- 대규모 리팩터링/기술 확정 전에는 왜 필요한지 보고하라.
- 현재 handoff의 최상위 원칙을 임의 변경하지 마라.

## 첫 응답/첫 행동

1. handoff와 source index를 읽었다고 짧게 확인.
2. repository 구조와 secret 주입 방법을 점검.
3. 실행할 API Spike 순서를 5~10줄로 제시.
4. 바로 smoke test harness와 sanitized raw sample 저장 구조부터 작업 시작.
5. API 호출에 필요한 환경변수 이름이 실제 repo와 다르면 `.env.example`만 수정하고 실제 값을 요구할 때는 **값 자체가 아니라 어떤 변수에 넣어야 하는지만** 안내.
