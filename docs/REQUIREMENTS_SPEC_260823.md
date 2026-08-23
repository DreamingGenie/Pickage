# Journey Reliability 요구사항정의서

> **문서 목적**: 확정 Service Plan과 IA를 구현 가능한 기능·규칙·인터페이스·데이터·품질·인수 계약으로 변환한다.  
> **문서 지위**: Product / Frontend / Backend / Data / Infra / QA 개발 handoff 정본  
> **정본 파일명**: `REQUIREMENTS_SPEC_260823.md`  
> **기준일**: 2026-08-23  
> **상위 기준**: `SERVICE_PLAN_260823.md`, `IA_SCREEN_SPEC_260823.md`  
> **적용 원칙**: Evidence에 없는 수치로 빈 셀을 채우지 않는다. 측정이 필요한 값은 상태와 해소 Gate를 명시한다.

## 0. 문서 정보와 규모

### 0.1 정의 규모

| 정의 단위 | 수량 | ID 범위 |
|---|---:|---|
| Feature | 18 | F001~F018 |
| Functional Requirement | 67 | REQ-001~098, 영역별 비연속 번호 유지 |
| Business Rule | 48 | BR-001~074, 영역별 비연속 번호 유지 |
| State Transition Rule | 22 | ST-001~022 |
| API/System Interface | 17 | API-000~009, SYS-001~007 |
| Canonical Entity | 23 | ENT-001~023 |
| NFR | 50 | NFR-001~088, 영역별 비연속 번호 유지 |
| Acceptance Scenario | 57 | AC-001~057 |
| Claim Gate | 7 | CG-001~007 |

수량은 문서 행 기준이며 구현 task 수와 동일하지 않다.

### 0.2 Priority와 상태

| 값 | 의미 |
|---|---|
| MUST | Minimum Release 필수 |
| CLAIM_GATE | 구현 가능성과 별개로 사용자/발표 claim 승격에 필요한 조건 |
| SHOULD | 핵심 E2E를 막지 않는 후순위; 일정 시 cut 가능 |
| COULD | 여유 시 선택 |
| TBD_AFTER_PROFILE | 실제 profile·benchmark 후 수치 결정 |
| INSUFFICIENT_SOURCE | source 부재로 결과 생성 금지; limitation/unavailable 필요 |
| HOLD | 계약은 정의됐지만 사용자-facing capability 활성화 금지 |

구현 상태(`PLANNED/IMPLEMENTED/TESTED/RELEASED`)는 별도 backlog에서 관리한다. 이 문서의 Priority를 구현 완료 상태로 해석하지 않는다.

### 0.3 승인 Gate

| Gate | 승인 기준 |
|---|---|
| G0 Service Plan | 승인 완료 |
| G1 IA | 승인 완료 |
| G2 Requirements | F/SCR/REQ/BR-NFR/API/ENT/AC 추적 누락 0, 정책 충돌 0 |
| G3 Contract-safe V0 | placeholder·residual·validation·BUS_SKIPPED·idempotency 계약 테스트 통과 |
| G4 Product E2E | 실제 모바일에서 SCR-01→05, foreground recovery, offline honesty와 정직한 failure states |
| G5 Security/Share | secret/privacy/retention/share expiry 승인 |
| G6 Release | release-blocking AC와 승인된 distributed proof 통과 |

---

## 1. 범위

### 1.1 포함

- 서울 행정구역, supported BUS+SUBWAY mixed structural route 하나
- Pre-trip analysis, Journey Start, Live state, UserEvent, Reforecast
- P50, P90, `P(on_time)`, Planned Connection Success, Final On-time
- Claim Gate 통과 시 Recommended Departure
- WALK/WAIT/TRANSIT_RIDE/TRANSFER/FINAL_WALK 경계
- support/fallback/confidence/freshness/validation/coordinate provenance
- Evidence Detail, optional Share Snapshot
- Raw→Observation→Actual→Residual→Distribution→Result 추적
- 보안, 개인정보 최소화, 운영·관측성, 분산 correctness proof
- Mobile-first PWA, non-install/standalone 동등성, offline read-only snapshot, foreground recovery, 안전한 update lifecycle
- versioned Route/WALK provider registry, `ROUTE_A_ONLY/KAKAO_WALK_ONLY` Minimum Release coverage mode, future `PROVIDER_SUPPORTED` promotion Gate

Minimum Release 완료는 두 층으로 판정한다. **Contract-complete**는 모든 정상·부족·실패 상태와 provenance가 구현된 상태이고, **Claim-capable**은 실제 Route A probability가 해당 Claim Gate를 통과한 상태다. Contract-complete를 위해 근거 없는 확률 숫자를 만들지 않으며 Claim-capable 미달은 `NOT_COMPUTED/INSUFFICIENT/HOLD`로 정상 처리한다.

### 1.2 Explicit Out

- route optimizer, 다중 경로 reliability ranking, “가장 안전한 경로”
- citywide accuracy/coverage/SLA, 전국/수도권 자동 지원
- 개인 boarding-failure probability, 미래 사고 발생확률
- BUS_TO_BUS, native app store package, 계정 personalization, push notification, background 위치 추적
- mandatory ML/AI와 생성형 AI probability
- 임의 WALK/transfer variance 또는 missing leg placeholder
- profile 전 stale/support/SLO/partition/watermark/TTL 수치

---

## 2. Feature Dictionary

| F-ID | Feature | 사용자 결과 | Primary SCR | Core REQ |
|---|---|---|---|---|
| F001 | Journey Input / Anonymous Access | 입력과 owner capability 발급 | SCR-01 | 001~004,007 |
| F002 | Structural Route / Provider Gate | Minimum Release의 Route A manifest 선택과 WALK provider provenance; future route-provider Gate의 first canonical-supported candidate 선택·정규화 | SCR-01/02/05 | 005~006,008~009 |
| F003 | Pre-trip Analysis | selected route의 도착분포·eligibility 계산 | SCR-02 | 010~017 |
| F004 | Journey Start/State | 분석 snapshot으로 live Journey 시작·복구 | SCR-02/03 | 020~021 |
| F005 | User Event | BOARD/BUS_SKIPPED/TRANSFER_MISSED | SCR-03 | 022~024 |
| F006 | Reforecast | 완료 이력 고정 후 남은 여정 재계산 | SCR-03/04 | 025~026 |
| F007 | WALK/Coordinate | provider별 access/final walk point와 좌표 provenance | SCR-02/03/05 | 030~032 |
| F008 | Transfer Domain | B2S/S2S/S2B 경계와 reference | SCR-02/03/05 | 033~035 |
| F009 | Evidence/Support | support·confidence·fallback·validation | SCR-02/05 | 040~045 |
| F010 | Freshness/Error | source→Journey freshness, stale/partial/provider/unsupported/no-fake | SCR-01/02/03 | 050~056 |
| F011 | Prediction/Actual/Residual | 관측과 signed error 계약 | SCR-05/Backend | 060~067 |
| F012 | Wait/Service Candidate | realtime/timetable/empirical WAIT | SCR-03/05 | 070~073 |
| F013 | Share Snapshot | privacy-safe read-only 결과 공유 | SCR-06 | 080~082 |
| F014 | Result Traceability / Internal QA | 결과 추적과 격리된 Route B 구조 검증 | SCR-05/Internal | 090~092 |
| F015 | Security/Privacy | secret·좌표·retention·access 보호 | Global | NFR-040~052 |
| F016 | Operations/Observability | provider/stream/API/artifact 관측, quota/entitlement, 2-node 복구, demo manifest | Ops | 008~009, NFR-030~069,083~088 |
| F017 | Distributed/ML Proof | scale/failure/correctness와 ML promotion | Internal | NFR-080~083,086, CG-006~007 |
| F018 | Mobile-first PWA Runtime | 설치 여부와 무관한 mobile flow, offline honesty, foreground recovery | Global/SCR-01~05 | 093~098, NFR-074~079,085~086 |

---

## 3. Functional Requirements

> 각 행은 `상세조건 → 정상 처리 → 예외·오류 → Interface/Entity → Rule/Acceptance`가 닫힌 구현 계약이다. API path의 최종 naming은 API Contract를 따르되 semantics와 ID는 고정한다.

### 3.1 Journey Input / Route

| REQ | F / SCR / Route | Priority | 상세조건·정상 처리 | 예외·오류 | Interface / Entity | BR·NFR / AC |
|---|---|---|---|---|---|---|
| REQ-001 출발지 입력 | F001 / SCR-01 / `/` | MUST | 장소명·주소 또는 명시적 one-shot 현재 위치를 label+coordinate로 resolve하고 `ORIGIN_POINT` role/source 저장. resolve 완료 전 분석 금지 | `LOCATION_NOT_RESOLVED`, `UNSUPPORTED_GEOGRAPHY`; 권한 거부 시 수동 입력 유지; raw response/secret 미노출 | SYS-001, API-000/002 / ENT-016,017,011 | BR-001,060,070 / AC-001,002,025,046 |
| REQ-002 목적지 입력 | F001 / SCR-01 / `/` | MUST | POI까지 표현하며 final boundary는 마지막 WALK 완료. destination label+coordinate provenance 저장 | 출발지와 동일/resolve 실패/서울 외면 submit 차단 | SYS-001, API-000/002 / ENT-016,017,011 | BR-001 / AC-001,025 |
| REQ-003 목표 도착시각 | F001 / SCR-01 | MUST | future timezone-aware datetime, Asia/Seoul 표시·rollover 지원 | 과거/invalid/naive datetime → `INPUT_INVALID` | API-002 / ENT-011 | BR-010 / AC-001,026 |
| REQ-004 목표 reliability | F001 / SCR-01 | MUST | 미지정 0.90, UI percent와 내부 0~1 분리 | 허용범위 밖→`INPUT_INVALID`; 90%를 SLA/accuracy로 설명 금지 | API-002 / ENT-011 | BR-003,060 / AC-001,003 |
| REQ-005 Structural Route 조회·선택 | F002 / SCR-01→02 | MUST | Minimum Release에서는 manifest hash가 일치하는 Route A와 `APPROVED_DEMO_ROUTE`를 기록한다. `PROVIDER_SUPPORTED`는 future mode이며, 활성화 시 provider order를 유지해 서울·mixed mode·ID/leg가 해석 가능한 첫 candidate와 `PROVIDER_FIRST_SUPPORTED`를 기록한다 | route 없음, provider error, mapping incomplete, unsupported, manifest mismatch를 구분; mode 간 silent switch 금지. Kakao publictraffic 후보를 Route A로 대체하거나 시간값을 혼합 금지 | API-001, SYS-002 / ENT-005 | BR-001~003,071 / AC-001,002,004,057 |
| REQ-006 Route normalization | F002 / SCR-02/03/05 | MUST | provider topology를 ACCESS_WALK/WAIT/TRANSIT_RIDE/TRANSFER/FINAL_WALK과 3 TransferType으로 변환; Transfer와 WAIT 분리 | 필수 node/leg identity 누락→`ROUTE_MAPPING_INCOMPLETE`; 조용한 leg 삭제 금지 | SYS-002 / ENT-005~009,017,018 | BR-030~032 / AC-004,017 |
| REQ-007 Anonymous Journey Access | F001/F015 / SCR-02~05 | MUST | Journey 생성 시 browser-bound owner capability 발급; `journeyId`는 locator만 사용. 조회·Start·Event·Evidence·Share 생성마다 owner capability 검증 | capability 없음/불일치는 resource 존재를 숨기는 동일 not-found/recovery; cross-device owner 복구 없음 | API-002~007 / ENT-012,020 | BR-004; NFR-041~043,053 / AC-035,036 |
| REQ-008 Provider Registry / Coverage Mode | F002/F016 / SCR-01/02/05 | MUST | provider·endpoint·adapterVersion·quota policy·selection policy를 versioned registry로 관리하고 Minimum Release deployment는 `ROUTE_A_ONLY` + `KAKAO_WALK_ONLY`를 반환. `PROVIDER_SUPPORTED`는 future route-provider mode다. `KAKAO_MOBILITY_WALK_LEGACY`, `KAKAO_MAP_WALK`, `KAKAO_MAP_PUBLIC_TRANSIT`는 별도 providerKey | UI와 server mode 불일치, provider silent switch, 구 Kakao Mobility 403과 신규 Kakao Map 성공의 병합, 다른 provider provenance 재사용 금지. publictraffic reference evidence를 selected route로 승격 금지 | API-001/002/006/009, SYS-001/002/007 / ENT-005,015,017,023 | BR-005,071~074; NFR-087,088 / AC-053~057 |
| REQ-009 Kakao Route Provider Promotion Gate | F002/F016 / SCR-01/05/Internal | FUTURE_OPTIONAL / NOT_REQUIRED_FOR_WALK_ONLY | `KAKAO_ROUTE_PROVIDER_GATE`: Kakao publictraffic을 Primary route provider로 승격할 때만 앱 entitlement, canonical bus/stop·station×line mapping, total/step/WAIT/WALK 시간 포함관계, 동일 OD 반복 안정성을 검증. **2026-08-23 판정: entitlement CONFIRMED(콘솔, publictraffic 9/1,000·walk 4/1,000) / mapping REJECTED(구조적 한계) / 시간 포함관계 PARTIAL / 반복 안정성 PASS → route-provider 승격 미통과.** `KAKAO_MAP_WALK` 사용은 REQ-031과 AC-056의 WALK provider contract를 따른다 | Kakao publictraffic route-provider 승격 실패→`ROUTE_A_ONLY + KAKAO_WALK_ONLY`; HTTP 200만으로 USER_FACING route 승격 금지 | SYS-001/002/007 / ENT-001,005,017,023 | BR-005,071~074; NFR-087,088 / AC-053~057 |

