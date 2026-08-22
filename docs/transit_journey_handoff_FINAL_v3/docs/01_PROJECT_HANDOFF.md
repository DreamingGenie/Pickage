# 서울 대중교통 Journey Reliability 프로젝트 — Agent Handoff

> 상태: **Phase 0 / 사전 검증 및 설계 기준선**  
> 기준일: **2026-08-21 KST**  
> 최종 마감: **2026-09-28**  
> 대상: VS Code에서 Claude/Codex 등 코딩 에이전트가 이어서 조사·검증·기획·Spike 구현을 수행하기 위한 인수인계 문서  
> 중요: 이 문서는 최종 기획서가 아니다. **최종 기획서를 수준 높게 만들기 위해 무엇을 사실로 보고, 무엇을 검증하고, 어떤 순서로 의사결정할지 고정하는 작업 기준서**다.

---

## 0. 이 문서를 읽는 Agent에게

이 프로젝트에서는 "그럴듯한 기획을 먼저 완성"하지 않는다.

반드시 다음 순서를 지킨다.

1. **실제 API / 실제 데이터로 가능한 것을 확인한다.**
2. `확인된 사실(VERIFIED)`과 `가설(HYPOTHESIS)`, `검증 필요(TO VERIFY)`, `폐기(DROP)`를 분리한다.
3. 데이터의 관찰 단위, timestamp, 식별자, Ground Truth, 결측/중복, 호출 한도를 먼저 고정한다.
4. 그 뒤에 Probability Contract를 정한다.
5. 그 뒤에 Web App 기능과 UX를 고정한다.
6. 마지막에 Kafka/Flink/Spark/ML/AI 같은 기술을 필요한 만큼 채택한다.

**기술을 사용하기 위해 문제를 만들지 말 것.**

---

# 1. 프로젝트 최상위 정의

## 1.1 현재 한 줄 정의

**서울시가 제공하는 버스·지하철 실시간/역사 운행 데이터를 이용해, 대중교통 전체 여정의 소요시간 불확실성을 계산하고, 출발 전에는 목표 정시 도착확률에 따른 권장 출발시각을, 이동 중에는 실제 진행상황을 반영한 정시 도착확률을 갱신해 주는 Web App.**

핵심은 "ETA를 새로 더 정확히 맞힌다"가 아니다.

핵심은 다음 두 질문에 답하는 것이다.

- **출발 전:** "목표 시각까지 늦지 않으려면 언제 출발해야 하는가?"
- **이동 중:** "지금까지 실제로 발생한 상황을 반영하면 이제 시간 내 도착할 확률은 얼마인가?"

개별 버스/지하철 ETA 신뢰도는 **상위 Journey Probability를 만들기 위한 하위 엔진**이다.

---

## 1.2 절대 우선 원칙

현재 사용자/PM이 명시한 원칙이다. 변경하려면 PM 승인 필요.

### P0-1. 데이터 원천

**서울시 데이터만 사용한다.**

**PM 확정 (2026-08-22, Q4 — D-041): "서울시 데이터"는 제공기관 기준 AND 지리적
서울 행정구역 기준을 모두 만족해야 한다 (교집합이지 합집합이 아니다).** 즉
핵심 교통(버스/지하철) reliability 데이터는 서울특별시/서울교통공사 등이 직접
제공하면서 동시에 서울 행정구역 내 노선/역/정류장이어야 한다.

- TAGO 등 전국 단위 API는 **최종 분석 데이터 소스에서 제외**한다.
- 기존 팀 자료의 TAGO 실험은 "왜 서울 API가 우위인지 보여주는 feasibility 참고"로만 남긴다.
- 버스/지하철 핵심 데이터 중 서울시가 제공기관이 아닌 데이터가 불가피하게
  필요한 경우 예외적으로 쓸 수 있으나, PM은 **MVP 범위를 안전하게 좁게
  유지**하려는 의도가 명확하므로 범위를 넓히는 판단은 신중히 한다.
- 이 원칙은 버스/지하철 등 **핵심 교통 reliability 데이터**에 적용되는 것이며,
  도보/접근시간 계산에 쓰는 지도·경로 API(카카오맵 등, Q3/D-040 참고)는 이
  원칙의 적용 대상이 아닌 별도 유틸리티로 취급한다.
- **실제 데모 경로는 서울시 데이터만으로 완결되는 서울 내 경로를 사용**한다
  (Demo Corridor 삼청동↔역삼역, D-030으로 이미 충족).

### P0-2. 교통수단

**버스 + 지하철 복합 여정이 Main**이다.

버스만, 지하철만의 신뢰도 화면은 하위 분석/보조 기능일 수 있으나 최종 제품의 중심은 아니다.

### P0-3. 제품 형태

**Web App**이다.

- 모바일 브라우저 사용을 고려한 반응형 Web을 우선한다.
- 별도 네이티브 앱 출시, 푸시 인프라 등은 현재 필수 아님.
- 이동 중 확인 Use Case를 위해 모바일 Web UX는 중요하다.

### P0-4. 설명 철학

"가장 정확한 교통 앱" 또는 "AI가 정확히 예측"을 주장하지 않는다.

원래 RailOdds 문서의 핵심 철학을 유지한다.

- 기존 공개 ETA/운행 신호를 대체하지 않는다.
- 실제 관측 오차 및 이동시간 분포를 누적한다.
- 확률의 **관측수/support/confidence**를 숨기지 않는다.
- 정확도 단일값보다 **calibration과 uncertainty honesty**를 우선한다.

---

# 2. Main Use Case — 제품 판단의 최상위 기준

## 2.1 원형 시나리오

사용자가 제시한 원래 Persona는 다음 구조였다.

- 아침에 약속이 있다.
- 전체 여정은 지하철 + 버스 환승이다.
- 평균 소요시간 하나가 아니라 "빠르면 / 보통 / 지연 시" 범위를 보고 안전하게 출발시각을 정한다.
- 이동 중 지하철 구간을 지난 뒤 버스로 환승한다.
- 버스가 혼잡하여 한 대를 보내고 다음 차를 탄다.
- 기존 예상이 깨졌으므로 앱을 다시 열어 **현재 상태에서 약속시간 내 도착확률을 재확인**한다.
- 그 결과를 친구에게 공유한다.

원형 예시는 수원→강남이었지만, **서울시 데이터 only 원칙과 실제 지원범위를 충돌시키지 않기 위해 실제 데모는 서울시 데이터만으로 완결되는 서울 내 mixed-mode corridor로 바꿔야 한다.**

스토리의 핵심은 지명이 아니라 다음 상태 전이다.

