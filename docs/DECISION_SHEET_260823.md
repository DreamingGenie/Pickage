# 2026-08-23 Decision Sheet

> Journey Reliability Evidence Resolution Pack(`docs/history/0823_plan_fix/00~07`) 실행 결과. Sunday `END` service day 기준. 모든 항목은 `provider×endpoint×OD/corridor×window×service day×adapter version` 범위로만 유효하다.

## 실행한 API calls

| Provider | Endpoint | 호출 수 | 결과 |
|---|---:|---:|---|
| Kakao Map REST API | publictraffic | 9(HTTP 400 검증 실패 1건 포함) | HTTP 200×8(business status OK×6, EQUAL_POINTS×1, NO_RESULTS×1), HTTP 400×1(param 이름 오류로 재시도 전 실패, Kakao 콘솔 사용량에는 포함됨) |
| Kakao Map REST API | walk | 4 | 전부 HTTP 200 OK |
| data.go.kr | getPathInfoByBusNSub(mixed-route) | 8 | 참고용 부가 evidence(오늘 실행 계획에는 없었으나 provider 확인 과정에서 수집됨) — 본 Decision Sheet의 정책 결정에는 반영하지 않음 |
| TMAP pedestrian | routes/pedestrian | 5 | 참고용 부가 evidence(위와 동일한 사유) |
| Seoul Bus Arrival(`getArrInfoByRouteAll`) | busRouteId=100100001 | 60 | 정상 완료 |
| Seoul Bus Position(`getBusPosByRouteSt`) | busRouteId=100100001 | 60 | 정상 완료 |
| Seoul Subway Arrival(`realtimeStationArrival`) | 안국/교대/역삼 개별 | 45×3=135 | 정상 완료(최초 시도의 `"역명1\|역명2\|역명3"` 파이프 결합 문법은 무효 — 45+45=90건 낭비 후 개별 호출로 재실행) |
| Seoul Subway Position(`realtimePosition`) | 3호선/2호선 개별 | 90×2=180 | 정상 완료(동일 사유로 최초 90건 낭비 후 재실행) |