### 3.2 Pre-trip Analysis

| REQ | F / SCR / Route | Priority | 상세조건·정상 처리 | 예외·오류 | Interface / Entity | BR·NFR / AC |
|---|---|---|---|---|---|---|
| REQ-010 Journey Analysis | F003 / SCR-02 / `/journey/{id}/plan` | MUST | selected route와 versioned leg inputs로 simulation; P50/P90/on-time/connection/recommended status/confidence/coverage/fallback/freshness/limitations 반환 | critical input 없음→`NOT_COMPUTED`; placeholder 금지; engine fixture user-facing 금지 | API-002, SYS-003 / ENT-010~015 | BR-010~016 / AC-003~007,021 |
| REQ-011 P50 | F003 / SCR-02/04/06 | MUST | final arrival samples의 Q0.50; KST datetime 반환; 기본 copy는 모델 도착분포의 중앙값 | result ineligible/null이면 미표시+reason; 평균과 동일시 금지 | SYS-003, API-002 / ENT-015 | BR-010,014 / AC-005,021 |
| REQ-012 P90 | F003 / SCR-02/04/06 | MUST | final arrival samples의 Q0.90; 기본 copy는 모델 도착분포의 90번째 백분위 | `90% 정확도`/exact arrival 표현 금지; E2E calibration 전 반복빈도 copy 금지; partial uncertainty limitation 전달 | SYS-003, API-002 / ENT-015 | BR-010,052,060,063 / AC-005,027,057 |
| REQ-013 On-time Probability | F003 / SCR-02/03/04/06 | MUST | `ΣI(finalArrival≤target)/N`; 0~1 저장, UI whole percent formatting | null≠0; low support/partial/validation scope 숨김 금지 | SYS-003, API-002/004 / ENT-014,015 | BR-010,012,016 / AC-005,021 |
| REQ-014 Planned Connection Success | F003 / SCR-02/04 | MUST when connection | 처음 계획한 candidate connection을 모두 지킨 simulation 비율; Final On-time과 별도 | 환승 없음/미계산을 0으로 채우지 않음; 두 metric 단순 대소 규칙 강제 금지 | SYS-003 / ENT-014,015 | BR-011 / AC-006,022 |
| REQ-015 Recommended Departure | F003 / SCR-02/06 | CLAIM_GATE/HOLD | route R, target T, p* 조건을 만족하는 가장 늦은 candidate. 각 d마다 WAIT/service/context/connection 재평가, grid/coarse-to-fine | future source/critical input/feasible candidate 없음→INSUFFICIENT_DATA/NOT_COMPUTED; simple shift·미검증 binary search 금지 | SYS-003, API-002 / ENT-008~015 | BR-020~024 / AC-007,023, CG-004 |
| REQ-016 Result Eligibility | F003 / SCR-02~05 | MUST | `USER_FACING/ENGINE_FIXTURE_ONLY/NOT_COMPUTED`, validationScope, provenance를 함께 반환 | real input missing에 fabricated numeric result 금지; V0 fixture user 화면 금지 | API-002 / ENT-014,015 | BR-013,014,062 / AC-003,008,021 |
| REQ-017 Eligibility / Start Decision | F003/F004 / SCR-02 | MUST | required time-bearing leg마다 valid distribution 또는 approved deterministic/reference input이 있으면 core 계산 가능. uncertainty만 미모델링이면 `USER_FACING+PARTIAL_MODEL`; input 자체 부재면 `NOT_COMPUTED`. `startEligibility=ELIGIBLE/REFRESH_REQUIRED/BLOCKED`와 reasonCodes 반환 | confidence `INSUFFICIENT`만으로 Start 차단 금지; optional connection/recommended 부재로 core 자동 무효화 금지 | API-002/003 / ENT-006~010,015 | BR-014,017,045 / AC-003,020,036,037 |

### 3.3 Journey Start / State / Reforecast

| REQ | F / SCR / Route | Priority | 상세조건·정상 처리 | 예외·오류 | Interface / Entity | BR·NFR / AC |
|---|---|---|---|---|---|---|
| REQ-020 Journey Start | F004 / SCR-02→03 | MUST | owner capability valid, USER_FACING, `startEligibility=ELIGIBLE`, PRE_TRIP_READY snapshot을 idempotent하게 ACTIVE로 전환; route/result/target/state version 보존 | NOT_COMPUTED/fixture/unsupported/REFRESH_REQUIRED/BLOCKED→차단; INSUFFICIENT confidence 단독 차단 금지; 중복 start는 같은 state 반환 | API-003 / ENT-012,015,020 | BR-043~045; NFR-023,053 / AC-009,035~037 |
| REQ-021 Current Journey State | F004 / SCR-03 | MUST | completed/active/future leg, freshness, current result, next candidate, state/result version 제공; direct route 복구 | ACTIVE인데 activeLeg 없음→contract error; resource 없음/상태 불일치 구분 | API-004 / ENT-006,012~015 | BR-040,044 / AC-009,010,024 |
| REQ-022 BOARD_CONFIRMED | F005 / SCR-03 | MUST | WAIT+identifiable candidate에서 user-confirmed event; WAIT completed, candidate fixed, RIDE active, reforecast 가능 | state/candidate mismatch, duplicate event; stale/no candidate에서 CTA/API 거부 | API-005 / ENT-008,012,013 | BR-041,043 / AC-010,011 |
| REQ-023 BUS_SKIPPED | F005 / SCR-03→04 | MUST | BUS_WAIT+candidate에서 current candidate만 SKIPPED; event time/complete history fixed; next BUS_WAIT+same BUS_RIDE+downstream 유지 | next source 없음→REFORECAST_UNAVAILABLE; bus ride 삭제 금지; boarding probability로 생성 금지 | API-005, SYS-003 / ENT-006,008,009,012,013 | BR-040~044 / AC-011~013 |
| REQ-024 TRANSFER_MISSED | F005 / SCR-03→04 | SHOULD | versioned Tier-0 feasibility rule 또는 user confirmation으로 planned candidate MISSED, next candidate 탐색 | rule/UI 미활성 시 CTA 없음; next source 없으면 unavailable | API-005 / ENT-007,008,012,013 | BR-030~034,041 / AC-014 |
| REQ-025 Reforecast | F006 / SCR-03/04 | MUST | current state에서 completed history/user facts/current time 고정, future만 재계산; new result version과 before/after 반환 | required source 없음→UNAVAILABLE, internal failure→FAILED; 이전 result를 새 current처럼 표시 금지 | API-005, SYS-003 / ENT-012~015 | BR-040~044; NFR-002,023 / AC-012~015 |
| REQ-026 Reforecast Reason | F006 / SCR-04 | MUST | deterministic reasonCode(`BUS_SKIPPED_NEXT_SERVICE`, `BOARD_CONFIRMED`, `TRANSFER_MISSED`, `SOURCE_STATE_UPDATE`, `REFORECAST_UNAVAILABLE`) 반환 | unknown reason→generic+logging; AI는 code 대체 금지 | API-005 / ENT-013,015 | BR-044 / AC-015 |

### 3.4 WALK / Transfer / Coordinate

| REQ | F / SCR | Priority | 상세조건·정상 처리 | 예외·오류 | Interface / Entity | BR·NFR / AC |
|---|---|---|---|---|---|---|
| REQ-030 Coordinate Provenance | F007 / SCR-05 | MUST | 모든 endpoint에 lat/lon/source/role/mappingVersion; role은 ORIGIN/POI/BUS_STOP/STATION_CENTER/STATION_EXIT/PLATFORM_REFERENCE | role unknown→DQ flag/leg limitation; center→exit/platform coercion 금지 | SYS-001/002 / ENT-016,017 | BR-052 / AC-016,025 |
| REQ-031 ACCESS WALK | F007 / SCR-02/05 | MUST | origin→first boarding point의 versioned provider point/reference; `DETERMINISTIC_POINT`, uncertainty UNMODELED 가능. Kakao/TMAP 값을 source별 보존 | provider failure 시 동일 provider/version의 승인 cached reference 없으면 unavailable; provider 간 평균·silent substitution·임의 속도/variance 금지 | SYS-001 / ENT-006,010,016,017 | BR-052,072; NFR-030,087 / AC-016,027,056 |
| REQ-032 FINAL WALK | F007 / SCR-02/03/05 | MUST | final alight→actual POI; Journey ARRIVED는 완료 후. STATION_CENTER 기반이면 명시 | exit 기반 표현·목적 역 도착 terminal 금지 | SYS-001 / ENT-006,010,016,017 | BR-052 / AC-016,017,027 |
| REQ-033 BUS_TO_SUBWAY | F008 / SCR-02/03/05 | MUST | street component + station internal component를 분리해 boarding-ready point 도달; WAIT는 이후 | internal source 없음→PARTIAL/UNMODELED; depth를 시간으로 환산 금지 | SYS-002 / ENT-007,016,017 | BR-030~032,052 / AC-017,027 |
| REQ-034 SUBWAY_TO_SUBWAY | F008 / SCR-02/03/05 | MUST | official reference 사용 가능; Route A Tier-0 OA-22521 144s, uncertainty UNMODELED | OA-13290 63s와 평균/혼합 금지; 개인 분포로 표현 금지 | SYS-002 / ENT-007,010 | BR-030~034,052 / AC-017,027 |
| REQ-035 SUBWAY_TO_BUS | F008 / SCR-02/03/05 | MUST | platform→exit internal + exit→bus stop street, 이후 BUS_WAIT 별도 | structural interoperability를 product E2E로 승격 금지; component 부족 시 limitation | SYS-002 / ENT-007,008,016,017 | BR-030~032,051 / AC-017,CG-003 |

### 3.5 Evidence / Support / Confidence

| REQ | F / SCR | Priority | 상세조건·정상 처리 | 예외·오류 | Interface / Entity | BR·NFR / AC |
|---|---|---|---|---|---|---|
| REQ-040 Support Metadata | F009 / SCR-05 | MUST | leg/artifact별 effective sample unit/count, observation window, group, fallback, rule/artifact version | sample unit 미확정이면 raw row count를 support로 사용 금지; count nullable | API-006 / ENT-008,010,014 | BR-012,050~053 / AC-018,019 |
| REQ-041 Confidence | F009 / SCR-02/03/05 | MUST/CLAIM_GATE | probability와 분리된 HIGH/MEDIUM/LOW/INSUFFICIENT; SUPPORT_RULE_V1 전 empirical 기본 INSUFFICIENT | 5/20/100 등 임의 threshold 금지; label rule/version 누락 시 승격 금지 | API-002/006 / ENT-010,015 | BR-012,050; CG-005 / AC-018,020 |
| REQ-042 Fallback | F009 / SCR-02/05 | MUST | broader supported group/reference 사용 시 level/reason/support/provenance 유지 | source 없는 critical leg를 fallback 숫자로 채우지 않음 | API-002/006 / ENT-010,015 | BR-012~014 / AC-003,018 |
| REQ-043 Unmodeled Uncertainty | F009 / SCR-02/05/06 | MUST | WALK/static transfer 등 variance 부재를 `UNMODELED_UNCERTAINTY`, coverage PARTIAL로 전달 | 임의 Gaussian/±% 생성 금지; critical limitation 숨김 금지 | API-002/006/008 / ENT-007,010,015 | BR-052,061 / AC-018,027 |
| REQ-044 Validation Scope | F009 / SCR-02/05/06 | MUST | V0 UNVALIDATED, V1 COMPONENT_ONLY, V2 CORRIDOR_REPLAY, V3 END_TO_END 매핑 | component→E2E 승격 금지; 계약 실패 fixture를 COMPONENT_ONLY로 승격 금지 | API-002/006/008 / ENT-010,014,015 | BR-050,051; CG-001 / AC-020,021 |
| REQ-045 Evidence Detail | F009 / SCR-05 | MUST | result/leg scope, source semantics, support, fallback, freshness, limitation, validation, coordinate provenance 제공 | endpoint failure가 parent result를 삭제하지 않음; raw secret/private coordinate 미노출 | API-006 / ENT-001~018 | BR-050~053,061 / AC-018,025 |

### 3.6 Freshness / Error / Unsupported

