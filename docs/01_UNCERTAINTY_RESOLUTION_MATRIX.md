# Uncertainty Resolution Matrix

## 1. 판정 코드

| 코드 | 의미 |
|---|---|
| `FULL_TODAY` | 현재 파일 또는 하루의 bounded experiment로 사실·계약을 확정 가능 |
| `PARTIAL_TODAY` | mechanics·corridor/window 범위는 판정 가능하지만 maturity/일반화는 불가 |
| `DECISION_ONLY` | API 실험이 아니라 PM·보안·운영 결정이 필요 |
| `IMPLEMENTATION_LATER` | 실제 구현·배포·부하·장애 시험 전에는 판정 불가 |
| `MULTI_DAY_REQUIRED` | 독립 window/outcome이 더 필요하여 하루로 claim 승격 불가 |

## 2. Provider·Quota·Route

| 미확정 항목 | 오늘 가능성 | 수행 evidence | 오늘 가능한 최종 판정 | 금지되는 일반화 |
|---|---|---|---|---|
| Kakao 프로젝트 앱 일일 limit | `FULL_TODAY` | console 캡처+전후 counter | endpoint별 `APP_LIMIT_CONFIRMED=1,000/day` | 영구 quota·billing 보장 |
| Kakao overage billing/reset | `DECISION_ONLY` | billing 화면·공식 정책·reset 관측 | 화면이 있으면 각각 별도 상태 | limit 확인만으로 유료 초과 가능 주장 |
| Kakao raw evidence | `FULL_TODAY` | SHA-256, HTTP/Kakao status, secret scan | `RECEIVED_HASH_VERIFIED`; register 등록은 별도 | raw 수신=canonical ingest |
| Kakao candidate 반복 안정성 | `FULL_TODAY` for tested OD/window | 같은 요청 반복 signature | 테스트 OD/window의 stable/variable | 서울 전체 안정성 |
| Kakao publictraffic time gap | `PARTIAL_TODAY` | 15후보 gap 분석+hidden WALK endpoint 비교 | hidden access/egress 가설 supported/rejected/ambiguous | WAIT·WALK 임의 분배 |
| Kakao canonical ID mapping | `PARTIAL_TODAY` | payload schema+서울 crosswalk | tested corridor `MAPPED/AMBIGUOUS/INCOMPLETE` | name-only citywide mapping |
| Kakao Primary 승격 | `PARTIAL_TODAY` | 전체 Gate 결과 | Gate가 모두 통과할 때만 tested-topology 판정 | 한 OD로 `PROVIDER_SUPPORTED` 서울 전역 |
| Route A와 Kakao 01A 후보 동일성 | `FULL_TODAY` | stop sequence/crosswalk | 서로 다른 structural route | 같은 노선명=같은 route |
| TMAP public transit 역할 | `FULL_TODAY` | 최대 3 golden calls+기존 evidence | validation-only 유지/접근 실패 판정 | 일 10회를 runtime primary로 해석 |

## 3. WALK·Transfer·Coordinate

| 미확정 항목 | 오늘 가능성 | 수행 evidence | 오늘 가능한 최종 판정 | 남는 한계 |
|---|---|---|---|---|
| Kakao WALK schema | `FULL_TODAY` | route/leg/step 합·geometry | point/reference contract 확정 | 개인 variance 없음 |
| Provider별 WALK 차이 | `FULL_TODAY` for selected pairs | 동일 좌표 Kakao/TMAP | 각각의 point estimate | 평균·empirical distribution 금지 |
| publictraffic hidden access/final walk | `PARTIAL_TODAY` | route endpoint별 WALK 재조회 | gap 일치/불일치/부분일치 | provider가 명시하지 않으면 semantic guarantee 불가 |
| Coordinate provenance | `FULL_TODAY` for tested points | input/path/stop/station/POI 좌표 role | 역할·source 기록 | station center를 exit/platform으로 승격 금지 |
| BUS_TO_SUBWAY street component | `FULL_TODAY` for point | 동일 pair WALK | provider point/reference | station internal time은 별도 |
| BUS_TO_SUBWAY internal time | `MULTI_DAY_REQUIRED` 또는 `DECISION_ONLY` | 공식 operational source 필요 | source 없으면 `UNMODELED` 유지 | depth→time 환산 금지 |
| FINAL_WALK | `FULL_TODAY` for selected pair | station/alight→POI WALK | provider point/reference | 개인·날씨 variance 없음 |

## 4. Bus Evidence

