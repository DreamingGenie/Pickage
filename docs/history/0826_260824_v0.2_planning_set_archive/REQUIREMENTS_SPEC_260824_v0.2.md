# Journey Reliability 요구사항정의서 — v0.2

> **문서 목적**: 확정 Service Plan과 IA를 구현 가능한 기능·규칙·인터페이스·데이터·품질·인수 계약으로 변환한다.  
> **문서 지위**: Product / Frontend / Backend / Data / Infra / QA 개발 handoff 정본  
> **정본 파일명**: `REQUIREMENTS_SPEC_260824_v0.2.md`  
> **버전**: v0.2 — 두 제품 기능의 API/Entity/Result 계약 완전 분리  
> **기준일**: 2026-08-24  
> **상위 기준**: `SERVICE_PLAN_260824_v0.2.md`, `IA_SCREEN_SPEC_260824_v0.2.md`  
> **적용 원칙**: Evidence에 없는 수치로 빈 셀을 채우지 않는다. 측정이 필요한 값은 상태와 해소 Gate를 명시한다.

## 문서 네비게이션

**정본 문서 바로가기**

- [Service Plan](SERVICE_PLAN_260824_v0.2.md)
- [IA / Screen Spec](IA_SCREEN_SPEC_260824_v0.2.md)
- **Requirements Spec**
- [Decision Sheet](DECISION_SHEET_260824_v0.2.md)

**핵심 변경**: v0.2 Minimum Release는 `Departure Recommendation`과 `Leave-now Forecast`를 **서로 독립된 product command**로 구현한다. v0.1의 `Dual Analysis`/combined result/API는 `RETIRED_FROM_MR`이며, 기존 Journey Start/UserEvent/Reforecast도 retired trace로만 보존한다.

## 문서 정보와 규모

### 정의 규모

아래 수량은 이 파일의 실제 표 행을 최종 감사에서 다시 계산해 반영한다. `RETIRED_FROM_MR` 행도 historical trace 보존을 위해 정의 행 수에 포함할 수 있으나 구현 task로 세지 않는다.

| 정의 단위 | 관리 방식 | ID 범위 |
|---|---|---|
| Feature | 기존 ID 보존 + Leave-now 신규 feature | F001~F019 |
| Functional Requirement | active/retired 분리; product split 신규 계약 추가 | 기존 REQ + REQ-107~116 |
| Business Rule | active rule + product isolation 신규 rule | BR-001~096 |
| State Transition Rule | v0.1 dual IDs retire + v0.2 function transitions | ST-001~035 |
| API/System Interface | Dual API retire + separated APIs | API-000~013, SYS-001~011 |
| Canonical Entity | legacy dual entity retire + split request/result 추가 | ENT-001~033 |
| NFR | 기존 + function isolation NFR | NFR-001~100, 비연속 |
| Acceptance Scenario | existing relevant AC + split contract 신규 075~080 | AC-001~080 |
| Claim Gate | Departure/Leave-now 및 realtime/ML Gate 포함 | CG-001~010 |

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
| `RETIRED_FROM_MR` | 2026-08-23 수동 tracking 계약의 역사 추적용; 구현·release 요구 아님 |
| `FUTURE_GPS_RESEARCH` | 향후 자동 GPS tracking 연구 방향; 현재 API/state 선행 설계 금지 |
| `INTERNAL_DIAGNOSTIC` | 사용자-facing 핵심 metric이 아닌 데이터/QA 진단 |

### 승인 Gate

| Gate | 승인 기준 |
|---|---|
| G0 Service Plan | v0.2 두 독립 기능 정책 승인 |
| G1 IA | SCR-00에서 분기하는 두 독립 flow + shared Evidence 정합성 |
| G2 Requirements | F/SCR/REQ/BR/NFR/API/ENT/AC/CG 추적 누락·정책 충돌 0 |
| G3 Data Contract | identity/timestamp/residual/historical artifact/realtime feature contract 테스트 |
| G4 Product E2E | 실제 모바일 Departure flow와 Leave-now flow를 각각 독립 통과 |
| G5 Security/Share | secret/privacy/retention/share 승인 |
| G6 Release | 두 독립 기능 release-blocking AC + distributed correctness proof |

## 범위

### 포함

- 서울 임의 OD BUS+SUBWAY structural route discovery/canonicalization; Route A demo/fallback
- Service Home의 두 독립 기능 entry
- `Departure Recommendation`: future target + historical baseline → Departure P50/P90
- `Leave-now Forecast`: departAt=now + historical baseline + eligible realtime → P(on_time), Arrival P50/P90
- 두 기능의 별도 input/request/result/API/entity/route
- WALK/WAIT/RIDE/TRANSFER/FINAL_WALK shared domain boundary
- historical distribution, support/fallback/confidence/validation
- realtime feature snapshot identity/timestamp/freshness/coverage — Leave-now only
- Prediction→Actual→Residual→Historical Artifact / Realtime Feature lineage
- Leave-now realtime quantile model + baseline fallback, optional unsupervised regime
- mode-scoped Evidence, single-function Share, Mobile-first PWA
- provider/quota/security/operations/distributed correctness

### Explicit Out

- v0.1 `Dual Analysis`: 한 submit/API/result에 두 기능 metric 동시 생성
- 한 기능 result/session을 다른 기능 prerequisite로 쓰는 flow
- Journey Start, active leg lifecycle, 수동 UserEvent/Reforecast
- background/continuous GPS tracking(MR)
- targetReliability, `{p*}%` legacy Recommended Departure
- route optimizer/multi-route ranking
- 생성형/black-box AI final probability
- unverified realtime feature의 임의 weight
- citywide SLA/accuracy claim

## Feature Dictionary

