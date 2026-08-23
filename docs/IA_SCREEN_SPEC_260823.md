# Journey Reliability IA & 화면 정의서

> **문서 목적**: UX/UI, Frontend, Backend, Data, QA가 추가 해석 없이 화면·route·접근조건·상태·데이터·CTA·예외·복구를 구현하고 검증할 수 있도록 한다.  
> **문서 지위**: Service Plan의 하위 IA/Screen Contract 정본  
> **정본 파일명**: `IA_SCREEN_SPEC_260823.md`  
> **기준일**: 2026-08-23  
> **대상**: 독립형 Mobile-first PWA / 로그인 없는 Minimum Release  
> **상위 기준**: `SERVICE_PLAN_260823.md`  
> **하위 구현 기준**: `REQUIREMENTS_SPEC_260823.md`

---

## 0. 문서 사용법과 IA 단위

### 0.1 IA가 정의하는 것

이 문서는 사용자가 인지하는 화면과 화면 안의 상태, URL 진입점, overlay, 시스템 처리 상태를 분리한다. 화면 수와 route 수, domain state 수를 같은 개념으로 세지 않는다.

| 단위 | 정의 | 정본 수/범위 |
|---|---|---:|
| 사용자 화면 | 독립된 목적·정보 우선순위·종료조건을 가진 화면 | SCR-01~SCR-06, 6개 |
| 공통 Shell | 모든 화면이 공유하는 Header·main·feedback·footer 영역 | 1개 |
| Route entry | 새로고침·직접 접근이 가능한 URL | 5개 제안 + `/` |
| Overlay | 현재 화면 맥락을 유지하는 sheet/drawer/modal | SCR-04, SCR-05 variant |
| System state | 별도 화면이 아니라 현재 화면을 대체/보강하는 처리 상태 | ANALYZING, REFORECASTING, ERROR 등 |
| Journey domain state | Backend가 보존하는 여정/leg 상태 | PRE_TRIP_READY, ACTIVE, ARRIVED 등 |

### 0.2 화면 ID 정책

- `SCR-01~06`은 기능명이 바뀌어도 추적성을 위해 유지한다.
- SCR-04는 독립 URL이 아니라 SCR-03의 결과 sheet/panel이다.
- SCR-05는 desktop drawer 또는 route, mobile full-height bottom sheet로 구현할 수 있으나 동일 화면 ID와 데이터 계약을 쓴다.
- `Analyzing`, `Unsupported`, `Provider Error`, `Expired`를 임의 신규 SCR로 만들지 않는다.
- route path는 제안이며 Backend/Frontend convention 변경 시 ID·의미·guard·trace를 보존한다.

### 0.3 Source-of-truth 경계

| 질문 | 정본 |
|---|---|
| 왜 이 기능이 존재하는가, 무엇을 claim하는가 | Service Plan |
| 어디서 무엇을 보고 어떤 상태로 이동하는가 | 본 IA |
| 필드/API/엔티티/정상·예외·Acceptance의 상세 계약 | Requirements·API/Data contracts |
| 실제 검증 사실과 scope | Evidence Register·실험 reports |

---

## 1. IA 핵심 결정

| ID | 결정 | 구현 결과 |
|---|---|---|
| IA-001 | Minimum Release는 selected structural route 하나만 분석 | route alternatives ranking UI 없음; 모든 결과에 “이 경로 기준” scope 제공 |
| IA-002 | 핵심 결정정보는 목표시각→`P(on_time)`→P50/P90→Recommended Departure 순으로 계층화 | 기술 metadata보다 사용자 결정이 먼저 보임 |
| IA-003 | probability와 evidence sufficiency를 분리 | 확률 숫자 옆에 confidence/coverage/validation을 동일 값처럼 결합하지 않음 |
| IA-004 | `INSUFFICIENT/NOT_COMPUTED/UNSUPPORTED`는 서로 다른 상태 | 0% 또는 `--%` 하나로 통합 금지 |
| IA-005 | Transfer와 WAIT를 타임라인에서도 분리 | “도보 중” 하나로 합치지 않음 |
| IA-006 | user event CTA는 현재 active state와 candidate identity가 충족될 때만 노출 | `BUS_SKIPPED`를 상시 버튼으로 제공하지 않음 |
| IA-007 | Reforecast 중 이전 result를 참고용으로 남길 수 있으나 current 값처럼 보이지 않게 잠금 | CTA disable, processing label, stale/current 혼동 방지 |
| IA-008 | Evidence Detail은 일반 사용자층과 Developer/Demo metadata를 분리 | raw payload, secret, 내부 ID 기본 미노출 |
| IA-009 | Share는 privacy-safe immutable snapshot이며 Should | G5 TTL/보안 Gate 미통과 시 생성 CTA 제거 가능 |
| IA-010 | direct URL·새로고침은 server state로 복구 | local UI state만으로 Journey 정본을 만들지 않음 |
| IA-011 | provider failure와 data insufficiency를 구분 | retry 가능성과 입력 수정 CTA가 다름 |
| IA-012 | mobile에서 정보 삭제가 아니라 재배치 | 핵심 결과·상태·CTA·limitation은 모든 viewport에서 유지 |
| IA-013 | Recommended Departure는 AVAILABLE일 때만 시간 표시 | 현재 Claim Gate HOLD이면 unavailable component를 사용 |
| IA-014 | final arrival은 FINAL_WALK 완료 | 역/정류장 도착만으로 ARRIVED 처리 금지 |
| IA-015 | 일반 Journey route는 browser-bound owner capability 필요 | `journeyId`만으로 조회·mutation·Evidence·Share 생성 불가; 권한 없음은 resource 존재를 숨기는 recovery UX |
| IA-016 | Confidence는 Start gate가 아님 | `INSUFFICIENT`라도 USER_FACING·startEligibility 충족 시 경고 후 Start 허용 |
| IA-017 | Freshness는 critical source를 기준으로 Journey-level projection | mixed source 상태에서도 badge·CTA·retry가 결정적 |
| IA-018 | Route B는 내부 개발·QA 검증 전용 | 사용자 화면·공개 데모·public route에는 Route B selector나 진입점이 없음 |
| IA-019 | PWA 설치 여부는 기능 권한이나 결과 의미를 바꾸지 않음 | 모바일 브라우저와 standalone mode에서 SCR-01~05 핵심 flow 동등 |
| IA-020 | 오프라인은 live 계산 mode가 아님 | 마지막 privacy-safe snapshot만 `OFFLINE_SNAPSHOT`으로 읽고 Start·Event·Share mutation 차단 |
| IA-021 | foreground 복귀 시 서버 정본과 재동기화 | `RECONNECTING` 동안 이전 결과를 live/current로 승격하지 않고 mutation을 잠금 |
| IA-022 | Service Worker update가 진행 중 Journey를 훼손하지 않음 | 새 worker는 안전한 activation 시점까지 대기하고 강제 reload로 미전송 event를 잃지 않음 |
| IA-023 | 위치 권한은 명시적 사용자 행동에만 요청 | 권한 거부 시 수동 장소 입력으로 동일 flow 계속; background GPS 없음 |
| IA-024 | WALK provider 접근과 Journey route 지원 가능성을 분리 | Kakao WALK 호출 성공은 도보 거리·시간 provider evidence로만 사용한다. Kakao publictraffic 후보는 canonical mapping·시간 의미 Gate 전까지 결과 숫자나 selected route로 승격하지 않는다 |
| IA-025 | 공개 coverage 축을 숨기지 않음 | `routeCoverageMode`(서울 임의 OD 검색 가능·Route A는 검증된 우선순위 경로), `walkProviderMode`(`KAKAO_MAP_WALK`), `modelCoverage`(leg/route별 확률 계산 가능 여부)를 서로 다른 축으로 입력/결과/Evidence에 보존. 세 축을 하나의 enum으로 합치지 않는다 |
| IA-026 | canonical mapping 실패는 통신 오류가 아니라 별도 상태 | 임의 route candidate의 `mappingStatus`가 `PARTIAL/FAILED`이면 경로 구조는 표시하되 확률은 `NOT_COMPUTED`+사유로 표시하고 재시도 유도 문구를 쓰지 않는다 |

---

## 2. 전체 Information Architecture

```text
SCR-01 Journey Input  /
  ├─ INPUT_INVALID
  ├─ UNSUPPORTED_GEOGRAPHY
  ├─ ROUTE_NOT_FOUND / ROUTE_MAPPING_INCOMPLETE
  └─ ANALYZING
       ↓ success
SCR-02 Pre-trip Result  /journey/{journeyId}/plan
  ├─ Evidence Detail → SCR-05 drawer/sheet or route
  ├─ Share create → SCR-06 public URL (Should)
  ├─ Edit input → SCR-01
  └─ Journey Start
       ↓
SCR-03 Live Journey  /journey/{journeyId}/live
  ├─ BOARD_CONFIRMED
  ├─ BUS_SKIPPED
  ├─ TRANSFER_MISSED (rule enabled 시)
  ├─ REFORECASTING → SCR-04 result sheet
  ├─ Evidence Detail → SCR-05
  ├─ ARRIVED
  └─ ABORTED

PWA Runtime State (모든 owner screen에 직교)
  ├─ ONLINE
  ├─ RECONNECTING
  ├─ OFFLINE_SNAPSHOT (read-only)
  └─ UPDATE_AVAILABLE (safe activation)

SCR-06 Share Snapshot  /share/{token}
  ├─ VALID SNAPSHOT
  ├─ EXPIRED
  └─ INVALID / NOT_FOUND
```

### 2.1 Main Journey 전이

| From | Trigger | Preconditions | To | 실패 시 |
|---|---|---|---|---|
| SCR-01 | 분석 CTA | 입력 유효, 중복 요청 없음 | ANALYZING→SCR-02 | SCR-01 오류 state |
| SCR-02 | 이동 시작 | `resultEligibility=USER_FACING`, `startEligibility=ELIGIBLE`, route/state·owner capability 존재 | SCR-03 | start error, SCR-02 유지 |
| SCR-02 | 입력 수정 | 없음 | SCR-01 | 기존 snapshot은 수정하지 않음 |
| SCR-03 | UserEvent | active leg/state와 candidate 일치 | REFORECASTING | event error, current state 유지 |
| REFORECASTING | success | result version 증가 | SCR-04 | unavailable/error sheet |
| SCR-04 | 계속 이동 | 새 state 반영 완료 | SCR-03 | 중복 submit 금지 |
| SCR-03 | FINAL_WALK 완료 | active leg FINAL_WALK | ARRIVED variant | 실패 시 active 유지 |
| SCR-02/03 | Evidence | journey/result 접근 가능 | SCR-05 overlay | evidence unavailable 안내 |
| owner screen | 앱 foreground 복귀 | network 가능 | RECONNECTING→서버 최신 state 화면 | 실패 시 OFFLINE_SNAPSHOT 또는 provider/network error |
| owner screen | network 단절 | privacy-safe local snapshot 존재 | 현재 SCR read-only variant | snapshot 없으면 offline empty state |

