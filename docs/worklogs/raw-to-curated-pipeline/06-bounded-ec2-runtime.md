# 기존 배포를 유지하는 두 EC2 실험 런타임

## 사용자 조건과 변경 범위

2026-09-15 사용자가 조건을 명확히 했다: 약간의 성능 영향은 허용하지만 기존 배포를 변경하지 않고 서비스에 지장이 없도록 제한한다. 따라서 05번 기록의 '서버 실행 전면 보류/별도 EC2 필요'는 최신 조건에서 해제한다. 기존 app/data EC2 두 대를 실제로 사용한다.

기존 서비스 컨테이너·이미지 태그·배포 파일·환경변수·방화벽·DB·운영 Curated 포인터는 변경하지 않는다. 별도 이름의 실험 이미지/컨테이너/경로로 준비하며, 신규 worker에만 자원 상한을 적용한다. 운영 worker를 재시작하거나 런타임을 설치하지 않는다. Jira 연결은 앞서 승인한 대로 보류한다.

## 작업 계획

1. 서버 자원, 서비스 health, 기존 Spark 작업, 포트 사용을 읽기 전용으로 재확인한다.
2. 로컬에서 검증한 공통 이미지를 두 EC2의 별도 실험 런타임에 제공한다. 전송/이미지 적재도 부하를 제한한다.
3. 실험 전용 master와 두 worker를 제한된 자원으로 실행하고 실제 서로 다른 EC2에서 작업이 수행되는지 확인한다. 제한 시간과 서비스/메모리 중단 기준을 둔다.
4. 결과와 서비스 전후 상태를 저장하고 실험 컨테이너를 정리한다. 두 EC2 실행 환경 검증과 실제 raw 전처리 성능 비교는 구분해서 기록한다.

## 착수 시 관측

17:44 KST: app/data 각각 4 논리 CPU, RAM 15.42 GiB. 가용 메모리 약 app 13.77 GiB, data 13.48 GiB. loadavg 낮음. API/web/Postgres 및 MinIO/MLflow health는 healthy. 기존 Spark worker 둘은 여전히 Python 3.8 / Java 11 / Node 없음이므로 그대로 둔다.

문서와 달리 data의 기존 일부 컨테이너는 memory+swap 상한이 memory의 두 배였다. 관측값을 기록하고 기존 설정을 수정하지 않는다. 신규 실험에는 swap 0을 적용한다.

## 실행 결과

**실제 app/data EC2 두 대의 실행 환경 및 노드 간 shuffle 검증 완료. 실제 raw 성능 비교는 아직 미실행.**

### 실행 구성

- 이미지 ID는 두 EC2 모두 로컬에서 검증한 `sha256:e3ca9ccf92c2c9fa0022920acab1713e6d35a0529e5ab6ac4f0a38428f955479`와 일치했다.
- 이미지 전송 파일 540,711,814 bytes. 각 서버 전송을 40,960 Kbit/s로 제한했다. archive SHA-256 `178604d0bfd4d400f17416d95ceba803fbbdb3024465f491fade2ff9125cb0ad`를 서버 양쪽에서 검사한 뒤 적재했다.
- 서버별 독립 경로 `/home/ubuntu/pickage-experiments/ec2-runtime-20260915-a1`. 기존 배포 경로에는 파일을 쓰지 않았다. 이미지 적재 클라이언트는 nice/ionice를 적용했지만 Docker daemon 전체의 CPU/I/O를 제한한 것은 아니다. 적재 중에도 서비스 health를 감시했다.
- 기존 UFW/보안그룹을 변경하지 않았다. 현재 비어 있는 기존 허용 포트로 별도 실험 master/data:40014, driver RPC/data:40012, driver block manager/data:40011, executor block manager/양쪽:40013, app worker RPC:40014를 사용했다. data worker RPC:17078은 같은 사설 IP로 self-connect를 먼저 확인했다.
- master UI/data:18080, worker UI/양쪽:18081. UI 포트를 외부에 새로 개방하지 않았다. 원래 master:7077 및 worker:40020은 유지했다. 이 포트 배치는 단기 실험용이며 다른 작업과 동시에 상시 운영하는 구성이 아니다.

| 실험 컨테이너 | EC2 | CPU 상한 | 컨테이너 메모리 상한 |
| --- | --- | ---: | ---: |
| master | data | 0.25 | 512 MiB |
| worker-data | data | 1 | 2 GiB |
| driver | data | 0.75 | 1 GiB |
| worker-app | app | 1 | 2 GiB |

