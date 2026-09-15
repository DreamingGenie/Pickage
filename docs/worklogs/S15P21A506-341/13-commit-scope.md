# 커밋 파일 분류

사용자가 요청한 범위는 파일 분류까지다. 아래 목록은 다음 커밋의 후보이며, 이번 정리에서는 스테이징·커밋·push를 하지 않았다. 파일을 삭제하거나 실행 중인 서버 구성을 바꾸지 않았다.

현재 후보는 **34개 텍스트 파일**이다. 새 파일도 포함한 목록이며 `git diff --stat`만으로는 새 파일이 표시되지 않는다.

## 이관 코드와 실행 안내 (12개)

- `scripts/service-data-migration/CandidateFlyway.java`
- `scripts/service-data-migration/README.md`
- `scripts/service-data-migration/build_benchmark_sample.py`
- `scripts/service-data-migration/cutover_service.py`
- `scripts/service-data-migration/finish_resumed_restore.py`
- `scripts/service-data-migration/local_dump_client.py`
- `scripts/service-data-migration/prepare_full_dump.py`
- `scripts/service-data-migration/resume_postdata.py`
- `scripts/service-data-migration/server_pilot.py`
- `scripts/service-data-migration/stop_for_ordered_resume.py`
- `scripts/service-data-migration/test_resume_integration.py`
- `scripts/service-data-migration/transfer.py`

## 회귀 테스트 (8개)

- `tests/test_atomic_migration_json.py`
- `tests/test_build_benchmark_sample.py`
- `tests/test_finish_resumed_restore.py`
- `tests/test_local_dump_client.py`
- `tests/test_prepare_full_dump.py`
- `tests/test_resume_postdata.py`
- `tests/test_server_pilot.py`
- `tests/test_service_data_migration.py`

## 작업 기록과 최종 결과 (14개)

- `docs/worklogs/S15P21A506-341/01-transfer-plan.md`
- `docs/worklogs/S15P21A506-341/02-work-log.md`
- `docs/worklogs/S15P21A506-341/03-local-validation.md`
- `docs/worklogs/S15P21A506-341/04-local-dump-access.md`
- `docs/worklogs/S15P21A506-341/05-server-pilot.md`
- `docs/worklogs/S15P21A506-341/06-large-benchmark.md`
- `docs/worklogs/S15P21A506-341/07-full-dump.md`
- `docs/worklogs/S15P21A506-341/08-full-server-restore.md`
- `docs/worklogs/S15P21A506-341/09-fk-performance-analysis.md`
- `docs/worklogs/S15P21A506-341/10-ordered-restore-resume.md`
- `docs/worklogs/S15P21A506-341/11-service-cutover.md`
- `docs/worklogs/S15P21A506-341/12-final-result.md`
- `docs/worklogs/S15P21A506-341/13-commit-scope.md`
- `docs/worklogs/S15P21A506-341/README.md`

## 제외하고 보존하는 파일

| 대상 | 이유와 보관 방식 |
| --- | --- |
| `data/service-data-migration/341/**` | 덤프, CSV, 원시 로그, receipt, 실행 결과 JSON. 기존 `/data/` Git 제외 규칙으로 로컬에 보존 |
| `J15A506T.pem` | 서버 개인키. `.git/info/exclude`로 로컬 제외 |
| `.omx/**`, `tmp-worker.log` | 에이전트 실행 상태와 임시 로그. `.git/info/exclude`로 로컬 제외 |
| `docs/jira/**` | 미추적 로컬 작업 문서는 기존 로컬 제외 규칙 유지. 이미 추적 중인 `분류_운영규칙.md`는 그대로 두고 이번 변경 범위에서 제외 |
| `pipeline/duckdb_ui.py` | 이번 이관과 무관한 변경. 수정/삭제/스테이징하지 않음 |
| 서버 `api-inspect.private.json` | 비밀번호를 포함한 복구 설정. 서버 권한 0600 파일로만 보존하며 다운로드·커밋하지 않음 |

`.git/info/exclude`는 이 체크아웃에만 적용되고 커밋에는 포함되지 않는다. 다른 사람이 받은 clone에 자동 적용되는 규칙이라고 표현하지 않는다. 개인키와 실행 산출물을 다른 경로로 복사했다면 그 경로도 별도로 확인해야 한다.

제외 규칙은 이미 추적 중인 파일을 자동으로 추적 해제하지 않는다. 기존 추적 파일을 삭제하거나 `git rm --cached`로 제거하는 작업은 하지 않았다.

## 이미 커밋된 파일

`LocalFlyway.java`, `test_integration.py`, `run-local-pilot.ps1`, 기존 SQL 및 migration 파일은 관련 기능의 일부지만 이번 정리에서 변경하지 않았다. 이번 후보 목록에 중복해서 넣지 않는다.

## 다음 커밋 전에 사용할 목록

명시적 경로 목록과 파일별 크기/줄 수/SHA는 로컬 `data/service-data-migration/341/commit-preparation-20260915/`의 `paths.txt`, `inventory.json`에 저장했다. 이 목록 자체는 Git에서 제외된다. 이후 새로 수정한 파일이 있다면 목록과 지문을 다시 확인한 뒤 해당 파일만 선택한다.

단위 테스트와 서버 실행 결과는 [최종 결과](12-final-result.md)에 있으며, 이번 문서 정리에서 기능 테스트를 다시 실행했다고 표현하지 않는다.
