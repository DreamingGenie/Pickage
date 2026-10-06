# 실제 raw 기준 결과 생성

## 범위와 계획

사용자가 `진행시켜`로 승인한 기준 결과 생성 실행. 고정 raw를 기존 구현으로 처리해 이후 baseline/Spark local/두 EC2 Spark 비교에 쓸 기준 결과와 단계별 입력을 만든다. 이번 실행은 공식 반복 성능 비교나 운영 게시/DB 적재가 아니다. Jira 보류를 유지한다.

1. app/data 서비스 상태, data 디스크/메모리, 기존 Spark 작업 여부를 확인한다.
2. 고정 코드와 raw manifest identity를 확인해 새 실험 디렉터리에 배치한다.
3. data EC2에서 CPU 3개/메모리 5.5GiB/swap 0, 외부 네트워크와 운영 자격증명 없이 실행한다.
4. 독립 서비스 guard와 cgroup monitor를 먼저 시작한 뒤 작업을 허용한다. 실행기 장애/감시 누락, 디스크 부족, 최대 실행 시간 도달 시 실험만 중단한다.
5. 서버 백그라운드 실행기가 종료 상태와 로그를 저장하고 컨테이너를 정리한다. 이번 대화에서는 시작과 초기 정상 동작을 확인한다.

## 현재 상태

2026-09-15 19:13 KST에 `reference-20260915-a2` 실행 시작. **20:39 KST에 repository 단계의 JVM heap 부족으로 실패 종료**했다. 아래 초기 관찰 기록은 시작 당시 증거이며 현재 실행 중이라는 의미가 아니다.

### 종료 확인과 원인 조사

- 실제 경과 약 1시간 26분. snapshot 기준 생성, package_version, downloads 완료. repository 실패, 이후 package_snapshot/dependents 및 최종 experiment.json 생성 미완료.
- 최초 원인은 `java.lang.OutOfMemoryError: Java heap space`, `UnsafeSorterSpillReader`에서 발생했다. 마지막 `SparkSession does not exist in the JVM`은 JVM 실패 후 정리 중 발생한 후속 오류다.
- 실패 연산은 `repository_metrics/transform.py`의 version→package 참조 검증용 left anti join/count. 검증의 결과를 얻기 전 sort/shuffle 작업에서 실패했다.
- 실제 Spark 이벤트 설정: `spark.driver.memory=2g`, `spark.master=local[2]`, `spark.sql.shuffle.partitions=16`, AQE 활성화. 실패한 stage 45는 task 6개였다. 파티션 수만으로 실제 작업 크기/분포나 AQE 병합이 직접 원인이라고 확정하지 않는다.
- 컨테이너 OOMKilled=false, cgroup OOM/oom_kill 0. 컨테이너 총 메모리 상한과 JVM heap 제한은 서로 다르다.
- guard 2,517회 관찰 중 issue 0. 확인 시점 MinIO HTTP 200/API UP, 해당 실행 컨테이너 0개, cleanup_errors=[]였다. 결과·중간 산출물은 보존했다.
- 해결 후보는 먼저 실패 단계만 분리하여 파티션 크기/AQE 병합/동시 작업 수를 조절하고, 필요하면 전체 상한 5.5GiB 안에서 JVM heap 배분을 조정하는 것이다. 아직 수정 실행이나 효과 검증은 하지 않았다. 완료한 단계 재사용은 입력/코드 계약 검증 후에만 진행한다.

## 실제 실행 내용

- 호스트: data EC2 `172.26.8.249`. app EC2는 이번 기준 생성의 계산에 사용하지 않으며 API health를 함께 감시한다. 후속 분산 Spark 비교에서는 app/data 두 EC2를 사용한다.
- 실행 루트: `/home/ubuntu/pickage-experiments/reference-20260915-a2`.
- 감독 프로세스 PID: `2022953` (시작 시점). SSH stdin/stdout에서 분리해 실행했다.
- 컨테이너: `reference-20260915-a2-job`, ID `5c3f13f555142c2374084a263c9e06faaf366e718a6b6413fd08afb9c9d26f1d`.
- 이미지: `sha256:e3ca9ccf92c2c9fa0022920acab1713e6d35a0529e5ab6ac4f0a38428f955479`.
- 코드 SHA: `76c301e95b9ae60680ee10a6c1d08e11c79484dee3d69f660ec0bdd912977cd3`.
- 전송 archive SHA: `9c7bdf8f744cb1fcf55f67a56458d6489d542c31c825547e84c41f6ea46985c5`, 서버에서 일치 확인.
- 입력은 앞선 `raw-freeze-20260915-b1/payload/frozen`을 `/frozen`에 읽기 전용 mount. raw manifest SHA는 `f5408949993f6e2f2c53edab74e8c30848aa98db1a1843ff6b89f1868a0b0de7`로 재확인했다.
- 코드와 control도 읽기 전용 mount. 쓰기 가능한 host mount는 이번 실행의 `output` 디렉터리뿐이다. 컨테이너 자체 파일 시스템은 임시 쓰기 가능 상태이며, Node 모듈 검색을 위한 링크를 그 내부에만 만든다.
- CPU 3개/메모리 5632MiB/swap 0/PID 512 상한, 외부 network 없음, cap-drop ALL/no-new-privileges. 기존 요청의 엔진 설정은 threads 2, memory 2GB를 유지했다.
- 원격 MinIO/DB 자격증명을 전달하지 않는다. 기존 전처리의 저장 요청은 `OverlayS3`를 통해 로컬 실험 파일로만 기록된다.