`PRE_TRIP → SUBWAY_ONBOARD → TRANSFER → BUS_WAITING → (BUS_SKIPPED) → BUS_ONBOARD → DESTINATION`

---

## 2.2 Main Use Case가 요구하는 출력

### 출발 전(Pre-trip)

최소한 다음을 사용자에게 제공하는 것이 목표다.

- 추천 경로 또는 분석 대상 경로
- 예상 도착시각의 대표값(P50 등)
- 보수적 도착시각 또는 도착 범위(P90 등)
- `목표 시각 이전 도착확률`
- 사용자가 원하는 확률(예: 80/90/95%)을 만족시키는 `권장 출발시각`
- 가장 큰 불확실성/위험 구간
- 근거가 충분한지(관측수/모델 또는 fallback 근거)

### 이동 중(In-trip / Reforecast)

실제 진행상태를 조건으로 남은 여정만 다시 계산한다.

예:

- 현재 교통수단과 단계
- 현재 위치/관측시각
- 남은 Journey의 P50/P90
- 목표시각 이전 도착확률
- 이전 계산 대비 변화량(예: -11%p)
- 변화 이유(실제 관측된 사건에 기반)

### 공유(Share)

MVP에서는 복잡한 소셜 기능이 아니라 **현재 Journey Snapshot을 공유 가능한 텍스트/URL 형태로 만드는 것** 정도가 적절하다.

예:

```text
09:30 약속
현재 예상 도착 09:23
09:30 전 도착확률 76%
기준시각 09:08
```

---

## 2.3 "버스 한 대 보냄" 사건 처리 원칙

MVP에서 "혼잡 때문에 사용자가 탑승 실패할 확률"을 억지로 학습하지 않는다.

이유:

- API 혼잡도/만차 값은 개별 사용자의 실제 승차 가능 여부와 동일하지 않다.
- 사람이 많아도 탈 수 있고, 사용자가 자발적으로 보내는 경우도 있다.
- 정류장별 실제 승차 실패 Ground Truth가 현재 확보되지 않았다.

권장 방식:

- Pre-trip에서는 정상 탑승 가정 또는 데이터로 지원 가능한 boarding model만 사용.
- 실제 사용자가 버스를 보내거나 놓쳤다면 **이미 관측된 user event**로 처리.
- `BUS_SKIPPED`/`MISSED_BOARDING` 이벤트 이후 다음 버스와 남은 여정을 재계산.

즉 "예측"보다 "Reforecast 입력"으로 사용한다.

---

# 3. 프로젝트 팀 / 일정 / 개발 환경

## 3.1 마감

- **최종 마감: 2026-09-28**
- 2026-08-21 기준으로 API key는 확보 완료되었고, 지금부터 실제 API Spike/수집을 즉시 시작해야 한다.
- 과거 실시간 이력을 사후 복구할 수 없는 데이터가 있으므로 수집기 가동이 Critical Path다.

## 3.2 팀 6인

현재 확정/선호 기준이다.

| 인원 | 현재 역할/성향 | 비고 |
|---|---|---|
| 사용자 | **팀장 + PM** | 전체 기획, 제품·데이터 계약, 빈 영역 보완, 통합/품질 판단 |
| 1명 | **UI/UX + AI** | 역할 확정 |
| 1명 | **Full-stack, Front 중심** | Web App 프론트 중심 |
| 3명 | **Backend 희망** | 이 중 1명이 Infra 담당 예정 |

아래는 권장 배치이며 확정은 아님.

- BE-A: Bus Collector + Bus Reliability
- BE-B: Subway Collector + Subway Reliability
- BE-C/Infra: Kafka/Flink/Storage/CI-CD/Observability/EC2
- Full-stack: Frontend + Serving API integration
- UI/UX+AI: UX 상태설계 + 분석/ML 실험 + 설명 계층
- PM: Scope/Data/Probability contract, Journey engine 요구사항, 검증표, QA, 문서 기준선

Journey Probability Engine은 특정 1명이 고립해서 만들지 말고 **PM + Reliability 담당 + Backend**가 공동 계약으로 설계한다.

## 3.3 인프라/기기

- 팀원 6명 모두 RTX 4050 노트북
- 주요 서버: **EC2 2대**
- AI/ML 학습용 **H100 지원 예정**
- GitLab monorepo
- Jenkins 포함 CI/CD·도구 사용 제한이 거의 없음

중요:

**컴퓨팅 자원보다 API 호출 한도와 실제 운행 데이터 축적시간이 더 희소한 자원**이다.

H100이 있다는 이유만으로 딥러닝을 채택하지 않는다.

---

# 4. 소스 문서의 위계 — 서로 섞지 말 것

첨부 문서들은 서로 다른 성격이다. 동등한 "기획안"으로 합치지 않는다.

## Tier A — 실제 데이터/Feasibility 근거

### `sources/project/01_bus_eta_reliability.pdf`

가장 중요한 실제 PoC 문서.

확인된 내용:

- 서울 버스 753번을 약 1시간 실제 수집.
- Prediction API와 Location API에서 차량 ID가 직접 연결됨.
- `stopFlag` 전이로 실제 도착을 interval Ground Truth로 잡음.
- 여러 Prediction snapshot ↔ 하나의 Actual arrival을 연결해 residual 생성 성공.
- ETA가 멀수록 residual 중앙값의 편향보다는 **분포 폭이 넓어지는 패턴**이 선명.
- 서울 API는 TAGO보다 vehicle identity/source timestamp/안정성 측면에서 이 프로젝트에 적합.
- 단일 노선 PoC 결과를 서울 전체 일반화하면 안 됨.
- API 호출 한도가 주요 병목.

이 문서의 실제 검증결과는 **버스 파트 최우선 기준**이다.

## Tier B — 계산/시나리오 설계

### `sources/project/02_bus_api_scenario.pdf`

활용 가치가 높은 아이디어:

- 버스 위치 API의 `vehId`, `sectOrd`, `stopFlag`, `nextStTm`, 거리/간격 등 활용.
- 차량 궤적 단위 feature.
- 노선 혼잡 계수 / 앞차 간격 / 구간 속도.
- PRE-TRIP / WAITING / ON-BOARD 세 상태를 공통 엔진으로 처리.
- 버스 A→B를 구간별 주행+정차 분포로 합성하는 Monte Carlo 아이디어.
- 인접 도로구간 상관관계를 무시하지 말 것.
- 관측 충분한 경험분포에 무조건 ML을 넣지 말 것.

단, 이 문서는 아이디어가 많으므로 **실제 API Spike에서 확인된 필드/품질만 승격**한다.

### `sources/project/03_journey_probability_research.pdf`

Journey Probability의 핵심 논리.

