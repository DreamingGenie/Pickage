# Journey Reliability 최종 기획 문서 세트 전문가 검토 보고서

- 검토 기준일: 2026-08-23
- 검토 대상: `SERVICE_PLAN_260823.md`, `IA_SCREEN_SPEC_260823.md`, `REQUIREMENTS_SPEC_260823.md`, `DECISION_SHEET_260823.md`
- 판정 범위: 제품 정책, 사용자 여정, 상태 모델, 확률·데이터 계약, API·ERD·아키텍처, 운영·보안, Evidence/Claim, QA·Release Gate, 문서 간 추적성
- 산출물 성격: 원문을 수정하지 않은 독립 검토 보고서

## 1. Executive Verdict

이 문서 세트는 학생 프로젝트 수준을 분명히 넘어선다. 확률의 의미를 통제하고, 불확실성과 데이터 부족을 숨기지 않으며, 화면·요구사항·API·상태·QA를 상당한 밀도로 연결했다. 특히 `P90 ≠ 90% 정확도`, TMAP 점추정치에 임의 분포를 부여하지 않음, `BUS_SKIPPED`를 개인 탑승 실패 확률로 해석하지 않음, Bus WAIT snapshot의 dependence, `station×line` 정체성, component validation과 end-to-end calibration의 분리, 좌표 provenance, selected structural route 조건부 Recommended Departure 같은 핵심 가드레일은 일관되게 살아 있다.

그러나 현재 상태를 “구현 동결 가능한 최종 정본”으로 판정할 수는 없다. 가장 큰 이유는 문장 완성도가 아니라 계약의 공백이다.

1. 정상 이동 중 leg가 다음 leg로 진행하는 상태 전이가 완결되지 않았다.
2. 서울 전역 임의 출발·도착 서비스 범위와 Route A 데모·검증 범위가 하나의 `ROUTE_A_ONLY` 정책으로 혼합되어 있다.
3. 확률 수치의 사용자 노출 자격이 한 개의 전역 gate로 뭉쳐 있어, 미성숙한 구성요소를 포함한 P90·P(on_time)이 과도하게 신뢰될 수 있다.
4. 2026-08-23 지하철 호출량 산술이 문서 내부에서 맞지 않는다.

따라서 최종 판정은 다음과 같다.

> **조건부 부적합 — Freeze 금지.** 4개 Blocker를 먼저 닫은 뒤, Major 항목 중 보안·쿼터·API/ERD 계약을 정리하면 구현 기준선으로 승격할 수 있다.

이 판정은 과거 실험만으로 내린 것이 아니다. 260823 문서와 그 안에 기록된 로컬 실험 결과를 우선 사용했다. 다만 현재 검토 묶음에 원본 artifact가 없는 260823 실험은 “거짓”으로 보지 않고, **문서상 확인됨 / 독립 재검증 불가**로 별도 분류했다.

## 2. 검토 방법과 Evidence 우선순위

### 2.1 수행 방식

단어 검색으로 특정 표현 주변만 본 것이 아니라 다음 순서로 검토했다.

1. 네 문서를 처음부터 끝까지 순차 독해했다.
2. 각 문서의 선언을 사용자 행동, 상태 전이, 데이터 생성, API, 저장, 화면 표현, QA 판정까지 정방향으로 추적했다.
3. 주요 AC와 데모 장면에서 출발해 필요한 요구사항·정책·Evidence가 실제로 존재하는지 역방향으로 추적했다.
4. 정상 흐름, 버스 미탑승, 환승 실패, 데이터 부족, provider quota 소진, 오프라인 복귀, Share 열람, 분산 처리 증명 시나리오를 문서 계약만으로 실행해 보았다.
5. 수치·provider 기능·quota·응답 schema·보관 조건은 최신 공식 문서와 대조했다.
6. 첨부된 Kakao JSON은 필드 구조와 합계 관계를 직접 점검했다.

### 2.2 Evidence 계층

| 우선순위 | 근거 | 이번 검토의 사용 방식 |
|---:|---|---|
| 1 | 260823 원문과 260823 로컬 실험 기록 | 현재 결정과 최신 사실의 1차 기준 |
| 2 | 함께 첨부된 raw/sanitized JSON·스크린샷 | 직접 재현 가능한 범위의 검증 |
| 3 | provider 공식 문서·약관 | quota, schema, 과금, 보관 조건 검증 |
| 4 | 이전 ZIP의 Phase 1/2 Evidence와 supporting contract | 역사적 배경과 회귀 여부 확인에만 사용 |

이전 Evidence와 현재 로컬 기록이 다르면 즉시 한쪽을 폐기하지 않았다. 수집기 버전, 호출 시각, console snapshot 시각, endpoint별 counter가 달랐을 가능성을 먼저 검토했다. 그 차이를 설명할 provenance가 없을 때만 문서 결함으로 판정했다.

### 2.3 검토 범위의 수량 확인

문서가 선언한 식별자 수는 실제와 일치한다.

| 항목 | 실제 수 |
|---|---:|
| Feature `F-*` | 18 |
| Requirement `REQ-*` | 67 |
| Business Rule `BR-*` | 48 |
| State `ST-*` | 22 |
| External API `API-*` | 10 |
| Internal/System API `SYS-*` | 7 |
| Entity `ENT-*` | 23 |
| NFR | 50 |
| Acceptance Criteria `AC-*` | 57 |
| Claim Gate `CG-*` | 7 |
| UI Acceptance Criteria `UI-AC-*` | 35 |

이는 단순 분량이 아니라 추적성 관리가 실제로 수행되었다는 강점이다.

## 3. 종합 Scorecard

점수는 문서의 절대 품질이 아니라 **현재 상태로 개발·QA를 동결할 수 있는가**에 초점을 둔 상대 평가다.

