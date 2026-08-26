# API 수집·사용 가능성 검증기

이 도구는 API 응답을 가져오는 것에서 끝나지 않고, **어떤 대상·기간·활용 목적에서 실제로 사용할 수 있는지**를 함께 판정한다. 제공 방식이 파일인 데이터는 CSV/XLSX를 별도 `FILE` evidence로 적재해 API 응답처럼 가장하지 않는다.

판정 범위는 다음 조합이다.

```text
provider × endpoint × purpose × target × collection window × adapter/schema/policy version
```

따라서 픽스처 한 건이 `CONTRACT_SMOKE=USABLE`이어도 `HISTORICAL_MODEL`이나 `REALTIME_FEATURE`가 자동으로 사용 가능해지지 않는다.

## 모노레포 컴포넌트 경계

수집기 코드, 설정, API 조사 문서, 테스트, 환경변수 예시와 로컬 실행 결과는 모두 `collector/` 안에 둔다.

```text
collector/
├─ config/             # source, quota, 보관 정책
├─ docs/api & data/    # API 조사 문서와 활용가이드
├─ tests/              # 단위·계약 테스트와 fixture
├─ var/                # 로컬 DB·리포트, Git 제외
├─ .env.example
└─ *.py                # 수집·검증 구현
```

## 지원 소스

```powershell
python -m collector sources
```

현재 설정에는 24개 수집·검증 단위가 들어 있다. `sources` 출력의 `source_kind`는 다음 의미다.

| Source kind | 실행 경로 | 의미 |
| --- | --- | --- |
| `API` | `collect` | 호출형 API |
| `FILE` | `collect-file` | 포털에서 내려받은 버전 파일만 사용 |
| `HYBRID` | `collect-file` 우선, `collect`는 보조 smoke/cross-check | 파일이 실제 원천이고 Open API는 계약 확인·교차검증용 |

기존 실시간·이력 호출형 소스는 다음과 같다.

| Source ID | 용도 후보 | 핵심 입력 |
| --- | --- | --- |
| `bus-arrival` | 실시간 ETA feature | `busRouteId` |
| `bus-position` | 실시간 위치, interval Actual 후보 | `busRouteId`, `startOrd`, `endOrd` |
| `subway-arrival` | 역별 ETA·상태전이 | `station` |
| `subway-arrival-all` | 전체 역 도착정보 profile | 없음 |
| `subway-position` | 노선별 열차 위치 | `line` |
| `tdata-bis-history` | 버스 Actual·운행시간 이력 | `stdrDe`, `routeId` |
| `tdata-road-hourly` | 시간대별 도로 외생변수 | `stndDt` |
| `seoul-road-realtime` | 실시간 도로 feature | `link_id` |
| `seoul-incidents` | 돌발 이벤트 feature | 없음 |
| `subway-alerts` | 지하철 운행장애 이벤트 | 없음 |
| `kma-asos-hourly` | 과거 날씨 공변량 | 날짜·시간·`stnIds` |
| `kma-ultra-short-nowcast` | 현재 날씨 공변량 | `base_date`, `base_time`, `nx`, `ny` |
| `kma-ultra-short-forecast` | 미래 날씨 공변량 | `base_date`, `base_time`, `nx`, `ny` |

추가 조사 결과를 반영한 소스는 다음과 같다.

| Source ID | Source kind | 주 수집 경로 | 올바른 해석 |
| --- | --- | --- | --- |
| `seoul-bus-ridership-monthly` | `HYBRID` | 월별 CP949 CSV | 월별 교통카드 실측 집계, 실시간 아님 |
| `seoul-subway-ridership-monthly` | `HYBRID` | 전체 이력 CP949 CSV | 월별 실측 집계, 48개 시간 컬럼·중복 검증 필수 |
| `seoul-subway-congestion-quarterly` | `HYBRID` | 분기 XLSX/CSV | 요일·방향별 historical 평균, 실시간 혼잡 아님 |
| `seoul-station-travel-time` | `HYBRID` | 기준 CSV | 역간 표준 계획 소요시간, 관측 지연 아님 |
| `seoul-bus-route-master` | `HYBRID` | versioned XLSX | 노선 ID crosswalk, 운행정보 아님 |
| `seoul-subway-timetable-file` | `FILE` | versioned CSV | 계획 시간표, 실제 도착·예측값 아님 |
| `seoul-subway-transfer-file` | `FILE` | versioned CP949 CSV | 정적 환승 기준 소요시간 |
| `seoul-path-location` | `API` | 요청 시점 호출 | 장소 후보 조회, 통계 polling 대상 아님 |
| `seoul-path-subway` | `API` | 요청 시점 호출 | 지하철 경로 후보, 관측 운행시간 아님 |
| `seoul-path-bus` | `API` | 요청 시점 호출 | 버스 경로 후보, 관측 운행시간 아님 |
| `seoul-path-mixed` | `API` | 요청 시점 호출 | 버스·지하철 경로 후보, 관측 운행시간 아님 |

