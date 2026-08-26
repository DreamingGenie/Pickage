# 데이터 수집·저장 플랫폼 계획서 — 2026-08-26

> 작성 기준: 2026-08-26 KST
> 담당 범위: 데이터 수집기, 저장 계층, 스키마, 원천 간 연결
> 선행 문서: [API 후보 종합 비교표](api%20&%20data/API_후보_종합_비교표_260826.md) · [SERVICE_PLAN v0.2](SERVICE_PLAN_260824_v0.2.md) · [REQUIREMENTS_SPEC v0.2](REQUIREMENTS_SPEC_260824_v0.2.md)

## 1. 목적과 이 문서가 답하는 질문

수집 대상 API가 확정된 뒤 남은 질문은 세 가지다.

1. 수집한 데이터를 DB에 넣어야 하는가, 넣는다면 어느 단계에서 넣는가
2. 원천별로 따로 저장한 데이터를 어떻게 하나로 연결하는가
3. 무엇부터 시작해야 손실 없이 착수할 수 있는가

이 문서는 위 세 가지에 대한 설계와 실행 순서를 정한다. 개별 API의 명세·품질·제약은 각 분석 문서를 정본으로 하며 여기서 반복하지 않는다.

## 2. 규모 산정 — 설계 판단의 출발점

| 데이터 | 실측 근거 | 일 적재량 | 월 누적 |
|---|---|---|---|
| 지하철 도착정보(일괄) OA-15799 | 1회 응답 **2,807,217 bytes** / 2,920행 · 120초 폴링 720회/일 | 약 **2.0GB / 210만 행** | 약 **60GB / 6,300만 행** |
| 지하철 열차위치 OA-12601 | 노선별 호출, 응답 소규모 | 수백 MB | 수 GB |
| 버스 위치·도착 | 상세기능당 1,000/day, 노선 단위 | 수십 MB | 수 GB |
| 정적 마스터 6종 | 723행 ~ 532,832행 (최대 44.7MB) | 0 (버전 갱신 시만) | 80MB 내외 |
| 이력 파일 | OA-12252 84,215행(30.8MB) · OA-12913 43,171행/월(15.8MB) | 0 (월 1회) | 수백 MB |

**결론: 실시간 폴링 로그 하나만 크고 나머지는 전부 단일 노드에서 다룰 수 있는 크기다.** 그 2.0GB/일도 XML 원문 기준이며 컬럼 포맷으로 변환하면 크게 줄어든다.

이 프로젝트에서 분산 스택이 필요한 이유는 데이터 크기가 아니라 아래 세 가지다. 설계 판단이 흔들릴 때 이 기준으로 돌아온다.

1. **평가 요구사항** — `NFR-081`이 Kafka 파티션을 2개 이상 worker가 처리하고 장애 후 복구할 것을 MUST로 요구한다
2. **상태 기반 스트림 처리** — `stopFlag 0→1` 전이 감지, Prediction→Actual 매칭은 키별 상태와 워터마크가 필요하다
3. **재처리 가능성** — 필드 해석 규칙이 바뀔 때 원문부터 다시 돌릴 수 있어야 한다

## 3. 저장 계층 설계

"DB에 넣을 것인가"가 아니라 **단계마다 저장 목적이 다르고 목적에 맞는 저장소가 따로 있다**로 접근한다. 메달리온 아키텍처(Bronze/Silver/Gold)를 따르며, 이는 SERVICE_PLAN의 `Silver/Gold Parquet` 표기와 같은 개념이다.

| 계층 | 목적 | 담는 것 | 저장소 | 스키마 |
|---|---|---|---|---|
| **Bronze** | 증거 보존 | API 응답 **원문 그대로** + 수집 메타 | 파일 (초기 로컬 디스크 → MinIO) | 없음 |
| **Silver** | 해석 | 파싱·정규화·canonical ID 부여·중복 제거 | PostgreSQL / Parquet (아래 분기) | 있음, 버전 관리 |
| **Gold** | 답변 | 질문 단위로 미리 집계된 분포 | **PostgreSQL** | 있음, 서빙용 |

### 3-1. Bronze는 DB에 넣지 않는다

가장 중요한 원칙이다. 근거는 각 API 분석 문서가 스스로 남긴 미확정 항목들이다 — 필드 casing 불일치(T-DATA-1015), 속도·여행시간 단위 미명시(OA-13291), `rnQcflg=9`의 의미 미확정(ASOS), `MM:SS` 해석 미확정(OA-22521), schema drift 가능성(다수).

