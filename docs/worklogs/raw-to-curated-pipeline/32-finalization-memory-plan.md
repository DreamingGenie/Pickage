# 최종 병합 메모리 확대 및 검증 개선 계획

## 요청과 범위 (2026-09-21)
- 사용자가 메모리 한도를 약 8GB로 확대하고 코드 수정 방안을 설명하도록 요청했다.
- 다음 복구 설정을 `C:/pg914r3/next-recovery-settings.json`에 저장했다: 최종 병합/결과 검증 8GB, 2 threads, 완료 분할 재사용. 아직 실행기에 연결하지 않은 PENDING_IMPLEMENTATION 설정이며 재시작하지 않았다.
- 기존 요청·완료 체크포인트·코드 계약은 변경하지 않는다. 현재 실행 상태는 FAILED다.

## 구현 계획
1. 최종 병합/검증 전용 memory_limit 옵션을 연결하고, 새 복구 실행 기록에 유효 설정을 남긴다. 기존 128개 worker 결과는 재사용한다.
2. all_source_summary의 COUNT(DISTINCT) 두 개를 min/max 일관성 검사로 바꾸고, 바로 다음 _weighted_sources 집계와 결합해 같은 source/version 전체 GROUP BY의 반복을 줄인다. NULL birth 무시/NULL error 별도 값 취급은 보존한다.
3. 기존 worker 생성 계약과 새 finalizer 계약을 구분하는 명시적 복구 증명을 추가한다. 기존 해시를 덮어쓰거나 일반 resume의 계약 검사를 해제하지 않는다.
4. 원래 쿼리와 NULL/충돌 결과 동등성을 테스트하고, 저장된 128개 결과 전체로 최종 병합부터 실제 검증한다. 이후 파일 생성·검증·게시 완료를 확인한다.
5. 병합/일관성 검사/품질 집계/출력 검증별 시작·종료·경과시간을 남긴다. 8GB는 DuckDB 한도이며 Python 등 전체 프로세스 메모리 상한이 아니다.

## 현재 검증 경계
- 코드 수정과 8GB 실제 실행은 아직 수행하지 않았다. 8GB만으로 전체 성공한다고 단정하지 않는다.

## 구현 착수
- 사용자 승인 후 최종 병합 전용 복구 ID `finalization-8gb-v3`를 추가한다. 다음 실행의 유효 설정은 8GB / 2 threads / temp 100GB로 고정한다.
- 기존 run_plan과 모든 complete.json의 SHA를 별도 증명에 고정하고, 새 계약에서는 검증/조정 코드 변경만 허용한다. 복구 모드는 미완료 분할을 계산하지 않고 모두 완료되어 있어야 진행한다.
- 테스트는 작은 fixture에서 worker 완료 후 최종화 실패를 주입하고, 이전 생성 계약을 보존한 채 새 finalizer로 재개한다. worker 재계산 함수가 호출되면 테스트가 실패하도록 한다.
- 이전 계획의 미실행 표시는 착수 전 상태이며, 실제 검증 결과는 아래에 누적한다.