## 독립 실행과 중단 조건

`reference_supervisor.py`가 service guard를 시작해 정상 샘플을 확인하고, 대기 중인 작업 컨테이너와 resource monitor를 띄운다. 모니터 첫 샘플을 확인한 후 `start.signal`을 기록해야 계산이 시작된다.

- 기존 MinIO/API health 이상, 운영 컨테이너 변화, 운영 Spark 작업 시작, data 가용 메모리 4GiB 미만: guard가 자기 실행 라벨의 컨테이너만 중단한다.
- guard/monitor 종료 또는 20초 이상 샘플 정지, 디스크 여유 30GiB 미만, 최대 6시간: supervisor가 실험을 중단한다. 실행 전 디스크 여유는 약 232GiB였다.
- supervisor heartbeat가 25초 이상 갱신되지 않으면 작업 컨테이너 자체도 종료한다. supervisor가 강제 종료된 경우 작은 guard는 최대 시간까지 남을 수 있지만 계산은 계속되지 않는다.
- 정상 완료/실패 시 supervisor가 `result.json`을 쓰고 guard/monitor를 종료한 뒤 실험 컨테이너를 제거한다. 결과·로그 파일은 유지한다. 자동 재실행이나 다음 엔진 실행은 하지 않는다.
- 기존 `ec2_guard.py`의 허용 최대 시간을 24시간으로 확장했지만 기본값은 유지했다. 이번 실행에는 6시간을 명시했다.

## 파일과 상태 확인

아래는 모두 실행 루트 기준이다.

| 파일 | 의미 |
| --- | --- |
| `status.json` | 감독 실행의 STARTING/RUNNING/COMPLETE/FAILED/ABORTED 상태 |
| `result.json` | 종료 상태·exit code/OOM·정리 오류, 종료 후 생성 |
| `job.log` | 기준 결과 생성의 stdout/stderr |
| `guard.jsonl`, `guard-result.json` | 서비스/여유 메모리 감시와 종료 이유 |
| `metrics/container-metrics.jsonl`, `container-summary.json` | 컨테이너 자원 시계열과 종료 요약 (둘 다 metrics 디렉터리) |
| `output/reference/w/ref/status.json` | 기존 전처리의 단계별 진행 상태 |
| `output/reference/experiment.json` | 기준 결과/단계 입력 manifest, 성공 시 생성 |
| `output/events/` | 기존 repository 단계에서 사용하는 local Spark 이벤트 로그 |

서버 프로세스가 측정·감시·정리를 맡으므로 Codex가 계속 접속해 있을 필요는 없다. 이번에는 자동 알림 스케줄을 만들지 않았다. 종료 후 결과를 확인하고 다음 비교를 진행해야 한다.

## 발생한 이슈와 해결

1. Node 모듈 설치 위치와 기존 resolver의 검색 위치가 다름: 운영 코드/이미지를 바꾸지 않고 disposable 컨테이너 내부의 `/usr/local/bin/node_modules`를 설치 위치로 연결했다. 고정 이미지의 runtime 검색 성공을 확인했다.
2. 첫 시도 `reference-20260915-a1`은 출력 폴더 권한으로 `PermissionError`가 발생했다. `cap-drop ALL`로 root의 DAC override도 제거되므로 ubuntu 소유 0755 폴더에 쓸 수 없었다. 전처리 시작 전 exit 1, OOM 없음, 서비스 정상, 컨테이너 자동 제거 및 정리 오류 없음.
3. 새 실행 a2에서는 이번 실험의 output/tmp 디렉터리만 명시적으로 쓰기 가능하게 생성했다. 실패 경로를 덮어쓰지 않았다. raw/운영 디렉터리 권한은 변경하지 않았다.

## 검증과 미완료 범위

- 관련 raw/guard/monitor/supervisor 테스트 15개 통과, 새 실행기 문법 검사 및 `git diff --check` 통과. 수정된 실행기에 대한 읽기 전용 독립 검토에서 시작 차단 요소 없음.
- a2 초기 관찰에서 실제 raw 파일 I/O, CPU/메모리 샘플 증가를 확인했다. guard issue 0, OOM/OOM kill 0. 해당 순간 메모리 대부분은 파일 캐시였다.
- 관찰 증거: `evidence/real-reference-run/`의 전후 초기 기록, 실패 a1 기록, 실행 a2 기록 및 코드 identity.
- 아직 기준 생성 완료 여부, 결과 동등성, 실제 처리 시간/자원 총량, 두 EC2 성능은 확인하지 않았다. Spark 성능 비교·운영 게시·DB 적재는 이번 백그라운드 작업에 포함되지 않는다.
- `ready_for_load=false`, `ready_for_publication=false`, `task_09_complete=false` 유지. 이번 변경은 커밋하지 않았다.