지금 해석이 확정되지 않은 필드가 수십 개다. 원문을 남기지 않고 파싱 결과만 적재하면 해석이 바뀔 때 **다시 만들 방법이 없다.** 실시간 API는 공식 과거 조회 기능이 없어(OA-13291·13315 문서 명시) 지나간 데이터를 backfill할 수 없다.

원문을 파일로 두면 규칙만 고쳐 Silver부터 재생성할 수 있다. 이 성질을 **재처리 가능성(reprocessability)** 이라 하며 이 계획의 1원칙이다.

### 3-2. Silver 저장소 분기

| Silver 대상 | 저장소 | 근거 |
|---|---|---|
| 차원·크로스워크 (`dim_station`, `dim_route`, `xref_*`) | **PostgreSQL** | 조인 대상이고 작음. 트랜잭션·제약조건 필요 |
| 정적 마스터 (시각표·역간거리·환승·노선) | **PostgreSQL** (SCD2) | 최대 53만 행. 인덱스 조회가 주 용도 |
| 과거 이력 집계 (OA-12252·12913·T-DATA-1068) | **PostgreSQL** 파티션 테이블 | 월 파티션. 수십만~수백만 행 규모 |
| 실시간 관측 로그 | **PostgreSQL 파티션 테이블로 시작 → 부담되면 Parquet 이전** | 월 6,300만 행은 파티셔닝으로 감당 가능. 조기 복잡도를 피한다 |

실시간 관측을 처음부터 Parquet으로 가지 않는 이유는, Kafka·Flink·MinIO를 모두 세운 뒤에 수집을 시작하면 그동안의 실시간 데이터가 영구 손실되기 때문이다. **Bronze만 확보되면 Silver 저장소는 나중에 언제든 바꿀 수 있다.**

### 3-3. 원천별 DB를 따로 만들지 않는다

원천별로 DB를 만들고 나중에 통합하는 방식은 채택하지 않는다.

- 통합 시점이 뒤로 밀리면 ID 불일치가 한꺼번에 터진다. 이 프로젝트는 특히 위험하다 — "역명 단독 조인 금지"(OA-22521), "`ROUTEID`를 `busRouteId`와 연결하기 전 referential-integrity test 필요"(OA-15262), "`STOPS_ID`가 `stId`와 같은 값 공간인지 미확정"(OA-12913)이 문서 전반에 반복된다
- 원천별로 스키마를 확정하면 그것이 곧 기술 부채가 된다
- 같은 실체(역·정류장·노선)가 DB마다 다르게 중복 정의된다

**분리는 Bronze까지만.** Bronze는 원천별 디렉터리로 나누고, Silver부터는 원천이 아니라 의미 단위로 나눈다.

## 4. Bronze 저장 규약

### 디렉터리·파일명

```
bronze/<source_key>/service_date=YYYY-MM-DD/
  <UTC timestamp>.<ext>          # 원문
  <UTC timestamp>.meta.json      # 수집 메타
```

예: `bronze/subway_arrival_all/service_date=2026-08-26/20260826T091500Z.xml`

파티션 키는 달력 날짜가 아니라 **운행일(`service_date`)** 이다. 근거는 6절.

### 수집 메타 스키마

```json
{
  "source_key": "subway_arrival_all",
  "provider": "seoul_open_data",
  "endpoint": "realtimeStationArrival/ALL",
  "request_url": "http://swopenAPI.seoul.go.kr/api/subway/***/xml/realtimeStationArrival/ALL",
  "requested_at": "2026-08-26T09:15:00.123Z",
  "received_at":  "2026-08-26T09:15:00.481Z",
  "http_status": 200,
  "business_code": "INFO-000",
  "row_count": 2920,
  "payload_bytes": 2807217,
  "payload_sha256": "…",
  "collector_version": "bronze-v1",
  "quota_seq_today": 137
}
```

**`requested_at`은 호출 직전, `received_at`은 응답 직후에 각각 따로 찍는다.**

이 항목을 규약에 못 박는 이유는 프로젝트가 이미 한 번 겪은 문제이기 때문이다. `DECISION_SHEET_260824_v0.2.md`에 기록된 바로, 기존 수집기가 두 타임스탬프를 응답 수신 후 동시에 stamping하는 바람에 수집된 240건 전부 latency가 0.00~0.001초로 기록되어 `BLOCKED_TOOLING` 판정을 받았다. 더욱이 과거 Phase 2에서 같은 문제를 한 번 고친 이력이 있으나 collector version이 기록되지 않아 회귀인지 별개 스크립트인지 구분조차 불가능한 상태다.

`request_url`은 인증키를 마스킹해 저장한다. 키가 URL path에 들어가는 provider가 다수이므로(서울 열린데이터광장 계열 전체) 마스킹은 선택이 아니라 필수다.

