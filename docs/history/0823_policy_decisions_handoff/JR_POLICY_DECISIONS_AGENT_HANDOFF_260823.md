# Journey Reliability 핵심 정책 확정 및 문서 수정 지시서

대상 독자: VS Code에서 기획 문서를 수정하는 Codex·Claude 등 작업 Agent  
작업 성격: **기획 문서 고도화만 수행하며 제품 코드·인프라·수집기·설정 파일은 수정하지 않는다.**

## 0. 이 지시서의 권한과 작업 대상

이 문서는 다음 세 가지 제품 결정을 확정한다.

1. Journey Reliability MVP의 경로 검색 범위와 Route A의 역할
2. 이동 중 각 계획 지점 도착을 사용자가 직접 확인하는 진행 방식
3. Kakao·서울시 데이터의 이용정책을 위반하지 않는 보존·캐시·출처표시 방식

다음 파일을 처음부터 끝까지 순차적으로 읽은 뒤 수정한다.

- `SERVICE_PLAN_260823.md`
- `IA_SCREEN_SPEC_260823.md`
- `REQUIREMENTS_SPEC_260823.md`
- `DECISION_SHEET_260823.md` — evidence와 현재 미확정 사실을 확인하기 위한 참고 문서

실제 수정 대상은 앞의 핵심 기획 문서 3개다. `DECISION_SHEET_260823.md`는 이 결정의 근거·실험 범위를 확인하는 supporting document로 사용하되, 별도 지시가 없으면 수정하지 않는다.

### 작업 절대 규칙

- 단어 검색 결과 주변만 수정하지 말고 세 문서를 전체 문맥으로 읽는다.
- 세 문서 중 하나만 고쳐 다른 문서와 충돌하게 만들지 않는다.
- 코드, API 호출 스크립트, collector, Docker, AWS, 데이터베이스 migration을 작성하거나 수정하지 않는다.
- 과거판 변경 요약, `신규`, `개선`, `반영`, `v2.0 변경사항` 같은 개정 이력을 정본 본문에 추가하지 않는다.
- 현재 처음 작성된 정본처럼 제품 정책을 직접 서술한다.
- 확인되지 않은 SLA, TTL, watermark, partition 수, support threshold, cache 시간, 호출 예약량을 만들지 않는다.
- Kakao point estimate를 확률분포로 변환하지 않는다.
- 사용자 도착 확인 사건을 provider의 차량·열차 Actual이나 residual ground truth로 사용하지 않는다.
- Route A를 서울 임의 OD를 대체하는 경로로 반환하지 않는다.
- provider 장애·quota 고갈 시 입력과 관계없는 Route A로 자동 대체하지 않는다.

---

## 1. 확정 결정 A — MVP는 서울 내 임의 OD를 지원한다

### 1.1 정본 정책

Journey Reliability의 **제품 MVP**는 사용자가 서울특별시 안에서 임의의 출발지와 목적지를 입력하고, 두 지점 사이의 대중교통 구조 경로 후보를 확인할 수 있어야 한다.

확률 계산 범위와 경로 검색 범위는 동일하지 않다.

- 서울 임의 OD에 대한 **경로 후보 검색과 구조 표시**는 MVP의 필수 기능이다.
- P50, P90, `P(on_time)`, Planned Connection Success, Recommended Departure는 canonical mapping과 reliability model coverage가 충족된 후보에서만 계산한다.
- 경로 구조는 찾았지만 확률 근거가 부족하면 후보를 숨기거나 Route A로 바꾸지 않고, 구조를 표시한 뒤 확률을 `NOT_COMPUTED`와 사유로 표시한다.
- 서울 밖의 입력은 `UNSUPPORTED_GEOGRAPHY`로 처리한다.

### 1.2 Route A의 정확한 역할

Route A는 다음 두 역할만 가진다.

1. **Protected Demo Scenario**: 최종 발표와 시연에서 사용하는 검증된 대표 시나리오
2. **Contingency Minimum Deliverable**: 일정·provider·canonicalization 문제가 해결되지 않는 최악의 경우에도 반드시 작동시켜야 하는 최소 복구선

Route A는 다음을 의미하지 않는다.

- 제품 MVP의 전체 경로 검색 범위
- 서울에서 검색 가능한 유일한 경로
- 모든 임의 OD 입력에 대신 반환할 fallback route
- 외부 provider가 실패했을 때 조용히 대체되는 경로
- 서울 전체 reliability model이 검증됐다는 근거

**중요:** 최악의 경우 Route A만 작동하는 상태는 `Contingency Demo Build` 또는 `Minimum Deliverable`이지, 서울 임의 OD를 지원하는 제품 MVP가 완성된 상태가 아니다. 일정상 이 복구선을 사용하더라도 “MVP 완료”라고 claim하지 않는다.

