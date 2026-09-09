# pipeline — Pickage 데이터 수집·변환·적재

deps.dev 수집과 보유 npm 다운로드 원본의 검증·MinIO 입고, Curated 생성·PostgreSQL 적재를 담당한다.
기존 GCS 원천 경로는 `gs://oss-shift-a506-raw/raw/…`이며, 로컬 원본과 실행 기록은 `data/`(gitignore)에 보관한다.

| 폴더 | 원천 | 처리 내용 | 실행 주기 | 안내 |
|---|---|---|---|---|
| `bigquery/` | `bigquery-public-data.deps_dev_v1` | PackageVersions · NPMRequirements · PackageVersionToProject · Projects(전 스냅샷) → GCS Parquet | T0 1회 · T1 1회 · T2 주간(화) · T2m 월간 | `docs/api & data/수집계획_BigQuery_Parquet_v2_260902.md` |
| `downloads/` | 이미 수집한 npm 다운로드 원본 | 대상 CSV·JSONL·일별/상태 Parquet 검증 → MinIO Bronze 불변 입고 | 수동 실행 | [다운로드 검증·입고 안내](downloads/README.md) |

공통 환경 `.venv-bq`(리포 루트, gitignore). 각 폴더의 `README.md`에 실행 명령·재시작 방법이 있다.

스냅샷 구간별 다운로드 집계는 검증 완료한 Bronze 원본에서 패키지별 구간 합계와 품질 정보를 만들어
Curated에 게시하는 작업이다. 다운로드 원본 입고와 같은 티켓(S15P21A506-278)에서 구현할 계획이다.
[구간 집계 계약](../docs/worklogs/S15P21A506-278/06-interval-contract.md)에 입력·시간·NULL·게시 조건을 기록하며,
예정 구현 위치는 `pipeline/downloads_interval/`다. 구간 집계 모듈과 실행 결과는 아직 없다.

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