| REQ | F / SCR | Priority | 상세조건·정상 처리 | 예외·오류 | Interface / Entity | BR·NFR / AC |
|---|---|---|---|---|---|---|
| REQ-050 Source Freshness | F010 / SCR-02/03/05 | MUST | source_generated/requested/received/calculated를 분리하고 provider-specific state 반환 | source time 없음은 flag+received fallback; 하나의 global now로 합치지 않음 | SYS-004, API-002/004/006 / ENT-001~003,015 | NFR-010,011 / AC-026,028 |
| REQ-051 Stale | F010 / SCR-02/03 | MUST | threshold 초과 시 STALE, last success/calculatedAt/retry 제공; stale container에서만 이전 값 표시 | fresh/live로 표시 금지; exact threshold는 TBD_AFTER_PROFILE | API-002/004 / ENT-015 | BR-061; NFR-011 / AC-028 |
| REQ-052 Provider Error | F010 / SCR-01/02/03 | MUST | transport와 business/quota error를 taxonomy로 변환; retryable/last success 제공 | raw error body/key 노출 금지; HTTP 200 quota payload success 처리 금지 | SYS-004, API-001~005 / ENT-001 | NFR-030,040,060 / AC-028,029 |
| REQ-053 Partial Data | F010 / SCR-02/05 | MUST | 일부 leg/reference만 usable일 때 eligibility policy가 허용하면 PARTIAL+limitation | critical input missing을 PARTIAL로 과승격 금지 | API-002/006 / ENT-010,015 | BR-012~014,061 / AC-003,027 |
| REQ-054 Unsupported | F010 / SCR-01/02 | MUST | geography/mode/route mapping 범위 밖이면 explicit unsupported | probability=0 또는 stale result로 대체 금지 | API-001/002 / ENT-005,015 | BR-001,060 / AC-002 |
| REQ-055 No Fake Fallback | F010 / Global | MUST | real path missing input→NOT_COMPUTED; synthetic fixture→ENGINE_FIXTURE_ONLY | arbitrary 400/600s/variance, mixed placeholder, fixture demo 금지 | SYS-003 / ENT-010,014,015 | BR-013,014,062 / AC-003,021,034 |
| REQ-056 Journey Freshness Aggregation | F010 / SCR-02/03/05 | MUST | source를 `CRITICAL_CALCULATION/NON_CRITICAL_CONTEXT`로 분류. critical usable input 없음→NOT_COMPUTED/PROVIDER_ERROR; critical 중 STALE 존재→STALE; 그 외 AGING 존재→AGING; 모두 FRESH→FRESH. non-critical failure는 core state 유지 | Frontend source-name 추론 금지; last success와 current input 혼합 금지; PARTIAL/confidence/validation과 단일 enum으로 합치지 않음 | API-002/004/006 / ENT-001,010,015 | BR-064; NFR-011,030 / AC-038 |

### 3.7 Prediction / Actual / Residual

| REQ | F / SCR | Priority | 상세조건·정상 처리 | 예외·오류 | Interface / Entity | BR·NFR / AC |
|---|---|---|---|---|---|---|
| REQ-060 Prediction Snapshot | F011 / SCR-05 dev | MUST | mode/route/vehicle-or-train/target/predictedAt/ETA/source/received/observation ID 보존 | vehId=0/no candidate를 real vehicle prediction으로 생성 금지 | SYS-004 / ENT-001,002 | BR-050 / AC-030 |
| REQ-061 Actual Arrival Interval | F011 / SCR-05 dev | MUST | polling exact time 불명 시 `(lower exclusive, upper inclusive]`, midpoint,width,rule,source IDs 저장 | midpoint만 보존하거나 invalid interval 생성 금지 | SYS-005 / ENT-003 | BR-050 / AC-030 |
| REQ-062 Bus Actual | F011 / Data | CLAIM_GATE | same route/vehicle/validated target context의 `stopFlag 0→1`; nondecreasing source time, dedupe | `1→0` departure를 arrival로 사용 금지; target identity 미검증 match는 diagnostic | SYS-005 / ENT-001~004,017 | CG-002 / AC-030,031 |
| REQ-063 Subway Actual | F011 / Data | CLAIM_GATE | `(subwayId,statnId,trainNo)`에서 `arvlCd!=1→1` 최초 transition | station name 혼합/line 누락/citywide 승격 금지 | SYS-005 / ENT-001~004 | CG-003 / AC-030,032 |
| REQ-064 Residual | F011 / Data | MUST | predictedArrival과 Actual interval로 signed lower/mid/upper 생성 | sign 제거/interval 파괴 금지 | SYS-005 / ENT-002~004 | BR-010,050 / AC-030,033 |
| REQ-065 Residual Semantics | F011 / Engine | MUST | `PREDICTION_RESIDUAL_SECONDS`는 provider prediction에 더함; duration/wait/transfer와 type 분리 | `abs(residual)`/residual-as-duration 금지 | SYS-003/005 / ENT-004,010 | BR-013 / AC-021,033 |
| REQ-066 Prediction Horizon | F011 / Data/ML | MUST | prediction 시점 observable ETA/horizon을 conditioning에 사용; realized outcome 별도 저장 | actual-derived time-to-event feature leakage 금지 | SYS-005 / ENT-004 | CG-007 / AC-033 |
| REQ-067 Out-of-order Detection | F011 / Data | MUST | collector receive order에서 source-time reversal 측정 후 canonical sort | source-time sort 후 비교해 evidence 제거 금지; threshold TBD | SYS-004/005 / ENT-001 | NFR-010,061 / AC-026,031 |

### 3.8 WAIT / Candidate Service

| REQ | F / SCR | Priority | 상세조건·정상 처리 | 예외·오류 | Interface / Entity | BR·NFR / AC |
|---|---|---|---|---|---|---|
| REQ-070 Bus WAIT Source | F012 / SCR-03/05 | MUST | near-now realtime candidate; future는 time-conditioned empirical wait/headway. sampleUnit·dependence 저장 | polling snapshot count를 iid support로 사용 금지; future exact vehId 필수 가정 금지 | SYS-004/003 / ENT-008,010 | BR-024,031,050 / AC-019,023 |
| REQ-071 Bus Event Unit | F012 / Data | CLAIM_GATE | previous candidate progression/near-zero·Actual 가능성/stop topology를 만족한 passenger-relevant event 또는 dependence-aware sampling | simple vehId turnover·near-terminal dispatch churn을 headway로 해석 금지 | SYS-005 / ENT-008,010 | CG-005 / AC-019 |
| REQ-072 Subway WAIT Source | F012 / SCR-03/05 | MUST | realtime exact candidate, verified timetable, empirical headway 중 source/version 저장 | timetable prior를 exact current guarantee로 표현 금지; source 없음→unavailable | SYS-004/003 / ENT-008,010 | BR-024,050 / AC-023,032 |
| REQ-073 Service Day | F012 / Engine | MUST | DAY/SAT/END, direction, service date, `>=24:00` rollover, encoding/source version 처리 | naive date split/24:00 parse failure→WAIT unavailable+quality flag | SYS-003/006 / ENT-008,010 | NFR-021,022 / AC-023 |

### 3.9 Share / Trace / Demo

| REQ | F / SCR | Priority | 상세조건·정상 처리 | 예외·오류 | Interface / Entity | BR·NFR / AC |
|---|---|---|---|---|---|---|
| REQ-080 Share Snapshot | F013 / SCR-06 | SHOULD | owner capability가 있는 Journey에서 eligible immutable snapshot 생성: destination,target,eligible summary,scope,critical limitation,calculatedAt | exact origin/coordinate/raw ID/debug/secret 제외; feature cut 시 core 무영향 | API-007/008 / ENT-015,019,020 | NFR-050~053 / AC-025,039 |
| REQ-081 Share Expiry | F013 / SCR-06 | SHOULD | opaque unpredictable token, 서버에는 digest+expiry+revocation status 저장, valid/expired/invalid variants | exact TTL은 G5 전 hard-code 금지; token logging/analytics/cache resurrection 금지 | API-007/008 / ENT-019 | NFR-051~054 / AC-025,039 |
| REQ-082 Share Authorization Boundary | F013/F015 / SCR-06 | SHOULD/G5 | Share token은 ENT-019 snapshot read만 허용하며 원본 Journey/Evidence/Start/Event/재공유 권한이 없다 | Share token을 owner capability로 교환·승격 금지; revoke/expire 후 read 금지 | API-007/008 / ENT-019,020 | BR-004; NFR-051~054 / AC-039 |
| REQ-090 Result Traceability | F014 / SCR-05/Demo | MUST final | result→run→distribution/wait/route/rule/source/raw ref와 version 역추적; fixed seed/N/state version | missing provenance result는 final demo eligibility 없음; raw handoff partial 표시 | API-006 / ENT-001~015 | BR-050,062; NFR-020,022,063 / AC-018,034 |
| REQ-091 No Mock Final Result | F014 / Demo | MUST | final user result는 real pipeline output+eligible metadata만 | hard-coded·illustrative·계약 실패 fixture·amplified training support 금지 | SYS-003/006 / ENT-014,015 | BR-053,062 / AC-034 |
| REQ-092 Route B Internal QA Isolation | F014 / Internal QA | MUST | Route B structural fixture는 격리된 development/QA runner에서 topology·realtime ID interoperability·BUS_SKIPPED invariant 검증에만 사용하고 provenance/run manifest를 남김 | 사용자 UI, public demo build/narrative, product analytics, production route selector에 노출 금지 | SYS-002/003/006 / ENT-005,014,015 | BR-053,062,065; NFR-066 / AC-040 |

### 3.10 Mobile-first PWA Runtime

| REQ | F / SCR | Priority | 상세조건·정상 처리 | 예외·오류 | Interface / Entity | BR·NFR / AC |
|---|---|---|---|---|---|---|
| REQ-093 Mobile Web/PWA Parity | F018 / SCR-01~05 | MUST | 설치하지 않은 mobile browser와 standalone display mode에서 동일 route guard, result semantics, CTA, error, accessibility 제공 | install 여부를 capability/claim gate로 사용 금지; unsupported browser는 mobile Web으로 계속 | API all / ENT-012,015,020 | BR-066; NFR-070,074 / AC-041,042 |
| REQ-094 Manifest/Installability | F018 / Global | MUST | HTTPS, manifest, icons, app name, start URL, standalone display와 installability smoke 제공; 설치 유도는 task를 차단하지 않음 | install prompt 미지원·거부는 오류가 아니며 반복 강요 금지 | SYS-001 / N/A client metadata | BR-066; NFR-041,075 / AC-042 |
| REQ-095 Offline Snapshot | F018 / SCR-02~05 | MUST | 마지막 eligible result의 privacy-safe projection만 device storage에 저장하고 `OFFLINE_SNAPSHOT`, savedAt, read-only로 표시 | snapshot 없음→offline empty; Start/Event/Share/새 분석을 성공처럼 queue 금지; fresh/live 표현 금지 | API-004/006, ENT-021 | BR-067; NFR-076 / AC-043 |
| REQ-096 Foreground Recovery | F018 / SCR-02~05 | MUST | visibility/pageshow 복귀 시 `RECONNECTING`, owner API로 최신 state/result version 재조회 후 server 정본 반영 | 완료 전 mutation 잠금; network 실패 시 offline/error; local optimistic state를 server 위에 유지 금지 | API-004, ENT-012,015,021 | BR-068; NFR-077 / AC-044 |
| REQ-097 Service Worker Update | F018 / Global | MUST | waiting worker를 감지하고 active mutation이 없을 때만 사용자 제어 또는 안전한 정책으로 activate; cache version과 runtime version 관측 | event/reforecast 중 강제 reload·중복 reload loop·구 schema API cache resurrection 금지 | SYS-001, ENT-022 | BR-069; NFR-078 / AC-045 |
| REQ-098 Device Capability | F018 / SCR-01/02/03 | MUST | `현재 위치 사용` click 후 foreground one-shot geolocation; 거부 시 수동 입력. Web Share 가능 시 OS sheet, 실패/미지원 시 copy fallback | page load 권한 선요청·continuous/background GPS 금지; share token analytics/log 금지 | API-000/007, ENT-016,019 | BR-070; NFR-050,079 / AC-046,047 |

---

## 4. Business Rules

### 4.1 Scope / Route

| BR | Rule |
|---|---|
| BR-001 | 서울 지원범위 밖에서 probability를 생성하지 않는다. |
| BR-002 | provider order를 reliability score로 재정렬하지 않는다. |
| BR-003 | selected-route 조건부 결과를 global recommendation으로 표현하지 않는다. |
| BR-004 | `journeyId`는 authorization credential이 아니며 owner capability와 Share read token은 상호 대체·승격할 수 없다. |
| BR-005 | provider HTTP 성공, Kakao WALK point 측정, canonical mapping 성공, Journey probability eligibility는 서로 다른 Gate다. WALK point 측정에는 route canonical mapping을 요구하지 않는다. |

### 4.2 Probability / Result

| BR | Rule |
|---|---|
| BR-010 | P50, P90, `P(on_time)`은 서로 다른 metric이다. |
| BR-011 | Planned Connection Success와 Final On-time을 분리한다. |
| BR-012 | 결과에는 support/fallback/coverage/validation/freshness/limitation이 필요하다. |
| BR-013 | arbitrary numeric fallback과 잘못된 value semantics를 금지한다. |
| BR-014 | critical input이 없으면 `NOT_COMPUTED`를 허용한다. |
| BR-015 | online Monte Carlo N은 선행 고정하지 않고 대표 artifact의 수렴·fixed-seed 재현성·응답시간·자원 benchmark를 만족하는 최소값으로 versioning한다. |
| BR-016 | finite-N sampling error를 model/data uncertainty나 calibration confidence로 설명하지 않는다. |
| BR-017 | required leg의 valid time input 부재와 uncertainty 미모델링을 구분한다. 전자는 NOT_COMPUTED, 후자는 USER_FACING+PARTIAL_MODEL이 될 수 있다. |

### 4.3 Recommended Departure

| BR | Rule |
|---|---|
| BR-020 | selected structural route 조건부다. |
| BR-021 | 출발 후보마다 service/WAIT/context/connection을 재평가한다. |
| BR-022 | 동일 distribution 단순 time shift를 금지한다. |
| BR-023 | monotonicity 미검증 binary search를 correctness 전제로 쓰지 않는다. |
| BR-024 | future candidate source가 없으면 unavailable이다. |

### 4.4 Domain / Reforecast