---

## 3. Route Inventory와 Guard

| Route | Screen | 접근 조건 | 직접 접근/새로고침 | 실패 Redirect/처리 |
|---|---|---|---|---|
| `/` | SCR-01 | 없음 | 항상 가능 | 없음 |
| `/journey/{id}/plan` | SCR-02 | Journey/result 존재 + owner capability 일치 | API로 최신 plan/result 복구 | 권한 없음/not found는 동일 recovery; ACTIVE면 live 이동 제안 |
| `/journey/{id}/live` | SCR-03 | owner capability 일치 + Journey state가 ACTIVE/ARRIVED/ABORTED | state+active leg+result 복구 | PRE_TRIP_READY면 plan으로 redirect; 권한 없음/not found는 동일 recovery |
| `/journey/{id}/evidence` | SCR-05 route variant | owner capability 일치 + Journey/result 접근 가능 | evidence snapshot 복구 | 권한 없음/not found는 동일 recovery |
| `/share/{token}` | SCR-06 | valid opaque token | public snapshot 조회 | expired/invalid variant를 같은 route에 렌더 |

PWA standalone display mode에서도 URL 의미와 guard는 동일하다. 앱 아이콘 진입은 `/`을 기본 entry로 사용하며, owner capability가 확인된 active Journey가 있을 때만 “현재 여정 계속” entry를 제안한다. Service Worker navigation fallback은 권한 오류나 API 오류를 HTML shell 성공으로 숨기지 않는다.

### 3.1 Guard 우선순위

1. route parameter 형식 검증
2. owner capability 검증(`/share` 제외)
3. resource 존재 여부
4. state-screen compatibility
5. result/start eligibility
6. freshness/evidence 상태

`UNSUPPORTED`와 `INSUFFICIENT`는 redirect가 아니라 현재 화면의 의미 있는 상태다. Browser back은 mutation을 되돌리지 않는다. event 적용 뒤 back으로 SCR-03에 복귀하면 server의 최신 `stateVersion/resultVersion`을 다시 읽는다.

### 3.2 URL과 개인정보

- URL에 exact origin/destination coordinate, target service ID, probability를 넣지 않는다.
- Share URL에는 opaque token만 사용한다.
- 일반 route의 `{journeyId}`는 locator일 뿐 authorization credential이 아니다. owner capability가 없거나 불일치하면 존재 여부를 구분하지 않는 동일 응답과 복구 UX를 사용한다.
- owner capability는 URL, DOM, analytics, JavaScript-readable storage에 노출하지 않는다.
- 다른 브라우저/기기에서 owner Journey를 복구하는 기능은 Minimum Release에 없다. Share는 축약 snapshot 조회만 허용한다.
- SCR-01 위치 검색·현재 위치 좌표는 API-000(POST) body로만 전달하며 URL query, browser history, reverse-proxy/access log에 평문으로 남기지 않는다(REQ-100).
- Share 경로에는 `Referrer-Policy: no-referrer`를 적용해 token이 Referer 헤더로 외부에 유출되지 않게 하고, owner/Share 응답에는 `Cache-Control: no-store`를 적용한다.

---

## 4. Global Shell과 Navigation

### 4.1 Shell hierarchy

```text
AppShell
├─ Skip Link
├─ Header
│  ├─ Brand → 새 여정 확인 후 SCR-01
│  ├─ Current Journey Context (plan/live에서만)
│  └─ Data Status Summary (해당 시)
├─ Global Feedback Region (aria-live)
├─ Main
├─ PWA Runtime Region (offline/reconnect/update; 조건부)
└─ Footer / policy links (선택)
```

### 4.2 Header

| 요소 | SCR-01 | SCR-02 | SCR-03 | SCR-05 | SCR-06 |
|---|---|---|---|---|---|
| Brand | 표시 | 표시 | 표시 | parent 유지 | 표시 |
| 새 여정 | 불필요 | 표시 | 확인 modal 후 표시 | parent 기준 | 표시 가능 |
| Journey 목적지/목표시각 | 없음 | compact | compact | parent 기준 | destination/target만 |
| Live indicator | 없음 | 없음 | 실제 freshness 상태와 함께 | 없음 | 금지 |
| Share | 없음 | feature enabled 시 | feature enabled 시 | 없음 | 없음 |
| Network/PWA state | 조건부 | 조건부 | 항상 즉시 인지 가능 | parent 기준 | offline cache 여부만 |

“Live”는 `FRESH`이고 live source가 실제 사용된 경우에만 쓴다. recorded/cached result에는 쓰지 않는다.

### 4.3 Navigation 정책

로그인과 계정이 없으므로 복잡한 전역 메뉴는 두지 않는다. 핵심 이동은 `새 여정`, `현재 여정`, `근거 보기`, `공유`다. active Journey 이탈 시:

- 상태를 서버에 저장한 뒤 이동한다.
- 미전송 user event/reforecast가 있으면 이탈 확인을 표시한다.
- 단순 조회 상태에서는 불필요한 confirm을 띄우지 않는다.
- 설치 유도는 첫 task를 가리거나 필수 단계처럼 보이지 않게 하며, dismiss 후 반복 노출을 제한한다.
- OS 공유가 가능하면 native share sheet를 사용하고, 불가능하거나 실패하면 링크 복사를 제공한다.

### 4.4 Global feedback

- field error는 해당 field에 연결한다.
- page-level error는 main heading 직후 배치한다.
- event/reforecast 결과는 `aria-live=polite`; 위험한 stale/provider error는 즉시 인지 가능한 banner로 제공한다.
- toast만으로 critical failure를 전달하지 않는다.
- `OFFLINE_SNAPSHOT`, `RECONNECTING`, `UPDATE_AVAILABLE`은 화면별 데이터 상태와 구분되는 runtime banner로 제공한다.
- update activation이 안전하지 않으면 “이동 종료 후 업데이트”를 기본으로 하고, 즉시 갱신을 primary CTA로 강요하지 않는다.

---

## 5. 공통 데이터·표시 계약

### 5.1 화면 공통 Result View Model

| Field | Required/Nullable | 사용 화면 | null/부재 처리 |
|---|---|---|---|
| `journeyId` | required except Share | SCR-02~05 | 없으면 화면 성립 불가 |
| `routeCandidateId` | required internal | SCR-02~05 | mapping error |
| `routeManifestProvider` | required | SCR-02~05 | Minimum Release는 approved Route A manifest provider/hash; 없으면 contract error |
| `walkProvider` | required when WALK measured | SCR-02~05 | providerKey·endpoint category·adapter version·cache key; route provider와 병합 금지 |
| `routeSelectionPolicy` | required | SCR-02/05/06 | Minimum Release는 `APPROVED_DEMO_ROUTE`; future mode에서만 `PROVIDER_FIRST_SUPPORTED`; reliability ranking으로 번역 금지 |
| `routeCoverageMode` | required | SCR-01/02/05 | 서울 임의 OD 검색 가능 여부와 Route A 우선순위 범위(`ROUTE_A_PRIORITY/PROVIDER_SUPPORTED`); 화면 copy와 실제 deployment config 불일치 금지 |
| `walkProviderMode` | required | SCR-01/02/05 | `KAKAO_MAP_WALK/REFERENCE_ONLY/UNAVAILABLE`; route coverage와 독립(아래 `modelCoverage`와도 별도 축) |
| `routeMappingStatus` | required | SCR-01→02/05 | Route A manifest는 `MAPPED`; future provider candidate는 `MAPPED/INCOMPLETE/UNSUPPORTED`; MAPPED 외 사용자 probability 표시 금지 |
| `routeSummary` | required | SCR-02/03/05 | 없으면 `NOT_COMPUTED`가 아니라 analysis failure |
| `targetArrivalAt` | required | SCR-02/03/04/06 | 화면 성립 불가 |
| `targetReliability` | required | SCR-02/06 | Recommended label에 사용 |
| `p50ArrivalAt` | nullable | SCR-02/03/04/06 | card row 숨김+미계산 사유 |
| `p90ArrivalAt` | nullable | SCR-02/03/04/06 | card row 숨김+미계산 사유 |
| `onTimeProbability` | nullable | SCR-02/03/04/06 | 0과 null 구분; null은 `계산되지 않음` |
| `plannedConnectionSuccessProbability` | nullable | SCR-02/04 | 환승 없음 또는 미계산 reason 구분 |
| `recommendedDeparture.status` | required | SCR-02/06 | AVAILABLE/INSUFFICIENT_DATA/NOT_COMPUTED |
| `recommendedDeparture.at` | nullable | SCR-02/06 | AVAILABLE일 때만 required |
| `resultEligibility` | required | SCR-02~05 | USER_FACING 아니면 일반 결과 숫자 금지 |
| `metricEligibility` | required | SCR-02/05/06 | P50/P90/onTime/recommended 각각 `STRUCTURE_ONLY/DISTRIBUTION_AVAILABLE/PROBABILITY_AVAILABLE/CALIBRATED_CLAIM`; `resultEligibility`와 별도 축(§8.4.1) |
| `startEligibility` | required on SCR-02 | SCR-02 | ELIGIBLE/REFRESH_REQUIRED/BLOCKED + reasonCodes |
| `validationScope` | required | SCR-02/05/06 | end-to-end로 자동 번역 금지 |
| `confidence.label` | required | SCR-02/03/05 | rule 전 기본 INSUFFICIENT |
| `modelCoverage` | required | SCR-02/05/06 | PARTIAL이면 limitation 필수 |
| `fallbacks` | array, empty 가능 | SCR-05 | 빈 배열은 fallback 없음 |
| `limitations` | array, empty 가능 | SCR-02/05/06 | PARTIAL인데 비어 있으면 contract error |
| `freshness` | required | SCR-02/03/05 | FRESH/AGING/STALE/PROVIDER_ERROR/NO_DATA |
| `sourceFreshness[]` | required | SCR-02/03/05 | source/leg, criticality, state, lastSuccessAt; 전체 상태의 근거 |
| `calculatedAt` | required for result | SCR-02~06 | 없으면 result 표시 금지 |
| `resultVersion` | required | SCR-02~05 | reforecast 전후 비교·중복 방지 |

Provider provenance는 화면용 이름으로 합치지 않는다. 특히 `KAKAO_MOBILITY_WALK_LEGACY`, `KAKAO_MAP_WALK`, `KAKAO_MAP_PUBLIC_TRANSIT`는 서로 다른 providerKey로 Evidence Detail과 내부 QA에 전달한다. 일반 결과에는 읽기 쉬운 provider label을 병기할 수 있으나 원래 key·endpoint category·adapter version을 바꾸지 않는다. Kakao publictraffic은 Minimum Release 사용자 결과의 route provider가 아니라 reference evidence다.

### 5.2 숫자 formatting