월별 승하차의 48개 시간대 컬럼과 혼잡도의 39개 30분 컬럼은 위치가 아니라 **헤더명과 기대 개수**로 검사한다. 음수 거리·승하차·혼잡 값, 형식이 틀린 날짜·시각·ID, 복합키 중복·revision, 필수 ID 결측도 리포트에 분리된다. CSV 데이터 행에 헤더보다 많은 셀이 있으면 새 컬럼이나 구분자 오류를 숨기지 않고 해당 파일의 파싱을 실패시킨다.

## 빠른 실행

1. `collector/.env.example`을 복사해 `collector/.env.local`을 만들고 필요한 key만 넣는다.
2. 먼저 네트워크를 쓰지 않는 fixture 검증을 실행한다.

```powershell
python -m collector validate-file `
  --source bus-position `
  --input collector/tests/fixtures/bus_position_success.json `
  --param busRouteId=100100001 `
  --param startOrd=1 `
  --param endOrd=30
```

3. 포털에서 받은 실제 CSV/XLSX는 `collect-file`로 읽는다. 이 명령은 파일 hash·크기·파싱 결과·중복·스키마 판정을 SQLite와 report에 남긴다. raw/normalized 본문 저장은 아래 정책이 승인된 경우에만 수행한다.

```powershell
python -m collector collect-file `
  --source seoul-bus-route-master `
  --input "C:\path\서울시버스노선ID정보(20260804).xlsx"
```

월별 버스 승하차 CSV 예시:

```powershell
python -m collector collect-file `
  --source seoul-bus-ridership-monthly `
  --input "C:\path\CARD_BUS_TIME_202607.csv" `
  --param USE_YM=202607
```

4. 유효키와 검토된 quota가 있으면 live contract smoke를 실행한다.

```powershell
python -m collector collect `
  --source tdata-bis-history `
  --param stdrDe=20260824 `
  --param routeId=100100001
```

서울 버스·서울 열린데이터광장·실시간 지하철의 공식 upstream은 조사 시점에 HTTP만 확인됐다. 해당 source는 credential 전송 위험을 인지한 경우에만 명시적으로 허용한다. 수집기는 redirect를 따르지 않아 query/path credential이 다른 origin으로 전달되는 것을 막는다.

`seoul-station-travel-time`의 선택 필터 `SBWY_ROUT_LN`, `SBWY_STNS_NM`은 query string이 아니라 공식 문서 순서대로 URL path에 붙는다. 역명만 단독으로 주면 세그먼트가 잘못 해석될 수 있으므로 거부한다.

```powershell
python -m collector collect `
  --source bus-position `
  --param busRouteId=100100001 `
  --param startOrd=1 `
  --param endOrd=30 `
  --count 10 `
  --interval 30 `
  --allow-insecure-http
```

`--count`와 `--interval`은 한 실행 안에서 시계열 snapshot을 모은다. `stopFlag 0→1` 또는 지하철 `arvlCd != 1→1` 상태전이가 있을 때만 interval-censored Actual 후보를 센다. ETA 숫자 하나는 Actual로 승격하지 않는다. 지하철 상행·하행은 identity와 중복 키에서 서로 다른 이벤트로 취급한다.

## 로그 읽기

stdout은 명령 결과 JSON 하나만 출력한다. 진행·오류 로그는 stderr에만 기록하므로 파이프라인에서 stdout을 그대로 `ConvertFrom-Json`으로 읽을 수 있다.

```powershell
New-Item -ItemType Directory -Path collector/var -Force | Out-Null
python -m collector `
  --log-level DEBUG `
  --log-format json `
  collect-file `
  --source seoul-bus-route-master `
  --input "C:\path\routes.xlsx" `
  1> collector/var/result.json 2> collector/var/collector.log.jsonl
```

주요 이벤트는 `collection.started/finished/failed`, `collection.finalization_failed`, `poll.started/finished`, `http.attempt_finished`, `http.retry_scheduled`, `business.retry_scheduled`, `quota.reserved/consumed/released`, `quota.expired_recovered`, `file.parsed`, `validation.finished`다. 모든 실행 로그는 `run_id`, `source_id`, 필요 시 `poll_index`, `exchange_id`, `reservation_id`로 연결된다. URL은 안전한 endpoint만 남기고 API key·원문 body·업무 메시지 전체는 로그에 기록하지 않는다. API key는 포맷된 출력뿐 아니라 Python `LogRecord`의 extra metadata에도 넣지 않는다. 경로 API의 검색어·출발/도착 좌표는 안전한 URL·파라미터에서 마스킹하고 target은 hash만 보존한다. `DEBUG` traceback도 credential 치환 후 출력한다.

## 판정 의미

