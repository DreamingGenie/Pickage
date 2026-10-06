# 전처리·게시·DB 적재의 자원 상한과 실제 완료

## 사용자 요청과 완료 기준
- 현재 워크트리의 raw → Curated → MinIO → Spring PostgreSQL 적재를 실제 입력으로 끝까지 성공시킨다.
- 메모리 부족을 SQL/실행 구조에서 개선하며 작은 fixture 통과를 전체 성공으로 보고하지 않는다.
- 파이프라인 디스크 사용은 50GB 이하를 지키고 사용 후 정리한다. 기존 원천·사용자 중요 데이터·완료 결과를 임의 삭제하지 않는다. 영구 DB/MinIO 보존 데이터와 작업 중간 파일의 범위는 실제 크기 측정으로 구분하고 명확히 기록한다.
- 운영 서버 실행/변경은 이번 범위에서 제외한다. 배포 절차를 만들고 기존 모니터링을 수정하지 않고 상태/로그/자원 관측을 제공한다.
- 최신 origin/develop과 충돌 여부를 검증한다. 원래 워크트리의 브랜치/index를 변경하지 않는다.

## 시작 상태 (2026-09-22)
- 활성 브랜치: data/feat/S15P21A506-372-raw-to-curated-pipeline.
- 앞선 작업의 미커밋 변경은 보존한다. Jira 372 범위의 로컬 작업이며 기존 사용자 승인에 따라 별도 Jira API 갱신은 보류한다.
- C:/pg914r3의 8/31 DB 적재는 PUBLISHED. 9/14 weekly package_version 단계의 메타데이터 상속 SQL이 DuckDB 4GB에서 OOM.
- 이전 시도는 terminal FAILED이며 실행 상태/로그를 다시 확인하고 새 실행을 준비한다.

## 진행 순서
1. 실제 디스크·입출력·메모리 경로, develop 변경, 배포/모니터링 계약 확인.
2. 버전 상속의 전체 후보 곱을 제거하고 기존 결과 계약을 회귀 검증.
3. 작업 파일 중복을 줄이고 단계별 제한/안전한 정리/실패 복구 경로 구현.
4. Spring 로더도 전체 파일의 누적 다운로드/변환 보관을 줄이고 완료 이력 재사용.
5. 새 실행 ID와 고정 코드/입력으로 실제 9/14 전처리→MinIO→DB 실행. 디스크 최고 사용량과 메모리/시간 기록.
6. 실패하면 원인/수정/재검증을 반복하고 이미 완료된 결과는 안전하게 재사용.
7. 완료 상태·DB 결과·정리 결과·배포 설명·develop 호환성을 항목별 감사.

## 실측과 미완료
아직 이 목표의 전체 완료를 검증하지 않았다. 실측/변경/실패는 아래 또는 후속 연결 로그에 기록한다.

- 사용자 확인: 50GB는 임시 파일·다운로드 캐시·DB 중간 적재·WAL 등 처리 공간 합계. 영구 원천·최종 MinIO·서비스 DB 결과는 제외한다.
- 속도 개선도 명시적 요구. 불필요한 전체 탐색·중복 변환·완료 단계 재실행을 줄이고 단계별 시간을 기록한다. 프로그램의 내부 자원 측정은 60초 간격으로 남기되 에이전트가 실행을 자주 조회하지 않는다.
- DB 실측: 총 73GB, version 27GB, package 약4.7GB. 완료된 ETL staging version 33GB 등 중간 테이블이 큰 비중. WAL 약8.47GB.
- 최신 origin/develop 341f389를 fetch 후 merge-tree: deploy/prod/README.md, pipeline/minio/README.md 충돌 예상. 실제 병합 및 미커밋 내용 포함 검증은 아직 남아 있다.
- runtime/run_snapshot.py는 filesystem 사용량 및 cgroup 메모리, 실행 시간, 상태를 구조화 stdout에 기록한다. 운영 모니터링 설정은 변경하지 않는다.

## 2026-09-23 로컬 변경과 실제 실행
- 검증된 baseline MinIO의 52개 파일(13,439,167,210 bytes)을 GET SHA로 확인한 뒤, 실패/완료 실행에 소유된 중간 파일만 정리했다. 삭제 목록·보존 로그는 `C:/pg914r3/scratch-cleanup-result.json`, `cleanup-evidence-20260923-000717`에 남겼다. 삭제 파일의 논리 크기 합은 약201GB이며 hardlink가 있어 실제 확보 공간과 같다고 해석하지 않는다.
- PUBLISHED baseline 실행 외 staging 행과 활성 적재가 없음을 확인하고 4개 ETL staging 테이블을 TRUNCATE했다. 서비스 테이블과 receipt/실행 이력은 유지. DB 총 크기 73GB → 33GB. WAL은 8,472,494,080 bytes.
- weekly metadata는 기존 버전 직접 연결, 신규 버전만 ASOF 이전 후보 탐색을 사용한다. provenance는 직접 Parquet로 생성한다.
- transform의 eligible/matched_requirements/final_versions 전체 TABLE 사본을 제거했다. 최종 version Parquet를 먼저 기록하고 그 결과를 검증한다. 연결 종료 후 scratch DB를 삭제하고 master/changes 연결을 별도로 연다. weekly 입력/provenance는 같은 filesystem rename으로 게시 경로에 옮긴다. master 출력도 256MB shard를 사용한다.
- Spring은 PUBLISHED 사전 조회, 파일별 다운로드→변환→staging→파일 삭제, 성공 후 staging 정리를 적용했다. 파일 작업 예산은 10진수4GB(최대8GB)이며 DuckDB spill을 포함한다. PostgreSQL staging/WAL 전체 제한과는 구분한다.
- Linux runtime에서 curated/storage/metadata/workspace 32개 테스트가 통과했다(`C:/pgb1/linux-curated-tests.log`). backend 전체 unit 테스트, publisher integration 18개는 별도 테스트 DB에서 통과했다. 전체 orchestration Linux 테스트는 fixture 공간 설정을 조정해 추가 실행 중이며 아직 전체 통과로 기록하지 않는다.
- 전처리 ext4 loop image는 36,000,000,000 bytes hard cap을 사용한다. 실제 ENOSPC, uid/capability 축소, 종료 후 image 정리를 작은 fixture로 확인했다. PostgreSQL 별도42GB WAL/staging filesystem은 fresh fixture만 검증 중이며 기존 실DB에는 아직 적용하지 않았다.
- 00:24 KST 실제9/14 실행 `w914b1`을 시작했다. 코드 `C:/pgb1/src`, 입력 `C:/pgb1/request.json`, container `pickage-bounded-w914b1`. Docker8GiB/swap추가없음/CPU2, DuckDB4GB/총thread2/worker2. repository/dependents spill8GB.
- 전처리 시작 시 DB staging65,536 bytes+WAL8,472,494,080 bytes, 다른 활성 세션0 확인. 전처리 동안 DB적재를 동시에 실행하지 않는다. 36GB scratch와 기존 DB 처리 공간 합계는50GB미만이며 DB phase는 전처리 scratch 해제 후 별도 제한을 검증하고 시작한다.
- 상태 `C:/pgb1/status.json`, 로그 `C:/pgb1/pipeline.log`. 내부60초 자원 이벤트를 Docker log stream으로 받으므로 watcher가 반복조회하지 않는다. DB까지 완료한 상태가 아니며 전처리 종료 표시는 CURATED_COMPLETE로 구분한다.
- 미커밋 변경을 포함한 임시 index/tree의 develop 검사는 `56602ace7923841ee1cb73b6cfa5086f255ef7bb`를 사용했다. 충돌5개: deploy/prod/README.md, pipeline/minio/README.md, preprocessing/package_snapshot/README.md 및 develop의 downloads_reload.py/test_downloads_reload.py 위치 이동. 실제 브랜치/index는 병합하지 않았다.
- 후속 검증: Linux orchestration 전체106개 통과(294.971초), 로그 `C:/pgb1/linux-orchestration.log`. 제한된 테스트용 filesystem에 맞춰 fixture spill을128MB로 명시했으며 실제 처리 계약은 유지했다.
- DB 품질 이력에서 dependency SQL NULL→기본 JSON 변환과 dependents NULL 제외를 서로 분리했다. 각각 사유·건수를 기록하고 입력 checksum을 유지한다. 상세 JSONL의 임시 쓰기도 디스크 예산에 포함한다.
- WAL/staging hard cap42GB의 fresh PostgreSQL fixture에서 실제 ENOSPC와 재시작 후 커밋 행 보존을 확인했다. 기존 PGDATA의 clean shutdown→WAL 전체SHA검증 복사→원본backup 보존→새runtimeCHECKPOINT/행보존도 freshfixture로 확인했다. `C:/pgb1/postgres-import-test-v2.log`.
- loader 자체도4GB ext4 scratch,8GiB container/512MiB Javaheap/4GB nativeDuckDB 제한으로 분리했다. 실제 baseline 대상으로 `SKIPPED`(DB조회약0.62초)를 확인했고 download 없이 끝났다. 종료 후 scratch.ext4 부재 확인. `C:/pgb1/loader-skip.log`.
- `C:/pgb1/continue.py`는 docker wait로 전처리 종료를 기다린다. 성공 시에만 고정된 로컬15441 실험DB를 WAL/staging 제한 runtime으로 옮긴 뒤9/14적재를 시작한다. 다른 사용자/운영DB에는 접근하지 않는다. WAL복사본은SHA검증·새DB기동·baseline확인·새DBCHECKPOINT 이후에만정리한다. 실패 시 기존컨테이너를 무조건 재시작하면 WAL경로가 달라져 위험하므로 새volume/원본backup을 유지하고 오류로 멈춘다.
- 전체상태 `C:/pgb1/flow-status.json`, 전처리상태 `C:/pgb1/status.json`, 처리공간측정 `flow-resources.jsonl`. `powershell -File C:/pgb1/status.ps1`로 함께 확인한다. 60초 표본의최고치와filesystem상한을 구분한다. 최종실DB적재 성공은 아직미확인이다.

