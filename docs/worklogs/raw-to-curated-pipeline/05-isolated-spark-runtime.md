# 운영 서버 영향 없는 Spark 실험 환경 준비

후속 조건 정정: 사용자가 제한된 성능 영향을 허용하고 기존 배포를 유지하는 실험을 승인했다.
아래 서버 실행 보류는 당시 판단의 기록이다. 이후 실제 두 EC2 검증 결과는 [06번 기록](06-bounded-ec2-runtime.md)을 따른다.

## 변경 범위와 작업 계획

2026-09-15 사용자 조건: 현재 배포된 서버에 절대 영향을 주지 않는다. 이번 작업에서는 SSH/서버 Docker/운영 MinIO에 접속하지 않고 서버 설치·설정·포트·worker 변경 및 실험 제출을 하지 않는다. 같은 EC2에서 수행하는 계산의 영향이 0이라고 보장할 수 없으므로 서버 실행은 보류한다.

1. 기존 실험 Dockerfile을 재사용해 Spark 3.5.3 / Python 3.11 / Java 17 / Node 24 이미지 빌드 입력과 실제 버전을 고정한다. 기존 3.5.7 비교 이미지 태그는 보존한다.
2. 로컬 Docker Desktop에서 네트워크 없는 작은 fixture로 기존 방식/Spark의 출력 동등성을 검증한다.
3. 로컬 내부 네트워크의 master + worker 2개 구성과 검증 도구를 만든다. 운영 연결 정보/자격증명, 외부 포트, Docker 소켓을 제공하지 않는다.
4. 동일 이미지로 두 로컬 worker의 실제 작업 참여 및 executor 안의 Node 버전 해석을 확인한다. 가능한 경우 같은 fixture의 분산 결과를 기존 출력과 대조한다.
5. 실제 실행 결과와 미실행 범위를 기록한다. 로컬 컨테이너 2개 검증을 EC2 2대 성능 검증으로 취급하지 않는다.

## 사전 확인

- 실험 worktree HEAD `878a0c0`, branch `codex/raw-to-curated-pipeline`.
- Docker context `desktop-linux`, endpoint `npipe:////./pipe/dockerDesktopLinuxEngine` 확인. 이후 Docker 명령은 해당 로컬 context를 명시한다.
- 기존 로컬 이미지 `pickage-spark-experiment:local` ID `c0d3c108c929` 보존.
- 기존 로컬 MinIO/DB 컨테이너는 별도 실행 중이다. 실험은 고유 compose project와 자원 상한으로 분리하며 기존 컨테이너를 재시작/삭제하지 않는다.

## 결과

로컬 공통 이미지 빌드와 검증 완료. 서버 실행 및 실제 raw 성능 측정은 하지 않았다.

### 구현한 내용

- 기존 Dockerfile에 선택 가능한 Python 베이스 인자를 추가하고 기존 기본값은 유지했다.
- `pipeline/spark_experiment/runtime/images.lock.json`: Spark 3.5.3, Node, Python 베이스의 amd64 manifest digest 고정.
- `runtime/build.local.ps1`: Docker Desktop 로컬 named pipe만 허용하고 빈 context로 이미지를 빌드한다. 기존 `:local` 태그를 덮어쓰지 않는다.
- `runtime/compose.local.yaml`: 내부 전용 network의 master/worker 2개와 opt-in driver. 공개 포트, 운영 설정/자격증명, Docker socket, MinIO 연결이 없다.
- `runtime/cluster_smoke.py`: barrier stage로 두 worker에 동시에 작업을 배치하고 각 executor의 Python/Java/Node 및 semver 호출 결과를 저장한다.
- `runtime/inspect_runtime.py`: 이미지의 실제 런타임 및 Python 패키지 버전을 기록한다.

### 실제 검증 결과

- 새 이미지: `pickage-spark-experiment:runtime-3.5.3`, ID `sha256:e3ca9ccf92c2c9fa0022920acab1713e6d35a0529e5ab6ac4f0a38428f955479`.
- Spark 3.5.3 / Python 3.11.16 / Java 17.0.20.1 / Node 24.21.0 / DuckDB 1.5.5.
  semver 7.8.5, npm-package-arg 13.0.2. 전체 패키지는 `evidence/isolated-runtime/runtime.json`에 기록했다.
