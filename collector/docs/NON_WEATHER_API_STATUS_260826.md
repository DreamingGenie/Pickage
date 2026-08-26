# 비날씨 API 호출 상태 보고서 — 2026-08-26

## 1. 판정 범위

- 테스트 시각: `2026-08-26 09:16~09:19 KST`
- 제외 범위: 기상청 ASOS·초단기실황·초단기예보 전체
- 키 점검: 값을 출력하지 않는 일회성 점검에서 `DATA_GO_BUS_API_KEY`, `SEOUL_OPEN_API_KEY`, `SEOUL_SUBWAY_REALTIME_KEY`, `T_DATA_API_KEY`가 모두 설정돼 있고 버스 키에 `%HH` 형태가 없음을 확인했다. 이 형식 점검 결과는 SQLite에 저장하지 않았다.
- 호출 원칙: live 호출이 허용된 source만 1회 호출하고 transport retry는 사용하지 않았다.
- HTTP source: 공식 upstream이 HTTPS를 제공하지 않아 `--allow-insecure-http`로 호출했다. 키는 로그·보고서에서 마스킹되지만 네트워크 구간은 암호화되지 않는다.

이 보고서의 `호출 가능`은 **현재 키로 HTTP 응답·업무 성공 코드·파싱 가능한 실제 행을 한 번 확보했다**는 뜻이다. 장기 가용성, 모델 품질, 저장 권한 또는 운영 SLA를 뜻하지 않는다.

## 2. 실제 호출 결과

| 분류 | source_id | 실제 결과 | 행 수 | Run ID | 판정 |
| --- | --- | --- | ---: | --- | --- |
| 호출 가능 | `bus-arrival` | HTTP `200`, 업무코드 `0` | 104 | `aa97d21dcd2c48edae3052efc63bda9f` | 변경한 버스 키가 버스도착정보 서비스에서 정상 동작함 |
| 호출 가능 | `subway-arrival` | HTTP `200`, 업무코드 `INFO-000` | 8 | `d99d8a105ae045d9bd6f29271ec0b503` | `강남` 역별 도착정보 계약 smoke 성공 |
| 호출 가능 | `subway-position` | HTTP `200`, 업무코드 `INFO-000` | 63 | `e48330bde0e24e1e8348f0adf2855918` | `2호선` 열차 위치정보 계약 smoke 성공 |
| 호출 불가 | `bus-position` | HTTP `401` | 0 | `14d223eccc6f4e878d0bbcc97e367882` | 같은 키로 버스도착은 성공하므로 키 문자열 자체보다 `15000332` 서비스별 활용신청·권한 문제 가능성이 큼 |
| 호출 불가 | `subway-arrival-all` | HTTP `307` redirect; `Location`은 DB에 미저장 | 0 | `2d86b5b252374c5ab8f5edba075dd0db` | collector는 path credential 재전송 방지를 위해 redirect를 따르지 않음. 현재 키로 일괄 API 정상 응답을 확보하지 못함 |
| 불안정·사용 불가 | `tdata-bis-history` | 현재 `20초 Timeout`; 같은 날 앞선 호출은 HTTP `200`과 본문 `[]` | 0 | `2f1d404ea0c249928bf88487bf781c24` | gateway가 현재 응답하지 않고, 응답했을 때도 실제 행이 없어 모델 입력으로 사용할 수 없음 |
| 불안정·사용 불가 | `tdata-road-hourly` | 현재 `20초 Timeout`; 같은 날 앞선 호출은 HTTP `404` | 0 | `4c11447634dd441aa9d9ecf5cb10c5e9` | gateway 불안정과 `T-DATA-1015` 활용권한을 모두 확인해야 함 |

### 호출 가능 3개 API의 모델 적용 상태

| source_id | 계약 smoke | 실시간 feature | Actual label·과거 모델 | 남은 검증 |
| --- | --- | --- | --- | --- |
| `bus-arrival` | `USABLE` | `CONDITIONAL` | ETA 예측값이므로 Actual label 아님 | 장기 freshness·coverage, 내부 ID mapping, 저장정책 |
| `subway-arrival` | `USABLE` | `CONDITIONAL` | 단일 snapshot 기준 Actual `CONDITIONAL`, 과거 모델 `UNUSABLE` | 반복 poll 전이, 내부 ID mapping, 장기 profile |
| `subway-position` | `USABLE` | `CONDITIONAL` | 위치 snapshot이며 도착시간 Actual 아님 | 제공시각 보강, 반복 poll, 내부 ID mapping |

따라서 세 API는 **호출·파싱 계약은 통과**했지만, 아직 장기 수집이나 확률모델 학습에 바로 투입할 상태는 아니다.

## 3. live 호출을 보류한 API

아래 source는 키가 없어서 실패한 것이 아니다. 공식 일일 한도 또는 계정 기준 운영 상한이 확인되지 않아 collector가 `UNCONFIRMED` quota로 fail-closed 차단한다. 실제 호출 결과가 없으므로 `된다/안 된다`로 판정하지 않는다.

