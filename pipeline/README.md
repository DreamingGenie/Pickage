# pipeline — Pickage 데이터 수집·변환·적재

deps.dev·npm 다운로드·패키지 텍스트 수집, 원본 검증·MinIO 입고, Curated 생성·PostgreSQL 적재와
DuckDB 분석·데이터셋 생성을 담당한다. 원천 수집기는 `collectors/`에, 검증·변환·적재 모듈은 역할별 폴더에 둔다.
BigQuery 수집 결과의 팀 공유 정본은 GCS `gs://oss-shift-a506-raw/raw/…`에, 로컬 원본과 실행 기록은
`data/`(gitignore)에 보관한다. 팀 공유용으로 추적하는 작은 파생 데이터는 [datasets/](../datasets/README.md)에 둔다.

## 폴더

| 폴더 | 역할 | 문서 |
|---|---|---|
| `collectors/bigquery/` | deps.dev BigQuery(`bigquery-public-data.deps_dev_v1`) → GCS Parquet. PackageVersions · NPMRequirements · PackageVersionToProject · Projects(전 스냅샷). T0 1회 · T1 1회 · T2 주간(화) · T2m 월간 | [BigQuery 수집 안내](collectors/bigquery/README.md) |
| `collectors/downloads/` | npm downloads API(`api.npmjs.org/downloads`) → 다운로드 순위 상위 10만 패키지의 일별 다운로드 → jsonl.gz → Parquet. 백필 1회 · 주간(화 10:00 KST~) | [다운로드 수집 안내](collectors/downloads/README.md) |
| `collectors/keywords/` | ecosyste.ms 목록 API(`packages.ecosyste.ms`) → 상위 100만 패키지의 keywords·description·GitHub topics → jsonl.gz → `package_text` Parquet(AI 학습 입력). 1회(필요 시 재수집) | [패키지 텍스트 수집 안내](collectors/keywords/README.md) |
| `minio/` | 로컬 MinIO 버킷 초기화·deps.dev 원본 적재 | [MinIO 원본 입고 안내](minio/README.md) |
| `downloads/` | 이미 수집한 대상 CSV·JSONL·일별/상태 Parquet 검증 → MinIO Bronze 불변 입고. 수동 실행 | [다운로드 검증·입고 안내](downloads/README.md) |
| `curated/` | MinIO의 deps.dev 원본 → PostgreSQL `package`·`version` 적재용 Curated Parquet | [Curated 전처리 안내](curated/README.md) |
| `orchestration/` | 명시적 MinIO raw 스냅샷 → 기존 전처리 순차 실행·실패 재개·완료 Curated 묶음 게시. 수집/DB 적재 제외 | [통합 실행 안내](orchestration/README.md) |
| `snapshot/` | Projects에 실제 존재하는 스냅샷 날짜·원천 시각·직전 기준일 검증 → 기준 날짜와 DB 실행 이력 적재 | [스냅샷 기준·적재 안내](snapshot/README.md) |
| `downloads_interval/` | 승인 패키지 전체의 스냅샷 구간 다운로드 합계·부분합·품질 정보 → MinIO Curated 게시 | [다운로드 구간 집계 안내](downloads_interval/README.md) |
| `repository_metrics/` | 승인 패키지의 저장소 선택·정확한 관측 시각의 stars·open_issues → Curated 게시 | [저장소 지표 안내](repository_metrics/README.md) |
| `package_snapshot/` | 다운로드 구간 합계·저장소 지표 통합 → 전체 패키지의 `package_snapshot`·DB 실행 이력 게시 | [통합 적재 안내](package_snapshot/README.md) |
| `postgresql/` | 승인 Curated `package`·`version` → staging 검증·실행 이력 기록·PostgreSQL 원자적 게시 | [PostgreSQL 적재 안내](postgresql/README.md) |
| `duckdb/` | 로컬 Parquet를 DuckDB로 읽는 도구와 데이터셋 빌더. `duckdb_ui.py`(브라우저 SQL 편집기), `inspect_duckdb.py`(원본 훑어보기), `build_*.py`(→ `datasets/`), `semver_rule.py`(의존 조건 해석 규칙, Spark 이식용 참조 구현), `sql/`(분석·확인 쿼리) | 각 파일 머리말 |

