# 실제 입력 고정과 측정 연결

## 변경 범위와 작업 계획

사용자 요청: 1) 실제 raw 입력을 동일하게 고정, 2) 시간/CPU/메모리/디스크/네트워크/셔플 측정을 준비한다. 기존 배포를 변경하지 않고 부하를 제한한다. 실제 raw의 기존/Spark 성능 비교 실행은 3번 후속 작업이다. Jira 연결은 기존 승인대로 보류한다.

1. 원본 manifest/marker/객체 SHA와 대상 목록을 검증해 실험 전용 경로로 고정한다. 원본이나 운영 Curated 포인터를 변경하지 않는다.
2. 데이터 노드의 로컬 파일과 두 EC2가 접근할 공유 입력 경로에 같은 내용이 대응하도록 기록한다. 입력 identity, 코드/이미지/자원 프로파일을 고정한다.
3. 실제 입력 준비 중 전송량과 CPU/메모리를 제한하고 서비스를 감시한다.
4. cgroup 측정 및 Spark event log 집계 도구를 만들고 실험 실행기에 연결한다. 측정 범위와 미측정/추정값을 구별한다.
5. 작은 데이터로 측정 도구를 검증하고 실제 입력 고정 결과/남은 단계를 기록한다.

## 중요한 실행 경계

현재 `spark_experiment.prepare()`는 raw 다운로드뿐 아니라 기존 전처리 전체를 실행해 단계별 기준 입력을 만드는 함수다. 이번 raw 고정에서는 그 함수를 호출하지 않는다. raw 입력 고정과 기준 결과 생성/성능 실행을 분리하여, 단순 준비 명령이 실제 전체 계산을 시작하지 않게 한다.

## 결과

2026-09-15: 요청한 raw 입력 고정과 측정 준비 완료. 실제 raw 전처리/성능 비교는 미실행이다.

### 1. 실제 입력 고정

- 기준 스냅샷: `2026-08-31`, timestamp `2026-08-31T21:01:10.517131Z`.
- versions_full/requirements 및 Projects의 8월 24일·31일 이력, downloads 원본/상태/대상 목록과 고정 dependents 대상 파일을 포함한다.
- 총 **1,960개 객체 / 13,767,054,117 bytes**. 원천 manifest/완료 marker를 검증하고, 실험용 복사본 GET 전체의 SHA-256과 로컬에 기록한 동일 바이트를 확인했다. Projects 24개 Parquet은 footer 통계로 timestamp를 확인했다. 전체 행의 업무 정합성 재검사는 수행하지 않았다.
- 입력 identity: `9ccbbae874773a165b678e13dee3b1103549deb3fc8bf00672d59c2aaa952970`.
- raw manifest SHA-256: `f5408949993f6e2f2c53edab74e8c30848aa98db1a1843ff6b89f1868a0b0de7`.
- 공유 경로: `s3a://pickage-curated/experiments/raw-freeze-20260915-b1/inputs`.
- data EC2 로컬 경로: `/home/ubuntu/pickage-experiments/raw-freeze-20260915-b1/payload/frozen`.
- 최종 `raw-inputs.json`은 공유 경로와 로컬 경로에 모두 있다. manifest의 컨테이너 절대 경로 대신 `relative_path`로 로컬 mount 위치를 바꿔도 같은 입력을 읽는다.
- app EC2에서 공유 객체 1개(2,787 bytes)를 S3 HTTP로 읽고 해시 일치를 확인했다. 이 결과는 접근성 증거이며 Spark S3A reader의 실제 작업 검증은 아니다.
- 복사·검증에 약 **875.42초**가 걸렸다. 이는 전처리 시간이 아니다.

`freeze_raw.py`는 raw 복사만 담당한다. `_CLAIM.json`으로 새 실험 prefix를 먼저 예약하고 완료 manifest는 마지막에 한 번 기록한다. 실패한 경로를 덮어쓰지 않는다. `frozen_raw_store.py`는 고정 파일을 읽기 전용 S3 형태로 제공하며, 파일 크기/해시가 달라지거나 누락되면 실패한다. `prepare-frozen` 명령은 이 저장소를 통해 기존 전처리를 실행해 5개 단계의 기준 입력을 만드는 **다음 단계**다. 이번에는 실제 raw로 실행하지 않았다.