**지하철 quota 산술 재검토(2026-08-23 검수 반영)**: 위 표의 성공 호출만 합산해도 Arrival 135 + Position 180 = **315건**이며, 낭비 호출(파이프 결합 문법 오류로 인한 재시도 전 실패분)은 이 표와 별도다. Service Plan/Requirements에 기록된 "2026-08-23 실사용 225/1,000"은 이 315건과 산술이 맞지 않는 것으로 확인됐다. 어느 쪽도 임의로 폐기하지 않고, 정확한 총 호출 수는 provider console 최종 스냅샷과 raw request log를 대조해야 확정할 수 있으므로 현재 상태를 `PENDING_RECONCILIATION`으로 표기한다. 세 문서(Service Plan, Requirements, Decision Sheet)는 재대사 전까지 이 상태값을 동일하게 사용한다.

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
| Kakao candidate 반복 안정성 | UNVERIFIED | 동일 window 2회 + 전날(08-22) 대비 재호출, 15개 후보 signature 완전 일치 | `FIXED` (tested OD 범위, reference evidence) | Demo Corridor OD, 2026-08-22~23 publictraffic | §1.4, §12 | — | AC-053 PASS | 다른 OD/corridor는 미검증; selected route 근거로 사용하지 않음 |
| Kakao WALK point 재현성 | CONDITIONAL | ACCESS leg 295m/323s가 전날과 완전 동일 | `FIXED` (tested pair 범위, WALK provider evidence) | Route A ACCESS pair | §12 | — | AC-056 PASS | 다른 pair는 미검증 |
| Kakao canonical mapping | CONDITIONAL | bus/subway/mixed 3개 topology candidate 전부 stop=name만, vehicle=name/type만; ID 필드 없음 | `REJECTED` (future route-provider payload 구조적 한계) | Kakao publictraffic 응답 스키마 전체 | §6.1, §12, §21.3, §22.2 | Open Decisions | AC-055 REJECTED, REQ-009 | 외부 name-based crosswalk 별도 설계 전에는 route-provider 재시도 무의미. WALK-only 사용에는 blocker 아님 |
| Kakao total/step 시간 포함관계 | CONDITIONAL | candidate 0(SUBWAY) gap 887s vs 경계WALK 829s(58s 잔차); candidate 2(BUS_AND_SUBWAY) gap 422s vs 437s(15s 이내) | `CONDITIONAL` 유지, candidate 0은 `PARTIALLY_EXPLAINED`, candidate 2는 `HIDDEN_WALK_STRONGLY_SUPPORTED` | 테스트한 2개 publictraffic candidate만 | §6.1, §12 | — | AC-054 PARTIAL | 58s 잔차의 원인(WAIT/환승/속도가정 차이) 미상. Minimum Release 결과 시간에 배분 금지 |
| Kakao 지리 범위 | 암묵적으로 서울 한정 가정 | 부산 좌표에서도 정상 200/OK, 3개 후보 반환 | `NEW_FACT` — Kakao는 서울 경계를 스스로 제한하지 않음 | publictraffic 전체 | §12 | — | REQ-001, BR-001 | product 입력단 지역 제한은 Requirements/IA에 반영됨. 구현·테스트에서 `UNSUPPORTED_GEOGRAPHY` 처리 확인 필요 |
| Kakao entitlement/quota | UNCONFIRMED | PM 제공 콘솔 스크린샷(2026-08-23 15:16 KST): publictraffic 9/1,000, walk 4/1,000 — 이 세션의 실제 호출 수와 정확히 일치 | `CONFIRMED` | Kakao Map REST API 앱 전체, 2026-08-23 | §18.4, §6.1 | — | AC-057 | billing usage history와 공식 overage 정책은 아래 별도 행에서 분리 관리 |
| Kakao billing usage history | UNCONFIRMED | PM 제공 콘솔 스크린샷(2026-08-23 15:23 KST, "유료 사용량" 화면, app `pjt_map` ID 1471189): 이번 달 유료 호출 0건(성공 0/실패 0), 무료 호출만 15건 — 2026-08-23 무료 13건(=publictraffic 9+walk 4), 2026-08-22 무료 2건(=baseline 1+1)과 정확히 일치 | `CONFIRMED` — 과금 발생 이력 없음 | Kakao Map REST API 앱 전체, 2026-08-01~08-23 | §18.4 | — | — | 과금 발생 이력 0건은 overage 단가·정책 확인과 별도 사실 |
| Kakao official overage policy | 별도 사실 | Kakao 공식 쿼터 문서: 첫 활성화 앱 무료 일 1,000회, 초과 10원/건 | `VERIFIED_OFFICIAL` | Kakao Map REST API | §18.4 | — | — | 콘솔 스크린샷 근거가 아니라 공식 문서 근거. 실제 billing history와 분리 |
| Seoul data.go.kr Bus Arrival/Position 승인 한도 | UNCONFIRMED | PM 제공 콘솔 스크린샷(2026-08-23 15:30 KST): `[개발계정]서울특별시_버스도착정보조회 서비스`의 `getArrInfoByRouteAllList` 등 4개 상세기능 각각 1,000/day, `[개발계정]서울특별시_버스위치정보조회 서비스`의 `getBusPosByRouteStList` 등 5개 상세기능 각각 1,000/day. 오늘 각각 60회씩만 사용(6%) | `CONFIRMED` — 서비스별 독립 1,000/day, 공유 풀 아님 | data.go.kr 계정, 활용기간 2026-08-21~2028-08-21 | §18.4 | — | AC-049 | 상세기능별 독립 pool이라는 판정은 콘솔 화면 판독에 근거하며, 원본 스크린샷을 보관하지 않아 제3자가 동일 결론을 재검증할 수 없다(M-04와 동일 사유) |
| Seoul 열린데이터광장 지하철 승인 한도 | UNCONFIRMED | PM 제공 콘솔 스크린샷(2026-08-23 15:31 KST, "인증키 안내"): 공식 정책 텍스트로 "실시간 지하철 오픈API는 1일 1,000회만 호출 가능(인증키 1개당)" 확인, 지하철인증키 상태 "정상". 일반인증키(Seoul Open Data 나머지 API)는 호출 "횟수" 제한 없음(1회당 최대 1,000건 조회 page cap만) | `CONFIRMED` | 서울 열린데이터광장 계정 전체 | §18.4 | — | AC-049 | 활용사례 갤러리 등록 여부(현재 미등록) — 등록 시 지하철도 무제한 전환 가능, release 전 검토 대상 |
| `KAKAO_ROUTE_PROVIDER_GATE` 종합 | 4개 조건 중 반복안정성만 부분 확인 | 위 4개 항목 판정 종합 | `REJECTED` 종합(mapping 조건 구조적 실패) | future Kakao publictraffic Primary route-provider 승격 | §6.1 | — | REQ-009 | mapping crosswalk 재설계 전에는 route-provider Gate 재도전 무의미. 당시 snapshot wording은 `ROUTE_A_ONLY + KAKAO_WALK_ONLY`였으며, 현재 활성 필드와의 관계는 아래 Post-decision Reconciliation을 따른다 |
| Bus target-stop(안국역6번출구, ord=21) Actual | IMMATURE | 2026-08-23 30분 window, sectOrd=21 필터링 결과 유효 `0→1` 전이 0건(다른 정류장에서는 93건) | `NO_VALID_EVENT` (이번 window) | busRouteId=100100001, 2026-08-23 12:47~13:17 KST | §21.3 | — | — | 더 길거나 여러 window로 재시도; sectOrd↔staOrd 대응 자체도 재검증 필요 |
| Subway station×line Actual(4개) | COMPONENT | 45분 window: 안국(3호선) 16건, 교대(3호선측) 16건, 교대(2호선측) 1건, 역삼(2호선) 1건 유효 `arvlCd=1` 확보; trainNo join 전부 100% | `CONDITIONAL` (2개 역은 표본 확대, 2개 역은 표본 부족) | 4개 station×line, 2026-08-23 13:31~14:16 KST | §21.3 | — | — | 2호선 두 역의 낮은 포착률 원인 미상 — window/interval 조정 후 재확인 |
| data.go.kr collector 인코딩 | 알려지지 않음 | `mixed_route_spike.py` 저장 raw의 한글 필드(정류장/노선명)가 mojibake; 숫자/ID/좌표 필드는 정상 | `NEW_FACT` (DQ 발견) | 오늘 호출분 전체 | — | — | — | collector encoding 수정은 별도 개발 작업으로 이관 |
| Route A ↔ Kakao 후보 구조 차이 | 서술만 있고 좌표 대조 없음 | 오늘 호출한 Kakao publictraffic 8건의 모든 candidate·모든 step의 path point를 검사한 결과, 승인 Route A 탑승점(춘추문, 126.97965,37.58308) 반경 100m 이내를 지나는 step이 0건 | `FIXED` — Kakao 응답은 승인 Route A 구조를 아예 후보로 제시하지 않음(우연 일치 불가능) | 오늘 호출한 8개 publictraffic 응답 | §22.1 | — | — | 없음(이 OD 범위에서는 충분히 확정적) |
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
| 문서가 참조하는 artifact 상대 경로 | `NOT_CAPTURED`(원본 이미지 미보관, 위 §Kakao entitlement/quota 단락 참조) |

