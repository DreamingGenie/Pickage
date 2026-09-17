# npm 다운로드 원본 검증 및 Bronze 입고

이미 수집한 `data/raw/downloads`의 파일을 검증하고 로컬 MinIO `pickage-raw`에 보존한다.
원본 API를 다시 호출하거나 원본 파일을 변경하지 않는다. 스냅샷 구간 합계와 PostgreSQL 적재는
후속 작업이다. [다운로드 원본 입고·구간 집계 작업 기록](../../docs/worklogs/S15P21A506-278/README.md)에 범위·이슈·실측 결과를 남긴다.

스냅샷 구간 합계·Curated 게시도 같은 티켓(S15P21A506-278)에서 초도 실행까지 완료했다.
[구간 집계 계약](../../docs/worklogs/S15P21A506-278/06-interval-contract.md)을 따르며 구현은
별도 [구간 집계 모듈](../preprocessing/downloads_interval/README.md)에 둔다. 구간 집계 CLI와 결과는 해당 모듈 README와 작업 기록에 남긴다.

## 입력과 의미

| 파일 종류 | 선택 경로 | 검증 / 의미 |
| --- | --- | --- |
| 대상 CSV | `targets_top100k_20260902.csv` | CSV 행 수와 고유 이름 수를 구분한다. 중복 이름은 보고하고 원본 행을 보존한다. CSV의 `status`는 선정 힌트이며 수집 결과 상태로 해석하지 않는다 |
| 원본 응답 | `raw/run=<source-run>/part-*.jsonl.gz` | 압축·JSON 구조·상태·요청 날짜 범위·일별 정수 값 검증. 응답 한 행과 패키지·일별 행 수는 다르다 |
| 수집 메타데이터 | 같은 raw 실행의 `run.json`, `manifest.json` | 원본 바이트 보존, run·target 일치와 final 상태 확인. 누적 처리 횟수는 고유 패키지 수가 아니다 |
| 일별 Parquet | `parquet/downloads/date=YYYY-MM-DD/*.parquet` | `(name,date)` 유일성·타입·음수·NULL/gap·실제 0·상태 관계 검사. 날짜는 Hive 경로에서 파생하며 물리 date가 있을 경우 경로와 대조한다 |
| 상태 Parquet | `parquet/downloads_status.parquet` | 대상 이름 집합·유일성·READY/NOT_FOUND·요청 날짜 범위와 일별 값의 관계 검사 |

smoke 자료, `.broken`, checkpoint와 로그는 정상 입력에서 제외하고 사유를 기록한다.
알 수 없는 파일과 symlink 경로는 거부한다. 현재 수집 구조와 다른 새 run·파일 종류는 입력 계약을
확인한 뒤 반영하며, 오류를 피하려고 원본을 삭제하거나 이름을 바꾸지 않는다.

`READY`는 값이나 날짜의 완전성을 보장하지 않는다. NULL과 `imputed_gap`, 실제 0은 각각 집계한다.
`NOT_FOUND`를 0으로 보정하지 않는다. 상태의 첫·마지막 날짜는 수집 요청 범위로 해석하며,
원본 응답 시각·다운로드 대상 날짜·입고 시각을 구분한다.

## 생성 계보와 표본 대조

과거 커밋 `33b49adef8ea6f6f01bf1f91048ffcf239c7a73d`의
`pipeline/collectors/downloads/to_parquet.py`를 생성 규칙의 후보 근거로 확인했다.
blob은 `d9562f12af10e62eac98e81f604c9635522ba56a`다.
이 코드가 현재 원본의 실제 생성에 사용된 버전인지는 **미확인**이다.

검증기는 전체 gzip 응답을 스트리밍으로 확인하고, `ok` 패키지 이름 정렬 순서의 최대 8개를
결정적인 표본으로 선택한다. 표본의 모든 원본 응답에서 `(name,date)`별 최신 `fetched_at`을
선택하며 동률의 값 충돌은 거부한다. 날짜순 앞 7행·현재 행·뒤 7행의 중앙값이 1,000 이상일 때
원본 0을 NULL·gap으로 바꾸는 후보 규칙을 재현하고, 선택된 패키지의 Parquet 전체 키·값·gap과 비교한다.
이 창은 **최대 15개의 관측 행**이며 고정된 15일 구간이라는 뜻은 아니다.

전체 파일 해시 검사, 전체 행 품질 검사, 최대 8개 패키지의 변환 표본 대조는 검증 범위가 다르다.
전체 원본으로 Parquet를 재생성해 전 행을 비교했다고 주장하지 않는다. 실제 사용 코드 버전의
미확인 상태와 표본 대조 결과는 manifest의 `lineage`에 함께 보존한다.

## 실행

프로젝트 루트에서 기존 `.venv-bq` 환경의 DuckDB·boto3를 사용한다.
입력 검증은 메모리 기반 DuckDB(4GB, 4스레드)로 수행한다.
실제 입고는 기존 `pipeline/minio/ingest_raw.py`의 클라이언트를 통해
`http://localhost:9000`과 로컬 `pipeline/minio/.env`의 인증 설정을 사용한다.
인증 값을 명령행이나 실행 보고서에 적지 않는다.

