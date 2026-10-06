# Bronze 저장 규약

> Jira 93 산출물 · 2026-08-26
> 상위 설계: [DATA_PLATFORM_PLAN_260826.md](../docs/DATA_PLATFORM_PLAN_260826.md)

이 문서만 보고 새 수집기를 규약에 맞게 만들 수 있어야 한다. 구현은 `collector/common/storage.py`가 강제한다.

## 원칙

**Bronze는 증거 보존 계층이다. DB에 넣지 않고 파일로 둔다.**

각 API 분석 문서에 아직 확정되지 않은 필드가 수십 개 있다 — 속도·여행시간 단위 미명시(OA-13291), `rnQcflg=9` 의미 미확정(ASOS), `MM:SS` 해석 미확정(OA-22521), 필드 casing 불일치(T-DATA-1015). 원문을 남기지 않고 파싱 결과만 적재하면 해석이 바뀔 때 **다시 만들 방법이 없다.** 실시간 API는 공식 과거 조회가 없어 backfill도 불가능하다.

원문을 파일로 두면 규칙만 고쳐 Silver부터 재생성할 수 있다. 이를 **재처리 가능성(reprocessability)** 이라 하며 이 규약의 존재 이유다.

## 디렉터리와 파일명

```
data/bronze/<source_key>/[<partition>/]service_date=YYYY-MM-DD/
    <UTC timestamp>_<request_id>.<ext>        원문 그대로 (바이트 무가공)
    <UTC timestamp>_<request_id>.meta.json    수집 메타
```

예시 (파티션 있는 경우 / 없는 경우)

```
data/bronze/bus_position/route=100100022/service_date=2026-08-27/
    20260827T043125443Z_f1b6d6854e6f.xml
    20260827T043125443Z_f1b6d6854e6f.meta.json

data/bronze/subway_arrival_all/service_date=2026-08-27/     ← 파티션 없음
    20260827T020253100Z_8ff4bc3894f1.json
    20260827T020253100Z_8ff4bc3894f1.meta.json
```

| 요소 | 규칙 |
|---|---|
| `source_key` | 수집 대상 식별자. snake_case. 예: `subway_arrival_all`, `bus_position` |
| `partition` | **선택.** 호출 파라미터별로 폴더를 나눠 특정 노선/호선만 쉽게 뽑게 한다. 아래 참조 |
| `service_date` | **운행일**. 달력 날짜가 아니다. 아래 참조 |
| UTC timestamp | `requested_at` 기준 `YYYYMMDDTHHMMSSmmmZ` |
| `request_id` | uuid4 앞 12자리. 원문과 메타를 잇는 키 |
| `ext` | 응답 원문 포맷. `json` / `xml` |

### 파티션 (노선/호선별 폴더 분리)

한 `source_key` 아래에 노선·호선이 수십 개 섞이면, 특정 노선만 뽑을 때 모든 파일의
메타를 열어 확인해야 한다. 그래서 **호출 파라미터를 폴더 한 단계로 내려** 경로만으로
식별되게 한다. `2026-08-27`부터 적용한다.

| source_key | 파티션 | 예 |
|---|---|---|
| `bus_position` · `bus_position_rtid` · `bus_arrival_all` | `route=<busRouteId>` | `route=100100022` |
| `subway_position` | `line=<노선명>` | `line=1호선` |
| `subway_arrival_station` | `station=<역명>` | `station=서울` |
| `subway_arrival_all` | **없음** (1콜에 전 노선) | — |

- 파티션 값은 `CollectionResult.partition`(어댑터가 채움)에서 오며 메타에도 `partition`으로 남긴다.
- 파티션이 없는 source는 기존처럼 `source_key/service_date=.../` 바로 아래에 저장한다.
- Bronze를 읽는 도구는 **깊이 무관 glob(`**/service_date=*/...`)** 을 써서, 파티션 유무가
  섞여 있어도(예: 규약 적용 전후 데이터) 모두 읽는다.

