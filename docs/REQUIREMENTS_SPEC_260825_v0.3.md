# 언제와 (Journey Reliability) 요구사항정의서 — v0.3

> **문서 목적**: 확정 Service Plan과 IA를 구현 가능한 기능·규칙·인터페이스·데이터·품질·인수 계약으로 변환한다.  
> **문서 지위**: Product / Frontend / Backend / Data / Infra / QA 개발 handoff 정본  
> **정본 파일명**: `REQUIREMENTS_SPEC_260825_v0.3.md`  
> **버전**: v0.3 — Shared Input Shell + milestone projection + URL public share  
> **기준일**: 2026-08-25  
> **상위 기준**: `SERVICE_PLAN_260825_v0.3.md`, `IA_SCREEN_SPEC_260825_v0.3.md`  
> **적용 원칙**: Evidence에 없는 수치로 빈 셀을 채우지 않는다. 측정이 필요한 값은 상태와 해소 Gate를 명시한다.

## 문서 네비게이션

**정본 문서 바로가기**

- [Service Plan](SERVICE_PLAN_260825_v0.3.md)
- [IA / Screen Spec](IA_SCREEN_SPEC_260825_v0.3.md)
- **Requirements Spec**
- [Decision Sheet](DECISION_SHEET_260825_v0.3.md)

**핵심 변경**: v0.3 Minimum Release는 `Splash → Shared Input Shell`을 사용하되 `Departure Recommendation`과 `Leave-now Forecast(사용자-facing: 도착 시간 계산)`를 **서로 독립된 product command**로 유지한다. 두 result에는 engine-produced milestone projection을 추가하고, Share는 URL create/copy/public read-only flow를 MUST로 승격한다. v0.3 Arrival core에서는 mandatory `targetArrivalAt`과 user-facing `P(on_time)`을 제거한다.

## 문서 정보와 규모

### 정의 규모

아래 범위는 v0.3 active/retired trace를 함께 관리한다. 기존 ID를 새 의미로 재사용하지 않는다.

| 정의 단위 | 관리 방식 | ID 범위 |
|---|---|---|
| Feature | 기존 ID 보존 + milestone projection | F001~F020 |
| Functional Requirement | active/retired 분리 + v0.3 entry/milestone/share 계약 | 기존 REQ + REQ-107~123 |
| Business Rule | active rule + v0.3 UI/data/share rule | BR-001~102 |
| State Transition Rule | historical IDs 보존 + v0.3 launch/tab/share transitions | ST-001~041 |
| API/System Interface | 기존 separated API 유지, schema 확장 | API-000~013, SYS-001~012 |
| Canonical Entity | 기존 entity + milestone projection | ENT-001~034 |
| NFR | 기존 + Splash/Milestone correctness | NFR-001~102, 비연속 |
| Acceptance Scenario | existing relevant AC + v0.3 contract 신규 081~090 | AC-001~090 |
| Claim Gate | Departure/Arrival 및 realtime/ML/Milestone Gate 포함 | CG-001~011 |

### Priority와 상태

| 값 | 의미 |
|---|---|
| MUST | Minimum Release 필수 |
| CLAIM_GATE | 사용자/발표 claim 승격에 evidence 필요 |
| D2_TARGET | 임의 OD 확장 목표; 미달 시 Route A fallback/structure-only |
| SHOULD / COULD | 후순위/선택 |
| TBD_AFTER_PROFILE | 실제 profile 후 수치 결정 |
| INSUFFICIENT_SOURCE | source 부재로 숫자 생성 금지 |
| HOLD | 계약은 있으나 capability 활성화 금지 |
| `RETIRED_FROM_MR` | 과거 구현 계약의 역사 추적용; 구현·release 요구 아님 |
| `SUPERSEDED_FROM_V0.3` | v0.2 active였으나 v0.3 새 계약이 대체; history 보존 |
| `FUTURE_GPS_RESEARCH` | 향후 자동 GPS tracking 연구 방향; 현재 API/state 선행 설계 금지 |
| `INTERNAL_DIAGNOSTIC` | 사용자-facing 핵심 metric이 아닌 데이터/QA 진단 |

### 승인 Gate

| Gate | 승인 기준 |
|---|---|
| G0 Service Plan | v0.3 Splash/Shared Input/Milestone/URL Share 정책 승인 |
| G1 IA | Shared Input Tab과 split submit/result, scrollable milestone, Share overlay/public view 정합성 |
| G2 Requirements | F/SCR/REQ/BR/NFR/API/ENT/AC/CG 추적 누락·정책 충돌 0 |
| G3 Data Contract | identity/timestamp/residual/historical artifact/realtime feature/milestone contract 테스트 |
| G4 Product E2E | 실제 모바일 Departure/Arrival flow + URL Share를 각각 통과 |
| G5 Security/Share | secret/privacy/retention/public token share 승인 |
| G6 Release | v0.3 release-blocking AC + distributed correctness proof |

## 범위

### 포함

- 서울 임의 OD BUS+SUBWAY structural route discovery/canonicalization; Route A demo/fallback
- APP-SPLASH transient presentation + Shared Input Shell
- Shared Input Shell의 `출발 시간 추천` / `도착 시간 계산` Tab
- `Departure Recommendation`: future target + historical baseline → Departure P50/P90
- `Leave-now Forecast`: departAt=now + historical baseline + eligible realtime → Arrival P50/P90
- 두 기능의 typed request/result/API/entity/analysisId isolation
- WALK/WAIT/RIDE/TRANSFER/FINAL_WALK shared domain boundary
- 의미 있는 selected-route milestone projection
- historical distribution, support/fallback/confidence/validation
- realtime feature snapshot identity/timestamp/freshness/coverage — Leave-now only
- Prediction→Actual→Residual→Historical Artifact / Realtime Feature lineage
- Leave-now realtime quantile model + baseline fallback, optional unsupervised regime
- mode-scoped Evidence
- **URL Share create/copy/public read-only**
- Mobile-first PWA
- provider/quota/security/operations/distributed correctness

### Explicit Out

- v0.1 `Dual Analysis`: 한 submit/API/result에 두 기능 metric 동시 생성
- v0.2 `Service Home` active entry
- v0.3 Arrival mandatory targetArrivalAt / user-facing P(on_time)
- 한 기능 result/session을 다른 기능 prerequisite로 쓰는 flow
- Journey Start, active leg lifecycle, 수동 UserEvent/Reforecast
- background/continuous GPS tracking(MR)
- targetReliability, `{p*}%` legacy Recommended Departure
- raw provider stop/station 전체를 UI milestone로 자동 노출
- FE에서 leg 평균/quantile을 단순 합산해 milestone time 생성
- 이미지 저장/카카오톡 직접 전송을 canonical Share로 구현
- route optimizer/multi-route ranking
- 생성형/black-box AI final time
- unverified realtime feature의 임의 weight
- citywide SLA/accuracy claim

## Feature Dictionary

| F-ID | Feature | 사용자/시스템 결과 | Primary SCR | Core REQ | Status |
|---|---|---|---|---|---|
| F001 | Shared Entry / Anonymous Access | Splash + Shared Input Shell + owner access | APP-SPLASH/01/07 | 001~003,007,113,117,118 | MUST |
| F002 | Structural Route / Provider Gate | shared route discovery/crosswalk | 01/02/07/08/05 | 005~009,104,105 | MUST/D2 |
| F003 | Departure Time Recommendation | Departure P50/P90 | SCR-01/02 | 107~109,114,116,119 | MUST/CLAIM_GATE |
| F019 | Leave-now Arrival Forecast | Arrival P50/P90 | SCR-07/08 | 011~012,110~112,115,116,120 | MUST |
| F020 | Journey Milestone Projection | selected-route checkpoint times | SCR-02/08/05/06 | 119,120,123 | MUST/CLAIM_GATE |
| F004 | Journey Start/State | old manual live lifecycle | SCR-03 | 020~021,101~102 | RETIRED_FROM_MR |
| F005 | User Event | old BOARD/BUS_SKIPPED/etc | SCR-03 | 022~024 | RETIRED_FROM_MR |
| F006 | Reforecast | old manual event reforecast | SCR-04 | 025~026 | RETIRED_FROM_MR |
| F007 | WALK/Coordinate | shared point/reference provenance | 02/08/05 | 030~032 | MUST |
| F008 | Transfer Domain | shared transfer structure/reference | 02/08/05 | 033~035 | MUST |
| F009 | Evidence/Support | analysisType-scoped evidence | 02/08/05 | 040~045 | MUST |
| F010 | Freshness/Error | historical + Arrival realtime freshness | 01/02/07/08/05 | 050~056 | MUST |
| F011 | Prediction/Actual/Residual | shared data lineage | Data/05 | 060~067 | MUST |
| F012 | WAIT/Service Context | historical WAIT + Arrival current context | Data/05 | 070~073 | MUST/CLAIM_GATE |
| F013 | URL Share | one-function privacy-safe public URL | OVL/06 | 080~082,121,122 | MUST |
| F014 | Traceability/Internal QA | analysisType lineage, Route B QA | 05/Internal | 090~092 | MUST |
| F015 | Security/Privacy | access/retention/secret/public token | Global | 007,080~082,100,121,122 | MUST |
| F016 | Operations/Observability | provider/quota/artifact/stream | Ops | 008~009 + NFR | MUST |
| F017 | Distributed/ML | shared data proof + Arrival model | Internal/08/05 | 106,109~112 | MUST/CLAIM_GATE |
| F018 | Mobile-first PWA | Splash + shared input + two independent submit flows | Global | 093~098,117,118 | MUST |

## Functional Requirements

> Active MR contract의 최상위 불변조건: **한 request는 한 `analysisType`만 가진다.** v0.1 `Dual Analysis` ID는 history를 위해 보존하되 구현 대상으로 해석하지 않는다.

### Service Entry / Common Input / Route

