# 실제 진행, 이슈와 검증 결과

작성일: 2026-09-09. 구현·로컬 검증과 실제 전체 계산 이력을 구분해 보존한다. 전체 계산은 완료됐고 결과 게시와 08 적재는 수행하지 않았다.

현재 결과를 표로 확인하려면 [결과 보기](C:/Users/SSAFY/workspace/S15P21A506-283-requirements-snapshot/docs/worklogs/S15P21A506-283/04-results-preview.md)를 먼저 읽는다.

이 문서는 구현·fixture 검증 이력을 보존한다. 이후 사용자가 전체 계산 진행을 요청했으며, 실제 실행 상태와 결과는 [05 전체 실행 기록](C:/Users/SSAFY/workspace/S15P21A506-283-requirements-snapshot/docs/worklogs/S15P21A506-283/05-full-run.md)에 별도로 기록한다.

## 실제 진행과 변경 파일

- 독립 worktree `C:/Users/SSAFY/workspace/S15P21A506-283-requirements-snapshot`, 브랜치 `feat/S15P21A506-283-requirements-snapshot`에서 구현했다. 기존 04/05 코드·Git index·브랜치는 변경하지 않았다.
- `pipeline/requirements_resolution/policy.py`: 필수 선택·결정 참조와 canonical 정책 SHA. 일반 dependencies만 허용, peer/optional 제외 이유 기록.
- `input.py`: 승인 Curated·Bronze run 계보, 로컬 전체 파일·SHA·행 수·스키마·정확한 raw SnapshotAt 검증과 재검증.
- `semver_worker.cjs`, `bridge.py`: 실제 npm semver와 npm-package-arg, 패키지별 후보 상태 및 고유 요청의 배치 처리. npm 모듈 및 설치된 전이 의존성 해시 기록.
- `transform.py`, `spark_job.py`, `runtime.py`: 모든 source 버전의 선언, 후보 및 source/declaration/edge/quality Parquet. 읽기 전용 입력, Spark 자원 제한, 07·snapshot 코드만 mount.
- `build.py`: 고정 입력·정책·코드·런타임의 실행/재검증, 로컬·원격 marker 중단 복구, 07 전용 불변 게시와 품질 gate.
- `test_input.py`, `test_bridge.py`, `test_build.py`, `test_transform.py`, `test_integration.py`, `test_support.py`: 실제 입력 계약 fixture, 실제 npm 및 Spark 검증, 게시 프로토콜의 메모리 내 S3 검증.
- 실행 문서, 07 티켓 현황, 본 worklog와 worktree 경계를 갱신했다. 공통 파이프라인·DDL 변경과 의존성 설치는 없다.

## 사용자 정책 기록

| 질문 | 실제 답변 / 상태 |
| --- | --- |
| 의존성 종류 | “일반 dependencies만 계산 (권장)” 선택을 반영 |
| 배포일 NULL 버전 참여 | 사용자 확정: 07 source/target에서 제외 |
| 미해석 발생 처리 | 사용자 확정: `partial`로 결과·품질 사유 보존 |

최신 상태: 확정 정책을 적용한 실제 전체 계산이 완료됐다. 결과는 PARTIAL이며 원격 게시와 08 적재는 수행하지 않았다. 아래의 기존 `include`·`partial` fixture와 이전 통합 검증 수치는 당시 합성/검증 정책의 증거이며 실제 전체 결과로 간주하지 않는다.

과거 테스트의 `include`·`partial`은 합성 입력용 명시 선택이다. 이 값을 실제 데이터에 적용하지 않았다. 최신 사용자 선택인 `exclude`·`partial`은 [정책 결정 기록](C:/Users/SSAFY/workspace/S15P21A506-283-requirements-snapshot/docs/worklogs/S15P21A506-283/03-policy-decision.md)과 `data/requirements-resolution/policy.json`에 저장하고 해시를 검증했다. 전체 계산은 이후 실행됐으며, 결과 수치와 제한은 [06 계산 결과](06-computation-results.md)에 기록했다.

## 실제 전체 입력 검증

아래는 표본이 아니라 승인된 consumed 파일 전체의 바이트·SHA·Parquet 스키마·footer 행 수, raw 전체 SnapshotAt 일치 검증 결과다. 서비스 package/version 외 Curated 보조 산출물은 계산 입력으로 소비하지 않는다.

| 입력 | 파일 수 | 행 수 |
| --- | ---: | ---: |
| Curated package | 4 | 11,080,940 |
| Curated version | 20 | 54,188,349 |
| Bronze versions_full 대응 로컬 원본 | 362 | 78,559,731 |
| Bronze requirements 대응 로컬 원본 | 790 | 78,559,731 |