| 판정 | 의미 |
| --- | --- |
| `USABLE` | 요청한 목적과 테스트 범위의 필수 검사를 통과했다. 다른 노선·기간·목적으로 일반화할 수 없다. |
| `CONDITIONAL` | 구조는 사용할 수 있지만 장기 profile, freshness/support 기준, ID mapping, live evidence 등이 부족하다. |
| `UNUSABLE` | HTTP/업무코드/파싱/핵심 schema/identity/time 또는 목적별 저장 정책에 hard blocker가 있다. |

주요 검사 결과는 `PASS`, `WARN`, `FAIL`, `NOT_EVALUATED`로 기록한다. raw polling 행 수와 중복 제거 후 `effective_event_count`를 구분한다.

## 저장과 정책

기본 실행 위치는 다음과 같다.

```text
collector/var/
├─ collector.sqlite3   # 요청 메타데이터, 업무코드, hash, quota, 판정
├─ reports/            # 목적별 JSON report
├─ raw/                # 정책이 허용된 경우만 생성
└─ normalized/         # 정책이 허용된 경우만 생성
```

`collector/var/`와 `collector/.env.local`은 Git에서 제외된다. 기본 `provider_policies.json`은 raw와 normalized 영구 저장을 모두 거부한다. HTTP 200이나 secret 제거만으로 보관 권한이 생기지 않기 때문이다.

정책 검토가 끝난 source만 `collector/config/provider_policies.local.example.json`을 복사해 `provider_policies.local.json`에서 로컬로 허용한다. `ALLOW_LOCAL_ONLY`에는 실제 승인 식별자인 `review_ticket`과 ISO 날짜 `reviewed_at`이 모두 필요하며, 임의의 `ALLOW_*` 값이나 예제 placeholder는 거부된다. 이 override 파일도 Git에서 제외된다. 파라미터 이름과 관계없이 credential 값은 run/HTTP 메타데이터에서 마스킹한다. raw/normalized 안에 실제 credential의 원문·URL 인코딩·이중 URL 인코딩 표현이 발견되면 허용 정책이어도 저장을 거부한다. 검증 리포트에는 정책 전체의 SHA-256이 남는다.

일일 한도가 확인된 버스 API는 서비스별 1,000회, 실시간 지하철 API들은 공유 pool 1,000회, ASOS는 서비스 pool 10,000회로 등록돼 있다. 기상청 단기예보 15084084의 초단기실황·초단기예보는 공식 개발계정 트래픽 10,000회를 하나의 보수적 공유 pool로 사용한다. T-DATA 두 API는 집계 단위가 미공개이므로 하나의 pool에서 보수적으로 총 1,000회를 공유한다. 호출 전에 retry 최악치를 포함한 quota를 SQLite에서 원자적으로 lease 예약하고, 남은 quota가 부족하면 네트워크 요청 전에 중단한다. 예약은 `run_id`와 `reservation_id`로 추적되고 lease 길이는 설정한 timeout·재시도 최악시간보다 길게 계산된다. 프로세스가 강제 종료돼도 만료된 lease를 다음 실행이 원자적으로 회수한다. 제공기관 quota 소진 업무코드가 오면 같은 run의 남은 poll을 중단하고 실행을 `PROVIDER_QUOTA_EXHAUSTED` 실패로 닫는다.

일일 한도나 reset 계약이 확인되지 않은 서울 일반키 API와 대중교통환승경로 API는 기본 live 호출이 차단된다. 계정 콘솔 또는 승인된 내부 운영 상한을 확인한 뒤 `collector/config/quota_limits.local.example.json`을 `quota_limits.local.json`으로 복사하고 `LOCAL_OVERRIDE`, 유한 `daily_limit`, 실제 `review_ticket`, `verified_at`을 기록해야 한다. 같은 credential의 여러 source는 하나의 quota pool을 공유한다. 파일 수집에는 API quota가 적용되지 않는다.

수집 도중 quota 예약, 네트워크, 파싱·개별 관측 저장 단계가 실패해도 run은 `FAILED`와 종료시각으로 닫히며, 최종 저장소가 정상이라면 이미 확보한 관측 범위를 포함한 `DQ-COLLECTION=FAIL`/`UNUSABLE` 리포트가 생성된다. run 최종화·검증·리포트 저장 자체가 실패하면 `collection.finalization_failed`를 남기고 상태를 `FAILED`로 재기록한 뒤 명령을 내부 오류로 종료한다.

## 리포트 조회와 종료 코드

```powershell
python -m collector report <RUN_ID 또는 REPORT_ID>
```

| 종료 코드 | 결과 |
| --- | --- |
| `0` | `USABLE` |
| `2` | `CONDITIONAL` |
| `3` | `UNUSABLE` |
| `4` | 설정·credential·입력 오류 |
| `5` | 예상하지 못한 내부 오류(`DEBUG` 로그 확인) |

## 테스트

```powershell
python -m unittest discover -s collector/tests -t . -v
```

live smoke는 유효키·quota·HTTP 전송 위험 동의가 필요하므로 기본 자동 테스트에 포함하지 않는다. Fixture 성공은 live availability, 장기 support, 모델 성능을 증명하지 않는다.