| REQ | F / SCR | Priority | 상세조건·정상 처리 | 예외·오류 | Interface / Entity | BR·NFR / AC |
|---|---|---|---|---|---|---|
| REQ-113 Function Tab Selection | F001/SCR-01/07 | MUST | Shared Input Shell에 `출발 시간 추천`, `도착 시간 계산` Tab; Tab 전환은 UI state only | Tab 전환으로 분석 API 자동 호출 금지 | UI / ENT-033 | BR-094~098 / AC-081,082 |
| REQ-117 App Launch Splash | F001/F018/APP-SPLASH | MUST | brand presentation 후 Shared Input Shell 진입; analysis/provider/permission prerequisite 0 | motion/asset 실패 시 static fallback | UI/PWA | BR-098; NFR-101 / AC-081 |
| REQ-118 Shared Input Shell | F001/F018/SCR-01/07 | MUST | 물리 shell/공통 장소 input 공유 가능; active tab에 맞는 schema/CTA만 submit | 두 schema를 한 request로 합치거나 hidden field 자동 전송 금지 | API-011,012 / ENT-029,030,033 | BR-094~098; NFR-100 / AC-082~084 |
| REQ-001 출발지 입력 | F001/SCR-01/07 | MUST | 장소/주소 또는 explicit one-shot 현재 위치를 GeoPoint로 resolve | unresolved/geography 구분 | API-000,011,012 / ENT-016,029,030 | BR-001,070 / AC-001 |
| REQ-002 목적지 입력 | F001/SCR-01/07 | MUST | POI/coordinate provenance 저장, final boundary FINAL_WALK | same/unresolved/outside | API-000,011,012 / ENT-016,029,030 | BR-001 / AC-001 |
| REQ-003 목표 도착시각 | F001/SCR-01 | MUST for Departure | future timezone-aware; supported horizonVersion 적용 | past/naive/out-of-horizon | API-011 / ENT-029 | BR-010 / AC-001,083 |
| REQ-004 목표 reliability | F001 | RETIRED_FROM_MR | 2026-08-23 legacy p* trace | active UI/API 사용 금지 | N/A | AC-067 |
| REQ-005 Structural Route 조회·선택 | F002/01/02/07/08 | MUST | 각 function request에서 first canonical+historical supported candidate; internal cache 재사용 가능 | mapping/provider/manifest 오류 | API-001,011,012; SYS-002 / ENT-005 | BR-001~005,071,096 / AC-004 |
| REQ-006 Route normalization | F002/02/08/05 | MUST | WALK/WAIT/RIDE/TRANSFER/FINAL_WALK | silent deletion 금지 | SYS-002 / ENT-005~009,017,018 | BR-030~032 / AC-017 |
| REQ-007 Anonymous Analysis Access | F001/F015 | MUST | analysisId별 browser-bound owner capability; type immutable | capability mismatch enumeration-safe | API-011~013,006,007 / ENT-020,033 | BR-004 / AC-035 |
| REQ-008 Provider Registry/Coverage | F002/F016 | MUST | coverage/route/walk/historical/realtime 축 분리; realtimeContextCoverage는 Arrival only | provenance 혼합 금지 | API-001,011,012,006,009 | BR-005 / AC-057 |
| REQ-009 Kakao Route Provider Gate | F002/F016 | D2_TARGET/CLAIM_GATE | 2026-08-23 evidence status 보존; external crosswalk 필요 | HTTP 200 승격 금지 | SYS-002/007 | BR-071~074 / AC-053~055 |
| REQ-100 Location Provider Contract | F001/F016 | MUST | location provider와 route provider quota/cache/provenance 분리 | URL/log exact location 노출 금지 | API-000,SYS-001 | NFR-090~094 / AC-046 |
| REQ-104 Arbitrary OD Discovery | F002 | MUST | 서울 임의 OD discovery + crosswalk; 각 function에서 독립 eligibility | mapping/model 미달 structure-only | API-001,011,012 | BR-083~085 / AC-061,062 |
| REQ-105 Canonicalization Crosswalk | F002 | D2_TARGET/CLAIM_GATE | name+coordinate+line/route+direction/order+unique candidate | unsafe matching 승격 금지 | SYS-002 / ENT-005 | BR-085 / AC-062 |

### v0.1 Dual Analysis — Retired trace

| REQ | Status | v0.3 처리 |
|---|---|---|
| REQ-010 Dual Analysis Snapshot | RETIRED_FROM_MR | 한 selected route/target에서 두 기능 result를 동시에 생성하던 v0.1 contract. API-002/ENT-011/015와 함께 active 사용 금지 |
| REQ-015 Legacy Recommended Departure | RETIRED_FROM_MR | `{p*}%` single metric trace |
| REQ-017 Start Eligibility | RETIRED_FROM_MR | live Start gate trace |

### Departure Time Recommendation

| REQ | F / SCR | Priority | 상세조건·정상 처리 | 예외·오류 | Interface / Entity | BR·NFR / AC |
|---|---|---|---|---|---|---|
| REQ-114 Departure Recommendation Analysis | F003/SCR-01→02 | MUST | Shared Input Departure state에서 별도 planning request/result; future target + selected route + historical artifact. response는 Departure metric만 | realtime 호출/Arrival metric contamination 금지 | API-011,SYS-010 / ENT-029,031,033 | BR-020~024,089,094~098; NFR-100 / AC-083 |
| REQ-107 Departure P50 | F003/SCR-02/06 | MUST/CLAIM_GATE | historical baseline만, on-time threshold .50 latest candidate | realtime/simple mean subtraction 금지 | SYS-010 / ENT-031,027 | BR-020~024,089 / AC-068,083; CG-004 |
| REQ-108 Departure P90 | F003/SCR-02/06 | MUST/CLAIM_GATE | historical baseline만, threshold .90 latest candidate | P90 leg 단순합 금지 | SYS-010 / ENT-031,027 | BR-020~024,089 / AC-068,083; CG-004 |
| REQ-109 Historical Reliability Artifact | F003/F011/F012/F019/F020 | MUST/CLAIM_GATE | day/time/route/node/service WAIT/RIDE distributions + support/fallback/version/window | poll row iid 금지 | SYS-005/006 / ENT-027 | BR-089 / AC-071; CG-002~005 |
| REQ-119 Departure Milestone Projection | F003/F020/SCR-02/06 | MUST/CLAIM_GATE | selected route milestone별 P50-plan median(`normalAt`)과 P90-plan median(`bufferedAt`) projection; scenario/version/eligibility 포함 | same-departure P50/P90로 오해, FE 누적, raw node 자동노출 금지 | SYS-010/012 / ENT-031,034 | BR-099,100 / NFR-102 / AC-085; CG-011 |

### Leave-now Arrival Forecast

| REQ | F / SCR | Priority | 상세조건·정상 처리 | 예외·오류 | Interface / Entity | BR·NFR / AC |
|---|---|---|---|---|---|---|
| REQ-115 Arrival Time Analysis | F019/SCR-07→08 | MUST | Shared Input Arrival state에서 별도 request/result; server calculatedAt으로 departAt≈now 고정. request core는 origin,destination; response는 Arrival P50/P90만 | Departure metric, mandatory targetArrivalAt, client arbitrary departAt 금지 | API-012,SYS-011 / ENT-030,032,033 | BR-090~098; NFR-098,100 / AC-084 |
| REQ-011 Arrival P50 | F019/SCR-08/06 | MUST | final-arrival Q0.50 | 평균 동일시 금지 | SYS-011 / ENT-032 | BR-010,090 / AC-069,084 |
| REQ-012 Arrival P90 | F019/SCR-08/06 | MUST | final-arrival Q0.90 | 90% accuracy 금지 | SYS-011 / ENT-032 | BR-010,063,090 / AC-069,084 |
| REQ-013 On-time Probability | F019 | RETIRED_FROM_MR | v0.2 `targetArrivalAt` 기반 P(finalArrival≤target) history | active API/UI/share 사용 금지 | historical only | D-260825-005 / AC-090 |
| REQ-110 Realtime Feature Snapshot | F019/F017 | MUST for realtime context | observable-before/at calculatedAt, identity/freshness/coverage immutable snapshot | leakage/stale/unmatched 사용 금지 | SYS-009 / ENT-028 | BR-090,091 / AC-072; CG-009 |
| REQ-111 Realtime Context Application | F019/F017 | MUST | verified feature만 leg distribution에 추가; FULL/PARTIAL/NONE + historical-only fallback | fabricated realtime 금지 | SYS-008/009/011 / ENT-028,032 | BR-090~093 / AC-069,072 |
| REQ-112 Optional Traffic Regime | F017/Internal | COULD/CLAIM_GATE | unsupervised regime은 supervised outcome model feature로만 | direct seconds/weight/final time 금지 | SYS-006/008 / ENT-025,026,028 | BR-092,093 / AC-074; CG-010 |
| REQ-120 Arrival Milestone Projection | F019/F020/SCR-08/06 | MUST/CLAIM_GATE | departAt=now scenario의 canonical milestone checkpoint Q0.50=`normalAt`, Q0.90=`bufferedAt`; version/eligibility 포함 | FE 누적/raw node 자동노출/90% accuracy 표현 금지 | SYS-011/012 / ENT-032,034 | BR-099,101 / NFR-102 / AC-086; CG-011 |

### Shared Result / Function Isolation

| REQ | F / SCR | Priority | 상세조건·정상 처리 | 예외·오류 | Interface / Entity | BR·NFR / AC |
|---|---|---|---|---|---|---|
| REQ-016 Result Eligibility | F003/F019/F020/02/08/05 | MUST | result/milestone type별 USER_FACING/ENGINE_FIXTURE_ONLY/NOT_COMPUTED | fabricated number 금지 | API-011~013 / ENT-031~034 | BR-013~017 / AC-003,087 |
| REQ-103 Per-metric Claim Eligibility | F003/F019/F020 | MUST | Departure/Arrival final metric과 milestone projection을 각각 판정 | 다른 function grade 전이 금지 | API-011,012 / ENT-031,032,034 | BR-082 / AC-073,087 |
| REQ-116 Function Isolation | F003/F019/Global | MUST | 두 기능은 Shared Input Shell을 쓸 수 있으나 별도 submit/API/result; 다른 기능 request/result prerequisite 없음; Evidence/Share도 single type | combined response, automatic continuation, cross-type route coercion 금지 | API-011~013,006~008 / ENT-029~034 | BR-094~098; NFR-100 / AC-082~084 |
| REQ-123 Milestone Common Contract | F020/02/08/05/06 | MUST | milestone은 selected route의 canonical checkpoint; sequence/type/label/subLabel/normalAt/bufferedAt/eligibility/limitations/semanticsVersion | provider raw node 전체 자동노출, fabricated time 금지 | SYS-002,003,012 / ENT-018,034 | BR-099~101 / NFR-102 / AC-085~087 |

### Journey Start / State / Reforecast — Retired trace

| REQ | Status | 2026-08-24 처리 |
|---|---|---|
| REQ-020~026 | RETIRED_FROM_MR | Start/Current State/BOARD_CONFIRMED/BUS_SKIPPED/TRANSFER_MISSED/Reforecast 구현 의무 제거 |
| REQ-101~102 | RETIRED_FROM_MR | 수동 정상 leg transition/Abort 구현 의무 제거 |

Future GPS 연구는 이 ID를 자동으로 재활성화하지 않는다. 연구가 구현 단계로 승격되면 새 evidence/decision 후 별도 contract를 작성한다.

### WALK / Transfer / Coordinate

| REQ | F / SCR | Priority | 상세조건·정상 처리 | 예외·오류 | Interface / Entity | BR·NFR / AC |
|---|---|---|---|---|---|---|
| REQ-030 Coordinate Provenance | F007/SCR-05 | MUST | endpoint lat/lon/source/role/mappingVersion | role coercion 금지 | SYS-001/002 / ENT-016,017 | BR-052 / AC-016 |
| REQ-031 ACCESS WALK | F007/02/08/05 | MUST | origin→first boarding point provider point/reference | provider 간 평균·fabricated variance 금지 | SYS-001 / ENT-006,010 | BR-052,072 / AC-016,027,056 |
| REQ-032 FINAL WALK | F007/02/08/05 | MUST | final alight→actual POI, final-arrival boundary | station center를 exit로 표현 금지 | SYS-001 / ENT-006,010 | BR-052 / AC-016,027 |
| REQ-033 BUS_TO_SUBWAY | F008/02/08/05 | MUST | street + station internal, WAIT 분리 | internal source 없음 PARTIAL/UNMODELED | SYS-002 / ENT-007 | BR-030~032,052 / AC-017 |
| REQ-034 SUBWAY_TO_SUBWAY | F008/02/08/05 | MUST | verified official reference 가능 | 서로 다른 reference 평균 금지 | SYS-002 / ENT-007,010 | BR-030~034,052 / AC-017 |
| REQ-035 SUBWAY_TO_BUS | F008/02/08/05/Internal | MUST | internal+street 후 BUS_WAIT 분리 | 구조 검증을 E2E probability로 승격 금지 | SYS-002 / ENT-007,008 | BR-030~032,051 / AC-017 |