| F-ID | Feature | 사용자/시스템 결과 | Primary SCR | Core REQ | Status |
|---|---|---|---|---|---|
| F001 | Service Entry / Anonymous Access | Home + owner analysis access | SCR-00/01/07 | 001~003,007,113 | MUST |
| F002 | Structural Route / Provider Gate | shared route discovery/crosswalk | 01/02/07/08/05 | 005~009,104,105 | MUST/D2 |
| F003 | Departure Time Recommendation | Departure P50/P90 | SCR-01/02 | 107~109,114,116 | MUST/CLAIM_GATE |
| F019 | Leave-now Arrival Forecast | P(on_time), Arrival P50/P90 | SCR-07/08 | 011~013,110~112,115,116 | MUST |
| F004 | Journey Start/State | old manual live lifecycle | SCR-03 | 020~021,101~102 | RETIRED_FROM_MR |
| F005 | User Event | old BOARD/BUS_SKIPPED/etc | SCR-03 | 022~024 | RETIRED_FROM_MR |
| F006 | Reforecast | old manual event reforecast | SCR-04 | 025~026 | RETIRED_FROM_MR |
| F007 | WALK/Coordinate | shared point/reference provenance | 02/08/05 | 030~032 | MUST |
| F008 | Transfer Domain | shared transfer structure/reference | 02/08/05 | 033~035 | MUST |
| F009 | Evidence/Support | analysisType-scoped evidence | 02/08/05 | 040~045 | MUST |
| F010 | Freshness/Error | historical + Leave-now realtime freshness | 01/02/07/08/05 | 050~056 | MUST |
| F011 | Prediction/Actual/Residual | shared data lineage | Data/05 | 060~067 | MUST |
| F012 | WAIT/Service Context | historical WAIT + Leave-now current context | Data/05 | 070~073 | MUST/CLAIM_GATE |
| F013 | Share Snapshot | one-function privacy-safe snapshot | 06 | 080~082 | SHOULD |
| F014 | Traceability/Internal QA | analysisType lineage, Route B QA | 05/Internal | 090~092 | MUST |
| F015 | Security/Privacy | access/retention/secret | Global | 007,080~082,100 | MUST |
| F016 | Operations/Observability | provider/quota/artifact/stream | Ops | 008~009 + NFR | MUST |
| F017 | Distributed/ML | shared data proof + Leave-now model | Internal/08/05 | 106,109~112 | MUST/CLAIM_GATE |
| F018 | Mobile-first PWA | two independent flows | Global | 093~098 | MUST |

## Functional Requirements

> Active MR contract의 최상위 불변조건: **한 request는 한 `analysisType`만 가진다.** v0.1 `Dual Analysis` ID는 history를 위해 보존하되 구현 대상으로 해석하지 않는다.

### Service Entry / Common Input / Route

| REQ | F / SCR | Priority | 상세조건·정상 처리 | 예외·오류 | Interface / Entity | BR·NFR / AC |
|---|---|---|---|---|---|---|
| REQ-113 Service Function Selection | F001/SCR-00 | MUST | Home에 `출발 시간 추천`, `도착 가능성 계산` 별도 CTA; 각기 SCR-01/07로 이동 | 통합 계산 CTA 금지 | UI / ENT-033 | BR-094~096 / AC-075 |
| REQ-001 출발지 입력 | F001/SCR-01/07 | MUST | 장소/주소 또는 explicit one-shot 현재 위치를 GeoPoint로 resolve | unresolved/geography 구분 | API-000,011,012 / ENT-016,029,030 | BR-001,070 / AC-001,076,077 |
| REQ-002 목적지 입력 | F001/SCR-01/07 | MUST | POI/coordinate provenance 저장, final boundary FINAL_WALK | same/unresolved/outside | API-000,011,012 / ENT-016,029,030 | BR-001 / AC-001 |
| REQ-003 목표 도착시각 | F001/SCR-01/07 | MUST | future timezone-aware; function별 supported horizonVersion 적용 | past/naive/out-of-horizon | API-011,012 / ENT-029,030 | BR-010 / AC-001 |
| REQ-004 목표 reliability | F001 | RETIRED_FROM_MR | 2026-08-23 legacy p* trace | active UI/API 사용 금지 | N/A | AC-067 |
| REQ-005 Structural Route 조회·선택 | F002/01/02/07/08 | MUST | 각 function request에서 first canonical+historical supported candidate; internal cache 재사용 가능 | mapping/provider/manifest 오류 | API-001,011,012; SYS-002 / ENT-005 | BR-001~005,071,096 / AC-004,078 |
| REQ-006 Route normalization | F002/02/08/05 | MUST | WALK/WAIT/RIDE/TRANSFER/FINAL_WALK | silent deletion 금지 | SYS-002 / ENT-005~009,017,018 | BR-030~032 / AC-017 |
| REQ-007 Anonymous Analysis Access | F001/F015 | MUST | analysisId별 browser-bound owner capability; type immutable | capability mismatch enumeration-safe | API-011~013,006,007 / ENT-020,033 | BR-004 / AC-035,079 |
| REQ-008 Provider Registry/Coverage | F002/F016 | MUST | coverage/route/walk/historical/realtime 축 분리; realtimeContextCoverage는 Leave-now only | provenance 혼합 금지 | API-001,011,012,006,009 | BR-005 / AC-057 |
| REQ-009 Kakao Route Provider Gate | F002/F016 | D2_TARGET/CLAIM_GATE | 2026-08-23 evidence status 보존; external crosswalk 필요 | HTTP 200 승격 금지 | SYS-002/007 | BR-071~074 / AC-053~055 |
| REQ-100 Location Provider Contract | F001/F016 | MUST | location provider와 route provider quota/cache/provenance 분리 | URL/log exact location 노출 금지 | API-000,SYS-001 | NFR-090~094 / AC-046 |
| REQ-104 Arbitrary OD Discovery | F002 | MUST | 서울 임의 OD discovery + crosswalk; 각 function에서 독립 eligibility | mapping/model 미달 structure-only | API-001,011,012 | BR-083~085 / AC-061,062 |
| REQ-105 Canonicalization Crosswalk | F002 | D2_TARGET/CLAIM_GATE | name+coordinate+line/route+direction/order+unique candidate | unsafe matching 승격 금지 | SYS-002 / ENT-005 | BR-085 / AC-062 |

### v0.1 Dual Analysis — Retired trace

| REQ | Status | v0.2 처리 |
|---|---|---|
| REQ-010 Dual Analysis Snapshot | RETIRED_FROM_MR | 한 selected route/target에서 두 기능 result를 동시에 생성하던 v0.1 contract. API-002/ENT-011/015와 함께 active 사용 금지 |
| REQ-015 Legacy Recommended Departure | RETIRED_FROM_MR | `{p*}%` single metric trace |
| REQ-017 Start Eligibility | RETIRED_FROM_MR | live Start gate trace |

### Departure Time Recommendation