- probability는 0~1 source를 whole percent로 표시하되 API 값과 rounding policy를 한 곳에서 통일한다.
- `0%`는 계산된 0일 때만 표시한다. null/unsupported/insufficient를 0%로 바꾸지 않는다.
- P50/P90는 KST 명시 또는 사용자에게 일관된 local time으로 표시한다.
- 날짜가 다음 날로 넘어가면 `다음 날` label을 붙인다.
- illustration 숫자는 디자인 fixture임을 별도 표시하며 production/demo와 혼합하지 않는다.

### 5.3 공통 probability copy

| Metric | Label | 도움말 |
|---|---|---|
| `P(on_time)` | `{target}까지 도착할 가능성` | 목표시각 기준 final arrival probability |
| P50 | `보통 도착 수준` | `현재 모델이 계산한 도착분포의 중앙값 시각` |
| P90 | `보수적 도착 수준` | `현재 모델이 계산한 도착분포의 90번째 백분위 시각` + validation limitation |
| Planned Connection | `계획한 환승 유지 가능성` | 다음 service 회복을 제외한 planned candidate 기준 |
| Recommended | `이 경로 기준 {p*}% 권장 출발` | selected route와 candidate service 재평가 조건부 |

금지: `정확도`, `보장`, `무조건`, `AI 예측`, `가장 안전한 경로/시간`.

“10번 중 약 9번” 같은 반복빈도 문구는 해당 화면과 Share가 end-to-end calibration 통과 scope임을 함께 증명할 때만 별도 승인한다. 기본 PWA copy에는 사용하지 않는다.

---

## 6. Global State Matrix

| State | 숫자 | Banner/본문 | Primary CTA | Retry/이탈 |
|---|---|---|---|---|
| LOADING/ANALYZING | 숨김 | skeleton+`경로와 도착 가능성을 계산하고 있어요.` | disabled | 중복 요청 차단; 입력으로 취소 가능 |
| FRESH | eligible 값 표시 | normal | state별 enabled | 필요 시 수동 새로고침 |
| AGING | 표시 | 계산시각+`업데이트가 필요할 수 있어요.` | 보통 enabled | `새로 계산/새로고침` 제공 |
| STALE | 마지막 값은 명확한 stale container 안에서만 | `마지막 성공: …, 현재 정보가 오래되었어요.` | Start/event는 정책상 disable 가능 | retry; 실패하면 stale 유지 |
| PARTIAL_MODEL | Gate가 허용한 값만 | `일부 구간의 변동성은 포함되지 않았어요.` | eligible이면 enabled | Evidence CTA 필수 |
| LOW_SUPPORT | calibrated rule이 있을 때만 | `현재 표본이 적어 결과가 달라질 수 있어요.` | 정책상 enabled/disabled | Evidence CTA |
| INSUFFICIENT | USER_FACING이면 값+근거 경고, NOT_COMPUTED면 숨김 | `현재 근거 수준이 충분하지 않아요.` | `startEligibility`에 따름; confidence만으로 차단 금지 | 근거 보기/later retry |
| NOT_COMPUTED | null | missing critical source/reason | Start disabled | retry 또는 입력 수정 |
| UNSUPPORTED | 숨김 | 지원 범위/해석 불가 사유 | `입력 수정` | 동일 요청 자동 retry 금지 |
| PROVIDER_ERROR | stale snapshot만 분리 표시 | provider raw body 없는 오류 | `다시 시도` 또는 disabled | retryable metadata 반영 |
| REFORECASTING | 이전 값 dim+`이전 결과` label | `새 상황을 반영하고 있어요.` | event CTA 모두 disabled | 중복 event 차단 |
| REFORECAST_UNAVAILABLE | 새 값 없음 | `다음 이동편을 계산할 근거가 없어요.` | `현재 여정으로 돌아가기` | retry 가능 시 제공 |
| OFFLINE_SNAPSHOT | 마지막 privacy-safe 값만 | `오프라인 저장본 · {savedAt}`; live/fresh 표현 금지 | mutation disabled, 연결 복구 | 앱 shell만 있고 snapshot 없으면 empty state |
| RECONNECTING | 이전 값 dim+저장/계산시각 | `최신 이동 상태를 확인하고 있어요.` | Start/Event/Share disabled | 성공 시 server version, 실패 시 offline/error |
| UPDATE_AVAILABLE | 현재 값 유지 | 안전한 업데이트 가능 시만 안내 | `나중에` 기본, 안전할 때 `업데이트` | active mutation 중 activation 금지 |

### 6.1 상태 합성 우선순위

상태가 동시에 존재할 때 우선 표시한다.

`UNSUPPORTED/NOT_COMPUTED > PROVIDER_ERROR/STALE > PARTIAL_MODEL > AGING > FRESH`

이 순서는 core display state projection에만 적용한다. Confidence(`INSUFFICIENT/LOW/MEDIUM/HIGH`)와 Validation Scope는 별도 영역에 항상 유지한다. `PARTIAL_MODEL`과 `INSUFFICIENT`가 동시에 존재할 수 있으며 하나의 색 배지로 덮지 않는다.

### 6.2 Source freshness → Journey freshness

| Critical source 상태 | Journey projection | Metric | Start/Event |
|---|---|---|---|
| usable input 없음 + `NO_DATA/PROVIDER_ERROR` | `NOT_COMPUTED` 또는 `PROVIDER_ERROR` | 새 값 없음; last success 분리 | 차단 |
| 하나 이상 `STALE` | `STALE` | stale container의 snapshot만 | Start는 `REFRESH_REQUIRED`; live event는 provider-specific safety policy |
| stale/error 없음, 하나 이상 `AGING` | `AGING` | 표시 | 기본 허용, refresh 제공 |
| 모두 `FRESH` | `FRESH` | 표시 | eligibility에 따름 |
| non-critical source만 실패 | core projection 유지 | 해당 row unavailable | core CTA 유지 |

Criticality는 Backend가 `CRITICAL_CALCULATION/NON_CRITICAL_CONTEXT`로 제공하며 Frontend가 source 종류를 보고 재추론하지 않는다. `PARTIAL_MODEL`, confidence, validation은 이 표와 별도 축이다.

---

## 7. SCR-01 — Journey Input

### 7.1 목적·접근·종료

| 항목 | 계약 |
|---|---|
| 목적 | 출발지·목적지·목표 도착시각·목표 reliability를 받아 분석 가능한 JourneyRequest 생성 |
| Entry | 최초 접속, 새 여정, 입력 수정, route/unsupported 실패 후 복귀 |
| Access | public |
| Success Exit | SCR-02 |
| Failure Exit | 없음; SCR-01에서 오류 해결 |

### 7.2 Component hierarchy

```text
SCR-01
├─ Page Intro
├─ Analysis Error Banner (conditional)
├─ Journey Form
│  ├─ Origin Field + resolver status + Current Location action
│  ├─ Destination Field + resolver status
│  ├─ Target Arrival Date/Time
│  └─ Target Reliability Control
├─ Scope Notice
│  ├─ coverageMode
│  └─ provider-supported limitation
└─ Primary CTA
```

### 7.3 Data dependencies

| Field | Required | 상태/검증 | Analytics 제한 |
|---|---|---|---|
| origin label+coordinate | yes | resolve 성공, coordinate role=ORIGIN_POINT | exact coordinate 저장 금지 |
| destination label+coordinate | yes | resolve 성공, role=POI/입력 provenance | exact coordinate 저장 금지 |
| targetArrivalAt | yes | timezone-aware, 과거 금지 | time bucket만 가능 |
| targetReliability | yes | 기본 0.90; UI 옵션은 구현 config | 값 저장 가능 |
| coverageMode | yes | server deployment config; UI가 임의 추론 금지 | mode만 가능 |

`현재 위치 사용`은 origin field의 보조 action이다. click 전 권한을 요청하지 않으며, 허용되면 foreground one-shot coordinate를 `ORIGIN_POINT` provenance와 함께 resolver에 전달한다. 거부·timeout·미지원은 field 오류가 아니라 안내 후 수동 입력을 유지한다.

사용자는 서울 안에서 임의의 출발지·목적지를 입력할 수 있다(`geographyCoverage`/`routeSearchCoverage`, REQ-104). 입력 전에 “서울 안 어디든 검색할 수 있지만, 경로에 따라 확률 계산 근거가 아직 부족할 수 있어요.”를 안내해 mapping/model coverage에 따라 결과가 달라질 수 있음을 미리 공개한다. `검증 완료된 데모 경로` badge가 붙은 Route A는 별도 preset/shortcut으로 제공할 수 있으나 입력 자체를 Route A로 제한하지 않는다. 임의 후보의 canonical mapping이 `PARTIAL/FAILED`이면 SCR-02에서 경로 구조는 보여주되 확률은 계산하지 않고 사유를 함께 표시한다(REQ-104, AC-061). 도보 구간은 Kakao WALK provider로 측정될 수 있음을 Evidence에 남긴다. Kakao 등 provider 호출 성공과 canonical mapping 성공은 항상 분리하며, mapping 실패를 일반 통신 오류로 바꾸지 않는다.

### 7.4 입력·CTA 계약

Primary CTA: `도착 가능성 계산`

Enabled 조건:

- 네 필드 유효
- origin/destination resolve 완료
- 동일 장소 아님
- 분석 요청 in-flight 아님

Click 시 입력 snapshot을 고정하고 중복 submit을 막는다. CTA가 disabled인 이유는 field-level로 알 수 있어야 한다.

### 7.5 Validation과 상태

| Condition | Copy | CTA |
|---|---|---|
| field empty/invalid | field별 구체 오류 | 수정 전 disabled |
| 동일 장소 | `출발지와 목적지를 다르게 입력해 주세요.` | disabled |
| 과거 목표시각 | `현재 이후의 도착시각을 선택해 주세요.` | disabled |
| resolve failure | `장소를 확인하지 못했어요. 다시 검색해 주세요.` | retry resolve |
| unsupported geography | `현재 서울 내 지원 범위에서만 분석할 수 있어요.` | `입력 수정` |
| route not found | `분석할 수 있는 대중교통 경로를 찾지 못했어요.` | 입력 수정/다시 시도 |
| mapping incomplete | `경로는 찾았지만 현재 분석에 필요한 정류장·노선 정보를 연결하지 못했어요.` | 입력 수정 |
| route/provider error | `교통 경로 정보를 불러오지 못했어요.` | retryable이면 `다시 시도` |
| provider entitlement/quota unavailable | `현재 새 경로를 조회할 수 없어요. 잠시 후 다시 시도해 주세요.` | 즉시 반복 retry 금지; 승인 Route A entry가 있을 때만 별도 제안 |

ANALYZING 중 probability, 임시 route, 가짜 progress %, 예상 완료시간을 표시하지 않는다.

### 7.6 Responsive·Accessibility

- Mobile: one-column, keyboard가 CTA/오류를 가리지 않음, sticky CTA는 safe-area 반영.
- Tablet/Desktop: form 최대 폭을 제한하고 scope notice를 인접 배치.
- 장소 suggestion은 keyboard 탐색, active descendant, loading/no-result를 지원한다.
- 날짜/시간 field는 label과 timezone context를 제공한다.

### 7.7 Analytics

