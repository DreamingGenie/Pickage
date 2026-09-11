# 07 requirements snapshot 해석

현재 구현 결과와 실제 테스트 데이터 표는 [결과 보기](../../docs/worklogs/S15P21A506-283/04-results-preview.md)에서 확인한다.

승인된 동일 snapshot의 Bronze `requirements`, `versions_full`과 Curated `package`, `version`을 사용해 관측된 의존성 선언을 특정 target 버전에 연결한다. 모든 eligible source 릴리스 버전을 유지한다. 설치된 실제 의존성 그래프 또는 npm install 결과를 재현하는 파이프라인은 아니다.

## 현재 결정과 실행 경계

2026-09-09 사용자 결정: 일반 `Dependencies`만 계산한다. peer/optional 원문은 승인된 Bronze 파일과 manifest 계보로 보존하며, source 결과에 제외 개수를 기록하고 정책에 제외 사유를 기록한다. 별도 결과 파일에 원문을 중복 복사하지 않는다.

정책 선택과 결과 검토 후 전체 데이터 계산을 완료했다. 실측 결과는 [전체 실행 기록](../../docs/worklogs/S15P21A506-283/05-full-run.md)과 [계산 결과](../../docs/worklogs/S15P21A506-283/06-computation-results.md)에 남긴다. 결과는 PARTIAL이며 정상 완료 결과로 게시하지 않는다.

실제 run은 Spark 결과 파일 생성 후 host 후속 단계가 완료되지 않아 표준 `run_manifest.json`과 `_SUCCESS`가 없다. 재부팅 후 추가 전수 검증도 메모리 한도로 중단됐다. 코드·합성 입력 테스트 통과와 실제 run의 게시 준비 상태를 구분하며, [현재 검증 범위](../../docs/worklogs/S15P21A506-283/07-final-verification.md)를 함께 확인한다.

| 정책 | 선택 가능한 값 | 의미 |
| --- | --- | --- |
| `unknown_published_at` | `exclude` | 배포일 NULL인 릴리스를 07 source와 target에서 제외 |
| `unresolved` | `partial` | 미해석/불완전 source와 선언 결과를 PARTIAL로 보존 |

`make_policy`의 필수 인수와 `decision_reference`로 선택을 명시한다. 승인 정책 파일은 `data/requirements-resolution/policy.json`에 저장했다. 코드가 임의의 승인 문구의 진위를 확인하지는 않으므로 실제 결정 기록을 함께 보존해야 한다.

## 입력과 처리

1. Curated 완료 marker와 manifest, 연결된 Bronze 두 run의 정확한 계보를 확인한다.
2. 승인 파일 목록과 로컬 파일 목록·바이트·SHA256·Parquet 행 수·스키마를 대조한다. raw의 모든 행은 정확히 같은 `SnapshotAt`이어야 한다. 로컬 raw `_MANIFEST.json`은 파일 목록이 없는 추출 요약이며 승인된 원격 source manifest의 SHA와 대조한다.
3. Spark가 Curated 전체 버전과 raw 릴리스·배포일의 일치를 검사하고, 같은 시점의 source·target 후보와 선언을 생성한다. 미래 배포를 제외하며 `NULL` 배포일에는 명시적 정책을 적용한다.
4. DuckDB가 고유 `(declared_name, requirement)` 요청을 정렬한다. 하나의 Node 프로세스가 target 패키지 하나의 버전 후보를 유지하며 npm semver로 해석한다. 전체 그래프를 드라이버에 수집하지 않는다.
5. Spark가 해석 결과를 모든 선언에 다시 연결하고 source coverage, edge 및 품질 Parquet를 기록한다. 중복 선언은 유지하고 edge만 복합키로 합친다.
6. 입력을 재검증하고 결과의 정확한 파일 집합·SHA·행 수·상태 정합성을 검증한 후 manifest와 마지막 완료 marker를 기록한다.

패키지명은 스코프를 포함한 정확한 npm 이름으로 기존 `package_id`에 연결한다. `version.dependency` 표시용 JSON과 저장소 provider ID는 계산에 사용하지 않는다. Curated `version`에는 `is_release`가 없으므로 승인된 `versions_full`에서 확인한다.

## 해석 계약

