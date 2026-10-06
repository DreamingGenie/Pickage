# 07 실제 전체 데이터 실행

최신 상태: 2026-09-10 재부팅 후 Spark 계산 결과와 산출물을 확인했다. 계산 결과는 2026-09-09 21:43:19 KST에 저장됐고 PARTIAL이다. 2,520개 Parquet footer 행 수 대조 후 입력 전체 SHA/원격 승인 기록 재검증도 통과했다. 전체 행 검증을 독립 프로세스로 실행했으며, 최신 완료/실패 상태는 [08-verification-result.md](08-verification-result.md)에 자동 기록된다. 초기 실행 증거 누락 때문에 표준 `_SUCCESS`는 생성하지 않는다. 상세 실행 범위는 [07-final-verification.md](07-final-verification.md), 계산 결과는 [06-computation-results.md](06-computation-results.md)를 참고한다. 아래 실행 중 상태는 당시의 이력이다.

2026-09-09 사용자 “진행해” 요청에 따라 결과 검토 대기를 마치고 시작한다.

## 확정 범위와 입력

- 전용 worktree: `C:/Users/SSAFY/workspace/S15P21A506-283-requirements-snapshot`.
- run ID: `requirements-20260831-v1`.
- snapshot: `2026-08-31`, Curated `curated-20260907-v2`, 연결된 Bronze `bronze-20260907-v1`.
- 정책: 일반 dependencies, source/target 배포일 NULL 제외, 미해석 PARTIAL 보존.
- policy SHA: `721c9d968f75429497b5e30b86ba0137998ea6a6ab1766bfb274d5661da52ef8`.
- 출력: `data/requirements-resolution/runs/requirements-20260831-v1/`. 기존 입력은 읽기 전용, 04/05 코드·index·산출물과 DB는 변경하지 않는다.
- 처음 실행에는 `--publish`를 지정하지 않는다. 결과 품질을 검증하고 PARTIAL이면 로컬 결과를 보존한다.

## 실행 계획

1. 자원 여유 및 고정 정책 확인, 승인 입력 전체 재검증.
2. CPU 2개, Spark 컨테이너 6GiB·driver 4GiB, shuffle 32로 전체 prepare.
3. 고유 선언을 Node/npm으로 해석하고 전체 Spark finalize.
4. 입력·산출물·정책·코드·런타임 불변 검증과 완료 기록.
5. 실제 포함/제외·선언·관계·미해석 사유·처리 시간 및 사례를 보고한다.

시작 시 호스트 가용 메모리는 약 29.1GiB였다. 실행 중 다른 작업과 시스템 자원을 공유하므로 제한을 유지하며 상태를 확인한다.

## 실제 결과

전체 계산은 완료됐고 `finalize/result.json`과 4종 Parquet 산출물이 생성됐다. 결과는 PARTIAL이다. 다만 host 제어 프로세스가 중간에 종료돼 표준 `run_manifest.json`과 `_SUCCESS`는 생성되지 않았다. 결과·검증 제한은 [06 계산 결과](06-computation-results.md)와 [07 최종 검증](07-final-verification.md)에 기록한다.

- 14:29 KST 시작. 실행 로그: `data/requirements-resolution/execution-logs/full-20260909T142956.log`.
- attempt: `20260909T052957543914Z`. 승인 입력 재검증을 마치고 Spark prepare를 시작했다.
- 실행 직후 가용 메모리 28.31GiB, 디스크 여유 1,319.9GiB. CPU 제한 2개와 메모리 제한 6GiB 유지.