규약 적용 전(2026-08-27 04:37 UTC 이전) 수집분은 파티션 폴더 없이 쌓여 있었으나,
2026-08-27에 3,778건(파일 7,556개)을 현행 구조로 일괄 이관했다. 파티션 값은 메타의
`request_url`에 남은 호출 파라미터에서 역산했고 원문 바이트는 건드리지 않았다.
이동 전량 매핑은 `data/migrations/bronze_partition_20260827T050614Z.json`에 남아 있다.
`subway_arrival_all`은 설계상 파티션이 없어 그대로 뒀다. **이제 Bronze에 파티션 없는
경로는 `subway_arrival_all` 하나뿐이다.** 1회성 작업이라 이관 도구는 남기지 않았다.

### 파티션 키는 반드시 운행일

자정을 넘겨 운행하는 데이터가 있다. **2026-08-26 새벽 1시에 도착한 열차는 2026-08-25 운행일 소속이다.** OA-22522 시각표에는 24시 이상 시각이 4,475건 존재한다.

경계는 **04:00 KST**이며 `collector/common/service_day.py`가 구현한다. 이 값은 provider별 확인 후 확정할 잠정값이지만, **파티션 키를 달력 날짜로 잡으면 나중에 전면 재적재가 필요하므로 첫 적재부터 운행일을 쓴다.**

### 원문은 메타와 분리한다

원문을 메타 JSON 안에 문자열로 넣지 않는다. OA-15799는 1회 응답이 2.8MB이고, JSON 문자열로 감싸면 이스케이프로 크기가 늘고 파싱 비용이 커진다.

## 수집 메타 스키마

```json
{
  "source_key": "subway_arrival_all",
  "provider": "seoul_open_data",
  "endpoint": "realtimeStationArrival/ALL",
  "request_id": "8ff4bc3894f1",
  "service_date": "2026-08-26",
  "request_url": "http://swopenAPI.seoul.go.kr/api/subway/***/json/realtimeStationArrival/ALL",
  "requested_at": "2026-08-26T01:51:55.246099+00:00",
  "received_at": "2026-08-26T01:51:55.363538+00:00",
  "latency_ms": 117.439,
  "http_status": 200,
  "business_code": "INFO-000",
  "outcome": "OK",
  "row_count": 2920,
  "payload_file": "20260826T015155246Z_8ff4bc3894f1.json",
  "payload_bytes": 2807217,
  "payload_sha256": "…",
  "collector_version": "bronze-v3",
  "quota_seq_today": 137,
  "key_id": "d137a9cf",
  "quota_pool": "seoul_subway_realtime",
  "partition": null,
  "error_code": null,
  "error_body": null
}
```

### 필수 규칙

**1. `requested_at`은 호출 직전, `received_at`은 응답 직후에 각각 따로 찍는다.**

이 프로젝트는 이미 한 번 실패했다. `DECISION_SHEET_260824_v0.2.md` 기록에 따르면 기존 수집기가 두 값을 응답 수신 후 동시에 stamping해 수집된 240건 전부 latency가 0.00~0.001초로 남았고 판정이 `BLOCKED_TOOLING`이 됐다.

`CollectionResult`는 두 필드를 **기본값 없는 필수 인자**로 두어 이 실수를 구조적으로 막는다. 기본값을 주지 말 것.

**2. `request_url`은 인증키를 마스킹해 저장한다.**

서울 열린데이터광장 계열은 인증키가 URL **path**에 들어간다. query param을 지우는 것만으로는 마스킹되지 않는다. `env.mask_in_text()`를 쓴다.

**3. HTTP 상태와 업무코드를 분리 판정한다.**

HTTP 200이면서 업무코드가 오류인 경우가 실제로 존재한다. 검증 중 관측한 예:

```
HTTP 200 + {"status":500,"code":"ERROR-336","message":"데이터요청은 한번에 최대 1000건을 넘을 수 없습니다."}
```

`outcome` 필드로 구분한다.

| outcome | 의미 |
|---|---|
| `OK` | HTTP 성공 + 업무코드 성공(`INFO-000`, `INFO-200`) |
| `BUSINESS_ERROR` | HTTP 성공이지만 업무코드가 오류 |
| `HTTP_ERROR` | HTTP 상태 자체가 실패 |
| `TRANSPORT_ERROR` | 연결 실패·타임아웃 등 응답 없음 |