- 각 구간 확률을 단순 합/곱하지 않는다.
- 가상 여정을 수천 회 끝까지 재생한다.
- 환승 실패 시 다음 차량을 선택해 최종 도착까지 계속 진행.
- 계획한 환승 성공확률과 최종 정시 도착확률을 분리.
- 같은 열차의 역별 지연을 독립적으로 추출하지 않는다.
- 현재 발생 중인 이례상황은 반영하되 미래 희귀 사고 발생확률은 MVP에서 예측하지 않는다.

이 문서는 **Journey Engine 논리의 주요 기준**이다.

## Tier C — ML/AI 고도화안

### `sources/project/04_journey_probability_ai_design.pdf`

- LightGBM Quantile → Monte Carlo 연결안.
- P10/P50/P90 등 분위수 예측.
- 현재 지연의 연속성/증분 모델링.
- Spark/Flink/Parquet 아키텍처 후보.

하지만 **LightGBM은 아직 필수 확정 기술이 아니다.**

Baseline 경험분포가 먼저며, 아래 평가에서 실제 개선이 확인될 때만 채택:

- Calibration
- Interval Coverage
- Pinball Loss
- Support가 적은 조합에서 안정성

## Tier D — 데이터 목록/참고

### `sources/project/05_subway_detail.pdf`

- 지하철 승하차/혼잡도/실시간 도착/실시간 위치 데이터 후보 목록.
- 30분 혼잡도는 **실시간 차량 혼잡도 아님**. Historical context로만 사용.
- 실시간 API가 과거 이력을 제공하지 않는 점을 강조.

## Tier E — 원래 RailOdds 기준

### `sources/project/06_subway_reliability_metric.pdf`

유지할 철학/설계 원칙:

- Point ETA가 아니라 신뢰구간/분포.
- `Prediction → Actual → Residual → Reliability`.
- raw 원본을 수정 없이 적재.
- source timestamp와 collector received_at을 둘 다 저장.
- 관측수가 적은 조합은 계층적 fallback.
- 리플레이는 부하 생성용이지 학습용 synthetic truth가 아님.
- calibration을 핵심 품질지표로 사용.
- Kafka/Flink/Spark를 쓸 경우 장애/백프레셔/처리량/정합성까지 증명.

단, 원 문서는 지하철 단일 모드 중심이므로 새 프로젝트의 최상위 제품 범위는 아니다.

## Tier F — 기획 품질 참고문서

### `sources/reference_quality/90_oss_shift_proposal.pdf`

내용을 복사하는 자료가 아니라 **기획 수준의 기준**.

특히 배울 점:

- 실제 Data Feasibility부터 확인.
- Data/Metric Contract를 먼저 고정.
- 한계/관찰범위를 명시.
- Distributed Proof를 benchmark, shuffle, correctness까지 연결.
- Final Acceptance Criteria가 재현 가능해야 함.

### `sources/reference_quality/91_service_plan_reference.md`

기획 구조의 기준:

- 범위/제외 원칙.
- 제품→UX→정책→데이터→인프라→품질/출시의 추적성.
- Gate 방식.
- Snapshot/version/과거 기록 불변 등의 계약화.

---

# 5. 현재 Data Feasibility 판정

> 상태는 Agent가 Spike 결과를 반영해 계속 갱신할 것.

| 영역 | 현재 판정 | 근거 / 다음 행동 |
|---|---|---|
| 서울 버스 Prediction 수집 | **VERIFIED / PASS** | 실제 753 PoC 있음 |
| 서울 버스 차량 식별 | **VERIFIED / PASS** | Prediction/Location `vehId` direct match 실측 |
| 서울 버스 Actual 도착 | **VERIFIED / PASS** | `stopFlag`/stop transition으로 arrival interval 구성 |
| 버스 Residual | **VERIFIED / PASS** | 여러 snapshot과 actual interval 매칭 성공 |
| 버스 Reliability 일반화 | **CONDITIONAL** | 1노선 1시간 PoC → 서울 전체 일반화 금지 |
| 버스 역사적 baseline | **AVAILABLE / VERIFY JOIN** | 서울시 구간별 평균 운행시간 자료 존재. 실시간 ID domain과 join Spike 필요 |
| 버스 실시간 혼잡/상태 | **AVAILABLE / VERIFY SEMANTICS** | API 필드 의미/갱신 품질 Spike 필요 |
| 지하철 실시간 ETA | **AVAILABLE / TO VERIFY** | 공식 API 존재. 실제 수집/중복/timestamp 검사 필요 |
| 지하철 실시간 위치 | **AVAILABLE / TO VERIFY** | 공식 API 존재. ETA와 열차번호/역/상태 join 검증 필요 |
| 지하철 Actual Ground Truth | **CRITICAL TO VERIFY** | Prediction→Actual 규칙을 실제 데이터로 아직 증명 안 함 |
| 지하철 과거 실시간 궤적 | **NOT PROVIDED** | 직접 수집이 필요 |
| 지하철 30분 혼잡도 | **SUPPORT ONLY** | 실시간 차량 혼잡도가 아니라 historical context |
| 이례상황 | **AVAILABLE / SUPPORT** | 현재 발생 중인 사건만 MVP에서 반영 |
| 버스+지하철 통합 경로 후보 | **API EXISTS / CRITICAL TO VERIFY** | 실제 응답, ID 연결, 최신성, mixed-mode route를 Spike |
| Journey Monte Carlo | **DESIGN FEASIBLE / TO IMPLEMENT** | 계산 계약부터 잠근 후 fixed corridor로 검증 |
| 미래 희귀 사고 발생확률 | **DROP FOR MVP** | 장기 incident history 부족 |
| 탑승 실패 확률 | **HOLD** | Ground Truth 부족. 사용자 사건 기반 Reforecast 우선 |
| TAGO | **DROP** | 서울시 only 원칙 + Seoul API가 Ground Truth에 더 적합 |

---

# 6. API / 데이터 레지스트리

## 6.1 Credential 상태

사용자가 2026-08-21 기준 필요한 API Key를 모두 취득했다고 알림.

**실제 key 문자열은 이 handoff/zip/repository에 포함하지 않는다.**

Secrets는 GitLab/Jenkins/EC2 Secret/환경변수로만 전달한다.

### 권장 Secret 이름

