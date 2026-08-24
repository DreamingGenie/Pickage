# Journey Reliability IA & 화면 정의서 — v0.2

> **문서 목적**: UX/UI, Frontend, Backend, Data, QA가 추가 해석 없이 화면·route·접근조건·상태·데이터·CTA·예외·복구를 구현하고 검증할 수 있도록 한다.  
> **문서 지위**: Service Plan의 하위 IA/Screen Contract 정본  
> **정본 파일명**: `IA_SCREEN_SPEC_260824_v0.2.md`  
> **버전**: v0.2 — 두 제품 기능의 entry/input/result 완전 분리  
> **기준일**: 2026-08-24  
> **대상**: 독립형 Mobile-first PWA / 로그인 없는 Minimum Release  
> **상위 기준**: `SERVICE_PLAN_260824_v0.2.md`  
> **하위 구현 기준**: `REQUIREMENTS_SPEC_260824_v0.2.md`

---

## 문서 네비게이션

**정본 문서 바로가기**

- [Service Plan](SERVICE_PLAN_260824_v0.2.md)
- **IA / Screen Spec**
- [Requirements Spec](REQUIREMENTS_SPEC_260824_v0.2.md)
- [Decision Sheet](DECISION_SHEET_260824_v0.2.md)

**이 문서 안에서 이동**