| BR | Rule |
|---|---|
| BR-030 | Transfer에 next-service WAIT를 포함하지 않는다. |
| BR-031 | WAIT는 boarding-ready point 도착 이후다. |
| BR-032 | B2S/S2B/S2S를 별도 TransferType으로 둔다. |
| BR-033 | connection miss는 versioned boarding feasibility 또는 user confirmation 결과다. |
| BR-034 | Tier-0 buffer/reference는 rule version을 가진다. |
| BR-040 | completed leg는 Reforecast에서 fixed다. |
| BR-041 | user-confirmed event와 event time은 fixed다. |
| BR-042 | BUS_SKIPPED는 개인 boarding-failure probability가 아니다. |
| BR-043 | UserEvent/Start는 idempotent하다. |
| BR-044 | Reforecast는 새 immutable result snapshot을 만든다. |
| BR-045 | Start gate는 resultEligibility·startEligibility·freshness·owner access로 결정하며 confidence label만으로 차단하지 않는다. |

### 4.5 Evidence / UX

| BR | Rule |
|---|---|
| BR-050 | VERIFIED/confidence/validation claim에는 scope가 맞는 evidence와 rule version이 필요하다. |
| BR-051 | corridor/component evidence를 citywide/E2E로 일반화하지 않는다. |
| BR-052 | point/static reference를 empirical distribution으로 표현하지 않는다. |
| BR-053 | synthetic/amplified replay copy를 training support나 real traffic으로 세지 않는다. |
| BR-060 | unsupported/not-computed/insufficient를 0%로 표현하지 않는다. |
| BR-061 | low-support/stale/partial/unmodeled를 숨기지 않는다. |
| BR-062 | illustrative·synthetic·계약 실패 fixture 숫자를 actual result로 사용하지 않는다. |
| BR-063 | `가장 안전한 경로/출발시간`, `P90=90% 정확도` 표현을 금지한다. |
| BR-064 | Journey freshness는 critical source 상태로 projection하며 confidence·coverage·validation과 결합 enum으로 만들지 않는다. |
| BR-065 | Route B는 격리된 내부 개발·QA 검증에서만 사용하며 사용자 화면과 최종 Demo narrative에 포함하지 않는다. |
| BR-066 | PWA 설치 여부는 기능·권한·확률 의미·검증 범위를 바꾸지 않는다. |
| BR-067 | offline snapshot은 저장 당시 결과의 read-only projection이며 live result가 아니다. |
| BR-068 | foreground 복귀 뒤 server state/result version 동기화가 끝나기 전 mutation을 허용하지 않는다. |
| BR-069 | Service Worker update는 active Journey mutation의 손실·중복보다 우선할 수 없다. |
| BR-070 | 위치 권한은 명시적 action 뒤 one-shot으로만 요청하고 권한 거부가 수동 입력을 막지 않는다. |
| BR-071 | Minimum Release의 `ROUTE_A_ONLY + KAKAO_WALK_ONLY`는 승인된 Route A manifest와 별도 WALK provider만 허용한다. `PROVIDER_SUPPORTED`는 future mode이며 활성 provider order의 first canonical-supported candidate만 허용한다. |
| BR-072 | provider별 route/WALK point·시간·namespace·version을 보존하며 평균·silent substitution·provenance 변경을 금지한다. |
| BR-073 | Kakao의 공식 무료 1,000회는 첫 번째 활성화 앱 조건이다. 프로젝트 앱의 entitlement 확인 전 remaining을 1,000으로 가정하지 않는다. |
| BR-074 | 2-node distributed correctness proof는 high availability나 무중단 failover claim이 아니다. |

---

## 5. State Transition Rules

### 5.1 State enums

| Domain | Values |
|---|---|
| Analysis | IDLE / ANALYZING / SUCCEEDED / FAILED |
| Journey Lifecycle | PRE_TRIP_READY / ACTIVE / ARRIVED / ABORTED |
| Reforecast | IDLE / PROCESSING / APPLIED / UNAVAILABLE / FAILED |
| Leg | PLANNED / AVAILABLE / IN_PROGRESS / COMPLETED / SKIPPED / MISSED / UNAVAILABLE |
| Freshness | FRESH / AGING / STALE / PROVIDER_ERROR / NO_DATA |
| Result Eligibility | USER_FACING / ENGINE_FIXTURE_ONLY / NOT_COMPUTED |
| Recommended Departure | AVAILABLE / INSUFFICIENT_DATA / NOT_COMPUTED |
| Validation Scope | UNVALIDATED / COMPONENT_ONLY / CORRIDOR_REPLAY / END_TO_END |
| Confidence | HIGH / MEDIUM / LOW / INSUFFICIENT |
| Start Eligibility | ELIGIBLE / REFRESH_REQUIRED / BLOCKED |
| PWA Runtime | ONLINE / RECONNECTING / OFFLINE_SNAPSHOT / UPDATE_AVAILABLE |

### 5.2 Transitions

| ST | Current | Event | Preconditions | Next | Side Effect / Invariant | REQ / AC |
|---|---|---|---|---|---|---|
| ST-001 | Analysis.IDLE | ANALYZE | valid input | Analysis.ANALYZING | request snapshot, duplicate submit lock | 001~005 / AC-001 |
| ST-002 | Analysis.ANALYZING | ANALYSIS_SUCCESS | selected route+eligible/not-computed result | Analysis.SUCCEEDED + Journey.PRE_TRIP_READY | resultVersion=1 | 010~017 / AC-003,037 |
| ST-003 | Analysis.ANALYZING | ANALYSIS_FAILED | error taxonomy | Analysis.FAILED | input preserved; retry/edit 가능 | 050~056 / AC-002 |
| ST-004 | Journey.PRE_TRIP_READY | START | owner valid+USER_FACING+start ELIGIBLE | Journey.ACTIVE | stateVersion increment, active leg | 007,017,020 / AC-009,035~037 |
| ST-005 | ACTIVE WAIT | BOARD_CONFIRMED | candidate match | ACTIVE RIDE | WAIT complete, RIDE active | 022 / AC-010 |
| ST-006 | Journey.ACTIVE + BUS_WAIT | BUS_SKIPPED | candidate match | Journey.ACTIVE + Reforecast.PROCESSING | only candidate SKIPPED, event fixed | 023 / AC-011 |
| ST-007 | Reforecast.PROCESSING | NEXT_SERVICE_FOUND | source valid | Journey.ACTIVE + Reforecast.APPLIED + BUS_WAIT | next WAIT+same BUS_RIDE retained | 023,025 / AC-012 |
| ST-008 | Reforecast.PROCESSING | NEXT_SERVICE_MISSING | no source | Journey.ACTIVE + Reforecast.UNAVAILABLE + Leg.UNAVAILABLE | new probability absent, topology retained | 023,025 / AC-013 |
| ST-009 | Journey.ACTIVE + TRANSFER/WAIT | TRANSFER_MISSED | rule/UI enabled | Journey.ACTIVE + Reforecast.PROCESSING | planned candidate MISSED | 024 / AC-014 |
| ST-010 | Reforecast.PROCESSING | SUCCESS | new result | Journey.ACTIVE + Reforecast.APPLIED | resultVersion increment; completed fixed | 025 / AC-015 |
| ST-011 | Reforecast.PROCESSING | FAILED | retryable/nonretryable | Journey.ACTIVE + Reforecast.FAILED | event applied 여부 refetch | 025 / AC-015 |
| ST-012 | ACTIVE FINAL_WALK | ARRIVAL_CONFIRMED | final walk complete | ARRIVED | live polling/events stop | 032 / AC-017 |
| ST-013 | ACTIVE | ABORT | user confirmation | ABORTED | events stop, result provenance retained | 021 / AC-024 |
| ST-014 | FRESH | AGE_CROSSES_POLICY | provider-specific | AGING | notice only | 050,051 / AC-028 |
| ST-015 | AGING/FRESH | STALE_CROSSES_POLICY | provider-specific | STALE | live label off, CTA policy apply | 051 / AC-028 |
| ST-016 | ANY LIVE | PROVIDER_FAILURE | provider error | PROVIDER_ERROR | last success separate | 052 / AC-029 |
| ST-017 | PROVIDER_ERROR/STALE | REFRESH_SUCCESS | new valid source | FRESH/AGING | new calculated snapshot | 050~052 / AC-028 |
| ST-018 | ANY MUTATION | DUPLICATE_IDEMPOTENCY_KEY | event exists | unchanged | no duplicate state/result/event | 020~025 / AC-011 |
| ST-019 | ONLINE owner screen | PAGE_FOREGROUND | owner capability 존재 | RECONNECTING | Start/Event/Share mutation lock, API-004 refetch | 096 / AC-044 |
| ST-020 | RECONNECTING | SYNC_SUCCESS | server state/result version 수신 | ONLINE | local optimistic state 폐기, server 정본 render | 096 / AC-044 |
| ST-021 | ONLINE/RECONNECTING | NETWORK_UNAVAILABLE | privacy-safe snapshot 유무 | OFFLINE_SNAPSHOT 또는 offline empty | 모든 mutation 금지, savedAt 표시 | 095,096 / AC-043,044 |
| ST-022 | ANY PWA runtime | WORKER_WAITING | active mutation 없음/있음 | UPDATE_AVAILABLE 또는 activation defer | 안전한 activation, cache/runtime version 기록 | 097 / AC-045 |

---

## 6. Error Taxonomy

| Code | Layer | Retry | User handling | Must preserve |
|---|---|---:|---|---|
| INPUT_INVALID | Client/API | N after edit | field error | input |
| LOCATION_NOT_RESOLVED | Provider/Client | Y | re-search location | text input |
| UNSUPPORTED_GEOGRAPHY | Product | N | input edit | input |
| ROUTE_NOT_FOUND | Provider/Product | maybe | retry/edit | input |
| ROUTE_PROVIDER_ERROR | Provider | Y | retry, no fake route | input |
| ROUTE_MAPPING_INCOMPLETE | Mapping | N until data fix | unsupported explanation | raw route evidence |
| INSUFFICIENT_DATA | Data/Probability | later | evidence/retry later | route/evidence |
| ANALYSIS_FAILED | Engine | maybe | retry | request/provenance |
| PROVIDER_ERROR | Provider | Y/policy | last success separate | stale snapshot |
| PROVIDER_QUOTA_EXCEEDED | Provider/Ops | not immediate default | wait/budget policy | error code/call ledger |
| PROVIDER_ENTITLEMENT_UNAVAILABLE | Provider/Ops | after operational verification | 새 route 분석 없음; 지원 범위/관리 상태 안내 | provider/app config version, secret 제외 |
| STALE_DATA | Data/Product | Y | refresh | last result/calculatedAt |
| EVENT_NOT_ALLOWED_IN_STATE | Domain | N | refetch current state | current server state |
| EVENT_ALREADY_APPLIED | Domain | N | sync latest | original event/result |
| TARGET_SERVICE_MISMATCH | Domain | Y after refresh | candidate changed | event not applied |
| REFORECAST_UNAVAILABLE | Engine/Data | later | return to live/evidence | required topology/completed history |
| REFORECAST_FAILED | Engine | maybe | refetch applied status then retry | event/state version |
| SHARE_EXPIRED | Share | N | expired page | no private payload |
| SHARE_NOT_FOUND | Share | N | invalid page | no token disclosure |
| NETWORK_UNAVAILABLE | Client/PWA | on reconnect | OFFLINE_SNAPSHOT 또는 offline empty | savedAt, local projection version |
| PWA_UPDATE_DEFERRED | Client/PWA | after mutation | 현재 version 유지, 안전 시 update 안내 | app/cache/worker version |
| INTERNAL_ERROR | System | maybe | generic request ID | logs without secret |

Provider raw error body를 그대로 반환하지 않는다. HTTP status exact mapping은 Backend convention에서 고정하되 error code semantics를 바꾸지 않는다.

---

## 7. API / System Interface Dictionary

### 7.1 User-facing API

| ID | Method/Path | Purpose | Request core | Response core | Errors | Owner |
|---|---|---|---|---|---|---|
| API-000 | GET `/api/v1/locations/search` | 장소 후보 resolve | query 또는 foreground coordinate | label,GeoPoint,role,source | invalid,no result,provider,permission은 client 처리 | Backend/Location |
| API-001 | POST `/api/v1/route-candidates` | Route A manifest 조회/선택(MR), future provider route 조회 | origin,destination | routeManifest,walkProvider,adapterVersion,coverageMode,selectionPolicy,selectedCandidate,futureCandidates,mappingStatus/support | geography,not found,provider entitlement/quota,mapping | Backend/Route |
| API-002 | POST `/api/v1/journeys/analyze` | pre-trip 계산+owner 발급 | input+target+route | journey/result/resultEligibility/startEligibility,routeManifest,walkProvider,coverageMode,selectionPolicy,futureRouteProviderStatus,mappingStatus,sourceFreshness,evidenceSummary; owner capability는 secure channel | insufficient,unsupported,analysis/provider | Backend/Engine |
| API-003 | POST `/api/v1/journeys/{id}/start` | live 시작 | owner capability+expected result/state version | JourneyLifecycleState | unauthorized는 not-found와 동일, invalid state,already started | Backend |
| API-004 | GET `/api/v1/journeys/{id}` | state 복구 | owner capability+id | lifecycle/reforecast/active leg/result/Journey+source freshness/candidate | unauthorized/not found 동일,provider | Backend |
| API-005 | POST `/api/v1/journeys/{id}/events` | user event+reforecast | owner capability+eventType,time,target,idempotency | lifecycle/reforecast state+result/status/reason | unauthorized/not found 동일,not allowed,already,mismatch,reforecast | Backend/Engine |
| API-006 | GET `/api/v1/journeys/{id}/evidence` | evidence detail | owner capability+id/result version optional | Route A manifest/selection, WALK provider/adapter, future route provider/crosswalk, leg/source/support/fallback/validation | unauthorized/not found 동일,unavailable | Backend/Data |
| API-007 | POST `/api/v1/journeys/{id}/share` | snapshot 생성 | owner capability+resultVersion | opaque token,url,expiresAt | unauthorized/not found 동일,not shareable/security | Backend |
| API-008 | GET `/api/v1/share/{token}` | public snapshot | token | privacy-safe snapshot | expired/not found | Backend |
| API-009 | GET `/api/v1/health/summary` | preflight | internal auth policy | component/provider entitlement/quota/Kakao WALK health/future route-provider Gate(REJECTED — mapping 구조적 한계, §AC-055)/coverageMode/artifact summary | partial | Ops |