```dotenv
# Seoul Open Data
SEOUL_OPEN_API_KEY=
SEOUL_SUBWAY_REALTIME_KEY=

# data.go.kr - 실제 발급 형태에 맞게 설정
DATA_GO_BUS_ARRIVAL_KEY=
DATA_GO_BUS_POSITION_KEY=
DATA_GO_TRANSIT_PATH_KEY=
DATA_GO_BUS_ROUTE_KEY=
DATA_GO_BUS_STATION_KEY=

# Walking / access-time (P0-1 대상 아님 — Q3/D-040)
KAKAO_MAP_REST_API_KEY=   # BLOCKED: 카카오모빌리티 제휴 전용 API로 확인됨 (D-043)
TMAP_APP_KEY=             # 대안, 아직 미검증 (D-044)
```

만약 data.go.kr이 서비스별로 동일 키를 발급했다 하더라도 코드에서는 **논리 이름을 분리**해 두는 것을 권장한다.

## 6.2 공식 데이터 페이지

### Subway P0

1. **서울시 지하철 실시간 도착정보(일괄)**  
   https://data.seoul.go.kr/dataList/OA-15799/A/1/datasetView.do  
   대표 service: `realtimeStationArrival/ALL`  
   주요 후보: `subwayId`, `updnLine`, `statnId`, `statnNm`, `barvlDt`, `btrainNo`, `recptnDt`, `arvlMsg2`, `arvlCd`, `lstcarAt`.

2. **서울시 지하철 실시간 열차 위치정보**  
   https://data.seoul.go.kr/dataList/OA-12601/A/1/datasetView.do  
   실제 필드와 열차 상태 semantics는 Spike에서 저장 후 확인.

3. **서울교통공사 지하철 알림정보 현황**  
   https://data.seoul.go.kr/dataList/OA-22718/A/1/datasetView.do  
   현재 발생 중인 지연/사고/무정차/시간표 변경 등의 context.

4. **서울교통공사 지하철역 최단경로이동정보**  
   https://data.seoul.go.kr/dataList/OA-22724/A/1/datasetView.do  
   존재/응답/서비스 명세를 실제 키로 다시 확인할 것.

5. **서울 지하철 운행시각표 후보 데이터**  
   https://data.seoul.go.kr/dataList/OA-22522/L/1/datasetView.do  
   실제 최신 파일/컬럼/호선 범위 확인 필요.

### Bus P0

6. **서울특별시 버스도착정보조회 서비스**  
   https://www.data.go.kr/data/15000314/openapi.do  
   기존 PoC에서 `getArrInfoByRouteAll` 계열 사용.

7. **서울특별시 버스위치정보조회 서비스**  
   https://www.data.go.kr/data/15000332/openapi.do  
   기존 문서에서 `getBusPosByRtid` / `getBusPosByRtidList` 표기가 혼재하므로 **실제 승인 서비스 명세를 기준으로 확정**할 것.

8. **서울특별시 대중교통환승경로 조회 서비스**  
   https://www.data.go.kr/data/15000414/openapi.do  
   Bus+Subway mixed route candidate의 핵심 후보.

9. **서울특별시 노선정보조회 서비스**  
   https://www.data.go.kr/data/15000193/openapi.do  
   route master / stop order / section mapping.

10. **서울특별시 정류소정보조회 서비스**  
    https://www.data.go.kr/data/15000303/openapi.do  
    stop master / 좌표 / ID mapping.

### Bus historical/support

11. **서울시 노선별 정류장 구간별 평균 운행시간 정보**  
    https://data.seoul.go.kr/dataList/OA-21217/A/1/datasetView.do  
    공식 페이지 기준 1일×1시간 단위, route-stop section average travel time. OpenAPI는 최근 범위, 과거 파일도 존재.  
    **실시간 bus ID/section ID와 join 가능한지 Spike 필요.**

12. **서울시 노선별 정류장 구간별 총 승객수 정보**  
    https://data.seoul.go.kr/dataList/OA-21218/A/1/datasetView.do  
    historical/context 후보. 실시간 혼잡 Ground Truth로 취급하지 말 것.

### Subway support

13. `sources/project/05_subway_detail.pdf`에 정리된 후보:

- 수도권 지하철 역별 일별 시간대별 승하차
- 30분 단위 혼잡도
- 환승인원

Agent는 사용 전 **공식 페이지의 현재 제공기관/범위/갱신주기/식별자를 다시 확인**한다.

### Walking / Access Time (P0-1 대상 아님, Q3/D-040)

14. **카카오맵 길찾기(도보) API — BLOCKED (D-043).** 출발지→첫 승강장
    접근시간, 그리고 마지막 정류장/역→실제 목적지 도보 leg(Q2/D-039) 계산에
    쓰려 했으나, 실제 키로 호출한 결과 `HTTP 403 permission denied` —
    카카오모빌리티 제휴 계약이 필요한 partner-only API로 확인됨. IP 허용
    목록 설정과는 무관한 별개의 권한 문제. 제휴가 승인되기 전까지는 사용 불가.
15. **TMAP(SK Open API) 보행자 경로 API — VERIFIED / GO (D-045).**
    `POST https://apis.openapi.sk.com/tmap/routes/pedestrian` — 실제 키로
    호출해 GeoJSON 도보 경로(turn-by-turn, totalDistance/totalTime) 수신
    확인. **주의:** 앱키 생성과 상품 구독(신청)이 분리된 구조라, 앱키만
    받고 "보행자 경로 안내" 상품을 별도 구독하지 않으면 `403
    INVALID_API_KEY`가 남 — openapi.sk.com > Products > TMAP > TMAP 기능 >
    경로 > 경로 안내 > 보행자 경로 안내에서 구독 신청 필요(구독 후 동일
    키로 바로 동작, 재발급 불필요). WALK leg(access-time/final-walk,
    Q2/Q3·D-039/D-040)의 확정 provider. 이 데이터도 P0-1(서울시 데이터만)
    원칙의 대상이 아니라 별도 유틸리티다.

---

# 7. API Key / 호출 정책

## 7.1 Secret 보안

절대 금지:

- `.env` 실제 값을 Git commit
- 프론트엔드 번들에 key 포함
- README에 key 복사
- Agent 로그/테스트 결과에 full key 출력
- 호출 한도를 우회하기 위해 팀원 여러 키를 rotation

권장:

- local: `.env.local` (gitignore)
- GitLab CI/CD Variables
- Jenkins Credentials
- EC2 environment/secret file with restricted permission
- 로그에서는 `first4...last4`도 필요 없으면 출력하지 않음

## 7.2 호출량 원칙

버스 PoC 문서에서 API 호출 예산이 실제 병목으로 확인되었다.

따라서 Spike 단계에서 다음을 반드시 수치화한다.

- endpoint별 일 호출 상한
- 실제 승인 트래픽
- 5/10/15/30/60/90초 polling 시 하루 호출량
- route-wide query가 가능한지
- source timestamp가 새로 갱신되지 않았는데 동일 response가 반복되는 비율
- duplicate response를 네트워크 호출은 했지만 분석 sample로 dedupe 가능한지