- [문서 사용법과 IA 단위](#문서-사용법과-ia-단위)
- [IA 핵심 결정](#ia-핵심-결정)
- [전체 Information Architecture](#전체-information-architecture)
- [Route Inventory와 Guard](#route-inventory와-guard)
- [Global Shell과 Navigation](#global-shell과-navigation)
- [공통 데이터·표시 계약](#공통-데이터표시-계약)
- [Global State Matrix](#global-state-matrix)
- [SCR-00 — Service Home](#scr-00-service-home)
- [SCR-01 — Departure Recommendation Input](#scr-01-departure-recommendation-input)
- [SCR-02 — Departure Recommendation Result](#scr-02-departure-recommendation-result)
- [SCR-07 — Leave-now Forecast Input](#scr-07-leave-now-forecast-input)
- [SCR-08 — Leave-now Forecast Result](#scr-08-leave-now-forecast-result)
- [SCR-03 — Future GPS Journey Tracking](#scr-03-future-gps-journey-tracking)
- [SCR-04 — Future Auto-Reforecast](#scr-04-future-auto-reforecast)
- [SCR-05 — Evidence Detail](#scr-05-evidence-detail)
- [SCR-06 — Share Snapshot](#scr-06-share-snapshot)
- [State namespace × Screen State](#state-namespace-screen-state)
- [Error Taxonomy와 Recovery UX](#error-taxonomy와-recovery-ux)
- [Mobile-first PWA Contract](#mobile-first-pwa-contract)
- [Accessibility Contract](#accessibility-contract)
- [Analytics Contract](#analytics-contract)
- [Screen ↔ Feature ↔ REQ/BR Traceability](#screen-feature-reqbr-traceability)
- [Development Handoff Checklist](#development-handoff-checklist)
- [QA Acceptance Scenarios](#qa-acceptance-scenarios)
- [Open Implementation Decisions](#open-implementation-decisions)
- [정본 정합성 규칙](#정본-정합성-규칙)

## 문서 사용법과 IA 단위

### IA가 정의하는 것

v0.2 Minimum Release는 **두 개의 독립 사용자 Journey**를 정의한다. 공통 Home/Evidence/Share를 제외하면 두 기능은 입력과 결과 화면을 공유하지 않는다.

| 단위 | 정의 | v0.2 범위 |
|---|---|---|
| 공통 entry | 기능 선택 | SCR-00 |
| Departure flow | 사전 계획용 | SCR-01 Input → SCR-02 Result |
| Leave-now flow | 지금 판단용 | SCR-07 Input → SCR-08 Result |
| Shared detail | analysisType별 근거/공유 | SCR-05, SCR-06 |
| Future reserved | GPS 자동 추적 연구 | SCR-03, SCR-04 |

### 화면 ID 정책

- 기존 SCR-01/02는 v0.1의 입력/통합결과에서 **Departure Recommendation 전용**으로 좁힌다.
- B를 억지로 SCR-02에 유지하지 않고 신규 SCR-07/08을 추가한다.
- SCR-00은 Service Home 신규 entry다.
- SCR-03/04는 Future reserved다.
- SCR-05/06은 `analysisType`에 따라 한 기능의 데이터만 렌더링한다.

### Source-of-truth 경계

| 질문 | 정본 |
|---|---|
| 왜 두 기능이 독립적인가 | Service Plan v0.2 |
| 화면/route/CTA/state | IA v0.2 |
| API/Entity/Data/Acceptance | Requirements v0.2 |
| 실제 검증 사실·제품 결정 history | Decision Sheet v0.2 |

## IA 핵심 결정

| ID | 결정 | 구현 결과 |
|---|---|---|
| IA-001 | selected structural route 하나만 분석 | reliability ranking 없음 |
| IA-002 | **두 기능은 Home에서 별도 CTA로 선택** | 통합 분석 CTA 금지 |
| IA-003 | Departure/Leave-now는 별도 input route | 입력 폼 자동 결합 금지 |
| IA-004 | Departure/Leave-now는 별도 result route | 한 화면 A+B 카드 금지 |
| IA-005 | 한 기능은 다른 기능 result/session을 prerequisite로 요구하지 않음 | 독립 direct entry 가능 |
| IA-006 | Departure는 historical-only | realtime badge/feature 없음 |
| IA-007 | Leave-now는 departAt=now snapshot | current context coverage 표시 |
| IA-008 | P50은 평균이 아님 | help text로 의미 고정 |
| IA-009 | Evidence는 analysisType-scoped | 사용하지 않은 기능 evidence 미표시 |
| IA-010 | Share는 한 기능 result만 | mixed metric payload 금지 |
| IA-011 | direct URL/refresh는 동일 analysisType snapshot 복구 | 다른 기능으로 변환 금지 |
| IA-012 | owner capability는 analysis result/evidence/share 보호 | live mutation 없음 |
| IA-013 | historical/realtime freshness 분리 | realtime은 Leave-now만 |
| IA-014 | Route B는 internal QA 전용 | public UI 미노출 |
| IA-015 | offline은 각 result not-current read-only | auto Leave-now refresh 없음 |
| IA-016 | origin 위치 권한은 explicit one-shot | background GPS 없음 |
| IA-017 | AI는 Leave-now leg distribution 보정 | final probability 직접 AI copy 금지 |
| IA-018 | SCR-03/04 manual tracking은 RETIRED_FROM_MR | route/CTA/state 없음 |
| IA-019 | Future tracking은 GPS/location 자동 추론 연구 | 구현 claim 금지 |
| IA-020 | unsupervised regime은 optional feature | direct delay weight 금지 |
| IA-021 | product split은 UI만이 아니라 API/result 의미까지 유지 | combined response 렌더 금지 |

## 전체 Information Architecture

```text
SCR-00 Service Home  /
  ├─ CTA: 출발 시간 추천
  │    ↓
  │  SCR-01 Departure Recommendation Input  /departure
  │    ↓ submit
  │  SCR-02 Departure Recommendation Result /departure/{analysisId}/result
  │    ├─ Departure P50 / P90
  │    ├─ Evidence → SCR-05
  │    └─ Share → SCR-06 (Should)
  │
  └─ CTA: 도착 가능성 계산
       ↓
     SCR-07 Leave-now Forecast Input  /arrival-now
       ↓ submit
     SCR-08 Leave-now Forecast Result /arrival-now/{analysisId}/result
       ├─ P(on_time) / Arrival P50 / Arrival P90
       ├─ realtimeContextCoverage
       ├─ Evidence → SCR-05
       └─ Share → SCR-06 (Should)

SCR-05 Evidence Detail  /analysis/{analysisId}/evidence
SCR-06 Share Snapshot   /share/{token}
SCR-03 / SCR-04         FUTURE_GPS_RESEARCH reserved
```

### Main Journey 전이

| From | Trigger | To | 불변조건 |
|---|---|---|---|
| SCR-00 | `출발 시간 추천` | SCR-01 | Leave-now 계산 실행 없음 |
| SCR-00 | `도착 가능성 계산` | SCR-07 | Departure 계산 실행 없음 |
| SCR-01 | `추천 출발 시간 계산` | SCR-02 | Departure request/result만 생성 |
| SCR-07 | `지금 출발 시 도착 가능성 계산` | SCR-08 | Leave-now request/result만 생성 |
| SCR-02/08 | Evidence | SCR-05 | parent analysisType 유지 |
| SCR-02/08 | Share | SCR-06 | parent analysisType의 metric만 snapshot |
| SCR-02/08 | `다른 기능 사용` | SCR-00 | 자동 결과 변환/continuation 없음 |

두 결과 화면 사이 direct 자동 transition은 없다.

## Route Inventory와 Guard

| Route | Screen | 접근 조건 | 직접 접근/새로고침 |
|---|---|---|---|
| `/` | SCR-00 Service Home | 없음 | 항상 가능 |
| `/departure` | SCR-01 Planning Input | 없음 | 항상 가능 |
| `/departure/{analysisId}/result` | SCR-02 Planning Result | type=DEPARTURE_RECOMMENDATION + owner | 동일 snapshot 복구 |
| `/arrival-now` | SCR-07 Leave-now Input | 없음 | 항상 가능 |
| `/arrival-now/{analysisId}/result` | SCR-08 Leave-now Result | type=LEAVE_NOW_FORECAST + owner | 동일 snapshot 복구; current 자동 갱신 금지 |
| `/analysis/{analysisId}/evidence` | SCR-05 | parent result access | parent type 유지 |
| `/share/{token}` | SCR-06 | valid token | public single-function snapshot |

잘못된 analysisType으로 result route에 접근하면 다른 화면으로 coercion하지 않고 동일한 not-found/recovery semantics를 사용한다.

### Guard 우선순위

1. route parameter / expected analysisType
2. owner capability(`/share` 제외)
3. resource 존재
4. result eligibility
5. 해당 기능의 evidence 상태

### URL과 개인정보

`analysisId`는 locator일 뿐 credential이 아니다. exact coordinate/token/secret/GPS trace를 URL에 넣지 않는다.

## Global Shell과 Navigation

### Shell hierarchy

```text
AppShell
├─ Header: Brand / Home
├─ Main
├─ Global Feedback
├─ PWA Runtime Region
└─ Footer / policy links
```

### Header / Navigation

- Home에서는 두 기능 CTA가 동등한 1차 선택지다.
- Departure flow header에는 `출발 시간 추천` context만 표시한다.
- Leave-now flow header에는 `도착 가능성 계산` context만 표시한다.
- 결과 화면의 `다른 기능 사용`은 Home으로 돌아가 새 request를 시작한다.
- 한 result 화면에서 다른 기능 metric을 preview 카드로 보여주지 않는다.
- `Live`, `이동 시작`, event mutation navigation은 없다.

### Global feedback

provider/network/input 오류는 현재 기능 context 안에서 처리한다. Leave-now가 historical-only로 축소되면 persistent limitation으로 표시한다.

## 공통 데이터·표시 계약

### Common Analysis Envelope

두 기능은 공통 envelope를 공유할 수 있지만 metric payload는 분리한다.

| Field | Required | 규칙 |
|---|---|---|
| `analysisId` | yes | locator |
| `analysisType` | yes | `DEPARTURE_RECOMMENDATION` 또는 `LEAVE_NOW_FORECAST` |
| `routeCandidateId` | internal | selected route |
| coverage/selectedRoute/canonicalMapping | yes | 기존 분리 축 유지 |
| `targetArrivalAt` | yes | 기능별 request target |
| `historicalModelCoverage` | yes | shared baseline coverage |
| `validationScope` / `confidence` | yes | probability와 분리 |
| `calculatedAt` | yes | result 생성시각 |
| `limitations[]` | array | 실제 기능 limitation만 |

### Departure Result View Model — SCR-02

| Field | 규칙 |
|---|---|
| `departureP50At` | nullable; Departure metric |
| `departureP90At` | nullable; Departure metric |
| `historicalArtifact` | computed 시 required |
| `metricEligibility.departure*` | 독립 판정 |

**금지 필드**: `departAt`, `arrivalP50At`, `arrivalP90At`, `onTimeProbability`, `realtimeContextCoverage`, realtimeFeatureCategories, realtime model provenance.

### Leave-now Result View Model — SCR-08

| Field | 규칙 |
|---|---|
| `departAt` | required; `calculatedAt≈now` |
| `arrivalP50At` / `arrivalP90At` | nullable |
| `onTimeProbability` | nullable, null≠0 |
| `realtimeContextCoverage` | FULL/PARTIAL/NONE |
| `realtimeFeatureCategories[]` | 실제 사용 category만 |
| `modelProvenance` | nullable |
| `metricEligibility.arrival*/onTime` | 독립 판정 |

**금지 필드**: `departureP50At`, `departureP90At`.

### 숫자 formatting / copy

| 기능 | Metric | Label |
|---|---|---|
| Departure | P50 | `보통은 {time}까지 출발` |
| Departure | P90 | `여유 있게는 {time}까지 출발` |
| Leave-now | P(on_time) | `{target}까지 도착할 가능성` |
| Leave-now | Arrival P50 | `지금 출발 시 보통 {time} 도착` |
| Leave-now | Arrival P90 | `늦는 경우까지 보면 {time} 정도` |

P50을 평균으로 정의하지 않는다. historical-only Leave-now에 `실시간 반영` copy를 사용하지 않는다.

## Global State Matrix

상태는 **현재 analysisType 내부**에서만 합성한다. 다른 기능 상태를 함께 보여주지 않는다.

| State | Departure | Leave-now |
|---|---|---|
| ANALYZING | route+historical/candidate search | route+historical+realtime context calculation |
| FRESH | eligible Departure metrics | eligible Leave-now metrics |
| HISTORICAL_ONLY | N/A — normal historical design | realtime none인 fallback |
| PARTIAL_REALTIME | N/A | 일부 realtime 사용 |
| STALE | historical artifact age limitation | stale realtime 제외/재계산 |
| PARTIAL_MODEL / INSUFFICIENT | 기능별 limitation | 기능별 limitation |
| NOT_COMPUTED | Departure null | Leave-now null |
| OFFLINE_SNAPSHOT | not-current planning snapshot | not-current now snapshot; current 표현 금지 |

`realtimeContextCoverage`는 Leave-now에만 존재한다.

## SCR-00 — Service Home

### 목적

사용자가 자신의 시점과 질문에 맞는 기능을 먼저 선택한다.

```text
SCR-00
├─ Intro: 목표시간을 지키기 위한 두 가지 도구
├─ Feature Card 1: 출발 시간 추천
│  ├─ `약속 전에 미리 계획`
│  └─ CTA `출발 시간 추천`
└─ Feature Card 2: 도착 가능성 계산
   ├─ `지금 출발해도 되는지 확인`
   └─ CTA `도착 가능성 계산`
```

두 CTA를 하나의 `계산하기` 버튼으로 합치지 않는다.

## SCR-01 — Departure Recommendation Input

### 목적·접근·종료

미래 일정에 대한 출발시간 추천 request를 만든다. 전날/수시간 전 사용을 정상 시나리오로 지원한다.

### Component hierarchy

```text
SCR-01
├─ Header: 출발 시간 추천
├─ Origin
├─ Destination
├─ Target Arrival Date/Time
├─ Historical planning notice
└─ CTA: `추천 출발 시간 계산`
```

현재 위치 one-shot은 origin convenience로만 제공하며 realtime 교통 반영을 암시하지 않는다.

### 입력 계약

origin, destination, future `targetArrivalAt`; planning supported horizon 안이어야 한다. targetReliability 없음.

### Analytics

`departure_input_view`, `departure_recommendation_submit`, `departure_recommendation_success/failed`.

## SCR-02 — Departure Recommendation Result

### 목적

Departure P50/P90과 historical 근거만 표시한다.

```text
SCR-02
├─ Target Header
├─ Primary Recommendation
│  ├─ Departure P50
│  └─ Departure P90
├─ Selected Route Timeline
├─ Historical Basis Summary
├─ Limitation / Validation
└─ Actions: 새로 계산 / 입력 수정 / 근거 보기 / 공유 / 다른 기능 사용
```

### 금지

- P(on_time), Arrival P50/P90 카드
- realtime context badge/current vehicle/congestion
- `지금 출발하면` copy

### Acceptance

Departure-only response가 그대로 렌더링되며 다른 기능 metric placeholder도 생성하지 않는다.

## SCR-07 — Leave-now Forecast Input

### 목적·접근·종료

실제 출발 직전의 독립 Leave-now request를 만든다. Departure result가 없어도 직접 접근 가능하다.

```text
SCR-07
├─ Header: 도착 가능성 계산
├─ Origin + Current Location(one-shot)
├─ Destination
├─ Target Arrival Date/Time
├─ `지금 {currentTime} 출발 기준` 안내
└─ CTA: `지금 출발 시 도착 가능성 계산`
```

submit 시 server `calculatedAt`을 기준으로 `departAt≈now`를 고정한다. 클라이언트가 임의 과거/미래 departAt을 지정하지 않는다.

### Analytics

`leave_now_input_view`, `leave_now_forecast_submit`, `leave_now_forecast_success/failed`.

## SCR-08 — Leave-now Forecast Result

### 목적

지금 출발 기준 P(on_time), Arrival P50/P90와 realtime context 사용 범위를 표시한다.

```text
SCR-08
├─ `지금 {departAt} 출발 기준`
├─ P(on_time)
├─ Arrival P50
├─ Arrival P90
├─ Realtime Context: FULL/PARTIAL/HISTORICAL_ONLY
├─ Selected Route Timeline
├─ Evidence Summary
└─ Actions: 새로 계산 / 입력 수정 / 근거 보기 / 공유 / 다른 기능 사용
```

### 금지

- Departure P50/P90
- planning 추천 CTA
- 이전 Departure result를 기준값으로 표시

### Freshness

화면 복귀만으로 current forecast가 되지 않는다. `새로 계산`을 눌러야 새 departAt/realtime snapshot을 만든다.

### Acceptance

Departure Recommendation을 사용한 적 없는 새 세션에서도 Leave-now flow가 완주된다.

## SCR-03 — Future GPS Journey Tracking

**Status: `FUTURE_GPS_RESEARCH / NOT_IN_MINIMUM_RELEASE`**

2026-08-23의 수동 `탑승했어요/버스를 보내요/하차했어요/환승 완료` UI 계약은 퇴역한다. MR에는 `/live` route, event CTA, active leg state, polling lifecycle을 구현하지 않는다.

향후 연구 시 원칙:

- 명시적 사용자 동의와 privacy/battery 정책 필요
- GPS/location과 transit context로 상태를 **자동 추론**하는 방향 우선
- 지하/도심 위치 품질, boarding/alighting false positive/negative를 독립 검증
- 검증 전에는 자동 tracking이나 정확도 claim 금지
- 사용자가 계속 버튼을 눌러 상태를 진행시키는 UX를 기본 fallback으로 설계하지 않음

---

## SCR-04 — Future Auto-Reforecast

**Status: `FUTURE_GPS_RESEARCH / NOT_IN_MINIMUM_RELEASE`**

SCR-03 자동 상태 추론이 별도 Gate를 통과한 이후에만 남은 여정 automatic reforecast를 설계한다. 현재 Requirements/API/State에는 구현 가능한 Reforecast contract를 두지 않으며, 기존 수동 event 기반 before/after overlay는 retired history로만 취급한다.

## SCR-05 — Evidence Detail

### 목적·접근

`analysisType`에 따라 **한 기능의 근거만** 보여준다. Evidence component는 공유하지만 두 기능의 metric/evidence를 한 페이지에서 합산하지 않는다.

### Information hierarchy — Departure Recommendation

```text
Scope / Route / Target
Historical Artifact / data window / bucket / support / fallback
Departure candidate search config / validation
Route Leg Evidence
```

### Information hierarchy — Leave-now Forecast

```text
Scope / Route / Target / departAt
Historical Baseline
Realtime Context FULL/PARTIAL/NONE
Used feature categories + freshness
AI/Model Provenance when used
Route Leg Evidence
```

`analysisType` 불일치 데이터가 payload에 있으면 contract error로 취급하고 렌더링하지 않는다.

### Leg evidence required/nullable

기존 source/semantics/support/fallback/coordinate/validation 필드를 유지하고 다음을 추가한다.

- `analysisType` (`DEPARTURE_RECOMMENDATION` / `LEAVE_NOW_FORECAST`)
- `historicalArtifactVersion`, `dataEndAt`, grouping/bucket scope
- Leave-now일 때만 `realtimeContextCoverage`
- Leave-now일 때만 `realtimeFeatureCategories[]`, feature source/freshness
- `modelKey/modelVersion/featureSchemaVersion/fallbackUsed`
- feature availability Gate status; **unverified leading vehicle/congestion/headway를 사용했다고 표시 금지**

### User-facing leg copy 예

- A: `과거 유사 요일·시간대의 버스 지연 분포를 사용했어요.` — 실제 grouping이 그 범위를 지원할 때만.
- B realtime used: `현재 버스 위치/도착정보 중 검증된 항목을 추가 반영했어요.` — category 실제 사용 시만.
- B historical-only: `현재 교통정보를 사용하지 못해 과거 조건만으로 계산했어요.`
- WALK/static transfer: 기존 point/reference + UNMODELED copy 유지.

### 상태별 UX

PARTIAL_MODEL, INSUFFICIENT, STALE, PROVIDER_ERROR를 유지하되 A historical artifact와 B realtime source의 원인을 분리한다.

### Developer/Demo Mode

허용: sample/window/artifact/model/schema/feature category/validation/run ID. 금지: secret, exact private origin, raw provider payload 전체, GPS trace(MR에 없음).

### CTA·Responsive·Accessibility

`결과로 돌아가기`, `상세 다시 시도`. Critical limitation은 접힌 영역에만 숨기지 않는다.

## SCR-06 — Share Snapshot

### 목적·범위

한 analysisId의 privacy-safe immutable snapshot을 공유한다. Share payload는 반드시 하나의 `analysisType`만 가진다.

### Departure Share 포함

- destination, targetArrivalAt
- Departure P50/P90 중 eligible 값
- selected-route scope, historical limitation, calculatedAt, validation

### Leave-now Share 포함

- destination, targetArrivalAt, departAt
- P(on_time), Arrival P50/P90 중 eligible 값
- realtimeContextCoverage 사용자 label
- selected-route scope, limitation, calculatedAt, validation

### 공통 제외

exact origin/coordinate/GPS trace, raw/internal IDs, secret/debug, **다른 기능 metric**.

Share 생성은 SCR-02 또는 SCR-08에서만 가능하며 parent `analysisType`을 보존한다.

## State namespace × Screen State

| Namespace | State | Primary Screen |
|---|---|---|
| Navigation | HOME | SCR-00 |
| AnalysisType | DEPARTURE_RECOMMENDATION | SCR-01/02/05/06 |
| AnalysisType | LEAVE_NOW_FORECAST | SCR-07/08/05/06 |
| AnalysisState | IDLE/ANALYZING/SUCCEEDED/FAILED | 해당 flow |
| RealtimeCoverage | FULL/PARTIAL/NONE | Leave-now only |
| PWA Runtime | ONLINE/OFFLINE_SNAPSHOT/UPDATE_AVAILABLE | Global |
| FutureTracking | NOT_IN_MR | SCR-03/04 |

한 analysisId의 `AnalysisType`은 생성 후 immutable이다.

## Error Taxonomy와 Recovery UX

| Error/State | 소유 화면 | 처리 |
|---|---|---|
| INPUT_INVALID / TARGET_BEYOND_SUPPORTED_HORIZON | SCR-01 또는 07 | 해당 form 수정 |
| UNSUPPORTED_GEOGRAPHY / ROUTE_NOT_FOUND | 01/07 | 지원/route 오류 |
| ROUTE_MAPPING_PARTIAL/FAILED | 02 또는 08 | 해당 기능 structure-only + NOT_COMPUTED |
| HISTORICAL_BASELINE_UNAVAILABLE | 02/05/08 | 해당 기능 metric 미계산 |
| REALTIME_CONTEXT_PARTIAL/UNAVAILABLE | 08/05 only | partial/historical-only limitation |
| STALE_DATA / PROVIDER_ERROR / QUOTA | 해당 flow | last/current 분리 |
| ANALYSIS_TYPE_MISMATCH | result/evidence/share | 다른 기능으로 coercion 금지; recovery |
| MODEL_FALLBACK | 08/05 only | baseline 사용, AI claim 축소 |
| NETWORK_UNAVAILABLE | Global | 각 result not-current offline snapshot |
| SHARE_EXPIRED/NOT_FOUND | SCR-06 | public variant |

legacy Event/Reforecast errors는 RETIRED_FROM_MR이다.

## Mobile-first PWA Contract

| 영역 | Mobile | Tablet/Desktop |
|---|---|---|
| SCR-00 | 두 feature cards vertical | side-by-side 가능 |
| SCR-01/02 | Departure flow | planning form/result expanded |
| SCR-07/08 | Leave-now flow | now form/result expanded |
| SCR-05 | mode-scoped sheet/full page | drawer/side panel |
| SCR-06 | single-function public card | centered card |

PWA installability, shell/static cache, offline privacy, one-shot location 원칙은 유지한다. Leave-now result는 foreground 복귀로 자동 current가 되지 않는다.

### PWA Compatibility Matrix

모든 지원 환경에서 다음 두 flow를 **각각** 통과한다.

- `SCR-00→SCR-01→SCR-02→SCR-05`
- `SCR-00→SCR-07→SCR-08→SCR-05`

Share enabled 시 각 result→SCR-06을 별도 확인한다. background GPS는 테스트 대상이 아니다.

## Accessibility Contract

- WCAG 수준 목표와 자동/수동 테스트 범위는 NFR에서 확정하되 다음은 Minimum 필수다.
- heading hierarchy와 landmark, skip link, logical DOM/focus order.
- 모든 field label/error association, keyboard-only 완료 가능.
- 색상 외 icon/text/pattern으로 state 전달.
- probability와 time은 screen reader가 문장으로 읽을 수 있게 accessible description 제공.
- dynamic loading/error는 적절한 live region 사용; 과도한 반복 announcement 금지.
- modal/sheet focus trap·return, ESC/back 정책.
- touch target, zoom/reflow, reduced motion.
- animation으로 probability를 확정적이거나 개선된 것처럼 과장하지 않는다.

---

## Analytics Contract

### 공통 원칙

exact coordinate, raw analysisId/token/provider ID, free-text location을 기본 analytics에서 제외한다. 두 기능 event namespace를 구분한다.

### Minimum dictionary

| Event | Screen | Required properties |
|---|---|---|
| service_home_view | 00 | entry_source |
| departure_feature_select | 00 | — |
| leave_now_feature_select | 00 | — |
| departure_input_view | 01 | — |
| departure_recommendation_submit/success/failed | 01→02 | target_time_bucket, eligibility/reason |
| departure_result_view | 02 | departure metric eligibility |
| leave_now_input_view | 07 | — |
| leave_now_forecast_submit/success/failed | 07→08 | target_time_bucket, realtime_context_coverage/reason |
| leave_now_result_view | 08 | arrival/on-time eligibility, realtime_context_coverage |
| evidence_open | 05 | analysis_type, confidence, model_used |
| share_create/share_view | 02/08/06 | analysis_type, privacy-safe state |
| pwa_runtime_state | Global | runtime_state, screen_id, snapshot_exists |

v0.1의 `journey_analyze_click`, `decision_result_view`, combined-result analytics와 Journey Start/Event/Reforecast events는 active dictionary에 없다.

### Internal QA event

Route B는 topology/realtime identity/data pipeline QA만 허용한다.

### Route A Demo 화면 계약

Departure demo와 Leave-now demo를 별도 flow로 실행한다. 한 화면에서 두 결과를 동시에 보여주는 demo-only mock을 만들지 않는다.

## Screen ↔ Feature ↔ REQ/BR Traceability

| Screen | Product Feature | Core REQ |
|---|---|---|
| SCR-00 | Service Function Selection | REQ-113,116 |
| SCR-01 | Departure Input | REQ-001~003,114 |
| SCR-02 | Departure Result | REQ-107~109,114,103 |
| SCR-07 | Leave-now Input | REQ-001~003,115 |
| SCR-08 | Leave-now Result | REQ-011~013,110~112,115,103 |
| SCR-05 | mode-scoped Evidence | REQ-040~073,090~092,106,109~112,116 |
| SCR-06 | single-function Share | REQ-080~082,116 |
| SCR-03/04 | Future GPS | retired F004~006 |

### 주요 정책 추적

- separate entry/input/result/API: SCR-00/01/02/07/08 + REQ-113~116
- Departure historical-only: SCR-01/02/05
- Leave-now now+realtime: SCR-07/08/05
- Share/Evidence analysisType isolation: SCR-05/06
- legacy Dual Analysis/manual tracking: active UI 없음

## Development Handoff Checklist

### Frontend

- [ ] Home에 두 독립 CTA가 있고 통합 계산 CTA가 없다.
- [ ] SCR-01/02에 Leave-now metric/realtime badge가 없다.
- [ ] SCR-07/08에 Departure P50/P90이 없다.
- [ ] result route의 analysisType mismatch를 다른 기능으로 변환하지 않는다.
- [ ] Evidence/Share가 parent analysisType의 metric만 표시한다.
- [ ] Start/Event/Reforecast CTA/route/analytics가 없다.

### Backend/API

- [ ] API-011 Departure response에 Departure metrics만 있다.
- [ ] API-012 Leave-now response에 Arrival/P(on_time) metrics만 있다.
- [ ] retired API-002 Dual Analysis endpoint가 MR route에 노출되지 않는다.
- [ ] API-013 read가 immutable analysisType을 보존한다.
- [ ] one function result/session이 other function prerequisite가 아니다.
- [ ] shared route/cache/artifact reuse가 result coupling을 만들지 않는다.

### Data/Probability

- [ ] Departure는 realtime feature를 사용하지 않는다.
- [ ] Leave-now는 verified current feature만 사용한다.
- [ ] P50을 평균으로 처리하지 않는다.
- [ ] unverified leading vehicle/congestion/headway를 fabricated하지 않는다.
- [ ] model uplift 미달 시 baseline fallback한다.

## QA Acceptance Scenarios

| ID | Scenario | Expected |
|---|---|---|
| UI-AC-001 | Home view | 두 기능 CTA 별도, 통합 분석 CTA 0 |
| UI-AC-002 | Departure direct entry | 다른 기능 선행 없이 SCR-01 접근 |
| UI-AC-003 | Departure submit | SCR-02에 Departure P50/P90만 표시 |
| UI-AC-004 | Departure payload contamination | Arrival/P(on_time)/realtime field 0 |
| UI-AC-005 | Leave-now direct entry | Departure result 없이 SCR-07 접근 |
| UI-AC-006 | Leave-now submit | SCR-08에 P(on_time)+Arrival P50/P90만 표시 |
| UI-AC-007 | Leave-now payload contamination | Departure P50/P90 field 0 |
| UI-AC-008 | same OD/target 두 기능 실행 | 별도 analysisId/result, 자동 연결 0 |
| UI-AC-009 | analysisType mismatch route | coercion 없이 recovery/error |
| UI-AC-010 | Departure Evidence | historical 근거만; realtime/model section 없음 |
| UI-AC-011 | Leave-now Evidence | historical + 실제 사용 realtime/model만 |
| UI-AC-012 | Share | 한 기능 metric만 포함 |
| UI-AC-013 | Leave-now refresh | 새 계산 전 old result는 not-current snapshot |
| UI-AC-014 | historical critical missing | 해당 기능 NOT_COMPUTED, fake number 0 |
| UI-AC-015 | mapping PARTIAL/FAILED | 해당 result structure-only + NOT_COMPUTED |
| UI-AC-016 | P50 copy | 평균 표현 0 |
| UI-AC-017 | retired scan | Dual Analysis button/result/API, Start/Event/Reforecast active 0 |
| UI-AC-018 | mobile compatibility | 두 독립 flow 각각 완주 |
| UI-AC-019 | offline | single-function snapshot only; cross-function resurrection 0 |
| UI-AC-020 | Future GPS | MR route/API/permission prompt 0 |

## Open Implementation Decisions

| Item | 현재 UI 계약 | Resolution Gate |
|---|---|---|
| historical bucket granularity | exact 수치/구간 하드코드 금지 | multi-window profile |
| support thresholds | rule 전 INSUFFICIENT | SUPPORT_RULE_V1 |
| Departure P50/P90 candidate grid | UI는 결과만 표시 | engine benchmark/CG |
| realtime context categories | 실제 사용 category만 표시 | feature availability evidence |
| leading vehicle congestion/headway | 기본 미표시/미사용 | identity+timestamp+coverage experiment |
| AI model serving | fallbackUsed/modelVersion만 evidence | baseline uplift Gate |
| unsupervised regime | 일반 UI 비노출 | value-add 검증 시 Evidence detail |
| Share TTL | API expiresAt | G5 |
| exact breakpoints/SLO | 임의 수치 금지 | design/performance profile |
| Future GPS | MR UI/route 없음 | 별도 privacy/accuracy/battery research |

## 정본 정합성 규칙

- `Dual Analysis`, `A/B Decision Result`, `출발 시간과 도착 가능성 계산` active UX를 금지한다.
- Service Home에서 두 기능을 별도 선택한다.
- Departure와 Leave-now는 input/result route와 CTA가 다르다.
- Departure result에는 Departure P50/P90만 존재한다.
- Leave-now result에는 P(on_time), Arrival P50/P90만 존재한다.
- 한 기능은 다른 기능의 result/session/API response를 prerequisite로 요구하지 않는다.
- Evidence/Share는 한 analysisType만 포함한다.
- historicalModelCoverage는 공통, realtimeContextCoverage는 Leave-now only다.
- unverified realtime feature를 사용했다고 표시하지 않는다.
- Future GPS/manual tracking은 active MR과 분리한다.

## Appendix — Screen 완료 정의

| Screen | Done |
|---|---|
| SCR-00 | 두 기능 CTA가 명확히 분리되고 통합 계산 CTA 없음 |
| SCR-01 | future planning input + Departure submit |
| SCR-02 | Departure-only metrics/result/evidence actions |
| SCR-07 | now forecast input + current departure context |
| SCR-08 | Leave-now-only metrics/realtime coverage |
| SCR-05 | parent analysisType의 evidence만 |
| SCR-06 | parent analysisType의 share metrics만 |
| SCR-03/04 | Future reserved, MR route/CTA 0 |

## Appendix — 금지 표현

- `한 번 입력하면 출발 시간과 도착 가능성을 동시에 계산`
- `통합 분석`, `A/B Decision Result`를 active product 화면으로 표현
- Departure 화면에서 `실시간 반영`
- Leave-now 화면에서 Departure P50/P90 표시
- `P50 평균`, `P90 90% 정확`, `가장 안전한 출발시간`
- `AI가 최종 도착확률을 직접 계산`
- `앞차 혼잡/거리 영향이 검증됨` — Evidence 전
- `GPS 자동 추적 가능` — Future Gate 전