- apt 패키지 및 pip 전이 의존성은 빌드 시 결정된다. 베이스 digest 고정만으로 매번 동일한 최종 이미지가 생성된다고 주장하지 않는다. 이번 두 엔진과 두 worker는 완성된 동일 이미지 ID로 실행했다.
- 기존 작은 fixture의 입력 28개 SHA-256을 다시 확인했다. 두 엔진 각 1회, 전처리 5단계와 출력 22개 그룹이 `EXACT_CANONICAL_ROW_MULTISET` 비교를 통과했다 (`VERIFIED`).
  실행 위치: `C:/Users/SSAFY/AppData/Local/Temp/px-y31l6gk0/i/b-d8f81b8e/`.
  요약 복사본: `evidence/isolated-runtime/fixture-summary.json`.
- fixture 비교 컨테이너: 각 2 CPU, 메모리 6 GiB, swap 0, `--network none`.
- 로컬 cluster의 worker 두 개(`453bdc564f73`, `da6bf65fc056`)에서 각각 1개 partition이 실행됐다. 두 executor 모두 같은 Python/Java/Node 버전이고 semver 검사에 성공했다.
  증거: `cluster-smoke.json`, `cluster-smoke.log`, `containers.json`, `compose-resolved.json`, `network-internal.txt`.
- cluster 자원 상한: master 0.5 CPU/512 MiB, worker 각각 1 CPU/2 GiB, driver 1 CPU/1 GiB. 모든 컨테이너의 memory+swap 상한은 memory 상한과 같고 외부 포트 binding은 없다.
- 새 구성 경계 테스트 3개, PowerShell parser 검사, `git diff --check` 통과.
- 실험 project `pickage-runtime-local-20260915`의 컨테이너와 network를 종료·삭제했다. 기존 로컬 DB/MinIO 3개의 ID와 시작 시각은 전후 동일하다 (`preexisting-containers-before.txt`, `preexisting-containers-after.txt`).
- 기존 `pickage-spark-experiment:local` 이미지 ID `c0d3c108c929...`도 보존됐다. 원래 작업 폴더의 branch `infra/config/S15P21A506-223-cd-pipeline`, HEAD `194154a`는 바꾸지 않았다.

### 발견한 문제와 처리

- 런타임 확인 파일을 컨테이너 `/inspect.py`에 mount하면 Python 표준 `inspect` 모듈을 가려 import 오류가 발생했다. `/runtime_probe.py`로 바꾼 후 버전 확인에 성공했다. 제품 계산 코드 변경은 없었다.
- barrier 작업 시작 시 executor가 기동 중이라 0 slots 경고가 1회 발생했다. 두 executor가 준비된 뒤 동일 실행에서 정상 완료했다.

### 미실행 범위와 다음 조건

- 이번 턴에는 SSH, 서버 Docker, 운영 MinIO 호출 및 서버 설정/배포/worker 변경을 전혀 하지 않았다. 앞선 다운로드·대상 목록 업로드 기록은 이번 작업 이전 이력이다.
- 실제 raw 데이터 처리·최고 메모리/CPU/셔플/네트워크 측정, 전체 단계의 분산 결과 비교 및 연속 연결, MinIO 게시, DB 적재는 미실행이다.
- 작은 fixture 검증과 local cluster smoke만 수행했다. 두 검증이 일부 겹쳤으므로 fixture summary의 시간/비율을 성능 비교에 사용하지 않는다. EC2 2대 성능 결과도 아니다.
- 같은 app/data EC2에서 계산하면 운영 서비스와 CPU·메모리·디스크·네트워크를 공유한다. 별도 컨테이너나 자원 상한만으로 운영 영향 0을 보장할 수 없다. 사용자 조건을 만족하는 별도 실험 자원이 확보되기 전까지 기존 EC2에 실험을 제출하지 않는다.
- `local_runtime_verified=true`, `server_runtime_deployed=false`, `ready_for_prepare=false`, `ready_for_benchmark=false`, `ready_for_publication=false`, `db_loaded=false`.
