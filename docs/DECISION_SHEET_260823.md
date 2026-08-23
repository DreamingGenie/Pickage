# 2026-08-23 Decision Sheet

> Journey Reliability Evidence Resolution Pack(`docs/00~07`) 실행 결과. Sunday `END` service day 기준. 모든 항목은 `provider×endpoint×OD/corridor×window×service day×adapter version` 범위로만 유효하다.

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

data.go.kr(Bus 계열)과 Seoul Subway 키의 승인 일일 한도는 이번 세션에서 포털 콘솔로 확인하지 않았다(계정 자체 로그인·화면 확인 없이 실 호출만 수행).

**Kakao entitlement/quota — PM이 제공한 콘솔 스크린샷 2장(2026-08-23 15:16 KST)으로 확인 완료.** "일간 쿼터 사용량 > 오늘" 화면 기준:

| Endpoint | 오늘 사용량 | Limit |
|---|---:|---:|
| `/route-open/openapi/v1/publictraffic.json` | 9 | 1,000 |
| `/route-open/openapi/v1/walk.json` | 4 | 1,000 |

이 세션이 실제로 호출한 수(publictraffic 9건 — HTTP 400 실패 1건 포함, walk 4건)와 정확히 일치한다. 두 endpoint 모두 프로젝트 앱에 1,000/day entitlement가 실제로 부여되어 있음이 콘솔로 직접 확인됐다(`KAKAO_ROUTE_GATE` 조건 1 = **`CONFIRMED`**). billing/overage 단가나 초과 정책 화면은 이번 스크린샷에 없어 별도 사실로 남긴다.

## Decision Sheet