### 2. 측정 연결

- `telemetry.py`: cgroup CPU 누적 시간, 메모리 current/peak/anon/file/kernel/sock, OOM 및 reclaim 이벤트, 블록 장치 I/O와 네트워크 namespace 카운터를 수집한다. 없는 값은 NULL, 감소한 누적 카운터는 reset 표시와 NULL delta로 기록한다.
- `job.py`/`benchmark.py`: 시작·입력 검증·단계별 시간과 cgroup 변화량, Spark event log, 최종 로컬 보고서를 연결했다. 기존 repository 단계도 내부에서 Spark를 사용하므로 그 이벤트 로그도 수집한다. 기존 구현을 순수 비-Spark 처리라고 해석하지 않는다.
- `monitor_container.py`: 정확한 이름/라벨/Docker ID로 실험 컨테이너의 cgroup만 찾는다. 이름이 같은 다른 컨테이너로 교체되면 중단하며 출력도 덮어쓰지 않는다. 모니터 자체는 컨테이너를 수정하거나 정지하지 않는다.
- Spark task 종료 이벤트를 중복 없이 집계하고 job group으로 전처리 단계와 연결한다. 셔플 read/write, remote read, 메모리/디스크 spill 등 제공된 지표를 집계한다. 누락된 지표나 깨진/미완료 이벤트 로그는 불완전 상태로 구분한다.
- Spark 종료/원격 보고서 저장이 실패해도 샘플 수집 종료·로컬 기록·환경 복구를 시도하며 원래 처리 오류를 유지한다. 원격 S3 report는 종료 전 보고서이고, 최종값은 `report-with-telemetry.json`이다.
- 두 EC2 모두 `/home/ubuntu/pickage-experiments/measurement-kit-20260915-a1`에 같은 측정 도구와 자원 프로파일을 등록했다. archive SHA-256 `58fbb140e3219416627d716a6077146ffc925f5d000cdf55fa0a29ce49810e8d`, 각 호스트의 CLI help 실행 통과. 측정용 서비스나 상주 컨테이너를 추가하지 않았다.

### 실제 측정 도구 확인

1. 작은 합성 입력으로 baseline/Spark 5개 단계 재실행: **22개 결과 그룹 전부 일치**. 양쪽 CPU/메모리 샘플과 완결된 Spark 이벤트 로그가 생성됐다. 이 결과로 실제 데이터 성능 우위를 판단하지 않는다.
2. data EC2의 raw 복사 컨테이너에서 15초 측정: 16개 샘플, CPU 약 **1.335초**, disk write **262,189,056 bytes**. OOM/OOM kill 0. 실제 CPU·메모리·I/O 카운터 수집을 확인한 짧은 구간이며 전체 복사의 소비량이 아니다.
3. 해당 구간 종료 시 메모리: anon **53,116,928 bytes**, file cache **2,032,988,160 bytes**. cgroup current 약 2GiB를 프로그램 RSS 또는 메모리 누수라고 부르지 않는다. `memory.events.max`는 reclaim/상한 압력 횟수이며 OOM 횟수가 아니다. lifetime peak는 샘플링 시작 전 상태를 포함할 수 있고 순간 커널 회계로 상한을 조금 넘게 관찰될 수 있다.
4. host network의 RX/TX는 운영 서비스도 포함한 호스트 범위다. Spark remote shuffle bytes와 구별하며 실험 전용 네트워크 사용량으로 제시하지 않는다. 디스크 I/O도 페이지 캐시/지연 쓰기에 영향을 받으므로 실제 데이터 크기와 같지 않다.
5. 관련 단위 테스트 **32개 통과**, CLI help/문법 확인, `git diff --check` 통과. tiny fixture 전체 실행 뒤 추가한 종료 실패 처리 및 구형 샘플 호환성은 별도 단위 테스트로 검증했다.

### 자원 제한과 서비스 확인