### Evidence / Support / Confidence

| REQ | F / SCR | Priority | 상세조건·정상 처리 | 예외·오류 | Interface / Entity | BR·NFR / AC |
|---|---|---|---|---|---|---|
| REQ-040 Support Metadata | F009/05 | MUST | artifact/leg effective sample unit/count/window/group/fallback/version | raw row count를 independent support로 사용 금지 | API-006 / ENT-010,027 | BR-050~053 / AC-018,019 |
| REQ-041 Confidence | F009/02/08/05 | MUST/CLAIM_GATE | probability와 분리된 evidence label | 임의 threshold 금지 | API-011/012/006 | BR-050 / AC-020 |
| REQ-042 Fallback | F009/02/08/05 | MUST | hierarchical pooling/reference/historical-only/model fallback reason/provenance | critical historical input을 fake value로 채우지 않음 | API-011/012/006 | BR-012~014 / AC-003,018 |
| REQ-043 Unmodeled Uncertainty | F009/02/08/05/06 | MUST | WALK/static transfer 등의 unmodeled 범위 | 임의 Gaussian/±% 금지 | API-011/012/006/008 | BR-052,061 / AC-027 |
| REQ-044 Validation Scope | F009/02/08/05/06 | MUST | V0/V1/V2/V3 | component→E2E 승격 금지 | API-011/012/006/008 | BR-050,051 / AC-020,021 |
| REQ-045 Evidence Detail | F009/05 | MUST | A historical artifact, B realtime feature/model, route/source/support/fallback/validation | unverified feature를 used로 표시 금지 | API-006 / ENT-001~028 | BR-050~053,061 / AC-018,072 |

### Freshness / Error / Unsupported

| REQ | F / SCR | Priority | 상세조건·정상 처리 | 예외·오류 | Interface / Entity | BR·NFR / AC |
|---|---|---|---|---|---|---|
| REQ-050 Source Freshness | F010/02/08/05 | MUST | source_generated/requested/received/calculated 분리 | source time 없음 flag | SYS-004/009 / ENT-001,028 | NFR-010,011 / AC-026,072 |
| REQ-051 Stale Realtime | F010/08/05 | MUST | stale realtime feature는 B current input에서 제외 | stale를 live/current로 사용 금지 | API-012/006 | BR-061,090 / AC-028,072 |
| REQ-052 Provider Error | F010/01/07/07/08/05 | MUST | transport/business/quota 분리 | raw body/key 노출 금지 | API-000/001/011/012/006 | NFR-030,060 / AC-029 |
| REQ-053 Partial Data | F010/02/08/05 | MUST | historical partial와 realtime partial 원인을 분리 | critical historical missing을 partial로 과승격 금지 | API-011/012/006 | BR-012~014 / AC-027,072 |
| REQ-054 Unsupported | F010/01/07 | MUST | geography/mode/mapping 범위 밖 explicit | fabricated time/0% 대체 금지 | API-001/011/012 | BR-001,060 / AC-002 |
| REQ-055 No Fake Fallback | F010/Global | MUST | missing critical historical→NOT_COMPUTED; synthetic fixture→ENGINE_FIXTURE_ONLY | arbitrary seconds/variance/feature fabrication 금지 | SYS-003 | BR-013,062 / AC-003,008 |
| REQ-056 Function-specific Freshness Projection | F010/02/08/05 | MUST | Departure artifact freshness와 Leave-now realtime coverage/freshness를 분리; Leave-now realtime none이면 historical-only | 하나의 global live enum으로 합치지 않음 | API-011/012/006 | BR-064,089,090 / AC-038,072 |

### Prediction / Actual / Residual

| REQ | F / SCR | Priority | 상세조건·정상 처리 | 예외·오류 | Interface / Entity | BR·NFR / AC |
|---|---|---|---|---|---|---|
| REQ-060 Prediction Snapshot | F011/05 dev | MUST | mode/route/service/target/predictedAt/ETA/source/observation 보존 | no candidate를 real prediction으로 생성 금지 | SYS-004 / ENT-001,002 | BR-050 / AC-030 |
| REQ-061 Actual Arrival Interval | F011/Internal | MUST | polling interval lower/upper/mid/width 보존 | midpoint only 금지 | SYS-005 / ENT-003 | BR-050 / AC-030 |
| REQ-062 Bus Actual | F011/Internal | CLAIM_GATE | validated target context `stopFlag 0→1`, dedupe | unverified target match diagnostic only | SYS-005 / ENT-001~004 | CG-002 / AC-030,031 |
| REQ-063 Subway Actual | F011/Internal | CLAIM_GATE | station×line×train×serviceDate actual transition | station name 혼합 금지 | SYS-005 / ENT-001~004 | CG-003 / AC-030,032 |
| REQ-064 Residual | F011/Internal | MUST | predictedArrival vs Actual interval signed L/M/U | sign 제거 금지 | SYS-005 / ENT-004 | BR-010,050 / AC-030,033 |
| REQ-065 Residual Semantics | F011/Engine | MUST | residual은 prediction error, duration/wait와 type 분리 | abs residual/duration misuse 금지 | SYS-003/005 | BR-013 / AC-021,033 |
| REQ-066 Prediction Horizon/Leakage | F011/ML | MUST | prediction 시점 observable horizon/context만 feature | actual-derived leakage 금지 | SYS-005/008/009 | BR-090 / AC-033,074 |
| REQ-067 Out-of-order Detection | F011/Internal | MUST | receive order에서 source-time reversal 측정 | sort 후 evidence 제거 금지 | SYS-004/005 | NFR-010,061 / AC-026,031 |

### WAIT / Candidate Service

| REQ | F / SCR | Priority | 상세조건·정상 처리 | 예외·오류 | Interface / Entity | BR·NFR / AC |
|---|---|---|---|---|---|---|
| REQ-070 Bus WAIT Source | F012/Data/05 | MUST | A: time-conditioned empirical/timetable prior; B: verified near-now candidate/context 추가 가능 | polling snapshot count iid 금지, future exact vehId 가정 금지 | SYS-003~005 / ENT-008,010,027,028 | BR-024,031,089~091 / AC-019,023,072 |
| REQ-071 Bus Event Unit | F012/Internal | CLAIM_GATE | passenger-relevant/dependence-aware event unit | simple vehId turnover/headway 오해 금지 | SYS-005 / ENT-008,027 | CG-005 / AC-019 |
| REQ-072 Subway WAIT Source | F012/Data/05 | MUST | A historical timetable/empirical, B exact realtime candidate if verified | timetable를 exact current guarantee로 표현 금지 | SYS-003~005 / ENT-008,027,028 | BR-024,089~091 / AC-023,032,072 |
| REQ-073 Service Day | F012/Engine | MUST | DAY/SAT/END, direction, serviceDate, >=24 rollover, source version | naive parse failure→unavailable flag | SYS-003/006 / ENT-008,027 | NFR-021,022 / AC-023 |

### Share / Trace / Demo

| REQ | F / SCR | Priority | 상세조건·정상 처리 | 예외·오류 | Interface / Entity | BR·NFR / AC |
|---|---|---|---|---|---|---|
| REQ-080 Share Snapshot | F013/OVL/06 | MUST | parent analysisType의 eligible metric + privacy-safe milestone만 immutable public projection | exact origin/raw ID/다른 기능 metric 제외 | API-007/008 / ENT-019,033,034 | NFR-050~054,093 / AC-025,088 |
| REQ-081 Share Expiry/Revoke | F013/06 | MUST/G5 | opaque token+expiry/revoke state | TTL hard-code 금지, revoked cache resurrection 금지 | API-007/008 | NFR-051~054,093 / AC-089 |
| REQ-082 Share Authorization Boundary | F013/F015 | MUST/G5 | public snapshot read only; owner result/evidence/recompute/share-create 권한으로 승격 불가 | token reuse/escalation 금지 | API-007/008 | BR-004,102 / AC-088,089 |
| REQ-121 Share URL Create/Copy | F013/OVL | MUST | owner result에서 API-007로 public URL 발급; UI는 URL copy 제공 | image/Kakao direct-send canonical CTA 금지, raw token analytics 금지 | API-007 / ENT-019,020 | BR-102 / AC-088 |
| REQ-122 Public Share View | F013/SCR-06 | MUST | `/share/{token}` direct access, API-008 immutable single-type projection render | owner capability 요구/권한 승격 금지 | API-008 / ENT-019,034 | BR-102; NFR-051~054,093 / AC-088,089 |
| REQ-090 Result Traceability | F014/05/Demo | MUST | result→run→historical distribution/realtime snapshot/model/route/source/version/milestone semantics | missing provenance final demo 금지 | API-006 / ENT-001~034 | BR-050,062 / AC-034 |
| REQ-091 No Mock Final Result | F014/02/08/Demo | MUST | 각 기능 final result/milestone은 해당 real pipeline output | hard-coded/combined mock 금지 | SYS-010~012/006 | BR-053,062 / AC-034,087 |
| REQ-092 Route B Internal QA Isolation | F014/Internal | MUST | topology/realtime identity/data pipeline QA only | BUS_SKIPPED/manual tracking QA/public UI 노출 금지 | SYS-002/004~006 | BR-065 / AC-040 |

### Mobile-first PWA Runtime

| REQ | F / SCR | Priority | 상세조건·정상 처리 | 예외·오류 | Interface / Entity | BR·NFR / AC |
|---|---|---|---|---|---|---|
| REQ-093 Mobile Web/PWA Parity | F018/APP-SPLASH/01/02/07/08/05/06 | MUST | browser/standalone에서 Splash→Shared Input→typed result→Evidence/URL Share semantics/guard/error 동일 | install 여부로 claim 차등 금지 | API-000,006~013 | NFR-070,074,101 / AC-041,042,081 |
| REQ-094 Manifest/Installability | F018/Runtime | MUST | HTTPS/manifest/icon/start URL/standalone | prompt 거부는 오류 아님 | SYS-001 | NFR-075 / AC-042 |
| REQ-095 Offline Snapshot | F018/02/08/05 | MUST | privacy-safe immutable typed analysis projection read-only | offline 새 분석/Share-create success queue 금지; Arrival current 표현 금지 | API-013/006 / ENT-021 | BR-067 / AC-043 |
| REQ-096 Foreground Recovery | F018/02/08/05 | MUST | 저장된 typed result snapshot refetch; 자동 Arrival recompute 없음 | local stale result를 new now/other type으로 승격 금지 | API-013 / ENT-021,031,032,033 | BR-068 / AC-044 |
| REQ-097 Service Worker Update | F018/Runtime | MUST | safe activation, cache/runtime version 관측 | 구 schema result resurrection/reload loop 금지 | SYS-001 | BR-069 / AC-045 |
| REQ-098 Device Capability | F018/01/07 | MUST | origin one-shot geolocation, clipboard share fallback | page-load/continuous/background GPS prompt 금지 | API-000/007 | BR-070 / AC-046,047 |

### AI / ML Training and Serving

