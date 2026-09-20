# dependents 명세 크기 제한 수정과 기존 입력 복구

## 변경 범위와 계획

- 사용자가 기존 결과를 재사용하여 dependents부터 고치고 재시작하도록 요청했다.
- C:/pg914r3의 앞 5개 완료 checkpoint, 기존 request/생성 해시와 frozen src를 보존한다.
- 실패 원인은 5,036,183바이트 입력 명세를 4MiB 제한 reader가 거부한 것이다.
- JSON reader를 유한한 16MiB로 수정하고 4MiB 초과/16MiB 초과 회귀 검증을 수행한다.
- 별도 recovery-src와 recovery receipt를 만든다. 기존 생성 해시를 새 값으로 고치지 않는다.
- 기존 512개 shard 및 원천 cache의 SHA와 구조를 검증한 뒤 새 worker 실행의 입력으로 사용한다.
- 미완료 baseline bundle에 기존 5개 producer와 새 dependents producer를 명시적 복구 출처와 함께 연결한다.
- 이후 기존 실험 흐름대로 baseline DB 적재, 9/14 전처리/DB 적재까지 진행한다.
- 상태는 C:/pg914r3/status.ps1에서 유지하고 검증·계산·게시 단계를 구분한다.

## 실행 및 검증

- reader는 실제 읽기도 16MiB+1바이트로 제한한다. 초과 파일·안전하지 않은 경로는 계속 거부한다.
- 입력 세대 계약은 원본을 보존한다. 대상 명세 경로/SHA와 이전·현재 계약을 고정한 복구 증명으로 reader 및 호환성 검사 코드 두 파일의 변경만 허용한다.
- 회귀 및 작은 fixture 복구 통합 테스트 12개 통과(5.751초). 기존 5개 checkpoint와 request 보존, bundle 완성 경로를 검증했다.
- 실제 5,036,183바이트 명세 읽기와 호환성 검사 통과: 512개 파일 기록을 읽었으며 명세 SHA가 변경되지 않았다. 전체 파일 내용 검증은 실행 과정에서 수행한다.
- `C:/pg914r3/recovery-src`에 수정본을 고정했다. 기존 `src`와 `source-files.json`은 보존했다. 초안 계획은 `recovery-plan.reader-only-draft.json`, 최종 계획/증명은 `recovery-plan.json`과 `recovery-input-proof.json`이다.
- 2026-09-19 15:43:51 KST `recover-start.ps1`로 백그라운드 시작(wrapper PID 35068). stdout/stderr 경로는 `launch.json`에 기록한다.
- 시작 직후 `RUNNING`, process alive, `baseline:recovery:VERIFY_COMPLETED_STAGES` 확인. 앞 5개 단계는 COMPLETE 유지하며 재계산하지 않는다. 아직 worker 계산 및 전체 DB 적재 성공을 확인한 것은 아니다.
- 자원 설정은 기존 요청의 총 2 threads / 4GB, 병렬 worker 2개를 유지한다. 서버 원천 수집·운영 배포 변경 없이 로컬 격리 환경에서 수행한다.
- 상태 확인: `powershell -ExecutionPolicy Bypass -File C:\pg914r3\status.ps1 -Watch`. 이전 실패 시간도 이력으로 표시된다. 맨 위 현재 Status/Phase를 기준으로 판단한다.