### 1.3 Route B의 역할

Route B는 기존 정책대로 내부 개발·QA 검증 전용이다.

- `SUBWAY_TO_BUS`, BUS WAIT, `BUS_SKIPPED` 등 Route A에 없는 구조 검증에 사용한다.
- 사용자 화면, 공개 route selector, 최종 Demo narrative, product analytics에 노출하지 않는다.
- Route B가 Route A보다 더 좋은 경로라는 의미를 부여하지 않는다.

### 1.4 Minimum Release의 provider 역할

현재 확인된 provider 능력에 따라 다음 역할을 분리한다.

| 역할 | Primary | 제품 사용 범위 | 금지사항 |
|---|---|---|---|
| 장소·주소→좌표 해석 | Kakao Local 후보를 기본 선택안으로 문서화 | 서울 범위 검사와 origin/destination GeoPoint 생성 | route/WALK quota와 같은 counter로 합치지 않음 |
| 임의 OD 구조 경로 탐색 | `KAKAO_MAP_PUBLIC_TRANSIT` | discovery/presentation-only candidate source | canonical route truth, reliability rank, probability input으로 자동 승격 금지 |
| 도보 거리·시간 | `KAKAO_MAP_WALK` | ACCESS/TRANSFER/FINAL WALK point estimate | 개인 보행 분포나 Actual arrival로 해석 금지 |
| canonical mapping | 자체 canonicalization layer + 공식 서울 master/crosswalk | stop·line·direction identity 및 mapping status 생성 | name-only 결과를 exact identity로 조용히 승격 금지 |
| reliability 계산 | 검증된 canonical route/model | 현재 Route A가 protected full-flow 대상 | 임의 OD 전체 정확도·calibration claim 금지 |
| 수동 비상 진단 | TMAP | 운영자·QA의 제한된 단건 reference | 자동 runtime failover와 사용자 신규 OD 기본 provider로 사용 금지 |

Kakao publictraffic 응답에 서울시 canonical ID가 없다는 사실은 **경로 후보 탐색 불가**를 뜻하지 않는다. 구조 후보의 사용자 표시에는 사용할 수 있지만, 외부 crosswalk 없이 그 후보를 reliability 계산의 canonical truth로 승격할 수 없다는 뜻이다.

### 1.5 Coverage 필드 분리

`ROUTE_A_ONLY` 하나로 입력 범위·검색 범위·모델 범위·데모 범위를 표현하지 않는다. 다음 필드를 서로 독립적으로 사용한다.

| 필드 | Minimum Release 값 | 의미 |
|---|---|---|
| `geographyCoverage` | `SEOUL_ONLY` | 지원 지역 |
| `routeSearchCoverage` | `SEOUL_OD_DISCOVERY` | 서울 임의 OD의 구조 후보 검색 가능 |
| `routeDiscoveryProvider` | `KAKAO_MAP_PUBLIC_TRANSIT` | 구조 후보 source |
| `reliabilityCoverage` | `ROUTE_A_ONLY` | full reliability가 우선 검증된 경로 범위 |
| `validationScope` | metric/result별 실제 Gate 값 | component/corridor/E2E 검증 수준 |
| `demoScope` | `ROUTE_A` | 최종 시연 범위 |
| `walkProviderKey` | `KAKAO_MAP_WALK` | 도보 point source |

이 필드와 enum은 Service Plan, IA ViewModel, Requirements/API/ENT/AC에서 완전히 같은 이름과 의미를 사용해야 한다.

### 1.6 임의 OD 정상 결과 분기

서울 임의 OD 분석은 다음 네 결과 중 하나로 끝나야 한다.

| 결과 | 사용자 화면 | 확률 |
|---|---|---|
| 구조 후보+canonical/model coverage 충족 | 구조와 eligible reliability 표시 | Gate가 허용한 metric만 표시 |
| 구조 후보+mapping/model coverage 부족 | provider 구조 후보와 limitation 표시 | `NOT_COMPUTED`+구체적 reason |
| route discovery no result | 입력 유지, 경로 없음 안내 | 없음 |
| provider/quota failure | provider/quota 오류와 재시도 가능 여부 표시 | 없음 |

어떤 경우에도 임의 OD 입력에 Route A를 대체 반환하지 않는다. Route A는 사용자가 명시적으로 Demo preset을 선택했거나 Route A의 실제 origin/destination을 입력했을 때만 선택된다.

### 1.7 Quota 대응

Kakao publictraffic의 `사용자 신규 OD 분석 budget 0` 정책은 폐기한다. 임의 OD discovery는 MVP 필수 기능이므로 runtime 호출 경로를 가져야 한다.

다만 현재 확인된 provider quota를 무제한으로 간주하지 않는다. 문서에 다음 원칙을 반영한다.