모든 response는 schemaVersion, requestId, generatedAt을 가진다. Result null을 placeholder로 채우지 않는다. owner API는 network-first이며 Service Worker가 Start/Event/Share mutation을 offline success로 변환하거나 stale API response를 current로 cache하지 않는다. GET offline projection은 ENT-021로 별도 생성하며 API response 원문 cache와 구분한다.

### 7.2 Internal interfaces

| ID | Interface | Input→Output | Contract |
|---|---|---|---|
| SYS-001 | Location/WALK Adapter | place query→resolved GeoPoint; points→walk point | Kakao/TMAP 등 provider별 query/result/provenance/quota/empty/error/retry를 구분; point/reference이며 transit GT 금지; provider 간 평균 금지 |
| SYS-002 | Route/WALK Provider Registry/Normalizer | Route A manifest 또는 future provider route→RouteCandidate/JourneyLeg | adapter/version/coverageMode/selection, provider order, namespace, crosswalk, time semantics; Kakao WALK contract와 future route-provider Gate 분리 |
| SYS-003 | Journey Probability Engine | route+state+distribution→run/result | value semantics, connection, benchmarked N, no placeholder |
| SYS-004 | Collector | external API→Bronze Observation | request-boundary timestamps, quota, raw/error/hash |
| SYS-005 | Actual/Residual Builder | ordered observations→Actual/Residual | interval, identity, sign, receive-order quality |
| SYS-006 | Artifact/Replay Pipeline | Gold/fixture→distribution/validation/benchmark | version/provenance; amplified not support |
| SYS-007 | Quota Coordinator | consumer reservation+provider budget→permit/degradation | credential alias×KST-day ledger, priority, retry cost, projected exhaustion, no bypass |

### 7.3 기준 기술과 배포 경계

| 영역 | 기준 기술 | 구현 경계 | 대안 전환 조건 |
|---|---|---|---|
| PWA | Next.js + TypeScript | manifest, Service Worker, mobile UI, foreground recovery | 통합 난도가 blocker면 custom worker 범위를 shell/static cache로 축소 |
| User API/Engine/Collector | Java 21 + Spring Boot | owner API, state, simulation, quota-aware collector | offline artifact builder만 Python으로 분리 가능 |
| Event/Stream | Kafka + Flink(Java) | replayable input, keyed identity state, Actual/Residual | EC2 profile상 불가능하면 Kafka+Spark Structured Streaming 또는 Spark Standalone replay proof |
| Serving/Operational | PostgreSQL | Journey/result/access/share/quota ledger SoT | profile에서 read contention이 확인될 때 Redis cache 추가 |
| Data Lake/Batch | MinIO+Parquet, Python/Spark | Bronze/Silver/Gold, replay, validation artifact | S3-compatible storage로 교체 가능 |
| Deployment | Docker Compose+Nginx, EC2 2대 | EC2-A public serving, EC2-B data processing을 기본 가설로 하되 두 node worker proof 수행 | 사양 확인 후 process placement ADR; 기능 의미는 불변 |
| Observability | OpenTelemetry+Prometheus/Grafana | API·collector·quota·stream·PWA runtime 신호 | 동등한 trace/metric 계약을 만족하는 도구로 교체 가능 |

framework·tool 교체는 허용하지만 API semantics, entity provenance, state transition, distributed correctness Gate를 약화할 수 없다. EC2 CPU/RAM/disk와 partition·watermark·TTL은 profile 뒤 ADR로 확정한다.

2-node 배치는 분산 task 참여·replay·correctness를 증명하기 위한 구조다. Kafka·JobManager·object store 등이 EC2-B에 집중된 현재 가설은 high availability가 아니며, 무중단 failover 또는 SLA 근거로 사용하지 않는다.

#### 7.3.1 2-node provisional deployment contract

| Node | MUST process | CONDITIONAL process | Isolation/Recovery |
|---|---|---|---|
| EC2-A | Nginx, Next.js PWA, Spring Boot API, PostgreSQL | Flink TaskManager A | public ingress는 Nginx/HTTPS로 제한; DB·internal UI 직접 공개 금지 |
| EC2-B | Collector, Quota Coordinator, Kafka, Flink JobManager, Flink TaskManager B, MinIO | offline Python artifact builder | Kafka/Flink/MinIO internal 접근; raw/object/DB backup과 restart order 필요 |

Spark daemon, Redis, AI serving과 부가 dashboard는 기본 placement가 아니다. profile에서 serving 또는 processing 보호 workload가 공존하지 못하면 이를 먼저 제거하고, processing time separation 또는 추가 자원을 검토한다. 두 worker correctness proof 자체는 제거하지 않는다.

---

## 8. Entity / Data Dictionary

| ENT | Entity | 핵심 필드/의미 | 주요 REQ | Invariant |
|---|---|---|---|---|
| ENT-001 | Observation | provider,api,entityKey,timestamps,hash,rawRef,flags,version | 050,052,060~067 | raw ref와 source/receive time 분리 |
| ENT-002 | PredictionSnapshot | mode,route,service,target,predictedAt,ETA,source,observation | 060,064~066 | prediction-time observable |
| ENT-003 | ActualArrivalInterval | service,node,lower,upper,mid,width,rule,source IDs | 061~064 | lower<upper, interval 보존 |
| ENT-004 | ResidualEvent | prediction/actual,horizon,realized,residual L/M/U,context | 064~066 | signed error, duration 아님 |
| ENT-005 | RouteCandidate | provider,adapterVersion,coverageMode,rank,selectionPolicy,status,origin,destination,legs,rawRef,mapping/crosswalk,timeSemantics | 005,006,008,009 | provider rank≠reliability rank; mapping 전 eligible 금지 |
| ENT-006 | JourneyLeg | sequence,type,mode,nodes,planned,state | 006,021~035 | topology 순서 불변 |
| ENT-007 | TransferLeg | type,components,sources,point,uncertainty,fallback | 033~035 | WAIT 미포함 |
| ENT-008 | WaitLeg | mode,node,candidate,source,distribution,sampleUnit,dependence | 022~024,070~073 | snapshot≠iid event |
| ENT-009 | TransitRideLeg | mode,route,pair,candidate,distribution | 023,035 | BUS_SKIPPED 후 required ride 유지 |
| ENT-010 | LegDistribution | kind,semantics,n,window,quantiles,samples,fallback,confidence,coverage,validation,versions | 010,040~044 | semantics별 계산 분리 |
| ENT-011 | JourneyRequest | origin,destination,target,reliability,requestedAt | 001~004 | timezone-aware |
| ENT-012 | JourneyState | route,active,state,completed,events,stateVersion,updated | 020~025 | mutation version 증가 |
| ENT-013 | UserEvent | journey,type,time,target,idempotency,source | 022~026 | unique idempotency |
| ENT-014 | JourneySimulationRun | route,state,seed,N,versions,provenance,validation,times | 010~016,025,090 | reproducible, provenance 명시 |
| ENT-015 | JourneyResultSnapshot | target,P50,P90,onTime,connection,recommended,confidence,validation,coverage,eligibility,fallback,limitations,version | 010~016,025,080,090 | immutable version |
| ENT-016 | GeoPoint | lat,lon,label,source,role | 001,002,030~035 | role 필수 |
| ENT-017 | NodeRef | namespace,provider ID,name,mode,line,coordinate,mappingVersion | 005,006,030~035 | namespace 무시 equivalence 금지 |
| ENT-018 | RouteLeg | sequence,mode,route/line,from,to,metadata | 005,006 | topology이며 distribution 아님 |
| ENT-019 | ShareSnapshot | tokenDigest,status,expiresAt,revokedAt,snapshotPayload,resultVersion,createdAt | 080~082 | immutable payload; read-only; token 원문·exact origin 없음 |
| ENT-020 | AnonymousAccessGrant | journeyId,ownerCapabilityDigest,status,issuedAt,expiresAt,revokedAt,lastAccessAt | 007,020~025,080 | owner capability 원문 저장/로그 금지; Share 권한과 분리 |
| ENT-021 | OfflineJourneyProjection | journey/resultVersion,savedAt,target,summary,routeScope,freshnessAtSave,limitations | 095,096 | privacy-safe read-only; owner secret/exact origin/raw ID/mutation payload 없음 |
| ENT-022 | PwaRuntimeManifest | appVersion,cacheVersion,workerState,installedDisplayMode,updatedAt | 093,094,097 | product result와 분리; rollback 가능한 version |
| ENT-023 | QuotaLedger | provider,credentialAlias,kstDay,approvedLimit,approvedStatus,reservation,priority,used,retry,businessError,remaining,resetAt,projectedExhaustion,yield,configVersion | NFR-060,067~069,084 | credential raw value 없음; 모든 consumer 합산; append/audit 가능한 변경 이력 |

### 8.1 Identity rules

- Bus: route+vehicle join은 verified 범위에서 사용하되 target stop/section mapping은 별도 Gate.
- Subway: `subwayId×statnId×trainNo`, station name만 join 금지.
- Mixed route/timetable/realtime ID는 explicit versioned crosswalk, 산술 추론 금지.
- 모든 datetime timezone-aware, KST display/UTC storage 가능하나 semantics 명시.

### 8.2 Data Quality minimum flags

`SOURCE_TIME_MISSING`, `DUPLICATE_SOURCE_EVENT`, `OUT_OF_ORDER_EVENT`, `UNMATCHED_VEHICLE`, `UNMATCHED_TRAIN`, `CROSSWALK_MISSING`, `ROUTE_TIME_SEMANTICS_UNRESOLVED`, `PROVIDER_ENTITLEMENT_UNCONFIRMED`, `STALE_OBSERVATION`, `PROVIDER_ERROR`, `PROVIDER_QUOTA_EXCEEDED`, `LOW_SUPPORT`, `FALLBACK_USED`, `UNMODELED_UNCERTAINTY`, `PARTIAL_MODEL`, `COORDINATE_ROLE_UNKNOWN`, `WAIT_SOURCE_MISSING`, `VALIDATION_SCOPE_LIMITED`, `MULTILINE_STATION_NOT_SPLIT`, `TIMESTAMP_INSTRUMENTATION_INVALID`.

숫자 threshold가 필요한 flag는 profile 전 `TBD_AFTER_PROFILE`이며 임의 수치로 구현하지 않는다.

---

## 9. Non-functional Requirements

### 9.1 Performance / Correctness

| NFR | Priority | Requirement | Measurement / Gate |
|---|---|---|---|
| NFR-001 Interactive Analysis | MUST/TBD_AFTER_PROFILE | Web interactive experience; timeout에서 fake result 금지 | first vertical slice p50/p95 후 목표 고정 |
| NFR-002 Reforecast | MUST/TBD_AFTER_PROFILE | event 후 processing/결과 경험, 중복 mutation 차단 | product integration p50/p95 |
| NFR-003 Bounded Simulation | MUST/TBD_AFTER_PROFILE | 대표 fixture·Route A artifact에서 metric 수렴, fixed-seed 재현성, 응답시간·자원을 만족하는 최소 N을 benchmark로 확정; 불안정 시 limitation | versioned convergence/performance benchmark |
| NFR-020 Deterministic Regression | MUST | fixed fixture/seed에서 동일 또는 metric tolerance 내 결과 | CI regression |
| NFR-021 Timezone | MUST | timezone-aware, Asia/Seoul UI, midnight rollover | unit/integration |
| NFR-022 Schema/Version | MUST | breaking change version, rule/artifact/engine/mapping versions | contract tests |
| NFR-023 Idempotency | MUST | retry가 UserEvent/Residual/Result 중복을 만들지 않음 | duplicate request tests |

### 9.2 Freshness / Availability / Recovery

| NFR | Priority | Requirement | Measurement / Gate |
|---|---|---|---|
| NFR-010 Timestamp Integrity | MUST | requested 직전/received 직후, source time 별도 | live boundary test |
| NFR-011 Provider-specific Freshness | MUST/TBD_AFTER_PROFILE | provider cadence/lateness 기반 threshold | valid timestamp profile |
| NFR-030 Provider Failure | MUST | explicit stale/error/no-data/partial, quota business error 분리 | failure injection/API fixtures |
| NFR-031 Restart Recovery | MUST | Journey state/raw/artifact reload, unfinished mutation consistency | restart/restore smoke |
| NFR-032 Rollback | MUST | engine/artifact/rule/code version rollback과 provenance 유지 | release drill |

### 9.3 Security / Privacy

