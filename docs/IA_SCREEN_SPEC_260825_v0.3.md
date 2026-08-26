# 언제와 (Journey Reliability) IA & 화면 정의서 — v0.3

> **문서 목적**: UX/UI, Frontend, Backend, Data, QA가 추가 해석 없이 화면·route·접근조건·상태·데이터·CTA·예외·복구를 구현하고 검증할 수 있도록 한다.  
> **문서 지위**: Service Plan의 하위 IA/Screen Contract 정본  
> **정본 파일명**: `IA_SCREEN_SPEC_260825_v0.3.md`  
> **버전**: v0.3 — Splash→Shared Input Shell, milestone timeline, URL public share  
> **기준일**: 2026-08-25  
> **대상**: 독립형 Mobile-first PWA / 로그인 없는 Minimum Release  
> **상위 기준**: `SERVICE_PLAN_260825_v0.3.md`  
> **하위 구현 기준**: `REQUIREMENTS_SPEC_260825_v0.3.md`

---

## 문서 네비게이션

**정본 문서 바로가기**

- [Service Plan](SERVICE_PLAN_260825_v0.3.md)
- **IA / Screen Spec**
- [Requirements Spec](REQUIREMENTS_SPEC_260825_v0.3.md)
- [Decision Sheet](DECISION_SHEET_260825_v0.3.md)

**이 문서 안에서 이동**