**폴링 주기를 길게 하는 것은 호출량은 줄이지만 Actual arrival interval을 넓혀 Ground Truth 품질을 악화시킨다.**

따라서 단순히 interval을 늘리는 것으로 해결하지 않는다.

---

# 8. 가장 먼저 해야 할 Phase 0 Spike

> Agent는 전체 앱 구현 전에 아래 Spike를 실제 API로 수행해야 한다.

## Spike A — Bus Prediction→Actual 재현

목표:

기존 PoC를 팀 repository에서 다시 재현 가능한 형태로 만든다.

### 최소 작업

- 서울 버스 한 노선 선정.
- Arrival + Position API를 일정 시간 동시 수집.
- 원문 body + HTTP status + collector `received_at` 저장.
- source timestamp(`mkTm`, `dataTm`) 저장.
- `vehId` direct join rate 측정.
- Actual arrival interval 생성.
- Prediction snapshots와 Actual interval 매칭.
- Residual lower/mid/upper 생성.
- duplicate source snapshot 비율 측정.
- expired-on-receipt 비율 측정.

### 완료 기준

`raw sample → normalized → actual interval → residual`이 script 한 번으로 재현된다.

## Spike B — Subway Prediction→Actual Ground Truth

**현재 프로젝트 최우선 리스크 중 하나.**

목표:

실시간 도착 API와 위치 API에서 같은 열차를 식별하고 실제 역 도착 event를 신뢰할 만하게 만들 수 있는지 확인.

### 조사할 join 후보

- ETA `btrainNo` ↔ position `trainNo` 또는 실제 명세의 열차번호
- 호선
- 방향
- 종착역
- 현재역/다음역
- source timestamp

### Actual 후보

실제 API의 상태값을 관찰하여 다음 중 무엇이 가장 일관적인지 확인:

- 위치 API `도착` 상태 전이
- 도착 API `arvlCd=1`
- `전역출발→진입→도착→출발` sequence
- 두 API 교차 검증

### 반드시 결과에 기록

- 같은 열차 join 성공률
- 번호 재사용/변경/누락 사례
- 실제 도착 interval 폭
- source timestamp 반복/지연
- 이상 순서 event
- 호선별 차이

**Spike 결과 전에는 subway Ground Truth 규칙을 최종 문서에 확정하지 말 것.**

## Spike C — Mixed Route API

목표:

서울시 Bus+Subway 통합 환승경로 API가 실제 Main Use Case의 Route Candidate Provider로 쓸 수 있는지 검증.

### 검증

- 서울 안 출발/도착 좌표로 bus+subway 경로가 실제 반환되는가?
- 여러 route 후보를 주는가?
- 버스 route ID/stop ID가 Bus Arrival/Position master와 연결되는가?
- 지하철 station/line ID가 realtime subway API와 연결되는가?
- walking/transfer 정보가 어느 수준까지 들어오는가?
- 시간 정보가 static인지 실시간인지?
- endpoint의 갱신상태/오래된 ID 문제는 없는가?

### 실패 시 fallback

Journey Engine과 Route Provider를 분리한다.

MVP는 **고정/사전 정의 mixed corridor**를 입력받아 확률 계산에 집중할 수 있다.

## Spike D — Historical Bus Section ↔ Realtime Join

목표:

OA-21217 historical section average를 realtime bus segment와 연결할 수 있는지 확인.

검증:

- route ID domain
- stop ID domain
- section ID 유무
- 방향/순번
- 시간대 granularity
- missing rate
- one-to-one/one-to-many join

성공하면 cold-start baseline으로 활용 가능.

## Spike E — Fixed Mixed Journey End-to-End

위 데이터 Spike의 최소 결과를 가지고 딱 한 mixed corridor로 다음을 만든다.

```text
Subway leg
→ transfer/walk
→ Bus waiting/boarding
→ Bus leg
→ destination
```

ML 없이도 먼저 동작해야 한다.

출력:

- P50 arrival
- P90 arrival
- target-time on-time probability
- target probability를 만족하는 recommended departure
- transfer success probability(계산할 경우)
- support/fallback 설명

이 Spike가 성공해야 제품 가설을 GO로 판단할 수 있다.

---

# 9. 데이터 수집 계약 — 반드시 먼저 구현

## 9.1 Raw를 버리지 않는다

수집 시 schema를 너무 일찍 확정하여 정보가 사라지지 않게 한다.

Bronze에서는 최소:

```text
provider
api_name
request_id
requested_at
received_at
http_status
request_params_sanitized
raw_payload
raw_payload_hash
source_timestamp (파싱 가능할 때 nullable)
collector_version
error_code / error_body
```

을 보존한다.

**API key는 request_params에 저장 금지.**

## 9.2 Source time과 Receive time 구분

다음 둘을 절대 섞지 않는다.

- `source_generated_at`: 원천이 생성했다고 알려주는 시각 (`recptnDt`, `mkTm`, `dataTm` 등)
- `received_at`: 우리 Collector가 응답을 받은 시각

파이프라인 지연은 가능한 경우:

`received_at - source_generated_at`

으로 별도 보존.

## 9.3 Missing ≠ Empty ≠ Error

예:

- HTTP success인데 데이터 empty
- source field 누락
- HTTP error
- API business error body
- duplicate source snapshot

을 모두 구분.

## 9.4 Actual은 interval일 수 있음

Polling 기반 Ground Truth는 정확한 단일 timestamp가 아니라:

`(last_not_arrived_source_time, first_arrived_source_time]`

형태의 interval일 수 있다.

분석에서는 midpoint만 저장하지 말고:

```text
actual_lower
actual_upper
actual_midpoint
actual_uncertainty_sec
```

를 보존한다.

---

# 10. Canonical Data Contract 후보

> 아래는 최종 schema가 아니라 서로 다른 모드 데이터를 하나의 Journey Engine에 연결하기 위한 작업 가설.

## 10.1 PredictionSnapshot

```text
prediction_id
mode                 BUS | SUBWAY
vehicle_run_id
route_id
from_stop_or_station_id
predicted_target_id
source_generated_at
received_at
lead_time_sec
predicted_arrival_at
rank                  # first/second candidate if meaningful
raw_event_id
quality_flags[]
```

## 10.2 ActualArrivalInterval

```text
actual_id
mode
vehicle_run_id
target_stop_or_station_id
actual_lower_at
actual_upper_at
actual_mid_at
uncertainty_sec
observation_rule_version
raw_event_refs[]
quality_flags[]
```

## 10.3 ResidualEvent