- 실제 측정 시간: 68.843초. 원격의 작은 승인 manifest를 조회하고 로컬 파일을 읽었으며 쓰기 요청은 하지 않았다.
- 정확한 snapshot timestamp: `2026-08-31T21:01:10.517131Z`.
- Curated run: `curated-20260907-v2`, manifest SHA `a537f84bae78c9209e56deddb24d94cdef606d06e0e563f93ddb67e3843e71b3`.
- Bronze run: `bronze-20260907-v1`.
- requirements run manifest SHA: `0d2b47a2829d1b46aebfa1616a21b9ea24ed5b2bf3cbc442d40f6163a47d4bc0`.
- versions_full run manifest SHA: `3157a73434228145059cb92b9ba03972f3a053eca11d463b8e91f66f80711984`.
- 로컬 input manifest SHA: `d673d51c73b9245ea897d5b910dc7a90c8e905930a7d05040d07ae9d3e9418e5`. 이 해시는 로컬 선택 경로를 포함한 receipt 해시다.
- 검증 결과: `data/requirements-resolution/preflight-20260909/input-manifest.json`.

이 검증은 행 관계의 전체 resolution 성공·edge 건수·처리 성능을 의미하지 않는다. 본 계산에서 다시 입력을 검증한다.

## 이슈, 해결과 검증 증거

| 발견한 문제 | 해결 | 실행 근거 |
| --- | --- | --- |
| 기본 Python의 DuckDB/boto3 부재 | 기존 `.venv-bq`를 읽기 전용 재사용, 추가 설치 없음 | 호스트 테스트 및 실제 파일 사전 검증 |
| 로컬 raw 요약에 개별 파일 목록 없음, Curated 로컬 manifest 없음 | 원격 승인 run의 정확한 파일 목록·SHA와 로컬 파일을 대조 | 실제 1,176개 consumed 파일 검증 |
| `is_release`가 Curated version에 없음 | 동일 원천 raw와 릴리스·배포일 provenance를 검사 | Spark duplicate·provenance mismatch fixture |
| NULL 배열 원소가 누락될 위험 | 원본 배열 index를 갖는 explode로 실제 NULL 원소를 미해석 선언으로 보존 | Spark fixture의 INVALID 선언 1행 |
| 빈 배열인데 `dependency_error=true/NULL` | 오류/미확인 source 상태로 보존, 단순 0 의존성으로 취급하지 않음 | Spark의 누락·NULL 목록·처리 오류·미확인 상태 검사 |
| 현재 raw에 `DependenciesProcessed` 없음 | upstream 완전성 미검증을 manifest에 명시 | deps.dev 공식 스키마 확인, 결과 metadata 검사 |
| npm prerelease `1.2.3-rev.01` fixture 오류 | SemVer상 invalid로 교정. 실제 semver 결과 사용 | Node boundary fixture |
| 불완전한 결과 그룹도 완료될 수 있던 lifecycle 초안 | 4개 정확한 그룹·파일·행 수·상태 집계·ready 정합성 검증 | 잘못된 그룹/상태/행 수·빈 그룹 회귀 검사 |
| manifest 기록 후 marker 전 중단 시 재시도 불가 | 기존 입력·정책·코드·런타임·파일 재검증 후 marker 복구 | 로컬/메모리 S3 중단 복구 테스트 |
| 원격 경로 제거가 결과 파일 상대경로도 삭제 | 알려진 로컬 필드만 제거, `files[].path` 및 `final_output=data` 유지 | 원격 receipt 파일별 객체·SHA 대조 |
| 기존 run 경로 junction 우회 | run/output과 부모의 링크 검사 후 resolve·포함 관계 검사 | run-root junction 탐지 모의 테스트, traversal 거부 |
| Windows MAX_PATH로 Spark 결과 재조회 실패 | Python/DuckDB 파일 I/O에 Windows extended path 적용 | 긴 파일 경로의 실제 해시·footer 검증 |

호스트 검사: 입력 9개, bridge 7개, lifecycle 12개가 통과했다. lifecycle의 Spark 호출은 대역으로 격리하고, bridge는 설치된 실제 Node/npm을 사용한다. 실제 S3 조건부 쓰기 동작을 모방한 메모리 대역은 기존 객체 덮어쓰기를 거부하며 파일 stream을 읽는다.

실제 Spark 검사: `test_transform.py` 3개가 155.095초에 통과했다. 9개 버전 fixture에서 미래 배포 제외 후 8개 source, 중복 선언 2개를 같은 edge로 합치고 최종 2개 edge, 해석 선언 3개·미해석 1개를 검증했다. 배포일 NULL 제외 정책은 source와 target 모두 7개로 줄어드는 것을 검사했다. fixture의 수치를 실제 데이터 결과로 사용하지 않는다. 로그: `data/requirements-resolution/verification/spark-tests-01/tests.log`.

