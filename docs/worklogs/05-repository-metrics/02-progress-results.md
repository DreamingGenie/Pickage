# 05 실제 진행과 결과

작성일: 2026-09-09

## 변경 범위

05 worktree의 `pipeline/repository_metrics/`에 입력 고정, Spark 변환, Docker 실행, 출력 검증, immutable MinIO 게시 및 테스트를 구현했다. 03 worktree, 공통 모듈, DDL, PostgreSQL 적재 경로는 수정하지 않았다. 원본의 03 브랜치는 별도 진행하면서 `a173015`에서 `fb2f838`로 변경된 것을 읽기 전용으로 확인했다. 05는 초기 기준 `e3a8a62`의 `codex/05-repository-metrics`에서 독립 작업을 완료했다.

사용자와 다음 정책을 확정했다.

- 유효한 저장소를 선택했지만 같은 시각 Projects 관측이 없으면 저장소를 유지하고 metric을 `NULL`로 기록한다.
- ordinal 동률은 기존 Curated 정렬인 `ordinal DESC, published_at DESC NULLS LAST, version ASC`를 사용한다.
- 동일 저장소·시각의 metric 충돌은 metric을 `NULL`로 하고 근거를 남긴다.
- PySpark는 05 전용 환경에 설치·사용하고 03 환경은 변경하지 않는다.
- GitHub 비교 경로만 소문자로 통일한다. 선택 URL과 선택 경로 원문, 정확한 SnapshotAt은 보존한다. GitLab은 대소문자를 구분한다. `repository-metrics-v2` 정책으로 기록했다.

## 실제 진행한 작업

- Curated request의 `bronze_run_id`와 `sources.versions_full` fingerprint를 Bronze manifest와 대조.
- Curated service/auxiliary 파일의 승인 목록, attempt path, extra/누락, schema, row count, bytes, full SHA 검증.
- 로컬 `versions_full` manifest SHA, Bronze basename 목록, 실제 Parquet bytes/full SHA/row count 검증.
- Projects candidate의 exact calendar timestamp와 target partition만 선택하고 full SHA와 footer SHA를 별도 보존.
- 입력 변경을 감지하는 `reverify_inputs` 구현.
- 승인 version과 같은 시각 Bronze의 이름/버전 키·ordinal·배포일·release 조건을 검증하고, URL 정규화 후 결정된 순서로 후보 선택.
- provider·전체 경로·정확한 SnapshotAt의 원본 지표를 연결. 같은 저장소를 공유하는 package에 합산 없이 동일 관측 적용.
- 동일 지표 쌍 중복은 통합하고 상충 쌍은 NULL 및 충돌 근거 보존. 매핑 불가능한 원본은 별도 `quality/unmapped_projects`에 기록.
- 출력 Parquet의 실제 재독해 건수·스키마·SHA 확인 후 입력과 코드 불변성을 검증하고 manifest/_SUCCESS 생성.
- JSON 완료 파일은 같은 디렉터리의 임시 파일에 완전히 기록·fsync한 후 원자적인 hard link로 게시. 기존 파일은 덮어쓰지 않음.
- 같은 입력의 완료 run은 재계산 없이 재검증. manifest 이후 marker 이전 실패는 출력 검증을 거쳐 marker 복구. 다른 입력·코드·정책으로 같은 run ID 재사용은 거절.
- 실제 `build.py --engine docker`/`--engine native` 인자와 Docker runtime의 고정 공식 image digest(`apache/spark@sha256:936ff39fd63e2bb5ed064f0fbe1518198473f1cdbfa2f863d087a9a8e58116ba`)를 확인하고, read-only 입력 mount·별도 writable run output·immutable publish prefix·`_SUCCESS` 순서를 문서화.
- transform output 계약인 `quality/unmapped_projects`, mapping status, selection/candidate/null reason 집계를 문서화.

## 검증 결과