| REQ | F / SCR | Priority | 상세조건·정상 처리 | 예외·오류 | Interface / Entity | BR·NFR / AC |
|---|---|---|---|---|---|---|
| REQ-106 JR Realtime Quantile Model Serving | F017/F019/08/05 | D2_TARGET/CLAIM_GATE | canonical model key `JR_REALTIME_QUANTILE_MODEL`; H100/Jupyter training-only; artifact+feature schema+eval+hash를 runtime 반입. B leg residual/WAIT quantile 반환 | baseline uplift/latency/calibration/artifact Gate 미달 시 B1/B0 fallback; final arrival/milestone distribution 직접 생성 금지 | SYS-003/006/008 / ENT-025,026,028 | BR-087,088,093; NFR-095,096,099 / AC-065,066,074; CG-008,010 |

`JR_TEMPORAL_QUANTILE_MODEL`은 2026-08-23 history의 deprecated alias다. historical evidence를 삭제하지 않지만 2026-08-24 active contract에서는 새 model key를 사용한다.

## Business Rules

### Scope / Route

| BR | Rule |
|---|---|
| BR-001 | 서울 지원범위 밖에서 두 핵심 기능의 사용자-facing 숫자를 생성하지 않는다. |
| BR-002 | provider order를 reliability score로 재정렬하지 않는다. |
| BR-003 | selected-route 조건부 결과를 global recommendation으로 표현하지 않는다. |
| BR-004 | analysisId는 credential이 아니며 owner/share 권한을 분리한다. |
| BR-005 | provider access, WALK, canonical mapping, historical model coverage, realtime context coverage는 서로 다른 Gate다. |

### Probability / Result

| BR | Rule |
|---|---|
| BR-010 | Departure P50/P90과 Arrival P50/P90은 서로 다른 metric이다. P50은 평균이 아니다. |
| BR-011 | Planned Connection Success는 INTERNAL_DIAGNOSTIC이며 두 핵심 기능의 primary result와 분리한다. |
| BR-012 | result에는 support/fallback/coverage/validation/freshness/limitation이 필요하다. |
| BR-013 | arbitrary numeric/feature fallback과 value semantics 오류를 금지한다. |
| BR-014 | critical historical input이 없으면 NOT_COMPUTED다. |
| BR-015 | simulation N은 benchmark 후 versioning한다. |
| BR-016 | finite-N error를 model/data uncertainty나 calibration으로 설명하지 않는다. |
| BR-017 | missing input과 unmodeled uncertainty를 구분한다. |

### Departure Planning (A)

| BR | Rule |
|---|---|
| BR-020 | A는 selected route + historical baseline 조건부다. |
| BR-021 | 각 departure candidate마다 service day/time bucket/WAIT/context를 재평가한다. |
| BR-022 | 동일 total distribution 단순 shift, 평균 total-time 차감을 금지한다. |
| BR-023 | P50/P90 threshold는 각각 0.50/0.90이며 사용자 p* 입력을 받지 않는다. |
| BR-024 | future historical/service source가 없으면 해당 Departure metric은 unavailable/NOT_COMPUTED다. |

### Domain

| BR | Rule |
|---|---|
| BR-030 | Transfer에 next-service WAIT를 포함하지 않는다. |
| BR-031 | WAIT는 boarding-ready point 이후다. |
| BR-032 | B2S/S2B/S2S를 별도 TransferType으로 둔다. |
| BR-033 | transfer reference는 의미/version을 가진다. |
| BR-034 | 서로 다른 reference를 평균하지 않는다. |
| BR-040~045 | `RETIRED_FROM_MR` — completed/user event/idempotent Start/Reforecast/Start gate legacy trace. |

### Evidence / UX / Operations

| BR | Rule |
|---|---|
| BR-050 | verified/confidence/validation claim은 scope evidence와 version이 필요하다. |
| BR-051 | corridor/component evidence를 citywide/E2E로 일반화하지 않는다. |
| BR-052 | point/static reference를 empirical distribution으로 표현하지 않는다. |
| BR-053 | synthetic/amplified를 support/real traffic으로 세지 않는다. |
| BR-060 | unsupported/not-computed/insufficient를 0%로 표현하지 않는다. |
| BR-061 | low-support/stale/partial/unmodeled/historical-only를 숨기지 않는다. |
| BR-062 | mock/failed fixture 숫자를 actual result로 사용하지 않는다. |
| BR-063 | `가장 안전`, `P90=90% 정확`, `P50=평균` 표현을 금지한다. |
| BR-064 | A artifact freshness와 B realtime freshness/coverage를 결합 enum으로 만들지 않는다. |
| BR-065 | Route B는 internal topology/identity/data QA 전용이다. |
| BR-066 | PWA 설치 여부는 결과 의미를 바꾸지 않는다. |
| BR-067 | offline snapshot은 not-current read-only projection이다. |
| BR-068 | foreground recovery는 저장 analysis snapshot 복구이며 자동 now recompute가 아니다. |
| BR-069 | Service Worker가 stale/구 schema result를 current로 부활시키지 않는다. |
| BR-070 | MR location은 explicit one-shot origin input만 허용한다. |
| BR-071 | `geographyCoverage`/`routeSearchCoverage`는 서울 임의 OD를 허용한다. D2 selected route는 `PROVIDER_FIRST_SUPPORTED`, demo/fallback은 `APPROVED_ROUTE_A_ONLY`로 분리한다. |
| BR-072 | provider별 route/WALK point·시간·namespace·version을 보존하고 평균·silent substitution·provenance 변경을 금지한다. |
| BR-073 | Kakao 공식 무료 1,000회는 첫 활성화 앱 조건이며 프로젝트 entitlement 확인 전 remaining을 임의 가정하지 않는다. |
| BR-074 | 2-node distributed correctness proof는 HA·무중단·SLA claim이 아니다. |
| BR-080 | 2026-08-23 manual leg transition contract는 `RETIRED_FROM_MR`이다. Future GPS state machine으로 자동 승계하지 않는다. |
| BR-081 | 2026-08-23 Journey Abort contract는 `RETIRED_FROM_MR`이다. |
| BR-082 | metric eligibility는 departureP50At/departureP90At/arrivalP50At/arrivalP90At 및 milestone projection별 독립이다. |
| BR-083 | route discovery coverage와 WALK provider coverage, historical model coverage, realtime context coverage는 서로 다른 축이다. |
| BR-084 | canonical mapping 또는 historical model coverage가 부족한 candidate는 현재 요청한 기능을 `NOT_COMPUTED`로 둔다. realtime context만 부족한 경우 Arrival은 historical-only로 축소할 수 있다. |
| BR-085 | canonicalization crosswalk는 임의 OD의 Departure Recommendation과 Arrival Time Calculation 모두에 필요한 route Gate다. name-only/거리-only/다중 후보는 EXACT/UNAMBIGUOUS로 승격하지 않는다. |
| BR-086 | API 호출, 화면 표시, cache, raw/derived retention, Share/재배포 권한은 서로 다른 Gate이며 하나의 승인으로 다른 권한을 추론하지 않는다. |
| BR-087 | H100/Jupyter는 training plane이며 production direct call 금지. |
| BR-088 | AI/ML은 B leg residual/WAIT distribution source이며 final arrival distribution/route/evidence를 대체하지 않는다. |
| BR-089 | A historical artifact는 realtime/current vehicle/train feature를 사용하지 않는다. |
| BR-090 | B realtime feature는 `calculatedAt` 이전/동시에 observable하고 source timestamp가 유효해야 한다. |
| BR-091 | leading vehicle/congestion/headway feature는 identity·ordering·timestamp·coverage가 검증된 경우만 사용한다. |
| BR-092 | unsupervised cluster/regime을 delay seconds, 영향 weight, final time으로 직접 해석하지 않는다. |
| BR-093 | B realtime/AI model은 historical baseline 대비 hold-out value-add가 없으면 fallback하고 관련 claim을 하지 않는다. |

### Product Function / Entry / Milestone / Share

| BR | Rule |
|---|---|
| BR-094 | Departure Recommendation과 Leave-now Forecast는 별도 submit/API/result를 가진다. Shared Input Shell 사용은 허용하되 combined Dual Analysis는 금지한다. |
| BR-095 | 어느 기능도 다른 기능의 analysisId/result/session을 prerequisite로 요구하거나 자동 continuation하지 않는다. |
| BR-096 | route/cache/historical artifact/simulation library의 내부 재사용은 허용하지만 shared infrastructure를 shared product request/result로 노출하지 않는다. |
| BR-097 | Tab 전환은 analysis command가 아니며 API-011/API-012 자동 호출이나 hidden cross-type field 제출을 발생시키지 않는다. |
| BR-098 | Splash는 transient presentation state이며 분석/provider/permission prerequisite가 아니다. reduced-motion/asset fail 시 static fallback을 허용한다. |
| BR-099 | 사용자 milestone은 selected route에서 canonical identity가 확인되는 의미 있는 checkpoint만 사용한다. raw provider node 전체 자동 노출을 금지한다. |
| BR-100 | Departure milestone `normalAt`은 P50-plan conditional median, `bufferedAt`은 P90-plan conditional median이다. |
| BR-101 | Arrival milestone `normalAt`/`bufferedAt`은 departAt=now 조건 checkpoint Q0.50/Q0.90이다. |
| BR-102 | canonical Share는 opaque URL create/copy/public read-only이며 image/Kakao direct-send는 active MR 계약이 아니다. public token은 owner 권한으로 승격하지 않는다. |

## State Transition Rules

### State enums

| Domain | Values | MR 여부 |
|---|---|---|
| Launch | APP_START / SPLASH / INPUT_READY | ACTIVE |
| InputTab | DEPARTURE_RECOMMENDATION / LEAVE_NOW_FORECAST | ACTIVE UI state |
| AnalysisType | DEPARTURE_RECOMMENDATION / LEAVE_NOW_FORECAST | ACTIVE, immutable after submit |
| Analysis | IDLE / ANALYZING / SUCCEEDED / FAILED | ACTIVE |
| Realtime Context Coverage | FULL / PARTIAL / NONE | Leave-now only |
| Freshness | FRESH / AGING / STALE / PROVIDER_ERROR / NO_DATA | ACTIVE |
| Result Eligibility | USER_FACING / ENGINE_FIXTURE_ONLY / NOT_COMPUTED | ACTIVE |
| Validation Scope | UNVALIDATED / COMPONENT_ONLY / CORRIDOR_REPLAY / END_TO_END | ACTIVE |
| Share | IDLE / CREATING / CREATED / EXPIRED / REVOKED | ACTIVE |
| PWA Runtime | ONLINE / OFFLINE_SNAPSHOT / UPDATE_AVAILABLE | ACTIVE |
| Journey Lifecycle / Reforecast / Leg progress | legacy | RETIRED_FROM_MR |

### v0.3 Active transitions