모두 swap 0, 재시작 정책 없음, 실험 label로 구분했다. worker가 제공하는 executor heap은 각각 1 GiB/1 core다. 권한 capabilities를 제거하고 코드 1개 파일은 읽기 전용, 실험 출력 폴더만 쓰기용으로 mount했다. MinIO 자격증명/DB 연결은 제공하지 않았다.

### 실제 결과

- Spark application `app-20260915085525-0001`, 상태 `VERIFIED`.
- Spark task event에서 executor host가 `172.26.6.235`(app), `172.26.8.249`(data)로 기록됐다. 환경변수 출력뿐 아니라 실제 Spark task 실행 host도 대조했다.
- 두 executor 모두 Spark 3.5.3 / Python 3.11.16 / Node 24.21.0이며 semver 실행에 성공했다.
- barrier 작업으로 양쪽 worker 참여를 확인한 뒤 10,000개 정수를 분산 처리하고 16개 그룹으로 shuffle 집계했다. 예상 합계와 일치했다. 총 14개 task, remote shuffle read 1,548 bytes, shuffle write 3,104 bytes. 작은 값이지만 노드 간 실제 block 전송이 발생했음을 확인했다.
- 시작 후 계산 경과 10.776초, task executor CPU 합계 1.224초. 이 값은 런타임 smoke 관측값이며 raw 전처리 성능이나 속도 향상 근거가 아니다.
- `ec2_guard.py`가 서버마다 약 2초 간격으로 142회 확인했다. 메모리 4 GiB 미만, 연속 3회 health 오류/1초 초과/기존 컨테이너 이상/운영 Spark 작업 시작이면 실험 label의 컨테이너만 중단하도록 했다. 최대 유효 시간 10분.
- 감시 중 중단 조건 0회. app 최소 가용 메모리 13.38 GiB, data 12.68 GiB. API health 최대 응답 56.1ms, MinIO health 47.8ms. health endpoint 관측이며 모든 제품 API의 지연을 측정한 것은 아니다.
- 기존 app 컨테이너 5개/data 컨테이너 4개의 ID, 이미지, 시작 시각, health, OOM 여부, restart count가 전후 동일했다. 정상 종료 시 guard `FINISHED`, 이번 label의 컨테이너를 모두 정리했다.
- 별도 실험 이미지·전송 archive·로그는 다음 실험을 위해 전용 경로에 보존했다. guard는 종료됐고 실험 컨테이너는 남아 있지 않다.

### 실패와 수정 이력

1. 첫 driver는 capabilities 제거 상태에서 Ubuntu 소유의 출력 디렉터리에 root로 쓰지 못해 event log 권한 오류가 났다. 기존 서비스와 관계없는 실험 경로의 문제였다.
2. 두 번째 시도에서 호스트 UID로 실행하자 이미지 passwd에 그 UID가 없어 Java home이 `?`로 해석되어 Ivy 초기화가 실패했다.
3. 이미지 기본 사용자와 권한 제한을 유지하고 새 실험 출력 폴더만 쓰기 가능하게 만든 세 번째 시도가 통과했다. 앞선 출력/로그는 덮어쓰지 않았다. event log는 root 소유로 저장되어 읽기 전용 sudo cat으로 수집했다.

### 증거와 검증

`evidence/bounded-ec2-runtime/verification-summary.json`에 전후 서비스 비교, guard 집계, Spark event 집계 및 smoke 결과를 모았다. 원본 `app-before/after.json`, `data-before/after.json`, 서버별 `guard.jsonl`, `containers.json`, `image-loaded.json`, 성공/실패 driver log, Spark event log도 같은 경로에 있다.

- guard가 실험 label만 대상으로 중단하는 테스트 2개 통과.
- 기존 로컬 runtime 경계 테스트 3개 통과.
- Python compile, `git diff --check` 통과.

### 다음 단계와 미실행 범위

두 EC2 실행 환경의 막힘은 해소됐다. 다음은 이 별도 실행 환경에 **선정한 실제 raw 입력을 고정해 제공하고, 전처리 결과 대조 및 메모리/CPU/I/O/셔플 측정을 연결하는 작업**이다. 같은 입력으로 기존 방식과 Spark 두 노드의 계산 결과를 먼저 대조한 뒤 성능을 비교한다. 단일 노드 Spark는 분산 효과를 구분하는 추가 비교군으로 둔다.

이번에는 실제 raw 전처리 5단계의 EC2 실행, 전체 분산 결과 대조, 실험 MinIO 입출력, 최고 프로세스 메모리, 연속 단계 연결/게시 및 DB 적재를 실행하지 않았다. 이번 resource cap은 작은 smoke 기준이며 실제 raw가 동일 상한에서 완료된다는 보장은 아직 없다. 운영 배포/DB/기존 raw·Curated 데이터 변경은 없다.