## w914b1 실패 확인과 후속 수정
- 실제 실행은 1,251.71초 후 FAILED. snapshot 단계 완료 후 package_version의 `weekly_metadata.prepare_versions` 최종 wide COPY에서 DuckDB spill 16.9GiB 상한에 도달했다. Docker `OOMKilled=false`, ExitCode=1로 컨테이너 메모리 강제 종료와 구분한다.
- metadata 단계 시작 기준 validate 약36초, eligible parent 구성 약53초, 신규 후보 구성 약101초. 이후 전체 버전·부모 메타데이터를 한 번에 조인해 출력하던 쿼리가 실패했다.
- scratch 표본 최고치는27,210,686,464 bytes. 별도 DB WAL/staging 약8.47GB와 합쳐 약35.69GB이며 실행 전체 순간 최고값을 의미하지 않는다. filesystem hard cap36GB는 유지한다.
- 자동 후속 실행은 `Curated exited 1; no DB changes attempted`로 멈췄다. DB 이전/적재는 실행하지 않았다. 종료 후 전처리 전용 volume에 `.lock`과 `OWNER_UUID`만 남고 scratch.ext4가 삭제된 것을 확인했다.
- 다음 수정은 넓은 metadata 조인의 양쪽 입력을 분할하고 모든 shard를 build/publish에 연결한다. 입력 검증 계약을 유지하면서 다운로드 병렬화와 DuckDB 연결 재사용을 검토한다. 변경 코드에는 새 run ID와 새 고정 source를 사용한다.

## w914b2 준비: 처리량과 임시공간 개선
- 입력 hydration은 요청의 workers 수로 다운로드를 병렬화한다. 각 파일 SHA/크기 검증은 유지하고 schema 검사 연결을 재사용한다. materialize는 기존 hardlink 경로를 유지하므로 cache와 입력 경로의 논리 크기를 물리 사용량에 이중 합산하지 않는다.
- metadata의 exact version 분류를 한 번 compressed Parquet로 기록한 뒤 재사용한다. 신규 후보만 ASOF로 찾고, 후보 lookup table은 사용 직후 제거한다. 최대16개 bucket으로 양쪽 metadata 입력을 제한하고 provenance는 narrow projection 한 번으로 생성한다.
- 6,000행·4 bucket fixture의 실제 EXPLAIN ANALYZE에서 한 bucket의 current1,530행, exact parent1,020행, source510행으로 제한됨을 확인했다. 모든 bucket 출력 합은6,000행. `C:/pgb2/metadata-bucket-plan.json`, `metadata-explain.log`에 증거를 저장했다.
- build는 metadata/weekly output의 모든 shard를 rename으로 연결한다. 강제로 여러 shard를 만든 회귀 테스트에서 버전·provenance 전체 행을 확인했다.
- requirements JSON의 전체 DuckDB TABLE 저장을 없애고 package name hash별 compressed Parquet로 분할한다. final version의 wide join은 해당 requirements partition만 읽고 output shard를 rename한다. NULL/invalid/missing 의존성 의미와 품질 행은 유지하며, 검증 후 임시 partition을 제거한다.
- changes는 동일 raw 값의 행을 먼저 제외한 materialized 후보에만 JSON 의미 비교를 수행한다. 양쪽 input을 동일 identity bucket으로 제한하고 후보 table은 각 bucket 직후 제거한다. 객체 key 순서 무시·배열 순서와 중복 보존 정책을 유지한다. 최종 파일 SHA는 streaming으로 계산한다.
- MinIO 전송 경로 실험: 동일한64MiB 구간을 Docker 내부와 Windows host port 경유로 읽었다. 첫회 host2.979초/native0.029초, 역순 재검사 native0.032초/host2.700초. 작은 cached 구간의 읽기 실험으로 전체 pipeline 가속률과 같다고 해석하지 않는다. 증거 `C:/pgb2/minio-path-native.json`, `minio-path-host.json`.
- 후속 실제 실행은 전용 local Docker network로 MinIO와 PostgreSQL에 접근해 Windows port forwarding을 우회한다. 기존 local MinIO의 공개 port/volume/image는 유지하고 운영 서버는 변경하지 않는다.
- 고정 코드 `C:/pgb2/src` 517파일,4,286,568bytes; run ID `w914b2`. 아직 실제 실행 전이며 Linux 전체 orchestration 검증이 끝난 뒤 시작한다. Linux curated33개 테스트는7.61초에 통과했다.
- Linux orchestration108개 중103개는 고정 pipeline source로 통과했다. deployment5개는 test container에 deploy shell 파일이 없어 실패했으므로 해당 디렉터리를 포함해 별도 재실행하여5개 모두 통과했다. 초기 실패 로그와 수정된 환경 검증 로그를 각각 `linux-orchestration.log`, `linux-weekly-deployment.log`로 보존한다.
- 미커밋 변경 포함 develop 재검사 결과 충돌은 기존5개로 유지됐다. 원격 develop341f389, 임시 effective commit32306b6, 증거 `C:/pgb2/develop-compat.json`. 현재 브랜치와 실제 index에는 병합하지 않았다.
- 2026-09-23 01:09:52 KST `w914b2` 실제 실행 시작. container `pickage-bounded-w914b2`, code/request는 `C:/pgb2` 아래 고정했다. 전용 local network `pickage-bounded-local`에 local실험MinIO를 추가 연결해 내부 endpoint를 사용하며, 기존 공개 port와 저장 volume은 유지했다.
- host watcher PID15432, 자동 DB 후속 실행 PID35360. `docker logs --follow`와 `docker wait`를 사용하며 agent의 반복 조회 없이 status/log/resource 파일을 갱신한다. 상태 명령 `powershell -File C:/pgb2/status.ps1`. 실DB PUBLISHED 및 전체 처리공간 최고값은 실행 완료 후 검증할 항목으로 남아 있다.
- 시작 후 최초 확인에서 `RUNNING/package_version`, error없음. 입력 준비+snapshot 전환은 기존 약777초에서 이번 약36초로 단축됐다. 동일 고정 입력을 처리한 실제 실행 관측이며 캐시 상태까지 통제한 벤치마크는 아니다. 60초 표본의 scratch17,200,218,112bytes, DB적재는 아직 WAIT_CURATED이다.
- PostgreSQL runtime 재시작 결함을 수정했다. 최초 offline WAL 이전 후 같은 컨테이너를 재시작하면 남아 있는 `POSTGRES_IMPORT_MODE=offline` 때문에 이미 symlink인 WAL을 다시 이전하려 했다. 이제 정확한 bounded WAL symlink는 재사용하고 다른 위치는 거부한다. fresh fixture에서 최초 기동과 같은 컨테이너 재시작 후 모두 `1|v3-row`를 확인했다(`C:/pgb2/postgres-restart-v3.log`). 실제 9/14 DB 적재 완료 검증과는 별개다.
- 01:19:05 KST 전처리를 잠깐 pause하고 WAIT_CURATED인 host controller만 교체한 뒤 즉시 unpause했다. 전처리 코드/실행 ID/입력은 유지했다. 새 controller PID46608은 검증한 PostgreSQL image `sha256:121e1fd61aa94570d27eb79a52b12354e40a4937179ec69bb825b2be38d3fc94`를 사용한다. `controller-replacement.json`에 이전/새 PID를 보존하고 시작 시간·처리공간 표본 최고치는 최초 실행부터 이어 계산한다. 교체 후 WAIT_CURATED 및 오류 로그 부재 확인.
- 재시작 회귀를 `runtime/test_postgres_restart.py`로 보존했다. 동일 컨테이너 재시작 후 행 보존, WAL 경로, staging이 비어 있지 않으면 설정 거부, 4개 staging 테이블과 4개 PK 인덱스의 bounded tablespace, 새 연결의 temp 설정을 검사한다. 임의 이름과 소유 label의 fixture만 생성·정리한다. 초기 fixture 대기에서 exit137이 발생한 기록은 보존하며, 해당 실행은 OOM 여부를 확정하지 않았다. 공식 이미지 entrypoint의 초기화용 서버는 TCP를 열지 않으므로 readiness를 TCP로 바꿔 초기화 완료 전 접근을 방지했다. 최종 검증 PASS, `C:/pgb2/postgres-restart-regression-tcp.log`.
- `runtime/configure_bounded_staging.sql`과 문서에 WAL뿐 아니라 staging 테이블·인덱스·SQL 임시 파일도 bounded filesystem으로 보내는 필수 절차를 추가했다. 기존 staged load는 자동 삭제하지 않고 거부한다. 현재 실행의 고정 controller SQL과 frozen preprocessing source는 교체하지 않았다.
- 실제 w914b2 metadata는 16개 출력 bucket을 459.511초에 끝내고 provenance까지 495.797초에 완료했다. 이전 w914b1 실패 구간을 통과한 증거이며 전체 package_version 완료를 의미하지 않는다. 840초 표본에서는 transform의 declared dependency JSON 생성 중, scratch28,873,228,288bytes, Docker OOMKilled=false였다. 전체 Curated 게시·9/14 DB PUBLISHED·최종 정리 검증은 여전히 진행 중이다.

