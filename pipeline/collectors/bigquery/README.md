# pipeline/collectors/bigquery — deps.dev BigQuery → GCS Parquet 수집기

계획서: [`docs/api & data/수집계획_BigQuery_Parquet_v2_260902.md`](../../docs/api%20&%20data/수집계획_BigQuery_Parquet_v2_260902.md)
환경: `.venv-bq` (google-cloud-bigquery 3.44 · google-cloud-storage 3.13), 프로젝트 `oss-shift-a506`, 버킷 `gs://oss-shift-a506-raw` (US)

## 실행 순서

```bash
# 0) 항상 먼저 계획 모드. dry-run만 하고 예산 합계를 보여준다 (과금 0)
.venv-bq/Scripts/python pipeline/collectors/bigquery/collect.py --tier t0 --plan

# 1) T0 핵심 4테이블, 최신 스냅샷 1회 (dry-run 합계 약 52.6 GiB)
.venv-bq/Scripts/python pipeline/collectors/bigquery/collect.py --tier t0

# 2) T1 Projects 전 스냅샷 백필 (228개, 합계 약 51 GiB, 40분 안팎)
.venv-bq/Scripts/python pipeline/collectors/bigquery/collect.py --tier t1

# 3) 매주 화요일: 새 스냅샷 증분 (약 23 GiB). 스냅샷이 없으면 "파티션이 없다"로 중단
.venv-bq/Scripts/python pipeline/collectors/bigquery/collect.py --tier t2

# 4) 월 1회: Description·Links·저장소 매핑 갱신 (약 35 GiB)
.venv-bq/Scripts/python pipeline/collectors/bigquery/collect.py --tier t2m

# 노트북으로 내려받기
gcloud storage rsync -r gs://oss-shift-a506-raw/raw ./data/raw
```

중단됐다가 다시 실행하면 `_MANIFEST.json`이 있는 (테이블, 스냅샷)은 건너뛴다. 재수집은 `--force`.

## 관문 6개 (전부 통과해야 실행)

| # | 관문 | 실패 시 |
|---|---|---|
| 1 | 매니페스트 존재 | 건너뜀 |
| 2 | SELECT dry-run이 테이블별 하드캡 이내 (versions_full 30 · versions_min 8 · requirements 22 · pkg_project 14 · projects 1 GiB) | **전체 중단** |
| 3 | 최신 스냅샷 dry-run이 실측 기대치 ±25% 이내 | 전체 중단 (`--allow-deviation`) |
| 4 | 이번 실행 누적 dry-run ≤ `--budget-gib` (t0 60 · t1 60 · t2 26 · t2m 40) | 그 잡 앞에서 정지 |
| 5 | `maximum_bytes_billed = dry-run × 1.25 + 512 MiB`. 일반 SELECT → 스테이징 테이블(`oss-shift-a506.staging`, 3일 자동 만료) → `extract` 잡으로 GCS Parquet(무과금) → 스테이징 삭제 | BigQuery가 잡을 거부, **과금 없음** |
| 6 | 스테이징 테이블 행 수 = `INFORMATION_SCHEMA.PARTITIONS` 행 수 (requirements·projects 정확, versions 1% 이내, pkg_project 상한) | 매니페스트에 MISMATCH 기록 후 중단 (`--continue-on-mismatch`) |

## 왜 EXPORT DATA 를 쓰지 않는가

처음 설계는 `EXPORT DATA … AS SELECT` 한 문장이었다. 리허설에서 두 가지가 드러났다(2026-09-02).

1. EXPORT DATA 문장의 dry-run은 **클러스터 프루닝을 추정에 반영하지 않는다.** PackageVersions는 `System='NPM'` 프루닝 18.5 GiB가 빠져 24.4 → 43.0 GiB로 나오고, `Name='express'` 필터도 무시된다.
2. `maximum_bytes_billed`는 그 **추정치**에 대해 검사된다. 그래서 상한을 실측(0.4 GiB)에 맞춰 걸면 잡이 "46,264,221,696 or higher required"로 거부된다. 상한을 43 GiB로 풀면 실제 과금이 얼마일지 보장할 수 없다.

일반 SELECT → 스테이징 테이블은 추정·상한·과금 세 가지가 전부 프루닝을 반영한다(리허설 4건: dry-run 1.325 GiB, 과금 1.326 GiB). 행 수도 테이블 메타데이터에서 정확히 나오고, `extract` 잡은 무과금이다. 스테이징 저장 비용은 24 GB × $0.02/GB·월을 하루 미만 쓰므로 무시 가능하다.

## 산출물

```
gs://oss-shift-a506-raw/raw/<table>/snapshot=YYYY-MM-DD/part-*.parquet
gs://oss-shift-a506-raw/raw/<table>/snapshot=YYYY-MM-DD/_MANIFEST.json   ← job_id · dry/billed 바이트 · 행수 · 검증 결과
pipeline/collectors/bigquery/ledger/ledger.jsonl                                              ← 실행된 모든 잡 1행씩 (git 추적)
```

`snapshot=` 폴더명은 Spark/DuckDB가 파티션 컬럼으로 자동 인식한다. 테이블: `versions_full` `versions_min` `requirements` `pkg_project` `projects`.