## 5. 수집 우선순위 — 긴급도는 비대칭이다

급한 이유는 일일 quota 제한이 아니라 **실시간 데이터는 지나가면 backfill이 불가능**하다는 점이다. 오늘 받지 못한 오늘치는 내일 quota를 남겨도 받을 수 없다.

| 긴급도 | 대상 | 근거 |
|---|---|---|
| **즉시** | 지하철 도착(일괄)·열차위치, 버스 위치·도착 | 오늘치는 오늘만 받을 수 있음 |
| 보통 | 정적 마스터 6종, OA-12252, OA-12913, ASOS | 과거분이라 나중에 받아도 동일 |
| 승인 대기 | T-DATA-1068, T-DATA-1015 | 과거 이력이라 승인 후 받아도 손실 없음 |

**정적·이력 수집기를 먼저 만들다가 실시간 수집 착수가 늦어지는 것이 최악의 시나리오다.**

### 폴링 예산

OA-15799 기준, 지하철 전용키는 인증키 1개당 1일 1,000회다.

| 주기 | 일 호출 수 | 판정 |
|---|---:|---|
| 30초 | 2,880 | 한도 초과 |
| 60초 | 1,440 | 한도 초과 |
| **120초** | **720** | **한도 내 — 채택** |

정규 720회 + 재시도·수동 검증 230회 + 비상 여유 50회로 배분하고, 일일 **950회 도달 시 자동 재시도를 중단**한다.

## 6. 원천 간 연결 설계

저장보다 어려운 문제다. 각 API가 같은 실체를 서로 다른 ID로 부른다.

| 실체 | OA-12764 실시간 | OA-12252 이력 | OA-22522 시각표 | OA-12928 혼잡도 |
|---|---|---|---|---|
| 역 | `statnId` | 역명 문자열 | 역 식별자(4호선 일부 공백) | `역번호` 3자리 |
| 노선 | `subwayId` | `호선명` 문자열 | `LINE` | 별도 체계 |

### Conformed Dimension + 크로스워크

사실 데이터끼리 직접 조인하지 않고 **모두가 공통 차원 테이블의 키를 참조**하게 만든다.

```
dim_station (canonical_station_id PK, 정규화_역명, 위경도, valid_from, valid_to)
dim_route   (canonical_route_id  PK, 노선구분, 정규화_노선명, valid_from, valid_to)

xref_station (canonical_station_id FK, source_system, source_id,
              mapping_method, confidence, valid_from, valid_to)
xref_route   (canonical_route_id  FK, source_system, source_id,
              mapping_method, confidence, valid_from, valid_to)

fact_subway_arrival_obs (canonical_station_id FK, canonical_route_id FK,
                         service_date, observed_at, train_no, …)
```

`mapping_method`와 `confidence`를 반드시 함께 저장한다. 역명 문자열 매칭으로 이었다면 그 사실이 남아야 나중에 틀렸을 때 추적할 수 있다. canonical ID는 raw identity와 매핑 근거를 **대체하지 않고 추가**한다.

**크로스워크는 부수적 매핑 테이블이 아니라 1급 설계 산출물로 다룬다.** 현재 기획 문서에는 이 요구가 각 API 문서의 TODO로 흩어져 있을 뿐 통합 설계가 없다.

### 운행일(service_date)

10개 이상의 분석 문서가 지적하는 함정이다. OA-22522에 24시 이상 시각이 **4,475건** 존재하고, 심야버스는 자정을 넘겨 운행한다. 8월 26일 새벽 1시에 도착한 열차는 **8월 25일 운행일** 소속이다.

- `service_date`를 달력 날짜와 분리된 별도 컬럼으로 둔다
- Bronze 디렉터리 파티션 키와 Silver 테이블 파티션 키 모두 `service_date`를 쓴다
- 경계 시각 규칙(예: 04:00 기준 분할)은 provider별로 확인 후 확정하며, 확인 전에는 원문 시각을 그대로 보존한다

나중에 고치려면 전면 재적재가 필요하므로 첫 적재 전에 확정한다.

## 7. 기존 기획서와 다른 부분 (제안)

아래 항목은 `SERVICE_PLAN_260824_v0.2.md`의 기존 서술과 다르거나 명시되지 않은 부분에 대한 제안이다. 팀 논의 후 확정한다.

### 7-1. Gold 산출물을 PostgreSQL로 물질화 — 제안

