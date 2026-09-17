# 스냅샷 구간 다운로드 집계

`pipeline.preprocessing.downloads_interval`은 검증 완료된 npm 다운로드 원본과 승인된 Curated
패키지 모집단을 사용해 한 스냅샷 기준일의 구간 합계를 계산하고, 결과를
`pickage-curated`에 불변 실행 단위로 게시한다.

## 입력 계약

초도 실행의 기준일은 `S=2026-08-31`, 이전 기준일은 전체 Projects 달력에서 바로 앞의
`P=2026-08-24`다. 집계 구간은 `[P,S)`, 즉 2026-08-24부터 2026-08-30까지다.
현재 실행은 S=`2026-08-31`의 승인 Curated `package/data` 전체 모집단만 사용한다.
이 모집단은 11,080,940행이며, 다른 228개 과거 기준일의 최신 모집단을 소급하지 않는다.

입력은 다음처럼 고정한다.

| 입력 | 위치·식별자 | 검증 범위 |
| --- | --- | --- |
| 다운로드 Bronze | `pickage-raw/npm-downloads/v1/run_id=<id>` | `_SUCCESS`, manifest SHA, `_INPUT.json`, 파일 크기·SHA |
| 승인 Curated | `pickage-curated/depsdev/v1/package-version/snapshot=2026-08-31/run_id=<id>` | `select_run`으로 완료 manifest와 snapshot timestamp, package/data schema·행 수 확인 |
| Projects 달력 | `data/snapshot/.../snapshot-candidate.json` | 후보 SHA, sidecar SQL·inventory 파일 SHA, 달력·Projects footer inventory |

실제로 읽어 캐시하는 선택 입력은 target CSV 1개, status Parquet 1개, 구간 일별
Parquet 7개, 승인 Curated package/data Parquet 4개로 총 13개다. 이 13개는 원격 GET과
로컬 SHA를 모두 확인하며, 재검증 때 다시 원격 GET SHA를 확인한다. 선택하지 않은 Bronze·
Curated 파일은 승인 manifest와 완료 표시만 검증하고 바이트 전체를 소비하지 않는다.
Projects 후보는 고정 SHA와 footer inventory를 확인하며 Projects 전체 원본의 전체 바이트
SHA를 계산하는 계약은 아니다.

## 결과와 품질

주 결과 `interval_downloads.parquet`의 grain은 `(package_id, snapshot_at)`이다. 모든 승인
package/data 행을 유지하고 `download_sum`, `expected_days`, `observed_days`, `valid_days`,
`data_status`, `null_reason`, `quality_reasons`와 세 입력·정책 해시를 함께 저장한다. 주 출력은
13개 컬럼이다. `daily_quality.parquet`은 `(package_id, name, date, reason)` grain이며,
같은 날짜에 여러 사유가 있으면 여러 행으로 저장한다. `package_id`는 승인 모집단 밖 이름에서 NULL일 수 있다.

`downloads`가 NULL이 아니고 `imputed_gap=false`인 날짜만 합산한다. 실제 `downloads=0`은
유효한 0으로 유지한다. 유효 날짜가 하나 이상이면 합계를 게시한다. `valid_days`가
`expected_days`와 같으면 `COMPLETE`, 일부면 `PARTIAL`이다. 유효 날짜가 없을 때만
`download_sum=NULL`, `UNAVAILABLE`이 된다. `quality_reasons`는 여러 사유를 배열로 보존하며,
`daily_quality.parquet`에는 대상 이름별 날짜·사유 상세를 남긴다. 대상 목록 밖 이름은 승인 모집단에
포함된 경우 주 출력에 기존 `package_id`의 NULL 행으로 유지한다. 승인 모집단에 없는 대상 이름은
새 package ID를 만들지 않고 `unmatched_packages.parquet`에 기록한다.

게시 prefix는 다음과 같다.

```text
pickage-curated/npm-downloads-interval/v1/snapshot=<S>/run_id=<run-id>/
```

정상 게시물은 `data/interval_downloads.parquet`, `data/daily_quality.parquet`,
`data/unmatched_packages.parquet`, `run_manifest.json`, `_INPUT.json`, `_SUCCESS`다.
manifest에는 입력 manifest SHA, `snapshot-time-v1` 정책 SHA, `downloads-interval-v1`
집계 정책 SHA, 코드 계약 SHA, 출력 파일별 크기·SHA·행 수를 기록한다. `_SUCCESS`는
manifest SHA를 가리키며, 게시 전후 모든 결과 파일을 GET·SHA로 검증한다.

## 실행

원격 입력 SHA를 명시해 실행한다.

```powershell
.venv-bq\Scripts\python.exe -m pipeline.preprocessing.downloads_interval.load `
  --snapshot 2026-08-31 `
  --bronze-run-id <bronze-run-id> `
  --bronze-manifest-sha256 <bronze-manifest-sha256> `
  --curated-run-id <curated-run-id> `
  --curated-manifest-sha256 <curated-manifest-sha256> `
  --candidate data\snapshot\S15P21A506-269\projects-v1\snapshot-candidate.json `
  --candidate-sha256 <candidate-sha256> `
  --run-id <interval-run-id>
```

실행 디렉터리는 기본적으로 `data/downloads_interval/executions/<run-id>/<attempt-id>`다.
`--verify-only`를 사용하면 입력 재검증과 로컬 집계 결과 확인만 하고 MinIO에 쓰지 않는다.
실패 후 같은 run ID로 재실행하면 완료 marker가 없는 결과는 이어서 검증할 수 있다.
이미 `_SUCCESS`가 있는 동일 run ID는 manifest와 모든 객체가 같을 때 `REVERIFIED`로
끝나며, 완료 결과의 누락·변경 객체를 자동으로 고치지 않는다. 입력·정책·코드 해시가
바뀌면 기존 결과를 보존한 채 실행을 거부한다.

초도 11,080,940행 실제 집계·게시와 동일 입력 재실행 검증을 완료했다.
[실제 결과·정확한 재실행 명령·조회 SQL](../../../docs/worklogs/S15P21A506-278/08-interval-results.md)에 실측값을 기록했다. PostgreSQL 쓰기와 DB
실행 이력 연결은 이 모듈의 책임이 아니며 후속 `package_snapshot` 적재 작업에서 연결한다.

승인 Bronze에는 전체 다운로드 보유 범위를 확인할 일별 파일이 있어야 한다. 첫 스냅샷에서
이전 P가 없으면 그 파일 목록에서 선택하는 구간 일별 입력은 비어 있고 `NO_PREVIOUS_SNAPSHOT`을 만든다.

## 검증

저장소 루트에서 실행한다. 실제 MinIO 테스트는 고유한 시험 prefix에만 쓰고 완료 후 정리한다.

```powershell
$env:DOWNLOADS_INTERVAL_MINIO_TEST = '1'
.venv-bq\Scripts\python.exe -m unittest discover -s pipeline/preprocessing/tests/downloads_interval -t . -v
```

신규 테스트 55개가 통과했다. 기존 원본 입고·MinIO 회귀 31개를 포함한 86개 검증 결과는
[테스트 기록](../../../docs/worklogs/S15P21A506-278/evidence/interval-tests.json)에 남겼다.