- `\.venv-repository-metrics\Scripts\python.exe -m unittest pipeline.repository_metrics.test_input -v` → 6 tests passed.
- build 테스트 12개 통과. 입력 테스트와 합쳐 18개 실행, 1.931초, 실패·skip 0개.
- Spark transform 테스트 13개 전체 통과, 103.530초, 실패·skip 0개. GitHub 비교 경로 정규화·원문 보존·동일 지표 통합·충돌 NULL 및 GitLab 대소문자 구분을 포함한다.
- host `transform_docker` → 공식 Spark 컨테이너 → 6종 Parquet 출력 연결 fixture 통과. 입력 package 1개, stars=4/open_issues=2, 충돌·매핑 실패 0개. 최신 fixture는 `data/repository-metrics/docker-bridge-smoke-fixture-fd451663`이며 컨테이너 내부 scratch를 사용했다.
- 독립 SQL 검증 도구의 최신 정책 분기는 별도 fixture에서 통과했다(0.687초, 모든 불일치 0건). GitHub 대소문자 통합·상이한 지표 쌍 구분·GitLab exact 비교도 DuckDB의 작은 입력으로 확인했다. 증거: `data/repository-metrics/independent-verifier-fixture-93ed413c04e24762b22dc8047b99d430/independent-verification.json`.
- 최종 독립 코드 검토에서 추가 correctness blocker가 없음을 확인했다. producer 코드는 실제 v3 실행 중 고정하고 문서와 독립 검증 도구만 별도 정리했다.
- 승인 입력 사전검증 418개 파일 완료:

  | 입력 | 행 수 |
  |---|---:|
  | package | 11,080,940 |
  | version | 54,188,349 |
  | versions_full | 78,559,731 |
  | projects | 5,234,999 |

  위 수치는 총 418개 입력 파일의 행 수다.

## 이슈와 해결 방법

- Bronze run manifest의 파일별 `rows`가 없는 정상 형식이 있어 파일별 `bytes`·SHA는 필수로 검증하고 실제 local Parquet row 합계를 Bronze `row_count`와 대조하도록 했다.
- Curated output에는 service 파일 외 package ID registry와 quality 파일이 있을 수 있어 전체 승인 manifest 집합은 엄격히 확인하되, package/version만 service schema와 table count를 검증하도록 분리했다.
- input manifest를 입력 디렉터리 내부에 생성하면 다음 재검증에서 입력 집합을 오염시키므로 output root가 입력 root 내부인 경우 차단한다.
- Windows Spark의 Parquet 출력은 `winutils`/`HADOOP_HOME` 문제로 실패해 공식 Linux 컨테이너로 전환했다. 컨테이너는 Java 11.0.27/Python 3.8.10/Spark 3.5.7, CPU 2개·메모리 6GB, 입력 read-only, network none이다.
- network none 상태에서 SparkSubmit이 Python 실행 전 hostname을 해석하다 실패했다. Docker 시작 시 `SPARK_LOCAL_IP=127.0.0.1`, `SPARK_LOCAL_HOSTNAME=localhost`를 주어 해결하고 host 함수 경유 재검증했다.
- Python 3.8은 trailing Z timestamp 파싱을 직접 지원하지 않아 05 경계에서 명시적 UTC offset으로 변환한다. 공유 snapshot policy는 그대로 사용한다.
- 원자적 기록 보완 전 실제 run `repository-metrics-20260909-v1`을 2026-09-09 00:54:47 UTC에 의도적으로 중단했다(exit 143). 이 run은 `FAILED`, `_SUCCESS` 없음이며 승인 산출물로 사용하지 않는다. 시작은 00:47:08 UTC였다.
- 독립 리뷰의 중복 쌍, NULL repository grouping, 후보 사유, 기존 Spark context 재사용, 반복 계산, 완료 marker 복구 및 원자적 기록 문제를 수정했다.

## 첫 전체 실행과 추가 정책 결정

`repository-metrics-20260909-v2`는 2026-09-09 00:55:54.678601~01:41:13.345340 UTC에 로컬 실행을 완료했다(45분 18.667초). Parquet 111개, 1,815,967,486바이트를 생성했고 별도 DuckDB 전체 대조 검증도 통과했다(14.047초, 모든 불일치 0건). 이 결과는 GitHub 경로를 대소문자까지 정확히 비교한 이전 정책이며 MinIO에 게시하지 않았다.

| 이전 정책 측정 | 패키지 수 |
|---|---:|
| 전체 지표 행 | 11,080,940 |
| 유효 저장소 선택 | 8,302,621 |
| 정확한 시각 관측 매핑 | 6,179,970 |
| 선택했으나 관측 부재 | 2,122,651 |
| 유효 저장소 후보 부재 | 2,778,319 |
| 두 지표 모두 NULL | 4,900,970 |