| 평가 축 | 판정 | 핵심 근거 |
|---|---|---|
| 서비스 문제·가치 정의 | 우수 | “가장 빠른 길”보다 도착 신뢰성과 행동 결정을 중심에 둠 |
| 확률·Claim 정직성 | 우수하나 gate 보완 필요 | 의미 가드레일은 강하지만 사용자 노출 eligibility가 너무 거침 |
| IA·상태 표현 | 양호 | partial/unavailable/offline/share를 구체화했으나 정상 leg 진행 누락 |
| 요구사항 추적성 | 매우 우수 | Feature–REQ–BR–AC 연결과 규모 정합성이 높음 |
| Evidence 해석 | 대체로 우수 | 과대 일반화를 억제하나 quota 산술과 일부 residual 표현 불일치 |
| API·데이터 계약 | 보완 필요 | location provider, idempotency, internal event, ERD cardinality 공백 |
| 운영·quota 방어 | 보완 필요 | 중앙 quota 정책은 있으나 공개 서비스 abuse/admission control 부족 |
| 보안·개인정보 | 보완 필요 | capability 분리는 좋으나 CSRF, URL token, log/referrer 통제가 부족 |
| 분산 처리 증명 | 양호 | HA와 구분한 proof 의도는 명확; checksum 범위와 실제 capacity는 미정 |
| Release 준비도 | 미달 | Blocker 4건과 핵심 정상 시나리오 미완결 |

## 4. 잘된 점 — 유지해야 할 설계 자산

### 4.1 제품 관점

- 서비스가 경로 탐색기가 아니라 “선택한 이동 구조의 도착 신뢰도를 설명하고 다음 행동을 돕는 서비스”로 정의되어 있다.
- Route A와 Route B의 역할이 혼합되지 않는다. Route A는 실제 사용자 흐름, Route B는 개발·검증용이다.
- Recommended Departure를 만능 최적화 값이 아니라 selected structural route와 service candidate 재평가를 전제로 한 조건부 권고로 제한한다.
- pre-trip과 in-trip/reforecast의 목적을 분리하고, 단순 화면 갱신과 사용자의 관측 이벤트를 구분하려는 방향이 좋다.
- 데이터 부족·partial·unsupported를 성공처럼 꾸미지 않고 사용자에게 이유와 다음 행동을 주도록 설계했다.

### 4.2 확률·데이터 관점

- P50, P90, P(on_time)의 뜻을 서로 다른 질문으로 분리했다.
- point estimate를 확률분포로 둔갑시키지 않는다.
- `Prediction / Actual / Residual`을 분리하고 observation uncertainty를 인정한다.
- Bus WAIT snapshot의 표본 간 dependence를 반영하며, 개별 row 수를 독립 표본 수처럼 해석하지 않는다.
- `station×line` identity, 좌표계와 좌표 source/provenance를 명시한다.
- component validation과 end-to-end Journey calibration을 구분한다.
- Bus residual maturity가 낮다는 사실을 숨기지 않고 validation scope에 남긴다.

### 4.3 UX·운영 관점

- 오프라인, foreground 복귀, stale 상태, provider failure, 재시도, share read-only 경계가 비교적 정교하다.
- owner capability와 share capability를 분리해 익명 사용에서도 수정 권한과 열람 권한을 같은 토큰으로 쓰지 않는다.
- 사용자에게 backend 내부 코드를 그대로 보여주지 않고, 원인·영향·가능한 다음 행동으로 번역하려는 원칙이 있다.
- 분산 처리를 단순 기술 이름 나열이 아니라 partition, replay, deterministic checksum 같은 증명 대상으로 잡았다.
- 범위를 줄이는 원칙과 Route B 격리, non-goal이 비교적 명확하다.

## 5. Blocker — 문서 동결 전에 반드시 해결할 항목

### B-01. 정상 In-trip 상태 전이가 완결되지 않음

**관찰**

문서는 `BOARD_CONFIRMED`, `BUS_SKIPPED`, `TRANSFER_MISSED`, FINAL_WALK 완료를 정의한다. 반면 다음 정상 사건이 계약되어 있지 않다.

- ACCESS_WALK 완료 후 BUS_WAIT 또는 SUBWAY_WAIT로 이동
- BUS_RIDE/SUBWAY_RIDE의 정상 하차와 다음 TRANSFER/WAIT 진입
- 정상 TRANSFER 완료
- source update가 leg 상태에 미치는 내부 이벤트 계약
- 데이터 부족으로 `UNAVAILABLE`이 된 뒤 다음 service candidate가 관측되었을 때의 회복
- 사용자가 여정을 중단하는 `ABORTED`의 UI CTA/API/허용 상태/AC

**영향**

문서만 구현하면 Route A의 시작부터 도착까지 정상적으로 진행할 수 없다. 특히 보호해야 할 E2E는 ACCESS_WALK에서 시작하지만 데모 핵심은 BUS_WAIT 이후 사건으로 점프한다. 오류 흐름이 정상 흐름보다 더 구체적인 역전 상태다.

**필수 수정**

1. leg type별 `ENTERED / COMPLETED / SKIPPED / MISSED / UNAVAILABLE / RECOVERED` 허용 사건을 하나의 canonical transition table로 만든다.
2. 사용자 입력 사건과 provider/source 사건을 분리한다.
3. 각 전이에 대해 API 또는 internal event owner, idempotency, timestamp, 다음 상태, reforecast 조건을 정의한다.
4. `ABORTED`를 유지한다면 owner UI와 mutation API를 추가하고, 아니면 MR 상태 집합에서 제거한다.
5. 정상 Route A 한 건을 Start부터 Arrived까지 UI–API–state–entity–AC로 완주시키는 보호 시나리오를 추가한다.

### B-02. 서울 전역 임의 경로 서비스와 Route A 데모·검증 범위가 분리되지 않음

**확정된 제품 의도**

- 사용자는 서울 안에서 임의의 출발지와 도착지를 검색할 수 있어야 한다.
- 서비스는 해당 OD의 대중교통 구조 경로 후보를 생성해야 한다.
- Route A는 서비스가 지원하는 유일한 경로가 아니라 최종 시연 및 우선 검증에 사용하는 대표 경로다.
- Route B는 개발 중 비교·회귀 검증용이며 사용자 데모에는 노출하지 않는다.

**관찰**

IA의 임의 위치 검색은 위 제품 의도와 맞다. 문제는 Service Plan과 Requirements의 `ROUTE_A_ONLY`가 제품 coverage, 모델 coverage, validation scope, demo scope 중 무엇을 뜻하는지 분리하지 않는다는 점이다. 현재 문구대로면 구현자는 서울 전역 경로 생성이 필요한지, Route A preset만 허용해야 하는지 서로 다르게 해석할 수 있다.

또한 Kakao publictraffic은 임의 OD에 후보를 반환하지만 현재 payload만으로 canonical stop/line ID를 직접 제공하지 않는다. 따라서 “임의 경로 후보 생성”과 “Journey Reliability 계산에 필요한 canonical transit identity 확보”는 별도의 문제다.