`INFO-200`(무결과)은 오류가 아니라 정상적인 빈 결과다. 오류로 처리하면 사고 없는 시점과 수집 실패 시점을 구분할 수 없게 된다.

**4. 실패도 저장한다.**

성공 응답만 남기면 장애 구간과 무데이터 구간을 구분할 수 없다. `TRANSPORT_ERROR`로 원문이 없어도 메타는 기록한다.

**5. `collector_version`을 남긴다.**

과거에 timestamp 문제를 한 번 고쳤으나 버전이 기록되지 않아 회귀인지 별개 스크립트인지 구분할 수 없었다. 수집 로직이 바뀌면 버전을 올린다.

| 버전 | 변경 |
|---|---|
| `bronze-v1` | 최초 규약 |
| `bronze-v2` | `key_id`·`quota_pool` 추가 (2026-08-26) |
| `bronze-v3` | `partition` 추가, 노선/호선별 폴더 분리 (2026-08-27) |

**6. `key_id`와 `quota_pool`을 남긴다. 인증키 값은 절대 남기지 않는다.**

`key_id`는 인증키의 SHA-256 앞 8자리이며(`quota.key_id`), 샘플키는 `sample`,
키가 없으면 `none`이다. `quota_pool`은 그 호출이 차감된 원장 풀 이름이고
`runner`를 경유하지 않은 호출에서는 `null`이다.

두 필드가 필요한 이유는 세 가지다.

1. **원장 복구** — `data/quota_ledger.json`이 유실·손상되면 카운터를 되살릴
   근거가 필요하다. 카운터가 0으로 돌아가면 일일 상한을 인식하지 못해 그날
   예산을 모두 태우고, 실시간 데이터는 backfill이 불가능해 하루가 영구
   손실된다. `quota.counts_from_bronze()`가 `f"{quota_pool}::{key_id}"`로
   당일 사용량을 재구성한다.
2. **샘플키 판별** — 샘플키 응답은 반환 행이 제한된 잘린 데이터이므로 Silver로
   넘기면 안 된다. 이 필드가 없던 시절에는 URL의 조회 범위(`/0/5/`)라는
   우연한 단서로 구분했는데, 실키로 같은 범위를 호출하면 오판한다.
3. **다중 키 추적** — `SEOUL_SUBWAY_REALTIME_KEY_2` 등으로 팀원 키를 늘리면
   어떤 키가 만든 기록인지 알 수 없어, 특정 키만 권한이 빠지는 상황을
   추적할 수 없다.

복구값은 **하한**이다. 호출은 했으나 저장에 실패한 건은 셀 수 없다. 재시도분은
`quota_seq_today`의 최댓값으로 보정한다 — 3회 재시도의 마지막 결과에 `seq=3`이
찍혀 있으므로 기록 1건에서 3회를 복원할 수 있다.

## 새 수집기 추가하는 법

`collector/sources/`에 provider별 모듈을 만들고 `http_client.fetch()`에 업무코드 판정 함수(`judge`)를 주입한다.

```python
from ..common.http_client import Verdict, fetch

def judge(payload: bytes) -> Verdict:
    """원문에서 업무코드와 행 수를 뽑아 성공 여부를 판정한다."""
    ...
    return Verdict(business_code=code, row_count=n, ok=..., message=...)

def collect(key: str, **kw):
    return fetch(
        source_key="...", provider="...", endpoint="...",
        url=..., secret=key, judge=judge, payload_ext="json", **kw,
    )
```

저장은 호출자가 `storage.record()`로 한다. `fetch()`는 저장하지 않는다 — quota 원장(Jira 97)이 중간에 개입할 수 있어야 하기 때문이다.

## 검증

```bash
python -m collector.smoke_test
```

실제 인증키 없이 공개 `sample` 키로 위 규칙 전부를 검증한다. 규약을 바꾸면 이 테스트도 함께 고친다.