- 15:08 KST 중간 체크포인트: `prepare/outputs/candidates`의 commit 임시 디렉터리가 제거됐음을 확인하고, 192개 Parquet footer를 읽어 후보 47,172,949행을 확인했다. Curated version 54,188,349행과의 차이는 7,015,400행이다. NULL/미래 배포 제외 수의 구분은 아직 단계 report가 나오지 않아 확정하지 않았다. 이것은 후보 단계 결과이며 전체 관계 계산 완료가 아니다.
- 15:40 KST source 192개 파일 저장을 마치고 declarations 저장으로 진행했다. 실행 중 cgroup `memory.peak`는 5,493,460,992bytes(약 5.12GiB), OOM/OOM-kill 이벤트는 0이었다(15:13 측정).
- 완료 후 검증 도구 `verify_full_run.py`를 준비했다. 상태 집계와 최대 2개 사례를 같은 읽기에 얻어 희귀 상태별 전체 재검색을 피한다. 기존 소규모 산출물로 실행 가능한 검사는 위반 0을 확인했으나, 삭제된 임시 입력에 대한 모집단/FK 검사는 생략된 `VERIFIED_WITH_GAPS`이다. 실제 전체 결과 검증은 별도로 실행한다.
- 16:14 KST prepare 성공을 `prepare/result.json`으로 확인하고 host bridge 단계로 진입했다. source/candidate 각각 **47,172,949행**, 일반 선언 **289,214,123행**이다. source 192개 파일, declarations 1,184개 파일(12,606,789,396bytes)을 저장했다.
- prepare에서 NULL 배포일 제외 **7,015,400개**, 제외된 peer 선언 **46,998,761건**, optional 선언 **1,957,230건**을 확인했다. 전체 Curated version과 후보 차이가 NULL 제외 수와 같으므로 미래 배포 제외는 0으로 계산되며, 최종 검증에서 입력 날짜 조건을 직접 다시 확인한다. 제외 kind 수는 이번에 포함한 source 버전 기준이다.
- 16:09 cgroup 측정: 최대 메모리 **5,589,700,608bytes(약 5.21GiB)**, memory.events의 max/oom/oom_kill 모두 0. prepare는 약 104분이 소요됐다(14:30 시작~16:14 완료 관측).
- 16:35 KST bridge 실행 중. `mappings.jsonl` 열린 파일 핸들에서 길이 1,000,584,923bytes를 관측했다. Python 작업 프로세스 약 2.20GB, Node 약 212MB이며 아직 bridge/finalize의 완료 결과는 아니다. Windows 디렉터리 조회의 열린 파일 크기/수정 시각이 갱신되지 않는 경우가 있어 실제 핸들 길이와 마지막 완결 행으로 진행을 확인한다.
- bridge 지연 구간을 prepare Parquet에서 읽기 전용으로 확인했다. `@octopusdeploy/design-system-icons` 후보 12,028개, `@octopusdeploy/design-system-tokens` 후보 29,390개(조회 0.953초). `@octopusdeploy/type-utils`는 후보 **33,966개**, 선언과 고유 requirement가 각각 **33,908개**(조회 8.891초)였다. 모든 유효 조건에 후보 전체를 대조하는 현재 npm maxSatisfying 방식의 비용이 큰 실제 입력 사례다. 코드 변경 없이 본 계산을 계속하며, 실제 후보 대조 횟수를 계측한 결과는 아니다.
- 17:34 KST bridge 완료, 17:34:46 Spark finalize 초기화를 확인했다. `mappings.jsonl` 최종 크기는 **2,488,056,387bytes**이며 Node stderr는 0bytes다. bridge는 약 80분이었다(16:14~17:34).
- bridge 연결이 닫힌 후 `bridge.duckdb`를 read-only로 열어 **고유 조건 11,051,014개**를 확인했다. RESOLVED **10,599,975개**, 미해석 **451,039개**다. 이것은 중복 제거된 조건 수이며, 전체 선언 289,214,123건에 가중된 최종 상태 수는 finalize에서 별도로 계산한다.
- 고유 조건별 미해석: NO_ELIGIBLE_TARGET 171,611 / NO_SATISFYING_VERSION 112,701 / INVALID_SPEC 42,406 / UNSUPPORTED_FILE 36,396 / UNSUPPORTED_GIT 34,555 / UNSUPPORTED_TAG 27,144 / UNSUPPORTED_ALIAS 19,362 / UNSUPPORTED_URL 5,281 / INVALID_PACKAGE_NAME 1,583. 조회된 후보 중 INVALID_TARGET_SEMVER 79건도 별도 quality에 보존됐다. NO_ELIGIBLE_TARGET 중 Curated package 자체가 없는 경우에는 finalize에서 UNMAPPED_TARGET_PACKAGE로 구분한다.
- 전체 계산은 finalize까지 완료됐다. 재부팅 후 footer 행 수 대조와 입력 재검증은 통과했으며, 별도 DuckDB 전수 관계 검증은 메모리 한도로 중단됐다. 이는 데이터 오류 발견이 아니며, 전체 검증 완료로 표시하지 않는다.