**영향**

이 구분이 없으면 한 팀은 Route A만 구현하고, 다른 팀은 Kakao 후보를 그대로 신뢰하며, 또 다른 팀은 임의 OD를 받아 놓고 대부분 `UNSUPPORTED`로 반환할 수 있다. 어느 경우도 확정된 제품 의도와 일치하지 않는다.

**필수 수정**

coverage를 다음 다섯 축으로 분리한다.

| 축 | Minimum Release 정책 |
|---|---|
| `geographyCoverage` | 서울특별시 안의 임의 origin/destination |
| `routeSearchCoverage` | 서울 내 임의 OD의 구조 경로 후보 생성 |
| `canonicalMappingCoverage` | 후보의 stop·line·direction을 공식 master와 충분히 식별한 범위 |
| `reliabilityModelCoverage` | canonical mapping과 구성요소 Evidence가 충족된 leg/route만 확률 계산 |
| `validationAndDemoScope` | Route A 우선 검증·최종 시연, Route B 내부 검증 |

구현 계약은 다음 흐름을 가져야 한다.

1. 위치 검색과 현재 위치를 서울 범위 안에서 실제 좌표로 해석한다.
2. route discovery provider로 임의 OD의 후보를 얻는다.
3. 후보의 정류장명·역명·노선명·순서·경로 geometry를 공식 정류장·노선 master와 대조하는 canonicalization layer를 둔다.
4. 각 후보에 `EXACT / UNAMBIGUOUS / PARTIAL / FAILED` 같은 mapping status와 provenance를 부여한다.
5. 필요한 leg가 정책상 충분히 식별된 후보에만 Journey Reliability 계산을 수행한다.
6. mapping이나 모델 coverage가 부족하면 경로 후보 자체는 보여 주되, 확률을 만들지 않고 `PARTIAL` 또는 `NOT_COMPUTED` 이유를 명시한다.
7. Route A는 이 전체 흐름이 end-to-end로 검증된 protected demo fixture로 관리한다.

따라서 Kakao publictraffic에 대한 기존 `REJECTED`도 역할별로 고쳐 읽어야 한다. **canonical route truth의 단독 source로는 기각**이지만, 임의 OD의 **route discovery source로 사용할 가능성까지 기각된 것은 아니다**. 현 payload의 ID 한계를 보완할 canonicalization 계약이나 대체 route provider를 확정하는 것이 이 Blocker의 종료 조건이다.

### B-03. 확률 결과의 사용자 노출 자격이 지나치게 단일화됨

**관찰**

현재 `resultEligibility`는 계약이 완성되면 `USER_FACING`으로 갈 수 있는 전역 gate에 가깝다. 그러나 Journey는 서로 성숙도가 다른 BUS, SUBWAY, WALK, TRANSFER, WAIT를 포함한다. 일부 leg가 deterministic reference이거나 주요 불확실성이 미모델링이어도 P50/P90/P(on_time), Share, Start가 함께 허용될 수 있다. `COMPONENT_ONLY`나 `INSUFFICIENT`가 경고 문구로만 투영되면 사용자가 숫자를 의사결정 가능한 확률로 받아들일 위험이 있다.

**영향**

문서의 claim guardrail은 강하지만 실제 화면은 그보다 강한 인상을 줄 수 있다. Journey Reliability의 핵심 가치가 바로 확률 신뢰성이므로 이는 일반 부가 기능의 표시 오류보다 심각하다.

**필수 수정**

전역 gate를 다음과 같이 per-metric claim eligibility로 분해한다.

| 자격 | 허용 표현 |
|---|---|
| `STRUCTURE_ONLY` | 경로 구조·reference time만 표시, 확률 미표시 |
| `DISTRIBUTION_AVAILABLE` | P50/P90을 모델 출력으로 표시, calibration claim 금지 |
| `PROBABILITY_AVAILABLE` | P(on_time) 표시 가능, observation/coverage 경고 필수 |
| `CALIBRATED_CLAIM` | 정해진 validation scope 안에서만 신뢰도 claim 가능 |

- P50, P90, P(on_time), Recommended Departure를 각각 판정한다.
- 어떤 필수 leg가 point reference인지, unmodeled인지, fallback인지 결과 payload에 노출한다.
- V3가 없으면 “실험 모델 출력” 또는 demo/replay 범위로 정직하게 위치시킨다.
- 계약 완성도와 통계적 claim 가능성을 같은 `USER_FACING` 값으로 합치지 않는다.
- 최종 데모도 `D0 계약/상태`, `D1 component/replay`, `D2 calibrated`처럼 gate에 따라 narrative를 달리한다.

### B-04. 지하철 quota 사용량 산술이 맞지 않음

**관찰**

Decision Sheet에는 지하철 도착정보 성공 호출 `45×3=135`, 위치정보 성공 호출 `90×2=180`이 기록되어 있다. 성공 호출만 합쳐도 315이다. 같은 표의 낭비 호출 45와 90까지 실제 provider 요청이었다면 합계는 450이다. 그런데 Service Plan과 Requirements는 2026-08-23 사용량을 `225/1,000`으로 기록한다.

**영향**

이 수치는 provider 선택, collector 주기, 실험 예산, demo 예약을 결정하는 핵심 운영 근거다. 산술이 맞지 않으면 이후 quota budget과 release gate 전체가 흔들린다.

**필수 수정**

1. provider console 최종 snapshot 시각을 기록한다.
2. 각 collector 실행의 시작·종료 시각, 실제 HTTP 요청 수, 성공 수, business error 수를 분리한다.
3. console snapshot 이후 호출이 있었는지 표시한다.
4. endpoint별 counter가 독립인지, service 단위인지 console 화면과 공식 문서로 구분한다.
5. 어느 숫자도 추정으로 선택하지 말고 원장과 raw request log를 맞춘 뒤 네 문서에 하나의 값만 반영한다.

현재 첨부된 quota 스크린샷은 8월 22일 Kakao WALK와 publictraffic 각각 `1/1,000`을 보여 준다. 8월 23일 지하철 수치를 직접 증명하는 artifact는 이번 검토 묶음에는 없으므로, 현재 상태는 `DOCUMENTED_BY_LOCAL_RUN / NOT_IN_REVIEW_PACK`이다.

## 6. Major — Blocker 이후 우선 정리할 항목

### M-01. 위치·지오코딩 provider 계약이 비어 있음