| Item | Before | Evidence | Decision | Scope | Service Plan | IA | Requirements | Remaining gate |
|---|---|---|---|---|---|---|---|---|
| Kakao candidate 반복 안정성 | UNVERIFIED | 동일 window 2회 + 전날(08-22) 대비 재호출, 15개 후보 signature 완전 일치 | `FIXED` (tested OD 범위) | Demo Corridor OD, 2026-08-22~23 | §1.4, §12 | — | AC-053 PASS | 다른 OD/corridor는 미검증 |
| Kakao WALK point 재현성 | CONDITIONAL | ACCESS leg 295m/323s가 전날과 완전 동일 | `FIXED` (tested pair 범위) | Route A ACCESS pair | §12 | — | AC-056 PASS | 다른 pair는 미검증 |
| Kakao canonical mapping | CONDITIONAL | bus/subway/mixed 3개 topology candidate 전부 stop=name만, vehicle=name/type만; ID 필드 없음 | `REJECTED` (payload 구조적 한계) | Kakao publictraffic 응답 스키마 전체 | §6.1, §12, §21.3, §22.2 | 1156행 | AC-055 REJECTED, REQ-009 | 외부 name-based crosswalk 별도 설계 전에는 재시도 무의미 |
| Kakao total/step 시간 포함관계 | CONDITIONAL | candidate 0(SUBWAY) gap 887s vs 경계WALK 829s(58s 잔차); candidate 2(BUS_AND_SUBWAY) gap 422s vs 437s(15s 이내) | `CONDITIONAL` 유지, candidate 0은 `PARTIALLY_EXPLAINED`, candidate 2는 `HIDDEN_WALK_STRONGLY_SUPPORTED` | 테스트한 2개 candidate만 | §6.1, §12 | — | AC-054 PARTIAL | 58s 잔차의 원인(WAIT/환승/속도가정 차이) 미상 |
| Kakao 지리 범위 | 암묵적으로 서울 한정 가정 | 부산 좌표에서도 정상 200/OK, 3개 후보 반환 | `NEW_FACT` — Kakao는 서울 경계를 스스로 제한하지 않음 | publictraffic 전체 | §12 | — | — | product 입력단 지역 제한 설계 필요(REQ 미반영, 후속 검토) |
| Kakao entitlement/quota | UNCONFIRMED | PM 제공 콘솔 스크린샷(2026-08-23 15:16 KST): publictraffic 9/1,000, walk 4/1,000 — 이 세션의 실제 호출 수와 정확히 일치 | `CONFIRMED` | Kakao Map REST API 앱 전체, 2026-08-23 | §18.4, §6.1 | — | AC-057 | 없음 — billing도 아래 행에서 확정됨 |
| Kakao billing/overage | UNCONFIRMED | PM 제공 콘솔 스크린샷(2026-08-23 15:23 KST, "유료 사용량" 화면, app `pjt_map` ID 1471189): 이번 달 유료 호출 0건(성공 0/실패 0), 무료 호출만 15건 — 2026-08-23 무료 13건(=publictraffic 9+walk 4), 2026-08-22 무료 2건(=baseline 1+1)과 정확히 일치 | `CONFIRMED` — 과금 발생 이력 없음 | Kakao Map REST API 앱 전체, 2026-08-01~08-23 | §18.4 | — | — | 없음 |
| `KAKAO_ROUTE_GATE` 종합 | 4개 조건 중 반복안정성만 부분 확인 | 위 4개 항목 판정 종합 | `REJECTED` 종합(mapping 조건 구조적 실패) | — | §6.1 | — | REQ-009 | mapping crosswalk 재설계 전에는 Gate 재도전 무의미; `ROUTE_A_ONLY` 유지 |
| Bus target-stop(안국역6번출구, ord=21) Actual | IMMATURE | 2026-08-23 30분 window, sectOrd=21 필터링 결과 유효 `0→1` 전이 0건(다른 정류장에서는 93건) | `NO_VALID_EVENT` (이번 window) | busRouteId=100100001, 2026-08-23 12:47~13:17 KST | §21.3 | — | — | 더 길거나 여러 window로 재시도; sectOrd↔staOrd 대응 자체도 재검증 필요 |
| Subway station×line Actual(4개) | COMPONENT | 45분 window: 안국(3호선) 16건, 교대(3호선측) 16건, 교대(2호선측) 1건, 역삼(2호선) 1건 유효 `arvlCd=1` 확보; trainNo join 전부 100% | `CONDITIONAL` (2개 역은 표본 확대, 2개 역은 표본 부족) | 4개 station×line, 2026-08-23 13:31~14:16 KST | §21.3 | — | — | 2호선 두 역의 낮은 포착률 원인 미상 — window/interval 조정 후 재확인 |
| data.go.kr collector 인코딩 | 알려지지 않음 | `mixed_route_spike.py` 저장 raw의 한글 필드(정류장/노선명)가 mojibake; 숫자/ID/좌표 필드는 정상 | `NEW_FACT` (DQ 발견) | 오늘 호출분 전체 | — | — | — | collector encoding 수정은 이번 세션 범위 밖(개발 코드 변경 금지) — 별도 작업으로 이관 |
| Route A ↔ Kakao 후보 구조 차이 | 서술만 있고 좌표 대조 없음 | 오늘 호출한 Kakao publictraffic 8건의 모든 candidate·모든 step의 path point를 검사한 결과, 승인 Route A 탑승점(춘추문, 126.97965,37.58308) 반경 100m 이내를 지나는 step이 0건 | `FIXED` — Kakao 응답은 승인 Route A 구조를 아예 후보로 제시하지 않음(우연 일치 불가능) | 오늘 호출한 8개 publictraffic 응답 | §22.1 | — | — | 없음(이 OD 범위에서는 충분히 확정적) |
| Collector round-trip latency 계측 | 확인 안 됨 | `bus_*_spike.py`/`subway_*_spike.py`의 `requested_at`/`received_at`은 둘 다 HTTP 응답을 받은 뒤 `storage.SpikeResult()` 생성 시점에 동시 stamping됨(dataclass default_factory 2회 호출이 거의 같은 시각) → 오늘 수집된 240건 전부 latency=0.00~0.001s로 기록되어 있어 실제 request-boundary latency로 볼 수 없음. 임시로 작성한 Kakao 호출 스크립트도 응답 전/후 시각을 분리 기록하지 않아 동일한 한계를 가짐 | `BLOCKED_TOOLING`(collector 자체의 timestamp 설계 한계, 이번 세션에서 코드 수정 금지 규칙과 충돌해 고치지 않음) | 오늘 사용한 모든 collector | — | — | — | collector가 `requested_at`을 호출 직전, `received_at`을 응답 직후로 분리 기록하도록 고치는 것 자체가 후속 작업(코드 변경 필요) |
| Out-of-order (source-time reversal) | 확인 안 됨 | receive 순서 기준 source timestamp 단조성 검사: bus position 13개 차량 계열, subway arrival 82개 station×train 계열 전부 역전 0건 | `NO_REVERSAL_OBSERVED`(이번 window) | 오늘 수집한 bus position + subway arrival 전체 | — | — | — | 표본이 늘어나면 재확인 필요(하루 한 window로 일반화 금지) |
| Subway Prediction→Actual Residual 실측 예시 | 미계산 | 안국(3호선) 열차 3166: 13:31:20 관측 시점 `barvlDt=210s` 예측(예상 도착 13:34:50) vs 실제 Actual interval (13:34:10, 13:35:05], mid=13:34:37.5, width=55s → signed residual L/M/U = −40s/−12.5s/+15s | `FIXED`(builder correctness 시연, 1개 사례) | 안국역 3호선, train 3166, 2026-08-23 13:31~13:35 KST | — | — | AC 없음(오늘 신규 발견, REQUIREMENTS에 반영 안 함) | 표본 1건 — support 주장 금지, 여러 window·여러 train으로 확대 필요 |
| Bus Prediction→Actual Residual 실측 예시 | 미계산 | staOrd=21(target)은 예측 60건 존재했으나 대응하는 Actual event가 이번 window에 없어(위 표 참조) target residual은 여전히 계산 불가. **General 예시(비-target)**: vehId=106024177, 12:54:23 관측 시점 `traTime=58s`(staOrd=13) 예측(예상 도착 12:55:21) vs 관측된 stopFlag `0→1` Actual interval (12:55:04, 12:55:32], mid=12:55:18 → signed residual L/M/U = −17s/−3s/+11s | `FIXED`(builder correctness 시연, target 아닌 1개 general 사례) — target(staOrd=21)은 `NO_VALID_EVENT` 유지 | busRouteId=100100001, non-target stop, 2026-08-23 12:54~12:56 KST | — | — | — | 이 예시의 stop이 staOrd=13과 정확히 일치하는지는 vehId+시간 근접으로만 추정했고 sectOrd로 직접 검증하지 않음 — target-stop 표본 확대가 여전히 필요 |
| Bus WAIT raw row 특성 | 미확인 | position raw 673행, 고유 차량 13대, 동일 차량 dataTm 중복 190행(28.2%) — snapshot 상당수가 신규 source 갱신 없이 반복됨 | `NEW_FACT`(dependence 근거) | busRouteId=100100001, 2026-08-23 30분 window | — | — | — | raw row를 independent support로 쓰지 않는다는 기존 정책의 실측 근거로만 사용; event-unit dependence 정량화(자기상관 등)는 미실시 |
| Kakao entitlement/billing 콘솔 | 미확인 | 이번 세션은 실 API 호출에 집중했고 developers.kakao.com 콘솔 로그인/캡처는 하지 않음 | `UNCONFIRMED`(변경 없음) | — | §18.4(무변경) | — | AC-057 | 콘솔 확인은 다음 단계에서 즉시 가능 |