| Event | Trigger | Required properties |
|---|---|---|
| `journey_input_view` | 화면 진입 | entry_source |
| `journey_analyze_click` | valid submit | target_reliability, target_time_bucket |
| `journey_input_validation_error` | submit/blur error | field, reason_code |
| `journey_analysis_failed` | API/domain failure | reason_code, retryable |

### 7.8 Acceptance

- 잘못된 입력이 API submit되지 않는다.
- unsupported와 route/provider error가 다른 copy/CTA를 쓴다.
- 중복 클릭이 중복 Journey를 만들지 않는다.
- exact coordinate가 analytics/log UI에 노출되지 않는다.

---

## 8. SCR-02 — Pre-trip Result

### 8.1 목적·접근·종료

| 항목 | 계약 |
|---|---|
| 목적 | selected route의 deadline risk와 근거를 이해하고 출발 여부 결정 |
| Entry | SCR-01 분석 성공, direct route 복구 |
| Access | PRE_TRIP_READY result snapshot 존재 |
| Success Exit | Journey Start→SCR-03 |
| Other Exit | 입력 수정→SCR-01, Evidence→SCR-05, Share 생성 |

### 8.2 Component hierarchy

```text
SCR-02
├─ Result State Banner
├─ Target Header
├─ Primary Decision Card
│  ├─ On-time Probability
│  ├─ P50 / P90 Rows
│  ├─ Recommended Departure
│  └─ Calculation Time
├─ Selected Route Scope Notice
├─ Route Timeline
├─ Connection Card (conditional)
├─ Evidence Summary
│  ├─ Confidence
│  ├─ Model Coverage
│  ├─ Validation Scope
│  └─ Limitation Preview
└─ Action Bar
```

### 8.3 정보 우선순위

1. 목표 도착시각
2. `P(on_time)` 또는 계산불가 상태
3. P50/P90
4. Recommended Departure status
5. selected route와 leg sequence
6. Planned Connection Success
7. evidence sufficiency·coverage·validation

### 8.4 Result eligibility별 렌더링

| Eligibility/State | Metric Card | Route | Evidence | Journey Start |
|---|---|---|---|---|
| USER_FACING + FRESH | 값 표시 | 표시 | summary+detail link | enabled |
| USER_FACING + PARTIAL | 허용 값+critical limitation | 표시 | prominent | `startEligibility=ELIGIBLE`이면 경고 후 enabled |
| ENGINE_FIXTURE_ONLY | 일반 사용자 route에서 숫자 표시 금지 | dev 환경만 | fixture 명시 | disabled |
| NOT_COMPUTED | 숫자 대신 reason | 가능하면 structural route 표시 | missing source/limitation | disabled |
| USER_FACING + INSUFFICIENT | 값+근거 부족 경고 | 표시 | support reason prominent | confidence만으로 차단하지 않음 |
| NOT_COMPUTED + INSUFFICIENT | 확률 숨김/미계산 문구 | 표시 가능 | missing input+support reason | disabled |
| STALE | stale container에 이전 값 | 표시 | calculatedAt/freshness | 새로 계산 전 disabled 가능 |

### 8.4.1 Metric별 Claim Eligibility

`resultEligibility`가 `USER_FACING`이어도 P50/P90/`P(on_time)`/Recommended Departure는 서로 다른 `metricEligibility`를 가질 수 있다. metric card는 값 표시 여부뿐 아니라 아래 자격에 따라 문구를 달리한다.

| `metricEligibility` | 카드 표시 |
|---|---|
| `STRUCTURE_ONLY` | 경로 구조·reference time만 표시, 확률 숨김 |
| `DISTRIBUTION_AVAILABLE` | P50/P90 표시, "모델 출력" 문구, calibration claim 문구 금지 |
| `PROBABILITY_AVAILABLE` | `P(on_time)` 표시, observation/coverage 경고 필수 |
| `CALIBRATED_CLAIM` | validation scope(V3)가 명시된 신뢰도 문구 허용 |

같은 결과 안에서 P50은 `DISTRIBUTION_AVAILABLE`, Recommended Departure는 `STRUCTURE_ONLY`처럼 metric마다 다를 수 있으며, 한 metric의 등급을 다른 metric에 전이하지 않는다.

### 8.5 Recommended Departure

| Status | UI |
|---|---|
| AVAILABLE | `이 경로 기준 {p*}% 권장 출발` + time + 계산시각 |
| INSUFFICIENT_DATA | `권장 출발시각을 계산할 근거가 아직 부족해요.` |
| NOT_COMPUTED | `권장 출발시각을 계산하지 않았어요.` + reason if available |

AVAILABLE인데 `at=null`이면 contract error로 전체 시간을 숨기고 오류를 계측한다. 현재 Claim Gate가 HOLD이면 UI fixture라도 AVAILABLE로 기본 설정하지 않는다.

### 8.6 Route Timeline

Leg sequence를 다음 label로 구분한다.

- `출발지에서 첫 탑승점까지 걷기`
- `버스/지하철 대기`
- `{route/line} 이동`
- `버스→지하철 / 지하철→지하철 / 지하철→버스 환승`
- `목적지까지 마지막 도보`

각 leg는 source/reference가 있더라도 일반 timeline에서 raw sample count를 강제 노출하지 않는다. `STATION_CENTER` 기반 final walk이면 “역 출구 기준”으로 쓰지 않는다.

### 8.7 Connection Card

환승이 하나 이상 있고 field가 계산된 경우만 표시한다. null일 때 `0%`로 렌더하지 않는다. `계획한 환승 유지 가능성`과 `최종 정시 도착 가능성`을 나란히 보여주되 설명 tooltips를 분리한다.

### 8.8 CTA 계약

| CTA | Preconditions | Disabled/Hidden |
|---|---|---|
| `이 경로로 이동 시작` | USER_FACING, `startEligibility=ELIGIBLE`, journey state PRE_TRIP_READY, owner capability valid | NOT_COMPUTED/fixture/unsupported/REFRESH_REQUIRED/BLOCKED |
| `계산 근거 보기` | evidence endpoint 또는 summary 존재 | 없으면 disabled가 아니라 unavailable explanation |
| `새로 계산` | AGING/STALE/provider recovery | request 중 disabled |
| `입력 수정` | 항상 | 없음 |
| `공유` | feature enabled, snapshot eligible, security Gate 통과 | Should cut 시 hidden |

### 8.9 상태별 Copy

- PARTIAL: `일부 구간은 기준 소요시간을 사용했고 변동성이 포함되지 않았어요.`
- USER_FACING + INSUFFICIENT: `현재 근거 수준은 충분하지 않지만, 사용 가능한 입력으로 계산한 결과예요. 한계를 확인하고 이동을 시작할 수 있어요.`
- NOT_COMPUTED + INSUFFICIENT: `이 경로의 도착 가능성을 계산할 입력과 근거가 아직 충분하지 않아요.`
- STALE: `이 결과는 {calculatedAt} 기준이에요. 최신 교통정보로 다시 계산해 주세요.`
- PROVIDER_ERROR with prior result: `교통정보를 새로 불러오지 못했어요. 아래 값은 마지막 계산 결과예요.`

### 8.10 Responsive·Accessibility

- Mobile first viewport: target, on-time state/value, P50/P90, Recommended status, critical limitation, primary CTA.
- Desktop: left decision/result, right route/evidence; reading order는 DOM에서 decision→route→evidence.
- probability change/importance를 색과 animation만으로 표현하지 않는다.
- metric abbreviation에는 accessible description을 연결한다.

### 8.11 Analytics·Acceptance

Events: `pretrip_result_view`, `journey_start_click`, `evidence_open`, `share_click`, `recommended_departure_unavailable`, `result_refresh_click`.

Acceptance:

- P50/P90/on-time/connection이 의미·label·null 처리에서 분리된다.
- selected route 조건이 화면에서 사라지지 않는다.
- PARTIAL/INSUFFICIENT/STALE이 badge 하나가 아니라 copy와 행동을 바꾼다.
- prohibited claim과 mock probability가 없다.

---

## 9. SCR-03 — Live Journey

### 9.1 목적·접근·종료

| 항목 | 계약 |
|---|---|
| 목적 | 현재 active leg, 완료/미래 여정, 남은 정시 가능성, 가능한 사용자 행동 제공 |
| Entry | Journey Start, direct live 복구, SCR-04 닫기 |
| Access | ACTIVE/REFORECASTING/ARRIVED/ABORTED |
| Exit | ARRIVED/ABORTED, 새 여정, Evidence/Share |

### 9.2 Component hierarchy

```text
SCR-03
├─ Live/Freshness Banner
├─ Destination & Target
├─ Current Result Summary
├─ Active Leg Card
│  ├─ Mode/Transfer/Wait label
│  ├─ Current candidate (nullable)
│  ├─ Last source update
│  └─ Contextual CTA
├─ Journey Timeline
│  ├─ Completed
│  ├─ Active
│  └─ Future
├─ Limitation/Evidence Link
└─ Terminal Action (conditional)
```

### 9.3 Live data dependencies

| Field | Required/Nullable | 규칙 |
|---|---|---|
| journey state/stateVersion | required | mutation 후 증가 확인 |
| activeLeg | nullable only terminal | ACTIVE인데 null이면 error |
| completedLegIds | required array | 완료 상태 재샘플링 금지의 UI 근거 |
| candidateServiceId | nullable | BUS_SKIPPED/BOARD CTA 조건 |
| observedState | nullable | 일반화된 copy로 표시 가능 |
| freshness/lastSuccessfulAt | required | live label과 CTA 결정 |
| current result snapshot | nullable in reforecast failure | previous/current version 구분 |

### 9.4 Timeline 상태

| Domain state | UI |
|---|---|
| COMPLETED | check+실제/확정 완료시각이 있으면 표시; 수정 CTA 없음 |
| IN_PROGRESS | 강조, active heading, contextual CTA |
| AVAILABLE/PLANNED | future style; 현재 확정처럼 표현 금지 |
| SKIPPED | 대상 candidate에만 적용; required bus ride는 future에 유지 |
| MISSED | planned connection miss label; 다음 service path가 있으면 유지 |
| UNAVAILABLE | 해당 leg와 reason 표시; 조용히 timeline에서 제거 금지 |

Transfer와 Wait는 별도 row다. `BUS_TO_SUBWAY` transfer 뒤에 `SUBWAY_WAIT`, `SUBWAY_TO_BUS` transfer 뒤에 `BUS_WAIT`가 이어진다.

### 9.5 Contextual CTA

