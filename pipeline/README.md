# pipeline — Pickage 데이터 수집·변환

원천에서 받아(`collectors/`) 로컬·MinIO에 보존하고, 정제(`curated/`)하거나 DuckDB로 분석·데이터셋을 만든다(`duckdb/`).
수집 결과는 GCS `gs://oss-shift-a506-raw/raw/…`(팀 공유 정본)와 로컬 `data/`(gitignore)에 쌓인다. 팀 공유용으로 추적하는 작은 파생 데이터는 리포 루트 `datasets/`에 둔다.

## 폴더

| 폴더 | 역할 | 문서 |
|---|---|---|
| `collectors/bigquery/` | deps.dev BigQuery(`bigquery-public-data.deps_dev_v1`) → GCS Parquet. PackageVersions · NPMRequirements · PackageVersionToProject · Projects(전 스냅샷). T0 1회 · T1 1회 · T2 주간(화) · T2m 월간 | `docs/api & data/수집계획_BigQuery_Parquet_v2_260902.md` |
| `collectors/downloads/` | npm downloads API(`api.npmjs.org/downloads`) → 다운로드 순위 상위 10만 패키지의 일별 다운로드 → jsonl.gz → Parquet. 백필 1회 · 주간(화 10:00 KST~) | `docs/api & data/수집계획_downloads_npmAPI_260902.md` |
| `collectors/keywords/` | ecosyste.ms 목록 API(`packages.ecosyste.ms`) → 상위 100만 패키지의 keywords·description·GitHub topics → jsonl.gz → `package_text` Parquet(AI 학습 입력). 1회(필요 시 재수집) | `docs/api & data/검증_keywords_수집가능성_260908.md` |
| `curated/` | MinIO의 deps.dev 원본 → PostgreSQL `package`·`version` 적재용 Curated Parquet | `curated/README.md` |
| `minio/` | 로컬 MinIO 버킷 초기화·원본 적재 | `minio/README.md` |
| `duckdb/` | 로컬 Parquet를 DuckDB로 읽는 도구와 데이터셋 빌더. `duckdb_ui.py`(브라우저 SQL 편집기), `inspect_duckdb.py`(원본 훑어보기), `build_*.py`(→ `datasets/`), `semver_rule.py`(의존 조건 해석 규칙, Spark 이식용 참조 구현), `sql/`(분석·확인 쿼리) | 각 파일 머리말 |

수집기 세 개는 원천마다 폴더 하나이고, 그 폴더 안에 수집·그 수집기 전용 변환(`to_parquet.py`, `build_package_text.py`)·현황판(`status.py`, `*.cmd`)·README가 함께 있다.
공통 환경은 `.venv-bq`(리포 루트, gitignore). 외부 API 수집기(`downloads`, `keywords`)는 User-Agent 연락처를 환경변수 `OSS_SHIFT_UA_CONTACT`로 받으며, 비어 있으면 시작하지 않는다.

## 로컬 Parquet 조회

`.venv-bq/Scripts/python.exe pipeline/duckdb/duckdb_ui.py` → `data/` 아래 데이터셋을 DuckDB 뷰(`projects`·`pkg_project`·`requirements`·`versions_full`·`downloads`·`downloads_status`·`package_text`)로 묶고 브라우저 SQL 편집기(DuckDB UI, `localhost:4213`)를 띄운다. `-c "<sql>"`로 1회 실행, `--no-ui`로 카탈로그(`data/oss_shift.duckdb`)만 갱신.
`duckdb/sql/`의 쿼리는 이 뷰 이름을 그대로 쓴다.

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