첫 Spark·Node 연결 smoke는 source/선언/후보 각각 1개와 최종 edge 1개로 통과했다. 로그·요약: `data/requirements-resolution/verification/smoke-b86b81cd/verification.json`. 이후 전체 lifecycle 통합 검증에서 발견한 긴 경로 문제는 `integration-f43b1007` 실패 attempt에 남아 있다. 최종 재검증 결과는 아래에 추가한다.

최종 실제 통합 검증 `integration-dbf68cf2`: **PASSED**. 실제 Spark prepare → 실제 Node bridge → 실제 Spark finalize → 결과·입력 재검증 → 완료 run 재검증 → 로컬 manifest-only 복구 → 메모리 S3 게시 → 원격 manifest-only 복구가 모두 통과했다. 선언/source/edge 각각 1행, target quality 0행, peer 제외 개수 1을 실제 Parquet에서 확인했다. 완료 manifest 바이트는 재실행 전후 동일하며 재계산하지 않았다. 합성 입력과 메모리 S3는 테스트 후 제거했고, 로그·Parquet·요약은 `data/requirements-resolution/verification/integration-dbf68cf2/verification.json` 및 해당 run의 `attempts/`에 남아 있다. 실제 MinIO로 게시하지 않았다.

독립 검토의 최종 결과: **CLEAR**. 처음 지적한 결과 완전성, marker 복구, run-root junction, 원격 manifest/marker GET 검증, 원격 파일 계보 보존 문제가 해결됐음을 읽기 전용 재검토로 확인했다. 긴 경로 회귀 테스트에서 파일 검증은 성공했으나 기본 임시폴더 정리도 MAX_PATH에 걸려 해당 테스트가 만든 파일을 extended path로 정리하도록 수정했고, lifecycle 12개를 다시 통과했다.

최종 정적 검사: Python 14개 파일 AST 파싱, Node worker 구문 검사, 소유 범위 21개 파일의 trailing whitespace 검사가 통과했다. 신규 파일은 아직 미추적이므로 `git diff --check` 외에 직접 검사했다. 07 worktree의 기존 추적 파일 변경 0개·stage 파일 0개와 정확한 작업 브랜치를 확인했다.

실제 통합 재현 명령(07 worktree):

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
& 'C:\Users\SSAFY\workspace\S15P21A506\.venv-bq\Scripts\python.exe' -m pipeline.requirements_resolution.test_integration --work-dir data/requirements-resolution/verification
```

Spark 경계 테스트는 고정 image로 `/opt/spark/bin/spark-submit --master local[2] --driver-memory 4g /workspace/pipeline/requirements_resolution/test_transform.py`를 실행했다. `--network none --cpus 2 --memory 6g`, `PYTHONPATH=/workspace`, `PYTHONDONTWRITEBYTECODE=1`, `TMPDIR=/run/tmp`, `SPARK_LOCAL_IP=127.0.0.1`, `SPARK_LOCAL_HOSTNAME=localhost`를 지정하고 코드 읽기 전용·검증 출력 `/run` mount를 사용했다. scratch와 warehouse도 `/run`에 두었다.

## 미실행 및 남은 범위

- 실제 전체 54,188,349 Curated 버전의 관계 계산과 품질·미해석 건수 산출: 전체 계산 완료. 결과는 PARTIAL이며 품질·검증 제한은 06·07 문서에 기록했다.
- 실제 전체 입력의 source/target 관계 join·중복 검사는 Spark finalize에서 수행됐고, 전체 실행 시간도 측정했다. 후속 독립 DuckDB 전수 unique-key 검사는 메모리 한도로 중단됐으므로 이를 전체 행 검증 통과로 표시하지 않는다.
- 실제 MinIO에 07 결과 게시: 미실행. 게시 테스트는 메모리 내 S3 대역만 사용.
- 08 dependents_count 계산, PostgreSQL 적재, 서버 실행: 범위 밖, 미실행.
- 이 문서 작성 당시 commit/push는 미실행이었다. 이후 로컬 커밋 준비·검증 결과는 [09 push 전 기록](09-pre-push.md)에 보존한다. push와 MR 생성은 수행하지 않는다.

Spark 컨테이너 테스트 중 PySpark의 socket `ResourceWarning`이 출력됐지만 테스트 종료 코드는 0이었다. 실제 full run은 약 7시간 13분, 산출물 5,719,755,195bytes로 측정했다. 큰 target 패키지의 Node 메모리 사례와 독립 전수 검증은 별도 제한으로 남긴다.