## 문서 확인

- 현행 root 기획 문서는 `SERVICE_PLAN_260823.md`, `REQUIREMENTS_SPEC_260823.md`, `IA_SCREEN_SPEC_260823.md`, `DECISION_SHEET_260823.md` 4개다. 260822 정본과 실행 지시/증거 파일은 `docs/history/0823_plan_fix/`에 보존한다.
- 2026-08-23 Decision Sheet 작성 이후 신규 API 호출 없음. 이후 변경은 문서 정합성 정리와 검수 반영에 한정한다.
- production code·개발 설정·배포 변경 없음 확인: docs 기획 문서와 docs 예시 설정 외 파일은 수정하지 않는다. 실제 secret은 Git 추적 대상에 포함하지 않는다.

## Post-decision Reconciliation

이 Decision Sheet의 Evidence 행은 2026-08-23 당시 관측과 PM 콘솔 snapshot을 보존한다. 따라서 `REJECTED`, `CONFIRMED`, `PENDING_RECONCILIATION`, `NOT_CAPTURED` 같은 과거 판정과 수집 사실은 소급 변경하지 않는다.

현재 정본 정책은 coverage와 selected route를 분리한다. PM 확정 후 Minimum Release의 목표 snapshot은 `geographyCoverage=SEOUL_ONLY`, `routeSearchCoverage=ARBITRARY_OD_DISCOVERY`, `selectedRoutePolicy=PROVIDER_FIRST_SUPPORTED`, `walkProviderMode=KAKAO_MAP_WALK`, `validationAndDemoScope=ROUTE_A_DEMO_ONLY`이다. 최종 시연은 Route A만 사용한다. 2026-09-14 팀 회의에서 남은 일정상 D2 Gate가 불가능하다고 판단하면 `selectedRoutePolicy=APPROVED_ROUTE_A_ONLY`의 Route A D1 fallback으로 probability/Recommended Departure claim을 축소하되, 서울 임의 OD structure-only 결과는 유지한다. Kakao publictraffic의 2026-08-23 payload-only route-provider 승격은 여전히 `KAKAO_ROUTE_PROVIDER_GATE`에서 `REJECTED`이며, D2 목표 달성에는 REQ-105 안전한 자동 canonicalization crosswalk가 필요하다.

