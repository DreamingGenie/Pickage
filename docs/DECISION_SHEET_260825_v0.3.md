# Journey Reliability Decision Sheet — 2026-08-25 v0.3 정본

> **2026-08-25 v0.3 제품 정본**. 아래 2026-08-23 Evidence Resolution Pack의 관측·판정과 2026-08-24 v0.1/v0.2 product history는 역사 사실로 그대로 보존한다. v0.3은 팀 회의에서 도출된 수정점을 반영해 **Splash→Shared Input Shell 진입, Milestone(경유포인트) Projection, URL public Share 승격, 기능 독립성 강화, Arrival 핵심에서 mandatory targetArrivalAt/P(on_time) 제거**를 신규로 확정한다.
>
> Journey Reliability Evidence Resolution Pack(`docs/history/0823_plan_fix/00~07`) 실행 결과. Sunday `END` service day 기준. 모든 항목은 `provider×endpoint×OD/corridor×window×service day×adapter version` 범위로만 유효하다.

## 문서 네비게이션

**정본 문서 바로가기**

- [Service Plan](SERVICE_PLAN_260825_v0.3.md)
- [IA / Screen Spec](IA_SCREEN_SPEC_260825_v0.3.md)
- [Requirements Spec](REQUIREMENTS_SPEC_260825_v0.3.md)
- **Decision Sheet**

**이 문서 안에서 이동**