- provider 공식 한도와 프로젝트 entitlement를 별도로 기록한다.
- normalized OD·provider·adapter version이 같은 동시 요청은 in-flight coalescing한다.
- 사용자의 중복 submit은 idempotency/dedup으로 한 번만 provider에 전달한다.
- session/user admission control과 중앙 Quota Coordinator를 사용한다.
- Route A final rehearsal과 active Journey에 필요한 호출을 낮은 우선순위 실험보다 보호한다.
- cache는 §3의 provider 정책이 허용하는 범위에서만 사용한다.
- quota가 소진되면 구조 경로 검색을 `PROVIDER_QUOTA_EXCEEDED`로 실패시키며 Route A로 바꾸지 않는다.
- 내부 budget 수치는 실제 usage profile과 provider 정책 확인 후 config로 확정하고 문서에서 임의 숫자를 만들지 않는다.

### 1.8 이 결정에 따라 제거·수정할 표현

세 문서에서 다음 의미의 표현을 찾아 제품 정책에 맞게 수정한다.

- “Minimum Release route는 Route A만 선택한다.”
- “임의 OD 입력은 가능하지만 runtime route discovery 호출은 하지 않는다.”
- “Kakao publictraffic 사용자 신규 OD budget 0.”
- “valid input이면 Route A manifest를 반환한다.”
- `ROUTE_A_ONLY`가 geography 또는 route search coverage를 뜻하는 표현
- `citywide`를 이유로 임의 OD route discovery 자체를 Scope Cut할 수 있게 쓰인 표현

Scope Cut에서는 다음을 구분한다.

- **Protected MVP Core**: 서울 임의 OD 입력·구조 후보 검색·mapping/model 부족 시 정직한 `NOT_COMPUTED`
- **Protected Demo/Recovery Floor**: Route A full E2E
- **Cuttable Expansion**: 서울 전체 reliability model coverage·calibration 확대, 다중 경로 reliability ranking

---

## 2. 확정 결정 B — 계획 지점 도착은 사용자가 직접 확인한다

### 2.1 정본 정책

Minimum Release에서는 사용자가 Journey 상의 **각 계획 지점에 실제로 도착했을 때 앱의 도착 확인 버튼을 누른다.** 이 사건이 다음 leg로 진행시키는 canonical user event다.

서비스는 Kakao WALK 예상시간의 경과, background GPS, provider ETA만으로 사용자의 지점 도착을 자동 확정하지 않는다.

### 2.2 “각 지점”의 정확한 정의

도착 확인 대상은 경로의 모든 중간 정류장이 아니라 **Journey leg의 경계를 이루는 Planned Journey Node**다.

예시: `집 → 버스 정류장 → 지하철역 → 목적지`

| 위치 | 사용자 행동 | 완료되는 구간 | 다음 상태 |
|---|---|---|---|
| 집/출발지 | `여정 시작` | 아직 없음 | ACCESS_WALK `IN_PROGRESS` |
| 버스 정류장 | `버스 정류장에 도착했어요` | ACCESS_WALK | BUS_WAIT `IN_PROGRESS` |
| 버스 탑승 | `탑승했어요` | BUS_WAIT | BUS_RIDE `IN_PROGRESS` |
| 지하철역/환승 지점 | `지하철역에 도착했어요` | BUS_RIDE 또는 inbound leg | TRANSFER 또는 SUBWAY_WAIT `IN_PROGRESS` |
| 지하철 탑승 | `탑승했어요` | SUBWAY_WAIT | SUBWAY_RIDE `IN_PROGRESS` |
| 목적지 | `목적지에 도착했어요` | FINAL_WALK 또는 마지막 inbound leg | Journey `ARRIVED` |

지하철 노선 간 환승처럼 별도의 planned transfer node가 있으면 `환승 지점에 도착했어요`를 제공한다. 사용자가 지나가는 모든 중간 정류장·역마다 버튼을 요구하지 않는다.

### 2.3 Canonical event

공통 사건은 다음과 같이 정의한다.

`NODE_ARRIVAL_CONFIRMED`

필수 field:

- `journeyId`
- `nodeId`
- `nodeRole`: `BOARDING_POINT/TRANSFER_POINT/ALIGHTING_POINT/DESTINATION`
- `eventOrigin=USER`
- `clientOccurredAt`
- `serverReceivedAt`
- `expectedStateVersion`
- `idempotencyKey`

필요한 경우 UI analytics에는 raw `journeyId`, exact coordinate, owner capability를 넣지 않고 analytics 전용 pseudonymous key와 node role만 사용한다.

### 2.4 상태 전이 invariant

`ACTIVE` Journey에는 언제나 정확히 하나의 `IN_PROGRESS` leg가 있어야 한다.

`NODE_ARRIVAL_CONFIRMED` 처리 시:

1. event의 `nodeId`가 현재 `IN_PROGRESS` leg의 planned destination인지 확인한다.
2. 이미 적용된 idempotency key면 기존 결과를 반환하고 중복 전이를 만들지 않는다.
3. 현재 inbound leg를 `COMPLETED`로 고정한다.
4. user-confirmed history와 event time을 fixed history에 추가한다.
5. 다음 planned leg를 `IN_PROGRESS`로 활성화한다.
6. 미래 구간에 영향이 있으면 reforecast를 시작하고, 필요하지 않으면 state만 갱신한다.
7. destination node라면 Journey를 `ARRIVED`로 종료하고 polling/event CTA를 중지한다.

사용자가 잘못된 node 또는 현재 state에서 허용되지 않는 도착 사건을 보내면 `EVENT_NOT_ALLOWED_IN_STATE` 또는 `TARGET_NODE_MISMATCH`로 거부한다.

### 2.5 도착 확인의 관측 의미

사용자 버튼은 실제 이동 사실을 반영하는 중요한 관측이지만, 정밀 센서 timestamp는 아니다.

- `NODE_ARRIVAL_CONFIRMED`는 **사용자가 해당 계획 지점에 도착했다고 확인한 사건**이다.
- `clientOccurredAt`과 실제 물리적 도착시각 사이에는 사용자 반응 지연이 있을 수 있다.
- 따라서 `observationSource=USER_CONFIRMATION`, `observationUncertainty=REACTION_DELAY_UNKNOWN`을 표시한다.
- 이 사건은 현재 Journey의 completed history와 Reforecast에는 사용할 수 있다.
- 별도 검증 없이 버스·지하철 provider Prediction의 Actual event나 residual calibration ground truth로 사용하지 않는다.
- `P50/P90/P(on_time)`의 model support로 세려면 별도 validation protocol을 통과해야 한다.

### 2.6 UI 정책

SCR-03에는 현재 active leg의 destination node에 맞는 단일 primary arrival CTA를 표시한다.

예시:

- `버스 정류장에 도착했어요`
- `환승 지점에 도착했어요`
- `지하철역에 도착했어요`
- `목적지에 도착했어요`

CTA 주변에는 `실제로 도착했을 때 눌러 주세요.`를 안내한다.

다음 정책을 적용한다.

- CTA는 active leg의 target node가 있을 때만 활성화한다.
- request 진행 중에는 중복 입력을 막는다.
- network failure 시 성공한 것처럼 다음 화면으로 optimistic 전환하지 않는다.
- 동일 idempotency key로 안전하게 재시도한다.
- offline에서는 `저장됨/반영됨`으로 표시하거나 성공 queue로 처리하지 않는다.
- foreground 복귀 후 server state를 먼저 동기화한다.
- 위치 권한은 도착 버튼 사용의 필수조건이 아니다.

`탑승했어요`는 WAIT candidate를 실제 탑승한 service로 고정하기 위해 유지한다. `이번 버스는 보내요`도 기존 정책대로 유지한다. 기존 `하차했어요`와 `환승 완료`는 계획 node 도착 CTA와 역할이 겹치지 않도록 정리한다.

권장 통합 방식:

- inbound RIDE가 planned transfer/alighting node에 도달한 사실은 `NODE_ARRIVAL_CONFIRMED`로 처리한다.
- 별도 `RIDE_COMPLETED` CTA는 제거하거나 같은 canonical event의 UI alias로만 사용한다.
- `환승 완료`는 별도의 이동 완료가 필요한 구조에서만 유지하되, planned transfer node 도착과 다음 WAIT 진입의 경계를 중복 처리하지 않는다.

### 2.7 Reforecast 응답 분리

도착 사건이 항상 새 확률 결과를 생성한다고 가정하지 않는다. API 응답은 다음을 분리한다.

- `stateTransitionApplied`
- `journeyState`
- `activeLegId`
- `stateVersion`
- `reforecastStatus=NOT_REQUESTED/PROCESSING/APPLIED/UNAVAILABLE/FAILED`
- nullable `newResultVersion`
- canonical `reasonCode`

정상 reason 예:

- `BOARDING_POINT_ARRIVAL_CONFIRMED`
- `TRANSFER_POINT_ARRIVAL_CONFIRMED`
- `ALIGHTING_POINT_ARRIVAL_CONFIRMED`
- `DESTINATION_ARRIVAL_CONFIRMED`

### 2.8 Acceptance 시나리오

다음 E2E를 Requirements와 IA Acceptance에 추가한다.