- 복사 컨테이너: CPU 1개, 메모리 2GiB, swap 0, 단일 객체씩 복사. 전송 예산은 copy+GET 바이트 합산 평균 30MiB/s다. S3 CopyObject 한 객체의 순간 대역폭까지 제한하는 트래픽 셰이퍼는 아니다.
- guard는 MinIO/API health, data 호스트 여유 메모리, 기존 컨테이너 상태와 운영 Spark 작업 시작 여부를 확인했다. 자기 실험 라벨의 컨테이너만 중단할 수 있다.
- 감시 **469회**, 이상 0회. data 호스트 최소 가용 메모리 약 13.21GiB. 관찰된 최대 health 응답 시간은 MinIO 약 38ms, app 약 43ms.
- 전후 비교에서 app 운영 컨테이너 5개, data 4개의 ID/image/시작 시각/restart/OOM/health 상태가 동일하다. 이는 관찰 범위의 정상 결과이며 모든 사용자 요청 지연을 측정했다는 뜻은 아니다.
- 복사 exit 0, guard `FINISHED`, 준비용 컨테이너 제거 후 해당 실험 라벨 컨테이너 0개. 입력 파일·공유 객체·증거·측정 도구는 실험 전용 경로에 남겼다.
- 운영 compose/환경/서비스 설정·기존 raw·운영 Curated 포인터·DB는 변경하지 않았다. Jira 보류를 유지하고 이번에는 커밋하지 않았다.

## 이슈와 해결

- 기존 `prepare`가 전체 전처리까지 시작함: raw-only freeze와 이후 기준 입력 생성을 분리했다.
- 호스트 측정기의 mountinfo 경로 오류: `/proc/self/mountinfo`로 수정하고 실제 서버 cgroup 측정을 확인했다.
- 메모리 측정에 파일 캐시가 포함됨: anon/file/kernel 분해와 측정 범위를 함께 기록했다.
- 구형 샘플의 memory.stat 누락: NULL gauge 호환 처리와 회귀 테스트를 추가했다.
- Spark 종료 또는 원격 report 쓰기 실패 시 측정 누락: 각 정리 단계를 독립 실행하고 원래 오류를 보존했다.

## 다음 실행과 남은 한계

자원 설정안은 `evidence/real-input-preparation/resource-profile.json`에 고정했다. 비교 대상 총 상한은 CPU 3개/메모리 5.5GiB다. baseline/Spark local은 data 한 대, 분산 Spark는 data master(.25CPU/.5GiB)+driver(.75CPU/1GiB)+worker(1CPU/2GiB)와 app worker(1CPU/2GiB)로 구성한다. 이는 예약 자원이 아닌 컨테이너 상한이며 실제 데이터의 메모리 적합성은 아직 모른다. 재시도에서 상한을 바꾸면 모든 비교 조건을 함께 다시 기록한다.

후속 순서는 고정 raw로 기준 결과·단계 입력 생성 → 그 결과의 공유 MinIO 경로 구성 및 Spark S3A 읽기 확인 → 각 컨테이너 모니터 시작 → 같은 입력으로 baseline/Spark local/실제 두 EC2 Spark 비교다. 새 코드 묶음은 현재 코드 SHA를 재확인해 전용 경로에 배치한다. 기존 freeze 실행 당시 코드 묶음을 최신 측정 실행기라고 가정하지 않는다.

baseline 로컬 파일과 Spark MinIO 입력은 I/O 경로가 다르므로 엔진 자체 차이와 배치 구조 차이를 구분한다. 워커별 CPU는 합산하고 메모리는 동일 시각 합계와 개별 peak를 따로 보고한다. 원천 복사·기준 계산·해시 검사·기동·전처리·결과 대조 시간을 분리한다. 캐시/동시 운영 부하도 기록한다.

현재 상태: raw 입력과 측정 도구 준비 완료, `all_five_stage_inputs_ready=false`, `real_preprocessing_executed=false`, `two_ec2_performance_benchmark_executed=false`, `ready_for_load=false`, `ready_for_publication=false`, `task_09_complete=false`.

## 증거 위치

`evidence/real-input-preparation/verification-summary.json`에 요약, `raw-inputs.json`에 전체 입력 목록/해시, `resource-profile.json`에 후속 자원 설정안이 있다. 같은 폴더의 `app/data-before/after.json`, `guard.jsonl`, `cleanup.json`, `app-shared-read.json`, `container-metrics.jsonl`, `container-monitor-summary.json`, `fixture-*.json`, `app/data-measurement-kit.json`이 실행 증거다.
