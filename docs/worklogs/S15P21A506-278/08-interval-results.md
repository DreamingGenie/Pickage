# 08. 스냅샷 구간 다운로드 집계·Curated 게시 결과

**2026-09-09 로컬 MinIO 실제 게시와 동일 입력 재검증을 완료했다.** 기준일 `2026-08-31`의
승인 패키지 11,080,940개에 대해 이전 기준일 `2026-08-24`부터 30일까지의 다운로드를 집계했다.
유효 값이 일부만 있어도 부분합을 게시하며, 기대·관측·유효 일수와 누락 사유를 함께 남긴다.

[계약](06-interval-contract.md) · [실행 안내](../../../pipeline/downloads_interval/README.md) ·
[원본 입고 결과](05-results.md) · [실행 증거](evidence/interval-load.json) ·
[전체 대조 결과](evidence/interval-reconciliation.json)

## 실제 결과

| 결과 | 패키지 수 | 의미 |
| --- | ---: | --- |
| `COMPLETE` | 97,091 | 7일 모두 유효한 값의 합계 |
| `PARTIAL` | 637 | 유효 날짜의 부분합과 NULL·gap 등의 사유 |
| `UNAVAILABLE` | 10,983,212 | 유효 값이 없어 합계 NULL |
| 합계 | 11,080,940 | 승인 모집단 전체, `(package_id,snapshot_at)` 중복 없음 |

NULL 가운데 10,983,195개는 다운로드 수집 대상 목록 밖 패키지이고, 17개는 `NOT_FOUND`다.
이는 집계 오류나 임의 누락이 아니다. 약 10만 개 수집 대상과 전체 승인 패키지 모집단의 범위가
다르므로 대상 밖 패키지도 기존 ID의 NULL 행으로 유지한다. 반대로 다운로드 대상 중 승인
모집단에 없는 2,251개 이름은 새 ID를 만들지 않고 별도 보고했다.

대상 CSV 100,000행의 고유 이름은 99,996개이며, 중복 4행은 합계 조인 전에 이름 기준으로
중복을 제거했다. 구간의 실제 일별 입력은 694,505행이다. 유효 합계 총합은 213,093,115,787이며
그중 부분합 행의 합은 504,212,835다. 서로 다른 패키지의 다운로드를 더한 값이므로 이용자 수를 뜻하지 않는다.

이번 실제 출력에서 합계 0인 패키지는 0개다. 실제 0과 부분합 0의 보존은 소형 fixture에서
검증했으며, 실제 출력에 0 사례가 있었다고 해석하지 않는다.

| 패키지 | package_id | download_sum | expected / observed / valid | 상태 |
| --- | ---: | ---: | --- | --- |
| `react` | 9,633,488 | 170,792,304 | 7 / 7 / 7 | COMPLETE |
| `typescript` | 10,602,005 | 273,437,565 | 7 / 7 / 7 | COMPLETE |
| `@acuminous/bitsyntax` | 72,482 | 453,518 | 7 / 7 / 6 | PARTIAL |

마지막 예시는 7일 행 중 하루가 NULL·gap이어서 6일의 합계를 게시했다.
`quality_reasons=[MISSING_DAILY_VALUES,NULL_VALUE,IMPUTED_GAP]`, `null_reason=NULL`이다.
날짜별 상세 6,759행은 `ROW_MISSING` 5,467행, `NULL_VALUE` 646행, `IMPUTED_GAP` 646행이다.
동일 날짜에 NULL과 gap이 함께 있으면 사유 두 행으로 남기므로 상세 행 수는 누락 날짜 수와 다르다.
상세에는 승인 모집단 밖 수집 대상도 포함하며 그 `package_id`는 NULL이다.

## 입력·게시 위치와 해시