## w914b2 ENOSPC 및 입력 조인 분할 수정
- w914b2는 908.84초에 requirements JSON COPY 중 `No space left on device`로 종료했다. 메모리 강제 종료가 아니며 Docker OOMKilled=false/ExitCode1. 36GB 전처리 filesystem이 상한을 강제했고 마지막 900초 표본은34,621,423,616bytes였다. 표본은 순간 최고값을 대신하지 않는다. controller는 DB 이전/적재 전에 FAILED로 멈췄다. scratch.ext4 제거 및 소유 marker/lock만 남은 것을 확인했다.
- 원인은 출력 Parquet만 PARTITION_BY로 나누고, 그 앞의 requirements↔전체 eligible version semijoin은 한 번에 수행한 데 있다. 수정은 hash(Name)으로 조인 양쪽 입력을 먼저 제한하고, 각 묶음에서 requirements 생성→version 생성→quality 검증/출력→requirements 임시 파일 삭제를 끝낸 다음 다음 묶음으로 이동한다.
- NULL/빈 배열/누락/invalid requirements, 중복 키 거부, 단일·다중 bucket의 전체 report/행 일치, 임시파일 제거를 회귀 검증했다. transform13개와 weekly build1개 통과(`C:/pgb2/transform-input-buckets-final.log`).
- 별도10만 버전 fixture, DuckDB256MB/2threads/10bucket의 EXPLAIN ANALYZE에서 semijoin의 양쪽 입력은 각9,520~10,420행으로 제한됐다. 전체 출력100,000행, 완료 후 requirements 임시 디렉터리0개. fixture1.25초는 실제 전체 데이터 예상 시간이 아니다. 증거 `C:/pgb3/join-probe/result.json`, `plans.json`.
- 다음 실행은 새 ID w914b3와 새 고정 코드를 사용한다. 추가로 누적 master 생성의 현재 결과 전체 복사를 hardlink로 대체하고, 이전에만 존재하는 행의 조인도 분할해 transform 이후 디스크 중복을 줄인다. 원본 MinIO/서비스 DB/이전 실행 증거는 보존한다.
- master는 현재 파일을 같은 filesystem의 hardlink로 연결하고 이전에만 있는 행만 양쪽 입력을 분할한 anti join으로 생성한다. 복합 버전 키, 현재 행 우선, 이전 누락 행 유지, 작은따옴표 경로, 원본 이름 제거 후 hardlink 유지 테스트를 통과했다. missing 출력도256MB shard를 유지하고 copy fallback은 허용하지 않는다.
- 새 frozen source520파일/4,334,850bytes로 Linux curated39개(8.767초), weekly build/integration2개(21.932초)가 통과했다. 로그 `C:/pgb3/linux-curated.log`, `linux-weekly-integration.log`. 이번 변경 대상 밖의 backend 및 전체 orchestration 테스트를 불필요하게 반복하지 않았다.
- 2026-09-23 01:35:26 KST 실제 재실행 w914b3 시작. 컨테이너 `pickage-bounded-w914b3`, 소스·요청·기록은 `C:/pgb3`. 전처리8GiB/2CPU/DuckDB4GB/36GB scratch 한도는 유지한다. watcher PID52208, controller PID48880. 새 controller는 최초 launch timestamp를 기록한 뒤 시작해 파일 생성 순서 경합을 제거했다. WAIT_CURATED의 DB 처리공간도 이번 실행 직전 실측값을 사용한다.
- 진행 확인 명령은 `powershell -File C:/pgb3/status.ps1`. 전처리/자동 DB 후속의 완료 이벤트를 기다리며, 전체 DB PUBLISHED와 최종 정리가 확인되기 전까지 목표는 미완료다.
- w914b3 첫 시작은 Python 실행 전 `losetup ... No such file or directory`로0.7초 내 종료했다. Docker private `/dev`에는 커널이 새로 할당한 loop node가 없을 수 있었다. 별도로 강제 삭제한 과거 PostgreSQL fixture의512MiB 이미지8개가 deleted backing inode 연결로 남아 있었다. 이8개는 기기명·inode·삭제 상태·크기가 일치하는지 재검사한 뒤 연결만 해제했다. Docker 시스템 loop0/1 및 서비스 컨테이너는 유지했다. 증거 `C:/pgb3/stale-fixture-loop-cleanup.json`.
- runtime은 필요한 free loop node만 생성하고 `mount -t ext4 -o loop,discard`로 AUTOCLEAR 연결을 사용한다. unmount 후 기기명으로 다시 detach하면 다른 실행이 재사용한 장치를 건드릴 수 있어 제거했다. 문서 근거 [util-linux umount](https://www.man7.org/linux/man-pages/man8/umount.8.html)의 loop lifecycle과 로컬 동적 테스트를 함께 확인했다.
- 전처리/loader v4 이미지 각각에서 없는 loop node를 재생성하고 uid1000 child의64MiB ENOSPC를 확인한 뒤 scratch image 제거까지 검증했다(`workspace-autoclear-smoke.log`, `loader-autoclear-smoke.log`). PostgreSQL v4는 이전/재시작/행 보존/8개 staging 관계 배치/임시공간 설정 외에 AUTOCLEAR=true와 강제 컨테이너 제거 후 동일 backing inode 연결 소멸까지 검증했다(`postgres-autoclear-final.log`). 단순 exit137을 OOM으로 단정하지 않는다.
- 첫 시작의 코드 목록·receipt·상태·로그는 `C:/pgb3/startup-failed-*`로 보존했다. Python/MinIO 요청이 시작되기 전 실패였으므로 동일 w914b3를 유지하고 terminal 컨테이너만 교체했다. 01:43:13 KST 실제 재시작, 새 컨테이너 ID3c60be7229a9, watcher PID37208/controller PID48592. 고정 source520파일/4,337,455bytes. 전처리 image53f6310b82eb, PostgreSQL26f9281a4a19, loaderbeec622bd79b로 모두 pin했다. 실행 자원·입력·변환 정책은 유지했다.
- 재시작 후 Docker 종료 대기로 기다렸다. 1,320초 표본에서 RUNNING/package_version, Docker OOMKilled=false, scratch24,254,398,464bytes. metadata는489.156초 완료, transform16개 bucket 중6개 완료였다. 실제 bucket당 requirements86.102~88.288초, version12.705~13.237초, quality4.916~5.338초. 이전 ENOSPC 구간을 분할하여 진행 중인 증거이며 남은 bucket/누적 master/후속 단계/DB의 성공을 대신하지 않는다. 전처리와 별도 DB WAL/staging을 합산하는 controller도 WAIT_CURATED 정상 상태다.
- 배포 안내를 현재 운영 경로와 검증된 로컬 bounded 실행으로 구분했다. 기존 timer/dispatcher·모니터링 설정은 그대로이며, 운영 전환에는 bounded 요청 전달과 전처리 scratch 해제 후 DB 적재 순서가 필요하다. Spring mode=once의 정확한 prefix/SHA, DB PUBLISHED 확인, PostgreSQL 예시의 사용자/DB 설정을 보완했다. 서버에는 접속하거나 배포하지 않았다.
- DB 인계의 독립 검토에서 고정된 과거 WAL 값 사용, df 실패 시0 처리, PUBLISHED 상태만 보는 검사를 보완했다. 전처리 watcher는 유지하고 WAIT_CURATED의 후속 controller만 교체했다. 이제 기존 DB WAL/staging을60초마다 실제 조회하고, df 불가 시 hard cap 전체를 예약하며, scratch image 부재 확인 후에만0으로 처리한다. 최종 검사는 dataset/snapshot/run/prefix/SHA, active attempt, current pointer, expected=actual counts, error_message 없음까지 확인한다. 실패 시 PGDATA/WAL 보존과 재기동 주의를 담은 recovery-required.json을 남긴다.
- offline WAL 복사 중42GB destination cap+기존 약8.47GB backup을 동시에 허용하면 최대 예약이50GB를 넘는다. PostgreSQL runtime에42GB 이하의 정상 BOUNDED_POSTGRES_BYTES 설정을 추가하고 이번 실행은40GB로 고정했다. clean shutdown 이후 WAL을 재측정한 뒤 destination40GB+backup+호스트파일+0.5GB여유가50GB 미만인지 검사하고, 원본 backup 삭제 직전에도 측정한다. 실제 filesystem을40GB로 제한하며 순간 표본만으로 최대 공간을 보장했다고 주장하지 않는다.
- v5 PostgreSQL 이미지 bfe0eb862e4d에서536,870,912byte fixture 설정, 이전/재시작 행 보존, staging8개 관계 배치, AUTOCLEAR 및 강제 제거 후 loop 해제를 모두 통과했다(`C:/pgb3/postgres-v5-regression.log`). controller resource 회귀5개도 통과했다(`C:/pgb3/test_controller.py`). 전처리/loader 이미지는 v4를 유지한다.
- 02:23:01 KST controller v2 PID13084로 재시작했다. 전처리 컨테이너와 고정 입력/코드는 변경하지 않았다. 증거 `C:/pgb3/controller-v2-receipt.json`, `flow-controller-v2.out/err`. 실제 PostgreSQL 적재는 아직 시작하지 않았다.
- 02:25 KST origin/develop을 다시 fetch했다. 최신 b255619b8aeca627523a72a5a1a086ff362d559e와 현재 미커밋 변경을 포함한 임시 tree90cecf69ca09afc215ebd06ce4ab4410c0021f90를 merge-tree로 검사했다. 충돌은 기존과 같은 문서3개와 downloads_reload.py/test_downloads_reload.py의 위치 이동2개다. 실제 HEAD/index hash 보존을 검증했으며 실제 병합은 하지 않았다. 증거 `C:/pgb3/develop-compat-v3.json`.
- 운영 관측 경로를 저장소 설정으로 확인했다. 기존 systemd journal, 고정 컨테이너명, MinIO 상태/이벤트를 통한 연결 조건을 runtime README에 기록했다. 저장소 밖 서버 대시보드의 자동 발견 여부는 미확인이며, 로컬 stdout 생성만으로 서버 모니터링 연동 완료를 주장하지 않는다.
- w914b3는 총3,744.47초 후 repository에서 실패했다. Docker OOMKilled=false. 패키지·버전 단계3,648.998초, downloads18.383초는 완료·게시됐다. 54,982,736개 버전/11,312,204개 패키지와 변경분 package242,856행/version1,186,870행이 생성됐다. package-version manifest SHA6913f8ff59ca0f25301889cabbe6407f47b6fd9c0bb5e48f20592371b6550f3f, downloads SHA1bbaa77ae22bd081004b199932fd9b5e57ceb60f4acd0f8def6b1ede99998c6d.
- repository는4개 전체 입력을 TEMP TABLE로 복사하고 타임스탬프 변환용 전체 version TABLE을 다시 만들다가8GB spill 제한에 걸렸다. URL 정규화도4096개마다 전체 matched를 다시 DISTINCT/정렬하는 구조였다. 다음 수정은 입력 VIEW, 패키지 묶음 단위 조인/선택/출력/해제, URL목록1회 순차 처리로 이 두 비용을 줄인다.
- generic runner는 코드 변경 후 같은 run ID를 엄격하게 거부하므로 이를 우회해 envelope를 덮어쓰지 않는다. 원본 producer manifest·checkpoint를 그대로 보존하고 변경허용 파일/기존checkpoint SHA/실행환경을 검증하는 명시적 repository recovery entry를 추가해 완료3단계를 재사용한다. 별도 recovery receipt에 구·신 코드와 복구기 SHA를 기록한다. 새 로컬 증거 C:/pgb4, 논리 입력 w914b3 유지, 원래 C:/pgb3 보존. 실제 복구 실행은 수정·검증 이후에 시작한다.
- repository 입력/타임스탬프 정규화를 VIEW로 바꾸고, URL DISTINCT를 한 번 순차 처리하며, 최대16개 패키지 묶음별로 조인·검증·출력·임시 관계 해제를 수행하도록 수정했다. 전체 입력 키/FK/충돌 검증과6개 출력 계약은 유지한다. Projects 입력은 후속 package_snapshot이 사용하므로 그 단계가 끝난 뒤 해제하도록 workspace 수명도 수정했다.
- frozen source550개를 사용한 Linux 회귀19개가17.028초에 통과했다(`C:/pgb4/linux-recovery-tests.log`). 원래 실행의 처음3단계를 FakeS3에서 완료한 후 실패→명시적 복구→재시도→완료→재실행까지 검증하고 원본 envelope/checkpoint 바이트 보존과 결과 재사용을 확인했다. 복구 허용 변경은 repository 변환과 workspace 두 파일이며 실행환경/원본 checkpoint SHA/복구기 자체 SHA를 별도로 고정한다.
- 기존 frozen 코드와 새 코드의1,000행 fixture에서6개 출력의 전체 행·스키마·report가 일치했다. 별도200만 버전/2만 패키지, DuckDB128MB/2threads/spill256MB fixture에서 기존 코드는255,819,776bytes spill에서 실패했고 새 코드는4.64초에 완료, 표본 spill0이었다. 기존 코드가 완료하지 않았으므로 속도 배수로 해석하지 않는다. 실제 전체 입력 성능은 후속 실행에서 측정한다. 증거 `C:/pgb4/repository-probe-result.json`.
- 로컬 controller는 watcher의 최초 STARTING 기록에 아직 사용량이 없을 때도36GB 전체를 예약한다. 최초 상태파일 생성 순서에 의존하던 경합을 제거했고 controller 회귀6개가 통과했다. 기존 실패 컨테이너의 scratch.ext4 부재를 다시 확인했다. 전처리/DB 후속은 docker wait로 연결하고60초 자원 기록만 자동 수행한다.
- 2026-09-23 03:03:37 KST `pickage-bounded-w914b3-recovery1`을 시작했다(container4762aeb751c1, watcher48900/controller50232). 원래 w914b3 요청과 입력을 유지한다. 첫 측정 전 전체 scratch 한도를 예약한 합산 상한은45,151,533,750bytes였으며 WAIT_CURATED 정상 기동을 확인했다. 상태는 `powershell -File C:/pgb4/status.ps1`로 조회한다. 실제 전체 성공 여부는 전처리 종료 및 DB PUBLISHED 이후 확인한다.
- 실제 repository는03:04:19~03:11:33 KST,433.841초에 검증·게시·체크포인트 기록까지 완료했다. 원래 패키지/버전·downloads 산출물은 재계산하지 않았고 snapshot은0.452초에 게시 파일을 복원했다. 이후 package_snapshot을 시작했다. 이 결과는 repository의 전체 데이터 성공 증거이며 DB 완료를 뜻하지 않는다. `C:/pgb4/wait_stage.py`는 Docker log stream의 단계 전환 이벤트만 기다리도록 구성했다.
- 복구기 독립 검토에서 경로 경계와 게시 직전 원본 checkpoint 재검증을 보강했다. 저장소 코드에는 snapshot metadata/실제 inventory 경로의 workspace 밖·symlink 접근 거부, 실행 도중 checkpoint 바이트 변경 시 bundle 게시 차단을 추가했다. 실제 진행 중인 frozen source와 receipt는 변경하지 않았다. 별도 read-only 증거 `C:/pgb4/recovery-prepublication-proof.json`으로 실제 원본 metadata가 소유 경로 안이고 checkpoint/frozen source가 그대로임을 확인했으며 완료 후 다시 검증한다.
- 강화된 복구기는 Linux8개 테스트가21.718초에 통과했다(`C:/pgb4/recovery-hardening-linux-final.log`). 실행 중 checkpoint 변경→_SUCCESS/manifest 미게시, dangling symlink 거부, inventory 경로 이탈 거부, footer 불일치 시mtime 미변경, 실제 fixture 실패/재시도/완료/재생을 검증했다. 최초512MiB test tmpfs는 fixture의1GB spill 사전조건보다 작아 실패했으며2GiB test tmpfs로 수정했다. 실제 실행의 자원 설정이나 코드 변경으로 해석하지 않는다. helper SHA pin은 유지하므로 현재 복구의 재시도는 C:/pgb4/src의 원래 frozen helper를 사용해야 한다.
- 실제 package_snapshot은03:11:33~03:18:15 KST,401.932초에 완료하고 dependents를 시작했다. 메모리 표본이8GiB에 근접했지만 cgroup 파일 cache를 포함하는 값이며, 이 단계는 종료 오류 없이 완료됐다. 추가 source 수정으로 진행 중인 실행을 바꾸지 않는다.
- 03:23:15 KST recovery1이 dependents 입력 준비 중 실패했다(전체1,178.238초, Docker exit1/OOMKilled=false). `historical_input.build_populations`의 `CREATE TABLE source_population`에서 DuckDB8GB spill을 소진했다. repository와package_snapshot은 정상 게시된5개 앞 단계에 포함되어 보존된다. scratch 표본 최고25,548,230,656bytes, 종료 후scratch.ext4 부재를 확인했다. DB 후속 controller는 WAIT_CURATED에서 멈춰 DB 이전/적재를 수행하지 않았다.
- 다음 수정 범위는 dependents 입력 준비의 전체 데이터 중복 저장/전역 조인 비용 축소다. 별도 dependents 복구 receipt는 기존 repository 복구 receipt와 완료5단계 SHA를 고정하고 dependents만 재실행하도록 준비한다. 전체 입력·버전 의미/NULL 정책을 바꾸거나 단순 spill 한도 증가로 처리하지 않는다.
- dependents 준비에서 version_basis 전체 저장 사본을 VIEW로 바꾸고, requirements 조인은 의존성 배열 대신 NULL 여부/개수 등 scalar projection만 전달하도록 수정했다. 사용이 끝난 version_birth/all_target_population/source_population도 해제한다. declaration 원래 배열 index와 selected_names 관계형 조인은 유지한다. 검토 중 발견한 배열 사전 필터의 index 재번호 문제를 회귀 테스트로 고정했고, MAP membership을 O(1)로 가정한 최적화는 채택하지 않았다. 로컬2,000회 부재 키 조회가10,000key0.016초→100,000key0.125초로 증가하는 실측을 확인했다(`C:/pgb5/map_probe.py`).
- population 기존 frozen 코드/새 코드의1,000행에서 source_population·target_population·snapshot_population 전체 행과 schema/statistics가 일치했다. 200만 버전/40만 패키지/8,000만 선언수 fixture를128MB memory/256MB spill/2threads로 실행했을 때 기존 코드가 spill 부족으로 실패했고 새 코드가4.923초에 완료했다(표본spill242,778,112bytes). 작은 fixture 속도는 실제 데이터 소요시간으로 환산하지 않는다. 별도512MB 조건에서는 둘 다 통과했으며4.551초/4.241초였다. 증거 `C:/pgb5/population-probe128-result.json`, `population-probe-result.json`.
- tail recovery는 원래 request/envelope, repository-bounded-v1 receipt, 완료5개checkpoint SHA, 신규dependents 코드와복구기 SHA를 별도로 고정한다. 기존3단계/repository/package_snapshot을 재실행하지 않고 dependents 입력만 다시 받는다. parent 검증에서 helper 과거hash=현재hash 비교를 제거하고 역사증거와 현재 실행코드를 구분했다. 실제 FakeS3 원본실행 실패→repository복구→dependents실패→tail재시도→게시중단→완료replay 및 원본5checkpoint 바이트보존/current포인터/상태복구를 확인했다(Windows4개7.075초). Linux frozen검증과 실제재실행은 후속 기록에서 구분한다.
- 새 frozen source552파일/5,245,204bytes로 Linux26개 테스트가83.022초에 통과했다(`C:/pgb5/frozen-tests.log`). 실제 병렬 worker 프로세스와 전체 역사 population14개, weekly 병렬 oracle8개, tail recovery4개를 포함한다. 첫 테스트 wrapper의 main guard 누락으로 spawn child가 테스트를 재실행해 process group 오류가 났으며 wrapper에 main guard를 넣어 해결했다. 제품 worker/runtime 코드의 오류로 분류하지 않는다. 일반 git diff --check도 통과했다.
- 2026-09-23 03:40:49 KST dependents만 재실행하는 recovery2를 시작했다. container `pickage-bounded-w914b3-recovery2`(660c48511e80), watcher32276/controller4832, 증거 `C:/pgb5`. 원래 request/run ID/8GiB container/4GB DuckDB/2CPU/8GB spill/36GB scratch를 유지한다. 앞5단계를 재계산하지 않는다. 기존 사용자 명령 `powershell -File C:/pgb4/status.ps1`은 새 `C:/pgb5/status.ps1`로 연결하고 이전 viewer는status-recovery1.ps1로 보존했다. 실제 DB 성공은 아직 확인 전이다.
- recovery2는03:45:17 KST,267.04초 후 global `CREATE TABLE version_birth`에서8GB spill을 소진해 실패했다. Docker OOMKilled=false, scratch 표본최고17,046,446,080bytes. scalar projection/VIEW만으로 전체5,498만 버전 조인을 충분히 제한하지 못했다. 표본 통과를 전체 성공으로 취급하지 않는다. 종료 후scratch.ext4 부재 확인, DB 이전/적재 없음.
- 다음 수정은 weekly dependents 준비 입력을 hash(name)으로 나누고 각 묶음의 조인·출력을 끝낸 뒤 임시 데이터를 해제하는 방식이다. 기존 전체 importers/version 의미와 배열 원래 index·품질/합계 검증을 유지한다. 실패한dependents-bounded-v1 receipt는 고치지 않고 새v2 receipt로 같은 앞5단계 증거를 참조한다. 새 증거디렉터리C:/pgb6만 준비했으며 실제시작은 검증 후 기록한다.

## dependents 입력 준비·최종 출력 개선 검증
- weekly 입력 준비를 패키지 이름 hash 기준 최대16개 bucket으로 나눴다. 모든 importers/version 의미, 원래 declaration index, raw release/date provenance, prerelease/invalid target 제외, NULL 및 source gaps 통계는 유지한다. 버전 문자열 분류는 전체에서 한 번만 수행한다.
- 기존 C:/pgb4 frozen adapter와 새 adapter의 입력 준비 전체(physical128분할 파일 작성·전역 input verifier 포함)를 비교했다. 작은2,000버전 fixture는4개 prepared table의 schema/전체행/통계/source gaps가 일치했다. 60만패키지·240만버전·1,821만유효 선언수 fixture에서는 schema/행수/통계/source gaps가 일치하고, 같은2threads·DuckDB256MB·spill512MB 조건에서 기존19.425초→신규10.965초(약43.6%단축)였다. 대규모 행 전체 비교와 실제55m입력 속도 보장으로 해석하지 않는다. 증거 C:/pgb6/preparation-probe-result.json.
- 첫 probe wrapper는 임시 검사 디렉터리를64MB /tmp에 두어 실패했다. 테스트용TMPDIR/tempfile을8GB한도 안으로 옮긴 후 재검증했다. 제품 실제 runtime은 원래 bounded workspace 임시경로를 사용한다. probe fixture 소유 container/volume만 종료·정리했다.
- dependents v2 복구는 게시 직전 앞5개 descriptor의 실제 manifest/출력 SHA도 다시 확인한다. 실행 중 retained manifest가 바뀌면 _SUCCESS 게시를 막고, 원상복구 후 이미 완료한 dependents checkpoint를 재사용하는 회귀를 추가했다. 전용4개 테스트7.309초 통과.
- 아직 recovery3 실제 실행과 DB 적재는 시작하지 않았다. 최종 출력 bucket 개선, frozen Linux 회귀와 검토를 마친 뒤 같은 원래요청으로 재개한다.
- 중간 frozen검증552파일/5,257,546bytes에서 Linux26개 회귀가84.399초 통과했다. 이후8/31실제증거에서 선언239,556,025건·lookup4,220,751건을 확인했다. 당시 검증은4GB메모리이지만100GBspill을 허용했으므로 이번8GBspill성공의 증거로 사용할 수 없다. 이를 근거로 source identity 중복/일관성 및 품질summary 전역집계도 hashbucket 검증으로 보강한다. 이 중간frozen은 src.before-validation에 보존하며 실제receipt/실행에는 사용하지 않는다.
- 최종 결과 materialization을 최대16bucket으로 나누고 service shard를 한 번 기록한 후 quality·중복·NULL/zero검증에서 재사용하도록 변경했다. 전역정렬 제거 첫probe에서 압축파일이 커지는 회귀가 있어 각bucket안에서만 정렬하도록 수정했다. 전체인구 전역정렬을 다시 도입하지 않는다.
- develop 최신 b255619b8aeca627523a72a5a1a086ff362d559e 기준 미커밋tree 검사에서도 기존5충돌이 동일했다. 실제index/HEAD는 그대로이며 임시tree d2079dcc2410050b800ddae4ce3af5169b1d7d85, 증거 C:/pgb6/develop-compat-v5.json. 실제merge/서버변경은 하지 않았다.
- declarations 자체도 narrow requested Parquet+lookup 조인 VIEW로 유지하여 전체2.4억행 DuckDB 사본을 만들지 않는다. 같은240만버전 전체준비 probe 재실행은 기존14.999초/신규9.805초, 작은fixture전체행일치 및 큰fixture schema/count/statistics/source gaps 일치였다. 반복 사이 절대속도 차이는 동시fixture/캐시 영향이 있으므로 대표bench평균으로 해석하지 않는다.
- 최종출력 정렬수정 후60만패키지/240만버전·256MB/512MB probe에서 작은3개파일전체행이 일치했고 큰입력은schema/행수/순서무관집계hash/품질이 일치했다. 파일크기 기존1,253,545bytes/신규1,280,756bytes(약2.2%증가), 시간0.821초/1.008초였다. 속도개선으로 주장하지 않으며 전역정렬의메모리위험을줄인tradeoff다. 증거 C:/pgb6/final-output-probe-result.json.
- source중복·birth/error일관성 검증은 동일source가반드시같은bucket에모이도록 source_package_id를hash한다. source summary 품질병합도같은방식으로 나눠 status별/birth별숫자만합산한다. NULL/error의충돌·누적품질의보존을검증하며 사용한bucket임시table을다음묶음전에해제한다.
- 신규frozen552파일/5,263,302bytes를준비했다. 실제실행환경이미지의read-onlypreflight에서기존repositoryreceipt SHA를확인하고 변경generator가허용5개파일에만한정됨을검증했다. v2receipt아직미게시이며 전체Linux회귀와품질probe를마친뒤실행한다.
- 최종 frozen 소스로 Linux 회귀 49개가 108.602초에 모두 통과했다. 입력 준비·병렬 worker·NULL/중복/source consistency·품질 집계·실패/재시도/완료 replay를 포함한다. 로그: C:/pgb6/frozen-tests.log. 실제 전체 실행 성공과 구분한다.
- 품질 finalization probe는 n=3, 작은120source의 전체 출력·schema·반환 metadata가 기존 frozen과 일치했다. 큰50만 source/55만 declaration fixture도 DuckDB128MB/spill256MB에서 통과하고 결과가 일치했다. 강제로5bucket을 사용한 시간은 기존0.238초/신규0.385초였으며 속도 배수 개선으로 주장하지 않는다. births0/1/2, true/false/NULL 추출 상태, no-dependency/미해결/부분해결/해결 및 count 보존을 포함한다. C:/pgb6/quality-probe-result.json.
- 2026-09-23 04:06:55 KST recovery3를 시작했다. container pickage-bounded-w914b3-recovery3 (287c58751a7a), watcher11348/controller40084. 같은 w914b3 요청과 완료5개 checkpoint를 유지하고 dependents-bounded-v2 receipt로 재개한다. DuckDB4GB/2CPU/worker2/spill8GB, 전처리filesystem36GB 및 처리공간합계50GB상한을 유지한다. 전처리 성공·scratch 해제 확인 뒤 로컬 DB 이전/적재가 자동 실행된다. 아직 DB 완료를 뜻하지 않는다.
- 기존 상태 명령 powershell -File C:/pgb4/status.ps1은 C:/pgb6/status.ps1로 연결했다. 모든 진행 로그와60초 자원 기록은 C:/pgb6에 남긴다. 컨테이너 종료 대기는 docker wait를 사용하며 반복 상태 조회를 하지 않는다.

## 반복 실행 배포 계약 점검
- 현재 실제 로컬 실행은 독립된 DB에 외부 writer가 없음을 확인하고 phase를 분리한다. 그러나 운영 재사용 경로에서 전처리36GB와 PostgreSQL40GB를 별도 filesystem으로 동시에 허용하면, 시작 시 WAL 사용량을 측정하는 것만으로 합계50GB hard cap을 보장할 수 없다. 주기적 측정과 물리 상한을 구분한다.
- 최초 run_chain scaffold는 컨테이너 lifecycle 및 전체 공간 합산·PUBLISHED 검증을 구현하지 못해 채택하지 않고 제거했다. mock3개 통과를 운영 실행기 완성 증거로 사용하지 않는다. 기존 실제 frozen 실행 코드는 변경하지 않았다.
- 공용 bounded 처리 공간 또는 모든 동시 자원 hard cap 합계가50GB 이하인 명시적 배포 profile을 검토한다. 서버 적용·기존 타이머·모니터링 변경은 하지 않는다.

## 실행 중 후속 감사: 반복 실행 예산과 배포 범위
- recovery3의 dependents 입력 준비16개 bucket이 모두 완료됐다. 앞선 두 번의 전체 population/version birth 조인 실패 구간을 통과했으며, 이것을 최종 dependents/DB 완료로 간주하지 않는다.
- 반복 운영에서는 서비스 DB WAL이 전처리 중에도 늘 수 있다. 따라서 현재 격리된 로컬 실험의36GB scratch+시작 시 DB 실측 예산을 그대로 운영의 hard aggregate cap이라고 주장할 수 없다. 두 노드 동시 실행에 적용할 각 filesystem 고정 상한 합계가50GB 이하여야 한다.
- 후보28GB preprocessing+17GB DB+4GB loader+0.5GB evidence는17GB DB의 전체 주간 적재 수용량 증거가 없다. 약1,900만 snapshot staging/최종 insert와 delta upsert가 같은 적재에서 WAL·임시공간을 사용하므로, 진행 중 후속 DB cap40GB를 임의로17GB로 줄이지 않았다. 실제 최종 측정 전까지 운영 준비 완료로 표시하지 않는다.
- 범용 chain prototype은 cap 환경변수 미전달, loop mount 권한 누락, PostgreSQL 저장 위치/크기 검증 누락, 완료 검증 우회 가능성 때문에 채택하지 않고 이번에 추가한 prototype 파일만 제거했다. 형식적인 mock/compile 검증을 실행 가능 증거로 기록하지 않는다. 이미 실제 fixture로 검증한 bounded 전처리·loader·PostgreSQL entrypoint와 배포 절차를 유지한다.
- goal의 서버 실행 제외 범위를 유지한다. 기존 timer/monitoring 구성 변경이나 운영 DB 이전을 수행하지 않았다. 성공한 로컬 실행과 운영 자동 연결 검증을 분리해서 기록한다.- 04:35 KST develop 재감사: origin/develop b255619, 미커밋 변경 포함 임시tree acdbee30/commit4947fb45. 기존5개 충돌(문서3개/이동 경로2개)이 동일하며 실제 index SHA664f3bac 및 HEAD f306b729는 유지했다. 원래 develop 워크트리도 기존 untracked3개만 남았다. 증거 C:/pgb6/develop-compat-v6.json. git diff --check는 통과했으며 Git 줄바꿈 안내만 있었다.
- 실험 폴더 C:/pgb1~pgb6 전체1,084,456,687bytes 중 frozen JAR6개1,041,384,864bytes, source28,607,659bytes다. 로그·결과·임시분류·기타 약14.5MB는500MB overhead 예약 범위 안이다. 이 실행기의 코드/JAR는 처리용 데이터와 구분하며 삭제하지 않았다. 종료된 이전 bounded volume6개는 Docker 보고 각각37bytes, 현재 recovery3만36GB sparse image를 가지고 있다. 이미지 논리 용량과 filesystem 실제 사용량을 혼동하지 않는다.
- 최종 Curated GET SHA 검증은 Docker 내부 MinIO endpoint를 쓰는 별도 읽기 전용 verifier로 준비했다. 전처리 종료코드0을 docker wait로 받은 뒤에만 실행하며512MiB/1CPU,16MiB tmpfs로 제한한다. frozen source와 실행 데이터는 수정하지 않는다. C:/pgb6/finish_curated_proof.py(PID13788)는 기다리는 중이며 PASS 증거는 아직 없다.
- backend 별도 정적 검토 결과 현재의 빈 staging/단일 loader40GB 실행을 막는 추가 결함은 발견하지 않았다. 장기 snapshot_at 조회 인덱스와 다른 실행 staging이 남았을 때 DELETE cleanup의 WAL 증가는 운영 후속 항목이다. 실제 완료/사용량 검증을 대신하는 증거로 사용하지 않는다.
## 실제 9/14 로컬 전처리·DB 적재 완료 증거
- 저장된 완료 기록을 확인했다. recovery3 Curated 완료06:38 KST(9,089.24초), 전체 자동 후속 검증 완료07:08:20 KST(10,884.474초). 앞5단계는 이전 성공 산출물을 재사용했으므로 이3시간1분을 처음부터 전체 파이프라인 시간으로 해석하지 않는다.
- 최종 bundle SHA82b6650328ce9deccdf473d9746ca51aa23d889c11cd86a037361b6f351bc277. 별도 native verifier는 모든6단계 산출물GET SHA와 고정 source 불변을14.128초에 PASS했다(C:/pgb6/final-curated-proof.json).
- Spring DB 적재06:39:49~07:08:04 KST, 약28분15초, PUBLISHED. package delta242,856행, version delta1,186,870행, package_snapshot11,312,204행, package_version_snapshot7,935,685행. NULL dependents0; 제외47,047,051행은 비선정47,047,026/부적격25로 사유별 기록됐다.
- final SQL 검증은 exact bundle/current pointer/active published attempt/expected actual counts 조건을 통과했다. 서비스 총package11,323,796/version55,026,921. staging65,536bytes, scratch는image 부재 확인 후0, WAL8,589,934,592bytes. cleanup은TRUNCATE였다.
- 실행기 기록의 처리공간 최고치는overhead 예약 포함27,532,721,882bytes(약27.53GB). 60초 표본 및 보수적 예약의 최고값이며 순간 전체 실측 최고값으로 표현하지 않는다. 최종 처리공간은예약포함약9.28GB, 주로 재사용 WAL이며 원천·최종 서비스 데이터는 제외했다.
- DB version_snapshot merge는1,294.074초(약21분34초)로 이번 DB적재의 주 병목이다. package_snapshot merge111.598초. 전처리 후반/DB 전체 성능 개선 판단에 실측 근거로 남긴다.
- 현재 조회 시 Docker Desktop Linux engine 소켓이 없어 live DB/컨테이너 재접속은 하지 못했다. 위 결과는 실제 실행 때 저장된PUBLISHED·검증·자원 로그로 확인한 사실이며 현재 DB 접속성의 재검증과 구분한다. 원래 데이터/서비스나 Docker를 임의로 재시작하지 않았다.
- 아직 운영 두노드 반복 실행의 합산 예산/배포 연결과 develop5개 충돌은 별도 후속 검토가 필요하다. 로컬 성공을 운영 검증 완료로 표시하지 않는다.
## 반복 실행용 공통 자원 제한 작업계획
- 현재 실제 성공 로그에서 DB processing 최고14,780,973,056bytes, loader scratch202,711,040bytes를 확인했다. 기존 성공한40GB 실험 이미지와volume은 변경하지 않는다.
- 새 runtime 공통 계약을 전처리28GB/DB17GB/loader4GB/overhead0.5GB로 제한한다. role별 하나의 전용 volume·잠금으로 동시 실행 수를 제한하는 배포 전제와 함께49.5GB 합산 상한을 설명한다. 잘못된 숫자·상한 초과는volume 생성/format 이전에 거부한다.
- 검증은 pure shell 경계값/역할 테스트, 실제 작은 filesystem ENOSPC·정리·실행권한 fixture, 기존 성공DB 재시작 후PUBLISHED 데이터 보존 조회로 나눈다. 신규17GB 한도에서 전체weekly 적재가 검증됐다고 주장하지 않는다.

## 공통 cap 및 DB 정렬 라이브러리 후속 검증
- resource_budget.sh의 immutable 역할별 최대값은28GB/17GB/4GB다. loader 역할은 이미지의workspace.role 파일에 고정하여 환경변수 override로28GB를 받지 못하도록 했다. cap 숫자·overflow·역할 오류는volume 생성/format 전에 거부하며 새 이미지들은 공통 helper를 포함한다. 고정volume별flock과 역할별singleton 배포 전제가 필요하다. 로그rotation을 포함한49.5GB 계약을문서화했다.
- budget 단위/실제Docker8개 테스트가13.157초에 통과했다(C:/pgb6/budget-fixture-tests.log). 실제64MiB ENOSPC·UID1000·scratchimage제거·marker거부·잘못된cap전후volume동일·loader역할환경override거부를 포함한다. 기존고정이름container삭제/저장소전체build를하던낡은test shell은소유label검증하는새fixture를호출하도록바꿨다.
- 재시작검증에서 과거bounded PG base(bookworm/glibc2.36)가기존baseline(glibc2.41)과다른문제를발견했다. 실제서비스DB의datcollversion은2.41이었다. 잘못된runtime을정지하고기존baseline의공식postgres:16 digest f1c3376c...를기반으로동일40GBwrapper만재빌드했다. PGDATA나정렬버전메타데이터를변경하지않았다.
- 현재compat container b1cbd6aa4ac4(pickage-bounded-db-w914b3-compat), image f458a623d629...에서2.41=2.41을확인했다. public서비스테이블/두snapshot파티션의10개Btree에bt_index_parent_check(heapallindexed=false)를수행해모두PASS했다. amcheck확장은트랜잭션안에서만만들고ROLLBACK하여영구schema변경없음을확인했다. PUBLISHED/current/activeattempt/counts일치도실DB조회1건이다. 증거runtime-compatibility.json/index-compatibility.log.
- 새PG이미지는기존DB와맞는base digest를기본으로하고기동중collation일치확인후에만ready marker를쓴다. 불일치시는종료하며Dockerhealthcheck도marker를요구한다. 기존40GBimage를새17GBwrapper로자동포맷/축소하지않는다.
- 새17GBfilesystem의작은실DBfixture에서offlineWALcopy/행보존/재시작/8개staging테이블·PK배치/temp설정/looprelease를통과했다. 40GB sparse sentinel은바이트변경없이거부했고,격리된fixture의collation을의도적으로다르게했을때exit2로차단했다. 이는fullweekly17GBcapacity증거와구분한다. 최종healthcheck추가이미지68e2a977...의같은fixture는후속결과로기록한다.- 최종17GB 이미지68e2a977... fixture도 PASS했다. role cap·40GB sentinel 보존/거부·offline copy·행 보존·ready marker·재시작·staging8개 객체 위치·collation 불일치 exit2·loop 해제를 확인했다(C:/pgb6/pg-budget-final-fixture.log).
- 로컬 실제 DB를 clean shutdown한 뒤, 기존40GB 처리 image를 read-only mount하여 새17GB image로 WAL/staging 파일을 복사했다. 전체 파일 SHA 목록이 일치했다. 원본 약6.996GB+새복사본 약6.998GB로 이전 중 처리 공간도50GB 미만이다. 서비스 PGDATA volume은 그대로 유지했다.
- 새 실제 DB a2fcbeeb4011(pickage-bounded-db-w914b3-budget17)는 healthy, collation2.41=2.41, image17,000,000,000bytes, 실제 사용6,998,323,200bytes다. CHECKPOINT 후 baseline8/31와 weekly9/14의 PUBLISHED/current/activeattempt, 서비스package11,323,796/version55,026,921 및9/14두snapshot11,312,204/7,935,685행을 실제 다시 조회해 보존을 확인했다. NULL0/staging64KiB/temp_tablespaces=curated_work도 일치했다.
- 검증 후 중복된 기존 처리volume pickage-bounded-db-w914b3와 그 volume을 참조하던 종료된 실험컨테이너3개만 제거했다. 삭제 전 inspect/log를 C:/pgb6/archived-container-*.json/.log에 보존했고 docker rm에-v를 사용하지 않았다. 영구 PGDATA 및 MinIO volume은 보존됐다. 최종증거budget17-migration-complete.json. 전체weekly를17GB cap에서 재적재한 결과와, 이미적재된DB를17GB로 이전·검증한 결과는 구분한다.
- 15:17 KST origin/develop c88e20a를 새로 fetch하고 전체미커밋변경 포함tree4c024a46/임시commitb65df925로 확인했다. 동일5개 충돌만 존재했다. HEAD/index는 바꾸지 않았다(C:/pgb6/develop-compat-v7.json).

## 2026-09-23 weekly bounded 연결과 모니터링 보존

- 이전 설명 턴은 상태 보고였고 구현 진전은 없었다. 이번에는 실제 dispatcher/Compose 연결을 수정했다.
- dispatcher는 supervisor의 BOUNDED_WORKSPACE/work와 tmp를 사용한다. 명시적 외부 work-dir는 MinIO client/lock 생성 전에 거부한다. 새 요청에만 work_cleanup=stage를 고정하며 이전 immutable request는 수정하지 않는다.
- 기존 weekly timer, run-weekly-ingest.sh, 호스트 flock, 고정 컨테이너 이름과 MinIO 상태/이벤트 경로를 유지했다. Compose의 무제한 /opt/work/data 쓰기 mount를 제거했다.
- run_snapshot의 기존 60초 자원 표본 코드를 resource_events.py로 추출해 dispatcher에서도 사용한다. 단일 실패 사례 테스트는 원래 예외 보존과 마지막 단계 상태 기록을 확인했다(1 test PASS).
- Dockerfile.bounded 전용 dockerignore로 Compose 빌드 context에서 데이터·Git·자격증명을 제외했다. 실제 빌드 성공, 전송 context 6.04kB(C:/pgb6/compose-bounded-build.log).
- delegated dispatcher/weekly deployment tests: 28 passed, 5 skipped. Windows 통합은 기존 긴 경로 제약으로 실패해 Linux bounded container에서 재검증한다.
- 첫 Linux smoke는 테스트 스크립트의 multiprocessing main guard 누락으로 실패했고, guard 추가 후 512MiB fixture가 dependents의 최소 여유2GB 정책에 의해 중단됐다(OOM 아님). 실제 코드 정책을 완화하지 않고 fixture filesystem을4GB로 늘려 재실행했다. 결과 파일: C:/pgb6/dispatcher-bounded-smoke-v2.log.
- 실제 로컬 MinIO + 현재17GB DB + 새 loader 이미지 연결에서 동일9/14 bundle은 DB_RESULT=SKIPPED, exit0/OOM=false였다. C:/pgb6/loader-budget17-skip.log. 이는 중복 방지 검증이며17GB 전체 재적재 성능 검증이 아니다.
- develop 재검사 v8: origin/develop c88e20ae7f9bee4842c8016c856e2426128ce4e5. 기존과 동일한 README3개와 이동 경로2개 충돌. 실제HEAD/index 변경 없이 임시 index/merge-tree로 확인했다(C:/pgb6/develop-compat-v8.json).
- 서버 명령, 운영 모니터링 변경, 커밋은 수행하지 않았다. 새17GB cap의 전체 weekly 적재 검증은 아직 남아 있다.

- Linux bounded dispatcher 최종 검증: 24 tests, 57.076s, OK. UID1000, bounded tmp/work, 자원 stdout, 실제 작은 전처리 통합과 완료 회차 skip을 확인했다. 컨테이너 exit0/OOM=false. 별도 readonly volume 검사에서 전처리와 loader의 scratch.ext4 모두 부재(SCRATCH_CLEANUP_PASS). fixture는4GB이며 실제 전체 데이터17GB DB 재적재 증거와 구분한다.


## 2026-09-23 완료 범위 재감사와 독립 baseline 확인

이전 goal 턴은 dispatcher 연결, 실제 Linux 통합 검증, 임시파일 정리 확인으로 progress였다.

| 요구사항 | 현재 직접 증거 | 판정 |
| --- | --- | --- |
| 실제 Curated 생성·MinIO 게시·DB 적재 성공 | pgb6/flow-status.json COMPLETE, final-curated-proof.json PASS, db-weekly.log PUBLISHED | 실제9/14 성공 |
| 메모리 제한 안에서 종료 | 실실행 전처리/loader exit0·OOM=false, DB4GiB/loader8GiB | 해당 실실행 통과 |
| 처리 공간50GB 이하 | 기존 순차 프로파일 실제 계측27.53GB, 새 역할 cap28/17/4GB+로그 예약 | 기존 실실행 계측 통과, 새17GB 전체 적재 수용량 미검증 |
| 작업 후 정리 | staging65536B, 전처리/loader scratch.ext4 부재 | 실실행·fixture 통과 |
| 중요한 데이터 보존 | 기존 PGDATA 유지, SHA 확인 WAL 이전, 실제 행 수 보존 | 확인 |
| 서버 적용 준비와 모니터링 유지 | bounded dispatcher Compose, 같은 timer·journal·MinIO 상태 경로, Linux24 tests | 로컬 연결 검증, 서버 실행 안 함 |
| develop 충돌 검사 | develop-compat-v8.json, 실제 index/HEAD 불변 | 검사 완료,5곳 충돌 남음 |

- 독립 기준 DB 탐색: pgb6의 원래/호환/17GB DB는 모두 PGDATA32ce7f8d... 하나를 사용한다. 따라서 기존 컨테이너 이름만 바꿔 재실행해도 fresh load가 아니며 현재9/14 결과를 SKIPPED한다.
- 별도 pickage-local_pgdata 볼륨 존재는 확인했지만, 그것이8/31 실데이터라는 증거는 없다. 해당 컨테이너를 시작하거나 내용을 수정하지 않았다. deploy/local/seed는 작은 SQL seed 파일들이며 실데이터 백업 증거가 아니다.
- 사용자에게 별도8/31 백업/볼륨 보유 여부만 확인 요청했다. 검증을 위해 성공 이력 삭제, 원천 bundle 변경, baseline 위조는 하지 않는다. 새17GB full_weekly_load 검증은 여전히 미완료이며 goal 완료로 표시하지 않았다.
- 이번 검사에서 만든 terminal 테스트 컨테이너3개와 scratch volume2개만 inspect로 소유 경로를 확인하고 정리했다. 전체 로그와 inspect를 pgb6에 보존했다(weekly-fixture-cleanup.json PASS). 서비스·MinIO·실제 성공 DB는 건드리지 않았다.


## 2026-09-23 독립 baseline 후보 발견 (이전 조사 보완)

- 별도 pickage-local_pgdata를 읽기 전용 mount로 검사했다. base53848KiB/WAL49160KiB라 실데이터 기준 DB와 다르다. 원본 DB는 기동하지 않았다.
- 추가 후보 pickage_267_validation_pgdata는 base163802812KiB/WAL8159276KiB, PG16, 중지 전 clean shutdown되지 않은 상태다. 원본을 시작하거나 writable mount하지 않았다. pg_tblspc 외부 symlink는 없었다.
- 과거267 worklog04/05와 evidence/full-load.json에서 DB pickage_267_full_defaulted,8/31 source curated-20260907-v2,package11080940/version54188349 성공을 확인했다. 현재baseline b831r3와 package/version 건수는 같지만 동일한 bundle이 아니며 snapshot metrics/행내용 동등성은 미검증이다. 과거 기준 DB가 없다고 결론내리면 안 된다.
- 현재 성공DB를 바꾸거나 원본267 DB를 쓰기 실행하지 않도록 원본과 동일 Alpine digest에 e2fsprogs/util-linux만 추가한 로컬 probe 이미지를 빌드했다(C:/pgb6/baseline-probe-build.log). overlay 또는 독립 복제의 실제 실행은 아직 안 했다. source shutdown이 불완전하므로 복구 쓰기까지 별도 물리 제한 공간에 격리해야 한다.
- C:/pgb6/baseline-candidate.json에 원본 identity와 미검증 경계를 기록했다. 사용자에게 앞서 요청한 백업 위치는 우선 답변 불필요하다고 알렸다. 다음 검증은 후보 DB의 실제 내용과 current baseline 계약 호환성 확인이다. 서버 변경 없음.


## 2026-09-23 읽기 전용 baseline 격리 조회

- source volume은 readonly mount하고 PostgreSQL 쓰기는12GB ext4 위 OverlayFS upper에만 기록하는 일회성 로컬 probe를 만들었다. 원본과 같은 postgres:16-alpine digest를 사용하고2GiB RAM/2CPU/network none을 적용했다.
- 원본 PGDATA/pg_tblspc의 외부 symlink 부재를 확인했다. 원본의 불완전 종료 복구도 private overlay 안에서만 발생하도록 했다. 조회는 default_transaction_read_only=on, autovacuum=off로 실행한다.
- 첫 probe는 OverlayFS upper 루트 소유자가root여서 PostgreSQL 기동 전 거부됐다. 원본 pg_control SHA 불변, overlay 해제, cow.ext4 삭제를 확인했다(C:/pgb6/baseline-readonly-probe.log). 임시 upper만UID70/mode700으로 생성하도록 수정한 뒤 동일 terminal 컨테이너를 재시작했다. 실제 성공DB/원본267 DB 설정은 변경하지 않았다.
- 진행 로그 C:/pgb6/baseline-readonly-probe-v2.log. 조회가 끝나면 private PostgreSQL 종료와 overlay/ext4 해제, 원본 control SHA 재검증을 수행한다. 성공9/14 DB는 별도 컨테이너로 계속 보존한다.


### 조사 정정: 원본8/31 후보의 실제 상태 (2026-09-23)

- v2 probe는 crash startup fsync가 OverlayFS 파일을 copy-up하면서12GB 상한에 도달해 기동 실패했다. actual pipeline loader의 실패가 아니라 disposable 격리 복사본의 복구 단계다. 원본readonly/control SHA불변, COW 해제·삭제 확인.
- v3는 재생성 가능한 일회성 probe에만 fsync=off를 적용했다. 원본이나 성공DB의 durability 설정은 변경하지 않았다. 실제 조회 성공 exit0; transaction_read_only=on. 종료 시 사용량42,766,336B, 원본control SHA불변, COW파일삭제 확인.
- 실제snapshot테이블에는229개 과거 날짜가 있고 마지막8/31이다. 이전267문서의 최초단일snapshot 기록만으로 현재볼륨에8/31 하나만 있다고 판단하면 틀린다. package_snapshot 통계추정603,130,240행 등 과거이력이 추가된 DB다. reltuples는 정확한count가 아니므로 실제건수로 보고하지 않는다.
- 성공9/14 DB는 별도로 유지했다. C:/pgb6/baseline-readonly-probe-v3.log와 baseline-candidate.json에 직접증거 기록. 남은 것은 이 과거DB와현재b831r3 baseline의 값·NULL정책·적재계약 동등성 검증과17GB 실제weekly재적재다. 무검증baseline등록은 하지 않는다.


## 2026-09-23 검증 경로 변경: 새 빈 DB에서 정확한 baseline 재적재

- package 표본5개는 b831r3 Parquet 전체파일SHA 검증 후 조회한 값과267원본DB가 일치했다. 그러나 package_snapshot 표본조회는 PostgreSQL의 파일쓰기모드open에 따른OverlayFS copy-up으로12GB공간을 소모해 실패했다. 원본control SHA불변 및 임시COW제거를 확인했다. 표본일치나조회실패를 전체baseline동등성으로 해석하지 않는다.
- 기존 adoptBaseline은 전체version중간테이블만과거약33GB이고 reader.prepare는전체TSV를보존한다. 이는17GBDB/4GBloader검증경로에맞지않는다. legacy원본전체복제/무검증adoption은폐기한다.
- 선택한경로는독립새빈DB에정확한b831r3 bundle을직접스트리밍bootstrap하고,동일w914b3를ordinaryweekly로적재하는것이다. bootstrap은한트랜잭션,빈DB재확인,서비스write잠금,최종테이블PK/UK/FK로파일간중복/참조를검사하고,모든reader품질·행수검증후publication만최종commit한다. 중간전체복제를없애며실패하면전체rollback한다. 기존weekly경로는유지한다. 관련구현/회귀시험은진행중이다.
- C:/pgb7에별도실험준비. pickage-budget17-replay-db,localhost15442,finalPGDATA=pickage-budget17-replay-pgdata,processing=pickage-budget17-replay-processing17GB. 원래성공DB15441은변경하지않았다.
- 이실험동안전처리/overlay를실행하지않는다. 성공DB17GB상한+새DB17GB상한+loader4GB+로그0.5GB=38.5GB를상한으로계산한다. 새PGDATA는검증후보존할최종서비스DB이며중간테이블/WAL/temp는17GB안에둔다.
- 새DB이미지68e2a977...,RAM4GiB/no-swap/CPU2,shared_buffers1GB/max_wal_size8GB/fsync기본on. V1~V8 DDL과bounded staging설정적용완료. database-launch.json/schema-setup.json에증거기록. 아직실제baseline/weeklyload는시작하지않았다.
- loaderproperties는새DB alias로정확히교체했다. 최초준비시baseline파일의host.docker.internal15441이문자열치환대상과달랐으나,어떤loader도시작하기전에검사해수정했다. 원래성공DB에replay하지않는다.


### 초기 적재 파일 단위 처리 검증 준비

- 기존 성공 DB(15441)는 보존하고 전용 통합 테스트 DB(15439)만 시작했다. 테스트 DB 메모리는 2GiB, swap 없이 제한했다.
- 초기 적재 코드를 검토해 파일별 COPY → 서비스 테이블 INSERT → 임시 테이블 TRUNCATE 경로를 확인했다. 실제 중복·참조·후반 실패 롤백 통합 테스트는 진행 중이며 완료로 간주하지 않는다.
- C:/pgb7/replay.py의 동시 측정을 직렬화하고 측정 실패 기록·완료 차단·종료 시 측정 스레드 대기를 추가했다. mock 검증에서 두 DB와 적재기의 최대 예약 합계 38.5GB 및 측정 오류 보존을 확인했다. mock은 컨테이너를 시작하지 않았으며 로그의 fixture 측정은 실측 성능 증거가 아니다.
- 새 DB(15442)의 실제 baseline/weekly 재생은 아직 시작하지 않았다. 빌드 및 통합 검증 후 실행한다.


### 2026-09-23 16:22 KST — 실제 초기 적재 및 weekly 재생 시작

- 전용 15439 PostgreSQL 통합 테스트 26개: 실패/오류/skip 0. 실제 reader callback을 통해 파일 간 중복, 마지막 파일 FK 실패, 올바른 parent_bundle 거부, 날짜 불일치, NULL 제외와 quality 일치, 기존 데이터 거부를 검증했다. 파티션 이름 오검사를 수정하고 테스트 전 해당 전용 빈 파티션을 제거하여 생성 롤백을 확인했다. 테스트 컨테이너는 종료했다.
- JAR SHA256: `1db1c4c342dce4fa493d8d6a94906cfb5a56902c662279359b803c227fe1adea`. C:/pgb7/loader-build-proof.json에 main 소스/설정 145개 해시와 빌드 결과를 기록했다.
- C:/pgb7/replay.py 백그라운드 PID 38808 시작. 실제 baseline 컨테이너 `pickage-bounded-budget17-baseline`의 running 상태와 PID 67639를 확인했다. 상태는 BASELINE이며 아직 완료가 아니다. 초기 적재 → DB 재시작 → 정확한 w914b3 weekly → 결과/정리 검증을 순서대로 실행한다.
- 기존 완료 DB 15441 보존. 새 DB 15442 사용. 두 DB의 처리 공간 17GB씩 + loader 4GB + 로그 예약 0.5GB = 38.5GB 상한으로 이번 실험을 계산한다. 전처리는 동시에 실행하지 않는다. 원천/최종 데이터는 합의된 제외 대상이다.
- C:/pgb6/develop-compat-v9.json: origin/develop c88e20ae 기준 임시 index 병합 검사에서 기존 5개 충돌만 확인했다(README 3개, 이동된 downloads_reload.py와 test_downloads_reload.py 2개). 실제 HEAD/index는 변경하지 않았다. 현재 브랜치에서 실제 병합은 하지 않았다.


### 2026-09-23 — baseline 대형 TSV 예산 초과 수정

- C:/pgb7 초기 적재가 204초에 FAILED. OOMKilled=false, 원인은 첫 version Parquet 전체를 TSV로 만들다가 WorkBudget 3.4GB를 초과한 것이다. 입력+TSV 여유는 DuckDB 예약을 빼면 약 1.188GB였다.
- 검증 DB package/version/snapshot/current 0건으로 롤백 확인, scratch.ext4 부재 확인. 기존 15441 current는 2026-09-14 그대로다.
- 변경 계획: 최초 bootstrap 경로에만 64MiB 이하 COPY 묶음 변환/즉시 적재/삭제를 적용한다. 기존 weekly receipt와 재시작 계약은 유지한다. 입력 전체 SHA 및 키 검증, 원본 행 수, NULL 제외/quality 합계, 최종 단일 트랜잭션 검증을 보존한다. 작은 chunk로 강제분할하는 테스트와 기존 변환 결과 비교 후 실제 입력을 다시 실행한다. 용량 상한은 늘리지 않는다.


### 2026-09-23 16:35 KST — COPY 묶음 분할 후 재실행

- 최초 bootstrap만 `prepareBootstrapStreaming`을 사용한다. Parquet SHA/키 검증 후 64MiB 이하 TSV 묶음을 변환 → PostgreSQL 반영 → 삭제한다. 원래 weekly staging/receipt 계약은 유지한다.
- 리뷰에서 발견한 선행/전체 NULL 행 수 누락, NULL 이중 합산, 예외 시 finally에서 callback 재호출 문제를 수정했다. 빈 입력도 0행 묶음으로 역할을 유지한다. bootstrap dependency 기본값 quality는 동일 집계 결과만 남겨 불필요한 JSONL 누적을 없앴다.
- 통합 테스트 27개 전부 PASS(오류/실패/skip 0). 256byte로 강제 분할한 결과가 기존 전체 TSV와 일치하고, 다음 묶음 전에 이전 파일 삭제, 실제 DB 20버전 적재, callback 실패 1회 전달을 검증했다. 관련 curatedload 단위 테스트도 PASS. 별도 전체 E2E fixture 한 개는 전용 설정 부재로 skip이며 실제 전체 입력은 아래 실행으로 검증한다.
- 실패 기록은 C:/pgb7/attempt1-failed-budget 및 종료 컨테이너 이름 suffix -attempt1로 보존했다. 새 DB의 롤백된 package에만 VACUUM/REINDEX를 수행해 빈 테이블 잔여 공간을 1975MB에서49152bytes로 회수했다. 기존 완료 DB는 변경하지 않았다.
- 새 JAR SHA256 `5f22a6b3ff491c6932d90cc672666afbe38393fa3106dca924e250924bbd6d29`, build source proof145개. 재실행 Python PID39916. 실제 결과는 아직 미확정이며 cap은 변경하지 않았다.


### 2026-09-24 — 17GB DB cap 실제 초기/weekly 적재 완료 확인

- C:/pgb7/status.json COMPLETE. 2026-09-23 16:35~20:50 KST, 총15302.56초(검증 포함). baseline 컨테이너13746.2초, weekly1503.4초. 둘 다exit0/OOMKilled=false.
- 금일 live SQL에서 b831r3(8/31), w914b3(9/14) 모두PUBLISHED 및 actual_counts=expected_counts 확인. current9/14. baseline 후 fsync=on DB 재시작 및 weekly 수행 기록 존재.
- 저장된 전체 검증: 최종 package11323796/version55026921, 9/14 package_snapshot11312204/version_snapshot7935685, NULL dependents0. baseline 검증도PASS.
- 60초 표본 최고: 새 DB 처리영역14783070208bytes, loader388112384bytes. 기존 보존 DB 및 로그 예약을 합산한 최고22342268160bytes. 해당 두 영역의 측정 실패/전체cap 대체 표본0. 이번 단계별 hardcap38.5GB 이내 실행; 원천과 영구 최종 데이터는 합의된 제외 대상.
- 금일 readonly volume 검사로 baseline/weekly 양쪽 scratch.ext4 부재 확인. live DB staging 총65536bytes. WAL은 정상 DB 복구용으로 유지하며 삭제하지 않는다.
- 이번 결과는 기존 검증된 Curated bundle의 DB 재생 결과다. raw 전처리를 새로 실행한 시간이나 새로운 서버 배포 검증으로 해석하지 않는다. 원래15441 완료DB와 원천/MinIO 결과는 보존했다.


### 최종 요구사항 대조 완료

- 36-bounded-pipeline-verification.md에 요구사항별 근거·실측·서버 미실행 경계를 정리했다. runtime 문서의17GB 미검증 문구를 실제 성공 결과로 갱신했다.
- 9/24 fetch 후 develop29153b3 기준으로도 같은5개 충돌이다. final audit의 real index SHA는 기존과 같고 실제 병합은 하지 않았다.