| Active state | CTA | Preconditions | 결과 |
|---|---|---|---|
| BUS_WAIT | `탑승했어요` | identifiable candidate | BOARD_CONFIRMED |
| BUS_WAIT | `이번 버스는 보내요` | candidateServiceId 존재, FRESH/정책상 valid | BUS_SKIPPED |
| SUBWAY_WAIT | `탑승했어요` | identifiable candidate | BOARD_CONFIRMED |
| BUS_RIDE/SUBWAY_RIDE | `하차했어요` | active leg RIDE, target node 도달 가능 | RIDE_COMPLETED, 다음 TRANSFER/WAIT/FINAL_WALK 진입 |
| TRANSFER | `환승 완료` (Should) | user confirmation 정책 enabled | active state 진행 |
| WAIT/TRANSFER | `환승을 놓쳤어요` | Tier-0 rule/confirmation enabled | TRANSFER_MISSED |
| FINAL_WALK | `목적지에 도착했어요` | active leg FINAL_WALK | ARRIVED |
| ANY ACTIVE | `여정 종료` | owner capability valid, user confirmation | ABORTED(API-010) |

BUS_SKIPPED copy는 개인의 탑승 실패를 추론하지 않는다. candidate가 없거나 stale/provider error면 hidden/disabled하고 이유를 보여준다. 모든 mutation CTA는 idempotency key를 포함하고 in-flight 동안 전체 event CTA를 disable한다. `여정 종료`는 실수 클릭을 막기 위해 confirm dialog를 거친 뒤에만 API-010을 호출한다.

### 9.6 Freshness/Provider failure

- FRESH: source update 시각과 현재 계산시각을 구분해 제공.
- AGING: 현재 값은 표시하되 update notice.
- STALE: `마지막 교통정보 업데이트: …`; live dot 제거; event CTA 정책상 disable.
- PROVIDER_ERROR: 마지막 결과가 있어도 “현재”처럼 유지하지 않음. retry 가능 여부 표시.
- NO_DATA: 현재 candidate를 만들지 않으며 user event CTA 숨김.

### 9.7 Journey recovery

새로고침·다른 탭 재진입 시 server state를 복구한다. local optimistic state와 server `stateVersion`이 다르면 server를 우선하고 사용자에게 `여정 상태가 업데이트되었어요.`를 알린다. 같은 event의 재시도는 중복 result를 만들지 않는다.

화면이 background에서 foreground로 돌아오면 즉시 `RECONNECTING`으로 전환해 Journey와 result version을 재조회한다. 동기화가 끝나기 전 `BOARD_CONFIRMED`, `BUS_SKIPPED`, `TRANSFER_MISSED`, Share 생성은 잠근다. 네트워크가 없으면 privacy-safe last snapshot을 `OFFLINE_SNAPSHOT`으로만 보여주며, offline 상태에서 발생한 mutation을 성공한 것처럼 queue하지 않는다.

### 9.8 Terminal variants

ARRIVED는 FINAL_WALK 완료 뒤에만 표시한다. ABORTED는 실패가 아니라 사용자가 여정을 종료한 상태일 수 있으므로 중립적으로 설명한다. terminal에서는 live polling과 event CTA를 중지한다.

### 9.9 Responsive·Accessibility

- Mobile: active leg와 CTA를 먼저, vertical timeline, sticky event action은 두 개를 넘지 않음.
- Tablet/Desktop: current summary+active card와 timeline 2-column 가능.
- status 변화는 focus를 강제로 이동시키지 않고 aria-live로 알림.
- CTA label은 mode/candidate context를 accessible name에 포함.

### 9.10 Analytics·Acceptance

Events: `live_journey_view`, `board_confirmed`, `bus_skipped`, `transfer_missed`, `live_provider_stale`, `journey_arrived`, `event_rejected`.

Acceptance:

- completed/active/future leg가 시각·텍스트로 구분된다.
- WAIT/TRANSFER가 합쳐지지 않는다.
- candidate 없는 BUS_SKIPPED CTA가 없다.
- stale/error에서 last result가 fresh로 보이지 않는다.
- FINAL_WALK 전 ARRIVED 처리되지 않는다.

---

## 10. SCR-04 — Reforecast Result Overlay

### 10.1 목적·형태

사용자 사건 또는 source state 변화가 남은 Journey에 어떤 영향을 주었는지 before/after와 reason으로 설명한다. Mobile은 bottom sheet/full-height sheet, desktop은 side panel/modal을 사용한다. 독립 history page가 아니다.

### 10.2 Trigger와 lifecycle

`Event submit → REFORECASTING → success/unavailable/error → SCR-04 → continue → SCR-03`

REFORECASTING 중:

- 이전 result는 `이전 결과` label로 dim 가능.
- 모든 event CTA와 overlay dismiss를 정책상 제한한다.
- 가짜 progress와 임시 delta를 표시하지 않는다.

### 10.3 Data contract

| Field | Required | 규칙 |
|---|---|---|
| reasonCode | yes | AI 문구보다 우선 |
| eventType/occurredAt | yes | user-confirmed fact |
| previousResultVersion | yes | before 기준 |
| newResultVersion | success 시 yes | previous보다 커야 함 |
| before metrics | nullable | 이전에 계산된 값만 |
| after metrics | nullable | 새로 계산된 값만 |
| reforecastStatus | yes | SUCCESS/UNAVAILABLE/FAILED |
| limitations | array | 새 결과의 한계 |

### 10.4 Before/After 표시

같은 metric이 양쪽에 존재할 때만 arrow/delta를 표시한다. 한쪽 null이면 `이전/새 결과 없음`으로 설명한다. probability delta는 percentage point로 정의하고 percent change와 혼동하지 않는다.

### 10.5 Reason copy

| Reason | 기본 문구 |
|---|---|
| BUS_SKIPPED_NEXT_SERVICE | `이번 버스를 보내 다음 버스 대기부터 남은 여정을 다시 계산했어요.` |
| BOARD_CONFIRMED | `실제 탑승을 반영해 남은 여정을 다시 계산했어요.` |
| TRANSFER_MISSED | `계획한 환승을 놓쳐 다음 이동편부터 다시 계산했어요.` |
| SOURCE_STATE_UPDATE | `새 교통정보를 반영해 남은 여정을 다시 계산했어요.` |
| REFORECAST_UNAVAILABLE | `다음 이동편을 구성할 근거가 없어 새 결과를 계산하지 못했어요.` |

`BUS_SKIPPED` 후 required bus ride가 사라졌다고 암시하는 copy를 쓰지 않는다. 생성형 AI 설명은 reason code와 result metadata를 보조할 뿐 대체하지 않는다.

### 10.6 CTA

- SUCCESS: `계속 이동하기` → SCR-03 current state.
- UNAVAILABLE: `현재 여정으로 돌아가기`, retryable이면 `다시 계산`.
- FAILED: retryable에 따라 `다시 시도`; event가 적용됐는지 불명확하면 state를 먼저 refetch.

### 10.7 Accessibility·Acceptance

- overlay open 시 heading으로 focus, close 후 trigger/active card로 복귀.
- ESC/back 동작은 mutation 진행 중 차단 이유를 알림.
- before/after를 색상·arrow만으로 구분하지 않음.
- completed history가 UI와 API에서 변하지 않고, skipped candidate만 제거되며 next WAIT+same RIDE가 timeline에 존재한다.

Events: `reforecast_started`, `reforecast_success`, `reforecast_unavailable`, `reforecast_failed`, `reforecast_result_closed`.

---

## 11. SCR-05 — Evidence Detail

### 11.1 목적·접근

사용자가 result를 맹신하지 않고 어떤 구간이 실측·reference·fallback·unmodeled인지 이해하도록 한다. SCR-02/03에서 열며 route 직접 접근도 가능하다. Evidence가 없다는 사실도 의미 있는 상태로 표시한다.

### 11.2 Information hierarchy

```text
SCR-05
├─ Result Scope Summary
│  ├─ Selected route / corridor
│  ├─ Calculated at / freshness
│  ├─ Validation scope
│  └─ Model coverage
├─ User-facing Limitation Summary
├─ Leg Evidence List
│  └─ source / semantics / support / fallback / coordinate role
├─ Probability Meaning
└─ Developer/Demo Detail (environment/permission conditional)
```

### 11.3 Leg evidence required/nullable

| Field | Required/Nullable | 표시 원칙 |
|---|---|---|
| leg label/type/mode | required | 사용자 언어 우선 |
| source type/name | required for computed/reference | provider internal API name은 detail |
| route manifest provider/hash | required result-level | Minimum Release는 approved Route A manifest provider/hash/version; Kakao publictraffic provider로 오표시 금지 |
| WALK provider/version | required when WALK measured | `KAKAO_MAP_WALK` 등 실제 WALK source와 adapter/cache version; route manifest와 병합 금지 |
| route selection/mapping | required result-level | approved demo 또는 future provider-first, crosswalk version과 mapping scope; future provider mode가 아니면 mapping Gate를 selected route 근거로 표시하지 않음 |
| value semantics | required | duration/wait/residual/point/reference 구분 |
| support count/window | nullable | independent unit이 확정된 값만; raw poll row를 support로 오인 금지 |
| fallback level | nullable | 사용 시 반드시 표시 |
| confidence | required | `SUPPORT_RULE_V1` 전 INSUFFICIENT |
| uncertainty coverage | required | MODELED/PARTIAL/UNMODELED |
| validation scope | required result-level, optional leg-level | component와 E2E 분리 |
| coordinate role/source | WALK/TRANSFER required | STATION_CENTER를 EXIT로 번역 금지 |
| artifact/rule version | dev/demo only | 일반 사용자는 생략 가능 |

### 11.4 User-facing leg copy 예

| 구간 | 표시 |
|---|---|
| ACCESS WALK | `보행 경로의 기준 소요시간을 사용했으며 시간 변동성은 포함되지 않았어요.` |
| 01A BUS | 실제 runtime metadata에 따른 support/fallback; mature claim 금지 |
| 안국 BUS→SUBWAY | `정류장→역 참조지점 보행은 확인했지만 역 내부 이동시간은 모델링되지 않았어요.` |
| 교대 3→2 | `공식 환승 기준시간을 사용했으며 개인별 변동성은 포함되지 않았어요.` |
| FINAL WALK | `역삼역 중심 참조지점에서 목적지까지의 보행 기준값이에요. 출구 기준은 아니에요.` |

### 11.5 상태별 UX

- PARTIAL_MODEL: 모델링되지 않은 leg 수/목록 제공.
- LOW_SUPPORT: calibrated rule이 있을 때 표본 단위·기간을 함께 제공.
- INSUFFICIENT: 왜 confidence를 승격하지 않았는지 표시.
- STALE: 어떤 source/artifact가 오래됐는지 구분.
- PROVIDER_ERROR: raw error body 대신 provider category, last success, retryability.
- Evidence endpoint failure: parent result는 유지하고 `근거 상세를 불러오지 못했어요.` + retry.

### 11.6 Developer/Demo Mode

허용: sample unit/count, observation window, fallback/rule/artifact/distribution version, simulation run ID, seed/N, validation scope, coordinate provenance, raw reference ID.  
금지: API key, auth header, exact private origin, provider raw payload 전체, production internal topology.

Developer mode가 없어도 사용자-facing limitations는 항상 접근 가능해야 한다.

### 11.7 CTA·Responsive·Accessibility