- 실제 설치된 npm `semver.maxSatisfying`, `loose=false`, `includePrerelease=false`를 사용한다. 문자열 강제 보정과 ordinal 순위 대체는 없다.
- target 후보는 같은 snapshot의 eligible release이며 유효한 stable semver여야 한다. source는 대표 버전으로 축소하지 않는다.
- semver 우선순위가 같은 build metadata 버전은 원래 문자열의 UTF-16 오름차순을 동률 규칙으로 사용한다. 원래 target 버전 문자열을 보존한다.
- alias, tag, git, file/directory, URL은 `npm-package-arg`로 분류하고 미지원 상태를 남긴다. 네트워크 조회로 추정하지 않는다.
- Node 버전, semver·npm-package-arg 버전과 파일 해시, 설치된 전이 의존성의 해시를 manifest에 기록한다.

공식 근거: [npm node-semver](https://github.com/npm/node-semver), [npm package spec](https://docs.npmjs.com/cli/v11/using-npm/package-spec/), [npm-package-arg](https://github.com/npm/npm-package-arg), [deps.dev BigQuery 스키마](https://docs.deps.dev/bigquery/v1/).

## 결과와 08 소비 계약

| Parquet 그룹 | 행 단위 / 주요 필드 |
| --- | --- |
| `declaration_outcomes` | source 버전·kind·원본 배열 index별 한 행. `declared_name`, `requirement`, `normalized_range`, `status`, target ID·버전 |
| `source_outcomes` | 모든 eligible `(source_package_id, source_version)`별 한 행. 입력 존재·NULL 목록·배포일 NULL·처리 오류·선언/해석 수·제외 peer/optional 수 |
| `edges` | `(snapshot_at, source_package_id, source_version, target_package_id, target_version)`별 한 행. `dependency_kinds`, 원본 선언 수 |
| `target_quality` | 실제 조회한 target 후보 중 유효하지 않은 semver 또는 prerelease. 조회하지 않은 패키지 전체의 semver 품질 조사 결과는 아님 |

모든 최종 그룹에 `snapshot_at` 날짜, 정확한 `snapshot_timestamp` UTC, run ID, Bronze·Curated run ID, input SHA, policy SHA가 포함된다. 빈 그룹도 타입이 있는 Parquet를 기록한다. Spark shard는 최대 250,000행으로 제한한다.

선언 상태는 `RESOLVED`, `INVALID_PACKAGE_NAME`, `INVALID_SPEC`, `UNSUPPORTED_ALIAS/TAG/GIT/FILE/URL`, `NO_ELIGIBLE_TARGET`, `NO_SATISFYING_VERSION`, `UNMAPPED_TARGET_PACKAGE`다.

source 상태는 `MISSING_REQUIREMENTS`, `NULL_DEPENDENCY_LIST`, `DEPENDENCY_EXTRACTION_ERROR`, `DEPENDENCY_EXTRACTION_UNKNOWN`, `OBSERVED_NO_DEPENDENCIES`, `RESOLVED`, `PARTIAL`, `UNRESOLVED`다. 실제 배열의 NULL 원소는 INVALID 상태인 선언으로 남는다.

`DependencyError=true`인 빈 배열은 정상 무의존성으로 처리하지 않는다. 현재 raw projection에 `DependenciesProcessed`가 없으므로 upstream 처리가 완료됐는지는 확인할 수 없다. `DependencyError=false`이고 관측 배열이 비어 있으면 `OBSERVED_NO_DEPENDENCIES`로 기록하지만 upstream 전체의 완전성을 증명하지 않는다. 따라서 manifest에 `dependencies_processed_available=false`, `upstream_source_processing_verified=false`를 유지한다.

`COMPLETE`와 `ready_for_dependents=true`는 **선택 정책 아래 관측된 선언 전체가 해석되었다는 뜻**이다. 실제 설치 그래프, upstream 전체 수집 완료, PostgreSQL 적재 완료를 뜻하지 않는다. `PARTIAL`은 로컬 결과와 사유만 보존하고 게시를 차단한다. 08은 PARTIAL을 정상 count로 사용하거나 누락 관계를 0으로 바꾸면 안 된다. 정상 계산에서도 metric 범위를 관측 선언 기반 관계로 명시해야 한다.

## 실행 환경

신규 패키지 설치 없이 확인한 로컬 환경을 재사용한다.

- Python: 기존 `.venv-bq`, DuckDB 1.5.5 및 boto3
- Node 24.18.0, npm 번들 semver 7.8.1 및 npm-package-arg 13.0.2. 다른 설치 경로는 CLI 인수로 지정 가능
- Spark 3.5.7 컨테이너의 고정 image digest는 `runtime.py`에 있다. `--pull never`, CPU 2개, 컨테이너 6GiB, driver 4GiB, 네트워크 차단이 기본이다.
- Python bridge DuckDB는 기본 2GB, Node heap은 768MiB다. 각 단계는 순차 실행된다. 하나의 target 패키지의 후보는 Node 메모리에 유지되므로 매우 큰 패키지에서 메모리/요청 timeout 실패 가능성이 있다. 실제 전체 계산은 CPU 2개, Spark 컨테이너 6GiB, shuffle 32에서 약 7시간 13분이 걸렸고, prepare 약 104분·bridge 약 80분을 측정했다. 이 측정은 실행 환경에 종속된다.
- Spark에는 07·snapshot 코드 폴더와 선택 입력을 읽기 전용 mount하고 해당 실행 폴더만 쓰기 가능하게 둔다. 기존 worktree의 `.env`와 데이터는 복사하지 않는다.

확정 정책은 이미 `data/requirements-resolution/policy.json`에 저장했다. 다음은 해당 정책의 생성 API 참고이며 전체 계산을 실행하는 코드는 아니다.

```python
from pathlib import Path
from pipeline.requirements_resolution.policy import make_policy, canonical_bytes

policy = make_policy(
    kinds=["dependencies"],
    unknown_published_at="exclude",
    unresolved="partial",
    decision_reference="docs/worklogs/S15P21A506-283/03-policy-decision.md: user decision 2026-09-09",
)
Path("data/requirements-resolution/policy.json").write_bytes(canonical_bytes(policy))
```

PowerShell 실행 예시(위 정책 파일 생성 후, 07 worktree에서 실행):

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$taskPython = 'C:\Users\SSAFY\workspace\S15P21A506\.venv-bq\Scripts\python.exe'
$taskArgs = @(
  '-m', 'pipeline.requirements_resolution.build',
  '--snapshot', '2026-08-31',
  '--curated-run-id', 'curated-20260907-v2',
  '--curated-outputs', 'C:\Users\SSAFY\workspace\S15P21A506\data\curated\curated-20260907-v2-oxudhdl5\outputs',
  '--versions-dir', 'C:\Users\SSAFY\workspace\S15P21A506\data\raw\versions_full\snapshot=2026-08-31',
  '--requirements-dir', 'C:\Users\SSAFY\workspace\S15P21A506\data\raw\requirements\snapshot=2026-08-31',
  '--run-id', 'requirements-20260831-v1',
  '--work-dir', 'data/requirements-resolution/runs',
  '--policy-file', 'data/requirements-resolution/policy.json',
  '--minio-env', 'C:\Users\SSAFY\workspace\S15P21A506\pipeline\minio\.env',
  '--threads', '2', '--shuffle-partitions', '32'
)
& $taskPython @taskArgs
```

`--verify-only`는 완료 run을 재계산 없이 검증한다. 동일 run ID에 다른 입력·정책·코드·런타임을 덮어쓰지 않는다. 실패 attempt는 남기고 새 attempt로 다시 시작한다. manifest 작성 후 marker 작성 전 중단은 기존 결과를 전부 재검증한 후 marker를 복구한다. 다른 쓰기 작업이 가진 lock은 자동으로 지우지 않는다.

`--publish`를 명시한 경우에만 `pickage-curated/depsdev/v1/requirements-resolution/snapshot=<S>/run_id=<R>/`에 게시한다. 기존 완료 결과도 재계산 없이 게시할 수 있다. 독립 writer lock과 불변 객체, SHA 검증, marker-last를 사용하며 기존 package/version·04·05 current 포인터와 DB는 갱신하지 않는다. 원격 manifest에는 로컬 절대경로를 제외하고 계보·정책·결과 파일 해시를 전달한다. `--verify-only`와 `--publish`는 동시 지정할 수 없다.

## 검증 방법과 실제 증거

호스트 단위 테스트:

```powershell
& $taskPython -m unittest pipeline.requirements_resolution.test_input pipeline.requirements_resolution.test_bridge pipeline.requirements_resolution.test_build -v
```

실제 Spark·Node·로컬 lifecycle 및 중단 복구 검증:

```powershell
& $taskPython -m pipeline.requirements_resolution.test_integration --work-dir data/requirements-resolution/verification
```

통합 검증은 합성 Parquet와 메모리 내 S3 대역만 사용한다. 실제 MinIO 쓰기 없이 게시 프로토콜을 검사한다. 실행 후 임시 입력을 제거하고 로그·결과·검증 요약은 별도 07 경로에 남긴다.

`test_transform.py`는 PySpark가 있는 고정 Spark 컨테이너에서 실행한다. 호스트 전체 discovery에 포함하거나 PySpark 부재를 skip으로 성공 처리하지 않는다. 실제 실행 명령·행 수·해시·미실행 항목은 [작업 기록](../../docs/worklogs/S15P21A506-283/02-progress-results.md)에 있다.
