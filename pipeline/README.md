# pipeline — OSS Shift 데이터 수집·변환

원천 두 개, 수집기 두 개. 결과는 GCS `gs://oss-shift-a506-raw/raw/…`(팀 공유 정본)와 로컬 `data/`(gitignore)에 쌓인다.

| 폴더 | 원천 | 무엇을 받나 | 주기 | 계획서 |
|---|---|---|---|---|
| `bigquery/` | `bigquery-public-data.deps_dev_v1` | PackageVersions · NPMRequirements · PackageVersionToProject · Projects(전 스냅샷) → GCS Parquet | T0 1회 · T1 1회 · T2 주간(화) · T2m 월간 | `docs/api & data/수집계획_BigQuery_Parquet_v2_260902.md` |
| `downloads/` | `api.npmjs.org/downloads` | 다운로드 순위 상위 10만 패키지의 일별 다운로드 → jsonl.gz → Parquet | 백필 1회 · 주간(화 10:00 KST~) | `docs/api & data/수집계획_downloads_npmAPI_260902.md` |

공통 환경 `.venv-bq`(리포 루트, gitignore). 각 폴더의 `README.md`에 실행 명령·재시작 방법이 있다.

앞으로 Spark 정제·적재 코드가 생기면 `pipeline/spark/`처럼 같은 층에 둔다. 폐기된 교통 데이터 수집기(2026-08)는 `docs/history/0901_journey_reliability_legacy/collector/`로 이동했다.