## 아직 하루로 해소할 수 없었던 항목과 이유

- **Bus/Subway 승인 일일 한도의 포털 재확인**: 이번 Decision Sheet 작성 세션에서는 재검증하지 않음(과거 세션에서 확인한 적 있으나 그 결과물은 이후 되돌려짐 — 사실상 미확인 상태로 취급해야 함)
- **Bus target-stop(staOrd=21) Actual 표본 부족**: 한 창(30분)의 우연 공백일 수 있어 `MULTI_DAY_REQUIRED`. General(비-target) residual 예시는 확보했으나 target 표본은 여전히 0건
- **Collector round-trip latency**: collector의 `requested_at`/`received_at` 설계 자체가 실제 latency를 담지 못함 — 코드 수정이 필요한 `BLOCKED_TOOLING`이며 이번 세션의 "코드 수정 금지" 규칙과 충돌해 고치지 않음
- **Subway 2호선 두 역의 낮은 이벤트 포착률 원인**: 이번 데이터만으로는 원인 특정 불가(`MULTI_DAY_REQUIRED` 또는 poll interval 조정 후 재시도)
- **Bus WAIT event-unit dependence 정량화**: raw row 중복률(28.2%)만 확인했고 자기상관 등 정량 dependence 분석은 하지 않음
- 표준 검증 사다리(V1~V3) 관련 항목 전부: 오늘 하루로 승격 불가, `MULTI_DAY_REQUIRED` 유지

## 문서 확인

- `SERVICE_PLAN_260823.md`, `IA_SCREEN_SPEC_260823.md`, `REQUIREMENTS_SPEC_260823.md` 생성 완료(260822 정본은 보존)
- 오늘 추가 API 호출 없이 세 문서만 최종 정리했다는 확인: 위 표 작성 이후 신규 호출 없음
- production code·개발 설정·배포 변경 없음 확인: docs/ 이외 파일은 수정하지 않았고, `docs/history/.../scripts/spikes/*.py`는 실행만 했을 뿐 코드를 수정하지 않음(단, `scripts/spikes/.env.local` 배치는 기존 `.env.example` 규격대로 시크릿 값만 채운 로컬 설정이며 git에 포함되지 않음)