`API-000`은 위치 검색을 추상화하지만 실제 provider, quota, business error, cache, provenance, 이용 조건이 정해지지 않았다. 서울 전역 임의 OD가 확정된 제품 범위이므로 위치 검색 provider는 MR 필수 구성요소다. Kakao 공식 REST API는 키워드 장소 검색과 좌표→행정구역 변환에 각각 일 100,000건 기본 quota를 제시한다. Kakao를 선택한다면 WALK/publictraffic와 분리된 quota counter와 provider key를 계약해야 한다.

위치 검색 API와 구조 경로 API도 분리해야 한다. 위치가 해석됐다고 해서 canonical transit route가 생성된 것은 아니다. route discovery adapter와 canonicalization 결과 schema를 별도 API/System Contract로 추가해야 한다.

현재 위치 좌표와 검색어를 GET query에 실으면 브라우저 기록, reverse proxy access log, 관측 도구에 남기 쉽다. 민감도는 낮더라도 이동 맥락 데이터이므로 POST body 사용 또는 URL/log redaction 정책이 필요하다.

### M-02. 공개 서비스의 quota abuse와 admission control이 부족함

중앙 quota coordinator와 reserved budget은 좋은 출발점이다. 하지만 익명 사용자가 `/locations/search`, `/route-candidates`, `/analyze`를 반복해 scarce provider quota를 소진하는 것을 막는 정책이 없다.

숫자를 지금 만들 필요는 없지만 다음 메커니즘은 계약해야 한다.

- client/session 단위 admission control
- 동일 요청 deduplication과 in-flight coalescing
- provider별 cache와 freshness 정책
- concurrency cap과 circuit breaker
- quota-exhausted 응답과 retry 가능 시점의 사용자 표현
- demo/validation 전용 예약 예산
- 운영 profile별 threshold는 설정값으로 분리하고 실측 후 확정

### M-03. Kakao 초과 과금 표현이 자동 과금처럼 읽힘

공식 문서는 WALK와 대중교통의 기본 quota를 각각 일 1,000건, 초과 단가를 10원/건으로 제시한다. 다만 quota 초과 사용은 Bizwallet 연결과 유료 API 사용 설정이 선행되어야 하며, 설정하지 않으면 quota 소진 후 429가 발생한다. 따라서 문서의 “1,000/day, 초과 10원/건”은 현재 배포 profile의 유료 사용 ON/OFF와 함께 써야 한다. 과금 이력이 0원이라는 사실은 초과 호출이 자동 허용된다는 증거가 아니다.

### M-04. 260823 로컬 Evidence의 auditability가 부족함

Decision Sheet는 8월 23일 raw 결과와 console 수치를 구체적으로 설명하지만 파일 경로, 실행 manifest, artifact hash, screenshot hash가 없다. “원본 이미지 artifact를 저장하지 않는다”는 방침은 재현성과 충돌한다.

민감정보를 제거한 artifact에 다음을 붙여야 한다.

- `experiment_id`, collector version/commit, executed_at
- endpoint와 sanitized request fingerprint
- HTTP count / provider business code count
- raw 또는 sanitized payload hash
- console screenshot hash와 captured_at
- 문서가 참조하는 artifact 상대 경로

이번 묶음에 없는 260823 artifact는 폐기할 근거가 없지만, 제3자가 동일 결론을 감사할 수 있는 상태도 아니다.

### M-05. timestamp collector 버전 provenance가 충돌함

이전 Phase 2 EV2 기록에는 corrected collector `spike-v1-ev2-01`과 nonzero latency가 존재한다. 최신 Decision Sheet는 현재 로컬 `bus_*_spike.py`, `subway_*_spike.py`가 응답 후 requested/received를 연속 기록해 240건 모두 latency Evidence로 부적합했다고 적는다. 서로 다른 파일 또는 회귀라면 두 기록은 동시에 참일 수 있다.

문제는 문서가 collector version을 일관되게 식별하지 않는다는 점이다. “collector timestamp가 잘못됐다”를 모든 과거 데이터로 일반화하지 말고 다음처럼 정리해야 한다.

- collector별 version/commit과 timestamp placement
- `VALID_FOR_LATENCY` 여부
- 260823 실행이 수정본인지 구본인지
- 회귀 방지 unit/integration test
- latency claim에는 허용된 collector version만 사용

### M-06. Bus residual example의 정체성 표현이 과함

Decision Sheet의 일부 예는 `vehId + 시간 근접`으로 매칭되었고 exact stop/`sectOrd`가 직접 검증되지 않았다고 적는다. 그런데 Service Plan에서는 signed residual example처럼 사실 목록에 놓여 있다. 문서 자체의 accepted residual 원칙은 동일 차량·동일 정류장·동일 예측 시점 문맥을 요구한다.

이 예는 `DIAGNOSTIC_CANDIDATE`로 낮추고 accepted residual sample 수에서 제외해야 한다. exact identity가 복원될 때만 승격한다.

### M-07. `coverageMode`가 서로 다른 축을 합침

어떤 곳에서는 `ROUTE_A_ONLY | KAKAO_WALK_ONLY | PROVIDER_SUPPORTED`라는 단일 enum처럼 쓰고, 다른 곳에서는 `ROUTE_A_ONLY + KAKAO_WALK_ONLY`처럼 조합한다. route coverage와 WALK provider coverage는 직교한다.

다음처럼 분리하는 편이 안전하다.

- `routeCoverageMode = ROUTE_A_ONLY | PROVIDER_SUPPORTED`
- `walkProviderMode = KAKAO_MAP_WALK | REFERENCE_ONLY | UNAVAILABLE`
- `modelCoverage`는 BUS/SUBWAY/WALK/TRANSFER/WAIT별 상태 map

### M-08. Share·owner capability의 보안 통제가 불충분함

현재 설계의 권한 분리는 좋지만 token 유출 경로와 browser mutation 방어가 빠져 있다.

- cookie 기반 owner mutation에 CSRF token 또는 strict Origin 검증
- HTTPS only, Secure, HttpOnly, SameSite 정책
- share token이 path, browser history, reverse-proxy log, Referer에 남지 않도록 log redaction과 `Referrer-Policy: no-referrer`
- owner/share 응답의 `Cache-Control: no-store`
- share revoke/rotation과 만료 후 동작
- CSP와 XSS 방어: capability token은 DOM/analytics에 노출하지 않음
- share 및 분석 endpoint의 abuse throttling