| 항목 | 고정값 |
| --- | --- |
| 실행 ID | `downloads-interval-278-20260909-v1` |
| 결과 prefix | `s3://pickage-curated/npm-downloads-interval/v1/snapshot=2026-08-31/run_id=downloads-interval-278-20260909-v1/` |
| 결과 manifest SHA | `7dfc0cb5b76102d35f9baa28e03d7370bbd0d9a241b9c4a58ba3de8a95906377` |
| 불변 입력 manifest SHA | `a0b80537f35e000a471ed95ce4e10c5f25264b587b6c433b0aed9561a777a9d7` |
| 시간 정책 | `snapshot-time-v1`, SHA `2ceb32a89212705db607d97e83a4cda96cc301e80c30d17da439d8f4b5579690` |
| 부분합 정책 | `downloads-interval-v1`, SHA `d037ae76e351c6b8b1613a1e9e724c5b375350967620d7a133fa7a4b47037427` |
| 코드 계약 SHA | `6174089e272c8a694463763230b3d7112a23b5f9004958d194df751556f73469` |

입력별 SHA와 정확한 파일 목록은 [입력 대장](evidence/interval-inputs.json)에 있다. 소비한 원격 파일은
target CSV 1개, status 1개, 일별 7개, 승인 `package/data` 4개, 총 13개·128,752,819바이트다.
이 파일은 전체 GET·크기·SHA, CSV 행 수, Parquet footer 행 수와 schema/값 관계를 검증했다.
게시 직전에도 로컬 캐시와 원격 입력을 다시 검증했다. 선택하지 않은 Bronze 및 Curated 파일은
승인 manifest·완료 표시로만 연결했고 전체 바이트를 다시 스캔하지 않았다.
Projects는 후보·SQL·inventory 파일 SHA와 원천 footer inventory를 검증했으며 전체 원본 바이트 검사는 아니다.

전체 Projects 달력 229개에서 P를 정한 후 S를 선택했다. 다른 228개 날짜는 이 실행에 승인
모집단 입력을 지정하지 않아 제외했다. 최신 모집단을 과거 날짜에 소급하지 않는다.

| 원격 파일 | 행 수 | 바이트 |
| --- | ---: | ---: |
| `data/interval_downloads.parquet` | 11,080,940 | 46,433,960 |
| `data/daily_quality.parquet` | 6,759 | 42,399 |
| `data/unmatched_packages.parquet` | 2,251 | 34,368 |

결과 파일 합계는 46,510,727바이트다. 제어 객체 `run_manifest.json`, `_INPUT.json`, `_SUCCESS`를
포함해 새 객체는 6개다. 파일별 SHA는 [실행 증거](evidence/interval-load.json)에 기록했다.

## 실행·검증 근거

| 검증 | 관측 결과 |
| --- | --- |
| 첫 실제 실행 | 2026-09-09 11:27:48~11:28:27 KST, 39.515초, `PUBLISHED` / `LOADED` |
| 동일 입력 재실행 | 11:28:28~11:29:11 KST, 42.562초, `REVERIFIED` |
| 실행 환경 | 기존 `.venv-bq`, DuckDB 1.5.5, DuckDB 메모리 제한 2GB·threads 4, 다운로드 workers 4 |
| 신규 검증 | 구간 입력·집계·게시 55개, 실제 로컬 MinIO 3개 포함 |
| 회귀 검증 | 원본 입고 28개 + 기존 MinIO 3개 = 31개 |
| 전체 테스트 | 86개 통과, 실패·오류·skip 0, 26.375초. [상세 로그](evidence/interval-tests.log)·[해시와 요약](evidence/interval-tests.json) |
| 독립 대조 | 원본 일별 데이터를 별도 SQL로 집계해 전체 출력의 합계·관측·유효 일수 대조, 불일치 0건 |
| 모집단·품질 검사 | 출력/승인 ID 집합 일치, 중복 0, 구간·상태·대상 밖 NULL·lineage 해시 확인 |
| 불변 게시 | 두 실행의 manifest 및 결과 3개 SHA 동일. 결과 전부 원격 GET·SHA 재검증 |
| 기존 객체 보존 | 실행 전 원격 객체 4,880개의 키·크기·ETag·수정 시각 불변. 기존 객체 전체의 바이트 재검사라는 뜻은 아님 |

2GB는 DuckDB에 설정한 제한값이며 프로세스의 실제 최대 메모리를 측정한 값은 아니다.
전체 실행 시간에는 입력 준비, Projects inventory 확인, 집계, 게시와 입력 재검증이 포함된다.