## 사용자 요청에 따른 추적 중단과 재확인

- 2026-09-09 사용자는 토큰 절약을 위해 실시간 추적을 멈추고 나중에 결과만 확인하도록 요청했다. 반복 polling/대기를 중단하며, 실행 중인 계산 프로세스는 종료하지 않는다. 자동 재확인이나 예약 작업은 만들지 않는다.
- 추적 중단 당시 host Python PID 25304와 finalize 컨테이너 `pickage-requirements-e78ce5e53acc`가 실행 중이었다. 실행 세션은 42241이며, finalize는 17:34:46 KST에 초기화됐다. 이후 재부팅 후 `finalize/result.json` 생성으로 계산 완료를 확인했다.
- 후속 확인은 먼저 run root의 `run_manifest.json`과 `_SUCCESS`, attempt의 `error.json`, `finalize/result.json`, `finalize/spark-driver.log`를 읽는다. 실행 중이면 불필요하게 재실행하지 않는다. 실패 시 해당 attempt와 로그를 보존한다.
- 정상 종료했다면 `verify_full_run.py`로 승인 정책과 전체 산출물을 한 번 검증하고, 실제 포함/제외·선언·관계·미해석 사유·처리 시간 및 사례를 정리한다. PARTIAL은 로컬 보존하고 COMPLETE로 게시하지 않는다. 08 계산/DB 적재는 별도 작업이다.
- 후속 검증 명령: `python docs/worklogs/S15P21A506-283/verify_full_run.py --manifest data/requirements-resolution/runs/requirements-20260831-v1/run_manifest.json --output data/requirements-resolution/runs/requirements-20260831-v1/verification/report.json`. Python은 기존 main worktree의 `.venv-bq/Scripts/python.exe`를 재사용하고, 작업 위치는 반드시 07 전용 worktree로 유지한다. `PYTHONPATH`는 이 worktree, `PYTHONDONTWRITEBYTECODE=1`로 설정한다. 실제 검증에는 `--allow-test-policy`를 사용하지 않는다.

### 19:14 KST 단발 상태 확인

- 사용자의 직접 확인 방법 질문에 한 번만 조회했다. finalize 컨테이너는 running, OOMKilled=false, CPU 약 31.7%, 메모리 약 3.45/6GiB였다. scratch 파일이 19:14:09까지 수정돼 실제 계산 진행을 확인했다. `finalize/result.json`, run manifest, `_SUCCESS`, attempt error 기록은 아직 없다.
- **중요 정정:** host Python PID 25304와 그 run을 실행한 Python/docker CLI 프로세스는 더 이상 없고, 실행 세션 42241도 Unknown process id를 반환한다. 종료 원인은 이번 조회만으로 확정하지 않았다. Docker의 Spark 계산은 계속되지만, 이를 기다리던 host 제어 프로세스가 사라져 계산 후 입력 재검증·산출물 검증·run manifest/`_SUCCESS` 생성은 자동으로 이어지지 않는다.
- 따라서 후속 확인에서 `finalize/result.json`이 있더라도 이를 전체 검증 완료로 표시하지 않는다. 성공한 계산 산출물을 보존하고, 기존 입력/정책/실행 provenance를 확인한 뒤 host 후속 검증과 완료 기록을 복구해야 한다. 위 `verify_full_run.py` 명령은 검증된 run manifest가 복구된 다음에 실행할 수 있다. 원래 실행의 초기 코드/런타임 증거가 충분한지도 확인하고, 확인되지 않은 보장을 복구 manifest에 단정해서 적지 않는다.
- 사용자 요청대로 반복 추적은 재개하지 않는다.