| ST | Current | Event | Next | Invariant | REQ / AC |
|---|---|---|---|---|---|
| ST-036 | APP_START | LAUNCH | SPLASH | analysis/provider/permission call 0 | 117 / AC-081 |
| ST-037 | SPLASH | PRESENTATION_DONE_OR_FALLBACK | INPUT_READY+DepartureTab | default Departure tab; static fallback 허용 | 117 / AC-081 |
| ST-038 | INPUT_READY+DepartureTab | SELECT_ARRIVAL_TAB | INPUT_READY+ArrivalTab | API call 0, no analysisId | 113,118 / AC-082 |
| ST-039 | INPUT_READY+ArrivalTab | SELECT_DEPARTURE_TAB | INPUT_READY+DepartureTab | API call 0, no analysisId | 113,118 / AC-082 |
| ST-032 | Departure.IDLE | SUBMIT_DEPARTURE | Departure.ANALYZING | type fixed, API-011 only | 114 / AC-083 |
| ST-033 | Arrival.IDLE | SUBMIT_ARRIVAL | Arrival.ANALYZING | type fixed, departAt server now, API-012 only | 115 / AC-084 |
| ST-034 | *.ANALYZING | ANALYSIS_SUCCESS | sameType.SUCCEEDED | typed result + milestone semantics; cross metric 0 | 114~120,123 / AC-083~087 |
| ST-035 | *.ANALYZING | ANALYSIS_FAILED | sameType.FAILED | input preserved, no cross fallback | 050~056,116 / AC-084 |
| ST-040 | Result | SHARE_CREATE | Share.CREATING→CREATED | owner capability, API-007, immutable snapshot | 080~082,121 / AC-088 |
| ST-041 | Public URL | SHARE_READ | SCR-06 read-only | API-008, owner privilege 0 | 122 / AC-088,089 |
| ST-014~017 | source freshness | AGE/STALE/FAIL/RECOVER | freshness update | realtime coverage는 Arrival만 | 050~056 / AC-072 |
| ST-019 | ONLINE result | NETWORK_UNAVAILABLE | OFFLINE_SNAPSHOT | same analysisType read-only | 095 / AC-043 |
| ST-020 | OFFLINE/ONLINE | RESULT_REFETCH | ONLINE | same immutable analysis; auto cross-function/new now 없음 | 096 / AC-044 |
| ST-022 | ANY PWA | WORKER_WAITING | UPDATE_AVAILABLE/defer | safe schema activation | 097 / AC-045 |

### Superseded / Retired IDs

- ST-030~031: v0.2 `HOME→별도 input` transition, `SUPERSEDED_FROM_V0.3`.
- ST-001~003: v0.1 Dual Analysis execution trace, `RETIRED_FROM_MR`.
- ST-004~013, ST-018, ST-021, ST-023~029 중 manual Start/Event/Reforecast 의미: `RETIRED_FROM_MR`.
- 번호를 새 의미로 재사용하지 않는다.

## Error Taxonomy

| Code | Layer | User handling | Must preserve |
|---|---|---|---|
| INPUT_INVALID / TARGET_BEYOND_SUPPORTED_HORIZON | Client | Departure 입력 수정 | input |
| LOCATION_NOT_RESOLVED / UNSUPPORTED_GEOGRAPHY | Provider/Product | 입력 수정 | input |
| ROUTE_NOT_FOUND / ROUTE_PROVIDER_ERROR | Route | retry/edit | input/provenance |
| ROUTE_MAPPING_PARTIAL/FAILED | Mapping | 현재 function structure-only + NOT_COMPUTED | route structure |
| HISTORICAL_BASELINE_UNAVAILABLE | Data | 현재 function unavailable | route/evidence |
| MILESTONE_NOT_COMPUTED / MILESTONE_PARTIAL | Engine/Data | 해당 checkpoint time 숨김/limitation | route/semantics/version |
| REALTIME_CONTEXT_PARTIAL | Data | Arrival partial realtime | used/missing categories |
| REALTIME_CONTEXT_UNAVAILABLE | Data | historical-only Arrival if allowed | historical artifact |
| STALE_DATA | Data | stale feature 제외/refresh | last success |
| PROVIDER_ERROR / QUOTA | Provider/Ops | bounded retry/degrade | quota/provenance |
| ANALYSIS_TYPE_MISMATCH | Contract | expected type route로 coercion 금지 | analysisType/resource |
| ANALYSIS_FAILED | Engine | retry | request/provenance |
| MODEL_FALLBACK | ML | baseline 사용, claim 축소 | model/fallback trace |
| SHARE_EXPIRED / SHARE_NOT_FOUND / SHARE_REVOKED | Share | public variant | no private payload |
| NETWORK_UNAVAILABLE | PWA | offline snapshot | savedAt |
| SPLASH_ASSET_FAILURE | PWA/UI | static brand fallback 후 input 진입 | business flow |
| INTERNAL_ERROR | System | generic request ID | secure logs |

`EVENT_NOT_ALLOWED_IN_STATE`, `EVENT_ALREADY_APPLIED`, `TARGET_SERVICE_MISMATCH`, `REFORECAST_*`는 `RETIRED_FROM_MR`이다.

## API / System Interface Dictionary

### User-facing API

| ID | Method/Path | Purpose | Request core | Response core | Status |
|---|---|---|---|---|---|
| API-000 | POST `/api/v1/locations/search` | location resolve | query/one-shot coordinate | GeoPoint/provenance/quota | ACTIVE |
| API-001 | POST `/api/v1/route-candidates` | route discovery/crosswalk | origin,destination | candidates,mapping,coverage | ACTIVE |
| API-002 | legacy POST `/api/v1/journeys/analyze` | v0.1 Dual Analysis | — | — | RETIRED_FROM_MR |
| API-003 | legacy `/start` | manual live start | — | — | RETIRED_FROM_MR |
| API-004 | legacy v0.1 journey snapshot read | — | — | — | RETIRED_FROM_MR; replaced by API-013 |
| API-005 | legacy `/events` | UserEvent/Reforecast | — | — | RETIRED_FROM_MR |
| API-006 | GET `/api/v1/analyses/{analysisId}/evidence` | mode-scoped evidence | owner+analysisId | parent analysisType evidence + milestone semantics/provenance | ACTIVE |
| API-007 | POST `/api/v1/analyses/{analysisId}/share` | create public URL share | owner+analysisId | opaque publicUrl/token metadata/expiry/status | MUST |
| API-008 | GET `/api/v1/share/{token}` | public read-only share | token | one analysisType privacy-safe result + milestones | MUST |
| API-009 | GET `/api/v1/health/summary` | internal preflight | internal auth | provider/quota/artifact/realtime/model/distributed | ACTIVE |
| API-010 | legacy `/abort` | manual live abort | — | — | RETIRED_FROM_MR |
| API-011 | POST `/api/v1/departure-recommendations` | Departure Recommendation | origin,destination,targetArrivalAt | analysisId + Departure P50/P90 + departure milestones + historical summary | ACTIVE |
| API-012 | POST `/api/v1/leave-now-forecasts` | Arrival Time Calculation | origin,destination | analysisId + departAt + Arrival P50/P90 + arrival milestones + realtime coverage | ACTIVE |
| API-013 | GET `/api/v1/analyses/{analysisId}` | immutable result recovery | owner+analysisId | exactly one typed result envelope | ACTIVE |

#### API isolation rules

- API-011 response schema에 Arrival/realtime/P(on_time) fields가 존재하면 contract failure다.
- API-012 request에 mandatory targetArrivalAt이 있거나 response에 Departure/P(on_time) fields가 존재하면 contract failure다.
- API-011을 호출한 뒤 API-012를 자동 호출하지 않으며 반대도 동일하다.
- Tab switch만으로 API-011/012를 호출하지 않는다.
- API-013은 stored `analysisType`을 다른 type으로 변환하지 않는다.
- API-007/008 public payload는 owner capability/evidence privilege를 포함하지 않는다.

### Internal interfaces

| ID | Interface | Input→Output | Contract |
|---|---|---|---|
| SYS-001 | Location/WALK Adapter | query/points→GeoPoint/WALK point | provenance/quota/error |
| SYS-002 | Route Registry/Normalizer | provider candidate→RouteCandidate/Leg | shared crosswalk/time semantics |
| SYS-003 | Shared Reliability Math Library | leg distributions + simulation config→samples/metric primitives | user product result 직접 생성하지 않음 |
| SYS-004 | Collector | external API→Observation | timestamps/quota/raw policy |
| SYS-005 | Actual/Residual Builder | observations→Actual/Residual | identity/interval/sign |
| SYS-006 | Artifact/Validation Pipeline | Gold→historical artifact/model/eval | provenance/hold-out |
| SYS-007 | Quota Coordinator | reservation→permit/degradation | shared budget/no bypass |
| SYS-008 | AI Artifact/Inference Adapter | model+features→leg quantiles | Leave-now only, fallback |
| SYS-009 | Realtime Feature Builder | current obs→RealtimeFeatureSnapshot | Leave-now only, causality Gate |
| SYS-010 | Departure Recommendation Engine | route+historical artifact+target→DepartureRecommendationResult | realtime input interface 자체 없음 |
| SYS-011 | Leave-now Forecast Engine | route+historical+optional realtime+now→LeaveNowForecastResult | Departure/P(on_time) metric 생성 금지 |
| SYS-012 | Milestone Projector | typed simulation/scenario + canonical route→JourneyMilestoneProjection[] | BR-099~101 semantics, raw node 자동노출 금지 |

### 기준 기술과 배포 경계

기존 Next.js/Java21+Spring/Kafka/Flink/PostgreSQL/MinIO/Python-Spark/Docker/Nginx/EC2 2-node 구조를 유지한다. Operational PostgreSQL은 typed analysis record/result/access/share/quota를 SoT로 둔다. 2-node proof는 HA가 아니라 worker correctness/recovery proof다.

#### 2-node provisional deployment contract

기존 물리 배치 가설을 유지하되 보호 workload는 API-011/API-012/API-007/API-008, shared data pipeline, SYS-010~012, Historical Artifact, Realtime Feature pipeline이다. manual live state/event service는 배치 대상이 아니다.

## Entity / Data Dictionary

| ENT | Entity | 핵심 필드/의미 | Status/Invariant |
|---|---|---|---|
| ENT-001~010 | Observation→LegDistribution shared data entities | 기존 semantics 유지 | ACTIVE |
| ENT-011 | LegacyUnifiedJourneyRequest | v0.1 origin,destination,target unified request | RETIRED_FROM_MR |
| ENT-012 | JourneyState | legacy live | RETIRED_FROM_MR |
| ENT-013 | UserEvent | legacy manual event | RETIRED_FROM_MR |
| ENT-014 | AnalysisSimulationRun | analysisId,analysisType,route,departAtNullable,seed,N,versions,provenance | shared/reproducible |
| ENT-015 | LegacyDualAnalysisResultSnapshot | v0.1 Departure+Arrival combined result | RETIRED_FROM_MR |
| ENT-016 | GeoPoint | lat/lon/label/source/role | ACTIVE |
| ENT-017 | NodeRef | namespace/providerID/name/mode/line/coordinate/mappingVersion | ACTIVE |
| ENT-018 | RouteLeg | sequence/mode/route/from/to/metadata | ACTIVE |
| ENT-019 | ShareSnapshot | analysisType,tokenDigest,status,expiresAt,publicProjection | immutable public read-only; mixed type 금지 |
| ENT-020 | AnonymousAccessGrant | analysisId,capabilityDigest,status/expiry | owner access |
| ENT-021 | OfflineAnalysisProjection | analysisId,analysisType,savedAt,summary,limitations | not-current read-only |
| ENT-022 | PwaRuntimeManifest | app/cache/worker/displayMode/version | runtime |
| ENT-023 | QuotaLedger | provider/credential/day/limit/reservation/used/yield | audit |
| ENT-024 | ProviderPolicyRegistry | terms/retention/cache/redistribution | default-deny |
| ENT-025 | ModelArtifactManifest | model/version/hash/schema/dataset/eval/modelCard | training-serving boundary |
| ENT-026 | ModelInferenceTrace | model/version/schema/leg/quantiles/latency/fallback | Leave-now provenance |
| ENT-027 | HistoricalReliabilityArtifact | version/window/grouping/distributions/support/fallback/validation | shared baseline SoT |
| ENT-028 | RealtimeFeatureSnapshot | snapshotId,calculatedAt,categories,identities,observedAt,freshness,coverage,schema,flags | Leave-now only |
| ENT-029 | DepartureRecommendationRequest | origin,destination,targetArrivalAt,requestedAt,planningHorizonVersion | realtime/departAt field 없음 |
| ENT-030 | LeaveNowForecastRequest | origin,destination,requestedAt | targetArrivalAt/client departAt 없음 |
| ENT-031 | DepartureRecommendationResult | analysisId,targetArrivalAt,departureP50At,departureP90At,milestones,historicalCoverage,eligibility,calculatedAt,limitations | Arrival/realtime/P(on_time) 없음 |
| ENT-032 | LeaveNowForecastResult | analysisId,departAt,arrivalP50At,arrivalP90At,milestones,historicalCoverage,realtimeCoverage,eligibility,calculatedAt,limitations | target/P(on_time)/Departure metric 없음 |
| ENT-033 | AnalysisRecord | analysisId,analysisType,routeCandidateId,status,createdAt,calculatedAt,resultRef | analysisType immutable; exactly one request/result type |
| ENT-034 | JourneyMilestoneProjection | sequence,milestoneType,label,subLabel,nodeRefInternal,normalAt,bufferedAt,eligibility,limitations,scenario,semanticsVersion | engine-produced; privacy projection separate |