| REQ | F / SCR | Priority | 상세조건·정상 처리 | 예외·오류 | Interface / Entity | BR·NFR / AC |
|---|---|---|---|---|---|---|
| REQ-114 Departure Recommendation Analysis | F003/SCR-01→02 | MUST | 별도 planning request/result; future target + selected route + historical artifact. response는 Departure metric만 | realtime 호출/Arrival metric contamination 금지 | API-011,SYS-010 / ENT-029,031,033 | BR-020~024,089,094~096; NFR-100 / AC-076,078 |
| REQ-107 Departure P50 | F003/SCR-02/06 | MUST/CLAIM_GATE | historical baseline만, on-time threshold .50 latest candidate | realtime/simple mean subtraction 금지 | SYS-010 / ENT-031,027 | BR-020~024,089 / AC-068,070; CG-004 |
| REQ-108 Departure P90 | F003/SCR-02/06 | MUST/CLAIM_GATE | historical baseline만, threshold .90 latest candidate | P90 leg 단순합 금지 | SYS-010 / ENT-031,027 | BR-020~024,089 / AC-068,070; CG-004 |
| REQ-109 Historical Reliability Artifact | F003/F011/F012/F019 | MUST/CLAIM_GATE | day/time/route/node/service WAIT/RIDE distributions + support/fallback/version/window | poll row iid 금지 | SYS-005/006 / ENT-027 | BR-089 / AC-071; CG-002~005 |

### Leave-now Arrival Forecast

| REQ | F / SCR | Priority | 상세조건·정상 처리 | 예외·오류 | Interface / Entity | BR·NFR / AC |
|---|---|---|---|---|---|---|
| REQ-115 Leave-now Forecast Analysis | F019/SCR-07→08 | MUST | 별도 request/result; server calculatedAt으로 departAt≈now 고정. response는 Arrival/P(on_time) metric만 | Departure metric contamination, client arbitrary departAt 금지 | API-012,SYS-011 / ENT-030,032,033 | BR-090~096; NFR-098,100 / AC-077,078 |
| REQ-011 Arrival P50 | F019/SCR-08/06 | MUST | final-arrival Q0.50 | 평균 동일시 금지 | SYS-011 / ENT-032 | BR-010,090 / AC-069 |
| REQ-012 Arrival P90 | F019/SCR-08/06 | MUST | final-arrival Q0.90 | 90% accuracy 금지 | SYS-011 / ENT-032 | BR-010,063,090 / AC-069 |
| REQ-013 On-time Probability | F019/SCR-08/06 | MUST | P(finalArrival≤target given depart=now,current context) | null≠0, calibration 과장 금지 | SYS-011 / ENT-032 | BR-010,090 / AC-069 |
| REQ-110 Realtime Feature Snapshot | F019/F017 | MUST for realtime context | observable-before/at calculatedAt, identity/freshness/coverage immutable snapshot | leakage/stale/unmatched 사용 금지 | SYS-009 / ENT-028 | BR-090,091 / AC-072; CG-009 |
| REQ-111 Realtime Context Application | F019/F017 | MUST | verified feature만 leg distribution에 추가; FULL/PARTIAL/NONE + historical-only fallback | fabricated realtime 금지 | SYS-008/009/011 / ENT-028,032 | BR-090~093 / AC-069,072 |
| REQ-112 Optional Traffic Regime | F017/Internal | COULD/CLAIM_GATE | unsupervised regime은 supervised outcome model feature로만 | direct seconds/weight/final probability 금지 | SYS-006/008 / ENT-025,026,028 | BR-092,093 / AC-074; CG-010 |

### Shared Result / Function Isolation

| REQ | F / SCR | Priority | 상세조건·정상 처리 | 예외·오류 | Interface / Entity | BR·NFR / AC |
|---|---|---|---|---|---|---|
| REQ-016 Result Eligibility | F003/F019/02/08/05 | MUST | result type별 USER_FACING/ENGINE_FIXTURE_ONLY/NOT_COMPUTED | fabricated number 금지 | API-011~013 / ENT-031~033 | BR-013~017 / AC-003 |
| REQ-103 Per-metric Claim Eligibility | F003/F019 | MUST | Departure two metrics와 Leave-now three metrics를 각 result entity 내부에서 판정 | 다른 function grade 전이 금지 | API-011,012 / ENT-031,032 | BR-082 / AC-073 |
| REQ-116 Function Isolation | F003/F019/Global | MUST | 두 기능은 독립 entry/input/API/result; 다른 기능 request/result prerequisite 없음; Evidence/Share도 single type | combined response, automatic continuation, cross-type route coercion 금지 | API-011~013,006~008 / ENT-029~033 | BR-094~096; NFR-100 / AC-075~080 |

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
| REQ-051 Stale Realtime | F010/02/08/05 | MUST | stale realtime feature는 B current input에서 제외 | stale를 live/current로 사용 금지 | API-011/012/006 | BR-061,090 / AC-028,072 |
| REQ-052 Provider Error | F010/01/07/07/08/05 | MUST | transport/business/quota 분리 | raw body/key 노출 금지 | API-000/001/011/012/006 | NFR-030,060 / AC-029 |
| REQ-053 Partial Data | F010/02/08/05 | MUST | historical partial와 realtime partial 원인을 분리 | critical historical missing을 partial로 과승격 금지 | API-011/012/006 | BR-012~014 / AC-027,072 |
| REQ-054 Unsupported | F010/01/07 | MUST | geography/mode/mapping 범위 밖 explicit | 0% 대체 금지 | API-001/002 | BR-001,060 / AC-002 |
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
| REQ-080 Share Snapshot | F013/06 | SHOULD | parent analysisType의 eligible metric만 immutable snapshot | exact origin/raw ID/다른 기능 metric 제외 | API-007/008 / ENT-019,020,033 | NFR-050~053 / AC-025,080 |
| REQ-081 Share Expiry | F013/06 | SHOULD | opaque token+expiry/revoke | TTL hard-code 금지 | API-007/008 | NFR-051~054 / AC-025 |
| REQ-082 Share Authorization Boundary | F013/F015 | SHOULD/G5 | snapshot read only; owner result/evidence 권한으로 승격 불가 | token reuse/escalation 금지 | API-007/008 | BR-004 / AC-039 |
| REQ-090 Result Traceability | F014/05/Demo | MUST | result→run→historical distribution/realtime snapshot/model/route/source/version | missing provenance final demo 금지 | API-006 / ENT-001~028 | BR-050,062 / AC-034 |
| REQ-091 No Mock Final Result | F014/02/08/Demo | MUST | 각 기능 final result는 해당 real pipeline output | hard-coded/combined mock 금지 | SYS-010/011/006 | BR-053,062 / AC-034 |
| REQ-092 Route B Internal QA Isolation | F014/Internal | MUST | topology/realtime identity/data pipeline QA only | BUS_SKIPPED/manual tracking QA/public UI 노출 금지 | SYS-002/004~006 | BR-065 / AC-040 |

### Mobile-first PWA Runtime