- [실행한 API calls](#실행한-api-calls)
- [Decision Sheet](#decision-sheet)
- [아직 하루로 해소할 수 없었던 항목과 이유](#아직-하루로-해소할-수-없었던-항목과-이유)
- [Evidence Manifest (신규, M-04 반영)](#evidence-manifest-신규-m-04-반영)
- [문서 확인](#문서-확인)
- [2026-08-23 Post-decision Reconciliation (Historical Snapshot)](#2026-08-23-post-decision-reconciliation-historical-snapshot)
- [2026-08-24 Product Reframing Decision — v0.1 history](#2026-08-24-product-reframing-decision)
- [2026-08-24 v0.2 Product Separation Decision](#2026-08-24-v02-product-separation-decision)
- [2026-08-25 v0.3 Entry / Milestone / URL Share Superseding Decision](#2026-08-25-v03-entry--milestone--url-share-superseding-decision)

---

## 실행한 API calls

| Provider | Endpoint | 호출 수 | 결과 |
|---|---:|---:|---|
| Kakao Map REST API | publictraffic | 9(HTTP 400 검증 실패 1건 포함) | HTTP 200×8(business status OK×6, EQUAL_POINTS×1, NO_RESULTS×1), HTTP 400×1(param 이름 오류로 재시도 전 실패, Kakao 콘솔 사용량에는 포함됨) |
| Kakao Map REST API | walk | 4 | 전부 HTTP 200 OK |
| data.go.kr | getPathInfoByBusNSub(mixed-route) | 8 | 참고용 부가 evidence(오늘 실행 계획에는 없었으나 provider 확인 과정에서 수집됨) — 본 Decision Sheet의 정책 결정에는 반영하지 않음 |
| TMAP pedestrian | routes/pedestrian | 5 | 참고용 부가 evidence(위와 동일한 사유) |
| Seoul Bus Arrival(`getArrInfoByRouteAll`) | busRouteId=100100001 | 60 | 정상 완료 |
| Seoul Bus Position(`getBusPosByRouteSt`) | busRouteId=100100001 | 60 | 정상 완료 |
| Seoul Subway Arrival(`realtimeStationArrival`) | 안국/교대/역삼 개별 | 45×3=135 | 정상 완료(최초 시도의 `"역명1&#124;역명2&#124;역명3"` 파이프 결합 문법은 무효 — 45+45=90건 낭비 후 개별 호출로 재실행) |
| Seoul Subway Position(`realtimePosition`) | 3호선/2호선 개별 | 90×2=180 | 정상 완료(동일 사유로 최초 90건 낭비 후 재실행) |

**지하철 quota 산술 재검토(2026-08-23 검수 반영)**: 위 표의 성공 호출만 합산해도 Arrival 135 + Position 180 = **315건**이며, 낭비 호출(파이프 결합 문법 오류로 인한 재시도 전 실패분)은 이 표와 별도다. Service Plan/Requirements에 기록된 "2026-08-23 실사용 225/1,000"은 이 315건과 산술이 맞지 않는 것으로 확인됐다. 어느 쪽도 임의로 폐기하지 않고, 정확한 총 호출 수는 provider console 최종 스냅샷과 raw request log를 대조해야 확정할 수 있으므로 현재 상태를 `PENDING_RECONCILIATION`으로 표기한다. 2026-08-23 당시 세 문서(Service Plan, Requirements, Decision Sheet)는 재대사 전까지 이 상태값을 동일하게 사용하도록 합의했다.

data.go.kr(Bus 계열)과 Seoul Subway 키의 승인 일일 한도는 PM이 제공한 콘솔 스크린샷 3장(2026-08-23 15:30~15:31 KST)으로 확인 완료 — 아래 Decision Sheet 참조.

**Kakao entitlement/quota — PM이 제공한 콘솔 스크린샷 2장(2026-08-23 15:16 KST)으로 확인 완료.** "일간 쿼터 사용량 > 오늘" 화면 기준:

| Endpoint | 오늘 사용량 | Limit |
|---|---:|---:|
| `/route-open/openapi/v1/publictraffic.json` | 9 | 1,000 |
| `/route-open/openapi/v1/walk.json` | 4 | 1,000 |

위 endpoint path는 Kakao 콘솔 사용량 화면의 집계 라벨이다. 실제 runtime 호출 URL은 Service Plan의 provider source 구분(`dapi.kakao.com/v2/routing/*`)을 따른다.

이 세션이 실제로 호출한 수(publictraffic 9건 — HTTP 400 실패 1건 포함, walk 4건)와 정확히 일치한다. 두 endpoint 모두 프로젝트 앱에 1,000/day entitlement가 실제로 부여되어 있음이 콘솔로 직접 확인됐다. Kakao WALK runtime budget은 `CONFIRMED`이며, publictraffic entitlement 확인은 future `KAKAO_ROUTE_PROVIDER_GATE`의 조건 1만 충족한다. billing usage history와 official overage policy는 이 quota 스크린샷이 아니라 아래 별도 근거로 분리 관리한다.

PM 콘솔 스크린샷은 프로젝트 의사결정 근거로 사용하지만, 현재 docs root에는 원본 이미지 artifact를 저장하지 않는다. 재현 가능한 감사가 필요하면 screenshot path/hash 또는 별도 Evidence Register 링크를 추가한다. 공식 quota/overage 정책은 콘솔 스크린샷이 아니라 Kakao 공식 쿼터 문서를 근거로 관리한다.

## Decision Sheet

| Item | Before | Evidence | Decision | Scope | Service Plan | IA | Requirements | Remaining gate |
|---|---|---|---|---|---|---|---|---|
| Kakao candidate 반복 안정성 | UNVERIFIED | 동일 window 2회 + 전날(08-22) 대비 재호출, 15개 후보 signature 완전 일치 | `FIXED` (tested OD 범위, reference evidence) | Demo Corridor OD, 2026-08-22~23 publictraffic | Service Plan 「제품 범위와 현재 확인 수준」, Service Plan 「핵심 설계 근거」 | — | AC-053 PASS | 다른 OD/corridor는 미검증; selected route 근거로 사용하지 않음 |
| Kakao WALK point 재현성 | CONDITIONAL | ACCESS leg 295m/323s가 전날과 완전 동일 | `FIXED` (tested pair 범위, WALK provider evidence) | Route A ACCESS pair | Service Plan 「핵심 설계 근거」 | — | AC-056 PASS | 다른 pair는 미검증 |
| Kakao canonical mapping | CONDITIONAL | bus/subway/mixed 3개 topology candidate 전부 stop=name만, vehicle=name/type만; ID 필드 없음 | `REJECTED` (future route-provider payload 구조적 한계) | Kakao publictraffic 응답 스키마 전체 | Service Plan 「Selected-route 정책」, Service Plan 「핵심 설계 근거」, Service Plan 「Top Risks」, Service Plan 「아직 Claim하면 안 되는 것」 | Open Decisions | AC-055 REJECTED, REQ-009 | 외부 name-based crosswalk 별도 설계 전에는 route-provider 재시도 무의미. WALK-only 사용에는 blocker 아님 |
| Kakao total/step 시간 포함관계 | CONDITIONAL | candidate 0(SUBWAY) gap 887s vs 경계WALK 829s(58s 잔차); candidate 2(BUS_AND_SUBWAY) gap 422s vs 437s(15s 이내) | `CONDITIONAL` 유지, candidate 0은 `PARTIALLY_EXPLAINED`, candidate 2는 `HIDDEN_WALK_STRONGLY_SUPPORTED` | 테스트한 2개 publictraffic candidate만 | Service Plan 「Selected-route 정책」, Service Plan 「핵심 설계 근거」 | — | AC-054 PARTIAL | 58s 잔차의 원인(WAIT/환승/속도가정 차이) 미상. Minimum Release 결과 시간에 배분 금지 |
| Kakao 지리 범위 | 암묵적으로 서울 한정 가정 | 부산 좌표에서도 정상 200/OK, 3개 후보 반환 | `NEW_FACT` — Kakao는 서울 경계를 스스로 제한하지 않음 | publictraffic 전체 | Service Plan 「핵심 설계 근거」 | — | REQ-001, BR-001 | product 입력단 지역 제한은 Requirements/IA에 반영됨. 구현·테스트에서 `UNSUPPORTED_GEOGRAPHY` 처리 확인 필요 |
| Kakao entitlement/quota | UNCONFIRMED | PM 제공 콘솔 스크린샷(2026-08-23 15:16 KST): publictraffic 9/1,000, walk 4/1,000 — 이 세션의 실제 호출 수와 정확히 일치 | `CONFIRMED` | Kakao Map REST API 앱 전체, 2026-08-23 | Service Plan 「API quota와 수집 예산」, Service Plan 「Selected-route 정책」 | — | AC-057 | billing usage history와 공식 overage 정책은 아래 별도 행에서 분리 관리 |
| Kakao billing usage history | UNCONFIRMED | PM 제공 콘솔 스크린샷(2026-08-23 15:23 KST, "유료 사용량" 화면, app `pjt_map` ID 1471189): 이번 달 유료 호출 0건(성공 0/실패 0), 무료 호출만 15건 — 2026-08-23 무료 13건(=publictraffic 9+walk 4), 2026-08-22 무료 2건(=baseline 1+1)과 정확히 일치 | `CONFIRMED` — 과금 발생 이력 없음 | Kakao Map REST API 앱 전체, 2026-08-01~08-23 | Service Plan 「API quota와 수집 예산」 | — | — | 과금 발생 이력 0건은 overage 단가·정책 확인과 별도 사실 |
| Kakao official overage policy | 별도 사실 | Kakao 공식 쿼터 문서: 첫 활성화 앱 무료 일 1,000회, 초과 10원/건 | `VERIFIED_OFFICIAL` | Kakao Map REST API | Service Plan 「API quota와 수집 예산」 | — | — | 콘솔 스크린샷 근거가 아니라 공식 문서 근거. 실제 billing history와 분리 |
| Seoul data.go.kr Bus Arrival/Position 승인 한도 | UNCONFIRMED | PM 제공 콘솔 스크린샷(2026-08-23 15:30 KST): `[개발계정]서울특별시_버스도착정보조회 서비스`의 `getArrInfoByRouteAllList` 등 4개 상세기능 각각 1,000/day, `[개발계정]서울특별시_버스위치정보조회 서비스`의 `getBusPosByRouteStList` 등 5개 상세기능 각각 1,000/day. 오늘 각각 60회씩만 사용(6%) | `CONFIRMED` — 서비스별 독립 1,000/day, 공유 풀 아님 | data.go.kr 계정, 활용기간 2026-08-21~2028-08-21 | Service Plan 「API quota와 수집 예산」 | — | AC-049 | 상세기능별 독립 pool이라는 판정은 콘솔 화면 판독에 근거하며, 원본 스크린샷을 보관하지 않아 제3자가 동일 결론을 재검증할 수 없다(M-04와 동일 사유) |
| Seoul 열린데이터광장 지하철 승인 한도 | UNCONFIRMED | PM 제공 콘솔 스크린샷(2026-08-23 15:31 KST, "인증키 안내"): 공식 정책 텍스트로 "실시간 지하철 오픈API는 1일 1,000회만 호출 가능(인증키 1개당)" 확인, 지하철인증키 상태 "정상". 일반인증키(Seoul Open Data 나머지 API)는 호출 "횟수" 제한 없음(1회당 최대 1,000건 조회 page cap만) | `CONFIRMED` | 서울 열린데이터광장 계정 전체 | Service Plan 「API quota와 수집 예산」 | — | AC-049 | 활용사례 갤러리 등록 여부(현재 미등록) — 등록 시 지하철도 무제한 전환 가능, release 전 검토 대상 |
| `KAKAO_ROUTE_PROVIDER_GATE` 종합 | 4개 조건 중 반복안정성만 부분 확인 | 위 4개 항목 판정 종합 | `REJECTED` 종합(mapping 조건 구조적 실패) | future Kakao publictraffic Primary route-provider 승격 | Service Plan 「Selected-route 정책」 | — | REQ-009 | mapping crosswalk 재설계 전에는 route-provider Gate 재도전 무의미. 당시 snapshot wording은 `ROUTE_A_ONLY + KAKAO_WALK_ONLY`였으며, 2026-08-23 당시 활성 필드와의 관계는 아래 historical reconciliation을 따른다 |
| Bus target-stop(안국역6번출구, ord=21) Actual | IMMATURE | 2026-08-23 30분 window, sectOrd=21 필터링 결과 유효 `0→1` 전이 0건(다른 정류장에서는 93건) | `NO_VALID_EVENT` (이번 window) | busRouteId=100100001, 2026-08-23 12:47~13:17 KST | Service Plan 「Top Risks」 | — | — | 더 길거나 여러 window로 재시도; sectOrd↔staOrd 대응 자체도 재검증 필요 |
| Subway station×line Actual(4개) | COMPONENT | 45분 window: 안국(3호선) 16건, 교대(3호선측) 16건, 교대(2호선측) 1건, 역삼(2호선) 1건 유효 `arvlCd=1` 확보; trainNo join 전부 100% | `CONDITIONAL` (2개 역은 표본 확대, 2개 역은 표본 부족) | 4개 station×line, 2026-08-23 13:31~14:16 KST | Service Plan 「Top Risks」 | — | — | 2호선 두 역의 낮은 포착률 원인 미상 — window/interval 조정 후 재확인 |
| data.go.kr collector 인코딩 | 알려지지 않음 | `mixed_route_spike.py` 저장 raw의 한글 필드(정류장/노선명)가 mojibake; 숫자/ID/좌표 필드는 정상 | `NEW_FACT` (DQ 발견) | 오늘 호출분 전체 | — | — | — | collector encoding 수정은 별도 개발 작업으로 이관 |
| Route A ↔ Kakao 후보 구조 차이 | 서술만 있고 좌표 대조 없음 | 오늘 호출한 Kakao publictraffic 8건의 모든 candidate·모든 step의 path point를 검사한 결과, 승인 Route A 탑승점(춘추문, 126.97965,37.58308) 반경 100m 이내를 지나는 step이 0건 | `FIXED` — Kakao 응답은 승인 Route A 구조를 아예 후보로 제시하지 않음(우연 일치 불가능) | 오늘 호출한 8개 publictraffic 응답 | Service Plan 「현재 확인된 사실」 | — | — | 없음(이 OD 범위에서는 충분히 확정적) |
| Collector round-trip latency 계측 | 확인 안 됨 | `bus_*_spike.py`/`subway_*_spike.py`의 `requested_at`/`received_at`은 둘 다 HTTP 응답을 받은 뒤 `storage.SpikeResult()` 생성 시점에 동시 stamping됨(dataclass default_factory 2회 호출이 거의 같은 시각) → 오늘 수집된 240건 전부 latency=0.00~0.001s로 기록되어 있어 실제 request-boundary latency로 볼 수 없음. 임시로 작성한 Kakao 호출 스크립트도 응답 전/후 시각을 분리 기록하지 않아 동일한 한계를 가짐 | `BLOCKED_TOOLING`(collector 자체의 timestamp 설계 한계) | 오늘 사용한 모든 collector | — | — | — | collector가 `requested_at`을 호출 직전, `received_at`을 응답 직후로 분리 기록하도록 고치는 후속 작업 필요. **주의**: 과거 Phase 2 EV2-01(`docs/history/journey_reliability_docs_v2/evidence/phase2/EV2-01_COLLECTOR_TIMESTAMP/`)에서 이미 `COLLECTOR_VERSION=spike-v1-ev2-01`로 이 문제를 한 번 수정한 이력이 있다. 오늘 사용한 `bus_*_spike.py`/`subway_*_spike.py`가 그 수정본인지, 회귀했는지, 별개 스크립트인지 collector version/commit이 기록되지 않아 구분할 수 없다 — 후속 작업에서 collector version을 명시적으로 남긴다 |
| Out-of-order (source-time reversal) | 확인 안 됨 | receive 순서 기준 source timestamp 단조성 검사: bus position 13개 차량 계열, subway arrival 82개 station×train 계열 전부 역전 0건 | `NO_REVERSAL_OBSERVED`(이번 window) | 오늘 수집한 bus position + subway arrival 전체 | — | — | — | 표본이 늘어나면 재확인 필요(하루 한 window로 일반화 금지) |
| Subway Prediction→Actual Residual 실측 예시 | 미계산 | 안국(3호선) 열차 3166: 13:31:20 관측 시점 `barvlDt=210s` 예측(예상 도착 13:34:50) vs 실제 Actual interval (13:34:10, 13:35:05], mid=13:34:37.5, width=55s → signed residual L/M/U = −40s/−12.5s/+15s | `FIXED`(builder correctness 시연, 1개 사례) | 안국역 3호선, train 3166, 2026-08-23 13:31~13:35 KST | — | — | REQ-060~063, AC-030/032 범위에서 일반 capability로 커버 | 표본 1건 — support 주장 금지, 여러 window·여러 train으로 확대 필요 |
| Bus Prediction→Actual Residual 실측 예시 | 미계산 | staOrd=21(target)은 예측 60건 존재했으나 대응하는 Actual event가 이번 window에 없어(위 표 참조) target residual은 여전히 계산 불가. **General 예시(비-target)**: vehId=106024177, 12:54:23 관측 시점 `traTime=58s`(staOrd=13) 예측(예상 도착 12:55:21) vs 관측된 stopFlag `0→1` Actual interval (12:55:04, 12:55:32], mid=12:55:18 → signed residual L/M/U = −17s/−3s/+11s | `FIXED`(builder correctness 시연, target 아닌 1개 general 사례) — target(staOrd=21)은 `NO_VALID_EVENT` 유지 | busRouteId=100100001, non-target stop, 2026-08-23 12:54~12:56 KST | — | — | — | 이 예시의 stop이 staOrd=13과 정확히 일치하는지는 vehId+시간 근접으로만 추정했고 sectOrd로 직접 검증하지 않음 — target-stop 표본 확대가 여전히 필요 |
| Bus WAIT raw row 특성 | 미확인 | position raw 673행, 고유 차량 13대, 동일 차량 dataTm 중복 190행(28.2%) — snapshot 상당수가 신규 source 갱신 없이 반복됨 | `NEW_FACT`(dependence 근거) | busRouteId=100100001, 2026-08-23 30분 window | — | — | — | raw row를 independent support로 쓰지 않는다는 기존 정책의 실측 근거로만 사용; event-unit dependence 정량화(자기상관 등)는 미실시 |

## 아직 하루로 해소할 수 없었던 항목과 이유

- **Bus target-stop(staOrd=21) Actual 표본 부족**: 한 창(30분)의 우연 공백일 수 있어 `MULTI_DAY_REQUIRED`. General(비-target) residual 예시는 확보했으나 target 표본은 여전히 0건
- **Collector round-trip latency**: collector의 `requested_at`/`received_at` 설계 자체가 실제 latency를 담지 못함 — 코드 수정이 필요한 `BLOCKED_TOOLING`이며 별도 개발 작업으로 이관
- **Subway 2호선 두 역의 낮은 이벤트 포착률 원인**: 이번 데이터만으로는 원인 특정 불가(`MULTI_DAY_REQUIRED` 또는 poll interval 조정 후 재시도)
- **Bus WAIT event-unit dependence 정량화**: raw row 중복률(28.2%)만 확인했고 자기상관 등 정량 dependence 분석은 하지 않음
- 표준 검증 사다리(V1~V3) 관련 항목 전부: 오늘 하루로 승격 불가, `MULTI_DAY_REQUIRED` 유지

## Evidence Manifest (신규, M-04 반영)

이번 세션에 사용한 PM 콘솔 스크린샷과 오늘 collector 실행 결과는 아래 필드를 아직 채우지 못했다. 값을 임의로 채우지 않고 `NOT_CAPTURED`로 정직하게 표기하며, 재현 가능한 감사가 필요해지면 이 필드부터 채운다.

| 필드 | 상태 |
|---|---|
| `experiment_id` | `NOT_CAPTURED` |
| collector version/commit | `NOT_CAPTURED`(위 EV2-01 caveat 참조) |
| `executed_at`(각 collector 실행 시작·종료) | `NOT_CAPTURED`(오늘 실행 시각 범위만 본문에 서술로 존재) |
| endpoint별 HTTP count / provider business code count | 본문 표에 서술로 존재하나 별도 구조화 필드 없음 |
| raw/sanitized payload hash | `NOT_CAPTURED` |
| console screenshot hash / `captured_at` | `NOT_CAPTURED`(PM 제공 스크린샷 3장의 촬영 시각만 본문에 KST로 서술) |
| 문서가 참조하는 artifact 상대 경로 | `NOT_CAPTURED`(원본 이미지 미보관, 위 Kakao entitlement/quota 단락 참조) |

## 문서 확인

- 2026-08-23 당시 root 기획 문서는 `SERVICE_PLAN_260823.md`, `REQUIREMENTS_SPEC_260823.md`, `IA_SCREEN_SPEC_260823.md`, `DECISION_SHEET_260823.md` 4개였다. 260822 정본과 실행 지시/증거 파일은 `docs/history/0823_plan_fix/`에 보존한다.
- 2026-08-23 Decision Sheet 작성 이후 신규 API 호출 없음. 이후 변경은 문서 정합성 정리와 검수 반영에 한정한다.
- 2026-08-24 v0.2 문서 세트로 정리되면서 260823 세트는 `docs/history/0824_260823_planning_set_archive/`로 이관됐다.
- 2026-08-26 팀 회의 수정점을 반영해 v0.3 문서 세트가 도착하면서 260824 v0.2 세트는 `docs/history/0826_260824_v0.2_planning_set_archive/`로 이관됐다.
- production code·개발 설정·배포 변경 없음 확인: docs 기획 문서와 docs 예시 설정 외 파일은 수정하지 않는다. 실제 secret은 Git 추적 대상에 포함하지 않는다.

## 2026-08-23 Post-decision Reconciliation (Historical Snapshot)

이 Decision Sheet의 Evidence 행은 2026-08-23 당시 관측과 PM 콘솔 snapshot을 보존한다. 따라서 `REJECTED`, `CONFIRMED`, `PENDING_RECONCILIATION`, `NOT_CAPTURED` 같은 과거 판정과 수집 사실은 소급 변경하지 않는다.

2026-08-23 당시 정본 정책은 coverage와 selected route를 분리했다. PM 확정 후 Minimum Release의 목표 snapshot은 `geographyCoverage=SEOUL_ONLY`, `routeSearchCoverage=ARBITRARY_OD_DISCOVERY`, `selectedRoutePolicy=PROVIDER_FIRST_SUPPORTED`, `walkProviderMode=KAKAO_MAP_WALK`, `validationAndDemoScope=ROUTE_A_DEMO_ONLY`이다. 최종 시연은 Route A만 사용한다. 2026-09-14 팀 회의에서 남은 일정상 D2 Gate가 불가능하다고 판단하면 `selectedRoutePolicy=APPROVED_ROUTE_A_ONLY`의 Route A D1 fallback으로 probability/Recommended Departure claim을 축소하되, 서울 임의 OD structure-only 결과는 유지한다. Kakao publictraffic의 2026-08-23 payload-only route-provider 승격은 여전히 `KAKAO_ROUTE_PROVIDER_GATE`에서 `REJECTED`이며, D2 목표 달성에는 REQ-105 안전한 자동 canonicalization crosswalk가 필요하다.

과거 행의 `ROUTE_A_ONLY + KAKAO_WALK_ONLY` wording은 deprecated composite snapshot이다. 이를 2026-08-23 당시 API/UI/manifest 필드로 기록할 때는 위 필드들로 분해했다. `PROVIDER_FIRST_SUPPORTED`는 이제 future 문구가 아니라 D2 목표 selected-route 정책이며, `APPROVED_ROUTE_A_ONLY`는 demo/fallback 정책으로만 사용한다.

Kakao publictraffic 후보의 canonical mapping이 `EXACT/UNAMBIGUOUS`이고 model Gate가 통과하면 서울 임의 OD에서도 probability와 Recommended Departure를 계산한다. `UNAMBIGUOUS` 이상은 name normalization, 좌표 근접성, 버스 노선/지하철 line, 방향·순서 조건으로 후보가 하나로 좁혀질 때만 인정한다. Recommended Departure는 후보 출발시각 5분 grid/coarse-to-fine 재평가를 통과한 경우에만 표시한다. `PARTIAL/FAILED` 또는 model 미달이면 SCR-02 structure-only fallback 결과로 표시하고 probability/Recommended Departure는 `NOT_COMPUTED`로 유지한다. 승인된 Route A manifest/hash/topology가 깨진 경우만 `ROUTE_MANIFEST_INVALID`로 분리한다.

Kakao raw artifact, screenshot hash, collector version/commit, raw/sanitized payload hash, artifact path는 이 저장소에서 확정 근거를 확인하지 못했으므로 `NOT_CAPTURED/UNVERIFIED` 상태를 유지한다. Kakao WALK/publictraffic raw retention은 Provider Policy Registry 검토 전까지 default-deny이며 persistent raw storage·cross-session cache·redistribution에 사용하지 않는다.

AI/ML 정책 snapshot은 다음과 같다. 제1 AI capability는 `JR_TEMPORAL_QUANTILE_MODEL`이며, BUS/SUBWAY leg의 residual/WAIT quantile source로만 사용한다. H100/Jupyter/Notebook 환경은 training plane으로만 사용하고 production PWA/API/collector/Journey Engine과 직접 연결하지 않는다. Runtime은 hash·feature schema·evaluation report가 있는 `ModelArtifactManifest`만 반입해 `SYS-008` inference adapter로 serving한다. 해당 모델이 evaluation·latency·artifact portability·ops cost Gate를 통과하지 못하면 같은 feature schema의 `QUANTILE_GBDT_BASELINE`으로 축소하고, 이 backup도 미달하면 empirical/timetable/reference fallback으로 전환하며 AI serving claim을 하지 않는다. 어떤 경우에도 AI output을 최종 `P(on_time)`, Recommended Departure, canonical mapping, provider evidence, Reforecast reason code의 단독 source로 쓰지 않는다.

---

## 2026-08-24 Product Reframing Decision

이 절은 2026-08-23 Evidence의 판정을 수정하지 않고 **제품 목표와 Minimum Release 범위만 새로 고정**한다. 기존 `REJECTED`, `CONFIRMED`, `PENDING_RECONCILIATION`, `NOT_CAPTURED`, `NO_VALID_EVENT` 등은 그대로 유지한다.

| Decision ID | 결정 | 상태 | 영향 문서 | Evidence 관계 |
|---|---|---|---|---|
| D-260824-001 | 제품 핵심 질문을 A `언제 출발해야 하는가`와 B `지금 출발하면 도착 가능한가`로 고정 | FIXED | Service/IA/REQ | 사용자 확정 방향; 과거 evidence 삭제 없음 |
| D-260824-002 | A는 historical-only `Departure P50/P90`을 제공 | FIXED | Service/IA/REQ | 성숙도는 신규 CG-004/History artifact Gate 필요 |
| D-260824-003 | B는 `departAt=now`에서 Arrival P50/P90, P(on_time)을 제공 | FIXED | Service/IA/REQ | realtime context 없을 때 historical-only fallback 허용, limitation 필수 |
| D-260824-004 | `targetReliability`와 단일 `{p*}% Recommended Departure`는 MR에서 폐기 | FIXED | IA/REQ/API/ENT | 기존 260823 의미는 retired trace 보존 |
| D-260824-005 | Journey Start/수동 UserEvent/수동 Reforecast는 MR에서 제외 | FIXED | Service/IA/REQ/API/State/AC | 기존 ID는 `RETIRED_FROM_MR` |
| D-260824-006 | 향후 tracking은 수동 버튼보다 GPS/location 기반 자동 상태 추론 연구를 우선 | FUTURE_GPS_RESEARCH | Service/IA | 현재 구현 가능성/정확도 Evidence 없음; API/state 선행 설계 금지 |
| D-260824-007 | B realtime feature는 identity·timestamp·freshness가 검증된 항목만 사용 | FIXED | REQ/Data/AI | leading vehicle/congestion/headway는 현재 UNVERIFIED |
| D-260824-008 | 비지도학습은 traffic regime 탐색용 optional feature; 실제 영향량은 outcome hold-out으로 검증 | FIXED | Service/REQ/AI | unsupervised만으로 weight/delay claim 금지 |
| D-260824-009 | realtime/AI model은 historical baseline 대비 hold-out uplift가 있어야 claim 승격 | FIXED | REQ/CG | 미달 시 historical/quantile baseline fallback |

### 신규 Evidence Gap Register

| Gap | 2026-08-24 상태 | 필요한 검증 | 미해소 시 동작 |
|---|---|---|---|
| 요일×시간대×route/node historical distribution support | `INSUFFICIENT/NOT_PROFILED` | multi-window collection, grouping/support profile | pooling/reference 또는 NOT_COMPUTED |
| Departure P50/P90 hold-out coverage | `NOT_STARTED` | target-time replay/hold-out | A claim 제한/NOT_COMPUTED |
| current vehicle congestion availability | `UNVERIFIED` | raw schema/coverage/timestamp | feature 미사용 |
| leading vehicle deterministic identity | `UNVERIFIED` | route+direction+order+time validation | feature 미사용 |
| leading vehicle congestion availability | `UNVERIFIED` | identity 후 raw field coverage | feature 미사용 |
| vehicle gap/headway feature | `UNVERIFIED` | position/order/timestamp/cadence profile | feature 미사용 |
| realtime feature incremental value | `NOT_STARTED` | B0/B1/B2 temporal hold-out | historical-only/B1 fallback |
| unsupervised traffic regime value-add | `OPTIONAL/NOT_STARTED` | U1 vs B2 comparison | 기능 cut |
| GPS automatic boarding/alighting inference | `FUTURE_GPS_RESEARCH` | privacy/battery/location-quality/labeled journey study | MR 미포함 |

### 과거 Evidence 해석 가드

- `congetion`이 관측 context 후보라는 기존 문장은 **앞차 혼잡도를 안정적으로 얻을 수 있거나 예측에 유효하다는 증거가 아니다**.
- Bus Arrival↔Position join 가능성은 **leading vehicle ordering/headway feature correctness를 자동 증명하지 않는다**.
- Subway/Bus residual builder 1건 사례는 historical distribution maturity나 model training sufficiency가 아니다.
- 2026-08-23 Kakao/Seoul quota·mapping·WALK 판정은 A/B 제품 구조 변경과 무관하게 기존 scope 그대로 유지한다.
- 2026-08-24 문서에서 신규 factual claim이 필요한 경우 이 Decision Sheet 또는 별도 Evidence artifact가 먼저 갱신되어야 한다.

---

## 2026-08-24 v0.2 Product Separation Decision

이 절은 v0.1에서 계산 의미만 A/B로 분리하고 **한 입력·한 API·한 결과 화면으로 묶었던 제품 구조를 supersede**한다. 2026-08-23 Evidence와 v0.1의 데이터/확률 의미·manual tracking retirement 결정은 변경하지 않는다.

| Decision ID | 결정 | 상태 | Supersedes / 영향 |
|---|---|---|---|
| D-260824-010 | `출발 시간 추천`과 `도착 가능성 계산`은 서로 다른 사용 시점의 **독립 제품 기능**이다 | FIXED | v0.1 `Dual Analysis` product coupling superseded |
| D-260824-011 | Home에서 두 기능은 별도 CTA로 진입하고 별도 input/result route를 가진다 | `SUPERSEDED_FROM_V0.3` | v0.1 SCR-01 단일 input→SCR-02 combined result superseded; v0.3에서 Home 자체가 D-260825-001로 재차 superseded |
| D-260824-012 | Departure Recommendation은 약속 전날/사전 계획을 정상 시나리오로 하며 historical-only다 | FIXED | v0.1 A math 의미 유지, product entry 독립화 |
| D-260824-013 | Leave-now Forecast는 출발 직전 독립 사용하며 `departAt=server now`로 고정한다 | FIXED | v0.1 B math 의미 유지, Departure result prerequisite 금지 |
| D-260824-014 | v0.1 API-002 `/journeys/analyze` combined snapshot은 `RETIRED_FROM_MR`; API-011/012로 분리한다 | FIXED | Requirements/API |
| D-260824-015 | v0.1 ENT-011 unified request와 ENT-015 combined result는 retired; typed request/result entity를 분리한다 | FIXED | Requirements/Entity |
| D-260824-016 | Evidence/Share는 공통 component/endpoint를 쓸 수 있으나 **한 analysisType의 metric만** 포함한다 | FIXED | IA/REQ |
| D-260824-017 | 한 기능은 다른 기능의 analysisId/result/session을 prerequisite로 요구하거나 자동 continuation하지 않는다 | FIXED | UI/API/State/AC |
| D-260824-018 | Route/cache/Historical Artifact/Simulation library는 내부 공유 가능하나 shared product request/result로 노출하지 않는다 | FIXED | Architecture |

### v0.2 Canonical User Journeys — v0.3 history

**Departure Recommendation** (v0.3에서 entry가 D-260825-001로 대체됨)
`Service Home → Departure Input → Departure Result → Evidence/Share`

**Leave-now Forecast** (v0.3에서 entry가 D-260825-001로 대체됨)
`Service Home → Leave-now Input → Leave-now Result → Evidence/Share`

두 Journey 사이에 자동 transition은 없다는 원칙과, 같은 약속을 전날/당일에 각각 사용해도 동일 세션 continuation이 아니라는 원칙은 v0.3에서도 유지된다. entry 화면(Service Home)만 v0.3 Shared Input Shell로 대체됐다.

### v0.2 Canonical API / Entity Decision

| Type | Request API | Request Entity | Result Entity | 허용 metric (v0.2) | v0.3 변경 |
|---|---|---|---|---|---|
| `DEPARTURE_RECOMMENDATION` | API-011 `/departure-recommendations` | ENT-029 | ENT-031 | Departure P50/P90 | milestone projection(ENT-034) 추가 |
| `LEAVE_NOW_FORECAST` | API-012 `/leave-now-forecasts` | ENT-030 | ENT-032 | departAt, P(on_time), Arrival P50/P90 | `P(on_time)` 제거(D-260825-005), milestone projection(ENT-034) 추가 |

공통 ENT-033 `AnalysisRecord`의 `analysisType`은 immutable이다. 다른 type metric이 response/Share/Evidence에 포함되면 contract defect다. 이 불변조건은 v0.3에서도 그대로 유지된다.

### v0.2 Evidence 해석 가드

- 기능 분리는 **사용자 확정 product decision**이며 새로운 provider/data evidence를 필요로 하지 않는다.
- historical/realtime maturity, Kakao mapping, quota, residual support, realtime feature availability의 기존 상태는 그대로다.
- v0.2 architecture가 realtime feature availability나 AI uplift를 새로 증명하지 않는다.
- `출발 시간 추천을 전날 사용할 수 있다`는 product usage contract이지, 먼 미래까지 임의 horizon을 보장한다는 뜻이 아니다. 실제 supported horizon은 provider/artifact profile Gate를 따른다.

### Superseded v0.1 표현

다음 표현은 2026-08-24 v0.1 history로는 존재할 수 있으나 v0.2/v0.3 active Service/IA/Requirements 계약에서는 사용하지 않는다.

- `한 번 입력하고 두 결과 계산`
- `Dual Analysis`
- `SCR-02 A/B Decision Result`
- `출발 시간과 도착 가능성 계산` 단일 CTA
- API-002 combined A/B response
- ENT-015 combined Departure+Arrival result

v0.2/v0.3 정본에서 위 표현이 active 정책으로 발견되면 문서 정합성 오류다.

---

## 2026-08-25 v0.3 Entry / Milestone / URL Share Superseding Decision

이 절은 팀 회의에서 도출된 수정점을 반영한다. 2026-08-23 Evidence, 2026-08-24 v0.1 Product Reframing, v0.2 Product Separation Decision은 소급 변경하지 않는다. v0.3은 **entry 구조, milestone(경유포인트) 표시, 공유 방식, 기능 독립성 강화, Arrival 핵심 계약 축소**만 새로 고정한다 — 새로운 provider/data evidence를 필요로 하지 않는다.

| Decision ID | 결정 | 상태 | Supersedes / 영향 문서 |
|---|---|---|---|
| D-260825-001 | 앱 진입을 `Splash → Shared Input Shell`로 단순화한다. 두 기능은 같은 물리 Input Shell을 Tab으로 공유하되 Tab 전환 자체는 분석을 실행하지 않는다 | FIXED | v0.2 Service Home(D-260824-011의 entry 부분)을 `SUPERSEDED_FROM_V0.3`으로 대체; Service/IA APP-SPLASH,SCR-01/07 |
| D-260825-002 | selected route에서 사용자에게 의미 있는 경유포인트(milestone)별 `보통/여유` 시간 projection을 결과에 추가한다. Departure는 P50-plan/P90-plan 조건의 milestone median, Arrival은 departAt=now checkpoint의 Q0.50/Q0.90이다 | FIXED | 신규 계약; Service/IA/REQ ENT-034, SYS-012, REQ-119/120/123, CG-011 |
| D-260825-003 | 결과 공유를 opaque token 기반 URL create/copy/public read-only로 canonical화한다. 이미지 저장·카카오톡 직접 전송은 canonical Share가 아니다 | FIXED | 신규 MUST 승격; Service/IA/REQ API-007/008, REQ-080~082,121,122 |
| D-260825-004 | Shared Input Shell 위에서도 두 기능의 submit/API/result isolation을 명시적으로 강화한다 — Tab 전환이 API 호출이나 hidden cross-type field 전송을 만들지 않는다 | FIXED | D-260824-016/017 원칙을 Shared Input Shell 맥락에 재확인; BR-094~098 |
| D-260825-005 | Leave-now Forecast(Arrival) 핵심 계약에서 mandatory `targetArrivalAt`과 user-facing `P(on_time)`을 제거한다. 과거 trace는 `RETIRED_FROM_MR`로 보존하고 active API/UI/Share에서 사용하지 않는다 | FIXED | v0.2 D-260824-003/D-260824-002 Canonical API Decision의 B 허용 metric 축소; REQ-013,115; ENT-030,032; AC-090 |

### v0.3 Canonical User Journeys

**Departure Recommendation**
`APP-SPLASH → Shared Input Shell(Departure Tab) → Departure Result(+Milestones) → Evidence/URL Share`

**Leave-now Forecast (도착 시간 계산)**
`APP-SPLASH → Shared Input Shell(Arrival Tab) → Arrival Result(+Milestones) → Evidence/URL Share`

두 Journey 사이에 자동 transition은 없다. Tab 전환은 값을 유지할 수 있으나 새 analysis를 만들지 않으며, 각 submit만 새 `analysisId`를 생성한다.

### v0.3 Canonical API / Entity Decision

| Type | Request API | Request Entity | Result Entity | 허용 metric | 금지 필드 |
|---|---|---|---|---|---|
| `DEPARTURE_RECOMMENDATION` | API-011 | ENT-029 | ENT-031 | Departure P50/P90 + `milestones[]`(ENT-034) | Arrival 계열, `onTimeProbability` |
| `LEAVE_NOW_FORECAST` | API-012 | ENT-030 | ENT-032 | `departAt`, Arrival P50/P90 + `milestones[]`(ENT-034), `realtimeContextCoverage` | `targetArrivalAt`, Departure 계열, `onTimeProbability` |

### v0.3 Evidence 해석 가드

- entry 단순화(Splash→Shared Input Shell), milestone projection, URL Share 승격, `P(on_time)`/mandatory targetArrivalAt 제거는 모두 **사용자(팀) 확정 product decision**이며 새로운 provider/data evidence를 필요로 하지 않는다.
- 2026-08-23 Evidence(Kakao mapping/quota, Bus/Subway identity·Actual 표본, timestamp tooling 한계 등)의 성숙도는 v0.3 entry/UI 변경으로 소급 승격되지 않는다. milestone projection이 화면에 존재한다는 사실이 milestone 정확도/coverage가 검증됐다는 뜻은 아니다(CG-011 참고).
- Milestone Projection은 versioned engine output(SYS-012)만 사용하며, FE가 leg 평균/quantile을 임의로 누적해 만든 시간은 evidence가 아니다.
- URL Share token은 owner capability와 분리된 public read-only 권한이며, 원본 analysis 존재를 증명하는 evidence로 사용하지 않는다.

### Superseded v0.2 표현

다음 표현은 2026-08-24 v0.2 history로는 존재할 수 있으나 v0.3 active Service/IA/Requirements 계약에서는 사용하지 않는다.

- `Service Home에서 두 기능 카드 선택`
- Arrival 결과의 `P(on_time)` / 정시 도착 확률
- Arrival 입력의 mandatory `targetArrivalAt`
- `이미지 저장 및 카카오톡 전송`을 canonical Share로 표현
- 경유지 시간을 FE가 leg 평균/P90 단순 합산으로 생성하는 구현

v0.3 정본에서 위 표현이 active 정책으로 발견되면 문서 정합성 오류다.