### Identity rules

기존 Bus/Subway/mixed crosswalk identity 규칙을 유지한다. leading vehicle feature는 route/direction/order/time 검증이 필요하다. Milestone은 ENT-018 route structure와 canonical NodeRef/leg boundary에 연결되어야 하며 display label만으로 identity를 확정하지 않는다.

### Data Quality minimum flags

기존 flags에 `ANALYSIS_TYPE_MISMATCH`, `CROSS_FUNCTION_METRIC_CONTAMINATION`, `REALTIME_FEATURE_STALE`, `LEADING_VEHICLE_UNVERIFIED`, `HEADWAY_UNVERIFIED`, `CONGESTION_UNVERIFIED`, `FEATURE_LEAKAGE_RISK`, `HISTORICAL_BUCKET_LOW_SUPPORT`, `MILESTONE_IDENTITY_UNVERIFIED`, `MILESTONE_TIME_NOT_COMPUTED`, `MILESTONE_SEMANTICS_MISMATCH`를 추가한다.

## Non-functional Requirements

### Performance / Correctness

| NFR | Priority | Requirement | Measurement / Gate |
|---|---|---|---|
| NFR-001 Interactive Analysis | MUST/TBD_AFTER_PROFILE | 각 기능의 Web interactive experience; timeout에서 fake result 금지 | first vertical slice p50/p95 후 목표 고정 |
| NFR-002 Reforecast | RETIRED_FROM_MR | 2026-08-23 manual reforecast performance trace | N/A |
| NFR-003 Bounded Simulation | MUST/TBD_AFTER_PROFILE | 각 기능 대표 artifact에서 metric 수렴, fixed-seed 재현성, 응답시간·자원을 만족하는 최소 N versioning | convergence/performance benchmark |
| NFR-020 Deterministic Regression | MUST | fixed fixture/artifact/seed에서 동일 또는 tolerance 내 결과 | CI regression |
| NFR-021 Timezone | MUST | timezone-aware, Asia/Seoul UI, midnight rollover | unit/integration |
| NFR-022 Schema/Version | MUST | breaking change version, rule/artifact/engine/mapping/feature/model schema version | contract tests |
| NFR-023 Idempotency/Dedup | MUST | analysis request coalescing, Share create, Residual/Artifact build retry가 duplicate result/event를 만들지 않음 | duplicate request/build tests |
| NFR-097 Historical Artifact Reproducibility | MUST | 동일 input manifest·rule·schema에서 동일 artifact 또는 선언 tolerance로 재현 | artifact manifest/checksum |
| NFR-098 Realtime Feature Causality | MUST | 모든 active Leave-now realtime feature는 `observedAt≤calculatedAt`, outcome-derived field 0, identity/freshness flag 보존 | leakage audit + feature snapshot test |
| NFR-099 Model Incremental Value | CLAIM_GATE | realtime model candidate(B2/U1)는 historical baselines(B0/B1) 대비 temporal hold-out pinball/coverage/calibration/value-add 및 ops cost Gate 통과 | evaluation report + promotion decision |
| NFR-100 Product Function Isolation | MUST | API/UI/entity contract에서 한 analysisType에 다른 기능 metric 0, 독립 호출 가능, automatic cross-function invocation 0 | schema/contract/E2E isolation tests |
| NFR-101 Splash Accessibility/Failure Safety | MUST | Splash는 provider/API/permission과 분리, reduced-motion/static fallback, asset failure로 input 진입 차단 금지 | AC-081 + real-device/a11y |
| NFR-102 Milestone Projection Correctness | MUST/CLAIM_GATE | 동일 route/scenario/seed/version에서 milestone ordering/semantics 재현, unsupported checkpoint fabricated time 0 | AC-085~087 + CG-011 |

### Freshness / Availability / Recovery

| NFR | Priority | Requirement | Measurement / Gate |
|---|---|---|---|
| NFR-010 Timestamp Integrity | MUST | requested 직전/received 직후/source time/calculatedAt 분리 | live boundary test |
| NFR-011 Provider-specific Freshness | MUST/TBD_AFTER_PROFILE | provider cadence/lateness 기반 threshold | valid timestamp profile |
| NFR-030 Provider Failure | MUST | historical artifact 문제와 realtime feature stale/error/no-data/quota를 분리 | failure injection/API fixtures |
| NFR-031 Restart Recovery | MUST | analysis result/access/share/quota/artifact reload; unfinished manual mutation 개념 없음 | restart/restore smoke |
| NFR-032 Rollback | MUST | engine/artifact/model/feature schema/code rollback과 provenance 유지 | release drill |

### Security / Privacy

| NFR | Priority | Requirement | Acceptance |
|---|---|---|---|
| NFR-040 Secret | MUST | key가 repo/frontend/log/error/README에 없음; quota 우회 rotation 금지 | secret scan critical 0, bundle key 0 |
| NFR-041 HTTPS | MUST | deployed Web/API HTTPS, internal admin UI 제한 | route smoke/security review |
| NFR-042 CORS | MUST | explicit origin allow-list, credential+`*` 금지 | preflight tests |
| NFR-043 Log Masking | MUST | key/auth/exact origin/raw payload 반복 로그 금지 | log inspection |
| NFR-050 Data Minimization | MUST | account 없음; exact coordinate/free-text location analytics 기본 저장 금지; GPS trace MR 수집 0 | payload/event review |
| NFR-051 Share Privacy | MUST/G5 | exact origin/GPS/raw ID/debug 제외, opaque token, public projection 최소화 | AC-025,088 |
| NFR-052 Retention | MUST/TBD_AFTER_PROFILE | analysis/share TTL을 G5에서 확정, 그 전 임의 기간 금지 | security decision+expiry test |
| NFR-053 Anonymous Authorization | MUST/G5 | owner capability는 HttpOnly/Secure/적절한 SameSite channel, URL·JS·DOM·analytics 미노출; result/evidence/share-create server-side 검증 | AC-035 + security review |
| NFR-054 Analytics Privacy | MUST/G5 | raw analysisId/token/free-text location/vehicle ID/congestion raw value 기본 analytics 금지; category/coverage만 목적 승인 후 | payload/event/log review |
| NFR-093 CSRF/Referrer/Cache | MUST/G5 | cookie 기반 Share-create mutation은 CSRF token 또는 strict Origin/SameSite 검증; owner/share response no-store; share no-referrer | AC-039 + security review |
| NFR-094 Provider Policy Default-Deny | MUST/G5 | ProviderPolicyRegistry에서 raw retention 권한 확정 전 persistent raw storage·cross-session cache·redistribution default deny | AC-063 + registry review |

### Observability / Operations

| NFR | Priority | Requirement | Required signals |
|---|---|---|---|
| NFR-060 Collector/Quota Budget | MUST | 모든 collector/user adapter가 SYS-007 통과; credential alias×KST-day budget/reservation/retry/business error | calls,reserved/used/remaining,reset,latency,yield |
| NFR-061 Data/Stream | MUST | join/dedupe/out-of-order/Actual/Residual + historical build/realtime feature health | rates,lag,state,checkpoint,backpressure,artifact yield |
| NFR-062 API/Product | MUST | function별 latency/error/eligibility; Leave-now realtime coverage | p50/p95,error code,result state,analysisType |
| NFR-063 Artifact/Model | MUST | historical artifact/model/evaluation age/version/load/fallback | artifact/model age/version/load success |
| NFR-064 Backup/Restore | MUST | canonical data, DB, permitted raw, artifact/model | restore smoke |
| NFR-065 Demo Preflight | MUST | Route A route/WALK/provider quota, latest historical artifact, optional realtime/model status, secret scan, rollback, PWA version | release checklist |
| NFR-066 Internal QA Isolation | MUST | Route B fixture/selector/analytics는 data/topology/identity QA runner에만 존재; public demo/production 노출 0 | config/build/route/event scan |
| NFR-067 Quota Priority/Degradation | MUST | `두 기능의 사용자 요청·Route A demo → historical Claim Gate corridor → realtime feature validation → coverage → experiment` 순 예약 | exhaustion/degradation log |
| NFR-068 Call Efficiency | MUST | bulk 우선, static/version cache, identical snapshot dedupe, cohort/window schedule, adaptive cadence, bounded retry | unique snapshot/Actual/Residual/useful-feature yield per call |
| NFR-069 Quota Application/Alternative Source | MUST operational | official quota application/alternative source는 provider별 별도 검증; approval을 release blocker로 가정 금지 | application/provider review |

#### Quota Budget v1 contract

2026-08-23 source별 approved limit/status와 Subway `PENDING_RECONCILIATION`은 `DECISION_SHEET_260825_v0.3.md`의 historical evidence를 정본으로 사용한다. 숫자를 이 문서에서 다시 추정하지 않는다. realtime feature 수집도 동일 SYS-007 ledger에 포함한다.

#### Public API Admission Control

| NFR | Priority | Requirement | Measurement / Gate |
|---|---|---|---|
| NFR-090 Client/Session Admission Control | MUST | `/locations/search`,`/route-candidates`,`/departure-recommendations`,`/leave-now-forecasts` 호출 빈도 제한; threshold TBD | rate-limit test |
| NFR-091 Request Dedup/Coalescing | MUST | 동일 `analysisType`의 정규화 typed input 동시 요청은 in-flight coalescing; Departure만 targetArrivalAt을 key에 포함하고 Arrival은 origin/destination+request context를 사용 | duplicate call ratio |
| NFR-092 Concurrency Cap | MUST | provider별 concurrency cap/circuit breaker; quota-exhaustion과 retry 가능 시점 표현 | concurrency injection |

### Responsive / Accessibility