- [문서 사용법과 IA 단위](#문서-사용법과-ia-단위)
- [IA 핵심 결정](#ia-핵심-결정)
- [전체 Information Architecture](#전체-information-architecture)
- [Route Inventory와 Guard](#route-inventory와-guard)
- [Global Shell과 Navigation](#global-shell과-navigation)
- [공통 데이터·표시 계약](#공통-데이터표시-계약)
- [Global State Matrix](#global-state-matrix)
- [APP-SPLASH — App Launch Splash](#app-splash--app-launch-splash)
- [SCR-00 — Service Home (v0.2 history)](#scr-00--service-home-v02-history)
- [SCR-01 — Departure Recommendation Input State](#scr-01--departure-recommendation-input-state)
- [SCR-02 — Departure Recommendation Result](#scr-02--departure-recommendation-result)
- [SCR-07 — Arrival Time Input State](#scr-07--arrival-time-input-state)
- [SCR-08 — Arrival Time Result](#scr-08--arrival-time-result)
- [SCR-03 — Future GPS Journey Tracking](#scr-03--future-gps-journey-tracking)
- [SCR-04 — Future Auto-Reforecast](#scr-04--future-auto-reforecast)
- [SCR-05 — Evidence Detail](#scr-05--evidence-detail)
- [SCR-06 — Public Share View](#scr-06-public-share-view)
- [State namespace × Screen State](#state-namespace--screen-state)
- [Error Taxonomy와 Recovery UX](#error-taxonomy와-recovery-ux)
- [Mobile-first PWA Contract](#mobile-first-pwa-contract)
- [Accessibility Contract](#accessibility-contract)
- [Analytics Contract](#analytics-contract)
- [Screen ↔ Feature ↔ REQ/BR Traceability](#screen--feature--reqbr-traceability)
- [Development Handoff Checklist](#development-handoff-checklist)
- [QA Acceptance Scenarios](#qa-acceptance-scenarios)
- [Open Implementation Decisions](#open-implementation-decisions)
- [정본 정합성 규칙](#정본-정합성-규칙)

## 문서 사용법과 IA 단위

### IA가 정의하는 것

v0.3 Minimum Release는 **하나의 Shared Input Shell 안에서 두 독립 product command를 선택**한다. 화면 shell 공유와 계산 계약 분리를 동시에 만족해야 한다.

| 단위 | 정의 | v0.3 범위 |
|---|---|---|
| App launch | 브랜드 presentation | APP-SPLASH |
| Shared entry | 기능 Tab 선택 + 공통 장소 입력 shell | SCR-01 / SCR-07 상태 |
| Departure flow | 사전 계획용 | SCR-01 state → SCR-02 Result |
| Arrival flow | 지금 판단용 | SCR-07 state → SCR-08 Result |
| Result detail | milestone timeline + Evidence | SCR-02/08, SCR-05 |
| Share create | owner result 위 URL 생성/복사 overlay | OVL-SHARE-CREATE |
| Public share | token 기반 read-only 결과 | SCR-06 |
| Future reserved | GPS 자동 추적 연구 | SCR-03, SCR-04 |
| Historical only | v0.2 Service Home | SCR-00 |

### 화면 ID 정책

- `SCR-00 Service Home`은 2026-08-24 v0.2 history로 보존하며 v0.3 active route/CTA에서 사용하지 않는다.
- 현재 Figma의 `scr-00-splash` frame은 IA에서 **APP-SPLASH transient state**로 매핑한다. historical SCR-00 ID를 다른 의미로 재사용하지 않는다.
- `SCR-01`과 `SCR-07`은 동일한 물리 Input Shell의 **서로 다른 analysis tab state**다. 상태 ID는 traceability를 위해 유지한다.
- `SCR-02`와 `SCR-08`은 typed result route를 계속 분리한다.
- `SCR-06`은 owner의 create modal이 아니라 **수신자가 URL로 보는 Public Share View**다.
- Share Create UI는 `OVL-SHARE-CREATE` overlay로 정의하며 독립 route/screen ID를 부여하지 않는다.
- SCR-03/04는 Future reserved다.
- SCR-05는 `analysisType`에 따라 한 기능의 evidence만 렌더링한다.

### Source-of-truth 경계

| 질문 | 정본 |
|---|---|
| 왜 Shared Input Shell이어도 두 기능이 독립인가 | Service Plan v0.3 |
| 화면/route/Tab/CTA/milestone/share overlay | IA v0.3 |
| API/Entity/Milestone/Data/Acceptance | Requirements v0.3 |
| 실제 검증 사실·제품 결정 history | Decision Sheet v0.3 |

## IA 핵심 결정

| ID | 결정 | 구현 결과 |
|---|---|---|
| IA-001 | selected structural route 하나만 분석 | reliability ranking 없음 |
| IA-002 | active entry는 APP-SPLASH 후 Shared Input Shell | Service Home active route 없음 |
| IA-003 | SCR-01/07은 같은 Input Shell의 Tab state | 물리 shell 공유 허용 |
| IA-004 | Tab 전환은 계산 실행이 아님 | submit 전 API 호출 0 |
| IA-005 | Departure/Arrival은 별도 submit/API/result route | combined response 렌더 금지 |
| IA-006 | Departure는 historical-only | realtime badge/feature 없음 |
| IA-007 | Arrival은 departAt=now snapshot | current context coverage 표시 |
| IA-008 | v0.3 user-facing B primary metric은 Arrival P50/P90 | P(on_time) active UI 없음 |
| IA-009 | P50은 평균이 아님 | help/copy 의미 고정 |
| IA-010 | Result는 최종 metric + milestone timeline | FE 임의 누적 금지 |
| IA-011 | Departure milestone `보통/여유`는 P50-plan/P90-plan timeline | same-departure P50/P90로 오해 금지 |
| IA-012 | Arrival milestone `보통/여유`는 departAt=now checkpoint P50/P90 | 평균/보장 표현 금지 |
| IA-013 | milestone list만 세로 스크롤 가능 | 상단 result와 하단 actions 고정 |
| IA-014 | 하단 액션은 `결과 공유하기` + `계산 근거 ›` 고정 | list 길이와 무관 |
| IA-015 | Evidence는 analysisType-scoped | 사용하지 않은 기능 evidence 미표시 |
| IA-016 | URL Share는 owner create overlay + public SCR-06로 분리 | create/view 권한 분리 |
| IA-017 | Share는 한 기능 result만 | mixed metric payload 금지 |
| IA-018 | direct result URL/refresh는 동일 analysisType snapshot 복구 | 다른 기능으로 coercion 금지 |
| IA-019 | owner capability는 result/evidence/share-create 보호 | public token은 read-only |
| IA-020 | historical/realtime freshness 분리 | realtime은 Arrival only |
| IA-021 | origin 위치 권한은 explicit one-shot | background GPS 없음 |
| IA-022 | AI는 Arrival leg distribution 보정 | final time 직접 AI copy 금지 |
| IA-023 | SCR-03/04 manual tracking은 RETIRED_FROM_MR | route/CTA/state 없음 |
| IA-024 | Splash animation은 presentation이며 reduced-motion/static fallback | provider/API loading gate 금지 |
| IA-025 | Figma primary action/highlight는 `#3C87FF`, small point accent는 `#FFB639`, base는 white 중심 | color는 state의 유일한 전달 수단이 아님 |

## 전체 Information Architecture

```text
APP-SPLASH  (transient, no route)
  ↓
Shared Input Shell  /
  ├─ SCR-01 state: 출발 시간 추천
  │    ↓ submit API-011
  │  SCR-02 Departure Result /departure/{analysisId}/result
  │    ├─ Departure P50 / P90
  │    ├─ Milestone timeline (scrollable)
  │    ├─ 계산 근거 → SCR-05
  │    └─ 결과 공유하기 → OVL-SHARE-CREATE
  │
  └─ SCR-07 state: 도착 시간 계산
       ↓ submit API-012
     SCR-08 Arrival Result /arrival-now/{analysisId}/result
       ├─ Arrival P50 / P90
       ├─ realtimeContextCoverage
       ├─ Milestone timeline (scrollable)
       ├─ 계산 근거 → SCR-05
       └─ 결과 공유하기 → OVL-SHARE-CREATE

OVL-SHARE-CREATE (owner-only overlay)
  └─ URL 생성/복사

SCR-05 Evidence Detail /analysis/{analysisId}/evidence
SCR-06 Public Share View /share/{token}
SCR-00 Service Home = v0.2 history, no active route
SCR-03 / SCR-04 = FUTURE_GPS_RESEARCH reserved
```

### Main Journey 전이

| From | Trigger | To | 불변조건 |
|---|---|---|---|
| App Launch | presentation start | APP-SPLASH | analysis/provider call 0 |
| APP-SPLASH | presentation complete/static fallback | SCR-01 tab state | default Departure tab; permission prompt 0 |
| SCR-01 | Tab `도착 시간 계산` | SCR-07 state | API-011/012 호출 0 |
| SCR-07 | Tab `출발 시간 추천` | SCR-01 state | API-011/012 호출 0 |
| SCR-01 | `출발 시간 추천받기` | SCR-02 | API-011만 호출 |
| SCR-07 | `도착 시간 계산하기` | SCR-08 | API-012만 호출; departAt server now |
| SCR-02/08 | `계산 근거` | SCR-05 | parent analysisType 유지 |
| SCR-02/08 | `결과 공유하기` | OVL-SHARE-CREATE | owner capability 검증 |
| OVL-SHARE-CREATE | URL create/copy | same result | API-007; 다른 기능 metric 0 |
| public URL | token open | SCR-06 | API-008 public read-only |

두 result 화면 사이 direct 자동 transition은 없다. Tab 전환은 새 request를 만들지 않고 submit 때 새 analysis가 생성된다.

## Route Inventory와 Guard

| Route | Screen/State | 접근 조건 | 직접 접근/새로고침 |
|---|---|---|---|
| `/` | Shared Input Shell | 없음 | 항상 가능; 기본 Tab은 Figma 기준 Departure state |
| `/departure/{analysisId}/result` | SCR-02 Planning Result | type=DEPARTURE_RECOMMENDATION + owner | 동일 snapshot 복구 |
| `/arrival-now/{analysisId}/result` | SCR-08 Arrival Result | type=LEAVE_NOW_FORECAST + owner | 동일 snapshot 복구; current 자동 갱신 금지 |
| `/analysis/{analysisId}/evidence` | SCR-05 | parent result access | parent type 유지 |
| `/share/{token}` | SCR-06 | valid public token | read-only single-function snapshot |

APP-SPLASH는 URL route가 아니라 app-launch presentation state다. Shared Input Shell의 Tab state를 URL에 어떻게 인코딩할지는 implementation TBD이며, 어떤 방식이든 Tab 전환만으로 분석을 실행해서는 안 된다.

v0.2 `/departure`, `/arrival-now` 입력 route의 redirect/compatibility 정책은 구현 결정으로 남긴다. legacy route를 유지하더라도 새 분석을 자동 실행하거나 다른 `analysisType`으로 coercion해서는 안 된다.

잘못된 analysisType으로 result route에 접근하면 다른 화면으로 coercion하지 않고 동일한 not-found/recovery semantics를 사용한다.

### Guard 우선순위

1. route parameter / expected analysisType
2. owner capability(`/share` 제외)
3. resource 존재
4. result eligibility
5. 해당 기능의 evidence 상태

### URL과 개인정보

`analysisId`는 locator일 뿐 credential이 아니다. exact coordinate/owner capability/secret/GPS trace를 URL에 넣지 않는다. `/share/{token}`의 token은 public read capability이므로 analytics/log/referrer 노출을 최소화하고 owner 권한으로 승격하지 않는다.

## Global Shell과 Navigation

### Shell hierarchy

```text
AppShell
├─ APP-SPLASH (launch only)
├─ Header: 언제와
├─ Function Tabs: 출발 시간 추천 / 도착 시간 계산
├─ Main
├─ Global Feedback
├─ PWA Runtime Region
└─ Footer / policy links
```

### Header / Navigation

- active Home screen은 없다.
- Input Shell에서 브랜드 `언제와`와 두 기능 Tab을 표시한다.
- Departure tab에는 future targetArrivalAt form이 존재한다.
- Arrival tab에는 origin/destination와 `지금 {currentTime} 출발 기준` context만 존재하며 mandatory targetArrivalAt input은 없다.
- 결과 화면에서 다른 기능으로 가려면 back/input shell로 돌아가 Tab을 선택한다. 현재 result를 다른 type으로 변환하지 않는다.
- result의 하단 고정 actions는 `결과 공유하기`와 `계산 근거 ›`다.
- `Live`, `이동 시작`, event mutation navigation은 없다.

### Global feedback

provider/network/input 오류는 현재 기능 context 안에서 처리한다. Arrival이 historical-only로 축소되면 persistent limitation으로 표시한다. Splash asset 실패는 분석 오류가 아니라 정적 brand fallback으로 처리한다.

## 공통 데이터·표시 계약

### Common Analysis Envelope

두 기능은 공통 envelope를 공유할 수 있지만 metric payload는 분리한다.

| Field | Required | 규칙 |
|---|---|---|
| `analysisId` | yes | locator |
| `analysisType` | yes | `DEPARTURE_RECOMMENDATION` 또는 `LEAVE_NOW_FORECAST` |
| `routeCandidateId` | internal | selected route |
| coverage/selectedRoute/canonicalMapping | yes | 기존 분리 축 유지 |
| `historicalCoverage` | yes | shared baseline coverage |
| `validationScope` / `confidence` | yes | 결과 metric과 분리 |
| `calculatedAt` | yes | result 생성시각 |
| `limitations[]` | array | 실제 기능 limitation만 |
| `milestones[]` | result별 | engine-produced, versioned projection |

`targetArrivalAt`은 Departure request/result에서만 required다.

### Departure Result View Model — SCR-02

| Field | 규칙 |
|---|---|
| `targetArrivalAt` | required |
| `departureP50At` | nullable; Departure metric |
| `departureP90At` | nullable; Departure metric |
| `historicalCoverage` | computed 시 required |
| `milestones[]` | P50-plan/P90-plan scenario projection |
| `metricEligibility.departure*` | 독립 판정 |

**금지 필드**: `departAt`, `arrivalP50At`, `arrivalP90At`, `onTimeProbability`, `realtimeContextCoverage`, realtimeFeatureCategories, realtime model provenance.

### Arrival Result View Model — SCR-08

| Field | 규칙 |
|---|---|
| `departAt` | required; `calculatedAt≈now` |
| `arrivalP50At` / `arrivalP90At` | nullable |
| `milestones[]` | departAt=now checkpoint P50/P90 |
| `realtimeContextCoverage` | FULL/PARTIAL/NONE |
| `metricEligibility.arrival*` | 독립 판정 |

`realtimeFeatureCategories[]`/`modelProvenance` 상세는 SCR-08 자체 필드가 아니라 SCR-05 Evidence Detail의 leg evidence 필드(「Leg evidence required/nullable」 참고)에서만 제공한다.

**금지 필드**: `targetArrivalAt`, `onTimeProbability`, `departureP50At`, `departureP90At`.

### Milestone View Model

| Field | 규칙 |
|---|---|
| `sequence` | selected route 내 표시 순서 |
| `milestoneType` | ORIGIN / BOARD / TRANSFER / ALIGHT / DESTINATION 등 canonical enum |
| `label` / `subLabel` | privacy/display policy 적용 |
| `normalAt` | analysisType별 `보통` semantics |
| `bufferedAt` | analysisType별 `여유` semantics |
| `eligibility` | USER_FACING / NOT_COMPUTED 등 |
| `limitations[]` | source/support/unmodeled 사유 |
| `scenario` | Departure는 P50-plan/P90-plan, Arrival은 departAt=now checkpoint 구분 |
| `semanticsVersion` | projection rule version |

provider raw node 전체를 그대로 렌더링하지 않는다.

### 숫자 formatting / copy

| 기능 | Metric | Label |
|---|---|---|
| Departure | P50 | `보통은 {time}까지 출발` |
| Departure | P90 | `여유 있게는 {time}까지 출발` |
| Arrival | Arrival P50 | `예상 도착 {time}` 또는 `보통 {time} 도착` |
| Arrival | Arrival P90 | `여유 있게 보면 {time} 도착` |
| Milestone | normal/buffered | `보통 {time}` / `여유 {time}` |

P50을 평균으로 정의하지 않는다. historical-only Arrival에 `실시간 반영` copy를 사용하지 않는다.

## Global State Matrix

상태는 **현재 analysisType 내부**에서만 합성한다. 다른 기능 상태를 함께 보여주지 않는다.

| State | Departure | Arrival |
|---|---|---|
| APP_SPLASH | transient presentation | transient presentation |
| INPUT_IDLE | Departure tab | Arrival tab |
| ANALYZING | route+historical/candidate search | route+historical+realtime context calculation |
| FRESH | eligible Departure metrics+milestones | eligible Arrival metrics+milestones |
| HISTORICAL_ONLY | N/A — normal historical design | realtime none인 fallback |
| PARTIAL_REALTIME | N/A | 일부 realtime 사용 |
| STALE | historical artifact age limitation | stale realtime 제외/재계산 |
| PARTIAL_MODEL / INSUFFICIENT | 기능별 limitation | 기능별 limitation |
| NOT_COMPUTED | Departure null/partial milestone | Arrival null/partial milestone |
| SHARE_CREATING | owner overlay | owner overlay |
| OFFLINE_SNAPSHOT | not-current planning snapshot | not-current now snapshot; current 표현 금지 |

`realtimeContextCoverage`는 Arrival에만 존재한다. Tab state와 AnalysisState는 분리한다.

## APP-SPLASH — App Launch Splash

### 목적

`언제와` 브랜드를 짧게 제시하고 Shared Input Shell로 연결하는 transient presentation state다. 현재 Figma frame `scr-00-splash`는 이 계약을 시각화한다.

### Component hierarchy

```text
APP-SPLASH
├─ Brand mark / logo
├─ `언제와`
├─ short brand copy
└─ optional motion
```

### 계약

- 분석 API, provider API, location permission을 Splash에서 선행 호출하지 않는다.
- motion 감소 설정에서는 정적 presentation을 허용한다.
- animation asset 실패가 Input 진입을 막지 않는다.
- animation duration/easing은 IA에서 임의 수치로 고정하지 않는다.
- Splash 자체를 loading/probability progress로 표현하지 않는다.

## SCR-00 — Service Home (v0.2 history)

**Status: `SUPERSEDED_FROM_V0.3 / NO_ACTIVE_ROUTE`**

2026-08-24 v0.2의 Service Home은 두 기능을 카드/CTA로 분기하던 historical product contract다. v0.3 active entry에서 구현·시연하지 않는다. ID는 traceability를 위해 보존하며 APP-SPLASH 의미로 재사용하지 않는다.

## SCR-01 — Departure Recommendation Input State

### 목적·접근·종료

Shared Input Shell의 `출발 시간 추천` Tab state다. 미래 일정에 대한 Departure request를 만든다. 전날/수시간 전 사용을 정상 시나리오로 지원한다.

### Component hierarchy

```text
Shared Input Shell
├─ Brand Header: 언제와
├─ Function Tabs
│  ├─ Active: 출발 시간 추천
│  └─ 도착 시간 계산
├─ Context: `약속 전에 미리 계획할 때`
├─ Origin
├─ Destination
├─ Target Arrival: Date + Time
├─ CTA: `출발 시간 추천받기`
└─ Compact Usage Flow
```

### 입력 계약

- origin, destination, targetArrivalAt required.
- Date/Time은 한 시각 계약으로 합성하며 timezone-aware다.
- Tab 전환은 값을 유지할 수 있으나 Arrival submit schema에 targetArrivalAt을 자동 전송하지 않는다.
- current location은 explicit one-shot action일 때만 권한을 요청한다.

### Analytics

`shared_input_view`, `function_tab_select{departure}`, `departure_recommendation_submit/success/failed`.

## SCR-02 — Departure Recommendation Result

### 목적

Departure P50/P90과 historical-only milestone projection을 표시한다.

```text
SCR-02
├─ Target Context Bar
├─ Primary Recommendation
│  ├─ `보통은` + Departure P50
│  └─ `여유 있게는` + Departure P90
├─ 이동 경로 요약
│  └─ Scrollable Milestone List
│     ├─ first/origin point highlighted
│     └─ each row: label/subLabel + 보통/여유 time
└─ Fixed Bottom Actions
   ├─ `결과 공유하기`
   └─ `계산 근거 ›`
```

### Milestone semantics

- `보통`: `departureP50At` plan 조건의 milestone median projection.
- `여유`: `departureP90At` plan 조건의 milestone median projection.
- 이 두 값은 같은 출발 시각의 P50/P90 pair가 아니다.
- milestone이 길면 **milestone list만 세로 스크롤**한다. 상단 결과와 하단 actions는 고정한다.
- raw provider stop/station을 전부 보여주지 않는다.

### 금지

- Arrival P50/P90/P(on_time) 카드
- realtime context badge/current vehicle/congestion
- `지금 출발하면` copy
- FE에서 leg duration을 더해 milestone 시간 생성
- list 스크롤 때문에 하단 share/evidence action 위치가 움직이는 구현

### Acceptance

Departure-only response와 engine milestone projection이 그대로 렌더링되며 다른 기능 metric placeholder를 생성하지 않는다.

## SCR-07 — Arrival Time Input State

### 목적·접근·종료

Shared Input Shell의 `도착 시간 계산` Tab state다. 실제 출발 직전의 독립 Leave-now request를 만든다. Departure result가 없어도 직접 사용 가능하다.

```text
Shared Input Shell
├─ Brand Header: 언제와
├─ Function Tabs
│  ├─ 출발 시간 추천
│  └─ Active: 도착 시간 계산
├─ Context: `지금 {currentTime} 출발 기준`
├─ Origin + Current Location(one-shot)
├─ Destination
├─ CTA: `도착 시간 계산하기`
├─ short realtime notice
└─ Compact Usage Flow
```

submit 시 server `calculatedAt`을 기준으로 `departAt≈now`를 고정한다. v0.3 MR에는 mandatory `targetArrivalAt` input이 없다.

### Analytics

`shared_input_view`, `function_tab_select{arrival}`, `leave_now_forecast_submit/success/failed`.

## SCR-08 — Arrival Time Result

### 목적

지금 출발 기준 Arrival P50/P90와 realtime context 사용 범위, milestone checkpoint 시간을 표시한다.

```text
SCR-08
├─ `지금 {departAt} 출발 기준`
├─ Primary Arrival
│  ├─ Arrival P50
│  └─ Arrival P90
├─ Realtime Context: FULL/PARTIAL/HISTORICAL_ONLY
├─ 이동 경로 요약
│  └─ Scrollable Milestone List
│     ├─ first/current point highlighted
│     └─ each row: label/subLabel + 보통/여유 time
└─ Fixed Bottom Actions
   ├─ `결과 공유하기`
   └─ `계산 근거 ›`
```

### Milestone semantics

- departAt=now 하나의 scenario다.
- `보통`: checkpoint arrival P50.
- `여유`: checkpoint arrival P90.
- raw provider rows가 아니라 canonical route milestone만 렌더링한다.
- list가 길어지면 middle list만 스크롤하며 상단/하단은 고정한다.

### 금지

- Departure P50/P90
- `P(on_time)` / 정시 도착 확률
- planning 추천 CTA
- 이전 Departure result를 기준값으로 표시
- FE fabricated milestone time

### Freshness

화면 복귀만으로 current forecast가 되지 않는다. 새 계산을 실행해야 새 departAt/realtime snapshot을 만든다.

### Acceptance

Departure Recommendation을 사용한 적 없는 새 세션에서도 Arrival flow가 완주된다.

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

## SCR-06 — Public Share View

### 목적·범위

`/share/{token}`을 받은 사용자가 로그인 없이 한 analysisType의 privacy-safe immutable 결과를 read-only로 조회한다. **Owner의 Share Create Overlay와 SCR-06을 동일 화면으로 취급하지 않는다.**

### OVL-SHARE-CREATE — Owner Result Overlay

```text
Owner Result
└─ 결과 공유하기
   └─ Share Create Overlay
      ├─ privacy-safe preview
      ├─ public URL
      └─ `URL 복사`
```

- API-007을 호출할 수 있는 owner capability가 필요하다.
- overlay close 후 원래 result로 돌아간다.
- image save/Kakao direct send CTA는 canonical v0.3 UI가 아니다.

### SCR-06 Public Share View

**Departure 포함**
- destination, targetArrivalAt
- eligible Departure P50/P90
- privacy-safe milestone timeline
- calculatedAt, limitation/validation scope

**Arrival 포함**
- destination, departAt
- eligible Arrival P50/P90
- privacy-safe milestone timeline
- realtimeContextCoverage label, calculatedAt, limitation/validation

### 공통 제외

exact origin coordinate/free-text, GPS trace, raw/internal IDs, owner capability, secret/debug, 다른 기능 metric.

### 접근/오류

- token은 public read-only capability다.
- expired/revoked/not-found는 public error variant로 처리한다.
- share token으로 owner result/evidence/recompute/share-create 권한을 획득할 수 없다.

## State namespace × Screen State

| Namespace | State | Primary Screen/State |
|---|---|---|
| Launch | APP_START / APP_SPLASH / INPUT_READY | APP-SPLASH / Shared Input |
| InputTab | DEPARTURE_RECOMMENDATION / LEAVE_NOW_FORECAST | SCR-01 / SCR-07 state |
| AnalysisType | DEPARTURE_RECOMMENDATION | SCR-01/02/05/06 |
| AnalysisType | LEAVE_NOW_FORECAST | SCR-07/08/05/06 |
| AnalysisState | IDLE/ANALYZING/SUCCEEDED/FAILED | 해당 submit flow |
| RealtimeCoverage | FULL/PARTIAL/NONE | Arrival only |
| Share | IDLE/CREATING/CREATED/EXPIRED/REVOKED | OVL/SCR-06 |
| PWA Runtime | ONLINE/OFFLINE_SNAPSHOT/UPDATE_AVAILABLE | Global |
| FutureTracking | NOT_IN_MR | SCR-03/04 |

한 analysisId의 `AnalysisType`은 submit 시 생성 후 immutable이다. Tab state는 analysisId가 아니다.

## Error Taxonomy와 Recovery UX

| Error/State | 소유 화면 | 처리 |
|---|---|---|
| INPUT_INVALID | SCR-01/07 | 해당 form 수정 |
| TARGET_BEYOND_SUPPORTED_HORIZON | SCR-01 only | Departure target 수정 |
| UNSUPPORTED_GEOGRAPHY / ROUTE_NOT_FOUND | 01/07 | 지원/route 오류 |
| ROUTE_MAPPING_PARTIAL/FAILED | 02 또는 08 | 해당 기능 structure-only + NOT_COMPUTED |
| HISTORICAL_BASELINE_UNAVAILABLE | 02/05/08 | 해당 기능 metric 미계산 |
| MILESTONE_NOT_COMPUTED/PARTIAL | 02/08/05 | 해당 checkpoint time 숨김/limitation |
| REALTIME_CONTEXT_PARTIAL/UNAVAILABLE | 08/05 only | partial/historical-only limitation |
| STALE_DATA / PROVIDER_ERROR / QUOTA | 해당 flow | last/current 분리 |
| ANALYSIS_TYPE_MISMATCH | result/evidence/share | 다른 기능으로 coercion 금지; recovery |
| MODEL_FALLBACK | 08/05 only | baseline 사용, AI claim 축소 |
| SPLASH_ASSET_FAILURE | APP-SPLASH | static fallback 후 Input 진입 |
| NETWORK_UNAVAILABLE | Global | 각 result not-current offline snapshot |
| SHARE_EXPIRED/REVOKED/NOT_FOUND | SCR-06 | public variant |

legacy Event/Reforecast errors는 RETIRED_FROM_MR이다.

## Mobile-first PWA Contract

| 영역 | Mobile | Tablet/Desktop |
|---|---|---|
| APP-SPLASH | full-screen brand presentation | centered presentation |
| Shared Input Shell | Tab + single-column form | wider form; semantics 동일 |
| SCR-02/08 | fixed summary + scrollable milestone middle + fixed actions | expanded timeline 가능 |
| SCR-05 | mode-scoped sheet/full page | drawer/side panel |
| OVL-SHARE-CREATE | modal/bottom-sheet style | centered modal |
| SCR-06 | public single-function result | centered/expanded public result |

PWA installability, shell/static cache, offline privacy, one-shot location 원칙은 유지한다. Arrival result는 foreground 복귀로 자동 current가 되지 않는다.

### PWA Compatibility Matrix

모든 지원 환경에서 다음 flow를 각각 통과한다.

- `APP-SPLASH→Input[Departure]→SCR-02→SCR-05`
- `APP-SPLASH→Input[Arrival]→SCR-08→SCR-05`
- `SCR-02/08→OVL-SHARE-CREATE→URL copy→/share/{token}→SCR-06`

background GPS는 테스트 대상이 아니다.

## Accessibility Contract

- WCAG 수준 목표와 자동/수동 테스트 범위는 NFR에서 확정하되 다음은 Minimum 필수다.
- heading hierarchy와 landmark, logical DOM/focus order.
- 모든 field label/error association, keyboard-only 완료 가능.
- 색상 외 icon/text/pattern으로 state 전달.
- time/quantile은 screen reader가 문장으로 읽을 수 있게 accessible description 제공.
- milestone list는 keyboard/assistive tech로 순서대로 탐색 가능하며 scroll 영역에 명확한 label을 둔다.
- fixed bottom actions가 zoom/reflow에서 content를 가리지 않는다.
- modal/share overlay focus trap·return, ESC/back 정책.
- touch target, zoom/reflow.
- Splash는 `prefers-reduced-motion` 등 motion 감소 환경에 정적 fallback을 제공한다.
- animation으로 정확도·실시간 개선을 암시하지 않는다.

## Analytics Contract

### 공통 원칙

exact coordinate, raw analysisId/token/provider ID, free-text location을 기본 analytics에서 제외한다. 두 기능 event namespace를 구분한다.

### Minimum dictionary

| Event | Screen/State | Required properties |
|---|---|---|
| app_splash_view | APP-SPLASH | entry_source, motion_mode_category |
| shared_input_view | 01/07 shell | active_analysis_type |
| function_tab_select | 01/07 | target_analysis_type; 계산 실행 0 |
| departure_recommendation_submit/success/failed | 01→02 | target_time_bucket, eligibility/reason |
| departure_result_view | 02 | departure metric/milestone eligibility |
| leave_now_forecast_submit/success/failed | 07→08 | realtime_context_coverage/reason |
| arrival_result_view | 08 | arrival/milestone eligibility, realtime_context_coverage |
| milestone_scroll | 02/08 | analysis_type, milestone_count_bucket only |
| evidence_open | 05 | analysis_type, confidence, model_used |
| share_create | 02/08 overlay | analysis_type, privacy-safe state |
| share_url_copy | overlay | analysis_type |
| public_share_view | 06 | analysis_type, share_state; raw token 0 |
| pwa_runtime_state | Global | runtime_state, screen_id, snapshot_exists |

v0.1/v0.2의 `service_home_view`, Home feature-select, combined-result analytics와 Journey Start/Event/Reforecast events는 active dictionary에 없다.

### Internal QA event

Route B는 topology/realtime identity/data pipeline QA만 허용한다.

### Route A Demo 화면 계약

Departure demo와 Arrival demo는 같은 Input Shell을 공유하되 submit/API/result는 독립 실행한다. 한 result에서 두 기능 metric을 동시에 보여주는 demo-only mock을 만들지 않는다.

## Screen ↔ Feature ↔ REQ/BR Traceability

| Screen/State | Product Feature | Core REQ |
|---|---|---|
| APP-SPLASH | App Launch/PWA | REQ-117; NFR-101 |
| SCR-00 | v0.2 Service Home history | SUPERSEDED_FROM_V0.3 |
| SCR-01 | Shared Input / Departure state | REQ-001~003,113,114,118 |
| SCR-02 | Departure Result + Milestones | REQ-107~109,114,119,123 |
| SCR-07 | Shared Input / Arrival state | REQ-001~002,113,115,118 |
| SCR-08 | Arrival Result + Milestones | REQ-011~012,110~112,115,120,123 |
| SCR-05 | mode-scoped Evidence | REQ-040~073,090~092,106,109~112,116,123 |
| OVL-SHARE-CREATE | URL Share Create | REQ-080~082,121 |
| SCR-06 | Public URL Share View | REQ-080~082,122,123 |
| SCR-03/04 | Future GPS | retired F004~006 |

### 주요 정책 추적

- Splash/direct input: APP-SPLASH + REQ-117
- shared shell / split command: SCR-01/07 + REQ-113,118,116
- Departure historical-only: SCR-01/02/05
- Arrival now+realtime: SCR-07/08/05
- milestone projection: SCR-02/08 + REQ-119/120/123 + ENT-034
- URL share create/read: overlay/SCR-06 + REQ-080~082,121~122
- legacy Home/Dual Analysis/manual tracking: active UI 없음

## Development Handoff Checklist

### Frontend

- [ ] Splash 후 별도 Home 없이 Shared Input Shell로 진입한다.
- [ ] Tab 전환만으로 API-011/012가 호출되지 않는다.
- [ ] SCR-01/02에 Arrival/realtime metric이 없다.
- [ ] SCR-07/08에 targetArrivalAt/P(on_time)/Departure P50/P90이 없다.
- [ ] milestone list는 engine payload만 렌더링하고 FE에서 시간을 합산하지 않는다.
- [ ] milestone list가 길어져도 상단 result와 하단 `결과 공유하기/계산 근거`가 고정된다.
- [ ] result route의 analysisType mismatch를 다른 기능으로 변환하지 않는다.
- [ ] Share Create Overlay와 Public SCR-06을 구분한다.
- [ ] URL 복사 외 image/Kakao direct-send를 canonical CTA로 두지 않는다.
- [ ] Start/Event/Reforecast CTA/route/analytics가 없다.

### Backend/API

- [ ] API-011 Departure response에 Departure metrics + Departure milestone scenarios만 있다.
- [ ] API-012 request에 mandatory targetArrivalAt이 없고 response에 Arrival P50/P90 + Arrival milestones만 있다.
- [ ] API-012 user-facing P(on_time) field가 active schema에 없다.
- [ ] API-007이 immutable share projection + opaque URL metadata를 생성한다.
- [ ] API-008은 public read-only snapshot만 반환하고 owner 권한으로 승격하지 않는다.
- [ ] API-013 read가 immutable analysisType을 보존한다.
- [ ] one function result/session이 other function prerequisite가 아니다.

### Data/Probability

- [ ] Departure는 realtime feature를 사용하지 않는다.
- [ ] Arrival은 verified current feature만 사용한다.
- [ ] P50을 평균으로 처리하지 않는다.
- [ ] Departure milestone two-plan semantics와 Arrival checkpoint P50/P90 semantics를 혼동하지 않는다.
- [ ] raw route node를 사용자 milestone로 자동 승격하지 않는다.
- [ ] unverified leading vehicle/congestion/headway를 fabricated하지 않는다.
- [ ] model uplift 미달 시 baseline fallback한다.

## QA Acceptance Scenarios

| ID | Scenario | Expected |
|---|---|---|
| UI-AC-001 | app launch | APP-SPLASH 후 Shared Input Shell 진입, Service Home 0 |
| UI-AC-002 | Splash reduced-motion/asset fail | 정적 fallback 후 입력 가능, API/permission 선행 0 |
| UI-AC-003 | Tab switch | Departure↔Arrival UI 전환, analysis API 호출 0 |
| UI-AC-004 | Departure submit | API-011만 호출, SCR-02에 Departure P50/P90+milestones |
| UI-AC-005 | Departure contamination | Arrival/realtime/P(on_time) field 0 |
| UI-AC-006 | Arrival submit | API-012만 호출, target input 없이 SCR-08 Arrival P50/P90+milestones |
| UI-AC-007 | Arrival contamination | Departure/P(on_time)/targetArrivalAt field 0 |
| UI-AC-008 | same OD 두 기능 실행 | 별도 analysisId/result, 자동 연결 0 |
| UI-AC-009 | analysisType mismatch route | coercion 없이 recovery/error |
| UI-AC-010 | Departure milestone semantics | 보통=P50-plan median, 여유=P90-plan median |
| UI-AC-011 | Arrival milestone semantics | 보통=checkpoint P50, 여유=checkpoint P90 |
| UI-AC-012 | long milestone list | middle list만 scroll, summary/bottom actions 고정 |
| UI-AC-013 | milestone unsupported | fabricated time 0, nullable/limitation |
| UI-AC-014 | Departure Evidence | historical 근거만; realtime/model section 없음 |
| UI-AC-015 | Arrival Evidence | historical + 실제 사용 realtime/model만 |
| UI-AC-016 | share create | owner에서 API-007 URL 생성/복사 |
| UI-AC-017 | public share | token으로 SCR-06 read-only; owner 권한 0 |
| UI-AC-018 | share privacy | exact origin/raw ID/owner capability/other type metric 0 |
| UI-AC-019 | share expired/revoked | public error variant, cache resurrection 0 |
| UI-AC-020 | P50 copy | 평균 표현 0 |
| UI-AC-021 | retired scan | Service Home active, P(on_time), image/Kakao send, Dual Analysis, Start/Event/Reforecast 0 |
| UI-AC-022 | mobile compatibility | 두 Tab flow + URL share E2E 완주 |
| UI-AC-023 | offline | typed snapshot only; Arrival current 승격/Share queue 0 |
| UI-AC-024 | Future GPS | MR route/API/permission prompt 0 |

## Open Implementation Decisions

| Item | 현재 UI 계약 | Resolution Gate |
|---|---|---|
| Shared Input Tab deep-link encoding | TBD; route/query를 임의 고정하지 않음 | FE routing decision |
| Splash motion duration/easing | 수치 하드코드 금지, reduced-motion/static fallback | design implementation |
| historical bucket granularity | exact 수치/구간 하드코드 금지 | multi-window profile |
| support thresholds | rule 전 INSUFFICIENT | SUPPORT_RULE_V1 |
| Departure P50/P90 candidate grid | UI는 결과만 표시 | engine benchmark/CG |
| milestone selection rule | canonical route checkpoint만 | Route/Milestone rule version |
| milestone support threshold | unsupported는 시간 숨김/limitation | validation profile |
| realtime context categories | 실제 사용 category만 표시 | feature availability evidence |
| leading vehicle congestion/headway | 기본 미표시/미사용 | identity+timestamp+coverage experiment |
| AI model serving | fallbackUsed/modelVersion만 evidence | baseline uplift Gate |
| Share TTL | API expiresAt | G5 |
| Share public cache policy detail | no-store/no-referrer baseline | G5/security profile |
| exact breakpoints/SLO | 임의 수치 금지 | design/performance profile |
| Future GPS | MR UI/route 없음 | 별도 privacy/accuracy/battery research |

## 정본 정합성 규칙

- active Service Home route/CTA가 없어야 한다.
- APP-SPLASH는 transient presentation이며 SCR-00 historical ID를 재사용하지 않는다.
- SCR-01/07은 Shared Input Shell을 공유하지만 submit/API/result는 다르다.
- Departure result에는 Departure P50/P90 + Departure milestones만 존재한다.
- Arrival result에는 Arrival P50/P90 + Arrival milestones만 존재한다.
- Arrival active input/result에 mandatory targetArrivalAt/P(on_time)이 없다.
- 한 기능은 다른 기능의 result/session/API response를 prerequisite로 요구하지 않는다.
- milestone time은 engine projection이며 FE fabricated accumulation 0.
- Evidence/Share는 한 analysisType만 포함한다.
- Share Create Overlay와 Public SCR-06은 권한/목적이 다르다.
- URL Share가 canonical이며 image/Kakao direct-send active CTA가 없다.
- historicalCoverage는 공통, realtimeContextCoverage는 Arrival only다.
- unverified realtime feature를 사용했다고 표시하지 않는다.
- Future GPS/manual tracking은 active MR과 분리한다.

## Appendix — Screen 완료 정의

| Screen/State | Done |
|---|---|
| APP-SPLASH | brand presentation + reduced-motion/static fallback, API/permission prerequisite 0 |
| SCR-00 | v0.2 history only, active route 0 |
| SCR-01 | Shared Input Shell Departure state + future target + API-011 submit |
| SCR-02 | Departure metrics + scrollable milestones + fixed share/evidence actions |
| SCR-07 | Shared Input Shell Arrival state + now context + API-012 submit |
| SCR-08 | Arrival P50/P90 + realtime coverage + scrollable milestones + fixed actions |
| SCR-05 | parent analysisType의 evidence만 |
| OVL-SHARE-CREATE | owner URL create/copy |
| SCR-06 | token public read-only share result |
| SCR-03/04 | Future reserved, MR route/CTA 0 |

## Appendix — 금지 표현

- `한 번 입력하면 출발 시간과 도착 시간을 동시에 계산`
- `통합 분석`, `A/B Decision Result`를 active product 화면으로 표현
- `Home에서 두 기능 카드 선택`을 v0.3 active flow로 표현
- Departure 화면에서 `실시간 반영`
- Arrival 화면에서 targetArrivalAt/P(on_time)/Departure P50/P90 표시
- `P50 평균`, `P90 90% 정확`, `가장 안전한 출발시간`
- `AI가 최종 도착시간을 직접 계산`
- `경유지 시간을 화면에서 단순 합산해 계산`
- `모든 정류장/역을 milestone로 노출`
- `이미지 저장 및 카카오톡 전송`을 canonical Share로 표현
- `앞차 혼잡/거리 영향이 검증됨` — Evidence 전
- `GPS 자동 추적 가능` — Future Gate 전