| REQ | F / SCR | Priority | 상세조건·정상 처리 | 예외·오류 | Interface / Entity | BR·NFR / AC |
|---|---|---|---|---|---|---|
| REQ-093 Mobile Web/PWA Parity | F018/00/01/02/07/08/05 | MUST | browser/standalone에서 두 독립 flow의 semantics/guard/error 동일 | install 여부로 claim 차등 금지 | API-000/001/006/011~013 | NFR-070,074 / AC-041,042 |
| REQ-094 Manifest/Installability | F018/Runtime | MUST | HTTPS/manifest/icon/start URL/standalone | prompt 거부는 오류 아님 | SYS-001 | NFR-075 / AC-042 |
| REQ-095 Offline Snapshot | F018/02/08/05 | MUST | privacy-safe immutable typed analysis projection read-only | offline 새 분석/Share success queue 금지; Leave-now current 표현 금지 | API-013/006 / ENT-021 | BR-067 / AC-043 |
| REQ-096 Foreground Recovery | F018/02/08/05 | MUST | 저장된 typed result snapshot refetch; 자동 Leave-now recompute 없음 | local stale result를 new now 또는 다른 analysisType으로 승격 금지 | API-013 / ENT-021,031,032,033 | BR-068 / AC-044 |
| REQ-097 Service Worker Update | F018/Runtime | MUST | safe activation, cache/runtime version 관측 | 구 schema result resurrection/reload loop 금지 | SYS-001 | BR-069 / AC-045 |
| REQ-098 Device Capability | F018/01/07 | MUST | origin one-shot geolocation, Share fallback | page-load/continuous/background GPS prompt 금지 | API-000/007 | BR-070 / AC-046,047 |

### AI / ML Training and Serving

| REQ | F / SCR | Priority | 상세조건·정상 처리 | 예외·오류 | Interface / Entity | BR·NFR / AC |
|---|---|---|---|---|---|---|
| REQ-106 JR Realtime Quantile Model Serving | F017/F019/08/05 | D2_TARGET/CLAIM_GATE | canonical model key `JR_REALTIME_QUANTILE_MODEL`; H100/Jupyter training-only; artifact+feature schema+eval+hash를 runtime 반입. B leg residual/WAIT quantile 반환 | baseline uplift/latency/calibration/artifact Gate 미달 시 B1/B0 fallback; final P(on_time) 직접 생성 금지 | SYS-003/006/008 / ENT-025,026,028 | BR-087,088,093; NFR-095,096,099 / AC-065,066,074; CG-008,010 |

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
| BR-010 | Departure P50/P90, Arrival P50/P90, P(on_time)은 서로 다른 metric이다. P50은 평균이 아니다. |
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
| BR-082 | metric eligibility는 departureP50At/departureP90At/arrivalP50At/arrivalP90At/onTimeProbability별 독립이다. |
| BR-083 | route discovery coverage와 WALK provider coverage, historical model coverage, realtime context coverage는 서로 다른 축이다. |
| BR-084 | canonical mapping 또는 historical model coverage가 부족한 candidate는 현재 요청한 기능을 `NOT_COMPUTED`로 둔다. realtime context만 부족한 경우 Leave-now는 historical-only로 축소할 수 있다. |
| BR-085 | canonicalization crosswalk는 임의 OD의 Departure Recommendation과 Leave-now Forecast 모두에 필요한 route Gate다. name-only/거리-only/다중 후보는 EXACT/UNAMBIGUOUS로 승격하지 않는다. |
| BR-086 | API 호출, 화면 표시, cache, raw/derived retention, Share/재배포 권한은 서로 다른 Gate이며 하나의 승인으로 다른 권한을 추론하지 않는다. |
| BR-087 | H100/Jupyter는 training plane이며 production direct call 금지. |
| BR-088 | AI/ML은 B leg residual/WAIT distribution source이며 final probability/route/evidence를 대체하지 않는다. |
| BR-089 | A historical artifact는 realtime/current vehicle/train feature를 사용하지 않는다. |
| BR-090 | B realtime feature는 `calculatedAt` 이전/동시에 observable하고 source timestamp가 유효해야 한다. |
| BR-091 | leading vehicle/congestion/headway feature는 identity·ordering·timestamp·coverage가 검증된 경우만 사용한다. |
| BR-092 | unsupervised cluster/regime을 delay seconds, 영향 weight, final probability로 직접 해석하지 않는다. |
| BR-093 | B realtime/AI model은 historical baseline 대비 hold-out value-add가 없으면 fallback하고 관련 claim을 하지 않는다. |


### Product Function Isolation

| BR | Rule |
|---|---|
| BR-094 | Departure Recommendation과 Leave-now Forecast는 별도 entry/input/submit/API/result를 가진다. combined Dual Analysis active contract를 금지한다. |
| BR-095 | 어느 기능도 다른 기능의 analysisId/result/session을 prerequisite로 요구하거나 자동 continuation하지 않는다. |
| BR-096 | route/cache/historical artifact/simulation library의 내부 재사용은 허용하지만 shared infrastructure를 shared product request/result로 노출하지 않는다. |

## State Transition Rules

### State enums

| Domain | Values | MR 여부 |
|---|---|---|
| AnalysisType | DEPARTURE_RECOMMENDATION / LEAVE_NOW_FORECAST | ACTIVE, immutable |
| Analysis | IDLE / ANALYZING / SUCCEEDED / FAILED | ACTIVE |
| Realtime Context Coverage | FULL / PARTIAL / NONE | Leave-now only |
| Freshness | FRESH / AGING / STALE / PROVIDER_ERROR / NO_DATA | ACTIVE |
| Result Eligibility | USER_FACING / ENGINE_FIXTURE_ONLY / NOT_COMPUTED | ACTIVE |
| Validation Scope | UNVALIDATED / COMPONENT_ONLY / CORRIDOR_REPLAY / END_TO_END | ACTIVE |
| PWA Runtime | ONLINE / OFFLINE_SNAPSHOT / UPDATE_AVAILABLE | ACTIVE |
| Journey Lifecycle / Reforecast / Leg progress | legacy | RETIRED_FROM_MR |

### v0.2 Active transitions