1. Route A Start 후 첫 ACCESS_WALK가 `IN_PROGRESS`다.
2. `버스 정류장에 도착했어요`를 누르면 ACCESS_WALK는 한 번만 완료되고 BUS_WAIT가 `IN_PROGRESS`가 된다.
3. `탑승했어요`를 누르면 WAIT가 완료되고 해당 RIDE가 `IN_PROGRESS`가 된다.
4. 지하철역 planned node 도착 버튼을 누르면 inbound RIDE가 완료되고 다음 TRANSFER/WAIT가 `IN_PROGRESS`가 된다.
5. 목적지 도착 버튼을 누르면 마지막 leg가 완료되고 Journey가 `ARRIVED`가 된다.
6. 동일 도착 event 재전송은 state/result를 다시 변경하지 않는다.
7. 잘못된 nodeId, stale stateVersion, offline 전송은 성공으로 표시되지 않는다.
8. 버튼 timestamp는 Journey history에 남지만 provider residual Actual로 자동 승격되지 않는다.

---

## 3. 확정 결정 C — 제공자 정책을 위반하지 않는 데이터 설계

### 3.1 최상위 원칙

API 호출 권한, 사용자 화면 표시 권한, cache 권한, raw 장기 보존 권한, derived data 보존 권한, Share/redistribution 권한은 서로 다른 Gate다.

`HTTP 200`, `sanitized`, `secret 제거` 중 어느 것도 장기 보존·재배포 허가를 자동으로 의미하지 않는다.

제공자별 보존 정책이 확인되지 않은 경우 다음 default-deny 원칙을 적용한다.

- runtime 호출과 현재 사용자 응답 생성은 허용된 API 목적 안에서 수행한다.
- persistent raw storage는 비활성화한다.
- cross-session cache와 redistribution은 비활성화한다.
- 확인되지 않은 데이터를 training·model support·fixture·public evidence로 사용하지 않는다.
- 상태값은 `UNVERIFIED` 또는 `NOT_RETAINED_BY_POLICY`로 남긴다.

### 3.2 Provider Policy Registry

다음 registry를 Service Plan의 데이터 lifecycle/architecture와 Requirements의 entity/NFR에 추가한다.

`ProviderPolicyRegistry`

필수 field:

- `providerKey`
- `endpointCategory`
- `termsUrl`
- `policyVersionOrReviewedAt`
- `runtimeUseStatus`
- `rawRetentionStatus`
- `derivedRetentionStatus`
- `cacheStatus`
- `redistributionStatus`
- `requiredAttribution`
- `allowedPurpose`
- `deletionOwner`
- `decisionEvidenceRef`
- `reviewOwner`

정책 상태 enum:

- `ALLOWED`
- `CONDITIONAL`
- `PROHIBITED`
- `UNVERIFIED`

`UNVERIFIED`는 persistent storage·cross-session cache·redistribution에서 default deny다.

### 3.3 Kakao 정책

Kakao Map WALK, publictraffic, Local API는 endpointCategory별로 분리한다. 하나의 Kakao 정책으로 합치지 않는다.

#### Runtime 사용

- Kakao Local: 현재 사용자의 장소·주소 검색과 GeoPoint 생성에 사용한다.
- Kakao publictraffic: 현재 사용자의 임의 OD 구조 후보 표시에 사용한다.
- Kakao WALK: 현재 Journey의 도보 거리·시간 point estimate에 사용한다.
- REST key는 backend secret store에서만 사용하고 frontend bundle, URL, analytics, Share에 포함하지 않는다.

#### Raw response 보존

공식 정책 또는 서면 확인으로 장기 보존이 허용되기 전까지:

- Kakao raw response를 MinIO/Parquet Bronze에 장기 저장하지 않는다.
- sanitized raw도 persistent fixture나 repository에 넣지 않는다.
- debug log에 raw body를 남기지 않는다.
- provider response hash의 장기 보존도 허용범위가 확인되지 않았다면 생략한다.
- Evidence에는 `rawRetentionStatus=NOT_RETAINED_BY_POLICY` 또는 `UNVERIFIED`를 표시한다.

#### Cache와 quota 절감

- 동일 요청의 in-flight coalescing과 동일 submit idempotency는 cache가 아니라 중복 호출 방지로 적용한다.
- 현재 사용자 경험을 위한 짧은 수명의 memory cache가 정책상 허용되는지 확인하기 전에는 cross-session persistent cache를 사용하지 않는다.
- cache freshness/기간 숫자는 공식 정책 확인 또는 provider 문의 결과 없이 만들지 않는다.
- 허용범위가 확정되면 `providerKey×endpointCategory×normalizedInput×adapterVersion` key와 freshness를 기록한다.
- quota 절감을 이유로 정책에서 금지한 장기 cache를 사용하지 않는다.

#### Derived result와 Share

- Kakao point와 구조 후보는 현재 Journey 결과를 제공하는 데 필요한 최소 필드만 사용한다.
- 장기 Journey snapshot에 저장할 derived field 범위는 provider policy review에서 확정한다.
- 확정 전에는 raw path, 전체 candidate payload, provider 내부 identifier를 Share에 포함하지 않는다.
- Kakao 결과를 자체 데이터처럼 재배포하거나 open dataset·training dataset으로 제공하지 않는다.
- 지도·Kakao 브랜드 표시가 필요한 UI에는 Kakao 공식 디자인·표시 가이드를 따른다.