“analytics에 token을 기록하지 않는다”만으로는 Nginx와 인프라 access log 누출을 막지 못한다.

### M-09. API·ERD cardinality와 행위 계약이 맞지 않음

다음 항목은 구현자마다 다르게 해석할 수 있다.

- `JOURNEY_REQUEST ||--|| JOURNEY`: 분석 실패 시 Journey가 없을 수 있으므로 0..1 여부 결정 필요
- `JOURNEY_RESULT ||--o| SHARE_SNAPSHOT`: 결과당 share가 하나인지, 반복 생성 가능한지 정책 필요
- `PREDICTION_SNAPSHOT`–`RESIDUAL`: outcome/context unique key 없이 다수 residual을 허용하는지 불명확
- IA/AC는 analyze idempotency를 기대하지만 `API-002`에 idempotency key와 재요청 응답 계약이 없음
- `SOURCE_STATE_UPDATE` reason은 있으나 internal event payload/owner가 없음
- `ABORTED` state는 있으나 사용자/API 계약이 없음

ERD의 선은 저장소 구현도가 아니라 business cardinality이므로 먼저 제품 정책으로 확정해야 한다.

### M-10. 활성 provider별 retention·redistribution 규칙이 없음

실제 Runtime과 Evidence에 사용하는 provider에는 다음 matrix가 필요하다. 기본 비활성화된 TMAP까지 운영 핵심 provider와 같은 깊이로 설계할 필요는 없으며, M-19의 단순 제외·만료 정책이면 충분하다.

| 항목 | 결정 내용 |
|---|---|
| Raw retention | 저장 가능 여부와 최대 기간 |
| Derived retention | 파생 feature/통계 보관 가능 범위 |
| Cache | endpoint별 허용 여부와 freshness |
| Share/redistribution | 사용자 화면·공유 snapshot에 포함 가능한 필드 |
| Deletion owner | 자동 만료와 수동 삭제 책임 컴포넌트 |
| Evidence exception | 별도 허가나 연구 목적 예외 증빙 |

데이터 lifecycle의 `immutable`은 “삭제하지 않는다”가 아니라 “허용 기간 동안 원본을 변조하지 않는다”로 재정의하는 편이 맞다.

### M-11. 제품 정본에 실험 연대기가 과도하게 들어감

Service Plan과 Requirements에 `신규`, `전날`, `오늘`, `재실험`과 날짜별 PASS/REJECTED가 많이 남아 있다. 정책의 근거는 필요하지만, 현재 문서가 최초 정본처럼 읽혀야 한다는 목표와는 어긋난다.

- Service Plan: 안정된 제품 원칙과 “왜”만 유지
- Requirements: 현재 구현해야 할 normative contract와 AC만 유지
- Decision Sheet/Evidence Register: 실행 날짜, 원시 수치, pass/rejected history 유지

요구사항의 Acceptance Scenario 안에 현재 Evidence verdict를 넣기보다 `Expected Result`와 `Current Evidence Status`를 분리해야 한다.

### M-12. 일정 대비 필수 범위가 과밀함

약 33일 안에 mobile-first PWA, Spring backend, Kafka/Flink 계열 분산 처리, object store, PostgreSQL, provider quota, 보안, data maturity, 배포, QA를 모두 완료하는 계획은 위험하다. 특히 확률 핵심 gate가 미성숙하므로 일정만 맞추기 위해 수치를 시연하면 문서의 정직성 원칙과 충돌한다.

최종 데모를 capability tier로 고정해야 한다.

1. `D0 Product Contract`: Route A 정상/오류/partial 상태와 분산 처리 replay를 정직하게 시연
2. `D1 Experimental Reliability`: component/replay 범위의 P50/P90/P(on_time)을 실험 출력으로 시연
3. `D2 Calibrated Journey`: V3와 Journey-level calibration gate를 통과한 경우에만 확률 신뢰 claim

상위 tier가 실패해도 하위 tier가 하나의 완결된 제품 서사를 유지해야 한다.

### M-13. 서울 지하철 quota 증액 표현이 공식 문구보다 강함

서울 열린데이터광장은 현재 이용 사례 갤러리에 콘텐츠와 인증키를 등록하면 지속적으로 제한 없이 이용할 수 있다고 안내한다. 문서의 “승인 시 무제한 전환”은 심사 절차, 소요 시간, 조건을 확정한 것처럼 읽힌다. 공식 문구에 맞추고, 현재 프로젝트가 언제 적용 가능한지 별도 확인 전까지 일정·quota 계획에 반영하지 않아야 한다.

### M-14. 공공데이터포털 버스 quota의 단위를 과대 해석할 수 있음

공식 페이지는 서울 버스도착정보 서비스와 버스위치정보 서비스를 별도 서비스로 제공하고 각각 개발계정 트래픽 1,000을 표시한다. 이것은 두 서비스의 pool이 구분된다는 근거는 되지만, 각 상세 기능마다 1,000건의 독립 pool이 있다는 뜻까지 자동으로 증명하지는 않는다. 문서는 `도착정보 서비스 1,000/day`, `위치정보 서비스 1,000/day`로 쓰고, 더 세분된 counter를 주장하려면 console artifact를 연결해야 한다.

### M-15. 오류 코드 enum이 문서 간 불일치함

- IA: `PROVIDER_QUOTA_EXHAUSTED`
- Requirements: `PROVIDER_QUOTA_EXCEEDED`
- IA: `EVENT_NOT_ALLOWED`
- Requirements: `EVENT_NOT_ALLOWED_IN_STATE`

canonical backend error enum, UI projection code, 사용자 문구를 한 표에서 관리해야 한다. business result state와 transport/API error namespace도 구분한다.

### M-16. IA 공통 Result ViewModel 표가 Markdown 구조상 깨짐

`modelCoverage` 이후 필드가 표 중간의 설명 문단 때문에 실제 표 밖으로 빠진다. 사람이 의미를 추론할 수는 있지만 renderer와 agent가 schema를 잘못 읽을 수 있다. 설명을 표 아래로 이동하고 필드 행을 하나의 표로 복원해야 한다.

### M-17. 분석 가능한 시간 범위가 없음

“과거 시각은 허용하지 않는다”만 있고 timetable/artifact 유효기간 밖의 미래를 어떻게 다룰지 없다. 현재 provider와 snapshot이 지원하는 `supportedAnalysisHorizon`을 버전 설정으로 두고, 범위 밖 입력은 구체적 사유로 거절해야 한다. 숫자는 실험 전 만들지 않아도 되지만 owner와 실패 의미는 정해야 한다.

