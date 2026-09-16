# 저장소 지표 JVM 4GiB 재시도

## 변경 범위와 계획

사용자 승인: JVM 한도를 4GiB로 늘려 본다. 앞서 제시한 실험 컨테이너 상한 7.5GiB를 적용한다. 실행 대상은 MinIO가 있는 data EC2다. Spring/app 배포 변경은 하지 않는다. Jira 보류 유지.

1. 기존 저장소 지표 입력 manifest와 완료한 package/version 결과를 읽기 전용으로 재사용한다. 입력 SHA와 생성 코드 계약을 검증한다.
2. 기존 repository 변환 코드, local[2], shuffle 16/AQE 활성화를 유지하고 JVM heap만 2→4GiB로 변경한다. 컨테이너 상한은 5.5→7.5GiB, swap 0을 명시한다.
3. 실패한 repository 단계만 별도 경로에서 실행한다. 같은 서비스 guard/자원 monitor/heartbeat/최대 6시간 제한을 적용한다.
4. 완료 여부와 결과를 보고하기 전에는 성공/전체 파이프라인 재개를 주장하지 않는다.

## Swap 확인

data 서버 `/proc/swaps`에 `/swapfile` 약 2GiB가 활성화돼 있다. 그러나 `deploy/prod/README.md`의 "Swap — 2 GiB 를 넣고, 컨테이너에는 주지 않는다" 정책대로 실험에도 `--memory`와 `--memory-swap`을 같은 값으로 준다. Docker에서 두 값이 같으면 컨테이너 swap 허용량은 0이다.

swap을 별도로 허용하는 것은 기술적으로 가능하다. 하지만 JVM의 최대 heap을 늘리는 설정은 아니므로 `Java heap space` 문제를 swap만으로 해결하지 못한다. 호스트 RAM 압박을 완충하는 기능이며 빈번한 paging에는 성능 비용이 있다. 배포 문서에 따르면 data 노드의 swap·MinIO·Spark scratch가 같은 디스크를 공유한다. 이번 실행은 호스트/컨테이너 swap 정책을 변경하지 않는다.

근거: [Docker resource constraints](https://docs.docker.com/engine/containers/resource_constraints/#--memory-swap-details).

## 실행 결과

실행 ID `repository-heap4g-20260915-a1`은 **2026-09-15 22:36 KST에 성공 종료**했다. 감독 상태 COMPLETE, 작업 보고서 COMPUTED, repository 자체 validation PASSED, exit 0/OOMKilled=false/cleanup_errors=[]다. 아래 초기 관찰은 실행 시작 당시 기록이다.

### 종료 결과

전체 실행 약 32분 49초(준비·검증·정리 포함), repository 계산 약 30분 21초. `metric/data` 11,080,940행과 품질 산출물을 생성했다. 동일 입력에 대해 JVM 4GiB/컨테이너 7.5GiB로 이번 repository 단계가 완료됐음을 확인했다. 모든 입력/후속 단계의 메모리 적합성이나 성능 우위를 의미하지 않는다. 운영 서비스의 현재 health는 정상이며, 실험 컨테이너는 자동 정리됐다.

전체 파이프라인 기준 생성과 분산 Spark 비교는 여전히 미완료다. 생성한 repository 결과의 후속 연결과 package_snapshot/dependents 처리는 별도 진행해야 한다. 종료 요약은 `evidence/repository-heap-retry/completion-summary.json`에 기록했다.

- 서버 실행 루트: `/home/ubuntu/pickage-experiments/repository-heap4g-20260915-a1`.
- 감독 프로세스 시작 PID `2146997`, 컨테이너 ID `0bfca59c8ca89c835b96504041fafce9f6466a7986aaecf3a8c9a5086f2f8643`.
- 코드 SHA `ed38f352f3841dde758dd8dc30b61b09ee25947f62fae0a87dbecf2e093f9c4b`, 업로드 archive SHA `5421ca1d137aaa332745996913393d11cdc3688a30d92319dfff03d7693d0e52` 서버 일치 확인.
- 이전 입력 manifest SHA `fb7e451424a6b49297ffd40ffe730b70fed5bf891bb911d5a9153e6e8cf8ed48` 및 repository 코드 계약 SHA `fe7382112c5278249bf9f7d8f26304b208ae89c8e898afdc635fdc36d24bf7ef`를 고정했다. 이전·현재 repository 코드 계약이 모두 이 값이어야 실행한다. 이전 manifest에 새 해시를 붙여 통과시키지 않는다.
- 이전 `/output/reference`를 기존 컨테이너 경로 `/experiment/reference`에 읽기 전용 mount하고, 이전 소스도 `/previous-code`에 읽기 전용으로 제공한다. 신규 결과와 scratch만 이번 output에 쓴다.
- 실제 Docker inspect: Memory=MemorySwap=8,053,063,680 bytes, CPU 3, network none. 컨테이너 내부 `memory.swap.max=0` 확인. 호스트나 기존 배포 설정은 변경하지 않았다.
- 실행 진입점 `repository_retry_entry.py`: 입력/생성 코드 pin 검사 → 기존 `reverify_inputs` → 별도 JVM 4GiB 확인 → 기존 `job`의 repository 단계만 실행. `--driver-memory 4g`를 JVM 시작 전에 전달하고 기존 runtime에도 4g를 설정한다. 셔플 파티션 16/local[2]는 유지한다.
- 로컬의 동일 고정 이미지에서 JVM `Runtime.maxMemory()`=4,294,967,296 bytes, `spark.driver.memory=4g`, local[2], 한 행 계산 성공을 확인했다. 이것은 설정 검증이며 서버 실제 데이터 성공 증거가 아니다. 서버에서도 입력 검증 후 같은 heap 확인을 통과해야 실제 작업을 시작한다.
- 관련 단위 테스트 14개 통과. 새 entry의 파일 충돌 검사 순서 오류는 실행 전 검토에서 수정했고, 실제 main 경로를 모의 실행하는 회귀 테스트를 추가했다. 문법 검사/`git diff --check` 통과.
- 초기 cgroup 샘플에서 입력 읽기 증가 확인, OOM 0, guard issue 0. 서비스/감시 오류·감시 정지·디스크 30GiB 미만·최대 6시간 중단 조건은 유지한다. 완료/실패 시 로그를 남기고 자기 실험 컨테이너를 정리한다.

이번 실행은 전체 기준 생성의 자동 재개가 아니라 **repository 단계만의 재시도**다. 완료한 package_version/downloads를 다시 계산하지 않는다. 성공하더라도 후속 단계 연결·전체 결과 검증·Spark 두 EC2 성능 비교는 남는다. JVM 확인용 별도 프로세스 시간은 준비 비용이며, host monitor의 시작부터 끝까지 집계에는 포함될 수 있다. `job` 보고서의 단계 계산 시간과 구별한다.

로그는 실행 루트의 `job.log`, `status.json`, 종료 후 `result.json`, `guard.jsonl`, `metrics/`에 남는다. 계산 보고서는 `output/repository-retry/report.json`, 최종 측정은 `output/retry-telemetry/report-with-telemetry.json`이다. 초기 증거는 `evidence/repository-heap-retry/`에 복사했다.

현재 `ready_for_load=false`, `ready_for_publication=false`, `task_09_complete=false`. 이번 변경은 커밋하지 않았다.