| 미확정 항목 | 오늘 가능성 | 수행 evidence | 오늘 가능한 최종 판정 | 남는 한계 |
|---|---|---|---|---|
| Bus credential limit | `FULL_TODAY` if portal visible | portal value+counter | approved limit/remaining | 미확인 상태에서 polling 금지 |
| Route A target identity | `FULL_TODAY` | 01A route/stop order | routeId·stId·staOrd 재확인 | 다른 route/corridor 일반화 금지 |
| Bus Actual interval builder | `PARTIAL_TODAY` | target `stopFlag 0→1` | 실제 event에서 interval correctness | event 미포착 시 rule 완화 금지 |
| Bus Prediction→Actual Residual | `PARTIAL_TODAY` | event 전 prediction+Actual interval | signed residual L/M/U 생성 가능 여부 | 성숙한 distribution 아님 |
| Bus WAIT event unit | `PARTIAL_TODAY` | snapshot→vehicle/event grouping | snapshot row와 event unit 분리 | support threshold 확정 불가 |
| Bus WAIT dependence | `PARTIAL_TODAY` | window별 autocorrelation/중복률 | 해당 window dependence profile | independent sample 수 일반화 금지 |
| Mature Bus Reliability | `MULTI_DAY_REQUIRED` | multi-window residual+hold-out | 오늘은 pipeline/window evidence | maturity·confidence claim 금지 |

## 5. Subway Evidence

| 미확정 항목 | 오늘 가능성 | 수행 evidence | 오늘 가능한 최종 판정 | 남는 한계 |
|---|---|---|---|---|
| Subway quota reset/recovery | `FULL_TODAY` if counter/error captured | preflight+counter+첫 정상 call | current credential state | 장기 운영 안정성 |
| station×line identity | `FULL_TODAY` for Route A | 안국 L3, 교대 L3/L2, 역삼 L2 | name-only 혼합 0 | citywide identity claim 금지 |
| Subway Actual interval builder | `PARTIAL_TODAY` | `arvlCd!=1→1`, trainNo join | 실제 transition correctness | 미포착 시 incomplete |
| Subway Residual | `PARTIAL_TODAY` | prediction+Actual interval | selected events의 signed residual | mature distribution 아님 |
| Service day `END` | `FULL_TODAY` | 2026-08-23 Sunday run | Sunday parsing/label | 평일 `DAY`, 토요일 `SAT` 별도 |
| Mature Subway Reliability | `MULTI_DAY_REQUIRED` | service-day·window별 residual+hold-out | component/window evidence | end-to-end claim 금지 |

## 6. Probability·Product·Platform

| 미확정 항목 | 분류 | 이유 | 안전한 현재 상태 |
|---|---|---|---|
| support HIGH/MEDIUM/LOW threshold | `MULTI_DAY_REQUIRED` | independent event 안정성 필요 | `INSUFFICIENT` |
| provider stale threshold | `MULTI_DAY_REQUIRED` | latency/cadence/outage profile 필요 | threshold 미정, metadata 표시 |
| Recommended Departure AVAILABLE | `MULTI_DAY_REQUIRED` | future service set·WAIT·residual·replay 필요 | `HOLD/UNAVAILABLE` |
| whole-Journey calibration | `MULTI_DAY_REQUIRED` | independent actual Journey outcomes 필요 | `COMPONENT_ONLY/CORRIDOR_REPLAY` |
| citywide accuracy/SLA | `MULTI_DAY_REQUIRED` | 별도 coverage/validation program 필요 | claim 금지 |
| analysis/reforecast SLO | `IMPLEMENTATION_LATER` | vertical slice benchmark 필요 | fake progress 금지 |
| partition/watermark/TTL/checkpoint | `IMPLEMENTATION_LATER` | actual stream profile/failure test 필요 | 숫자 미정 |
| EC2 sizing·2-node recovery | `IMPLEMENTATION_LATER` | 사양·배포·worker failure test 필요 | distributed proof 계획만 유지 |
| PWA offline/update/device support | `IMPLEMENTATION_LATER` | 실제 PWA와 기기 필요 | 계약 유지, support claim 금지 |
| Journey/Share TTL·capability expiry | `DECISION_ONLY` | 보안·retention 검토 필요 | 장기 저장·cross-device 복구 금지 |
| analytics retention | `DECISION_ONLY` | 목적·privacy 결정 필요 | raw ID/token/location 금지 |
| ML/AI promotion | `MULTI_DAY_REQUIRED` | baseline·temporal hold-out 필요 | optional/HOLD |

## 7. 하루 성공의 정의

오늘의 성공은 모든 TBD를 억지로 `CONFIRMED`로 바꾸는 것이 아니다. `FULL_TODAY`는 실제 evidence로 닫고, `PARTIAL_TODAY`는 mechanics와 적용 범위를 정확히 줄이며, 하루로 불가능한 claim은 왜 불가능한지 더 명확하게 만드는 것이다.