#### Evidence와 QA fixture

- 실제 Kakao raw를 장기 보존할 수 없으면 schema를 재현한 `SYNTHETIC_CONTRACT_FIXTURE`를 자체 생성한다.
- synthetic fixture는 실제 provider output, traffic evidence, model support로 세지 않는다.
- 실제 연결 검증은 허용된 live contract test에서 수행하고 호출시각·endpoint category·HTTP/business status·adapter version·quota 상태 같은 자체 운영 metadata를 남긴다.
- 저장하지 않은 raw를 보관한 것처럼 `rawRef`나 hash를 만들지 않는다.

### 3.4 서울특별시 공공데이터 정책

서울 열린데이터광장 데이터는 데이터셋별 이용조건과 제3자 권리 여부를 확인한다. 이용이 허용된 데이터는 source/version과 함께 보존할 수 있으나, 결과를 노출하는 페이지에는 출처를 표시한다.

사용자-facing 기본 문구:

> 이 결과는 서울특별시 공공데이터를 활용해 계산되었습니다.

적용 위치:

- SCR-02 Pre-trip Result의 source/footer 영역
- SCR-03 Live Journey의 Evidence/source 진입부
- SCR-05 Evidence Detail
- SCR-06 Share Snapshot에 서울시 기반 metric이 포함된 경우

데이터 contract:

- `provider=SEOUL_OPEN_DATA`
- dataset/service name
- endpoint category
- source observation time과 receive time
- license/terms reference
- attribution requirement
- third-party rights status
- schema/collector version
- retention class와 deletion owner

서울시 API key는 raw payload, frontend, Share, public repo에 포함하지 않는다. `vehId`, `trainNo` 등 운영상 필요한 identifier도 사용자 Share에는 포함하지 않는다.

제3자에게 권리가 있는 개별 API·파일은 서울시 일반 원칙만으로 저장·재배포 가능하다고 가정하지 않고 해당 권리자의 조건을 따른다.

### 3.5 Provider별 초기 정책표

| 항목 | Kakao Local/Publictraffic/WALK | 서울 Open Data |
|---|---|---|
| Runtime request | API 목적 안에서 사용 | 승인 key·dataset 조건 안에서 사용 |
| Persistent raw | 공식 확인 전 `UNVERIFIED`, default deny | dataset terms가 허용할 때만 `ALLOWED` |
| Derived retention | 최소 Journey 결과 범위도 policy review 필요 | 허용조건·출처를 보존해 사용 |
| Cross-session cache | 공식 확인 전 default deny | freshness·dataset 조건을 확인해 결정 |
| In-flight dedup | 허용, provider 호출 전 중복 병합 | 허용, quota coordinator와 연결 |
| Fixture | synthetic contract fixture, actual evidence로 claim 금지 | 허용범위의 sanitized fixture 또는 synthetic |
| Share | raw·provider 내부 ID 제외, 허용된 최소 결과만 | raw ID 제외, 서울시 출처표시 포함 |
| Training/model support | 장기 이용권 확인 전 금지 | 실제 독립 표본·license·provenance Gate 통과 시만 |
| Attribution | Kakao 표시 가이드 확인 | `서울특별시 공공데이터` 사용 사실 필수 표시 |

### 3.6 데이터 lifecycle 수정

기존의 “모든 provider raw를 가능한 범위에서 immutable Bronze 보존”을 다음처럼 수정한다.

1. Collect 직후 `ProviderPolicyRegistry`를 조회한다.
2. `rawRetentionStatus=ALLOWED`인 source만 persistent Bronze에 저장한다.
3. `CONDITIONAL`은 조건과 목적이 일치할 때만 저장한다.
4. `UNVERIFIED/PROHIBITED`는 raw를 저장하지 않고 허용된 최소 운영 metadata만 기록한다.
5. 저장하지 않은 raw는 `NOT_RETAINED_BY_POLICY`로 provenance에 남긴다.
6. 삭제는 임의 TTL이 아니라 provider terms, 개인정보 review, 운영 필요성으로 정한 retention class에 따라 수행한다.
7. replay·QA는 policy-safe retained data 또는 명확히 표시된 synthetic fixture만 사용한다.
8. Share/analytics/training은 raw retention과 별도의 redistribution·purpose Gate를 통과해야 한다.

### 3.7 Release Gate

다음 중 하나라도 충족하지 않으면 해당 provider의 persistent data path와 Share redistribution을 활성화하지 않는다.