- CTA: `결과로 돌아가기`, `상세 다시 시도`.
- Mobile: sections accordion/bottom sheet; critical limitation은 collapsed 안쪽에만 숨기지 않음.
- Desktop: summary fixed column+leg list.
- 용어에는 plain-language 설명; 표는 screen reader caption/header 제공.

Events: `evidence_open`, `evidence_leg_expand`, `evidence_retry`, `developer_evidence_open`.

Acceptance:

- probability/confidence/validation scope가 서로 다른 항목으로 표시된다.
- WAIT snapshot raw rows를 독립 support로 표현하지 않는다.
- coordinate provenance와 `UNMODELED_UNCERTAINTY`가 WALK/transfer에서 보인다.
- raw secret·private coordinate가 없다.

---

## 12. SCR-06 — Share Snapshot

### 12.1 목적·범위

동행/약속 상대에게 계산 당시의 축약된 도착 전망을 전달한다. live tracking page가 아니며 원본 Journey의 변화를 자동 반영하지 않는 immutable snapshot이다.

### 12.2 Access variants

| Variant | 조건 | UI |
|---|---|---|
| VALID | token valid, snapshot 존재 | snapshot 표시 |
| EXPIRED | 만료 | `공유 링크가 만료되었어요.` |
| INVALID/NOT_FOUND | token invalid/삭제 | `공유 결과를 찾을 수 없어요.` |
| PROVIDER-independent | 원본 provider 현재 장애 | snapshot은 calculatedAt와 함께 표시; live라고 표현 금지 |

### 12.3 Included/Excluded data

포함:

- destination label
- target arrival
- snapshot 당시 P50/P90/`P(on_time)` 중 eligible 값
- Recommended Departure status/value(AVAILABLE일 때만)
- selected-route condition copy
- model coverage/critical limitation
- calculatedAt, validation scope

제외:

- exact origin·coordinate·GPS trace
- provider raw/internal IDs
- evidence debug, sample raw reference
- secret, Journey mutation CTA

### 12.4 Component hierarchy

```text
SCR-06
├─ Shared Result Header
├─ Snapshot/Not-live Notice
├─ Target & Arrival Summary
├─ Selected-route Scope
├─ Limitation Summary
├─ Calculated Time
└─ CTA: 내 여정 계산하기 → SCR-01
```

### 12.5 Share creation contract

SCR-02/03의 `공유` CTA는 feature flag와 G5 security Gate가 통과하고 shareable result가 있을 때만 노출한다. create 중 중복 요청을 막는다. exact TTL 숫자는 확정 전 UI copy에 박지 않고 API `expiresAt`을 formatting한다.

- Share 생성은 owner capability가 있는 원본 Journey에서만 가능하다.
- public Share token은 snapshot read 권한만 가지며 원본 Journey 조회·Evidence·Start·Event 권한으로 승격되지 않는다.
- token 원문은 URL 처리에만 사용하고 analytics, error copy, DOM debug attribute, application log에 넣지 않는다.
- revoke/expire 후에는 snapshot을 cache에서 복원해 표시하지 않는다.
- cookie 기반 owner mutation(Start/Event/Share 생성)은 CSRF token 또는 strict Origin/SameSite 검증을 통과해야 한다(NFR-093).

### 12.6 Responsive·Accessibility·Analytics

- public page는 최소 shell, no private navigation.
- copy URL 결과는 toast뿐 아니라 inline confirmation 또는 accessible live region으로 알림.
- events: `share_create`, `share_create_failed`, `share_view`, `share_expired`, `share_copy`.

Acceptance:

- exact origin/coordinate/internal ID가 payload·DOM·analytics에 없다.
- expired/invalid가 provider error와 구분된다.
- snapshot이 live result로 보이지 않는다.
- Share가 cut되어도 SCR-01~05 core flow는 영향받지 않는다.

---

## 13. State namespace × Screen State

서로 다른 상태축을 하나의 Domain enum으로 합치지 않는다.

| Namespace | State | Primary Screen | 허용 action | 금지 action |
|---|---|---|---|---|
| AnalysisState | IDLE | SCR-01 | edit/analyze | event/start |
| AnalysisState | ANALYZING | SCR-01 loading | cancel/back | duplicate analyze |
| JourneyLifecycleState | PRE_TRIP_READY | SCR-02 | start/evidence/share/edit | user event |
| JourneyLifecycleState | ACTIVE | SCR-03 | active-state event/evidence/share | plan mutation without new analysis |
| ReforecastState | PROCESSING | SCR-03+SCR-04 loading | wait/refetch | duplicate event/navigation mutation |
| ReforecastState | UNAVAILABLE/FAILED | SCR-03+SCR-04 result | retry/return | required ride 삭제 |
| JourneyLifecycleState | ARRIVED | SCR-03 terminal | evidence/share/new journey | live event/polling |
| JourneyLifecycleState | ABORTED | SCR-03 terminal | evidence/new journey | live event |

### 13.1 Leg state × rendering

| Leg state | Icon/Label | 시간 | CTA |
|---|---|---|---|
| PLANNED | future | planned/reference if eligible | 없음 |
| AVAILABLE | next | candidate source 표시 | active로 전환될 때만 |
| IN_PROGRESS | active | 시작/last update | contextual |
| COMPLETED | complete | actual/confirmed | 없음 |
| SKIPPED | skipped candidate | occurredAt | 없음 |
| MISSED | missed connection | occurredAt/rule | next candidate flow |
| UNAVAILABLE | unavailable | 없음 | retry/reason |

---

## 14. Error Taxonomy와 Recovery UX

| Error/State | 소유 화면 | 사용자 문구 방향 | Retry | 보존 |
|---|---|---|---|---|
| INPUT_INVALID | SCR-01 | field-specific | 입력 수정 | 입력값 |
| UNSUPPORTED_GEOGRAPHY | SCR-01 | 지원범위 | 입력 수정 | 입력값 |
| ROUTE_NOT_FOUND | SCR-01 | 경로 없음 | 입력 수정/재시도 | 입력값 |
| ROUTE_MAPPING_INCOMPLETE | SCR-01 | 분석에 필요한 연결 불가 | 입력 수정 | 입력값 |
| INSUFFICIENT_DATA | SCR-02/05 | 근거 부족 | later retry | structural route/evidence |
| STALE_DATA | SCR-02/03 | last success와 현재 차이 | retry | stale snapshot |
| PROVIDER_ERROR | SCR-01/02/03 | raw body 없는 provider 실패 | retryable 기준 | 마지막 성공 분리 |
| PROVIDER_QUOTA_EXCEEDED | SCR-01/02/03 | 새 조회 제한과 마지막 성공 상태를 분리 | reset/정책상 retry | 승인 cache 또는 입력값 |
| PROVIDER_ENTITLEMENT_UNAVAILABLE | SCR-01 | 앱 권한·요금제 상태로 새 경로 조회 불가 | 운영 확인 후 | 입력값; probability 없음 |
| EVENT_NOT_ALLOWED_IN_STATE | SCR-03 | 현재 상태에서 수행 불가 | state refetch | current server state |
| EVENT_ALREADY_APPLIED | SCR-03 | 이미 반영된 상태로 동기화 | retry 금지 | latest state/result |
| TARGET_SERVICE_MISMATCH | SCR-03 | 이동편이 바뀌었음 | refresh | user event 미적용 |
| REFORECAST_FAILED | SCR-04 | 적용/미적용 상태 확인 후 안내 | 조건부 | completed history |
| REFORECAST_UNAVAILABLE | SCR-04 | next service source 없음 | 조건부 | required route topology |

Retry는 동일 입력/이벤트를 무한 반복하지 않는다. API `retryable`과 idempotency를 반영하고 provider quota error에는 즉시 재시도를 기본 CTA로 강요하지 않는다.

`FREE_QUOTA_STATUS_UNCONFIRMED`는 특정 provider credential의 무료 제공 조건이나 승인량이 아직 콘솔·공식 evidence로 확인되지 않은 운영 상태다. 2026-08-23 Kakao Map publictraffic/WALK는 콘솔 기준 `CONFIRMED`로 갱신됐지만, 다른 provider나 새 credential에는 이 상태가 남을 수 있다. 사용자에게 “1,000회 남음” 같은 내부 quota 잔량을 직접 표시하지 않는다. entitlement 미확인 때문에 새 조회가 차단된 경우에만 `PROVIDER_ENTITLEMENT_UNAVAILABLE`로 투영하고, quota 소진은 `PROVIDER_QUOTA_EXCEEDED`로 분리한다.

---

## 15. Mobile-first PWA Contract

| 영역 | Mobile | Tablet | Desktop |
|---|---|---|---|
| Shell | compact header, one primary action | compact/expanded | full header |
| SCR-01 | one-column, sticky CTA | centered form | form+scope note |
| SCR-02 | decision first, vertical sections | result+route split 가능 | result left, route/evidence right |
| SCR-03 | active leg first, vertical timeline | summary+timeline | summary/active card+timeline |
| SCR-04 | full-height/bottom sheet | modal/sheet | side panel/modal |
| SCR-05 | bottom sheet/full page, accordion | drawer/page | side drawer or route page |
| SCR-06 | single-column public card | centered card | centered card |

Breakpoints는 design system에서 고정하며 이 문서가 임의 px를 만들지 않는다. 모든 viewport에서 target, result state, critical limitation, primary CTA, freshness를 제거하지 않는다. sticky CTA는 content를 가리지 않고 safe-area·keyboard를 처리한다.

| PWA 항목 | 화면 계약 |
|---|---|
| Installability | manifest·icon·standalone display·HTTPS를 갖추되 설치 prompt는 task를 막지 않음 |
| Non-install parity | 모바일 브라우저에서도 SCR-01~05, 권한, 결과 의미, 오류 처리가 동일 |
| App shell cache | shell/static asset만 안전하게 cache; Journey API·event mutation·확률 result의 무조건 cache-first 금지 |
| Offline snapshot | owner screen의 privacy-safe projection만 read-only로 표시; savedAt와 offline label 필수 |
| Foreground recovery | visibility/pageshow 복귀 시 server state/result version 재조회; 완료 전 mutation 잠금 |
| Update lifecycle | active event/reforecast 중 worker 강제 activation 금지; reload 전 unsent state 여부 확인 |
| Location | 사용자 CTA 후 foreground one-shot 권한 요청; 거부·오류 시 수동 입력 유지 |
| Share | Web Share API 가능 시 OS sheet, 그 외 copy fallback; token을 analytics/log에 남기지 않음 |

### 15.1 PWA Compatibility Matrix

| Test profile | Required flow | Runtime variants | Acceptance |
|---|---|---|---|
| iOS Safari Mobile Web | SCR-01→02→Start→03→04/05 | permission allow/deny, background→foreground, network loss | 핵심 정보·CTA·owner guard 유지 |
| iOS standalone | 동일 flow | launch from icon, route restore, update 후 reopen | browser mode와 의미·권한 동등 |
| Android Chrome Mobile Web | 동일 flow | OS share/cancel/fallback, offline snapshot | Share 실패가 Journey를 막지 않음 |
| Android installed PWA | 동일 flow | install, waiting worker, safe activation, rollback | mutation 손실·중복·reload loop 0 |
| Desktop Chrome/Edge | SCR-01→02→05 | wide responsive layout | mobile에서 제공하는 핵심 정보 삭제 0 |