| ST | Current | Event | Next | Invariant | REQ / AC |
|---|---|---|---|---|---|
| ST-030 | HOME | SELECT_DEPARTURE | Departure Input | 다른 기능 계산 0 | 113 / AC-075 |
| ST-031 | HOME | SELECT_LEAVE_NOW | Leave-now Input | 다른 기능 계산 0 | 113 / AC-075 |
| ST-032 | Departure.IDLE | SUBMIT_DEPARTURE | Departure.ANALYZING | type fixed, API-011 only | 114 / AC-076,078 |
| ST-033 | LeaveNow.IDLE | SUBMIT_LEAVE_NOW | LeaveNow.ANALYZING | type fixed, departAt server now, API-012 only | 115 / AC-077,078 |
| ST-034 | *.ANALYZING | ANALYSIS_SUCCESS | sameType.SUCCEEDED | result entity type 동일; cross metric 0 | 114~116 / AC-078 |
| ST-035 | *.ANALYZING | ANALYSIS_FAILED | sameType.FAILED | input preserved, no cross fallback | 050~056,116 / AC-079 |
| ST-014~017 | source freshness | AGE/STALE/FAIL/RECOVER | freshness update | realtime coverage는 Leave-now만 | 050~056 / AC-072 |
| ST-019 | ONLINE result | NETWORK_UNAVAILABLE | OFFLINE_SNAPSHOT | same analysisType read-only | 095 / AC-043,080 |
| ST-020 | OFFLINE/ONLINE | RESULT_REFETCH | ONLINE | same immutable analysis; auto cross-function/new now 없음 | 096 / AC-044 |
| ST-022 | ANY PWA | WORKER_WAITING | UPDATE_AVAILABLE/defer | safe schema activation | 097 / AC-045 |

### Retired IDs

- ST-001~003: v0.1 Dual Analysis execution trace, `RETIRED_FROM_MR`.
- ST-004~013, ST-018, ST-021, ST-023~029 중 manual Start/Event/Reforecast 의미: `RETIRED_FROM_MR`.
- 번호를 새 의미로 재사용하지 않는다.

## Error Taxonomy

| Code | Layer | User handling | Must preserve |
|---|---|---|---|
| INPUT_INVALID / TARGET_BEYOND_SUPPORTED_HORIZON | Client | 입력 수정 | input |
| LOCATION_NOT_RESOLVED / UNSUPPORTED_GEOGRAPHY | Provider/Product | 입력 수정 | input |
| ROUTE_NOT_FOUND / ROUTE_PROVIDER_ERROR | Route | retry/edit | input/provenance |
| ROUTE_MAPPING_PARTIAL/FAILED | Mapping | 현재 function structure-only + NOT_COMPUTED | route structure |
| HISTORICAL_BASELINE_UNAVAILABLE | Data | 현재 function unavailable | route/evidence |
| REALTIME_CONTEXT_PARTIAL | Data | B partial realtime | used/missing categories |
| REALTIME_CONTEXT_UNAVAILABLE | Data | historical-only B if allowed | historical artifact |
| STALE_DATA | Data | stale feature 제외/refresh | last success |
| PROVIDER_ERROR / QUOTA | Provider/Ops | bounded retry/degrade | quota/provenance |
| ANALYSIS_TYPE_MISMATCH | Contract | expected type route로 coercion 금지 | analysisType/resource |
| ANALYSIS_FAILED | Engine | retry | request/provenance |
| MODEL_FALLBACK | ML | baseline 사용, claim 축소 | model/fallback trace |
| SHARE_EXPIRED / SHARE_NOT_FOUND | Share | public variant | no private payload |
| NETWORK_UNAVAILABLE | PWA | offline snapshot | savedAt |
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
| API-006 | GET `/api/v1/analyses/{analysisId}/evidence` | mode-scoped evidence | owner+analysisId | parent analysisType의 evidence만 | ACTIVE |
| API-007 | POST `/api/v1/analyses/{analysisId}/share` | single-function share | owner+analysisId | token/url/expiry | SHOULD |
| API-008 | GET `/api/v1/share/{token}` | public share | token | one analysisType snapshot | SHOULD |
| API-009 | GET `/api/v1/health/summary` | internal preflight | internal auth | provider/quota/artifact/realtime/model/distributed | ACTIVE |
| API-010 | legacy `/abort` | manual live abort | — | — | RETIRED_FROM_MR |
| API-011 | POST `/api/v1/departure-recommendations` | Departure Recommendation | origin,destination,targetArrivalAt | analysisId + Departure P50/P90 + historical evidence summary | ACTIVE |
| API-012 | POST `/api/v1/leave-now-forecasts` | Leave-now Forecast | origin,destination,targetArrivalAt | analysisId + departAt + P(on_time)+Arrival P50/P90 + realtime coverage | ACTIVE |
| API-013 | GET `/api/v1/analyses/{analysisId}` | immutable result recovery | owner+analysisId | exactly one typed result envelope | ACTIVE |

#### API isolation rules

- API-011 response schema에 Arrival/P(on_time)/realtime fields가 존재하면 contract failure다.
- API-012 response schema에 Departure P50/P90가 존재하면 contract failure다.
- API-011을 호출한 뒤 API-012를 자동 호출하지 않으며 반대도 동일하다.
- API-013은 stored `analysisType`을 다른 type으로 변환하지 않는다.

### Internal interfaces

| ID | Interface | Input→Output | Contract |
|---|---|---|---|
| SYS-001 | Location/WALK Adapter | query/points→GeoPoint/WALK point | provenance/quota/error |
| SYS-002 | Route Registry/Normalizer | provider candidate→RouteCandidate/Leg | shared crosswalk/time semantics |
| SYS-003 | Shared Reliability Math Library | leg distributions + simulation config→samples/metrics primitives | user product result 직접 생성하지 않음 |
| SYS-004 | Collector | external API→Observation | timestamps/quota/raw policy |
| SYS-005 | Actual/Residual Builder | observations→Actual/Residual | identity/interval/sign |
| SYS-006 | Artifact/Validation Pipeline | Gold→historical artifact/model/eval | provenance/hold-out |
| SYS-007 | Quota Coordinator | reservation→permit/degradation | shared budget/no bypass |
| SYS-008 | AI Artifact/Inference Adapter | model+features→leg quantiles | Leave-now only, fallback |
| SYS-009 | Realtime Feature Builder | current obs→RealtimeFeatureSnapshot | Leave-now only, causality Gate |
| SYS-010 | Departure Recommendation Engine | route+historical artifact+target→DepartureRecommendationResult | realtime input interface 자체 없음 |
| SYS-011 | Leave-now Forecast Engine | route+historical+optional realtime+now→LeaveNowForecastResult | Departure metric 생성 금지 |
### 기준 기술과 배포 경계