재현 테스트는 저장소 루트에서 실행한다. MinIO 검증은 고유 시험 prefix에만 쓰고 정리한다.

```powershell
$env:DOWNLOADS_INTERVAL_MINIO_TEST = '1'
.venv-bq\Scripts\python.exe -m unittest discover -s pipeline/downloads_interval -t . -v
$env:DOWNLOADS_MINIO_TEST = '1'
.venv-bq\Scripts\python.exe -m unittest discover -s pipeline/downloads -t . -v
.venv-bq\Scripts\python.exe -m unittest discover -s pipeline/minio -v
```

실제 동일 입력 재실행 명령:

```powershell
.venv-bq\Scripts\python.exe -m pipeline.downloads_interval.load `
  --snapshot 2026-08-31 `
  --bronze-run-id downloads-278-20260909-v1 `
  --bronze-manifest-sha256 0617c12a1c810ecc11fcc01e281e375a8c1aa53bdb5ba57dab15a61120eec35d `
  --curated-run-id curated-20260907-v2 `
  --curated-manifest-sha256 a537f84bae78c9209e56deddb24d94cdef606d06e0e563f93ddb67e3843e71b3 `
  --candidate data/snapshot/S15P21A506-269/projects-v1/snapshot-candidate.json `
  --candidate-sha256 d22099ce22031deb47993f5c66b633d3754fd0625dbb1dcbaafc60070f8afaa7 `
  --run-id downloads-interval-278-20260909-v1
```

위 명령은 같은 입력·코드 계약에서 재검증한다. 코드/정책/입력이 바뀐 실행은 새 run ID를 사용한다.
현재 원본 파일과 로컬 MinIO가 있는 환경에서 실행하며 새 다운로드 API 호출은 하지 않는다.

## 직접 SQL로 보기

아래는 저장소 루트를 기준으로 실행하는 DuckDB SQL이다. 첫 실제 실행의 파일 한 개를 정확히
지정한다. 여러 attempt를 wildcard로 함께 읽으면 재실행 결과가 중복 집계되므로 피한다.

```sql
CREATE OR REPLACE VIEW interval_result AS
SELECT * FROM read_parquet(
  'data/downloads_interval/executions/downloads-interval-278-20260909-v1/d02900d932a04ca5a566e391afb44834/output/interval_downloads.parquet',
  hive_partitioning=false
);

SELECT data_status, count(*) AS packages, sum(download_sum) AS download_sum
FROM interval_result GROUP BY data_status ORDER BY data_status;

SELECT package_id, download_sum, expected_days, observed_days, valid_days,
       data_status, null_reason, quality_reasons
FROM interval_result WHERE package_id IN (72482,9633488,10602005)
ORDER BY package_id;

SELECT null_reason,count(*) FROM interval_result
WHERE download_sum IS NULL GROUP BY null_reason ORDER BY null_reason;
```

실제 데이터와 실행 기록은 `data/` 아래 로컬 산출물이며 Git에 포함하지 않는다. 다른 환경에서는
완료 manifest의 경로와 SHA로 MinIO 결과를 가져와 파일 경로를 바꿔 조회한다.

## 인계와 범위

AC-10~19의 입력 고정·구간·모집단·부분합·ID/값 정합성·불변 게시·테스트·실제 재실행·인계 조건을
위 증거로 충족했다. PostgreSQL `package_snapshot` 적재는 별도 후속 작업이다. 소비자는
`_SUCCESS`와 `run_manifest.json` SHA를 먼저 검증한 뒤 manifest에 적힌 3개 파일만 사용하고,
DB 실행 이력에 이 run ID·manifest SHA·정책 SHA를 연결해야 한다.

부분합을 전체 기간 합계와 구분하기 위해 `data_status`, `expected_days`, `valid_days`와 품질
정보를 함께 소비한다. 이번에는 PostgreSQL 데이터·스키마, 원격 Jira, 운영 스케줄러를 변경하지 않았다.
기존 raw→Parquet 생성 버전은 이전 입고에서 기록한 `UNVERIFIED` 상태를 그대로 유지한다.