**현황**: 아키텍처 다이어그램은 `BATCH(Spark) → HIST(Historical Reliability Artifact)`로 되어 있으나 **HIST가 어느 저장소에 사는지 명시가 없다.** 구성요소 표는 PostgreSQL의 책임을 "analysisType별 request/result/access/share/quota metadata"로 한정하므로, 소거법상 HIST는 Gold Parquet에 위치하게 된다.

**문제**: `출발 시간 추천` API는 요청 시점에 해당 경로·시간대의 분포를 읽어야 한다. MinIO의 Parquet을 요청마다 스캔하면 응답 지연이 초 단위로 발생한다. Parquet은 분석 스캔용이지 서빙 저장소가 아니다.

**제안**: Spark가 생성한 분포를 PostgreSQL 테이블로 물질화한다.

```
gold_leg_distribution (
  canonical_route_id, leg_type, day_type, time_bucket,
  p50_seconds, p90_seconds, support_count,
  artifact_version, data_start_at, data_end_at,
  PRIMARY KEY (canonical_route_id, leg_type, day_type, time_bucket, artifact_version)
)
```

인덱스가 붙은 수만~수십만 행이면 밀리초 응답이 가능하다. 이는 기존 결정과의 충돌이라기보다 **명시되지 않은 공백을 메우는 성격**이다.

### 7-2. 크로스워크 스키마의 독립 설계 — 제안

6절 참조. 각 API 문서 TODO에 흩어진 요구를 하나의 스키마 설계 산출물로 통합한다.

### 7-3. Flink 적용 범위 축소 — 검토 요청

Flink가 실제로 필요한 것은 상태 기반 작업 세 가지다 — 중복 제거, `stopFlag 0→1` 전이 감지, Prediction→Actual 매칭. 나머지 정규화·집계는 Spark 배치가 개발·디버깅 모두 쉽다. `NFR-081`의 분산 증명 요구는 위 세 작업만으로도 충족 가능한지 검토한다.

## 8. 단계별 실행 계획

| 단계 | 내용 | 선행 조건 | 산출물 |
|---|---|---|---|
| **P0** | Bronze 저장 규약 확정 + 실시간 4종 수집기 가동 | 없음 | 매일 원문·메타가 쌓임 |
| **P0'** | 게이트 확인 2건 (`:8088` 차단, T-DATA-1068 승인) | 없음 (P0와 병렬) | 도로 계열·버스 이력의 가부 판정 |
| **P1** | 운행일 규칙 + 크로스워크 스키마 설계 | 정적 마스터 Bronze 확보 | DDL |
| **P2** | 정적 마스터 Silver 적재(SCD2) + 크로스워크 구축 | P1 | 조인 가능한 차원 테이블 |
| **P3** | 이력 파일 Silver 적재 (OA-12252 dedup 포함) | P2 | 분포 계산 재료 |
| **P4** | 실시간 관측 Silver 적재 (append-only) | P2 | Prediction→Actual 재료 |
| **P5** | Gold 물질화 + 서빙 테이블 | P3, P4 | API가 읽을 분포 |

**P0가 오늘 안에 돌아가는 것이 이 계획의 성패를 가른다.** 나머지는 늦어도 데이터가 손실되지 않는다.

## 9. 리스크

| 리스크 | 영향 | 대응 |
|---|---|---|
| T-DATA-1068 backfill이 얕음 | 버스 historical 분포와 날씨 상관분석이 동시에 무너짐 | P0'에서 최우선 확인. 얕으면 연구 범위 축소 결정 |
| `:8088` 차단이 망 문제가 아님 | 도로 context feature 3종 사용 불가 | Leave-now 범위에서 제외하고 Evidence에 명시 |
| 실시간 수집 착수 지연 | 지연 일수만큼 영구 손실 | 인프라 완비를 기다리지 않고 로컬 디스크로 시작 |
| 크로스워크 조인율 미달 | 원천 간 연결 실패, 데이터가 섬으로 남음 | P2에서 조인율을 측정 지표로 두고 미달 시 매핑 근거 보강 |
| 운행일 규칙 사후 변경 | Bronze 파티션·Silver 테이블 전면 재적재 | 첫 적재 전 확정 |

## 10. 참고

- [API 후보 종합 비교표](api%20&%20data/API_후보_종합_비교표_260826.md) — 수집 대상 선정 근거
- [SERVICE_PLAN v0.2](SERVICE_PLAN_260824_v0.2.md) — 제품 범위·아키텍처
- [REQUIREMENTS_SPEC v0.2](REQUIREMENTS_SPEC_260824_v0.2.md) — `NFR-080`~`NFR-084` 분산 증명·quota 요구
- [DECISION_SHEET v0.2](DECISION_SHEET_260824_v0.2.md) — collector timestamp 사고, provider quota 확인 이력