과거 행의 `ROUTE_A_ONLY + KAKAO_WALK_ONLY` wording은 deprecated composite snapshot이다. 이를 현재 API/UI/manifest 필드로 기록할 때는 위 필드들로 분해한다. `PROVIDER_FIRST_SUPPORTED`는 이제 future 문구가 아니라 D2 목표 selected-route 정책이며, `APPROVED_ROUTE_A_ONLY`는 demo/fallback 정책으로만 사용한다.

Kakao publictraffic 후보의 canonical mapping이 `EXACT/UNAMBIGUOUS`이고 model Gate가 통과하면 서울 임의 OD에서도 probability와 Recommended Departure를 계산한다. `UNAMBIGUOUS` 이상은 name normalization, 좌표 근접성, 버스 노선/지하철 line, 방향·순서 조건으로 후보가 하나로 좁혀질 때만 인정한다. Recommended Departure는 후보 출발시각 5분 grid/coarse-to-fine 재평가를 통과한 경우에만 표시한다. `PARTIAL/FAILED` 또는 model 미달이면 SCR-02 structure-only fallback 결과로 표시하고 probability/Recommended Departure는 `NOT_COMPUTED`로 유지한다. 승인된 Route A manifest/hash/topology가 깨진 경우만 `ROUTE_MANIFEST_INVALID`로 분리한다.

Kakao raw artifact, screenshot hash, collector version/commit, raw/sanitized payload hash, artifact path는 이 저장소에서 확정 근거를 확인하지 못했으므로 `NOT_CAPTURED/UNVERIFIED` 상태를 유지한다. Kakao WALK/publictraffic raw retention은 Provider Policy Registry 검토 전까지 default-deny이며 persistent raw storage·cross-session cache·redistribution에 사용하지 않는다.
