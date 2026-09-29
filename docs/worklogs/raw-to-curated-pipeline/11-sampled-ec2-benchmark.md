# 패키지 1만 개 표본 EC2 비교

## 변경 범위와 작업 계획

전체 스냅샷 비교가 오래 걸려 사용자가 약 1만 개 표본으로 축소를 요청했다. 단위는 패키지이며 선택된 패키지의 버전은 함께 보존한다. 기존 운영 배포·수집·DB 적재는 변경하지 않는다. 기존 전체 실험 기록과 입력도 보존한다.

1. 이전에 고정한 실제 입력 manifest에서 결정적인 표본을 선정한다. 다운로드·역의존 대상이 비어 있는 무의미한 실험이 되지 않도록 대상 포함 여부를 기록한다.
2. raw와 중간 Curated 입력을 동일한 패키지 집합에 맞춰 줄인다. 저장소 데이터는 참조 관계로 포함한다. 역의존 수는 표본 내 importer만 계산하므로 전체 스냅샷 지표로 사용하지 않는다.
3. 동일 표본을 기존 방식과 실제 app/data 두 EC2 Spark에 제공한다. 입력 hash·단계별 건수·CPU·메모리·시간과 결과 일치를 기록한다.
4. sample-ec2-20260916-a1을 새 실험 디렉터리/MinIO 접두사로 사용한다. 준비 → Spark 두 노드 → 기존 방식 → 정확한 결과 비교를 백그라운드 실행한다.

## 유지하는 실행 조건

- 양 방식 합계 CPU 3, 컨테이너 RAM 7.5GiB, swap 0. Spark worker는 호스트마다 1 CPU/2.75GiB, executor heap 2GiB. driver 0.75 CPU/1.5GiB, master 0.25 CPU/0.5GiB.
- 입력 준비는 1 CPU/2GiB, 파일 전송 16MiB/s 제한. 표본 추출 시간은 계산 엔진 비교 시간에 포함하지 않는다.
- 서비스 보호 감시 유지. API 배포로 health 확인이 실패하면 실험이 중단될 수 있다는 기존 조건도 유지한다.
- 공식 Curated 게시와 DB 적재는 하지 않는다. 표본 성능을 전체 스냅샷 성능으로 단순 환산하지 않는다.

## 결과

구현·검증 및 실행 준비 중. 실제 표본 크기, 단계별 결과, 실측은 확인 후 추가한다.

## 실제 수행 기록
- 표본 추출기 구현: 대상 목록 합집합에서 해시 순서로 최대 5천 개를 우선 선택하고, 전체 패키지 목록에서 중복을 제외해 같은 순서로 1만 개를 채운다. 모든 버전/요구사항은 선택된 패키지 기준으로 보존하고 기존 ID를 사용한다.
- 다운로드 CSV/상태/날짜별 파일, 저장소의 모든 선택 raw URL에 연결되는 Projects, 스냅샷 통합 입력을 같은 표본으로 축소한다. 실제 표본 이름 SHA와 단계별 행 수를 기록한다.
- 표본용 snapshot 입력에 기존 검증기가 요구하는 interval/lineage/파일 목록을 명시했다. 원본 전체 실행용 입력을 그대로 완성된 표본 입력으로 간주하지 않는다. snapshot 입력 검증을 Spark 시작 전에 수행한다.
- 원천 manifest SHA256 4d5005e4c5cd4e7fa77df7b2ef736007c05b118dc7d5ca1b513b606335735713. 원천 파일의 크기와 SHA를 재검증한 뒤 표본을 추출한다.
- 관련 40개 테스트 통과. 선택 결정성/모든 버전 보존/이전 ID/변경된 원천 거부/공유 날짜 경로 보존을 포함한다. 실제 두 EC2 성능 결과와 결과 일치는 아직 미검증이다.
- 코드 ZIP SHA256 ad53b8f015be5d703fa590be08152731b8b46ef1876a158fbf64cd00e1d393c0, 양 호스트 검증 완료. data PID 2733165/app PID 1314088로 백그라운드 시작.
- 기존 본 작업 폴더는 변경하지 않았으며 원래 있던 untracked pipeline/duckdb_ui.py는 그대로다.

- 착수 확인: data RUNNING/prepare, app은 master 시작 대기 중. 양 호스트 서비스 guard 정상. 원천 해시 재검증/표본 추출은 준비 시간으로 별도 집계한다. 아직 Spark 계산 완료나 표본의 성능 우위를 주장하지 않는다.
- 실제 서버 로그 SAMPLE_SELECTED 10000 확인: 원천 검증과 1만 개 패키지 선정 통과. 현재 선택된 패키지의 raw/중간 파일 추출 중이다.

## 2026-09-16 13:18 KST executor 종료 진단
- app EC2 executor 0(04:13:36 UTC, exit 52), executor 2(04:16:35 UTC, exit 50)가 종료됐다. 두 stderr에서 `OutOfMemoryError: unable to create native thread`를 확인했다.
- app 실험 worker cgroup은 `pids.max=256`, `pids.events max=20`으로 프로세스/스레드 상한 도달이 확인됐다. 조회 시 `pids.current=101`. `memory.events`의 max/oom/oom_kill은 모두 0이고 컨테이너 OOMKilled=false다. JVM heap 부족이나 컨테이너 RAM OOM으로 단정하지 않는다.
- Spark가 app executor 3을 새로 시작해 작업을 이어갔다. 13:17 KST 기준 package_version 445.127초, downloads 46.712초, repository 113.823초 완료 로그 및 repository 출력 건수 검증을 확인했다. 다음 package_snapshot 단계가 진행 중이며 전체 결과 일치는 아직 미검증이다.
- 조회 시 운영 서비스 정상. 실행 조건은 변경하지 않았다. 이번 측정에는 executor 재시도 비용이 포함되므로 정상 조건의 성능 비교 결과로 확정하지 않는다. 후속 수정 시 app/data worker의 pids 제한 차이(app 256/data 512)를 검토하고 새 run으로 재측정해야 한다.

## 후속 상태 확인: 실행 종료
- data result.json은 FAILED. Spark 컨테이너는 2026-09-16 04:24:10 UTC(13:24:10 KST) exit 1, Spark 구간 1028.597초로 종료됐다. package_snapshot 17.386초 및 dependents 370.988초 완료 로그까지 있어 5개 계산 단계 완료 로그는 존재한다.
- 최종 요약 생성 시 이미 중지된 SparkContext의 applicationId를 조회해 AttributeError가 발생했다. cluster_benchmark_entry.py는 finally에서 Spark를 중지한 후 summary와 예외 기록에서 applicationId를 다시 조회한다. 기존 방식 및 최종 비교는 실행되지 않았다.
- 같은 시점 서비스 guard에도 data HTTPError/app ConnectionResetError가 기록됐다. 현 시점 운영 web/api/postgres는 최근 시작된 상태이며 healthy; 이 정보만으로 당시 연결 실패 원인을 확정하지 않는다.
- 양 호스트의 해당 실험 컨테이너는 모두 종료됐다. 현재 운영 MinIO/mlflow/web/api/postgres는 healthy. 본 확인에서는 재시작이나 설정 변경을 하지 않았다.
