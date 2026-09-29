# 24. 하나의 주간 timer로 수집과 전처리 연결

## 변경 범위와 계획
- 기존 weekly timer와 수집 상태 계약을 유지하고, 같은 호스트 잠금 아래 수집 후 전처리를 순차 실행한다.
- 수집 종료 코드와 별개로 완료된 raw 회차를 조회한다. 이전 Curated baseline 이후의 회차를 날짜순으로 처리한다.
- raw manifest SHA와 완료 마커를 확인하고 요청을 고정한다. 실패 시 같은 실행 ID로 재개한다.
- 전처리 운영 상태·실패 이벤트를 로컬과 MinIO에 남긴다. 입력 대기, 일시 실패, 수동 조치가 필요한 차단을 구별한다.
- 로컬 테스트로 선택·재시도·차단·중복 실행 방지를 확인한다. 운영 서버 배포와 실제 데이터 실행은 하지 않는다.

## 실제 작업과 검증
- `orchestration/dispatcher.py`: raw 회차 페이지 조회, 완료 bundle 부모 이력 검증, 가장 오래된 미처리 회차 하나 실행. baseline이 없으면 대기한다.
- MinIO 운영 prefix `_ops/preprocessing/<snapshot>/`에 불변 request와 상태·이벤트를 남긴다. 요청의 raw SHA와 완료 표시를 재검증한다. 완료 이력의 raw가 바뀌어도 차단한다.
- 일시 오류는 실패 종료 시각 기준 10·20·40·60분 간격(이후 60분), 연속 10회까지 재시도한다. 입력/코드 계약 오류는 즉시 차단한다. 강제 종료로 남은 RUNNING도 실패 예산에 포함한다.
- 입력 대기와 다른 실행의 잠금 경합은 실패 횟수에서 제외한다. 단계 실행은 기존 runner의 잠금·checkpoint·게시 계약을 그대로 사용한다.
- 전역 discovery 오류도 로컬과 가능한 경우 MinIO `_dispatcher` 상태/이벤트에 기록한다. 정상 판정 후에는 TICK_FINISHED와 종료 코드를 남긴다.
- 기존 timer는 변경하지 않았다. 기존 실행 스크립트가 같은 flock 안에서 수집 후 Curated를 순차 호출하며 수집 실패 시에도 전처리 대상을 확인한다. 진단 인자는 수집만 실행한다.
- `run-curated-retry.sh`는 같은 flock 아래 수집 없이 전처리 재시도 횟수만 초기화한다. 두 고정 이름의 orphan 정리도 공통 잠금 아래에서만 수행한다.
- 기존 ingest 이미지는 변경하지 않았다. 별도 Curated Dockerfile에 Python 3.12·Node 24·DuckDB/boto3를 구성했다. 코드 read-only, 작업 데이터 persistent bind, CPU 2 / RAM 4GiB / swap 0이다.
- systemd 전체 제한은 수집+전처리를 포함해 36시간으로 설정했다. 이는 초기 운영 설정이며 실제 전체 데이터로 검증한 처리 시간 보장이 아니다.

## 발견한 이슈와 해결
- 기존 수집 이미지에 Node가 없어 재사용만으로는 dependents 단계가 실행되지 않는다. 별도 전처리 런타임을 빌드하고 그 이미지에서 실제 6단계 합성 테스트를 실행했다.
- 디렉터리 정리 이후 curated requirements의 MinIO 상대 경로가 잘못 남아 있었다. `../../minio/requirements.txt`로 수정하고 이미지 빌드로 설치를 확인했다.
- 첫 테스트 명령에 존재하지 않는 `test_runner` 모듈명을 넣어 loader 오류가 발생했다. 실제 `test_orchestration_runner` 이름으로 수정 후 회귀 검증을 통과했다.
- 중단 횟수가 10회에 도달할 때 두 번 증가하지 않도록 차단 상태를 직접 기록하며, 테스트로 10회 상한을 확인했다.

## 검증 결과
- 기존 runner/weekly CLI/request/parent 최종 회귀: **27 tests 통과**. 실제 dispatcher 통합은 아래 컨테이너 검증에 포함한다.
- 기존 weekly 수집 테스트: **106 tests, 100 통과 / 외부 MinIO 등 6 skip**.
- 신규 전처리 이미지에서 `--network none --cpus 2 --memory 4g --memory-swap 4g`, 저장소 read-only로 테스트: **24 tests 모두 통과**.
  - dispatcher 상태·실패·재시도·로그 18개
  - 가짜 Docker/flock으로 실제 shell의 수집 실패 후 전처리, 진단 모드, 잠금 경합, 수동 재시도 5개
  - 실제 full baseline → weekly min 전처리 6단계 → 다음 tick skip 통합 1개
- Docker 이미지 빌드 성공. 기존 Docker/Spark 서비스는 건드리지 않았다.
- Compose는 임시 가짜 환경값과 `config --no-env-resolution --quiet`로 구조 검증 성공. 실제 자격증명/endpoint 검증을 뜻하지 않는다.
- Python compileall, CLI help, git diff --check 통과.
- 원래 작업 디렉터리의 기존 untracked 2개 파일은 그대로 보존했다. 작업은 `data/feat/S15P21A506-372-raw-to-curated-pipeline`에서 진행했다.

## 미실행 및 운영 조건
- 운영 서버 접속, systemd 설치·재시작, 실제 MinIO 게시, DB 적재, 실제 스냅샷 성능 측정은 하지 않았다.
- 배포 전에 기존 완료 baseline과 raw 운영 기록, persistent 디렉터리 권한/여유 용량을 확인해야 한다. 이 작업은 전체 데이터 처리 시간·디스크 상한을 보증하지 않는다.
- 한 호스트와 공통 wrapper/flock으로 실행한다. 컨테이너를 별도로 직접 띄우는 우회 경로나 다른 호스트의 동시 실행은 지원하지 않는다.
- 코드/입력/경로가 달라진 실행을 retry 옵션으로 덮어쓰지 않는다. 계약 변경과 과거 누락 회차의 backfill은 명시적으로 별도 처리해야 한다.
- 사용자 요청에 따라 weekly 수집·전처리 연결 변경을 커밋한다. 원격 push와 운영 배포는 별도다.