각 run은 실제 device/OS/browser/appVersion/cacheVersion을 test manifest에 기록한다. 특정 버전 숫자는 보유 기기와 배포 시점에 확정하고, 검증하지 않은 환경을 “지원”으로 표시하지 않는다.

---

## 16. Accessibility Contract

- WCAG 수준 목표와 자동/수동 테스트 범위는 NFR에서 확정하되 다음은 Minimum 필수다.
- heading hierarchy와 landmark, skip link, logical DOM/focus order.
- 모든 field label/error association, keyboard-only 완료 가능.
- 색상 외 icon/text/pattern으로 state 전달.
- probability와 time은 screen reader가 문장으로 읽을 수 있게 accessible description 제공.
- dynamic loading/reforecast/error는 적절한 live region 사용; 과도한 반복 announcement 금지.
- modal/sheet focus trap·return, ESC/back 정책.
- touch target, zoom/reflow, reduced motion.
- animation으로 probability를 확정적이거나 개선된 것처럼 과장하지 않는다.

---

## 17. Analytics Contract

### 17.1 공통 원칙

- exact origin/destination coordinate, API secret, raw provider ID를 property로 저장하지 않는다.
- raw `journeyId`와 public Share token은 analytics에 저장하지 않는다. Journey 단위 분석이 필요하면 analytics 전용 pseudonymous key를 사용하며 owner capability와 상호 변환할 수 없어야 한다.
- exact location label이 민감 위치를 드러낼 수 있으므로 free-text label도 기본 analytics property에서 제외한다.
- event success/failure는 reason code와 version을 구분한다.
- UI view와 실제 domain mutation success를 같은 event로 세지 않는다.

### 17.2 Minimum dictionary

| Event | Screen | Trigger | Required properties |
|---|---|---|---|
| journey_input_view | 01 | view | entry_source |
| journey_analyze_click | 01 | valid submit | target_reliability, target_time_bucket |
| journey_analysis_success | 01→02 | result received | route_type, route_manifest_type, walk_provider_category, future_route_provider_status, selection_policy, coverage_mode, eligibility, validation_scope, model_coverage |
| journey_analysis_failed | 01 | failure | reason_code, retryable |
| pretrip_result_view | 02 | eligible/failed result view | eligibility, freshness |
| journey_start_click | 02 | click | result_version |
| journey_start_success | 03 | state active | state_version |
| bus_skipped | 03 | user submit | target_service_id_exists |
| board_confirmed | 03 | user submit | mode, target_service_id_exists |
| reforecast_success | 04 | new result | reason_code, probability_delta_pp_nullable, result_version |
| reforecast_failed | 04 | failure/unavailable | reason_code, retryable |
| evidence_open | 05 | open | confidence, model_coverage, fallback_exists |
| share_create | 02/03 | success | journey_state, result_version |
| share_view | 06 | valid view | snapshot_age_bucket |
| provider_stale | 02/03 | transition | source_category, provider_key, previous_freshness |
| journey_arrived | 03 | terminal success | state_version |
| pwa_runtime_state | Global | offline/reconnecting/online transition | runtime_state, screen_id, snapshot_exists |
| pwa_update_available | Global | waiting worker 발견 | screen_id, journey_lifecycle, safe_to_activate |
| pwa_install_outcome | Global | prompt outcome 또는 standalone detection | outcome, platform_category |

event dictionary 변경은 Privacy review를 거치며 각 property에 목적·owner·retention class를 부여한다. 정확 retention 기간은 G5에서 정하고, 미정 상태에서는 새 식별성 property를 추가하지 않는다.

### 17.3 Internal QA event

`internal_route_fixture_loaded`는 일반 product analytics가 아닌 격리된 development/QA log에서만 허용한다. Route B는 내부 topology·interoperability 검증에만 사용하며 사용자 화면과 최종 발표 narrative에는 나타나지 않는다. production 또는 public demo build에서 fixture entry가 발견되면 release-blocking configuration error다.

### 17.4 Route A Demo 화면 계약

- 발표용 별도 mock screen을 만들지 않고 SCR-01→05의 실제 product flow를 사용한다.
- result에는 Route A scope, calculatedAt, live/recorded 상태, eligibility, validation scope와 critical limitation을 유지한다.
- Developer detail에서 route manifest provider, WALK provider, selection policy, route hash, mapping/artifact/engine/app/schema version과 distributed run reference를 추적할 수 있어야 한다.
- Route A가 `APPROVED_DEMO_ROUTE`이면 Kakao의 현재 첫 후보라고 설명하지 않는다. Kakao WALK를 사용하면 같은 run의 walk provider/version/cache evidence를 manifest에서 확인한다. Kakao publictraffic live candidate는 future route-provider Gate 전까지 현재 selected route로 설명하지 않는다.
- live provider 실패 시 recorded evidence를 live로 바꾸지 않고 `기록된 근거` 또는 unavailable state를 표시한다.
- manifest/preflight가 실패하면 해당 숫자 scene을 제거하며 Route B나 illustrative probability로 대체하지 않는다.

---

## 18. Screen ↔ Feature ↔ REQ/BR Traceability

| Screen | Product Feature | REQ | BR/NFR | 핵심 AC |
|---|---|---|---|---|
| SCR-01 | Input/Location/Route | REQ-001~009,050~056,093~094,098 | BR-001~005,060~074; NFR-010,053,054,070,074,075,079,084,087,088 | UI-AC-001~002,015~016,025,030,033~034; AC-001~002,035~036,041~042,046,053~057 |
| SCR-02 | Pre-trip Result | REQ-005~017,020,030~045,050~056,093~098 | BR-001~005,010~017,020~024,045,050~053,060~074; NFR-084,087,088 | UI-AC-003~008,013,020~023,025~029,034~035; AC-003~008,037~045,047,053~057 |
| SCR-03 | Live Journey/User Event | REQ-007,020~025,030~035,050~056,070~073,093,095~098 | BR-030~045,060~070; NFR-002,053,074~079 | UI-AC-007~012,015~022,025~030; AC-009~015,024,035~047 |
| SCR-04 | Reforecast | REQ-023~026 | BR-040~044 | UI-AC-010~012,028~029; AC-011~015,044~045 |
| SCR-05 | Evidence | REQ-007~009,040~045,060~073,090~092,093,095~097 | BR-005,012~017,050~053,061~074; NFR-087,088 | UI-AC-013,019,022~029,034~035; AC-018~021,027,034~045,053~057 |
| SCR-06 | Share | REQ-080~082,098 | NFR-050~054,079 | UI-AC-014,023,047; AC-025,039,047 |

### 18.1 주요 정책 추적

| 정책 | 화면 적용 |
|---|---|
| Selected route conditional | SCR-02/06 scope label, alternatives ranking 없음 |
| Provider access ≠ supported Journey | SCR-01 WALK/route mapping/entitlement 상태, SCR-02 scope, SCR-05 WALK provider·future route crosswalk detail |
| Coverage mode | SCR-01 사전 고지, SCR-02/05 selection policy, Demo Route A manifest |
| P90 ≠ 90% accuracy | SCR-02/04/05/06 copy guard |
| Recommended Departure service re-evaluation | SCR-02 AVAILABLE Gate/copy; 계산 로직은 REQ/API |
| Transfer ≠ Wait | SCR-02/03 timeline separate rows |
| BUS_SKIPPED user-confirmed | SCR-03 CTA precondition, SCR-04 reason/topology |
| Component ≠ E2E calibration | SCR-02 evidence summary, SCR-05 validation scope |
| WALK/Transfer uncertainty | SCR-02 limitation, SCR-05 leg detail, SCR-06 critical limitation |
| Provider quota/failure | SCR-01/03 retry policy, immediate retry 제한 |
| Coordinate provenance | SCR-05 display; exit claim guard |
| Anonymous owner access | SCR-02~05 route guard; SCR-06 token 권한 분리 |
| Eligibility vs confidence | SCR-02 metric/start decision 분리 |
| Critical freshness aggregation | Global state projection + SCR-02/03 CTA |
| Route B internal QA | 개발·QA 도구에서만 검증; 사용자 IA·public demo entry 없음 |
| PWA install parity | SCR-01~05에서 browser/standalone 기능·권한·copy 동등 |
| Offline/foreground | Global runtime banner, mutation lock, privacy-safe snapshot, server version 복구 |
| Service Worker update | active mutation 중 activation defer, version/rollback 관측 |

---

## 19. Development Handoff Checklist

### Frontend

- [ ] Screen ID, route, overlay, system state가 분리돼 있다.
- [ ] Result View Model의 null/0/unsupported가 구분된다.
- [ ] 모든 CTA가 precondition·in-flight disable·retry behavior를 가진다.
- [ ] state priority와 compound state가 구현돼 있다.
- [ ] production에서 fixture/mock probability가 보이지 않는다.
- [ ] responsive에서 핵심 정보가 삭제되지 않는다.
- [ ] analytics에 exact coordinate/token/secret이 없다.
- [ ] owner capability는 JS/URL/DOM에서 읽을 수 없고, 권한 없는 Journey route는 동일 recovery UX다.
- [ ] `startEligibility`를 confidence나 badge 문자열로 재추론하지 않는다.
- [ ] Service Worker는 owner API/mutation을 cache-first 또는 offline success로 처리하지 않는다.
- [ ] foreground 복귀 중 mutation이 잠기고 server version으로 복구된다.
- [ ] install/non-install/standalone에서 핵심 flow와 접근성 의미가 동일하다.
- [ ] 실제 PWA Compatibility Matrix run과 device/OS/browser/app/cache version이 기록된다.
- [ ] Route A Demo 화면이 product flow와 동일하고 manifest version·live/recorded 상태를 추적할 수 있다.
- [ ] Protected E2E인 SCR-01→02→Start→03→BUS_SKIPPED→04/Unavailable→05가 다른 polish보다 먼저 통과한다.
- [ ] coverageMode와 route manifest/WALK provider/selection/mapping field가 배포 config 및 화면 copy와 일치한다.
- [ ] Kakao WALK 호출 성공을 publictraffic canonical mapping 성공이나 Route A 선택으로 재해석하지 않는다.

### Backend/API

- [ ] direct route 복구용 Journey/result/state가 제공된다.
- [ ] `resultEligibility`, `validationScope`, coverage, confidence, freshness, limitations가 누락되지 않는다.
- [ ] UserEvent idempotency와 state/result version이 제공된다.
- [ ] provider error와 insufficient/unsupported가 분리된다.
- [ ] Share payload가 privacy-safe snapshot이다.
- [ ] source별 criticality와 Journey freshness projection을 응답한다.
- [ ] owner capability와 Share read token의 권한이 분리된다.
- [ ] provider entitlement·quota·mapping failure가 공통 500 또는 0%로 합쳐지지 않는다.