```text
mode
vehicle_run_id
target_id
prediction_id
actual_id
lead_time_sec
residual_mid_sec
residual_lower_sec
residual_upper_sec
pipeline_lag_sec (nullable)
time_bucket
dow
support_context
feature_snapshot_version
```

Residual sign convention:

`Actual - Predicted`

- positive: 실제가 예측보다 늦음
- negative: 실제가 예측보다 빠름

## 10.4 LegDistribution

Journey Engine에게 Bus/Subway 내부 구현을 숨긴다.

```text
leg_id
mode                BUS | SUBWAY | WALK   # WALK 추가: Q2/D-039(최종 도보 포함), Q3/D-040(접근시간 포함)
from_id
to_id
query_time
journey_state       PRE_TRIP | WAITING | ON_BOARD
vehicle_run_id      nullable              # WALK leg는 null
distribution_repr   empirical/t_digest/quantiles/samples/model
p10_sec
p50_sec
p90_sec
sample_count
confidence_level
fallback_level
model_or_rule_version
context_snapshot
```

**WALK leg 참고 (D-039/D-040):** `distribution_repr`은 WALK leg에서 보통
`model`(카카오맵 등 라우팅 API가 반환한 단일 추정치)이 되며, 버스/지하철처럼
관측 기반 empirical distribution이 아닐 수 있다. `confidence_level`/
`fallback_level`로 이 차이를 명시해야 사용자에게 support 수준을 숨기지 않는다
(P0-4 원칙).

## 10.5 JourneyResult

```text
journey_id
calculated_at
route_candidate_version
current_journey_state
target_arrival_at
arrival_p10
arrival_p50
arrival_p90
on_time_probability
recommended_departure_at (when inverse query)
planned_transfer_success_probability nullable
recovery_probability nullable
simulation_count
support_summary
risk_factors[]
engine_version
```

---

# 11. Probability Contract

## 11.1 최종 확률

최종 정시 도착확률은 각 leg의 "지연 확률"을 단순 합산/곱셈하지 않는다.

한 simulation에서 사용자의 Journey를 끝까지 진행한다.

```text
for each simulation:
  sample/construct first waiting & travel
  move user through first leg
  determine transfer feasibility
  if missed:
      choose next feasible vehicle according to MVP rule
  continue remaining journey
  save final arrival timestamp
```

최종:

```text
P(on_time) = count(final_arrival <= target_arrival) / N
```

## 11.2 반드시 분리할 확률

- **계획한 환승/차량을 그대로 지킬 확률**
- **대체 차량까지 포함해 최종 목표시각 전에 도착할 확률**

환승 실패 = Journey 실패가 아니다.

## 11.3 권장 출발시각

사용자가 목표 confidence `p*`를 입력하면:

`P(arrival <= target | depart_time) >= p*`

를 만족하는 가장 늦은 출발시각을 탐색한다.

초기 구현은 binary search 또는 time grid로 충분하다.

## 11.4 이동 중 Reforecast

이미 완료된 구간은 확률변수가 아니다.

현재까지 실제로 확인된 상태는 condition으로 고정하고 **남은 불확실성만** 다시 계산한다.

따라서 여정이 진행될수록 일반적으로 distribution 폭이 좁아지는 것이 자연스럽다.

---

# 12. 상관관계 처리 — 이 프로젝트의 중요한 분석적 품질

## 12.1 Subway

잘못된 방식:

각 역 지연을 독립적으로 샘플링.

같은 열차가 앞 역에서 +120초인데 다음 역에서 갑자기 +5초처럼 비현실적일 수 있음.

후보:

1. **delay increment model**  
   `next_delay = current_delay + sampled_delta`

2. **block/bootstrap trajectory**  
   유사한 과거 train run의 지연 궤적을 통째로 샘플.

Spike에서 train_run 식별 가능성을 먼저 확인할 것.

## 12.2 Bus

도로 정체는 인접 구간에 공통 영향을 준다.

각 section travel time을 완전히 독립적으로 뽑으면 전체 분산을 과소평가할 수 있다.

후보:

- 같은 시간대/노선의 실제 trajectory block sample
- route congestion factor를 동일 simulation의 여러 section이 공유
- 과거 A→B 직접 분포가 충분하면 direct empirical distribution 사용
- 부족한 pair만 section composition

---

# 13. Baseline 먼저, ML은 비교 후

## 13.1 Baseline 후보

- empirical residual/travel-time distribution
- t-digest / quantile sketch
- time-of-day / DOW condition
- hierarchical fallback
  - stop/section/time
  - route/time
  - route overall
- historical bus section average + realtime correction

## 13.2 ML 후보

현재 팀 문서의 1순위 후보는 LightGBM Quantile Regression.

가능한 q:

- P10/P50/P90 최소
- 더 세밀한 quantile grid는 데이터/시간에 따라

하지만 다음 기준을 Baseline보다 개선해야 채택:

1. Calibration
2. Interval coverage
3. Pinball loss
4. Low-support cell 일반화
5. inference cost/operational simplicity

**MAE 하나로 승패를 결정하지 않는다.**

## 13.3 H100/AI 사용 원칙

H100 사용 가능 = 딥러닝 필요라는 뜻이 아니다.

핵심 확률값은 설명 가능한 통계/ML pipeline에서 산출한다.

Generative AI가 들어간다면 후보 역할은:

- 사용자에게 현재 확률 변화 이유를 근거 범위 내에서 자연어 설명
- 운영/분석 리포트 요약

Generative AI가 **확률 숫자를 임의 생성하면 안 된다.**

---

# 14. 아키텍처 — 현재는 Candidate

현재 자료를 가장 잘 연결하는 후보:

```text
Seoul APIs / Historical files
          ↓
     Collectors
          ↓
       Kafka
          ↓
   Flink Streaming
 - vehicle state
 - snapshot matching
 - actual detection
 - residual/realtime features
          ↓
  Bronze/Silver/Gold
 MinIO(S3)/Parquet
          ↓
 Spark batch / profiling / training
          ↓
 empirical artifacts / optional ML model
          ↓
 Reliability Serving
          ↓
 Journey Probability Engine
          ↓
 API / Postgres cache
          ↓
 Responsive Web App

Observability: Grafana + logs + Flink/Spark metrics
CI/CD: GitLab monorepo + Jenkins (candidate)
```

하지만 **G4 Distributed Feasibility 전에는 이 아키텍처를 최종 확정하지 않는다.**

## 14.1 왜 Kafka/Flink가 후보인가

버스 PoC에서 한 route의 state가:

`route/vehicle/target_stop`

단위로 자연스럽게 나뉘며 prediction state를 유지하다 actual event에서 flush한다.