| 계열 | source_id | 현재 수집 경로 |
| --- | --- | --- |
| 서울 도로·사고 | `seoul-road-realtime`, `seoul-incidents` | API 호출 보류 |
| 지하철 공지 | `subway-alerts` | API 호출 보류 |
| 정적·집계 교통 | `seoul-bus-ridership-monthly`, `seoul-subway-ridership-monthly`, `seoul-subway-congestion-quarterly`, `seoul-station-travel-time`, `seoul-bus-route-master` | API smoke 보류, 파일 수집 가능 |
| 대중교통 경로 | `seoul-path-location`, `seoul-path-subway`, `seoul-path-bus`, `seoul-path-mixed` | 요청 시점 API 호출 보류 |

`seoul-subway-timetable-file`, `seoul-subway-transfer-file`은 API가 아니라 포털 파일 source이므로 이 호출 판정에서 제외했다.

## 4. 제공 서버 상태와 전송 제약

아래 연결시간·redirect 목적지는 같은 점검 턴에서 본문과 자격증명을 출력하지 않은 별도 probe로 관측했다. collector SQLite/report에는 이 probe를 저장하지 않았으므로, 앞 절의 Run ID 기반 결과와 구분한다.

- `ws.bus.go.kr`, `swopenAPI.seoul.go.kr`, `openapi.seoul.go.kr:8088`의 HTTPS 무인증 probe는 각각 `10~15초 Timeout`이었다. 현재 공식 계약과 collector 설정 모두 HTTP upstream을 사용한다.
- `subway-arrival-all`의 `307`은 같은 `swopenapi.seoul.go.kr`의 HTTP 위치를 가리켰고 query는 없었다. 실제 `Location` path는 credential 보호를 위해 출력·저장하지 않았다.
- T-DATA HTTPS gateway는 TLS 연결은 약 `0.07초`에 완료됐지만, 무인증 probe와 인증 호출 모두 응답 body 없이 Timeout이 발생했다. 이 관측만으로 영구 장애 또는 키 오류라고 단정하지 않는다.
- 서울 Open API 계열은 HTTP `200`만으로 성공 판정하지 않고 `RESULT.CODE` 또는 `errorMessage.code`까지 확인해야 한다.

## 5. quota 확인

`2026-08-26 KST` ledger에서 이번 비날씨 점검을 포함한 누적 실제 시도 수는 다음과 같다.

| quota pool | attempt_count | reserved_count |
| --- | ---: | ---: |
| `data-go-bus-arrival` | 1 | 0 |
| `data-go-bus-position` | 1 | 0 |
| `seoul-subway-realtime-shared` | 3 | 0 |
| `tdata-shared` | 5 | 0 |

모든 reservation은 `RELEASED` 상태이며 남은 예약량은 없다. `tdata-shared=5`에는 앞선 같은 날 사전점검 3회와 이번 Timeout 점검 2회가 포함된다.

## 6. 다음 조치

1. 공공데이터포털에서 [버스위치정보조회 서비스 `15000332`](https://www.data.go.kr/data/15000332/openapi.do)의 활용신청이 현재 키에 연결됐는지 확인한다. 버스도착정보 `15000314`는 이미 정상이다.
2. 서울 열린데이터광장에서 [지하철 실시간 도착정보 일괄 `OA-15799`](https://data.seoul.go.kr/dataList/OA-15799/A/1/datasetView.do)의 전용 키·사용 가능 기능 범위를 확인한다.
3. T-DATA에서 `T-DATA-1068`, `T-DATA-1015`를 각각 활용신청했는지 확인하고, `1068`의 실제 조회 가능 `stdrDe`를 확인한다. T-DATA는 개발자 활용신청 기준 하루 최대 1,000건이다.
4. `UNCONFIRMED` source는 공식 quota 또는 승인된 내부 상한을 확보한 뒤 local quota override로만 live 호출을 연다.
5. 위 권한 문제를 해결한 뒤 성공한 실시간 API를 여러 시점에 반복 수집해 freshness, 중복, 차량·열차 상태 전이와 내부 ID mapping을 검증한다.

## 7. 공식 근거

- [공공데이터포털 버스도착정보 `15000314`](https://www.data.go.kr/data/15000314/openapi.do)
- [공공데이터포털 버스위치정보 `15000332`](https://www.data.go.kr/data/15000332/openapi.do)
- [서울 지하철 실시간 도착정보 `OA-12764`](https://data.seoul.go.kr/dataList/OA-12764/F/1/datasetView.do)
- [서울 지하철 실시간 도착정보 일괄 `OA-15799`](https://data.seoul.go.kr/dataList/OA-15799/A/1/datasetView.do)
- [서울 지하철 실시간 열차 위치정보 `OA-12601`](https://data.seoul.go.kr/dataList/OA-12601/A/1/datasetView.do)
- [T-DATA Open API 이용안내](https://t-data.seoul.go.kr/userguide/guideopenapi.do)