| NFR | Priority | Requirement | Acceptance |
|---|---|---|---|
| NFR-040 Secret | MUST | key가 repo/frontend/log/error/README에 없음; quota 우회 rotation 금지 | secret scan critical 0, bundle key 0 |
| NFR-041 HTTPS | MUST | deployed Web/API HTTPS, internal admin UI 제한 | route smoke/security review |
| NFR-042 CORS | MUST | explicit origin allow-list, credential+`*` 금지 | preflight tests |
| NFR-043 Log Masking | MUST | key/auth/exact origin/raw payload 반복 로그 금지 | log inspection |
| NFR-050 Data Minimization | MUST | account 없음; exact coordinate analytics 기본 저장 금지; 최소 state만 | payload/event review |
| NFR-051 Share Privacy | SHOULD/G5 | exact origin/GPS/raw ID/debug 제외, opaque token | AC-025 |
| NFR-052 Retention | MUST/TBD_AFTER_PROFILE | Journey/share TTL을 G5에서 확정, 그 전 임의 기간 금지 | security decision+expiry test |
| NFR-053 Anonymous Authorization | MUST/G5 | owner capability는 HttpOnly/Secure/적절한 SameSite channel, URL·JS·DOM·analytics 미노출; 모든 owner API server-side 검증; enumeration-safe response | AC-035,036 + security review |
| NFR-054 Analytics Privacy | MUST/G5 | raw journeyId/token/free-text location 금지; 필요 시 비가역 analytics 전용 pseudonymous key, property별 purpose/owner/retention class | payload/event/log review + AC-039 |

### 9.4 Observability / Operations

| NFR | Priority | Requirement | Required signals |
|---|---|---|---|
| NFR-060 Collector/Quota Budget | MUST | 모든 collector·user adapter가 SYS-007을 통과; credential alias×KST-day 공유 budget, reservation, retry cost, business error, projected exhaustion | last success/error,call count,reserved/used/remaining,quota reset,latency,yield/call |
| NFR-061 Data/Stream | MUST | join/dedupe/out-of-order/actual/residual와 stream health | rates,lag,state,checkpoint,backpressure |
| NFR-062 API/Product | MUST | latency/error/result eligibility/state mutation | p50/p95,error code,result state |
| NFR-063 Artifact | MUST | latest distribution/validation age/version, provenance | artifact age/version/load success |
| NFR-064 Backup/Restore | MUST | raw,canonical schema,DB if used,distribution,docs | restore smoke |
| NFR-065 Demo Preflight | MUST | Route A provider quota/health, latest eligible artifact, secret scan, rollback, PWA runtime version 확인 | release checklist; 임의 고정 시각을 SLA로 만들지 않음 |
| NFR-066 Internal QA Isolation | MUST | Route B fixture/selector/analytics는 격리된 development/QA runner에만 존재; public demo·production artifact occurrence는 release-blocking | config/build/route/event scan, AC-040 |
| NFR-067 Quota Priority/Degradation | MUST | `active Journey·Route A demo → Claim Gate corridor → evidence window → coverage → experiment` 순 예약; 임박 시 하위 예약 중단 | exhaustion forecast와 degradation transition log |
| NFR-068 Call Efficiency | MUST | bulk 우선, static/version cache, identical snapshot dedupe, cohort/window schedule, adaptive cadence, bounded retry/backoff/jitter/circuit breaker | useful unique snapshot·Actual·Residual per call, duplicate ratio |
| NFR-069 Quota Application/Alternative Source | MUST operational | 실시간 지하철은 공식 활용사례 절차를 추진하되 서울 버스가 동일 절차라고 가정하지 않고 별도 확인. 승인을 release 전제로 하지 않음. 대체 source는 license·identity·timestamp·Prediction→Actual 가능성 검증 | application status, provider별 official source review, no key rotation bypass |

수집 계획은 `DailyCalls = Σ(activeWindowSeconds / pollingIntervalSeconds × endpointCount)`로 사전 계산한다. ledger는 consumer·purpose·priority·예약량·실사용·retry·business error·unique snapshot/Actual/Residual yield를 함께 기록하며, 여러 process가 동일 credential을 별도 quota처럼 계산하지 않는다.

#### Quota Budget v1 contract

| Source | Approved-limit input | Initial status | Collector start condition | Degradation |
|---|---|---|---|---|
| Seoul realtime subway | 서울 열린데이터광장 공식 정책(2026-08-23 확인): **1,000/day per key**, station×line 쿼리 종류와 무관한 계정 단위 공유 한도(활용사례 갤러리 등록 시 무제한) | `CONFIRMED/GALLERY_NOT_REGISTERED` | KST-day ledger 관리; 2026-08-23 실사용량은 `PENDING_RECONCILIATION`(Decision Sheet 호출표 기준 성공 호출만 135+180=315건 확인, 이전 기록 225/1,000과 불일치 — raw request log 재대사 필요) | low-priority collection stop→stale/not-computed |
| Seoul bus Arrival | data.go.kr 마이페이지(2026-08-23 확인): `getArrInfoByRouteAllList` 등 4개 상세기능 각각 **1,000/day**(서비스 단위 독립) | `CONFIRMED` | 없음 — 확인 완료 | Route A active/demo 보호, evidence window 축소 |
| Seoul bus Position | data.go.kr 마이페이지(2026-08-23 확인): `getBusPosByRouteStList` 등 5개 상세기능 각각 **1,000/day**(Arrival과 별도) | `CONFIRMED` | 없음 — 확인 완료 | Route A active/demo 보호, evidence window 축소 |
| Kakao Map public transit | official first-enabled-app 1,000/day, overage 10원/건 | `API_VERIFIED/FREE_QUOTA_CONFIRMED`(2026-08-23: 9/1,000; billing 콘솔 확인 결과 이번 달 유료 호출 0건) | runtime route provider 미사용; REQ-009는 future 승격 Gate | 사용자 신규 OD route 분석 budget 0, reference evidence만 보존 |
| Kakao Map WALK | official first-enabled-app 1,000/day, overage 10원/건 | `API_VERIFIED/FREE_QUOTA_CONFIRMED`(2026-08-23: 4/1,000) | runtime WALK provider; route와 별도 counter·cache/providerVersion | 동일 provider 승인 cache 외 unavailable |
| TMAP public transit | official free trial 10/day | `KNOWN_BASE/VALIDATION_ONLY` | runtime primary 제외, golden-route 비교 예약만 | 호출 중단 |
| TMAP pedestrian | project credential limit | `API_VERIFIED/LIMIT_UNCONFIRMED` | 별도 ledger와 point provenance | Kakao silent substitution 금지 |

`UNCONFIRMED` credential은 무제한 scheduler를 시작하지 않는다. Kakao 공식 1,000/day를 프로젝트 앱 `remaining`으로 입력하려면 첫 활성화 앱 무료 배지 또는 실제 billing entitlement 증거가 필요하다. 수동 preflight reservation을 넘는 dry run을 금지하며, 승인량 변경은 product probability semantics가 아니라 collector configuration version을 변경한다.

### 9.5 Responsive / Accessibility

| NFR | Priority | Requirement | Acceptance |
|---|---|---|---|
| NFR-070 Responsive | MUST | core flow mobile/tablet/desktop, 핵심 정보 삭제 금지, overflow 0 | viewport E2E |
| NFR-071 Non-color State | MUST | state를 text/icon/copy로도 전달 | visual/accessibility test |
| NFR-072 Keyboard/Focus | MUST | form/CTA/overlay/refresh keyboard, focus restore/live region | manual+automated a11y |
| NFR-073 Reduced Motion/Reflow | MUST | zoom/reflow/reduced motion, probability animation 과장 금지 | manual test |
| NFR-074 Mobile Browser Parity | MUST | supported iOS/Android mobile browser와 standalone에서 SCR-01~05 의미·guard·CTA 동등 | real-device E2E |
| NFR-075 Installability | MUST | valid manifest/icon/start URL/display/HTTPS; install prompt가 core task를 차단하지 않음 | manifest/installability audit |
| NFR-076 Offline Privacy/Honesty | MUST | shell/static cache와 ENT-021만 offline 사용; secret/exact origin/API mutation cache 금지 | cache/storage inspection, AC-043 |
| NFR-077 Foreground Recovery | MUST | background→foreground에서 server version refetch, 완료 전 mutation lock | lifecycle/network test, AC-044 |
| NFR-078 Update Safety | MUST | worker/cache/app version 관측, active mutation 중 activation defer, rollback 가능 | update/rollback matrix, AC-045 |
| NFR-079 Device Permission/Share | MUST | geolocation은 explicit one-shot, permission denied fallback; OS share 실패 시 copy | real-device permission/share test |

### 9.6 Distributed Proof

| NFR | Priority | Requirement | Acceptance |
|---|---|---|---|
| NFR-080 Real vs Amplified | MUST for proof | replay multiplier·purpose 표시, amplified는 training support 금지 | run manifest |
| NFR-081 Worker Participation/Failure | MUST | Kafka partition input을 Flink의 2개 이상 worker task가 실제 처리하고 worker 종료 후 checkpoint/restart 또는 replay 복구 | participation/recovery evidence |
| NFR-082 Correctness | MUST | single-worker와 multi-worker의 input/output count·checksum 일치, duplicate/loss 0, keyed identity state 중복 없음 | correctness manifest |
| NFR-083 Two-node Deployment | MUST/G6 | EC2-A serving, EC2-B processing 기본 배치와 TaskManager A/B 참여; 사양 profile, public/internal port, backup/restart/rollback ADR | AC-048, deployment manifest |
| NFR-084 Quota Budget v1 | MUST/G3 | source별 approved status·reservation·forecast·degradation이 ENT-023에 있고 UNCONFIRMED는 bounded dry run만 | AC-049, quota manifest |
| NFR-085 PWA Compatibility Matrix | MUST/G4 | iOS/Android Mobile Web·standalone과 desktop secondary run에 device/OS/browser/app/cache version 기록 | AC-050, UI-AC-031 |
| NFR-086 Route A Demo/Protected E2E | MUST/G6 | Route A actual product flow manifest와 Protected E2E lane; Route B·mock replacement 금지 | AC-051,052, UI-AC-032 |
| NFR-087 Kakao WALK / Route Provider Contract | MUST for WALK, FUTURE_OPTIONAL before route Primary | `KAKAO_MAP_WALK`는 WALK point provider로 entitlement·quota·cache·providerVersion·raw evidence를 보존한다. publictraffic HTTP 200/OK evidence는 future route-provider 검토용으로 보존하되 canonical ID·time semantics Gate 전에는 Journey route support로 승격 금지 | AC-053~056, UI-AC-033~034 |
| NFR-088 Provider Provenance/Cache | MUST | provider+endpoint+adapter/crosswalk/version+request/result hash를 보존; 동일 normalized OD cache만 승인 policy로 재사용; target/reliability 변경만으로 route 재호출 금지; cross-provider cache 대체 금지 | AC-054~056, provider contract tests |

---

## 10. Acceptance Test Scenarios