기존 Next.js/Java21+Spring/Kafka/Flink/PostgreSQL/MinIO/Python-Spark/Docker/Nginx/EC22 구조를 유지한다. Operational PostgreSQL은 typed analysis record/result/access/share/quota를 SoT로 둔다. 2-node proof는 HA가 아니라 worker correctness/recovery proof다.

#### 2-node provisional deployment contract

기존 물리 배치 가설을 유지하되 보호 workload는 API-011/API-012, shared data pipeline, SYS-010/SYS-011, Historical Artifact, Realtime Feature pipeline이다. manual live state/event service는 배치 대상이 아니다.

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
| ENT-019 | ShareSnapshot | analysisType,tokenDigest,status,expiresAt,payload | 다른 type metric 포함 금지 |
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
| ENT-030 | LeaveNowForecastRequest | origin,destination,targetArrivalAt,requestedAt | departAt client override 없음 |
| ENT-031 | DepartureRecommendationResult | analysisId,target,departureP50At,departureP90At,historicalCoverage,eligibility,calculatedAt,limitations | Arrival/realtime metric 없음 |
| ENT-032 | LeaveNowForecastResult | analysisId,target,departAt,arrivalP50At,arrivalP90At,onTimeProbability,historicalCoverage,realtimeCoverage,eligibility,calculatedAt,limitations | Departure metric 없음 |
| ENT-033 | AnalysisRecord | analysisId,analysisType,routeCandidateId,status,createdAt,calculatedAt,resultRef | analysisType immutable; exactly one request/result type |

### Identity rules

기존 Bus/Subway/mixed crosswalk identity 규칙을 유지한다. leading vehicle feature는 route/direction/order/time 검증이 필요하다.

### Data Quality minimum flags

기존 flags에 `ANALYSIS_TYPE_MISMATCH`, `CROSS_FUNCTION_METRIC_CONTAMINATION`, `REALTIME_FEATURE_STALE`, `LEADING_VEHICLE_UNVERIFIED`, `HEADWAY_UNVERIFIED`, `CONGESTION_UNVERIFIED`, `FEATURE_LEAKAGE_RISK`, `HISTORICAL_BUCKET_LOW_SUPPORT`를 추가한다.

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
| NFR-051 Share Privacy | SHOULD/G5 | exact origin/GPS/raw ID/debug 제외, opaque token | AC-025 |
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

2026-08-23 source별 approved limit/status와 Subway `PENDING_RECONCILIATION`은 `DECISION_SHEET_260824_v0.2.md`의 historical evidence를 정본으로 사용한다. 숫자를 이 문서에서 다시 추정하지 않는다. realtime feature 수집도 동일 SYS-007 ledger에 포함한다.

#### Public API Admission Control

| NFR | Priority | Requirement | Measurement / Gate |
|---|---|---|---|
| NFR-090 Client/Session Admission Control | MUST | `/locations/search`,`/route-candidates`,`/departure-recommendations`,`/leave-now-forecasts` 호출 빈도 제한; threshold TBD | rate-limit test |
| NFR-091 Request Dedup/Coalescing | MUST | 동일 정규화 input(origin,destination,targetArrivalAt)의 동시 요청은 in-flight coalescing; route/historical artifact 승인 cache 사용 | duplicate call ratio |
| NFR-092 Concurrency Cap | MUST | provider별 concurrency cap/circuit breaker; quota-exhaustion과 retry 가능 시점 표현 | concurrency injection |

### Responsive / Accessibility

| NFR | Priority | Requirement | Acceptance |
|---|---|---|---|
| NFR-070 Responsive | MUST | Departure flow와 Leave-now flow 각각 mobile/tablet/desktop에서 핵심 정보 삭제 금지 | viewport E2E |
| NFR-071 Non-color State | MUST | historical-only/partial/stale/error를 text/icon/copy로 전달 | visual/a11y |
| NFR-072 Keyboard/Focus | MUST | form/CTA/evidence/share keyboard, focus restore/live region | manual+automated |
| NFR-073 Reduced Motion/Reflow | MUST | zoom/reflow/reduced motion, probability animation 과장 금지 | manual |
| NFR-074 Mobile Browser Parity | MUST | iOS/Android browser와 standalone에서 두 독립 flow의 의미·guard·copy 동등 | real-device E2E |
| NFR-075 Installability | MUST | manifest/icon/start URL/display/HTTPS | install audit |
| NFR-076 Offline Privacy/Honesty | MUST | shell/static + privacy-safe snapshot만 offline; B를 current/live로 표현 금지 | cache/storage inspection |
| NFR-077 Foreground Recovery | MUST | 저장된 result refetch; 자동 now recompute 없음 | lifecycle/network test |
| NFR-078 Update Safety | MUST | worker/cache/app version 관측, 구 schema snapshot resurrection 방지 | update/rollback matrix |
| NFR-079 Device Permission/Share | MUST | origin one-shot geolocation; background/continuous GPS MR prompt 0; share fallback | real-device test |

### Distributed Proof

| NFR | Priority | Requirement | Acceptance |
|---|---|---|---|
| NFR-080 Real vs Amplified | MUST for proof | replay multiplier/purpose 표시, amplified는 training support 금지 | run manifest |
| NFR-081 Worker Participation/Failure | MUST | Kafka partition input을 2개 이상 worker task가 처리하고 worker 종료 후 checkpoint/restart 또는 replay 복구 | participation/recovery evidence |
| NFR-082 Correctness | MUST | single vs multi-worker input/output count·checksum, duplicate/loss 0, keyed identity state consistency | correctness manifest |
| NFR-083 Two-node Deployment | MUST/G6 | EC2-A serving, EC2-B processing 기본; resource 부족 시 worker-level proof로 scope 축소 가능, 물리 2-node claim 조건 분리 | deployment manifest |
| NFR-084 Quota Budget | MUST/G3 | source approved status/reservation/forecast/degradation이 ENT-023에 존재 | quota manifest |
| NFR-085 PWA Compatibility Matrix | MUST/G4 | iOS/Android browser/standalone + desktop secondary run version 기록 | AC-050 |
| NFR-086 Route A Demo/Protected E2E | MUST/G6 | `SCR-00→01→02→05`와 `SCR-00→07→08→05`를 각각 실제 product flow로 시연; Route B/mock replacement 금지 | AC-051,052,075~080 |
| NFR-087 Kakao WALK / Route Provider Contract | MUST for WALK,D2 target route | WALK point provider와 publictraffic discovery/crosswalk Gate 분리; 2026-08-23 판정 보존 | AC-053~056 |
| NFR-088 Provider Provenance/Cache | MUST | provider/endpoint/adapter/crosswalk/version/hash 보존; cross-provider silent cache 대체 금지 | provider contract tests |