표본에서 `typescript`의 선택 경로 `microsoft/TypeScript`와 원본 관측 경로 `microsoft/typescript`가 달라 NULL이 되는 사례를 발견했다. 원본 전체를 별도 대조한 결과 970,515개 패키지·198,369개 저장소가 이 차이만으로 매핑되지 않았고, 소문자 통일에 따른 원본 저장소 중복/충돌 그룹은 0개였다. [GitHub 공식 API](https://docs.github.com/en/rest/repos/repos#get-a-repository)의 owner/repo 대소문자 비구분 계약을 확인하고 사용자에게 질의해 GitHub 비교 경로만 소문자화하는 정책을 확정했다. 원문 URL·경로와 정확한 관측 시각은 유지한다.

이전 전체 실행의 임시 정렬 파일은 Windows bind mount를 사용해 디스크 병목이 관찰됐다. 새 실행에서는 컨테이너 내부 Linux `/tmp/repository-metrics-runtime`에 scratch를 두고 최종 산출물만 05 폴더에 쓴다. CPU 2개·메모리 6GB 제한은 유지한다.

## 최신 정책 전체 실행

`repository-metrics-20260909-v3`는 2026-09-09 01:57:23.047412~02:22:48.478425 UTC에 완료됐다(25분 25.431초). 최신 정책 `repository-metrics-v2`와 정확한 관측 시각 `2026-08-31T21:01:10.517131Z`를 사용했다. Parquet 111개, 1,909,715,146바이트를 생성했다.

| 최종 패키지 결과 | 행 수 |
|---|---:|
| 전체 지표 / 고유 package_id | 11,080,940 |
| 유효 저장소 선택 | 8,302,621 |
| 정확한 시각 관측 매핑 | 7,150,485 |
| 선택했으나 관측 부재 | 1,152,136 |
| 유효 저장소 후보 부재 | 2,778,319 |
| 두 지표 모두 NULL | 3,930,455 |
| 실제 stars=0 | 504,766 |
| 실제 open_issues=0 | 1,476,898 |

GitHub 비교 경로 보정으로 이전 정책보다 970,515개 패키지에 지표가 추가 연결됐다. 선택 URL은 기존 Curated와 전부 일치하며 변경된 패키지는 0개다. 관측이 없는 저장소는 선택 URL을 유지하고 NULL로 남았다.

| 품질 결과 | 행 수 |
|---|---:|
| 후보 전체 | 54,188,349 |
| 유효 URL 후보 | 36,191,690 |
| URL 부재 후보 | 15,360,018 |
| URL 무효/미지원 후보 | 2,636,641 |
| 저장소 관측 | 5,217,958 |
| 충돌 관측 | 0 |
| 매핑 제외 원본 Projects | 17,041 |

매핑 제외 원본 17,041행은 모두 BITBUCKET이다. GitHub·GitLab만 지원하는 범위에 따라 원문과 사유를 `quality/unmapped_projects`에 보존했다. 이는 원본 관측 행 수이며 패키지 수와 다르다.

### 독립 전수 검증

Spark 구현과 별도의 DuckDB SQL로 원본 Projects를 provider/비교 경로/정확한 SnapshotAt 기준으로 집계하고, 모든 출력 지표와 대조했다. 21.953초에 통과했다.

- package_id 중복·잘못된 날짜·음수 지표·알 수 없는 package_id: 각각 0건.
- 기존 Curated 선택 URL과의 불일치: 0건.
- 원본에서 독립 계산한 저장소별 지표·중복 쌍 수·유효성·원본 행 수 불일치: 0건.
- 패키지별 지표·관측 시각·비교용 경로·원본 관측 대표 경로 불일치: 0건.
- 매핑된 원본 5,217,958 + 매핑 제외 17,041 = Projects 전체 5,234,999행.
- `typescript`: 선택 URL `https://github.com/microsoft/TypeScript` 유지, stars 110,779, open_issues 5,170, 정확한 관측 시각 일치.
- `@gitlab/ui`: 선택 URL 유지, 같은 시각의 정확한 경로 관측이 없어 NULL 및 `NO_EXACT_OBSERVATION` 유지.

실제 실행한 검증 명령(05 worktree에서 실행):

```powershell
$env:PYTHONPATH=(Get-Location).Path
.\.venv-repository-metrics\Scripts\python.exe -B `
  docs/worklogs/05-repository-metrics/verify_actual.py `
  data/repository-metrics/repository-metrics-20260909-v3
```

증거는 해당 run의 `run_manifest.json`, `_SUCCESS`, `independent-verification.json`, `attempts/f0f679c39fb04c8d8c33c2e1347342cf/execution-report.json`에 남겼다.

### 승인 해시

| 구분 | SHA-256 |
|---|---|
| 결과 manifest | `ca92eaa351fcd2ecd7d9355d3b5ee0635d9046ffecdb8fc946d28b226ecc0f30` |
| 입력 identity | `3d1add9f29eb0445dc98c235cd6376f0489d48effdfa507ffbdc6080ab18f49d` |
| 구현 코드 | `c880d0c4265a253d4fa651095f5db7bf68e53612b526078b42b2cbc1a017c98b` |
| 저장소 정책 | `4dc9174880b6b06eaba30e3d76081295f5fdb7b739199f411ae294ac47e1461d` |

### MinIO 게시

독립 검증 통과 후 같은 입력으로 `build --publish`를 재실행했다. 2026-09-09 02:23:30.259576~02:25:14.833301 UTC에 로컬 `REVERIFIED`, 원격 `PUBLISHED`로 완료됐다(1분 44.574초). Spark 재계산 없이 동일 입력·코드·정책과 출력 해시를 다시 확인했다.

```text
bucket: pickage-curated
prefix: depsdev/v1/repository-metrics/snapshot=2026-08-31/run_id=repository-metrics-20260909-v3
manifest: <prefix>/run_manifest.json
approval: <prefix>/_SUCCESS
verification: GET_SHA256_ALL_FILES
```

Parquet 111개를 업로드한 뒤 모두 GET으로 다시 읽어 bytes/full SHA를 확인했다. 이후 manifest와 그 SHA를 가리키는 `_SUCCESS`를 게시했다. 기존 package/version 포인터와 03 다운로드 prefix는 수정하지 않았다.

같은 완료 run을 다시 게시하는 검증도 19.391초에 통과했다. 원격 내용은 그대로 유지되고 action은 `REVERIFIED`, 검증 방식은 `GET_SHA256_ALL_FILES`였다. 로컬 `publication-reverification.json`에 결과를 기록했다. 주요 실행·원본·출력·독립 검증·게시 증거는 [03-measured-evidence.json](03-measured-evidence.json)에 함께 보존했다.

06은 이 명시적 run과 manifest SHA, 정책 `repository-metrics-v2`/`snapshot-time-v1`을 확인한 뒤 `files`에서 `dataset=metric/data`인 파일만 읽으면 된다. 품질 데이터와 이전 정책 v2 run은 지표 적재 대상이 아니다.

## 미실행 범위

PostgreSQL 적재는 06 범위로 실행하지 않는다. 과거 날짜의 package/version 원천이 없으므로 현재 사용 가능한 2026-08-31 스냅샷만 처리한다. 이 로컬 검증은 별도 서버 실행을 입증하지 않는다.

## 변경 파일과 마무리

- 구현·테스트·실행 안내: `pipeline/repository_metrics/`.
- 정책과 완료 상태: `docs/jira/db-loading/05-repository-metrics.md`.
- 분리 경계·계획·문제 해결·측정 증거: `AGENTS.md`, `docs/worklogs/05-repository-metrics/`.
- 기존 공통 함수를 그대로 재사용했고 새 의존성은 승인받은 `pyspark==3.5.7`이다. 파일 선택과 입력 검증은 기존 Curated 의존성을 사용한다.
- 독립 리뷰와 Python 문법 검증, 변경 범위의 공백·충돌 마커 검사를 통과했다. 기존 tracked 파일 변경과 staged 파일은 없다. 초기 복사한 다른 Jira 문서는 참고 사본이다.
- 코드와 자료는 05 worktree에 남아 있으며 commit/push는 수행하지 않았다. 03 환경·원본 및 PostgreSQL 적재를 변경하지 않았다.