| AC | Type | Scenario / Preconditions | Steps | Expected | Related |
|---|---|---|---|---|---|
| AC-001 | E2E | coverageMode에 맞는 valid input | SCR-01 입력→analyze | Minimum Release는 `ROUTE_A_ONLY + KAKAO_WALK_ONLY`로 manifest Route A와 WALK provider provenance를 반환; future `PROVIDER_SUPPORTED`는 first canonical-supported; SCR-02 eligible/not-computed, duplicate 0 | F001~003, REQ-001~010 |
| AC-002 | Product | 서울 외/route mapping fail | analyze | 0%가 아닌 unsupported/mapping copy, input edit | REQ-005,054 |
| AC-003 | Probability | critical source 없음 | real analysis | placeholder 0, eligibility NOT_COMPUTED, start disabled | REQ-010,016,055 |
| AC-004 | Route | provider candidates mixed | selection | provider order 유지한 첫 supported, reliability reorder 0 | REQ-005,006 |
| AC-005 | UI/Math | eligible result | render | P50/P90/on-time label·null·copy 분리 | REQ-011~013 |
| AC-006 | Probability | connection miss+recovery fixture | simulate | planned success와 final on-time 별도 | REQ-014 |
| AC-007 | Claim | departure 후보별 service set 변화 | calculate | 각 후보 재평가, simple shift/binary-only 없음; Gate 미통과면 unavailable | REQ-015 |
| AC-008 | Security/Product | V0 synthetic fixture | user API/UI 요청 | ENGINE_FIXTURE_ONLY, user-facing 숫자 없음 | REQ-016,055 |
| AC-009 | E2E | eligible PRE_TRIP_READY | start+refresh | ACTIVE, state 복구, 중복 start mutation 0 | REQ-020,021 |
| AC-010 | State | WAIT candidate | BOARD_CONFIRMED | WAIT complete, RIDE active, event once | REQ-022 |
| AC-011 | State | BUS_WAIT candidate | BUS_SKIPPED twice | candidate skipped, duplicate second ignored, bus ride 유지 | REQ-023 |
| AC-012 | Probability | skipped bus+next source | reforecast | next WAIT+same BUS_RIDE+downstream, resultVersion+1 | REQ-023,025 |
| AC-013 | Failure | skipped bus+no next source | reforecast | REFORECAST_UNAVAILABLE, topology retained, no earlier fake arrival | REQ-023,025 |
| AC-014 | State | planned transfer miss | rule/user event | MISSED, next candidate or unavailable, final recompute | REQ-024 |
| AC-015 | UI/State | event before/after | reforecast overlay | deterministic reason, nullable metrics safe, completed unchanged | REQ-025,026 |
| AC-016 | Data/UI | WALK/transfer endpoints | build+view evidence | role/source present, center→exit coercion 0 | REQ-030~032 |
| AC-017 | Domain | Route A/B canonicalize | inspect sequence | Transfer와 WAIT separate, FINAL_WALK before ARRIVED | REQ-006,033~035 |
| AC-018 | Product | mixed modeled/reference legs | Evidence Detail | support/fallback/freshness/limitation/validation/provenance | REQ-040~045 |
| AC-019 | Data | 20s correlated BUS snapshots | build WAIT | rows를 iid support로 세지 않음; event unit explicit | REQ-040,070,071 |
| AC-020 | Claim | SUPPORT_RULE_V1 없음 | build result | empirical confidence INSUFFICIENT, HIGH/MEDIUM/LOW auto 0 | REQ-041 |
| AC-021 | V0 | signed residual/missing inputs/seed | run regression | residual sign, no duration misuse, benchmarked N/version, UNVALIDATED | REQ-010~016,064~066 |
| AC-022 | Probability | planned miss but target recovery | simulate | independent connection/final metrics | REQ-014 |
| AC-023 | WAIT | future departure/service day | calculate | timetable/empirical source or unavailable, >=24 rollover | REQ-015,070~073 |
| AC-024 | Recovery | live refresh/back/restart | reload | server state/version 우선, mutation rollback/duplicate 0 | REQ-021,025 |
| AC-025 | Privacy | create/view/expire Share | inspect payload/DOM/events | exact origin/coordinate/raw ID/token log 0; expired variant | REQ-080,081 |
| AC-026 | Data | live HTTP+out-of-order fixture | collect/process | boundary timestamps, receive-order DQ before sort | REQ-050,067 |
| AC-027 | UX | WALK/static uncertainty | render result/share | PARTIAL/UNMODELED visible, P90 full coverage claim 0 | REQ-031~043 |
| AC-028 | Failure | FRESH→AGING→STALE→refresh | advance policy clock | live label off, last success, retry, new result on success | REQ-050,051 |
| AC-029 | Ops | quota error HTTP payload/provider outage | collect/API | business error separate, raw body/key hidden, budget/backoff signal | REQ-052, NFR-060 |
| AC-030 | Data | real/synthetic 0→1 and subway transition | build events | valid intervals/residual L/M/U | REQ-060~064 |
| AC-031 | Data | target node mismatch+receive-order reversal | build bus/out-of-order | residual diagnostic only, DQ emitted | REQ-062,067 |
| AC-032 | Data | 교대 L2/L3 rows | join/build WAIT/Actual | subwayId×statnId split, timetable source version | REQ-063,072,073 |
| AC-033 | Data/ML | positive/negative residual+horizon | build/use | predicted+signed residual, actual-derived feature 없음 | REQ-064~066 |
| AC-034 | Release | Route A final demo and trace | run corridor story | real eligible result, failed fixture/mock 0, full provenance, recorded/live 구분 | REQ-090,091 |
| AC-035 | Security | owner capability 없음·변조·다른 Journey의 capability | plan/live/evidence/start/event/share-create 호출 | 동일 not-found/recovery semantics, resource existence leak 0, mutation 0 | REQ-007,020~025,080; NFR-053 |
| AC-036 | Product/Security | 정상 owner capability + USER_FACING result | refresh/start/event/evidence | same browser 복구·mutation 성공; URL/DOM/analytics에 capability 0 | REQ-007,017,020; NFR-053,054 |
| AC-037 | Eligibility | required leg time input missing / deterministic unmodeled / confidence insufficient 각각 | analyze+render+start | missing→NOT_COMPUTED+blocked; unmodeled→USER_FACING+PARTIAL; insufficient confidence만이면 start eligible 유지 | REQ-017,020; BR-017,045 |
| AC-038 | Freshness | critical FRESH+AGING/STALE/ERROR와 non-critical ERROR 조합 | aggregate+render | BR-064 우선순위와 CTA가 결정적; last success 혼합 0; confidence/partial 보존 | REQ-056 |
| AC-039 | Share Security/Privacy | owner create, public read, token으로 owner API 시도, revoke/expire | API/payload/DOM/event/log 검사 | snapshot read만 성공; owner mutation/evidence 0; token/raw journeyId/exact origin analytics 0; revoke 후 cache resurrection 0 | REQ-080~082; NFR-051~054 |
| AC-040 | Internal QA Isolation | development/QA runner, public demo와 production build | Route B fixture 실행 후 artifact/route/event scan | 내부 run manifest 존재; 사용자 UI·public demo narrative·product analytics·production selector/route/event 0 | REQ-092; NFR-066 |
| AC-041 | Mobile Web E2E | 설치하지 않은 supported mobile browser | SCR-01→02→Start→03→event→04/05 | desktop과 동일 result/state/guard 의미, overflow·blocked CTA 오류 0 | REQ-093; NFR-070,074 |
| AC-042 | PWA Install/Standalone | HTTPS 배포, install/non-install | manifest audit→install→동일 Journey flow | valid installability; 설치 여부에 따른 기능·권한·claim 차이 0 | REQ-093,094; NFR-075 |
| AC-043 | Offline Honesty/Privacy | eligible snapshot 후 network 차단 | SCR-02/03 reload·mutation 시도·storage 검사 | OFFLINE_SNAPSHOT+savedAt; Start/Event/Share success 0; secret/exact origin/mutation payload cache 0 | REQ-095; NFR-076 |
| AC-044 | Foreground Recovery | active Journey를 background 후 source/state 변경 | foreground 복귀→sync 중 mutation 시도 | RECONNECTING, mutation 0, 최신 server state/result version 반영 | REQ-096; NFR-077 |
| AC-045 | Service Worker Update | active event/reforecast와 waiting worker | update activation/rollback/reload 반복 | mutation 손실·중복·reload loop 0; safe activation과 version 관측 | REQ-097; NFR-078 |
| AC-046 | Geolocation Permission | allow/deny/timeout/unsupported | 현재 위치 CTA 실행 후 수동 입력 | click 전 prompt 0; 허용 시 ORIGIN_POINT provenance; 모든 실패에서 수동 입력 가능 | REQ-098; BR-070; NFR-079 |
| AC-047 | Device Share | Web Share 지원/취소/실패/미지원 | Share CTA | 가능 시 OS sheet, 그 외 copy fallback; token analytics/log 0 | REQ-098; NFR-079,054 |
| AC-048 | Deployment | 실제 EC2 사양과 2-node manifest | deploy→port scan→serving/processing smoke→worker kill→rollback | public/internal boundary, 보호 workload 기동, backup/restart, TaskManager A/B 참여; 사양 미충족 시 optional process cut | NFR-083,081,082 |
| AC-049 | Quota Budget | subway/bus/Kakao/TMAP credential 상태 조합 | ledger 입력→reservation→exhaustion forecast→degradation | subway 1,000/day(계정 공유, CONFIRMED), bus Arrival/Position 각 1,000/day(서비스별 독립, CONFIRMED), Kakao WALK 1,000/day runtime budget CONFIRMED, Kakao publictraffic 1,000/day는 reference budget으로만 CONFIRMED, TMAP transit 10과 project entitlement를 구분; UNCONFIRMED 무제한 schedule 0; active Route A 우선; config version trace | NFR-060,067~069,084,087,088; ENT-023 |
| AC-050 | PWA Compatibility | iOS/Android browser·standalone, desktop secondary | SCR-01→05+offline+foreground+update+permission+share | 각 device/OS/browser/app/cache version과 pass/fail 기록; 미검증 환경 support claim 0 | NFR-074~079,085; REQ-093~098 |
| AC-051 | Route A Demo Manifest | final rehearsal input과 provider live/recorded variants | manifest 검증→SCR flow→provenance trace→rollback | route/data/engine/PWA/quota/distributed/claim/recovery field complete; Route B·mock probability 0 | REQ-090~092; NFR-065,086 |
| AC-052 | Protected E2E Scope Cut | 일정/자원 failure injection | cut trigger 적용 후 build/demo | Route A input→analysis→Start→BUS_SKIPPED→Reforecast/Unavailable→Evidence, quota, security, distributed proof 유지; Share/AI/ML/Spark/Redis polish cut 가능 | NFR-086; BR-013,042,053,065~069 |
| AC-053 | Kakao API Access Evidence | 2026-08-22 WALK/publictraffic response + 2026-08-23 동일 OD 재호출(15개 candidate 완전 일치) | sanitized raw ingest+schema parse | **PASS for access/reference** — 두 endpoint HTTP 200/OK, secret 0, request/result hash와 adapter version 기록, raw ingest 완료(`RECEIVED_HASH_VERIFIED`); WALK는 runtime point provider evidence, publictraffic은 future route-provider reference evidence | REQ-008,009; NFR-087 |
| AC-054 | Kakao Time Semantics | publictraffic total 2,651s/step sum 1,764s(887s gap, candidate 0); candidate 2는 gap 422s | raw field decomposition+contract test | **PARTIAL** — candidate 0(SUBWAY)은 경계 WALK 합(829s)과 58s 잔차(`PARTIALLY_EXPLAINED`); candidate 2(BUS_AND_SUBWAY)는 경계 WALK 합(437s)과 15s 이내 일치(`HIDDEN_WALK_STRONGLY_SUPPORTED`). 어느 쪽도 잔차를 WAIT/WALK/transfer에 임의 배분하지 않음; result eligibility 승격 0 | REQ-006,009; BR-005,072; NFR-087 |
| AC-055 | Kakao Canonical Mapping | bus/subway/mixed 3개 topology candidate(2026-08-23) | provider stop/vehicle/coordinate→서울 bus route/stop·station×line crosswalk | **REJECTED** — stop 객체는 `name`만, vehicle 객체는 `name`/`type`만 존재하고 busRouteId/stId/stationId 필드가 응답 스키마 자체에 없음(3개 candidate 전부 동일 구조). deterministic mapped candidate 0건; 이 API 응답만으로는 향후에도 통과 불가, 별도 외부 crosswalk 필요 | REQ-005,006,009; NFR-087 |
| AC-056 | WALK Provider Separation | 동일 Route A 접근 pair Kakao 295m/323s(2026-08-22, 2026-08-23 재현), TMAP 297m/245s | adapter/cache/evidence/result 검사 | **PASS** — 각 point와 provider/version 보존, 평균·cross-provider silent fallback·fabricated variance 0; Kakao point는 day-to-day 완전 재현(개인 variance 없는 deterministic point 근거 강화) | REQ-031; BR-052,072; NFR-088 |
| AC-057 | Coverage/Quota/P90 Contract | Kakao entitlement `CONFIRMED`(2026-08-23 콘솔 스크린샷: publictraffic 9/1,000, walk 4/1,000), publictraffic route-provider Gate fail(AC-055 REJECTED), P90 render | analyze→render→quota exhaustion/deployment switch | **PASS for coverage contract / HOLD for probability claim** — deployment mode는 `ROUTE_A_ONLY + KAKAO_WALK_ONLY`; publictraffic Gate fail은 future route-provider 승격만 막고 WALK-only release를 막지 않음; calibration 전 반복빈도 P90 copy 0 | REQ-008,009,012; BR-071~073; NFR-084,087,088 |

---

## 11. Claim Gates와 Evidence Dependency

| CG | Claim | Required Evidence / Validation | Current | User-facing fallback |
|---|---|---|---|---|
| CG-001 | Whole-Journey calibrated | independent Journey outcomes, V3 calibration metrics | NOT_STARTED | validationScope를 실제 단계로 표시, calibrated claim 금지 |
| CG-002 | Mature Bus Reliability | validated target-node mapping, multi-window Prediction→Actual residual, interval/support/hold-out | INSUFFICIENT; 수용 가능한 target-stop Actual/Residual 표본 미확보 | INSUFFICIENT/NOT_COMPUTED/claim 축소 |
| CG-003 | Mature Subway Reliability / S2B component | fresh-quota station×line residual/hold-out; Route B internal interoperability run | CONDITIONAL; structural interoperability만 verified | component/corridor scope 표시 |
| CG-004 | Recommended Departure AVAILABLE | Route A future subway prior+passenger-relevant bus WAIT+candidate re-evaluation+component/replay validation | HOLD | INSUFFICIENT_DATA/NOT_COMPUTED |
| CG-005 | HIGH/MEDIUM/LOW support / empirical Bus WAIT | independent event unit, down-sample/bootstrap/coverage, SUPPORT_RULE_V1 | NOT_STARTED; raw dependence 0.77 | INSUFFICIENT |
| CG-006 | Distributed performance/recovery | real volume baseline, replay manifest, multi-worker, failure, correctness, A/B | NOT_STARTED | 기술 사용 claim 축소 |
| CG-007 | ML promotion | temporal hold-out vs B0/B1/B2, pinball/coverage/calibration/low-support/ops cost | HOLD | empirical baseline 유지 |

### 11.1 Evidence guardrails

- EVD-BUS-010 11건은 traverse duration이며 residual support가 아니다.
- EVD-WAIT-001의 181 snapshots는 181 independent events가 아니다.
- EVD-WAIT-002의 약 20초 turnover는 passenger headway가 아니다.
- EVD-SCHED-002는 Route A two-snapshot static prior evidence이며 exact current/citywide guarantee가 아니다.
- EVD-VSLICE-001 numeric result는 FAILED이며 acceptance/demo에 사용하지 않는다.
- 일부 live raw는 전달 package에 없어 artifact completeness PARTIAL이다.
- 2026-08-22 Kakao WALK/publictraffic raw JSON은 2026-08-23 `docs/`에 실제로 ingest·hash 검증됐다(`RECEIVED_HASH_VERIFIED`). 같은 날 동일 OD 재호출로 후보 안정성도 확인됐다. WALK는 runtime point provider evidence로 사용할 수 있다. publictraffic의 ID mapping은 검증이 아니라 `REJECTED`로 판정됐고(payload 자체에 canonical ID 없음), 시간 의미는 candidate별 `PARTIAL`이다 — 이 두 항목은 future route-provider 승격 대상이며 WALK-only release blocker가 아니다.
- Kakao WALK 295m/323s와 기존 TMAP 297m/245s는 서로 다른 provider point estimate다. 2026-08-23 Kakao 재호출도 295m/323s로 동일해 provider point의 day-to-day 재현성은 강화됐지만, 두 값의 차이를 표본 분포로 세거나 평균하지 않는다.
- 기존 `SRC-KAKAO-001`의 Kakao Mobility 403/BLOCKED evidence와 신규 Kakao Map route endpoint 성공은 서로 다른 제품·endpoint 계약이다. 어느 한쪽으로 다른 쪽을 덮어쓰지 않는다.

