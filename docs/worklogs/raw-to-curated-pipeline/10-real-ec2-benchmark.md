# 실제 두 EC2 전처리 성능 비교

## 변경 범위와 계획

사용자 요청: EC2 성능 측정을 진행하고, 기존 방식의 메모리 변경을 Spark에도 반영한다. Jira는 기존 승인대로 보류한다. 운영 배포/DB/원천 수집은 변경하지 않는다.

1. 성공한 기준 산출물에서 5개 단계의 입력을 구성하고 파일/생성 계약을 검증한다. 아직 실행하지 않은 package_snapshot/dependents의 입력도 앞 단계의 검증된 결과로 만든다.
2. 동일 입력 identity와 코드/image/JAR를 고정하고 실험 전용 MinIO에 공유 입력을 준비한다.
3. 실제 app/data 두 EC2 worker로 Spark를 실행한다. barrier와 본 작업 이벤트에서 두 사설 IP의 실행을 확인한다.
4. Spark 실험 컨테이너를 정리한 뒤 같은 총 자원 한도로 기존 방식 전체를 실행한다. 이후 결과를 비교한다. 단계별 입력을 고정한 비교이며 Spark 결과를 다음 단계로 이어 게시하는 운영 파이프라인이 아니다.
5. 모든 실행은 서버 감독/서비스 감시/자원 측정과 함께 백그라운드로 진행한다. 준비 시간·입력 검증·실제 계산·결과 비교를 분리하고, 완료 또는 실패 상태를 기록한다.

## 자원 조건

| 방식/역할 | EC2 | CPU 상한 | 컨테이너 메모리 | JVM heap |
| --- | --- | ---: | ---: | ---: |
| 기존 방식 | data | 3 | 7.5GiB | repository local Spark 4GiB |
| Spark master | data | 0.25 | 0.5GiB | 256MiB |
| Spark driver | data | 0.75 | 1.5GiB | 1GiB |
| Spark worker | data | 1 | 2.75GiB | executor 2GiB + worker daemon 256MiB |
| Spark worker | app | 1 | 2.75GiB | executor 2GiB + worker daemon 256MiB |

두 방식 모두 총 CPU 3/컨테이너 메모리 7.5GiB/swap 0이다. 계산용 executor heap 합계는 4GiB이며, 분산 방식에는 별도 driver/daemon heap이 있다. 동일 총 cgroup 상한이지 프로세스 구성이나 전체 JVM heap 합계가 동일하다는 뜻은 아니다. 기존 방식의 DuckDB 메모리 상한도 4GB로 명시하고 결과에 기록한다.

운영 서비스는 같은 호스트를 공유한다. baseline은 로컬 입력, Spark는 MinIO 입력이므로 I/O 경로 차이를 결과에 표시한다. 이번 실행 순서는 Spark 두 EC2 → 기존 방식이며 캐시/동시 운영 부하가 통제된 반복 실험이라고 주장하지 않는다. Spark 한 대 비교는 이 두 노드 측정 이후 별도 실행 대상으로 남긴다.

## 준비 및 실행 상태

작업 중. 이전 repository-only 성공을 전체 baseline 성공으로 간주하지 않는다. 실제 두 EC2 계산, 전체 결과 일치 및 성능 우위는 아직 미검증이다.

## 실제 착수 기록