먼저 로컬 입력만 검증하려면 다음과 같이 실행한다. 이 모드는 MinIO에 연결하지 않는다.

```powershell
.venv-bq\Scripts\python.exe -m pipeline.downloads.load `
  --source-root data/raw/downloads `
  --source-run 2026-09-02 `
  --run-id downloads-278-20260909-v1 `
  --verify-only
```

실제 입고는 같은 명령에서 `--verify-only`를 제외한다. 검증 전용 실행과 실제 입고 모두
입력 목록·전체 해시·전체 행 품질·원본 구조 및 표본 계보를 검사한다.
`--target-name`으로 대상 CSV 이름, `--work-dir`로 원본 밖의 실행 기록 위치를 지정할 수 있다.
기본 기록 위치는 `data/downloads/executions/<run-id>/<attempt-id>/`다.

```text
input-manifest.json       검증한 입력·코드 계약·품질·계보의 고정 JSON
execution_report.json     이번 시도의 상태·시각·결과·오류
```

동일한 입력·계약·run ID의 반복 실행은 동일 manifest를 생성한다. 실행 시각과 attempt ID는
별도 보고서에만 적으며 원격 manifest를 바꾸지 않는다. 입력 또는 코드 계약이 달라지면
새 Bronze run ID를 사용한다. 기존 완료 실행을 재검증하려면 해당 실행의 코드 계약과 입력을 유지한다.

## 원격 실행과 완료 계약

```text
pickage-raw/npm-downloads/v1/run_id=<run-id>/
  _INPUT.json             이 경로에 처음 고정한 manifest SHA-256
  data/<원본 상대 경로>    선택한 원본 파일의 동일 바이트
  run_manifest.json       파일 목록·종류·통계·품질·계보·코드 계약
  _SUCCESS                run_manifest.json의 SHA-256와 줄바꿈
```

모든 새 객체는 `IfNoneMatch='*'` 조건부 생성으로 기존 내용을 덮어쓰지 않는다.
같은 경로의 동시 생성에서는 기존 내용이 같은 경우만 받아들인다. 단일 PUT의 지원 범위는
파일당 5GiB 이하이며, 그보다 큰 파일은 업로드 전에 거부한다.

업로드한 파일을 전부 GET으로 다시 읽어 크기·SHA-256을 대조하고, 선택 목록과 로컬 원본도
재확인한 뒤 `_SUCCESS`를 게시한다. 일부 파일이나 manifest만 존재하는 실행은 완료가 아니다.
완료 run 재실행은 모든 원격 파일을 재검증하며 누락 객체를 자동 복구하지 않는다.

| 상태 | 의미 |
| --- | --- |
| `VERIFIED` | 로컬 검증 전용 실행 성공. 원격 완료를 의미하지 않음 |
| `PUBLISHED` / `LOADED` | 전체 검증을 거쳐 새 실행의 완료 표시를 게시 |
| `REVERIFIED` | 기존 완료 run의 manifest·파일과 현재 입력의 동일성 재검증 |
| `FAILED` | 이번 시도 실패. 원래 완료된 원격 run의 성공을 취소하지 않음 |

실패한 새 run에는 업로드된 일부 객체가 남을 수 있다. 원인 해결 후 **같은 입력과 계약**으로
재실행하면 기존 객체를 검사하며 이어간다. 다른 내용이 발견되면 원본과 실행 기록을 조사하고,
완료 표시나 기존 객체를 임의로 삭제하여 검증을 우회하지 않는다.

후속 집계는 `_SUCCESS`의 manifest 해시를 확인하고 manifest에 명시된 일별·상태 파일만 읽는다.
다른 실행이나 시험·실패 파일을 한꺼번에 읽지 않는다. 구간 계산에는
[스냅샷 시간 정책 — S15P21A506-269](../preprocessing/snapshot/README.md)의 `[P,S)`를 적용한다.

## 검증

```powershell
.venv-bq\Scripts\python.exe -m unittest pipeline.downloads.test_input pipeline.downloads.test_lineage pipeline.downloads.test_bronze pipeline.downloads.test_load -v
```

실제 로컬 MinIO fixture 검사는 아래와 같다. 테스트는 고유한 `test-278-<uuid>` 실행 경로만 쓰며
각 테스트 종료 시 그 경로의 객체만 정리한다. 기본 실행에서는 이 검사가 생략되므로 실제 실행 여부와
skip 수를 결과에 명시한다.

```powershell
$env:DOWNLOADS_MINIO_TEST = '1'
.venv-bq\Scripts\python.exe -m unittest pipeline.downloads.test_integration -v
```

실제 전체 입력의 통과 건수와 완료 run은 [다운로드 원본 검증·입고 결과](../../docs/worklogs/S15P21A506-278/05-results.md)에서 확인한다.