---

## 12. End-to-End Traceability Matrix

| F | SCR | REQ | BR/NFR | API/SYS | ENT | AC/CG |
|---|---|---|---|---|---|---|
| F001 | SCR-01~05 | 001~004,007 | BR-001,003,004,060,070; NFR-021,053,054 | API-000~007, SYS-001 | 011,012,016,017,020 | AC-001~003,035,036,046 |
| F002 | SCR-01/02/05 | 005~006,008~009 | BR-001~005,030~032,071~074; NFR-087,088 | API-001/002/006/009, SYS-001/002/007 | 001,005~009,015,017,018,023 | AC-001,002,004,017,053~057 |
| F003 | SCR-02/04/06 | 010~017 | BR-010~024,045,050~064; NFR-001~003,020 | API-002, SYS-003 | 006~015 | AC-003~008,020~023,037,038; CG-001,004 |
| F004 | SCR-02/03 | 017,020~021 | BR-040,043~045; NFR-023,031,053 | API-003/004 | 006,012,015,020 | AC-009,024,035~037 |
| F005 | SCR-03 | 022~024 | BR-030~043; NFR-023 | API-005 | 007~009,012,013 | AC-010~014 |
| F006 | SCR-03/04 | 025~026 | BR-040~044; NFR-002,020,023 | API-005, SYS-003 | 012~015 | AC-012~015 |
| F007 | SCR-02/03/05 | 030~032 | BR-052,061,072; NFR-030,087,088 | SYS-001 | 006,010,016,017 | AC-016,017,027,056 |
| F008 | SCR-02/03/05 | 033~035 | BR-030~034,051,052 | SYS-002/003 | 007,008,010,016,017 | AC-017,027; CG-003 |
| F009 | SCR-02/05 | 040~045 | BR-012~014,050~053,061 | API-002/006 | 001~015 | AC-018~021,027; CG-001,005 |
| F010 | SCR-01/02/03 | 050~056 | BR-001,013,014,060~064; NFR-010,011,030 | API-001~006, SYS-004 | 001,005,010,015 | AC-002,003,008,028,029,038 |
| F011 | SCR-05/Data | 060~067 | BR-010,013,050; NFR-010,020,022,023 | SYS-004/005 | 001~004,010,017 | AC-021,026,030~033; CG-002,003,007 |
| F012 | SCR-03/05 | 070~073 | BR-020~024,031,050; NFR-021 | SYS-003~006 | 008,010 | AC-019,023,032; CG-004,005 |
| F013 | SCR-06 | 080~082 | BR-004; NFR-040~054 | API-007/008 | 015,019,020 | AC-025,039 |
| F014 | SCR-05/Internal QA | 090~092 | BR-050~053,062,065; NFR-020,022,063,065,066 | API-006, SYS-002/003/006 | 001~015 | AC-034,040 |
| F015 | Global | 007,080~082; NFR-040~054 | BR-004,060~062 | API all | 019,020, privacy fields | AC-025,029,034~036,039 |
| F016 | Ops | 008~009; NFR-030~069,083~088 | BR-050~053,071~074 | API-001/006/009, SYS-001/002/004~007 | 001,005,010,014,015,017,023 | AC-026,028,029,034,048,049,051~057; CG-006 |
| F017 | Internal | NFR-080~083,086 | BR-015,016,053 | SYS-003/006 | 010,014,015 | AC-021,034,048,051,052; CG-006,007 |
| F018 | Global/SCR-01~05 | 093~098 | BR-066~070; NFR-041,050,070,074~079,085,086 | API-000,004,006,007; SYS-001 | 012,015,016,019~022 | AC-041~047,050~052 |

### 12.1 Traceability completeness rules

- 모든 MUST/CLAIM_GATE REQ는 최소 하나의 AC 또는 CG를 가진다.
- 사용자 화면이 있는 REQ는 SCR과 route가 일치해야 한다.
- API/ENT가 비적용이면 `N/A — UI copy only`처럼 이유를 기록해야 하며 빈칸으로 두지 않는다.
- 계약 변경 시 관련 F/SCR/BR/NFR/API/ENT/AC를 같은 change set에서 갱신한다.

---

## 13. Development-only Decisions / TBD Register

| Item | Status | Why not fixed | Resolution artifact | Safe behavior until resolved |
|---|---|---|---|---|
| provider stale thresholds | TBD_AFTER_PROFILE | valid lateness/cadence profile 필요 | ADR+NFR-011 | state metadata 없으면 fresh 승격 금지 |
| support thresholds | CLAIM_GATE | independent unit 안정성 필요 | SUPPORT_RULE_V1 | INSUFFICIENT |
| analysis/reforecast SLO | TBD_AFTER_PROFILE | vertical slice benchmark 전 | performance ADR | processing state, fake progress 금지 |
| partition count | TBD_AFTER_PROFILE | volume/key skew 미측정 | stream ADR | arbitrary scaling claim 금지 |
| watermark/allowed lateness/state TTL/checkpoint | TBD_AFTER_PROFILE | valid timestamp/out-of-order/failure profile 필요 | Flink ADR | late data 조용히 drop 금지 |
| Journey/share TTL | G5 | privacy/operational review 필요 | Security Decision | 장기 history 금지, Share cut 가능 |
| anonymous capability expiry/revocation | G5 | threat/retention/operational review 필요 | Security Decision | owner API는 capability 필수; cross-device 복구 없음 |
| analytics retention | G5 | property 목적·법적/운영 검토 필요 | Privacy Decision | raw journeyId/token/location label 수집 금지 |
| BUS_TO_SUBWAY internal time | INSUFFICIENT_SOURCE | depth만 있고 시간 source 없음 | Evidence/PM Decision | UNMODELED/PARTIAL |
| Recommended Departure | HOLD | WAIT/residual/replay Gate 미통과 | CG-004 result | unavailable |
| exact infrastructure sizing/Redis | REVIEW/OPTIONAL | EC2 profile 미확정 | deployment ADR | core contract와 분리 |
| LightGBM/Generative AI | HOLD/OPTIONAL | baseline Gate·scope cut | CG-007/feature flag | baseline/reason code 유지 |
| offline projection retention | G5 | server retention과 별도 client privacy review 필요 | PWA Privacy Decision | savedAt 표시, secret/exact origin 저장 금지 |
| Service Worker activation policy | integration Gate | active mutation·rollback 검증 필요 | PWA ADR | mutation 중 activation defer |
| exact iOS/Android support versions | G4 | 보유 기기·배포 시점 확인 필요 | PWA Compatibility Matrix | 미검증 환경 support claim 금지 |
| 2-node process sizing | G3/G6 | EC2 사양 미확정 | Deployment ADR+AC-048 | optional process cut, correctness 유지 |
| Kakao project entitlement | `CONFIRMED`(2026-08-23) | 콘솔 스크린샷: publictraffic 9/1,000, walk 4/1,000(quota) + 이번 달 유료 호출 0건(billing) — 이 세션 실제 호출 수와 일치 | quota manifest+AC-057 | WALK runtime budget은 확정. publictraffic route-provider 승격 Gate와는 별개 |
| Kakao canonical mapping | `REJECTED`(2026-08-23 확정) | stop/vehicle 응답 스키마에 canonical ID 필드 자체가 없음 — 별도 외부 crosswalk 없이는 이 API로 해결 불가 | REQ-009/AC-055 | publictraffic route-provider 승격 보류. `ROUTE_A_ONLY + KAKAO_WALK_ONLY`에는 blocker 아님 |
| Kakao total/step 시간 포함관계 | `PARTIAL`(2026-08-23) | candidate 유형별로 다름 — BUS_AND_SUBWAY는 15s 이내 explained, SUBWAY는 58s 잔차 | REQ-009/AC-054 | publictraffic 잔차를 WAIT/WALK에 배분하지 않음; result eligibility 승격 0 |
| deployment coverage mode | G6 | Minimum Release는 approved Route A와 Kakao WALK provider에 의존. publictraffic Gate는 future-only | release manifest | `ROUTE_A_ONLY + KAKAO_WALK_ONLY` 확정 |

개발 fixture는 `SYNTHETIC_FIXTURE/ENGINE_FIXTURE_ONLY` provenance로 허용한다. Final runtime result와 같은 endpoint/환경에서 사용자-facing으로 노출하지 않는다.

---

## 14. Security / Operations Release Checklist

- [ ] repo secret scan critical 0, frontend bundle key 0, logs masked.
- [ ] HTTPS/CORS/internal admin access가 검증됐다.
- [ ] exact coordinate가 analytics와 Share에 없다.
- [ ] key×KST-day quota budget·preflight·business error 계측이 있다.
- [ ] provider outage가 fake fresh result를 만들지 않는다.
- [ ] backup/restore/restart/rollback smoke가 통과했다.
- [ ] result/artifact/rule/engine version을 rollback 후에도 추적할 수 있다.
- [ ] demo 전 eligible artifact, validation scope, Recommended HOLD/AVAILABLE, coordinate limitation을 확인했다.
- [ ] amplified replay를 actual traffic/training support로 표현하지 않는다.
- [ ] anonymous owner capability와 Share token의 권한 분리·enumeration-safe access test가 통과했다.
- [ ] criticality/eligibility/Start/freshness 조합 AC-037~038이 통과했다.
- [ ] Route B fixture/selector가 내부 QA runner 밖의 public demo·production artifact·product analytics에 없다.
- [ ] 실제 iOS/Android mobile browser와 standalone에서 AC-041~047이 통과했다.
- [ ] Service Worker cache에 secret·exact origin·mutation response가 없고 update rollback이 검증됐다.
- [ ] Quota Budget v1의 source별 승인 상태·reservation·degradation과 AC-049가 통과했다.
- [ ] 2-node Deployment ADR, port boundary, backup/restart와 AC-048이 통과했다.
- [ ] Route A Demo Run Manifest와 Protected E2E AC-051~052가 통과했다.
- [ ] Kakao WALK provider는 AC-053, AC-056, quota evidence가 통과했고 raw evidence가 저장됐다.
- [ ] Kakao publictraffic을 Primary route provider로 사용할 경우 AC-053~055와 `KAKAO_ROUTE_PROVIDER_GATE`가 통과했다.
- [ ] Minimum Release 배포는 `ROUTE_A_ONLY + KAKAO_WALK_ONLY`이며 UI/API/manifest의 coverageMode가 일치한다.
- [ ] 2-node proof를 HA·무중단·SLA로 표현하지 않는다.

---

## 15. 정본 정합성 규칙

- Service Plan의 selected-route, Route A/B 역할, probability 의미, domain boundary, claim wording을 유지한다.
- IA의 SCR-01~06, route guard, required/nullable result, CTA precondition, state priority를 REQ/API/AC로 연결한다.
- Probability/Data contracts의 value semantics, identity, timestamp, validation ladder를 보존한다.
- placeholder, residual-as-duration, BUS_SKIPPED topology 삭제, target mapping 오류, leakage, out-of-order를 acceptance로 차단한다.
- component validation과 END_TO_END calibration을 분리한다.
- Recommended Departure AVAILABLE은 HOLD이며 service candidate 재평가 Gate를 요구한다.
- evidence 없는 SLA/support/partition/watermark/TTL 숫자를 만들지 않는다.
- access/eligibility/freshness/PWA/demo 정책과 IA의 guard/CTA/runtime state를 동일 계약으로 유지한다.
- provider access/WALK/mapping/eligibility, `ROUTE_A_ONLY/KAKAO_WALK_ONLY/future PROVIDER_SUPPORTED`, Kakao quota entitlement와 IA의 scope/error copy를 동일 계약으로 유지한다.

---

## Appendix A. Claim wording guardrail

| 금지 | 허용 |
|---|---|
| `서울 전체 90% 정확` | `검증 corridor의 선택 경로 조건부 분석` |
| `P90은 90% 정확한 도착시간` | `현재 모델 도착분포의 90번째 백분위 시각` + scope |
| `버스를 못 탈 확률` | `사용자가 이번 버스에 타지 않았음을 확정` |
| `가장 안전한 출발시간` | `이 경로 기준 {p*}% 권장 출발` |
| `Kakao/TMAP WALK 분포` | `{provider} point estimate, uncertainty UNMODELED` |
| `카카오 API 성공으로 서울 전체 지원` | `Kakao WALK 접근 성공; publictraffic route-provider 승격은 canonical mapping·time semantics·coverage Gate 별도` |
| `전체 Journey calibrated` | 실제 `validationScope` 명칭 |
| `실제 서울 20x traffic` | `amplified benchmark replay` |

## Appendix B. Definition of Done

**G2 DONE**: 모든 F가 승인 IA 화면 또는 명시적 internal capability에 연결되고, 모든 MUST/CLAIM_GATE REQ가 정상·예외·API/SYS·ENT·BR/NFR·AC/CG를 가지며, 실제 evidence가 부족한 capability는 임의 숫자 없이 HOLD/INSUFFICIENT/NOT_COMPUTED/UNMODELED로 안전하게 실패한다.