- run_id: `benchmark-ec2-20260915-a1`. app/data 양쪽에 동일 실험 코드와 이미지, S3A JAR를 준비하고 서버 감독 프로세스를 분리 실행했다.
- 코드 ZIP SHA256: `9a06b7e31fdc13b5ac3863d61490a889b530796747ce8fba8eb8de3d8289bb8d`. 두 호스트에서 검증했다. 운영 코드/이미지는 변경하지 않았다.
- data supervisor PID `2202917`, app supervisor PID `646133`. 최초 확인에서 data `prepare` 컨테이너가 실행 중이며 app 감독은 실험 master 시작을 기다린다.
- 준비 단계는 1 CPU/2GiB로 입력 검증·공유 전송만 수행한다. 비교 대상인 계산 단계의 자원 조건은 위 표와 같다.
- 고정 입력 준비 → Spark 양 호스트 → Spark 정리 → baseline 전체 → SQL exact 비교가 백그라운드로 연결돼 있다. 실패하면 해당 시점에서 중단하며 후속 단계로 넘어가지 않는다.
- 입력 공유와 결과 다운로드는 16MiB/s로 제한한다. Spark 계산 중 MinIO I/O는 CPU/메모리/서비스 상태 감시를 적용하지만 별도 네트워크 속도 제한은 없다.
- 양 호스트의 서비스 guard, 컨테이너별 1초 cgroup 메트릭, supervisor heartbeat를 기록한다. 6시간 제한, 서비스 이상/감시 중단/디스크 30GiB 미만/가용 메모리 4GiB 미만 조건에서 실험만 중단한다.
- adapter/comparator/cluster entry/app supervisor/guard/monitor 관련 테스트 34개 통과. 추가 Python 경로 수정 후 app supervisor 6개 재검사 통과. 이는 실행기 검증이며 실제 데이터 결과 일치나 분산 성능 성공 판정은 아직 아니다.
- 최종 상태와 원인: 서버 run 디렉터리 `status.json`, `result.json`. 단계 로그는 `prepare.log`, `spark.log`, `baseline.log`, `compare.log`; 실험 산출물은 `output/` 아래 보존한다.
- JVM 한도는 RAM 안의 한도이며 swap을 늘리지 않았다. 운영 서비스의 swap/배포 설정은 그대로다.
- 착수 직후 실측: 양 호스트 guard issue=null, data 가용 메모리 약 13.4GiB/app 약 13.7GiB. data 준비 컨테이너 cgroup 샘플 정상 갱신. 이 시점에는 Spark 계산이 시작되기 전이다.

## 2026-09-16 상태 확인 — 준비 단계 실패

- 서버 최신 status/result/log를 조회했다. data 준비 단계는 2026-09-15 23:39:26 KST에 exit 1로 종료했다(약 184초, OOMKilled=false).
- 원인: `real_stage_inputs.assemble`의 JSON 저장에 `PosixPath` 값이 남아 `TypeError: Object of type PosixPath is not JSON serializable` 발생. 새 입력 어댑터의 직렬화 결함이며 메모리 부족이 아니다.
- Spark 계산 및 이후 baseline/결과 비교는 시작되지 않았다. 성능 비교 결과 없음.
- app 감독은 master가 시작되지 않아 6시간 대기 후 TIME_LIMIT_WAITING_FOR_MASTER로 종료했다. app 실험 worker 자체는 시작되지 않았다.
- 두 호스트의 실험 컨테이너는 현재 없고 cleanup_errors=[]이다. 현재 운영 web/api/postgres/MinIO/mlflow 컨테이너는 healthy이며 기존 Spark 컨테이너는 running이다. 기록된 guard에서 서비스 이상은 없었다.
- 이번 요청은 상태 확인이므로 재실행하지 않았다. 재실행 전 Path를 문자열로 정규화하는 수정과 실제 어댑터 경로를 포함한 회귀 검증이 필요하다.

## 2026-09-16 재실행 계획
Path 입력을 문자열로 정규화하고 직렬화를 파일 생성 전에 검증한다. 중첩 Path 회귀 검사를 추가하고 이전 실패 기록을 보존한 채 benchmark-ec2-20260916-a1로 같은 자원 제한의 실행을 재개한다. 실제 준비 단계 통과 및 Spark 착수 여부를 확인한다.