Kafka를 raw replay source로 두면 collector와 계산을 분리하고 Flink 장애 후 replay가 가능하다.

## 14.2 Spark의 후보 역할

- historical files + residual logs batch preprocessing
- distribution/profile aggregation
- ML training dataset
- scale-out proof

실시간 scoring 자체가 무조건 Spark여야 하는 것은 아니다.

---

# 15. 분산처리 Proof 기준

프로젝트가 "분산 기술을 썼다"에서 끝나지 않게 다음을 남기는 것을 권장.

## Stream

- events/sec
- p50 / p99 processing latency
- Kafka consumer lag
- Flink checkpoint duration
- state size growth
- backpressure
- TaskManager 또는 broker 장애 시 recovery
- duplicate/loss count

## Batch

- input size
- 1 / 2 / 4 worker runtime
- actual task participation
- shuffle read/write
- spill
- skew/straggler
- 최소 2개 optimization A/B
- optimization 전후 logical output checksum/row-count equality

## Replay

리플레이/증폭 데이터는 **성능부하 생성용**.

**학습 데이터로 사용하지 않는다.**

이 구분을 문서/발표에서 반드시 명시한다.

---

# 16. Web App UX 상태 계약 후보

## State 1 — PRE_TRIP

사용자 입력:

- 출발지
- 목적지
- 목표 도착시각
- 목표 확률(optional)

출력:

- route
- P50/P90 arrival
- target on-time probability
- recommended departure
- 주요 risk leg

## State 2 — WAITING / TRANSFER

추가 context:

- 현재 정류장/역
- 기다리는 실제 차량 후보
- realtime ETA/position
- current route condition

초기보다 distribution이 좁아지는 것을 UX로 보여준다.

## State 3 — ON_BOARD

추가 context:

- vehicle_run_id
- current position/segment
- waiting uncertainty 제거

남은 travel-time distribution 중심.

## State 4 — USER EVENT

예:

- 버스를 보냄
- 차량 놓침
- 사용자가 실제 탑승 완료를 확인

이 이벤트를 state transition으로 저장하고 즉시 Reforecast.

---

# 17. 아직 고정하면 안 되는 항목

Agent는 아래를 "최종 결정"처럼 작성하지 말 것.

1. Subway Actual arrival 판정 규칙 — Spike 필요
2. LightGBM 필수 여부 — Baseline 비교 필요
3. 모든 서울 노선 실시간 full coverage — 호출량/운영키 승인량 필요
4. 통합 환승경로 API가 production-grade route provider라는 주장 — 실제 호출/ID join 필요
5. 실시간 지하철 혼잡 — 현재 자료의 30분 혼잡은 historical context
6. 버스 승차 실패 probability — Ground Truth 부족
7. 희귀 사고 future probability — MVP 제외
8. ~~최종 목적지의 정의~~ — **PM 결정 완료 (D-039, Q2): 마지막 도보(약속 장소)까지 포함**
9. 환승 횟수 제한 — 현재 문서 1회는 과거 4주 MVP 가정. 이번 일정에서 재평가 필요
10. EC2 2대의 정확한 역할/cluster topology — infra 담당자와 benchmark 목표에 따라 확정

---

# 18. Phase 0에서 PM에게 결정 요청해야 하는 질문

Agent는 기술적으로 답할 수 없는 아래 결정이 필요할 때 PM에게 물어본다.

> **Q1~Q4 전부 PM 답변 완료 (2026-08-22).** 근거와 세부 사항은
> `05_DECISION_LOG.md` D-030(Q1), D-039(Q2), D-040(Q3), D-041(Q4) 참고.

## Q1. Demo Corridor — 결정됨 (D-030)

서울 내에서 반드시 재현할 **대표 mixed-mode route** 1~2개를 정해야 한다.

선정 기준:

- subway + bus 포함
- API coverage 안정적
- 환승이 명확
- 실제 수집/현장검증 가능
- 너무 긴 광역구간 피함

**PM 답변: 삼청동 ↔ 역삼역** (도착지는 역삼역으로 지정, 출발지는 무관). 3호선
안국역→교대역 subway leg, 총 소요 50분. Spike E에서 subway leg·bus leg 모두
100% Ground Truth join 확인됨 (D-034, D-038).

## Q2. Arrival Boundary — 결정됨 (D-039)

MVP의 "도착"을 어디까지로 볼지.

후보:

- 목적 버스정류장/지하철 승강장 도착
- 목적 역/정류장 + 사용자가 입력한 마지막 보행시간
- 경로 API walking leg까지 포함

Main Use Case는 실제 약속장소까지를 원하지만 데이터 근거가 약해지면 Transit boundary를 먼저 고정할 수 있다.

**PM 답변: 마지막 도보(약속 장소까지)를 포함한다.** 목적 정류장/승강장 도착이
아니라 실제 약속 장소 도착까지가 "도착"의 정의다. Journey 구성은
`... → 목적 정류장/역 도착 → WALK leg → 실제 목적지`. `LegDistribution`/
`JourneyResult` 계약의 `mode` enum(`BUS | SUBWAY`)에 `WALK`를 추가해야 한다
(섹션 10.4 참고).

## Q3. Access Time — 결정됨 (D-040)

출발지→첫 승강장/정류장까지 시간을:

- 사용자 직접 입력
- route provider walking time
- 고정 demo value

중 무엇으로 할지.

**PM 답변: 카카오맵 등 실제 지도/경로 API로 계산한 값을 쓴다.** 사용자 입력이나
고정값이 아니라 실제 지도 앱처럼 계산된 도보/접근 시간을 사용해야 한다는 판단.

> **중요 — P0-1과의 관계:** "서울시 데이터만" 원칙(P0-1)은 버스/지하철 등
> **핵심 교통 reliability 데이터**의 공급자에 적용되는 것이며, 도보/경로 계산용
> 지도 API(카카오맵 등)는 이 원칙의 대상이 아닌 별도 유틸리티로 취급한다.
>
> **업데이트: 카카오맵은 BLOCKED (D-043), TMAP으로 확정 (D-045).** 카카오는
> 키 발급 후 실제 호출 결과 `403 permission denied` — 카카오모빌리티 제휴
> 계약이 필요한 partner-only API였다. 대안으로 확인한 **TMAP(SK Open API)
> 보행자 경로 API**는 실제 키로 GeoJSON 도보 경로 수신까지 확인 완료 — WALK
> leg의 provider로 확정. 섹션 6 API 레지스트리 참고.

## Q4. Support geography — 결정됨 (D-041)

"서울시 데이터만"의 의미를

- 제공기관 기준
- 지리적 서울시 행정구역 기준