- endpointCategory별 terms URL과 검토일 존재
- raw/derived/cache/redistribution status 확정
- required attribution이 IA에 구현 가능한 문구·위치로 연결
- deletion owner와 lifecycle 존재
- secret/frontend/log 검사 통과
- 실제 evidence와 synthetic fixture가 명확히 분리
- `UNVERIFIED` source가 MinIO/DB/repository에 장기 저장되지 않음

---

## 4. 문서별 수정 지시

### 4.1 `SERVICE_PLAN_260823.md`

다음 상위 정책을 수정한다.

1. Executive Summary와 Minimum Release에서 MVP를 `서울 임의 OD 구조 경로 검색`으로 선언한다.
2. Route A를 `Protected Demo Scenario + Contingency Minimum Deliverable`로 정의한다.
3. Route A-only 상태는 정상 MVP 완료가 아니라 최악 상황의 복구선임을 명시한다.
4. Selected-route 정책에서 임의 OD discovery와 full reliability selected route를 분리한다.
5. coverage를 §1.5의 독립 필드로 교체한다.
6. Kakao publictraffic을 discovery-only runtime provider로 배치하고 신규 OD budget 0을 제거한다.
7. Scope Cut에서 임의 OD 구조 검색은 보호하고 citywide reliability model 확대만 cuttable로 둔다.
8. Main Journey에 계획 node별 사용자 도착 확인을 포함한다.
9. 자동 ACCESS_WALK 완료를 제거한다.
10. data lifecycle을 Provider Policy Registry와 default-deny 보존정책으로 수정한다.
11. Result/Evidence/Share의 서울시 출처표시 원칙을 추가한다.
12. QA/Release Gate와 Final Demo narrative에 Route A의 정확한 역할을 반영한다.

서비스 정의 권장문:

> Journey Reliability는 서울 안의 임의 출발지와 목적지에 대해 대중교통 구조 경로를 탐색하고, 검증된 데이터 범위에서는 목표시각 정시 도착 가능성과 불확실성을 제공하는 mobile-first PWA다. Route A는 최종 시연과 full reliability 검증을 위한 protected scenario이며, 최악의 일정 위험에서도 보존해야 하는 최소 구현선이지 서비스의 전체 검색 범위가 아니다.

### 4.2 `IA_SCREEN_SPEC_260823.md`

다음 UI 계약을 수정한다.

1. SCR-01은 서울 임의 OD 입력을 실제 provider route discovery로 연결한다.
2. SCR-02에 `구조 후보만 표시+확률 NOT_COMPUTED` variant를 완성한다.
3. Route A preset은 별도 명시적 demo shortcut이며 임의 입력의 자동 fallback이 아니다.
4. SCR-03에 planned node role별 도착 CTA를 추가한다.
5. ACCESS_WALK 자동 전이를 제거한다.
6. `하차했어요`·`환승 완료`와 `NODE_ARRIVAL_CONFIRMED`의 중복을 정리한다.
7. network/offline/idempotency/stale stateVersion UX를 정의한다.
8. 사용자 도착 확인을 provider Actual로 표현하지 않는 copy와 Evidence 표시를 추가한다.
9. Result/Evidence/Share에 서울시 출처표시 위치를 명시한다.
10. Kakao raw·내부 ID·secret이 화면, analytics, Share에 포함되지 않게 한다.

### 4.3 `REQUIREMENTS_SPEC_260823.md`

REQ/BR/ST/API/ENT/NFR/AC를 같은 change set에서 수정한다.

필수 변경:

- 임의 OD discovery를 실제 runtime provider와 quota coordinator에 연결
- Route A를 MVP coverage가 아닌 demo/recovery scope로 재정의
- coverage field와 enum을 §1.5로 통일
- API-001이 임의 OD candidate를 반환하도록 수정
- API-002가 candidate별 mapping/model eligibility를 처리하도록 수정
- `NODE_ARRIVAL_CONFIRMED` requirement와 state transition 추가
- `JourneyEvent.eventOrigin`, nodeRole, client/server time, idempotency 추가
- ACTIVE Journey의 단일 `IN_PROGRESS` leg invariant 추가
- 정상 도착 event response와 optional Reforecast 분리
- Provider Policy Registry entity/system interface 추가
- provider policy default-deny NFR과 release AC 추가
- 서울시 attribution NFR/UI acceptance 추가
- Kakao persistent raw·cache·redistribution이 `UNVERIFIED`일 때 비활성인지 검사
- arbitrary OD에 Route A silent substitution이 0건인지 Acceptance로 검증

기존 ID를 재사용할 수 있으면 의미를 보존하며 확장한다. 새 ID가 필요하면 문서의 수량 선언, Feature/REQ/BR/ST/API/ENT/NFR/AC count, Traceability Matrix와 Definition of Done을 함께 갱신한다.

---

## 5. 필수 End-to-End Acceptance