### M-18. 두 종류의 Actual이 혼동될 수 있음

데이터 모델의 Actual은 provider가 관측한 차량·열차 도착 구간이다. Live Journey에서 사용자 확인으로 얻는 실제 사건은 탑승·미탑승·환승 실패다. 둘을 모두 Actual이라고 부르면 residual 산출과 사용자 사건을 잘못 결합할 수 있다.

- `ProviderActualArrivalInterval`
- `JourneyUserEvent`

처럼 이름과 provenance를 분리하는 것이 안전하다.

### M-19. TMAP을 운영용 자동 fallback처럼 상세 설계할 필요는 없음

**확정된 정책**

- TMAP은 호출 제한이 지나치게 작아 Minimum Release의 primary provider가 아니다.
- Kakao route discovery/WALK가 정상일 때 TMAP을 호출하지 않는다.
- Route A 데모, Journey Reliability 계산, 분산 처리 증명, release success가 TMAP에 의존하지 않는다.
- Kakao 불능 시에도 전체 사용자 트래픽을 TMAP으로 자동 전환하지 않는다. 호출량상 서비스 연속성 provider가 될 수 없기 때문이다.

따라서 TMAP의 정확한 상태는 `DISABLED_BY_DEFAULT`인 **수동 비상 reference/diagnostic 수단**이다. “backup provider”라는 표현은 자동 failover를 연상시키므로 문서에는 이 뜻을 함께 적는다.

필요한 정책은 다음으로 충분하다.

1. 운영자 또는 데모 관리자가 제한된 단건 확인에만 명시적으로 활성화한다.
2. 결과는 point estimate/reference로만 사용하고 확률분포·canonical route truth·사용자 신뢰 claim에 사용하지 않는다.
3. raw/result는 장기 Evidence store에 넣지 않고 공식 허용 기간 안에 만료한다.
4. TMAP이 비활성화되거나 quota가 없으면 Kakao 실패를 숨기지 않고 `PROVIDER_UNAVAILABLE` 또는 승인된 cache 상태를 표시한다.

이 네 줄이 세 문서에 동일하게 반영되면 TMAP은 Release Blocker가 아니다. 장기 TMAP raw를 계속 보관하거나 자동 runtime failover로 다시 승격할 때만 별도 약관·quota 설계가 필요하다.

## 7. 문서 간 핵심 충돌 Matrix

| ID | Service Plan | IA | Requirements | Decision Sheet / Evidence | 판정 |
|---|---|---|---|---|---|
| C-01 | 서울 전역 서비스와 Route A 데모가 혼재 | 임의 서울 위치 검색 | `ROUTE_A_ONLY` | Kakao publictraffic canonical source REJECTED | coverage 축 혼합·route 생성 계약 공백 |
| C-02 | 사용자 확률 제공 | 전역 `resultEligibility` | 미성숙 leg 경고 중심 | Journey calibration 미완 | claim gate 부족 |
| C-03 | 정상·오류 reforecast | 정상 leg 완료 CTA/전이 누락 | 정상 transition 요구 누락 | BUS_SKIPPED 중심 검증 | E2E 불완전 |
| C-04 | 지하철 225/1,000 | quota 상태 표시 | 225/1,000 AC | 표 산술상 최소 315 | 수치 충돌 |
| C-05 | TMAP reference가 일부 남음 | 사용자 노출 불필요 | generic lifecycle 적용 가능 | TMAP은 사실상 폐기·수동 비상용 | `DISABLED_BY_DEFAULT`와 비보관만 명문화하면 해소 |
| C-06 | coverage mode 조합 | 단일 필드처럼 표현 | enum-like 정의 | route와 WALK Evidence 분리 | 모델 충돌 |
| C-07 | provider failure | `EXHAUSTED` | `EXCEEDED` | provider code 별도 | enum 충돌 |
| C-08 | owner/share 분리 | share path token | API/보안 요구 | log/referrer Evidence 없음 | 보안 계약 공백 |
| C-09 | BUS residual 미성숙 | diagnostic UI 가능 | strict identity | 일부 time+vehicle 근접 예 | status 과장 |
| C-10 | abort 상태 존재 | CTA 없음 | API 없음 | 실험 없음 | 유령 상태 |

## 8. 최신 실험 및 공식 자료에 대한 Evidence 판정

### 8.1 직접 확인된 항목

| 항목 | 확인 결과 | 사용 가능한 claim |
|---|---|---|
| Kakao WALK 8/22 JSON | HTTP 200, 295m, 323s, 1 leg | 해당 OD·호출 시점에서 WALK endpoint 성공 |
| Kakao publictraffic 8/22 JSON | HTTP 200, 15 routes: bus 8, subway 3, mixed 4 | 해당 OD·시점에서 후보 반환 성공 |
| publictraffic Stop schema | 첨부 payload의 Stop key는 `name`뿐 | 이 payload만으로 canonical stop ID 미제공 |
| publictraffic Vehicle schema | 첨부 payload의 Vehicle key는 `name`, `type` | 이 payload만으로 canonical vehicle/line ID 미제공 |
| 후보 총시간 정합성 | 첫 후보 total 2,651초, step 합 1,764초로 887초 차이 | total과 step 단순합을 동일 의미로 가정 금지 |
| Kakao quota screenshot 8/22 | WALK 1/1,000, publictraffic 1/1,000 | 두 endpoint의 기본 quota와 별도 counter 관찰 |

첨부 JSON과 Kakao 공식 응답 schema가 같은 방향을 가리키므로, publictraffic을 MR primary structural route source로 사용하지 않는 결정은 강하게 지지된다. 단, “어떤 외부 crosswalk로도 영원히 해결 불가”가 아니라 **현재 payload 단독으로는 deterministic identity를 만들 수 없다**고 표현해야 한다.

### 8.2 문서에는 있으나 이번 묶음에서 독립 확인하지 못한 항목

| 항목 | 상태 | 필요한 보강 |
|---|---|---|
| 8/23 Kakao WALK 9/1,000 | 로컬 실행 기록 | console screenshot/hash/captured_at |
| 8/23 Kakao publictraffic 4/1,000 | 로컬 실행 기록 | console screenshot/hash/captured_at |
| 지하철 225/1,000 | 내부 산술 충돌 | 최종 console ledger와 요청 manifest |
| bus/subway 240건 latency invalid | 로컬 collector 기록 | script version/commit, sanitized run manifest |
| Bus residual examples | 일부 identity 불완전 | stop/sectOrd/vehicle/time join provenance |