### AI / ML Serving Boundary

| NFR | Priority | Requirement | Acceptance |
|---|---|---|---|
| NFR-095 Training/Serving Plane Separation | MUST/CLAIM_GATE | H100/Jupyter/Notebook은 offline training/eval 전용; runtime은 versioned artifact만 사용 | AC-065 |
| NFR-096 Inference Latency/Fallback | D2_TARGET/CLAIM_GATE | JR_REALTIME_QUANTILE_MODEL bounded inference; 실패/미달 시 B1→B0 fallback | AC-066 |
| NFR-099 Model Incremental Value | CLAIM_GATE | realtime/unsupervised feature model은 same temporal hold-out에서 baseline value-add 통과 전 claim 금지 | AC-074 |


## Acceptance Test Scenarios

### v0.2 Product Split Scenarios

| AC | Scenario | Expected | Related |
|---|---|---|---|
| AC-075 | Service Home | 두 독립 CTA, combined calculate CTA 0 | REQ-113,BR-094 |
| AC-076 | Departure independent flow | fresh session Home→SCR-01→API-011→SCR-02; Leave-now 선행/후행 호출 0 | REQ-114,NFR-100 |
| AC-077 | Leave-now independent flow | fresh session Home→SCR-07→API-012→SCR-08; Departure result 필요 0 | REQ-115,NFR-100 |
| AC-078 | API/schema isolation | API-011에 Arrival/realtime fields 0; API-012에 Departure fields 0; distinct analysisId | REQ-114~116 |
| AC-079 | analysisType route guard | wrong result route/API read가 type coercion하지 않음 | REQ-007,116 |
| AC-080 | Evidence/Share isolation | parent analysisType의 metric/evidence만 포함 | REQ-045,080,116 |

### Active / Updated Core Scenarios

| AC | Scenario | Expected | Related |
|---|---|---|---|
| AC-001 | valid common input | 각 function form에서 resolve/target validation 성공 | REQ-001~003 |
| AC-002 | unsupported/mapping fail | 0% 대신 explicit error/structure-only | REQ-005,054 |
| AC-003 | critical historical missing | 현재 function NOT_COMPUTED; 다른 function fake result 생성 0 | REQ-016,055 |
| AC-004 | route selection | provider order first supported, reliability reorder 0 | REQ-005,006 |
| AC-016~023 | WALK/Transfer/Evidence/WAIT | 기존 semantics/support/fallback 계약 유지 | REQ-030~073 |
| AC-025 | Share privacy | exact origin/raw ID/other function metric 0 | REQ-080~082 |
| AC-026~033 | Data/Residual | timestamp/identity/residual/leakage 계약 유지 | REQ-060~067 |
| AC-034 | Final trace | 각 기능 result가 real pipeline/provenance로 trace | REQ-090,091 |
| AC-035 | Anonymous auth | analysisId별 enumeration-safe owner guard | REQ-007 |
| AC-041~050 | PWA/Ops/Deployment | 두 기능 각각 mobile/offline/update/permission, infra proof | REQ-093~098,NFR |
| AC-053~057 | Kakao evidence | 기존 2026-08-23 판정 보존 | REQ-008,009,104,105 |
| AC-061~063 | Arbitrary OD/policy | 각 function 독립 eligibility, provider/default-deny | REQ-104,105 |
| AC-065~066 | AI isolation/fallback | Leave-now only model, runtime training direct call 0 | REQ-106 |
| AC-067 | Legacy contract audit | targetReliability, legacy Recommended, API-002 Dual, manual tracking active 0 | retired set |
| AC-068 | Departure math | .50/.90 threshold, realtime input 0, simple subtraction 0 | REQ-107,108 |
| AC-069 | Leave-now math | departAt=now, P(on_time), Arrival P50/P90, realtime coverage | REQ-011~013,111 |
| AC-070~074 | Hold-out/artifact/realtime/model | 기존 신규 Gate semantics 유지 | REQ-106~112 |

### Retired Scenarios

- 2026-08-23 manual Start/Event/Reforecast AC IDs는 `RETIRED_FROM_MR`.
- v0.1 Dual Analysis UI/API behavior도 `RETIRED_FROM_MR`; AC-075~080이 v0.2 product isolation canonical tests다.

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

### Evidence guardrails

기존 2026-08-23 Bus/Subway/WAIT/Kakao evidence 제한을 유지한다. 추가 guardrail:

- `congetion` 존재 가능성은 leading vehicle congestion availability/effect 증거가 아니다.
- vehicle 순서/거리/headway는 identity와 timestamp가 검증되기 전 feature로 사용하지 않는다.
- unsupervised cluster는 actual delay label을 설명하거나 weight를 정한 증거가 아니다.
- B realtime model claim은 historical-only baseline보다 같은 hold-out에서 개선돼야 한다.

## End-to-End Traceability Matrix

| F | SCR | Active REQ | API/SYS | ENT | AC/CG |
|---|---|---|---|---|---|
| F001 | 00/01/07 | 001~003,007,100,113 | API-000,011~013 | 016,020,029,030,033 | AC-001,035,046,075 |
| F002 | 01/02/07/08/05 | 005~009,104,105 | API-001,011,012,006,009; SYS-002,007 | 005,017,018,033 | AC-004,053~057,061,062 |
| F003 | 01/02/05/06 | 107~109,114,116 | API-011,013,006,007; SYS-003,010 | 027,029,031,033 | AC-068,070,071,076,078~080; CG-004 |
| F019 | 07/08/05/06 | 011~013,110~112,115,116 | API-012,013,006,007; SYS-003,008,009,011 | 028,030,032,033 | AC-069,072,074,077~080; CG-008~010 |
| F004~006 | 03/04 | retired | retired | 012,013 | retired |
| F007~008 | 02/08/05 | 030~035 | SYS-001~003 | 006~010,016,017 | AC-016,017,027 |
| F009 | 02/08/05 | 040~045,116 | API-006,011~013 | 010,027~033 | AC-018~021,080 |
| F010 | 01/02/07/08/05 | 050~056 | API-011~013,006; SYS-004,009 | 001,027,028,031~033 | AC-028,029,072 |
| F011~012 | Data/05 | 060~073,109~111 | SYS-003~006,009~011 | 001~010,027,028 | AC-019,023,026,030~033,071,072; CG-002~005,009 |
| F013 | 06 | 080~082,116 | API-007,008 | 019,020,033 | AC-025,080 |
| F014 | 05/Internal | 090~092 | API-006,SYS-002~006 | shared entities | AC-034,040 |
| F015~016 | Global/Ops | security/provider NFR | active APIs | 020,023,024,033 | AC-029,035,048,049,063 |
| F017 | 08/05/Internal | 106,110~112 | SYS-006,008,009,011 | 025,026,028,032 | AC-065,066,072,074; CG-008~010 |
| F018 | 00/01/02/07/08/05/06 | 093~098,113~116 | API-000,006~013 | 019~022,029~033 | AC-041~047,075~080 |