## 검증·실행 기록
- 품질/이벤트/SQL 테스트 25개 통과(18.023초), 병렬/파이프라인 회귀 12개 통과(71.581초), 복구 증명·통합 복구 테스트 6개 통과(6.606초).
- 실제 기존 parallel generation과 수정본의 차이는 `production/weighted_quality_sha256`, `code/historical_parallel` 두 항목이다. 원래 worker 계산 코드와 입력 계약은 유지된다.
- 수정본을 `C:/pg914r3/recovery-v3-src`에 고정했다. v1/v2 소스와 기존 계획·완료 분할은 보존했다.
- 로컬 Docker가 꺼져 있었다. 기동 시 `dockerInference` 소켓 접근 오류로 Docker Desktop 자체가 실패했다. 소켓 백업 이동은 OS 접근 오류, 삭제 시도는 자동 승인 정책에 의해 거절되어 실행되지 않았다. 볼륨 삭제·초기화는 수행하지 않았다.
- MinIO 없이 가능한 로컬 최종화/검증을 먼저 실행한다. `local_finalization.py`는 기존 128개 포인터와 plan 해시를 증명에 고정하고, 8GB/2 threads/temp 100GB로 병합·결과 생성을 수행한 뒤 verify_run을 실행한다. 이 보조 실행기는 로컬 실험 디렉터리에 보존했다.
- 2026-09-21 10:15:20 KST 시작, 실제 PID 5876. `launch.json`에 최신 stdout/stderr 경로가 기록된다. 성공 시 `finalization-v3-verified.json`을 남기고 WAITING_MINIO 상태로 끝난다. MinIO 게시 및 DB 적재까지 성공했다는 뜻이 아니다.
- 사용자가 Docker를 정상 기동했다고 알려준 뒤 Docker API 응답을 확인했다. 기존 실험용 `pickage-real914r3-minio`, `pickage-real914-pg`, 원본 재사용 cache용 `pickage-real914r2-minio`만 시작했다. 19000 서버 MinIO 터널도 다시 열었다.
- MinIO에서 원래 요청·앞 5개 checkpoint를 읽어 v3 복구 계획 준비가 통과했다. 로컬 최종화가 끝난 뒤 `recover-v3-start.ps1`로 게시/적재 흐름을 이어갈 준비가 완료됐다.
- 10:20:36 KST 로컬 parallel run COMPLETE. 128개 재사용, 신규 분할 계산 0개. 입력/완료파일 재검증부터 cache·history 출력 생성까지 316.313초.
- 최종 품질 집계 누적 경과: weighted_sources 100.818초, source_statuses 103.153초, declaration_statuses 103.212초, quality_rows 104.065초. 구간 순수 시간과 누적 시간을 혼동하지 않는다.
- 이어서 verify_run으로 입력/128개 영수증/cache의 도출 결과/history 출력 검증을 수행 중이다. 이 시점은 MinIO bundle 게시 완료가 아니다.
- 10:26:06 KST 로컬 최종화와 verify_run 모두 PASSED: 전체 646.053초(약 10분 46초), FULL_SELECTED 128분할 / 1스냅샷. 검증 보고서는 `C:/pg914r3/finalization-v3-verified.json`. `ready_for_load=false`는 이 계산 산출물 자체의 기존 계약이며, 아직 전체 Curated bundle 게시·DB 적재 완료를 의미하지 않는다.
- 검증 재계산 시 최종 품질 집계도 112.539초에 완료했다. OOM 없이 cache 도출 결과 및 grouped history 검증을 통과했다.
- 로컬 검증 성공/프로세스 종료를 확인하는 `continue-after-v3-verification.ps1`가 10:26:06에 후속 `recover-v3-start.ps1`를 시작했다. 실제 PID 36220, RUNNING/앞 5개 완료 결과 검증, stderr 비어 있음을 확인했다.
- 후속 흐름은 기존 출력 재검증 → dependents 게시 → baseline bundle 게시/로컬 Spring DB 적재 → 9/14 처리다. 전체 적재 완료는 아직 미확인이다. 작업 중인 서버 운영 서비스에는 변경하지 않았다.

## 최종 확인 및 커밋 시점 상태
- 2026-09-21 10:48:19 KST 8/31 baseline Curated 6단계 및 로컬 MinIO 게시 COMPLETE. Bundle SHA는 `16a1bcf918733cc1588e59c5957ee078b0cb559a0f06d962185fcf705c812673`이다.
- 후속 Spring 적재는 10:59:21 실패했다. `CuratedBundleReader.validateParquet`에서 별도 DuckDB JDBC의 256MB 한도를 초과했다(242.7MiB/244.1MiB). 이번에 조정한 전처리 8GB 설정과 별개의 제한이다.
- 적재 전 파일 준비/검증 중 실패하여 DB 실행 이력과 package/version/snapshot 적재 건수는 0이었다. 9/14 처리는 시작하지 않았다.
- 이번 커밋은 최종 병합 메모리 개선, 128개 완료 결과의 계약·해시 보존 복구, 상태 출력, 테스트 및 작업 기록을 포함한다. Spring 적재기 메모리 제한 수정은 미해결이며 재실행하지 않았다.