이들은 삭제할 항목이 아니라 Evidence maturity를 한 단계 낮춰 기록할 항목이다.

### 8.3 공식 자료로 보강된 항목

- Kakao 공식 quota 문서는 지도 REST 키워드/좌표 검색 일 100,000건, 대중교통과 WALK 각각 일 1,000건을 제시한다.
- Kakao 유료 초과 호출은 Bizwallet과 유료 API 설정이 있어야 하며, 설정하지 않으면 제한 초과 시 429가 발생한다.
- Kakao publictraffic 공식 response schema의 Stop은 `name`, Vehicle은 `name`과 `type`만 정의한다.
- 공공데이터포털은 서울 버스도착정보와 버스위치정보를 별도 서비스로 제공하며 개발계정 트래픽을 각각 1,000으로 표시한다.
- 서울 열린데이터광장은 이용 사례 갤러리 등록을 지속 이용 경로로 안내하지만, 이번 검토로 심사 기간이나 프로젝트별 승인 보장을 확인한 것은 아니다.
- TMAP 약관은 API 데이터의 24시간 초과 저장·사용을 제한한다.

## 9. E2E 시나리오 실행 결과

| 시나리오 | 문서만으로 실행 가능? | 결과 |
|---|---|---|
| 임의 서울 OD: Search→Route Candidate→Analyze | 부분 가능 | 위치 입력은 있으나 route discovery·canonicalization·mapping failure 계약이 불완전 |
| Route A 데모: Analyze→Start→Arrive | 아니오 | 보호 경로는 맞지만 ACCESS_WALK 완료, RIDE 하차, 정상 TRANSFER 전이가 없음 |
| BUS_SKIPPED | 대부분 가능 | 현재 후보 제거와 다음 WAIT/RIDE 구성은 좋음; 다음 source 부재 후 회복은 부족 |
| TRANSFER_MISSED | 부분 가능 | 오류 진입은 있으나 정상 transfer 완료와 비교 가능한 canonical 흐름 부족 |
| Kakao WALK 실패 | 대체로 가능 | unavailable/cache 원칙은 있음; 임의 입력과 Route A 관계가 불명확 |
| Provider quota 소진 | 사용자 상태는 가능 | 숫자 원장 충돌, public abuse 방어, paid-mode 행동 미확정 |
| Partial model coverage | 화면 표시는 가능 | per-metric 확률 eligibility가 없어 과신 위험 |
| Offline→Foreground 복귀 | 가능 | freshness와 재동기화 원칙이 비교적 명확 |
| Share 열람 | 기능적으로 가능 | URL token, log, referrer, cache, revoke 계약 부족 |
| 분산 replay/determinism 증명 | 의도상 가능 | canonical checksum 범위, floating tolerance, 2-node 실제 capacity 미정 |

## 10. 문서별 상세 판정

### 10.1 `SERVICE_PLAN_260823.md`

**강점**

- 서비스 차별점과 확률 용어의 금지 표현이 선명하다.
- Minimum Release, Explicit Out, Route A/B, 데이터 provenance, ML 비적용 기준이 잘 구분된다.
- provider 실패를 제품 상태로 번역하고 분산 처리의 목적을 명확히 한다.

**보완 핵심**

- 서울 전역 임의 OD 서비스 범위와 Route A 검증·데모 범위를 서비스 정의 수준에서 분리한다.
- route discovery와 canonical transit mapping을 별도 제품 capability로 설명한다.
- stable policy와 dated experiment history를 분리한다.
- 활성 provider의 license matrix를 추가하고, TMAP은 `DISABLED_BY_DEFAULT·비보관·수동 단건 reference`로 짧게 제외한다.
- 확률 노출을 per-metric claim eligibility로 재작성한다.
- 정상 live journey와 demo tier를 보완한다.

### 10.2 `IA_SCREEN_SPEC_260823.md`

**강점**

- PWA/mobile-first, offline, stale, partial, share read-only의 UI 상태가 충실하다.
- 사용자 문구 원칙과 technical detail 접기 전략이 좋다.
- 화면과 UI-AC 연결이 강하다.

**보완 핵심**

- 서울 내 임의 위치 검색을 유지하고 geography validation, route discovery, canonicalization 상태를 화면 계약으로 분리한다.
- Route A는 검색 가능 범위를 제한하는 preset이 아니라 `검증 완료된 데모 경로` badge 또는 내부 fixture로만 다룬다.
- 임의 후보의 mapping이 불완전할 때 경로 표시와 확률 미계산 사유를 함께 보여 주는 partial state를 추가한다.
- 모든 정상 leg의 완료/다음 행동 CTA를 추가한다.
- abort, unavailable recovery, source update projection을 추가한다.
- 공통 Result ViewModel 표를 복구한다.
- 확률 자격을 metric별 view field로 투영한다.
- error enum과 share security header/로그 정책을 Requirements와 맞춘다.

### 10.3 `REQUIREMENTS_SPEC_260823.md`

**강점**

- 요구사항 식별자, traceability, AC, NFR의 밀도가 매우 높다.
- 불확실성·fallback·null·unsupported를 개발자가 구현 가능한 수준으로 분해했다.
- 분산 증명과 quota coordinator의 책임을 요구사항화했다.

**보완 핵심**

- 정상 leg transition과 internal source event 요구사항을 추가한다.
- analyze idempotency, abort, recovery API를 확정한다.
- ERD cardinality와 share 생성 정책을 정리한다.
- 활성 provider별 retention/license와 public admission control을 NFR로 추가하고, TMAP에는 자동 fallback 금지와 만료 정책만 둔다.
- Acceptance expectation과 현재 Evidence verdict를 분리한다.
- quota 숫자와 error enum을 canonical register에 맞춘다.

### 10.4 `DECISION_SHEET_260823.md`

**강점**

- 무엇을 채택·기각·유보했는지 짧고 명확하다.
- Kakao WALK와 publictraffic의 다른 역할을 분리한 판단은 raw payload 및 공식 schema와 부합한다.
- 잘못된 latency 수집을 숨기지 않고 Evidence에서 제외한 태도가 좋다.