### E2E-A — 서울 임의 OD, 구조 후보만 가능한 경우

1. 사용자가 Route A와 다른 서울 origin/destination을 입력한다.
2. Location provider가 GeoPoint를 반환한다.
3. Kakao publictraffic이 구조 후보를 반환한다.
4. canonical mapping이 `PARTIAL`이다.
5. SCR-02는 후보 구조를 표시한다.
6. probability card는 `NOT_COMPUTED`와 mapping/model limitation을 표시한다.
7. Route A가 대신 반환되지 않는다.

### E2E-B — Route A 정상 시연

1. 사용자가 Route A preset 또는 실제 Route A OD를 선택한다.
2. 분석 결과와 현재 허용된 metric을 확인한다.
3. Journey를 시작한다.
4. 버스 정류장 도착 버튼을 누른다.
5. 버스 탑승을 확인한다.
6. 지하철역/환승 지점 도착 버튼을 누른다.
7. 필요한 탑승 확인을 수행한다.
8. 목적지 도착 버튼을 누른다.
9. Journey가 `ARRIVED`로 종료된다.
10. 각 event는 한 번만 적용되고 completed history가 되돌아가지 않는다.

### E2E-C — Provider quota failure

1. 임의 OD route discovery에서 provider quota error가 발생한다.
2. 입력은 유지된다.
3. `PROVIDER_QUOTA_EXCEEDED`와 재시도 가능 여부를 표시한다.
4. Route A로 자동 전환하지 않는다.
5. 실제 Route A demo preset은 별도 보호 경로로만 실행할 수 있다.

### E2E-D — Policy-safe data path

1. Kakao raw retention이 `UNVERIFIED`다.
2. runtime 결과는 사용자에게 표시된다.
3. raw response가 MinIO/DB/repository/log에 남지 않는다.
4. provenance에는 `NOT_RETAINED_BY_POLICY`가 남는다.
5. QA에는 synthetic contract fixture만 사용되고 actual evidence로 claim하지 않는다.
6. 서울시 데이터 기반 결과 화면에는 필수 출처표시가 보인다.

---

## 6. 최종 자체 검수 체크리스트

작업 Agent는 완료 전에 세 문서를 다시 처음부터 끝까지 읽고 다음을 검사한다.

- [ ] 서울 임의 OD route discovery가 MVP MUST로 세 문서에서 동일하다.
- [ ] Route A는 demo scenario와 contingency floor이며 MVP 전체 범위가 아니다.
- [ ] Route A-only contingency build를 MVP 완료라고 표현하지 않는다.
- [ ] 임의 OD에 Route A를 silent fallback하는 경로가 없다.
- [ ] Kakao publictraffic runtime 신규 OD budget이 0으로 남아 있지 않다.
- [ ] route search, reliability coverage, validation, demo scope가 별도 필드다.
- [ ] planned journey node마다 사용자 도착 CTA가 있다.
- [ ] ACCESS_WALK와 다른 leg가 시간 경과만으로 자동 완료되지 않는다.
- [ ] ACTIVE Journey에 정확히 하나의 `IN_PROGRESS` leg가 있다.
- [ ] 사용자 도착 확인을 provider Actual/residual ground truth로 쓰지 않는다.
- [ ] 정상 event와 Reforecast 결과가 분리되어 있다.
- [ ] Kakao raw/cache/derived/redistribution 정책이 endpoint별로 구분된다.
- [ ] `UNVERIFIED` provider 데이터는 persistent storage에서 default deny다.
- [ ] 서울시 데이터 결과 화면과 Share에 필요한 출처표시가 있다.
- [ ] provider policy 때문에 raw를 보존하지 않은 상태를 결함처럼 숨기지 않는다.
- [ ] 새로운 임의 TTL·SLA·quota budget·support threshold가 없다.
- [ ] Route B와 TMAP의 기존 제한된 역할이 유지된다.
- [ ] P50/P90/P(on_time), Recommended Departure, BUS_SKIPPED, component/E2E validation 정책이 훼손되지 않았다.
- [ ] REQ/BR/ST/API/ENT/NFR/AC 수량과 traceability가 실제 문서와 일치한다.
- [ ] 변경 요약이나 과거판 비교가 아니라 현재형 정본으로 읽힌다.

## 7. 완료 산출물

수정 Agent는 다음만 산출한다.

1. 수정된 `SERVICE_PLAN_260823.md`
2. 수정된 `IA_SCREEN_SPEC_260823.md`
3. 수정된 `REQUIREMENTS_SPEC_260823.md`
4. 별도 짧은 검수 보고서: 수정한 정책, 해소한 충돌, 남은 실제 미정 항목만 기록

기획 문서 외 파일은 변경하지 않는다. 실제 개발, API 재실험, provider 호출, 배포는 수행하지 않는다.