중 어디까지 엄격히 적용할지 최종 확인.

**PM 답변: 제공기관 AND 지리적 행정구역, 둘 다 만족해야 한다** (교집합이지
합집합이 아님). 버스/지하철 핵심 데이터 중 서울시가 제공기관이 아닌 데이터가
불가피하게 필요하면 예외적으로 쓸 수 있으나, PM은 **MVP 범위를 안전하게 좁게
유지**하고 싶다는 의사를 명확히 함 — 범위를 넓히는 방향의 판단은 신중하게.
지금까지 검증된 API·Demo Corridor는 이미 이 기준을 만족한다.

---

# 19. 권장 일정 (PM 승인 전 제안)

## 8/21 ~ 8/24 — Phase 0A: API Spike / 수집 시작

- Secrets 세팅
- Bus 재현
- Subway Ground Truth
- Mixed route API
- raw collector 최소 배포
- 24h 수집 시작

**새 기능보다 수집이 먼저.**

## 8/25 ~ 8/31 — Phase 0B/G1: Data Contract

- Bronze/Silver schema
- ID mapping
- quality flags
- fixed demo corridor
- Baseline distributions
- Data Feasibility Report

## 9/1 ~ 9/7 — G2: Probability Engine

- fixed mixed journey E2E
- empirical/t-digest baseline
- Pre-trip + Reforecast
- support/fallback

## 9/8 ~ 9/14 — Product Integration / optional ML

- Web UI 연결
- LightGBM baseline comparison
- Journey state UX
- route coverage 확대

## 9/15 ~ 9/21 — Distributed Proof / QA

- 1/2/4 worker
- failure injection
- replay benchmark
- calibration evaluation
- observability

## 9/22 ~ 9/25 — Scope Freeze / Acceptance

- 신규 기능 동결
- 재현성
- acceptance checklist
- 문서/데모 데이터 freeze

## 9/26 ~ 9/28 — Final

- Demo rehearsal
- backup scenario
- final report/presentation

---

# 20. Phase 0 Acceptance Criteria

다음이 모두 충족되기 전 최종 서비스기획서/아키텍처를 확정하지 않는다.

### API

- [ ] 모든 credential이 repo 밖에서 정상 로드됨
- [ ] Bus arrival 실제 호출 성공
- [ ] Bus position 실제 호출 성공
- [ ] Subway arrival 실제 호출 성공
- [ ] Subway position 실제 호출 성공
- [ ] Mixed route 실제 호출 성공 또는 명시적 fallback 결정

### Data

- [ ] raw payload 보존
- [ ] source time / received time 분리
- [ ] duplicate/empty/error 규칙
- [ ] Bus actual interval 재현
- [ ] Subway actual rule 검증
- [ ] ID mapping 표
- [ ] historical bus section join 결과

### Probability

- [ ] fixed mixed route의 travel-time distribution 생성
- [ ] `P(on_time)` 계산
- [ ] recommended departure 역산
- [ ] transfer/miss recovery 처리
- [ ] current state를 반영한 Reforecast

### Honesty

- [ ] synthetic replay를 학습 truth로 사용하지 않음
- [ ] support 부족을 숨기지 않음
- [ ] 1 route PoC를 서울 전체 정확도로 표현하지 않음
- [ ] historical congestion을 realtime 혼잡으로 표현하지 않음

---

# 21. Agent의 작업 규칙

1. `docs/01_PROJECT_HANDOFF.md`를 최상위 working baseline으로 읽는다.
2. 실제 Spike 결과가 나오면 `docs/05_DECISION_LOG.md`에 Evidence와 함께 기록하고 handoff를 갱신한다.
3. 팀 PDF의 내용과 실제 API가 충돌하면 **실제 API + 공식 최신 명세**를 우선한다.
4. 단, silently 수정하지 말고 "문서 주장 vs 실제 결과"를 기록한다.
5. secret은 절대 출력/commit하지 않는다.
6. 실제 API 호출 전 예상 일 호출량을 계산한다.
7. raw response sample을 sanitization하여 저장한다.
8. 통합 앱을 먼저 만들지 말고 **fixed corridor vertical slice**부터 만든다.
9. ML 이전에 empirical baseline을 만든다.
10. 최종 숫자/데모는 illustrative mock이 아니라 실제 pipeline result를 사용한다.

---

# 22. 권장 Repository 구조 후보

현재 GitLab monorepo를 전제로 한 예시. 기존 repo가 있다면 무리해서 맞추지 말고 ADR로 조정.

```text
/
├─ docs/
│  ├─ handoff/
│  ├─ decisions/
│  ├─ data-contract/
│  ├─ api-spikes/
│  └─ architecture/
├─ apps/
│  ├─ web/
│  └─ api/
├─ services/
│  ├─ collector-bus/
│  ├─ collector-subway/
│  ├─ stream-processing/
│  └─ journey-engine/
├─ analytics/
│  ├─ baseline/
│  ├─ spark/
│  └─ models/
├─ infra/
│  ├─ docker/
│  ├─ jenkins/
│  └─ observability/
├─ contracts/
│  ├─ schemas/
│  └─ examples/
├─ data/
│  └─ samples/           # sanitized only
└─ scripts/
   └─ spikes/
```

---

# 23. 최종 기획서가 나중에 가져야 할 수준

Phase 0가 통과되면 최종 기획서는 아래 축을 하나의 추적 가능한 논리로 연결해야 한다.

1. Executive Summary / 현재 판단
2. Problem & Decision Context
3. Product Scope / In-Out
4. Main Use Case / Journey State
5. Data Feasibility
6. Observation / Timestamp / Identity Contract
7. Prediction-Actual-Residual Contract
8. Bus Reliability
9. Subway Reliability
10. Journey Probability Mathematics
11. Correlation / Bootstrap / Conditional update
12. Baseline vs ML validation
13. Web Product Experience
14. Distributed Architecture
15. Storage / Partition / State / Replay
16. Scale-out / Failure / Correctness
17. Quality Gates
18. WBS / Team / Risk / Scope Cut
19. Final Acceptance Criteria
20. Demo Narrative
21. Limitations / Honesty Contract

**"문서가 길다"가 목표가 아니라, 사용자 출력 → 계산 → 데이터 → 파이프라인 → 검증까지 역추적 가능한 것이 목표다.**

---

# 24. 현재 가장 중요한 한 문장

> 지금 당장 가장 먼저 해야 할 일은 전체 서비스를 만드는 것이 아니라, **서울 버스·지하철의 실제 Prediction→Actual 계약과 mixed route ID 연결을 재현 가능한 Spike로 증명하면서 Raw 데이터를 축적하는 것**이다.