**보완 핵심**

- 지하철 quota 산술을 원장 기준으로 바로잡는다.
- 모든 결정에 artifact path/hash와 collector version을 연결한다.
- 8/23 local-only Evidence의 감사 상태를 표시한다.
- bus residual 예를 diagnostic으로 낮춘다.
- “이미지 미보관” 대신 secret-redacted screenshot 보관 정책을 채택한다.

## 11. 권고 수정 순서

문장 다듬기보다 의존성이 큰 결정부터 닫아야 한다.

1. **Coverage 축 재정의**: 서울 전역 임의 OD, route discovery, canonical mapping, model coverage, Route A demo scope를 분리
2. **정상 상태 머신 완결**: 모든 leg의 enter/complete와 abort/recovery/source event 정의
3. **확률 claim matrix 확정**: metric별 eligibility와 D0/D1/D2 데모 tier
4. **quota 원장 재조정**: 8/23 지하철 수치, provider별 pool, paid mode 확인
5. **provider data governance**: 활성 provider의 raw/derived retention을 정하고 TMAP은 기본 비활성·비보관으로 제외
6. **API/ERD 보정**: idempotency, internal event, cardinality, canonical errors
7. **보안·abuse control**: CSRF, token leakage, log/cache/referrer, admission control
8. **Evidence packaging**: manifest, version, path/hash, screenshot captured_at
9. **세 문서 동기 수정**: Service Plan→IA→Requirements 순서로 상위 정책을 하위 계약에 투영
10. **마지막 E2E 역검증**: AC에서 정책까지, 정상 Start에서 Arrived까지 양방향 추적

## 12. Release / Freeze Gate 제안

다음 조건이 모두 충족되기 전에는 문서를 `FROZEN`으로 표시하지 않는다.

| Gate | 통과 조건 |
|---|---|
| FG-01 Normal Journey | Route A가 Start부터 Arrived까지 UI–API–state–entity–AC로 완주됨 |
| FG-02 Coverage Truth | 서울 임의 OD 검색·경로 생성과 Route A 검증·데모 범위가 분리되고, mapping/model 미지원 시 동작이 동일하게 정의됨 |
| FG-03 Claim Eligibility | P50/P90/P(on_time)/Recommended Departure의 metric별 자격과 문구가 일치함 |
| FG-04 Quota Ledger | Decision Sheet 산술과 console/request manifest가 일치함 |
| FG-05 Provider License | 활성 provider의 보관 정책이 공식 조건과 충돌하지 않고, TMAP은 기본 비활성·자동 failover 금지·허용 기간 내 만료로 정의됨 |
| FG-06 API/ERD | abort, source update, idempotency, cardinality, error enum이 확정됨 |
| FG-07 Security | CSRF, token log/referrer/cache, rate abuse 정책이 요구사항과 IA에 반영됨 |
| FG-08 Evidence Audit | 최신 실험의 artifact path/hash/version/captured_at을 제3자가 추적 가능 |
| FG-09 Demo Honesty | 최종 demo tier가 통과한 validation gate를 넘는 claim을 하지 않음 |
| FG-10 Cross-doc Check | 세 문서와 Decision Sheet 간 canonical term/value diff가 0건 |

## 13. 수정 후 반드시 다시 실행할 보호 시나리오

1. 서울 내 Route A OD 검색 → 후보 생성 → canonical mapping → 분석 → Start → ACCESS_WALK 완료 → BUS_WAIT → 탑승 → BUS_RIDE 하차 → TRANSFER → SUBWAY → FINAL_WALK → Arrived
2. BUS_WAIT에서 BUS_SKIPPED → 다음 후보 존재 / 없음 / 나중에 회복되는 세 분기
3. TRANSFER 정상 완료와 TRANSFER_MISSED 비교
4. WALK 성공 / business error / HTTP error / stale cache / quota 소진
5. 일부 leg distribution 부재 시 P50·P90·P(on_time) 각각의 노출 결과
6. owner cookie 없음, 위조 CSRF, 만료 share, revoke share, access-log redaction
7. analyze 동일 요청 재전송과 idempotency
8. provider quota가 reserve threshold에 진입했을 때 public/demo/validation 요청 우선순위
9. 동일 input replay의 canonical output checksum과 허용 수치 오차
10. 앱 offline→foreground 복귀 시 Journey state와 source freshness 동기화

## 14. 최종 결론

현재 세 핵심 문서는 방향을 다시 세워야 하는 초안이 아니다. 제품 철학, 확률 가드레일, 실패 정직성, 추적성은 이미 높은 수준이다. 문제는 그 좋은 원칙 사이의 몇 군데가 아직 연결되지 않았다는 데 있다.

가장 먼저 해야 할 일은 새 기능을 늘리는 것이 아니다. `서울 임의 OD와 Route A 데모 범위의 분리`, `route discovery와 canonicalization 계약`, `정상 상태 전이`, `확률별 claim 자격`, `quota 원장`을 canonical 결정으로 고정하는 것이다. 이 항목들이 닫히면 나머지 문제는 IA·REQ·API·ERD에 일관되게 투영할 수 있다. TMAP은 여기에 포함되는 핵심 의존성이 아니라 기본 비활성·비보관의 수동 비상 reference로 짧게 경계를 정하면 된다.

따라서 현 상태는 **높은 완성도의 pre-freeze 세트**이며, **최종 freeze 세트는 아니다**. Blocker 수정 후 문서 전체를 다시 읽고, 정상 E2E와 실패 E2E를 모두 통과시키는 2차 검토가 필요하다.

## 15. 공식 확인 자료

- [Kakao API 쿼터](https://developers.kakao.com/docs/ko/getting-started/quota)
- [Kakao Map 공통·과금 및 쿼터](https://developers.kakao.com/docs/ko/kakaomap/common)
- [Kakao Map REST API와 응답 schema](https://developers.kakao.com/docs/ko/kakaomap/rest-api)
- [서울 열린데이터광장 인증키·이용 사례 안내](https://data.seoul.go.kr/together/mypage/actkeyMain.do)
- [공공데이터포털 서울특별시 버스도착정보조회 서비스](https://www.data.go.kr/data/15000314/openapi.do)
- [공공데이터포털 서울특별시 버스위치정보조회 서비스](https://www.data.go.kr/data/15000332/openapi.do)
- [TMAP 대중교통 API 이용약관](https://transit.tmapmobility.com/terms)
