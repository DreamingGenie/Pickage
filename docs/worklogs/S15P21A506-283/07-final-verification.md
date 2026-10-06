# 07 최종 검증과 완료 기록 복구

2026-09-10 사용자 진행 승인에 따라 수행한다. 계산 산출물은 변경하지 않고 PARTIAL을 유지한다.

## 변경 범위와 계획

- 범위: 이 worktree의 검증 도구와 작업 기록, 이 run의 새 검증 기록. 원본, 04/05, 공통 모듈, MinIO 게시, 08/DB 적재는 변경하지 않는다.
- 입력 manifest와 승인된 원격 manifest를 비교하고 원본 파일 해시를 재검증한다.
- 최종 산출물 파일 해시를 기록하고, 행별 source/target 연결·모집단·중복·상태·정책·lineage를 검사한다.
- 실행 당시의 코드/런타임 증거와 현재 관측을 구분한다. 초기 hash가 사라진 경우 현재 hash를 초기 hash로 가장하지 않는다. 표준 완료 계약을 만족할 증거가 없으면 `_SUCCESS`를 임의 생성하지 않고, 별도 복구 검증 기록에 보장 범위를 명시한다.
- 검증 후 문서에 실제 결과와 남은 제약을 반영한다. 재계산이나 반복 진행 알림은 하지 않는다.

## 실제 작업과 결과

- 표준 `run_manifest.json` / `_SUCCESS`는 생성하지 않는다. 초기 코드 hash와 런타임 identity가 이 attempt에 저장되지 않아 원래의 완료 계약을 입증할 수 없다. 별도 recovery 기록으로 현재 검증 결과를 보존한다.
- 전체 실행 이전 소규모 integration manifest와 현재 production 코드 SHA는 `20a8d53cb1e24ffb3554ac76c755247438e2bec76d6a7e43496a28c61235682c`로 같다. Node/npm metadata도 같다. 이는 보강 증거이며 전체 실행 당시의 직접 증명은 아니다.
- production 모듈을 변경하지 않고 `recover_full_run.py`를 추가했다. 승인 입력/원격 manifest, stage invocation, 전체 출력 SHA와 행별 검사를 수행하고, 마지막에 입력/출력/코드/runtime 안정성을 다시 확인한다. 원본 계산 재실행과 외부 쓰기는 없다.
- `verify_full_run.py`에 명시적 `RECOVERY_CANDIDATE` 검증 모드를 추가했다. 일반 모드는 marker/hash/PASSED 계약을 그대로 요구하며, 후보 모드는 provenance gap을 보고서에 유지한다. 선언 중복 및 해석 선언과 edge의 정확한 관계/건수 일치 검사도 추가했다.
- 소규모 fixture: 일반 모드가 미봉인 후보를 거부함을 확인했다. 후보 모드는 실행 가능한 데이터 검사 위반 0이지만 provenance/삭제된 fixture 입력의 검증 공백을 유지했다. 저장된 invocation 일치와 입력 mount 밖 경로 거부도 통과했다. 실제 전체 검증을 대신하는 결과는 아니다.
- 2026-09-10 08:50 KST 전체 검증을 독립 Python 프로세스(PID 311192)로 시작했다. 로그: `data/requirements-resolution/execution-logs/recovery-20260910T085046.log`. 상태와 실패 기록은 run의 `verification/recovery-20260909T235047Z/`에 보존한다. 실제 완료 결과는 실행 후 아래에 추가한다.
- 초기 검증은 전체 행별 검사 전에 중단했다. 검토에서 최종 기록이 검사한 candidate bytes와 정확히 연결되도록 보강이 필요함을 확인했다. 후보/보고서 생성 직후 hash 캡처·최종 재대조, 느린 input/output 재검증 뒤 code/runtime/evidence 비교, 빈 gap 거부, stage report의 identity/count 직접 비교를 추가했다. 정상 stage report와 변조된 input SHA/count/빈 gap 거부 검사는 통과했다. 계산 산출물은 변경하지 않았다.
- 08:54 KST 수정된 검증을 독립 프로세스(PID 321124)로 시작했다. 로그는 `data/requirements-resolution/execution-logs/recovery-20260910T085450.log`이다. 첫 검증의 기록도 그대로 보존한다.
- 수정 후 별도 검토에서 blocker 해소를 확인했다. 승인 입력 전체 로컬 SHA와 원격 manifest 재검증은 통과했다. 전체 행 검사는 아직 실행 중이며 완료로 표시하지 않는다.
- 사용자 요청대로 실시간 agent 추적을 계속하지 않는다. 검증기는 완료/실패 JSON을 자체 저장한다. 별도 요약 작성 프로세스(PID 307496)는 운영체제의 단일 프로세스 종료 대기로 기다린 뒤 [08-verification-result.md](08-verification-result.md)를 완료/실패 결과로 자동 갱신한다. Codex 모델 호출, 예약 작업, 반복 에이전트 polling, 재계산은 없다. PC가 다시 종료되면 이 로컬 프로세스들도 중단되므로 자동 재부팅 복구를 보장하지 않는다.
- 기존 결과 전체에 대한 semver 해석을 다시 실행한 검사는 아니다. 현재 입력/출력의 내용과 관계를 검사하며, 초기 실행 증거 누락은 결과 기록에도 유지한다.

### 실제 종료 결과와 08 연계 검토

- 후속 확인에서 검증 종료를 확인했다. `declaration_unique_key`의 전체 GROUP BY 중 DuckDB 2GB 제한에 도달해 `OutOfMemoryException`이 발생했다. 데이터 위반 발견 결과가 아니라 검증 자원 한도 실패이며, 전체 검사 통과를 주장하지 않는다. 오류는 `verification/recovery-20260909T235450Z/failure.json`과 실행 stderr에 남아 있다.
- 원본 계산 결과는 보존됐고 재실행하지 않았다. 요약 작성 프로세스가 `08-verification-result.md`를 실패 상태로 자동 갱신했으며 두 프로세스 모두 종료됐다.
- 로그상 승인 입력/원격 manifest 재검증, 출력 inventory 캡처, source publication flag·건수 산술, 선언 필드, declaration→source FK까지 통과했다. 그 뒤 edge/target/lineage 및 종료 시 불변성 재검증은 완료하지 못했다.
- 사용자 질문에 따라 08 계획과 겹치는 검사를 검토했다. 07 Spark finalize 자체에도 선언 unique·source 누락 방지·eligible target·edge unique와 건수 검사가 있다. 별도 전수 재검증 완료가 08 개발 착수의 필수 조건은 아니다. 08 티켓에 정의된 입력 run/체크섬/coverage 검증, 집계 중 중복 처리, DB staging FK/중복 검증으로 연계할 수 있지만, 현재 자동 연동은 구현되지 않았다. 단순 count 집계가 원래 semver 해석의 정확성이나 누락된 초기 실행 증거를 복원하지는 않는다.
- 현재 PARTIAL/ready=false이며 표준 승인 run 조건을 충족하지 않으므로 자동 DB 게시 대상으로 승격하지 않는다. 검사를 08에 통합하는 방안은 검토 결과이며 이 질문만으로 08 구현이나 게시 정책을 변경하지 않았다.