### Traceability completeness rules

- 모든 active MUST/CLAIM_GATE REQ는 AC 또는 CG를 가진다.
- API-002/ENT-011/ENT-015 v0.1 Dual contract는 active SCR/F에 연결하지 않는다.
- Departure와 Leave-now result schema는 서로의 metric ID를 참조하지 않는다.
- Product split 변경은 Service/IA/Requirements/Decision v0.2에서 동시에 반영한다.
- 새로운 factual claim은 Decision/Evidence 없이 추가하지 않는다.

## Development-only Decisions / TBD Register

| Item | Status | Resolution artifact | Safe behavior |
|---|---|---|---|
| provider stale thresholds | TBD_AFTER_PROFILE | latency profile/ADR | stale feature current 사용 금지 |
| support thresholds | CLAIM_GATE | SUPPORT_RULE_V1 | INSUFFICIENT |
| function별 latency SLO | TBD_AFTER_PROFILE | 두 vertical slice benchmark | fake progress/number 금지 |
| partition/watermark/state/checkpoint | TBD_AFTER_PROFILE | stream ADR | arbitrary scaling claim 금지 |
| historical bucket granularity | NEW/TBD | multi-window profile | broader pooling은 fallback 표시 |
| Departure candidate grid/coarse-to-fine | CG-004 | benchmark/eval | simple subtraction 금지 |
| leading vehicle identity | UNVERIFIED | feature feasibility experiment | feature 미사용 |
| current/leading congestion availability | UNVERIFIED | raw schema+coverage experiment | feature 미사용 |
| headway/distance feature | UNVERIFIED | route/order/timestamp validation | feature 미사용 |
| realtime feature freshness threshold | TBD_AFTER_PROFILE | feature latency profile | stale 제외 |
| JR_REALTIME_QUANTILE_MODEL | PENDING | CG-008/010 | B1/B0 fallback |
| unsupervised traffic regime | OPTIONAL | U1 eval | 일반 result에 영향 claim 금지 |
| Future GPS Tracking | FUTURE_GPS_RESEARCH | 별도 privacy/accuracy/battery research | MR route/API/state 없음 |
| Share/owner TTL, analytics retention | G5 | security/privacy decision | 최소화/default deny |
| Kakao crosswalk/provider policy | 기존 2026-08-23 상태 유지 | REQ-105/registry | unsupported/structure-only/default-deny |

## Security / Operations Release Checklist

- [ ] repo/frontend/log secret critical 0, HTTPS/CORS/access guard 검증.
- [ ] exact coordinate/token/raw IDs가 analytics/Share에 없음.
- [ ] provider quota ledger/degradation, 2026-08-23 verified statuses를 임의 수정하지 않음.
- [ ] historical artifact version/data window/support/fallback/validation trace 가능.
- [ ] B realtime feature는 identity/timestamp/freshness Gate를 통과한 category만 사용.
- [ ] leading vehicle/congestion/headway unverified feature가 active schema/result에 없음.
- [ ] Home에 separate feature CTA 2개, combined Dual Analysis CTA 0.
- [ ] API-011/API-012 schema cross-function metric contamination 0.
- [ ] 한 기능이 다른 기능 analysisId/result를 prerequisite로 요구하는 코드/계약 0.
- [ ] targetReliability/Recommended `{p*}`/API-002 Dual/Start/Event/Reforecast active route·API·UI 0.
- [ ] offline/foreground에서 이전 B snapshot을 current로 승격하지 않음.
- [ ] H100/Jupyter direct runtime call 0, model fallback 정상.
- [ ] B2/U1 claim은 baseline hold-out uplift evidence가 있을 때만.
- [ ] distributed proof를 HA/SLA로 표현하지 않음.
- [ ] Future GPS를 구현된 기능처럼 표현하거나 background permission을 요청하지 않음.

## 정본 정합성 규칙

- canonical product functions는 `DEPARTURE_RECOMMENDATION`, `LEAVE_NOW_FORECAST` 두 개이며 서로 독립 호출 가능하다.
- v0.1 `Dual Analysis`, API-002, ENT-011/015 combined contract는 `RETIRED_FROM_MR`이다.
- Departure API/result에는 Departure P50/P90만 존재한다.
- Leave-now API/result에는 departAt, P(on_time), Arrival P50/P90만 존재한다.
- analysisType은 immutable이며 wrong-type route/read를 coercion하지 않는다.
- Evidence/Share는 single analysisType payload다.
- shared route/data/math library는 product request/result 결합을 의미하지 않는다.
- Departure는 realtime feature를 사용하지 않는다.
- Leave-now realtime은 causality/identity/freshness Gate를 통과한다.
- P50을 평균으로 정의하지 않는다.
- manual tracking/Future GPS/history 경계를 유지한다.
- 과거 Evidence status와 검증되지 않은 feature effect를 fabricated하지 않는다.

## Appendix — Claim wording guardrail

| 금지 | 허용 |
|---|---|
| `한 번에 두 기능 계산` / `통합 분석` | `두 독립 기능이 공통 Reliability Platform을 사용` |
| `P50 평균` | `P50 중앙값/50% threshold` |
| `P90 90% 정확` | percentile/threshold + validation scope |
| Departure에 `실시간 반영` | historical-only planning |
| Leave-now에 Departure P50/P90 | Leave-now 전용 arrival/on-time metrics |
| `AI가 P(on_time)을 직접 계산` | AI는 Leave-now leg distribution 보정 |
| `앞차 영향 검증됨` | 검증 대상 feature candidate |
| `GPS 자동 추적 가능` | Future GPS Research |

## Appendix — Definition of Done

**G2 DONE**: Home에서 두 독립 기능이 분기되고, 각각의 input/API/result/entity/Evidence/Share가 analysisType으로 격리되며, API-011에는 Departure metrics만, API-012에는 Arrival/P(on_time) metrics만 존재하고, 다른 기능 result prerequisite/자동 continuation이 0이며, shared data/engine은 내부 재사용으로만 남고 모든 active MUST/CLAIM_GATE REQ가 AC/CG로 닫힌다.

