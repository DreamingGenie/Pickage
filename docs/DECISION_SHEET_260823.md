# 2026-08-23 Decision Sheet

> Journey Reliability Evidence Resolution Pack(`docs/00~07`) 실행 결과. Sunday `END` service day 기준. 모든 항목은 `provider×endpoint×OD/corridor×window×service day×adapter version` 범위로만 유효하다.

## 실행한 API calls

| Provider | Endpoint | 호출 수 | 결과 |
|---|---:|---:|---|
| Kakao Map REST API | publictraffic | 8 | 전부 HTTP 200; business status OK×6, EQUAL_POINTS×1, NO_RESULTS×1 |
| Kakao Map REST API | walk | 5 | 전부 HTTP 200 OK |
| data.go.kr | getPathInfoByBusNSub(mixed-route) | 8 | 참고용 부가 evidence(오늘 실행 계획에는 없었으나 provider 확인 과정에서 수집됨) — 본 Decision Sheet의 정책 결정에는 반영하지 않음 |
| TMAP pedestrian | routes/pedestrian | 5 | 참고용 부가 evidence(위와 동일한 사유) |
| Seoul Bus Arrival(`getArrInfoByRouteAll`) | busRouteId=100100001 | 60 | 정상 완료 |
| Seoul Bus Position(`getBusPosByRouteSt`) | busRouteId=100100001 | 60 | 정상 완료 |
| Seoul Subway Arrival(`realtimeStationArrival`) | 안국/교대/역삼 개별 | 45×3=135 | 정상 완료(최초 시도의 `"역명1\|역명2\|역명3"` 파이프 결합 문법은 무효 — 45+45=90건 낭비 후 개별 호출로 재실행) |
| Seoul Subway Position(`realtimePosition`) | 3호선/2호선 개별 | 90×2=180 | 정상 완료(동일 사유로 최초 90건 낭비 후 재실행) |

data.go.kr(Bus 계열)과 Seoul Subway 키의 승인 일일 한도는 이번 세션에서 포털 콘솔로 확인하지 않았다(계정 자체 로그인·화면 확인 없이 실 호출만 수행). Kakao 키의 entitlement/billing 콘솔도 확인하지 않았다.

## Decision Sheet