### Data/Probability

- [ ] null을 임의 숫자로 대체하지 않는다.
- [ ] support sample unit과 raw poll row가 구분된다.
- [ ] coordinate role/source, fallback, uncertainty coverage가 leg별 전달된다.
- [ ] validation scope가 V0~V3에 맞다.
- [ ] Recommended Departure HOLD가 UI AVAILABLE로 새지 않는다.
- [ ] provider별 WALK point를 평균하거나 다른 provider provenance로 바꾸지 않는다.

---

## 20. QA Acceptance Scenarios

| ID | Scenario | Expected |
|---|---|---|
| UI-AC-001 | valid SCR-01 submit | 중복 요청 없이 SCR-02 복구 가능한 result 생성 |
| UI-AC-002 | unsupported geography | probability 0%가 아니라 지원범위 copy+입력 수정 |
| UI-AC-003 | NOT_COMPUTED result | metric null, Journey Start disabled, missing reason 표시 |
| UI-AC-004 | PARTIAL_MODEL | metric 허용 시 표시하되 critical limitation+Evidence link |
| UI-AC-005 | P50/P90/on-time | 서로 다른 label/help/null 처리 |
| UI-AC-006 | Recommended unavailable | 시간 없음, conditional unavailable copy, AVAILABLE mock 없음 |
| UI-AC-007 | stale plan/live | last success 표시, current/live 오인 없음, retry |
| UI-AC-008 | provider error with snapshot | error+stale snapshot 분리, raw body 없음 |
| UI-AC-009 | BUS_WAIT candidate 없음 | BUS_SKIPPED/BOARD CTA 없음 |
| UI-AC-010 | BUS_SKIPPED | reforecast 중 CTA disabled, 이후 next WAIT+same BUS_RIDE 유지 |
| UI-AC-011 | duplicate event | state/result 한 번만 변경, 최신 화면 동기화 |
| UI-AC-012 | reforecast unavailable | required ride 삭제 없이 unavailable reason |
| UI-AC-013 | Evidence Detail | support/fallback/freshness/validation/coordinate/limitation 표시 |
| UI-AC-014 | Share | exact origin/coordinate/internal ID 없음, expired variant |
| UI-AC-015 | mobile | 핵심 flow overflow 없음, keyboard/focus/touch/CTA 정상 |
| UI-AC-016 | screen reader/keyboard | input→result→event→overlay→복귀 완료 가능 |
| UI-AC-017 | browser refresh/back | server version 복구, mutation rollback/duplicate 없음 |
| UI-AC-018 | ARRIVED | FINAL_WALK 완료 전 terminal 불가 |
| UI-AC-019 | owner capability 없음/불일치 | plan/live/evidence/start/event/share-create 모두 resource 존재를 숨기는 동일 recovery; mutation 0 |
| UI-AC-020 | USER_FACING + INSUFFICIENT + start eligible | 경고와 Evidence link를 보이고 Journey Start 허용 |
| UI-AC-021 | required leg time input 없음 | NOT_COMPUTED, placeholder 0, Start disabled |
| UI-AC-022 | mixed source freshness | critical source 기준으로 deterministic Journey state/CTA; non-critical failure는 core CTA 유지 |
| UI-AC-023 | Share token | snapshot read만 가능; owner API/evidence/mutation 접근 0 |
| UI-AC-024 | Route B internal QA isolation | 개발·QA 도구 외 사용자 화면·public demo build·product analytics 노출 0 |
| UI-AC-025 | 설치하지 않은 모바일 브라우저 | SCR-01→02→03→04/05 핵심 flow와 owner guard 정상 |
| UI-AC-026 | PWA standalone | browser mode와 result·state·CTA·error 의미 동일 |
| UI-AC-027 | network 단절 | privacy-safe last snapshot만 OFFLINE_SNAPSHOT으로 표시, Start/Event/Share mutation 0 |
| UI-AC-028 | foreground 복귀 | RECONNECTING 후 최신 server state/result version 반영, 이전 값 current 승격 0 |
| UI-AC-029 | Service Worker update | active event/reforecast 손실·중복·무한 reload 없이 safe activation |
| UI-AC-030 | 위치 권한 거부 | 수동 입력으로 전체 flow 계속, 반복 강제 prompt·background tracking 0 |
| UI-AC-031 | PWA compatibility matrix | iOS/Android browser·standalone 각 run의 device/OS/browser/app/cache version과 결과 기록 |
| UI-AC-032 | Route A final demo | 실제 SCR flow, Route A scope, live/recorded, eligibility/validation/limitation/version trace; Route B·mock 숫자 0 |
| UI-AC-033 | Kakao publictraffic reference + mapping incomplete | publictraffic HTTP 성공을 일반 route 결과로 승격하지 않고 SCR-01 mapping copy; probability·Start 0. Kakao WALK 성공은 WALK provenance로만 표시 |
| UI-AC-034 | coverage 축 | 서울 임의 입력 허용을 submit 전 고지하되 mapping/model coverage에 따라 결과가 달라질 수 있음을 함께 안내; `routeCoverageMode`/`walkProviderMode`/`modelCoverage` provenance 유지 |
| UI-AC-035 | P90 기본 copy | “모델 도착분포의 90번째 백분위”와 validation scope를 인접 표시; calibration Gate 전 “10번 중 9번” 0 |
| UI-AC-036 | RIDE 정상 하차 | `하차했어요` CTA로 RIDE_COMPLETED, 다음 TRANSFER/WAIT/FINAL_WALK가 timeline에 AVAILABLE로 나타남 |
| UI-AC-037 | 여정 종료(ABORT) | confirm dialog 통과 후 API-010 호출, ABORTED terminal, live polling/event CTA 중지, 완료 이력 보존 |
| UI-AC-038 | 임의 서울 OD mapping PARTIAL/FAILED | 경로 구조는 표시하되 확률 카드 숨김+사유 표시, 재시도 유도 문구 없음 |
| UI-AC-039 | metric별 claim eligibility | 같은 결과 안에서 P50/P90/on-time/Recommended가 서로 다른 `metricEligibility` 문구를 가질 수 있음을 확인 |

---

## 21. Open Implementation Decisions

다음은 IA 누락이 아니라 측정·보안·하위 계약 Gate가 필요한 값이다.

| Item | 현재 UI 계약 | Resolution Gate |
|---|---|---|
| provider별 stale threshold | metadata state를 그대로 렌더; 임의 시간 금지 | latency/poll profile |
| support HIGH/MEDIUM/LOW threshold | rule 전 INSUFFICIENT | SUPPORT_RULE_V1 |
| Share TTL | API expiresAt 표시; hard-coded 기간 금지 | G5 Security Review |
| exact breakpoint | 동일 정보 재배치 원칙 | design system |
| performance SLO/loading fallback | 진행률/시간 조작 금지 | first vertical slice benchmark |
| Recommended Departure AVAILABLE | unavailable component 유지 | future WAIT+validation Gate |
| BUS_TO_SUBWAY internal time | UNMODELED limitation | real source/explicit decision |
| active stale state의 event CTA | safety 우선 disable 가능 | provider-specific freshness policy |
| owner capability/Journey TTL | expiry UI는 server state 사용; 숫자 hard-code 금지 | G5 Security Review |
| analytics retention | raw ID/token 금지; pseudonymous key만 | G5 Privacy Review |
| offline snapshot storage lifetime | server retention과 별도 policy; savedAt·clear path 제공 | G5 Privacy/Security Review |
| Service Worker activation timing | active mutation 안전성 우선 | PWA integration test |
| Kakao publictraffic Primary 승격 | 호출 성공만으로 승격하지 않고 entitlement·ID mapping·시간 분해·반복 안정성 Gate. 2026-08-23 판정: mapping `REJECTED`(payload에 canonical ID 없음)로 route-provider 승격 미통과 확정 — UI는 계속 `ROUTE_A_ONLY + KAKAO_WALK_ONLY` 기준 copy를 사용 | `KAKAO_ROUTE_PROVIDER_GATE` |
| deployment coverage mode | Minimum Release는 `ROUTE_A_ONLY + KAKAO_WALK_ONLY`; future Gate 통과 시에만 `PROVIDER_SUPPORTED` 검토 | Release manifest |

---

## 22. 정본 정합성 규칙

- Service Plan의 selected-route, probability, Reforecast, honesty 정책을 보존한다.
- Requirements의 SCR-01~06, REQ·BR 의미와 동일한 용어를 쓴다.
- 화면·route·overlay·system/domain/PWA runtime state를 구분한다.
- 화면별 required/nullable data와 null rendering을 명시한다.
- 모든 mutation CTA에 precondition, disable, retry, idempotency 조건을 연결한다.
- partial/low-support/insufficient/stale/provider-error/reforecasting은 실제 copy와 행동을 바꾼다.
- probability·confidence·coverage·validation scope를 하나의 badge로 합치지 않는다.
- 개인정보·Share·analytics·device cache에서 exact coordinate와 secret을 제외한다.
- IA 범위를 넘어서는 schema·threshold·TTL 숫자를 만들지 않는다.
- Mobile Web·standalone·offline·foreground·update 상태를 product state와 혼합하지 않는다.
- Route B는 내부 개발·QA 범위이며 사용자 IA와 최종 데모에 노출하지 않는다.
- Kakao/TMAP/서울 provider 이름과 값의 provenance를 바꾸거나 서로 평균하지 않는다.
- `ROUTE_A_ONLY + KAKAO_WALK_ONLY`와 future `PROVIDER_SUPPORTED`의 화면 고지·입력 허용범위·선택 정책을 혼합하지 않는다.

---

## Appendix A. Screen 완료 정의

| Screen | Done |
|---|---|
| SCR-01 | 입력·resolve·validation·coverage mode·WALK provider entitlement·future route mapping·failure를 구분해 분석 요청 가능 |
| SCR-02 | eligible 결과 또는 정직한 미계산 상태를 selected-route scope와 근거로 설명하고 start 가능 |
| SCR-03 | server state를 복구해 active leg·freshness·timeline·조건부 event CTA 제공 |
| SCR-04 | event 전후 결과·reason·unavailable을 completed-history invariant와 함께 설명 |
| SCR-05 | leg별 source/support/fallback/uncertainty/validation/coordinate provenance 확인 가능 |
| SCR-06 | privacy-safe immutable snapshot을 valid/expired/invalid로 제공 |

## Appendix B. 금지 표현

- `정확도 90%`
- `P90 시각에 정확히 도착`
- `AI가 계산한 확정 도착시간`
- `가장 안전한 경로/출발시간`
- `버스를 못 탈 확률`
- `역 출구 기준` — 실제 coordinate가 STATION_CENTER일 때
- `실시간` — stale/recorded/cached snapshot일 때
- `지원 확률 0%` — unsupported/not-computed일 때
- `카카오 경로이므로 분석 가능` — publictraffic canonical mapping/route-provider Gate 미확인일 때
- `10번 중 9번 도착` — end-to-end calibration Gate 미통과일 때