| NFR | Priority | Requirement | Acceptance |
|---|---|---|---|
| NFR-070 Responsive | MUST | Shared Input Shell과 Departure/Arrival result/milestone/share가 mobile/tablet/desktop에서 핵심 정보 삭제 없이 동작 | viewport E2E |
| NFR-071 Non-color State | MUST | historical-only/partial/stale/error를 text/icon/copy로 전달 | visual/a11y |
| NFR-072 Keyboard/Focus | MUST | form/CTA/evidence/share keyboard, focus restore/live region | manual+automated |
| NFR-073 Reduced Motion/Reflow | MUST | zoom/reflow/reduced motion, Splash static fallback, 결과 정확도 암시 animation 금지 | manual |
| NFR-074 Mobile Browser Parity | MUST | iOS/Android browser와 standalone에서 Splash→Shared Input의 두 submit flow 및 URL Share 의미·guard·copy 동등 | real-device E2E |
| NFR-075 Installability | MUST | manifest/icon/start URL/display/HTTPS | install audit |
| NFR-076 Offline Privacy/Honesty | MUST | shell/static + privacy-safe snapshot만 offline; B를 current/live로 표현 금지 | cache/storage inspection |
| NFR-077 Foreground Recovery | MUST | 저장된 result refetch; 자동 now recompute 없음 | lifecycle/network test |
| NFR-078 Update Safety | MUST | worker/cache/app version 관측, 구 schema snapshot resurrection 방지 | update/rollback matrix |
| NFR-079 Device Permission/Share | MUST | origin one-shot geolocation; background/continuous GPS MR prompt 0; URL clipboard unavailable 시 수동 copy fallback | real-device test |

### Distributed Proof

| NFR | Priority | Requirement | Acceptance |
|---|---|---|---|
| NFR-080 Real vs Amplified | MUST for proof | replay multiplier/purpose 표시, amplified는 training support 금지 | run manifest |
| NFR-081 Worker Participation/Failure | MUST | Kafka partition input을 2개 이상 worker task가 처리하고 worker 종료 후 checkpoint/restart 또는 replay 복구 | participation/recovery evidence |
| NFR-082 Correctness | MUST | single vs multi-worker input/output count·checksum, duplicate/loss 0, keyed identity state consistency | correctness manifest |
| NFR-083 Two-node Deployment | MUST/G6 | EC2-A serving, EC2-B processing 기본; resource 부족 시 worker-level proof로 scope 축소 가능, 물리 2-node claim 조건 분리 | deployment manifest |
| NFR-084 Quota Budget | MUST/G3 | source approved status/reservation/forecast/degradation이 ENT-023에 존재 | quota manifest |
| NFR-085 PWA Compatibility Matrix | MUST/G4 | iOS/Android browser/standalone + desktop secondary run version 기록 | AC-050 |
| NFR-086 Route A Demo/Protected E2E | MUST/G6 | `APP-SPLASH→Input[Departure]→02→05/Share`와 `APP-SPLASH→Input[Arrival]→08→05/Share`를 실제 product flow로 시연; Route B/mock replacement 금지 | AC-081~090 |
| NFR-087 Kakao WALK / Route Provider Contract | MUST for WALK,D2 target route | WALK point provider와 publictraffic discovery/crosswalk Gate 분리; 2026-08-23 판정 보존 | AC-053~056 |
| NFR-088 Provider Provenance/Cache | MUST | provider/endpoint/adapter/crosswalk/version/hash 보존; cross-provider silent cache 대체 금지 | provider contract tests |

### AI / ML Serving Boundary

| NFR | Priority | Requirement | Acceptance |
|---|---|---|---|
| NFR-095 Training/Serving Plane Separation | MUST/CLAIM_GATE | H100/Jupyter/Notebook은 offline training/eval 전용; runtime은 versioned artifact만 사용 | AC-065 |
| NFR-096 Inference Latency/Fallback | D2_TARGET/CLAIM_GATE | JR_REALTIME_QUANTILE_MODEL bounded inference; 실패/미달 시 B1→B0 fallback | AC-066 |
| NFR-099 Model Incremental Value | CLAIM_GATE | realtime/unsupervised feature model은 same temporal hold-out에서 baseline value-add 통과 전 claim 금지 | AC-074 |


## Acceptance Test Scenarios

### v0.2 Product Split Scenarios — Historical / Superseded Entry

| AC | Scenario | v0.3 Status |
|---|---|---|
| AC-075 | Service Home 두 CTA | `SUPERSEDED_FROM_V0.3`; history 보존 |
| AC-076 | Home→Departure independent flow | entry 부분 superseded; API/result isolation 의미는 AC-083으로 승계 |
| AC-077 | Home→Leave-now independent flow | entry/target 부분 superseded; API/result isolation 의미는 AC-084로 승계 |
| AC-078 | API/schema isolation | v0.3 schema로 갱신되어 active 의미는 AC-083/084/090 |
| AC-079 | analysisType route guard | active 의미 유지 |
| AC-080 | Evidence/Share isolation | active 의미 유지, URL Share AC-088/089로 확장 |

### v0.3 Entry / Milestone / URL Share Scenarios

| AC | Scenario | Expected | Related |
|---|---|---|---|
| AC-081 | App launch / Splash | provider/API/permission 선행 0; reduced-motion/asset fail static fallback 후 Shared Input 진입 | REQ-117,NFR-101 |
| AC-082 | Shared Input Tab switch | Departure↔Arrival Tab 전환, API 호출/analysisId 생성 0 | REQ-113,118,BR-097 |
| AC-083 | Departure independent submit | API-011만 호출; target required; Departure P50/P90 + Departure milestones; Arrival/realtime/P(on_time) 0 | REQ-114,107~109,119 |
| AC-084 | Arrival independent submit | API-012만 호출; request origin+destination; departAt server now; Arrival P50/P90 + milestones; target/P(on_time)/Departure 0 | REQ-115,011,012,120 |
| AC-085 | Departure milestone semantics | normal=P50-plan conditional median, buffered=P90-plan conditional median; route order/version 보존 | REQ-119,123,NFR-102 |
| AC-086 | Arrival milestone semantics | departAt=now checkpoint Q0.50/Q0.90; 90% accuracy copy 0 | REQ-120,123,NFR-102 |
| AC-087 | Milestone integrity/fallback | raw provider node 자동노출 0, FE fabricated accumulation 0, unsupported milestone null/limitation | REQ-016,103,123 |
| AC-088 | URL Share E2E | owner API-007 URL 생성/복사→recipient API-008 public read-only view; single analysisType | REQ-080,082,121,122 |
| AC-089 | Share expiry/revoke/privacy | expired/revoked public error, cache resurrection 0, exact origin/raw ID/owner capability 0 | REQ-080~082,122; NFR-051~054,093 |
| AC-090 | v0.3 legacy active scan | Service Home active, B mandatory target/P(on_time), image/Kakao direct send, Dual Analysis, Start/Event/Reforecast 모두 0 | retired/superseded set |

### Active / Updated Core Scenarios

| AC | Scenario | Expected | Related |
|---|---|---|---|
| AC-001 | valid common input | origin/destination 공통 resolve 성공; target validation은 Departure에만 적용 | REQ-001~003 |
| AC-002 | unsupported/mapping fail | fabricated number 대신 explicit error/structure-only | REQ-005,054 |
| AC-003 | critical historical missing | 현재 function NOT_COMPUTED; 다른 function fake result 생성 0 | REQ-016,055 |
| AC-004 | route selection | provider order first supported, reliability reorder 0 | REQ-005,006 |
| AC-016~023 | WALK/Transfer/Evidence/WAIT | 기존 semantics/support/fallback 계약 유지 | REQ-030~073 |
| AC-025 | Share privacy | exact origin/raw ID/other function metric 0 | REQ-080~082 |
| AC-026~033 | Data/Residual | timestamp/identity/residual/leakage 계약 유지 | REQ-060~067 |
| AC-034 | Final trace | 각 기능 result+milestone이 real pipeline/provenance로 trace | REQ-090,091,123 |
| AC-035 | Anonymous auth | analysisId별 enumeration-safe owner guard | REQ-007 |
| AC-041~050 | PWA/Ops/Deployment | mobile/offline/update/permission/infra proof | REQ-093~098,NFR |
| AC-053~057 | Kakao evidence | 기존 2026-08-23 판정 보존 | REQ-008,009,104,105 |
| AC-061~063 | Arbitrary OD/policy | 각 function 독립 eligibility, provider/default-deny | REQ-104,105 |
| AC-065~066 | AI isolation/fallback | Leave-now only model, runtime training direct call 0 | REQ-106 |
| AC-067 | Legacy contract audit | targetReliability, legacy Recommended, API-002 Dual, manual tracking active 0 | retired set |
| AC-068 | Departure math | .50/.90 threshold, realtime input 0, simple subtraction 0 | REQ-107,108 |
| AC-069 | Arrival math | departAt=now, Arrival P50/P90, realtime coverage; P(on_time) active 0 | REQ-011,012,111 |
| AC-070~074 | Hold-out/artifact/realtime/model | 기존 Gate semantics 유지 | REQ-106~112 |

### Retired Scenarios

- 2026-08-23 manual Start/Event/Reforecast AC IDs는 `RETIRED_FROM_MR`.
- v0.1 Dual Analysis UI/API behavior는 `RETIRED_FROM_MR`.
- v0.2 Home-based entry와 B target/P(on_time) flow는 history로 보존하되 v0.3 release acceptance가 아니다.

## Claim Gates와 Evidence Dependency

| CG | Claim | Required Evidence | Current/Fallback |
|---|---|---|---|
| CG-001 | Whole-Journey calibrated | independent V3 Journey outcomes | NOT_STARTED; calibration claim 금지 |
| CG-002 | Mature Bus Historical Reliability | target mapping + multi-window residual/support/hold-out | INSUFFICIENT |
| CG-003 | Mature Subway Historical Reliability | station×line multi-window residual/hold-out | CONDITIONAL |
| CG-004 | Departure P50/P90 usable | historical service/WAIT/residual + candidate re-eval + hold-out coverage | PENDING; 미달 NOT_COMPUTED |
| CG-005 | Empirical WAIT support | passenger-relevant/dependence-aware unit | NOT_STARTED |
| CG-006 | Distributed performance/recovery | multi-worker failure/correctness/replay | NOT_STARTED |
| CG-007 | General Model Promotion | temporal hold-out baseline comparison | HOLD |
| CG-008 | JR Realtime Quantile Model serving | artifact/eval/latency/fallback | PENDING; baseline fallback |
| CG-009 | Realtime Feature Availability | identity+timestamp+freshness+coverage for candidate features | NEW/UNVERIFIED; historical-only B |
| CG-010 | Realtime/Unsupervised Incremental Value | B2/U1 vs B0/B1 hold-out improvement | NEW/NOT_STARTED; no uplift→claim 금지 |
| CG-011 | Milestone Time Projection | canonical milestone identity + scenario/quantile semantics + replay/hold-out/reproducibility | NEW/PENDING; 미달 milestone time 숨김/limitation |

### Evidence guardrails

기존 2026-08-23 Bus/Subway/WAIT/Kakao evidence 제한을 유지한다. 추가 guardrail:

- Figma example 시간은 validation/calibration evidence가 아니다.
- `congetion` 존재 가능성은 leading vehicle congestion availability/effect 증거가 아니다.
- vehicle 순서/거리/headway는 identity와 timestamp가 검증되기 전 feature로 사용하지 않는다.
- unsupervised cluster는 actual delay label을 설명하거나 weight를 정한 증거가 아니다.
- B realtime model claim은 historical-only baseline보다 같은 hold-out에서 개선돼야 한다.
- milestone UI가 존재한다는 사실은 milestone accuracy/coverage가 검증됐다는 뜻이 아니다.

## End-to-End Traceability Matrix

| F | SCR/State | Active REQ | API/SYS | ENT | AC/CG |
|---|---|---|---|---|---|
| F001 | APP-SPLASH/01/07 | 001~003,007,100,113,117,118 | API-000,011~013 | 016,020,029,030,033 | AC-001,035,046,081~084 |
| F002 | 01/02/07/08/05 | 005~009,104,105 | API-001,011,012,006,009; SYS-002,007 | 005,017,018,033 | AC-004,053~057,061,062 |
| F003 | 01/02/05/06 | 107~109,114,116,119,123 | API-011,013,006,007; SYS-003,010,012 | 027,029,031,033,034 | AC-068,071,083,085,087; CG-004,011 |
| F019 | 07/08/05/06 | 011,012,110~112,115,116,120,123 | API-012,013,006,007; SYS-003,008,009,011,012 | 028,030,032,033,034 | AC-069,072,074,084,086,087; CG-008~011 |
| F020 | 02/08/05/06 | 119,120,123 | API-011~013,006~008; SYS-002,003,010~012 | 018,031,032,034 | AC-085~089; CG-011 |
| F004~006 | 03/04 | retired | retired | 012,013 | retired |
| F007~008 | 02/08/05 | 030~035 | SYS-001~003 | 006~010,016,017 | AC-016,017,027 |
| F009 | 02/08/05 | 040~045,116,123 | API-006,011~013 | 010,027~034 | AC-018~021,080,087 |
| F010 | 01/02/07/08/05 | 050~056 | API-011~013,006; SYS-004,009 | 001,027,028,031~034 | AC-028,029,072 |
| F011~012 | Data/05 | 060~073,109~111 | SYS-003~006,009~012 | 001~010,027,028,034 | AC-019,023,026,030~033,071,072,085~087; CG-002~005,009,011 |
| F013 | OVL/06 | 080~082,121,122 | API-007,008 | 019,020,033,034 | AC-025,088,089 |
| F014 | 05/Internal | 090~092 | API-006,SYS-002~006,012 | shared entities | AC-034,040 |
| F015~016 | Global/Ops | security/provider NFR | active APIs | 020,023,024,033 | AC-029,035,048,049,063,088,089 |
| F017 | 08/05/Internal | 106,110~112 | SYS-006,008,009,011 | 025,026,028,032 | AC-065,066,072,074; CG-008~010 |
| F018 | APP-SPLASH/01/02/07/08/05/06 | 093~098,117,118 | API-000,006~013 | 019~022,029~034 | AC-041~047,081~090 |

### Traceability completeness rules

- 모든 active MUST/CLAIM_GATE REQ는 AC 또는 CG를 가진다.
- API-002/ENT-011/ENT-015 v0.1 Dual contract는 active SCR/F에 연결하지 않는다.
- SCR-00 v0.2 Home contract는 `SUPERSEDED_FROM_V0.3`이며 APP-SPLASH 의미로 재사용하지 않는다.
- Departure와 Leave-now result schema는 서로의 final metric ID를 참조하지 않는다.
- REQ-013 P(on_time)은 historical retired trace이며 active F019/API-012/ENT-032에 연결하지 않는다.
- milestone projection은 ENT-034/SYS-012/REQ-119~120,123/CG-011로 닫힌다.
- Product 변경은 Service/IA/Requirements/Decision v0.3에서 동시에 반영한다.
- 새로운 factual claim은 Decision/Evidence 없이 추가하지 않는다.

## Development-only Decisions / TBD Register

| Item | Status | Resolution artifact | Safe behavior |
|---|---|---|---|
| Splash motion duration/easing | TBD_DESIGN | design implementation | static fallback; 수치 임의 고정 금지 |
| provider stale thresholds | TBD_AFTER_PROFILE | latency profile/ADR | stale feature current 사용 금지 |
| support thresholds | CLAIM_GATE | SUPPORT_RULE_V1 | INSUFFICIENT |
| function별 latency SLO | TBD_AFTER_PROFILE | two submit-flow benchmark | fake progress/number 금지 |
| partition/watermark/state/checkpoint | TBD_AFTER_PROFILE | stream ADR | arbitrary scaling claim 금지 |
| historical bucket granularity | NEW/TBD | multi-window profile | broader pooling은 fallback 표시 |
| Departure candidate grid/coarse-to-fine | CG-004 | benchmark/eval | simple subtraction 금지 |
| milestone selection rule detail | NEW/TBD | MILESTONE_RULE_V1 | canonical checkpoint만, raw node 자동노출 금지 |
| milestone support/coverage threshold | CG-011 | replay/hold-out profile | time 숨김/limitation |
| leading vehicle identity | UNVERIFIED | feature feasibility experiment | feature 미사용 |
| current/leading congestion availability | UNVERIFIED | raw schema+coverage experiment | feature 미사용 |
| headway/distance feature | UNVERIFIED | route/order/timestamp validation | feature 미사용 |
| realtime feature freshness threshold | TBD_AFTER_PROFILE | feature latency profile | stale 제외 |
| JR_REALTIME_QUANTILE_MODEL | PENDING | CG-008/010 | B1/B0 fallback |
| unsupervised traffic regime | OPTIONAL | U1 eval | 일반 result에 영향 claim 금지 |
| Future GPS Tracking | FUTURE_GPS_RESEARCH | 별도 privacy/accuracy/battery research | MR route/API/state 없음 |
| Share/owner TTL, analytics retention | G5 | security/privacy decision | 최소화/default deny |
| Public Share cache detail | G5 | security review | no-store/no-referrer baseline |
| Kakao crosswalk/provider policy | 기존 2026-08-23 상태 유지 | REQ-105/registry | unsupported/structure-only/default-deny |

## Security / Operations Release Checklist

- [ ] repo/frontend/log secret critical 0, HTTPS/CORS/access guard 검증.
- [ ] exact coordinate/token/raw IDs가 analytics/Public Share에 없음.
- [ ] provider quota ledger/degradation, 2026-08-23 verified statuses를 임의 수정하지 않음.
- [ ] historical artifact version/data window/support/fallback/validation trace 가능.
- [ ] B realtime feature는 identity/timestamp/freshness Gate를 통과한 category만 사용.
- [ ] leading vehicle/congestion/headway unverified feature가 active schema/result에 없음.
- [ ] active Service Home route/CTA 0; Splash→Shared Input 정상.
- [ ] Tab switch가 분석 API를 호출하지 않음.
- [ ] API-011/API-012 schema cross-function metric contamination 0.
- [ ] API-012 active request에 mandatory targetArrivalAt, response에 P(on_time) 0.
- [ ] milestone identity/semantics/version trace 가능, FE fabricated time 0.
- [ ] API-007/008 URL share create/read, expiry/revoke/privacy/owner boundary 검증.
- [ ] image/Kakao direct-send canonical CTA 0.
- [ ] 한 기능이 다른 기능 analysisId/result를 prerequisite로 요구하는 코드/계약 0.
- [ ] targetReliability/Recommended `{p*}`/API-002 Dual/Start/Event/Reforecast active route·API·UI 0.
- [ ] offline/foreground에서 이전 B snapshot을 current로 승격하지 않음.
- [ ] H100/Jupyter direct runtime call 0, model fallback 정상.
- [ ] B2/U1 claim은 baseline hold-out uplift evidence가 있을 때만.
- [ ] distributed proof를 HA/SLA로 표현하지 않음.
- [ ] Future GPS를 구현된 기능처럼 표현하거나 background permission을 요청하지 않음.

## 정본 정합성 규칙

- canonical product commands는 `DEPARTURE_RECOMMENDATION`, `LEAVE_NOW_FORECAST` 두 개이며 서로 독립 호출 가능하다.
- active entry는 APP-SPLASH→Shared Input Shell이며 SCR-00 Service Home은 `SUPERSEDED_FROM_V0.3` history다.
- Shared Input Shell 사용은 UI reuse이며 Tab switch는 analysis command가 아니다.
- v0.1 `Dual Analysis`, API-002, ENT-011/015 combined contract는 `RETIRED_FROM_MR`이다.
- Departure API/result에는 Departure P50/P90 + Departure milestone projection만 존재한다.
- Leave-now API/result에는 departAt, Arrival P50/P90 + Arrival milestone projection만 존재한다.
- Leave-now active request에 mandatory targetArrivalAt이 없고 active result/share에 P(on_time)이 없다.
- analysisType은 immutable이며 wrong-type route/read를 coercion하지 않는다.
- milestone은 ENT-034/SYS-012 versioned engine output이며 FE fabricated accumulation을 금지한다.
- Evidence/Public Share는 single analysisType payload다.
- URL Share public token은 owner capability와 분리된다.
- image/Kakao direct-send는 canonical v0.3 Share가 아니다.
- shared route/data/math library는 product request/result 결합을 의미하지 않는다.
- Departure는 realtime feature를 사용하지 않는다.
- Leave-now realtime은 causality/identity/freshness Gate를 통과한다.
- P50을 평균으로 정의하지 않는다.
- manual tracking/Future GPS/history 경계를 유지한다.
- 과거 Evidence status와 검증되지 않은 feature effect를 fabricated하지 않는다.

## Appendix — Claim wording guardrail

| 금지 | 허용 |
|---|---|
| `한 번에 두 기능 계산` / `통합 분석` | `두 독립 command가 Shared Input Shell과 Reliability Platform을 사용` |
| `Home에서 두 기능 선택`을 v0.3 active flow로 표현 | `Splash 후 Input Tab에서 기능 선택` |
| `P50 평균` | `P50 중앙값/50% threshold` |
| `P90 90% 정확` | percentile/threshold + validation scope |
| Departure에 `실시간 반영` | historical-only planning |
| Arrival에 Departure P50/P90 또는 P(on_time) | Arrival P50/P90 + realtime coverage |
| `AI가 최종 도착시간을 직접 계산` | AI는 Leave-now leg distribution 보정 |
| `경유지 시간은 단순 누적` | versioned milestone projection |
| `이미지/카카오톡 직접 공유` | public URL 생성/복사 + read-only view |
| `앞차 영향 검증됨` | 검증 대상 feature candidate |
| `GPS 자동 추적 가능` | Future GPS Research |

## Appendix — Definition of Done

**G2 DONE**: APP-SPLASH 이후 Shared Input Shell에서 두 기능을 Tab으로 선택하되 Tab switch 자체는 계산을 실행하지 않고, API-011에는 Departure P50/P90 + Departure milestone projection만, API-012에는 departAt + Arrival P50/P90 + Arrival milestone projection만 존재하며 mandatory B target/P(on_time)이 0이고, milestone은 ENT-034/SYS-012 versioned projection으로 추적되며, API-007/008 URL share가 owner/public 권한을 분리해 동작하고, 다른 기능 prerequisite/automatic continuation·active Home·Dual Analysis·manual tracking이 0이며 모든 active MUST/CLAIM_GATE REQ가 AC/CG로 닫힌다.**

