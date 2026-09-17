# Repository metrics 입력·실행 계약

05번은 승인된 package/version과 Projects 관측을 snapshot별로 연결해 `stars`와 `open_issues`를 만드는 작업이다. 이 디렉터리는 03번 다운로드 작업과 공통 모듈을 수정하지 않는 전용 경로다. PostgreSQL `package_snapshot` 반영은 06번 범위다.

## 확정된 정책

- Projects의 `SnapshotAt`은 snapshot calendar의 timestamp와 정확히 일치해야 한다. 과거·미래 관측값으로 대체하지 않는다.
- 유효한 저장소 URL을 선택했지만 같은 시각 Projects 관측이 없으면 저장소 선택은 유지하고 `stars`와 `open_issues`를 `NULL`로 기록한다. 관측 부재 사유는 evidence에 남긴다.
- 후보 정렬은 `ordinal DESC`, `published_at DESC NULLS LAST`, `version ASC`다. URL이 무효이면 다음 후보를 시도한다.
- provider와 전체 project path가 저장소 식별자다. GitHub와 GitLab의 같은 경로 문자열은 서로 다른 저장소다.
- `repository-metrics-v2`는 GitHub 비교 경로를 소문자로 통일하고 GitLab은 대소문자를 유지한다. 선택 URL 원문은 바꾸지 않는다. [GitHub 공식 API](https://docs.github.com/en/rest/repos/repos#get-a-repository)의 owner/repo 대소문자 비구분 규칙과 사용자 결정을 반영한다.
- 같은 provider/path/timestamp에 서로 다른 metric 값이 있으면 충돌로 기록하고 두 metric을 `NULL`로 만든다. 완전히 같은 중복 관측은 하나로 합친다.
- API 재호출, 최신 URL을 이용한 과거 소급, package별 metric 합산, PostgreSQL 적재는 이 작업에서 하지 않는다.

## 입력 고정

`prepare_inputs(...)`는 다음을 모두 읽기 전용으로 확인하고 deterministic `input-manifest.json`을 만든다.

1. 완료된 Curated package/version run의 `_SUCCESS`, run manifest, service files.
2. Curated request의 `bronze_run_id` 및 `sources.versions_full` fingerprint와 일치하는 Bronze `versions_full` run.
3. 승인된 snapshot candidate와 Projects inventory.
4. 로컬 Curated output, `versions_full`, Projects Parquet 파일과 각 manifest.

Curated service 파일은 package/version schema·row count·size·full SHA를 확인한다. auxiliary 파일도 승인 manifest의 전체 파일 집합, size, full SHA를 확인한다. `versions_full`은 Bronze의 basename 목록과 대조하고 실제 row 합계를 Bronze `row_count`와 비교한다. Projects는 target partition만 선택하고 full-file SHA와 Parquet footer SHA를 별도로 보존한다.

입력 manifest에는 snapshot timestamp, policy version/hash, candidate SHA, Curated/Bronze manifest SHA, source paths, table별 파일 목록·row count·size·SHA가 들어간다. `reverify_inputs(prepared, s3=None)`는 재실행 직전에 로컬 파일과 source metadata를 다시 확인하며, `s3`를 주면 Curated/Bronze 원격 lineage도 재확인한다.

## Spark 실행과 Docker 경계

대량 transform은 Spark 3.5.7을 사용한다. Docker runtime의 공식 image는 `apache/spark@sha256:936ff39fd63e2bb5ed064f0fbe1518198473f1cdbfa2f863d087a9a8e58116ba`로 고정했고 실행 manifest에 기록한다. Windows에서는 Docker Desktop이 필요하다. host Python에는 `python -m pip install -r pipeline/preprocessing/repository_metrics/requirements.txt`로 전용 환경의 의존성을 설치한다.

`build.py`는 host Python에서 실행하며 `--engine docker`일 때만 transform subprocess를 Docker로 격리한다. Docker CLI에 `--engine` 옵션을 전달하지 않는다. 현재 입력 위치는 다음과 같다.

```text
worktree:        C:\Users\SSAFY\workspace\S15P21A506-05-repository-metrics
Projects:        C:\Users\SSAFY\workspace\S15P21A506\data\raw\projects
versions_full:   C:\Users\SSAFY\workspace\S15P21A506\data\raw\versions_full\snapshot=2026-08-31
Curated:         C:\Users\SSAFY\workspace\S15P21A506\data\curated\curated-20260907-v2-oxudhdl5\outputs
candidate:       C:\Users\SSAFY\workspace\S15P21A506\data\snapshot\S15P21A506-269\projects-v1\snapshot-candidate.json
```

Windows PowerShell의 전체 실행 명령이다. 아래 경로는 2026-09-09 검증 환경 기준이다.

```powershell
$repo = 'C:\Users\SSAFY\workspace\S15P21A506-05-repository-metrics'
$source = 'C:\Users\SSAFY\workspace\S15P21A506'
Set-Location -LiteralPath $repo
& "$repo\.venv-repository-metrics\Scripts\python.exe" -B -m pipeline.preprocessing.repository_metrics.build `
  --snapshot 2026-08-31 `
  --curated-run-id curated-20260907-v2 `
  --curated-outputs "$source\data\curated\curated-20260907-v2-oxudhdl5\outputs" `
  --versions-dir "$source\data\raw\versions_full\snapshot=2026-08-31" `
  --projects-dir "$source\data\raw\projects" `
  --candidate-path "$source\data\snapshot\S15P21A506-269\projects-v1\snapshot-candidate.json" `
  --run-id repository-metrics-20260909-v3 `
  --work-dir "$repo\data\repository-metrics" `
  --minio-env "$source\pipeline\minio\.env" `
  --engine docker --threads 2 --driver-memory 4g
```

네이티브 Linux에서는 같은 `build.py`를 host Python으로 직접 실행하고 `--engine native`를 명시한다. 아래는 worktree를 `/workspace/S15P21A506-05-repository-metrics`에 checkout한 실행 호스트의 절대 경로 예시이며, 모든 입력은 별도 read-only source root에서 읽고 output은 worktree의 `data/repository-metrics`에 쓴다.

snapshot candidate에는 입력의 절대 경로가 들어 있다. Linux로 옮겨 실행할 때는 02의 절차로 그 호스트 경로에 맞는 candidate를 검증·생성한 뒤 지정해야 한다. Windows의 candidate 파일을 그대로 가져오면 경로 검증에서 거절된다.

```bash
REPO=/workspace/S15P21A506-05-repository-metrics
SOURCE=/workspace/S15P21A506
cd "$REPO"
"$REPO/.venv-repository-metrics/bin/python" -m pipeline.preprocessing.repository_metrics.build \
  --snapshot 2026-08-31 \
  --curated-run-id curated-20260907-v2 \
  --curated-outputs "$SOURCE/data/curated/curated-20260907-v2-oxudhdl5/outputs" \
  --versions-dir "$SOURCE/data/raw/versions_full/snapshot=2026-08-31" \
  --projects-dir "$SOURCE/data/raw/projects" \
  --candidate-path "$SOURCE/data/snapshot/S15P21A506-269/projects-v1/snapshot-candidate.json" \
  --run-id repository-metrics-20260831-native \
  --work-dir "$REPO/data/repository-metrics" \
  --minio-env /secure/pickage-minio.env \
  --engine native
```

`--engine docker`는 `build.py`의 실행 engine이며 Docker CLI 옵션이 아니다. `docker_runtime.py`는 `/workspace`에 repository code를 read-only로, `/input/curated`, `/input/versions`, `/input/projects`에 각 source root를 read-only로, `/run`에 해당 attempt output을 writable로 mount하고 network를 끈다. 컨테이너 내부 경로와 host 경로는 `spark-invocation.json` 및 run manifest에 남긴다. Spark executor가 로컬 파일을 공유한다고 가정하지 않으며, 다중 executor 실행 시 공용 object storage 또는 명시적인 read-only 입력 staging을 사용한다.

Docker의 Spark scratch/warehouse는 컨테이너 내부 `/tmp/repository-metrics-runtime`에 둔다. Windows bind mount에서 발생한 임시 정렬 파일 I/O 병목을 줄이기 위한 선택이며, 임시 파일은 컨테이너 제거와 함께 정리된다. 최종 산출물·실행 로그·manifest는 `/run`을 통해 05 worktree에 남는다.

## 출력·게시 계약

각 run은 fresh directory에 다음을 생성한다.

- package/snapshot별 metric Parquet: package당 snapshot 한 행
- 후보 선택 및 fallback evidence Parquet (`quality/selection`, `quality/candidates`)
- repository 관측·충돌 evidence Parquet (`quality/project_observations`, `quality/project_conflicts`)
- provider/path 매핑 실패 evidence (`quality/unmapped_projects`)
- `quality/selection.mapping_status`와 `run_manifest.report`의 `selection_reasons`, `null_reasons`, `candidate_reasons` 집계
- 입력/코드/policy/image hash와 counts를 담은 run manifest

local validation, transform completed, MinIO publish completed는 서로 다른 상태다. MinIO 게시 prefix는 run별 immutable 경로를 사용한다.

```text
pickage-curated/
  depsdev/v1/repository-metrics/snapshot=YYYY-MM-DD/run_id=<run>/
```

게시 순서는 output 파일 업로드 → GET/full SHA 검증 → run manifest immutable write → `_SUCCESS` write다. `_SUCCESS`는 manifest SHA를 가리키며, 어느 단계에서든 실패하면 게시 완료로 기록하지 않는다. 기존 run prefix나 current pointer를 덮어쓰지 않고 같은 입력 재실행만 원래 계약과 SHA가 일치할 때 재검증한다.

MinIO 게시까지 수행하려면 위 실행 명령에 `--publish`를 추가한다. 이미 완료된 run은 입력·코드·정책과 모든 출력 해시를 다시 확인하고 변환을 생략한다. 게시가 실패한 run도 같은 명령으로 재시도할 수 있다. 입력이나 구현이 바뀌면 새 run ID가 필요하다. 강제 종료로 `.writer.lock`이 남으면 해당 실행이 종료됐는지 확인한 후 그 lock만 정리해야 한다.

`metric/data`의 컬럼은 `package_id INT`, `snapshot_at DATE`, `stars INT NULL`, `open_issues INT NULL`이다. 06은 `_SUCCESS`가 가리키는 manifest의 `files` 중 `dataset=metric/data`만 소비한다. `quality/selection`은 패키지별 선택 버전·URL·provider·전체 경로·실제 관측 시각을 보존한다. 관측 부재의 `observed_timestamp`는 NULL이다. `quality/unmapped_projects`는 특정 패키지에 억지로 연결하지 않고 원본 관측 자체를 보존한다.

06은 현재 저장소 정책 `repository-metrics-v2`와 `snapshot-time-v1`도 확인해야 한다. 선택 근거의 `project_path`는 원래 선택 경로, `comparison_project_path`는 비교용 경로, `observed_project_path`는 원본 관측의 대표 경로다. 관측 파일의 `project_path`는 비교용 경로이고 `source_project_path`는 원본 경로다. 동일 비교 키에 여러 원문 표기가 있을 때 대표 경로는 문자열 최솟값으로 결정하며, 전체 원본은 입력 manifest의 파일 목록·해시로 추적한다.

`selection_reasons`는 모든 패키지를, `null_reasons`는 두 지표 중 하나 이상이 NULL인 패키지만 센다. `mapping.null`은 두 지표가 모두 NULL인 패키지 수다. 관측 행이 있지만 원본 지표가 NULL인 경우 `SELECTED` 사유와 관측 시각을 유지한다. 후보/관측/충돌 원본과 입력 SHA로 NULL 근거를 추적할 수 있다.

검증 명령:

```powershell
.\.venv-repository-metrics\Scripts\python.exe -B -m unittest pipeline.preprocessing.tests.repository_metrics.test_input pipeline.preprocessing.tests.repository_metrics.test_build -v
docker run --rm --cpus=2 --memory=6g --network=none `
  -e SPARK_LOCAL_IP=127.0.0.1 -e SPARK_LOCAL_HOSTNAME=localhost `
  -e PYTHONPATH=/workspace:/opt/spark/python:/opt/spark/python/lib/py4j-0.10.9.7-src.zip `
  -e PYTHONDONTWRITEBYTECODE=1 -v "${PWD}:/workspace:ro" --workdir /workspace `
  apache/spark@sha256:936ff39fd63e2bb5ed064f0fbe1518198473f1cdbfa2f863d087a9a8e58116ba `
  python3 -W ignore::ResourceWarning -m unittest pipeline.preprocessing.tests.repository_metrics.test_transform -v
```

## 현재 검증 상태

입력 테스트 6개, build 테스트 12개, transform 테스트 13개로 총 31개가 통과했다. GitHub 대소문자 비교·원문 보존·동일 관측 통합·충돌 NULL 및 GitLab 대소문자 구분을 포함한다. Docker 연결도 host 함수부터 Parquet 출력까지 작은 fixture로 통과했다. 실제 승인 입력 사전검증은 418개 파일을 대상으로 완료됐다.

| 입력 | 행 수 |
|---|---:|
| package | 11,080,940 |
| version | 54,188,349 |
| versions_full | 78,559,731 |
| projects | 5,234,999 |

`repository-metrics-20260909-v3`는 위 승인 입력으로 지표 11,080,940행을 생성했고, 7,150,485개 패키지에 관측값을 연결했다. GitHub 비교 경로 보정으로 이전 정책보다 970,515개가 추가 연결됐다. 두 지표가 모두 NULL인 패키지는 3,930,455개이며 사유를 보존했다.

독립 DuckDB 전수 검증에서 선택 URL·원본 지표·패키지 지표·관측 시각 불일치는 모두 0건이었다. Parquet 111개를 로컬 MinIO `pickage-curated/depsdev/v1/repository-metrics/snapshot=2026-08-31/run_id=repository-metrics-20260909-v3`에 게시했고 GET/full SHA 검증 후 `_SUCCESS`를 생성했다. 승인 manifest SHA는 `ca92eaa351fcd2ecd7d9355d3b5ee0635d9046ffecdb8fc946d28b226ecc0f30`이다.

측정값과 검증 증거는 [실제 진행·결과](../../../docs/worklogs/05-repository-metrics/02-progress-results.md)에 기록했다. 과거 package/version 원천은 없어 현재 사용 가능한 2026-08-31 스냅샷만 처리한다. PostgreSQL 적재는 06에서 별도 수행한다.