수집기 세 개는 원천마다 폴더 하나이고, 그 폴더 안에 수집·그 수집기 전용 변환(`to_parquet.py`, `build_package_text.py`)·현황판(`status.py`, `*.cmd`)·README가 함께 있다.
공통 환경은 `.venv-bq`(리포 루트, gitignore). 외부 API 수집기(`collectors/downloads`, `collectors/keywords`)는 User-Agent 연락처를 환경변수 `OSS_SHIFT_UA_CONTACT`로 받으며, 비어 있으면 시작하지 않는다.

다운로드 처리 순서는 `collectors/downloads/`의 API 수집·Parquet 변환 → `downloads/`의 원본 검증·Bronze 입고 →
`downloads_interval/`의 스냅샷 구간 집계·Curated 게시다. 실행 명령과 입력 조건은 각 폴더의 안내를 따른다.

## 로컬 Parquet 조회

`.venv-bq/Scripts/python.exe pipeline/duckdb/duckdb_ui.py` → `data/` 아래 데이터셋을 DuckDB 뷰(`projects`·`pkg_project`·`requirements`·`versions_full`·`downloads`·`downloads_status`·`package_text`)로 묶고 브라우저 SQL 편집기(DuckDB UI, `localhost:4213`)를 띄운다. `-c "<sql>"`로 1회 실행, `--no-ui`로 카탈로그(`data/oss_shift.duckdb`)만 갱신.
`duckdb/sql/`의 쿼리는 이 뷰 이름을 그대로 쓴다.

## 다운로드 구간 집계

스냅샷 구간별 다운로드 집계는 검증 완료한 Bronze 원본에서 패키지별 구간 합계와 품질 정보를 만들어
Curated에 게시한다. 다운로드 원본 입고와 같은 티켓(S15P21A506-278)에서 초도 게시까지 완료했다.
[구간 집계 계약](../docs/worklogs/S15P21A506-278/06-interval-contract.md)에 입력·시간·NULL·게시 조건을 기록하며,
유효 날짜가 일부만 있으면 부분합을, 하나도 없으면 NULL을 게시한다. 초도 실행 결과와 재검증 근거는
[작업 결과 기록](../docs/worklogs/S15P21A506-278/08-interval-results.md)에 있다.
다운로드 결과와 저장소 지표를 `package_snapshot`에 함께 적재하는 방법은
[통합 적재 안내](package_snapshot/README.md)를 따른다. 부분합·NULL의 품질 근거도 DB 실행 이력에 연결한다.

## PostgreSQL 적재

Curated `package`·`version`을 PostgreSQL에 적재할 때는 [PostgreSQL 적재 안내](postgresql/README.md)를
따른다. 적재기는 승인된 Curated manifest의 `package/data`·`version/data`만 읽고, PostgreSQL
staging과 실행 이력을 거쳐 원자적으로 게시한다. Curated 결과를 새로 만드는 방법은
[Curated 전처리 안내](curated/README.md)에, 로컬 PostgreSQL·Flyway·샘플 DB 운영은
[로컬 개발 환경 안내](../deploy/local/README.md)에 있다.

적재 CLI의 기본 작업 디렉터리는 `data/postgresql`이며, 실행 report·psql stderr·Parquet
캐시·COPY 전송 파일을 여기에 남긴다. 이 파일에는 인증정보를 저장하지 않는다. 전체
PostgreSQL 적재 성공 여부와 실제 검증 결과는 [작업 결과 기록](../docs/worklogs/S15P21A506-267/05-results.md)을
확인한다.

앞으로 Spark 정제·적재 코드가 생기면 `pipeline/spark/`처럼 같은 층에 둔다. 폐기된 교통 데이터 수집기(2026-08)는 `docs/history/0901_journey_reliability_legacy/collector/`로 이동했다.