### 수정 및 재착수
- stage 입력의 중첩 Path/list/tuple을 JSON용 문자열/배열로 정규화한다. 임의 객체는 문자열로 숨기지 않고 오류를 유지한다.
- JSON 직렬화를 출력 파일 생성 전에 수행해 직렬화 실패가 잘린 manifest를 남기지 않도록 수정했다.
- 실제 오류와 같은 다운로드 daily_files의 Path, 중첩 repository 경로, MinIO 경로 치환을 회귀 검사했다. 관련 36개 테스트 통과.
- 새 run: benchmark-ec2-20260916-a1. 코드 ZIP SHA256 de6aedf50af59929cfc7f695649ddaf2fba27a8ace04173a3b668aaab36ce270, 양 호스트 검증 완료. 기존 실행 디렉터리는 보존.
- data PID 2338305 / app PID 1002856으로 분리 실행. 시작 전 운영 컨테이너 상태 정상, 디스크 여유 data 122.6GiB/app 132.8GiB. CPU/RAM/swap/서비스 중단 기준 변경 없음.

- 실제 서버 재검증: output/local-manifest.json을 JSON으로 다시 읽는 데 성공했다. input_files=1266, stages=5. 이전 PosixPath 직렬화 오류 지점 통과 확인.
- 확인 시점 상태 RUNNING/prepare, 준비 컨테이너 정상 실행, service guard issue=null. 이후 공유 입력 전송 및 Spark/기존 방식/결과 비교는 자동 순차 진행 예정이며, 본 계산 완료와 성능 결과는 아직 미검증이다.

### 2026-09-16 09:30 KST 무렵 진행 확인
- prepare 종료코드 0, 약 529초. 1266개 입력 준비 완료, 새 공유 업로드 5,037,560,150 bytes.
- RUNNING/spark. package_version 단계의 실제 Spark job 54개 제출, 전체 53개 job 종료 기록 및 최신 job 성공 확인. 두 호스트에서 TaskEnd 기록 확인(app 1411/data 968, barrier 포함 시점 집계). 단순 연결 확인을 넘어 본 데이터 작업이 양 호스트에서 실행 중이다.
- baseline/compare 아직 미착수. 양 호스트 서비스 guard issue=null, 운영 컨테이너 healthy/running. data worker의 cgroup 사용량은 파일 캐시 포함 약 2.75GiB 상한에 근접하며 oom/oom_kill=0. 실행 조건 변경 없음.

### 2026-09-16 10:00 KST 무렵 지연 확인
- 여전히 package_version 계산 중이나 이벤트 파일은 조회 직전 갱신됐다. 이전 확인 대비 TaskEnd 2379→2716, 종료 Job 53→65. TaskEnd 사유는 2716건 모두 Success로 실패 재시도 증거 없음.
- 마지막 활성 stage 117(count), 총 16태스크 중 5개 완료를 확인했다. 해당 stage 제출 시각도 최신이므로 동일 태스크에 정지한 상황은 아니다.
- 최근 약 62초 CPU 누적 증가량 기준 data worker 약 0.90코어/app worker 약 0.98코어 사용. 각 1CPU 제한 내에서 계산 부하가 지속된다. 양쪽 worker oom/oom_kill=0이며 메모리에는 파일 캐시가 포함된다.
- 서비스 guard issue=null. 전체 Spark 완료 시간과 6시간 내 전체 비교 완료 여부는 아직 알 수 없다. 자원 조건과 실행은 변경하지 않았다.

### 2026-09-16 종료 확인
- 정상 완료가 아닌 FAILED. 11:08:29~31 KST에 양 호스트 guard가 서비스 상태 확인 3회 연속 실패를 감지하여 실험 컨테이너를 종료했다. data HTTPError, app URLError/ConnectionResetError. Spark 실행 약 2시간 11분 후 중단.
- 운영 API의 현재 컨테이너 StartedAt은 11:08:24 KST로 감시 실패 시각과 겹친다. 배포/재시작 관련 중단 가능성이 있으나 원인 자체는 미확정이며 실험이 API 장애를 유발했다고 판단할 근거는 없다.
- 실험 컨테이너 OOMKilled=false, cleanup_errors=[]이며 현재 잔여 실험 컨테이너 없음. baseline/compare와 최종 benchmark 결과 파일 없음. 현재 API 등 운영 서비스 healthy.
- 상태 확인만 수행했으며 재실행하지 않았다.