| Item | Before | Evidence | Decision | Scope | Service Plan | IA | Requirements | Remaining gate |
|---|---|---|---|---|---|---|---|---|
| Kakao candidate 반복 안정성 | UNVERIFIED | 동일 window 2회 + 전날(08-22) 대비 재호출, 15개 후보 signature 완전 일치 | `FIXED` (tested OD 범위) | Demo Corridor OD, 2026-08-22~23 | §1.4, §12 | — | AC-053 PASS | 다른 OD/corridor는 미검증 |
| Kakao WALK point 재현성 | CONDITIONAL | ACCESS leg 295m/323s가 전날과 완전 동일 | `FIXED` (tested pair 범위) | Route A ACCESS pair | §12 | — | AC-056 PASS | 다른 pair는 미검증 |
| Kakao canonical mapping | CONDITIONAL | bus/subway/mixed 3개 topology candidate 전부 stop=name만, vehicle=name/type만; ID 필드 없음 | `REJECTED` (payload 구조적 한계) | Kakao publictraffic 응답 스키마 전체 | §6.1, §12, §21.3, §22.2 | 1156행 | AC-055 REJECTED, REQ-009 | 외부 name-based crosswalk 별도 설계 전에는 재시도 무의미 |
| Kakao total/step 시간 포함관계 | CONDITIONAL | candidate 0(SUBWAY) gap 887s vs 경계WALK 829s(58s 잔차); candidate 2(BUS_AND_SUBWAY) gap 422s vs 437s(15s 이내) | `CONDITIONAL` 유지, candidate 0은 `PARTIALLY_EXPLAINED`, candidate 2는 `HIDDEN_WALK_STRONGLY_SUPPORTED` | 테스트한 2개 candidate만 | §6.1, §12 | — | AC-054 PARTIAL | 58s 잔차의 원인(WAIT/환승/속도가정 차이) 미상 |
| Kakao 지리 범위 | 암묵적으로 서울 한정 가정 | 부산 좌표에서도 정상 200/OK, 3개 후보 반환 | `NEW_FACT` — Kakao는 서울 경계를 스스로 제한하지 않음 | publictraffic 전체 | §12 | — | — | product 입력단 지역 제한 설계 필요(REQ 미반영, 후속 검토) |
| Kakao entitlement/quota | UNCONFIRMED | 콘솔 미확인(오늘 범위 밖) | `NO_CHANGE` (여전히 UNCONFIRMED) | — | §18.4(무변경) | — | AC-057 HOLD | 콘솔 entitlement/billing 확인 필요 |
| `KAKAO_ROUTE_GATE` 종합 | 4개 조건 중 반복안정성만 부분 확인 | 위 4개 항목 판정 종합 | `REJECTED` 종합(mapping 조건 구조적 실패) | — | §6.1 | — | REQ-009 | mapping crosswalk 재설계 전에는 Gate 재도전 무의미; `ROUTE_A_ONLY` 유지 |
| Bus target-stop(안국역6번출구, ord=21) Actual | IMMATURE | 2026-08-23 30분 window, sectOrd=21 필터링 결과 유효 `0→1` 전이 0건(다른 정류장에서는 93건) | `NO_VALID_EVENT` (이번 window) | busRouteId=100100001, 2026-08-23 12:47~13:17 KST | §21.3 | — | — | 더 길거나 여러 window로 재시도; sectOrd↔staOrd 대응 자체도 재검증 필요 |
| Subway station×line Actual(4개) | COMPONENT | 45분 window: 안국(3호선) 16건, 교대(3호선측) 16건, 교대(2호선측) 1건, 역삼(2호선) 1건 유효 `arvlCd=1` 확보; trainNo join 전부 100% | `CONDITIONAL` (2개 역은 표본 확대, 2개 역은 표본 부족) | 4개 station×line, 2026-08-23 13:31~14:16 KST | §21.3 | — | — | 2호선 두 역의 낮은 포착률 원인 미상 — window/interval 조정 후 재확인 |
| data.go.kr collector 인코딩 | 알려지지 않음 | `mixed_route_spike.py` 저장 raw의 한글 필드(정류장/노선명)가 mojibake; 숫자/ID/좌표 필드는 정상 | `NEW_FACT` (DQ 발견) | 오늘 호출분 전체 | — | — | — | collector encoding 수정은 이번 세션 범위 밖(개발 코드 변경 금지) — 별도 작업으로 이관 |

## 아직 하루로 해소할 수 없었던 항목과 이유

- Kakao entitlement/billing 콘솔 확인: 포털 로그인·화면 캡처가 필요한 작업이며 이번 세션은 실 API 호출에 집중함(`MULTI_DAY_REQUIRED`가 아니라 단순 미실행 — 다음 세션에서 즉시 가능)
- Bus/Subway 승인 일일 한도의 포털 재확인: 지난 세션(08-23 앞선 대화)에서 이미 확인했으나 이번 Decision Sheet 작성 시점에 재검증하지 않음
- Bus target-stop Actual 표본 부족: 한 창(30분)의 우연 공백일 수 있어 `MULTI_DAY_REQUIRED`
- Subway 2호선 두 역의 낮은 이벤트 포착률 원인: 이번 데이터만으로는 원인 특정 불가(`MULTI_DAY_REQUIRED` 또는 poll interval 조정 후 재시도)
- 표준 검증 사다리(V1~V3) 관련 항목 전부: 오늘 하루로 승격 불가, `MULTI_DAY_REQUIRED` 유지

## 문서 확인

- `SERVICE_PLAN_260823.md`, `IA_SCREEN_SPEC_260823.md`, `REQUIREMENTS_SPEC_260823.md` 생성 완료(260822 정본은 보존)
- 오늘 추가 API 호출 없이 세 문서만 최종 정리했다는 확인: 위 표 작성 이후 신규 호출 없음
- production code·개발 설정·배포 변경 없음 확인: docs/ 이외 파일은 수정하지 않았고, `docs/history/.../scripts/spikes/*.py`는 실행만 했을 뿐 코드를 수정하지 않음(단, `scripts/spikes/.env.local` 배치는 기존 `.env.example` 규격대로 시크릿 값만 채운 로컬 설정이며 git에 포함되지 않음)
