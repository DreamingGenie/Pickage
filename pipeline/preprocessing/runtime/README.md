# Bounded preprocessing workspace

이 runtime은 로컬 Docker에서 raw → Curated 전처리를 시험하고, 나중에 data 노드에 같은 방식으로 올리기 위한 격리 실행기다. 저장소의 `curated-dispatch` Compose 서비스에 연결하며 기존 timer와 모니터링 수집 설정은 유지한다. 실제 서버에는 아직 적용하지 않았다.

## 저장공간 계약

전용 Docker named volume 하나만 `/var/lib/pickage-bounded`로 연결한다. supervisor가 그 안에 고정 경로 `scratch.ext4`를 만들고 ext4 loop mount를 `/run/pickage-bounded`에 연결한다. 현재 이미지 생성 시 최대 크기는 `28,000,000,000` bytes이며, 이미 존재하는 파일의 크기·소유 marker·mount 상태가 다르면 포맷하거나 재사용하지 않고 중단한다.

`resource_budget.sh`는 전처리28GB, PostgreSQL WAL/staging/temp17GB, loader4GB를 각 runtime의 최대값으로 고정한다. Docker 로그·실행 기록0.5GB를 포함해 합계49.5GB다. 이미지에 고정된 `workspace.role`로 역할을 구분하며 환경변수로 loader를 전처리 역할로 바꿀 수 없다. 크기 초과·잘못된 숫자는 filesystem 생성 전에 거부한다. 작은 filesystem은 가능한 처리량도 작으므로 이 제한이 모든 스냅샷의 성공을 보장하지는 않는다.

이 합계는 **역할별 동시 실행이 하나**인 배포 계약이다. 전처리는 기존 weekly 호스트 잠금 안에서 고정 container/volume을 사용하고, app 노드 loader도 `pickage-bounded-loader`/`pickage-loader-work` 하나만 사용한다. volume 내부 `flock`이 같은 작업 공간의 동시 사용을 거부한다. 다른 이름의 volume을 추가하는 병렬 실행은 이 예산에 포함되지 않으므로 지원하지 않는다. PostgreSQL 영구 서비스 데이터와 MinIO 원천·최종 결과는 합의한 처리 공간에서 제외한다. 신규 로그는 역할별 `max-size=10m`, `max-file=3`으로 제한하고, 별도 로그 사본도 회전 파일로만 기록한다. 운영 모니터링의 수집 설정은 변경하지 않는다.

## 권한과 실행

컨테이너의 `--privileged`는 loop mount를 위한 설정이며 컨테이너 수명 동안 유지된다. pipeline child는 `setpriv`로 uid/gid 1000, no-new-privileges, capability 제거 상태에서 실행한다. 코드는 read-only로 연결하고 처리 파일은 제한된 filesystem 안에 기록한다. stdout의 단계·자원 이벤트를 기존 로그 수집기로 전달한다.

아래는 이미 고정한 단일 요청 실행 예시다. `request.json`에 `options.work_cleanup="stage"`가 필요하다. env 파일에는 `PICKAGE_BOUNDED_S3_ENDPOINT`, `PICKAGE_BOUNDED_S3_ACCESS_KEY`, `PICKAGE_BOUNDED_S3_SECRET_KEY`를 설정한다. `<commit>`에는 아래 절차로 만든 이미지 태그를 지정한다.

```bash
docker volume create pickage-bounded-workspace
docker run --rm --name pickage-bounded-run \
  --privileged --read-only --tmpfs /tmp:size=64m --tmpfs /run:size=16m \
  --memory=8g --memory-swap=8g --cpus=2 \
  --log-opt max-size=10m --log-opt max-file=3 \
  --add-host=host.docker.internal:host-gateway \
  --env-file /srv/pickage/bounded.env \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 \
  -v pickage-bounded-workspace:/var/lib/pickage-bounded \
  -v "$PWD:/opt/work:ro" \
  -v /srv/pickage/requests/request.json:/opt/request.json:ro \
  pickage-preprocessing:bounded-<commit> \
  python -m pipeline.preprocessing.runtime.run_snapshot --request /opt/request.json
```

실행이 끝나면 `fstrim` 후 mount를 해제하고, 해당 실행이 만든 `scratch.ext4`를 삭제한다. mount가 설정한 `AUTOCLEAR`로 loop 연결이 해제되며, unmount 실패나 연결 잔존 시 이미지 삭제도 중단한다. Docker의 `/dev`에 새 loop node가 없으면 해당 node를 만든 뒤 연결한다. 컨테이너 강제 종료 때도 namespace 해제로 연결은 해제되지만, 파일 삭제 trap은 실행되지 않으므로 소유 marker가 있는 volume의 잔여 image를 별도로 확인해야 한다. MinIO를 호스트 tunnel로 사용할 때는 `--add-host=host.docker.internal:host-gateway`와 명시적 endpoint 환경변수를 추가한다. 운영 Compose에 바로 넣기 전에 Linux host에서 loop device 허용 여부와 dedicated volume의 실제 디스크 상한을 확인한다. loop가 허용되지 않는 환경에서는 Docker storage quota만으로 대체하지 말고, 50GB 전체 상한을 증명할 수 없으므로 실행을 차단한다.

## 배포 전 절차

운영 저장소 전체를 Docker build context로 보내지 않는다. Linux data 노드에서 다음처럼 새 임시 디렉터리에 Dockerfile, supervisor script, `pipeline/minio/requirements.txt`, `pipeline/preprocessing/curated/requirements.txt`만 복사한 뒤 작은 context로 이미지를 만든다.

```bash
CTX=/srv/pickage/bounded-build-context
mkdir -p "$CTX/pipeline/minio" "$CTX/pipeline/preprocessing/curated" "$CTX/pipeline/preprocessing/runtime"
cp pipeline/minio/requirements.txt "$CTX/pipeline/minio/"
cp pipeline/preprocessing/curated/requirements.txt "$CTX/pipeline/preprocessing/curated/"
cp pipeline/preprocessing/runtime/Dockerfile.bounded pipeline/preprocessing/runtime/bounded_workspace.sh \
   pipeline/preprocessing/runtime/resource_budget.sh pipeline/preprocessing/runtime/workspace.role \
   "$CTX/pipeline/preprocessing/runtime/"
docker build -t pickage-preprocessing:bounded-<commit> \
  -f "$CTX/pipeline/preprocessing/runtime/Dockerfile.bounded" "$CTX"
```

기존 운영 모니터링과 timer는 수정하지 않는다. 단일 요청과 weekly dispatcher가 같은 자원 로그를 stdout으로 전달하고 기존 MinIO 실행 상태 객체를 유지한다. weekly 배포에서는 위 빌드 태그를 `pickage-curated:bounded-runtime`으로 지정한 뒤 기존 `curated-dispatch` 서비스를 사용한다. 실제 서버 반영은 별도 배포 작업이다.

이 절차는 로컬 Docker와 서버 반영을 위한 준비 문서다. 서버에서 실제 명령을 실행하지 않았다. 저장소의 Compose 변경은 배포 준비 코드다. 서버 반영 전에는 loop device 허용, dedicated volume 용량, DB/WAL을 합산한 전체 50GB 예산을 별도로 확인한다.

## 현재 배포 경로와 연결 범위

아래36GB/40GB는 과거 실제 실행의 설정 기록이다. 현재 공통 cap28GB/17GB/4GB와 구분한다. 기존40GB DB filesystem은 새17GB 이미지로 자동 축소하지 않으며 크기 불일치로 기동을 거부한다.

저장소의 실제 운영 경로는 `pickage-weekly.timer` → `run-weekly-ingest.sh` → `ingest-weekly` → `curated-dispatch`다. 기존 timer·호스트 잠금·컨테이너 이름·실패 시 재시도와 MinIO `_ops/preprocessing` 기록은 유지한다. 저장소의 `curated-dispatch`는 bounded supervisor 안에서 dispatcher를 실행하도록 구성한다. 작업·임시 파일은 bounded root 아래에 두고 새 요청은 `work_cleanup=stage`를 사용한다. 기존 요청은 덮어쓰지 않고 계약이 다르면 중단한다. 단순 MR 병합만으로 아래 자원 격리가 적용된다고 해석하지 않는다.

| 실행 | 이 로컬 실험에서 적용한 설정 | 다음 운영 배포에 필요한 연결 |
| --- | --- | --- |
| Raw → Curated | 고정 request, 8GiB container / DuckDB4GB / 2CPU, 36GB scratch | 기존 dispatcher를 bounded supervisor의 자식으로 실행하고 `work_cleanup=stage` 사용 |
| MinIO 게시 → loader | 전처리 종료 및 scratch image 부재 확인 후 시작 | 과거 실험은 순차 실행. 현재28/17/4GB는 역할별 하나씩 동시 실행해도 합계 제한 적용 |
| Spring loader | 8GiB container / Java512MiB / native DuckDB4GB, 4GB scratch | 별도 batch jar와 `mode=once`, 정확한 bundle prefix/SHA, 보호된 properties 제공 |
| PostgreSQL | 기존 영구 PGDATA 보존, WAL/staging/temp만 별도40GB filesystem(설정 최대42GB) | app 노드 DB에 적용할 저장 경로·기존 데이터 이전을 별도 배포 절차로 검증 |

디스크 상한은 RAM 설정과 다르다. 전처리 중에는36GB scratch와 기존 DB WAL/staging 및 로그를 합산한다. DB 단계에는 전처리 scratch가 없어야 하며,42GB DB 처리 filesystem과4GB loader scratch에 나머지 로그·호스트 임시 공간을 더한다. offline WAL 이전의 원본 backup도 삭제가 검증될 때까지 포함한다. Docker/호스트의 영구 원천·최종 서비스 데이터는 사용자와 합의한 처리 공간 범위에서 제외한다.

이번 로컬 후속 실행기는 WAL 이전 원본 약8.47GB와 동시에 존재하는 최대 공간을 확보하기 위해 DB cap을40GB로 선택했다. 이전 시작 전, 이전 완료 후 backup 삭제 전, loader 실행 및 최종 검증 시 각각 실제 사용량과 단계별 예약 상한을 기록한다. `df`를 읽지 못하면0으로 기록하지 않고 해당 filesystem의 전체 cap을 예약한다. 최종0바이트는 scratch image 부재를 확인한 경우에만 인정한다.

위36GB/40GB 구성은 다른 쓰기 작업이 없는 격리된 로컬 실험의 단계별 예산이다. 실제 DB 적재의 WAL/staging/temp 표본 최고치는14.78GB였다. 현재 공통 cap은 역할별 하나씩 실행할 때 합계49.5GB다. 2026-09-23 로컬의17GB DB filesystem에서 정확한8/31 baseline과9/14 weekly를 연속 적재하고 중간 DB 재시작까지 통과했다. DB 처리 영역 표본 최고14.783GB이며 초기 적재와weekly 적재는 각각3시간49분,25분이었다. TSV64MiB 묶음 처리와scratch삭제도 실제 입력으로 확인했다. 운영 수용량 검증 전에는 production_ready로 표시하지 않는다. dispatcher의 경로·잠금·정리 계약을 로컬에서 검증한 뒤 서버에 배포한다.

## 기존 모니터링에 전달하는 기록

운영의 모니터링 수집 설정은 수정하지 않는다. 전처리 stdout에 `PIPELINE_RESOURCES`가60초마다 run_id, phase, 단계 상태, 경과 시간, scratch 사용량·표본 최고치, cgroup 메모리를 기록한다. cgroup 메모리는 파일 cache도 포함한다. 종료 시 `PIPELINE_COMPLETE` 또는 `PIPELINE_FAILED`를 남기고, Spring wrapper는 `DB_RESULT`를 출력한다. 기존 dispatcher의 MinIO 상태·이벤트와 함께 사용할 수 있다.

`watch_local.py`는 `docker logs --follow`와 `docker wait`로 기록하므로 반복 프로세스 조회가 필요 없다. 로컬 `CURATED_COMPLETE`는 DB 완료가 아니다. 최종 완료는 정확한 bundle SHA의 PostgreSQL PUBLISHED, NULL 정책, staging/loader scratch 정리까지 확인해야 한다. 표본 최고 사용량과 filesystem hard cap도 구분해 보고한다.

저장소에서 확인되는 운영 관측 경로는 `pickage-weekly.service` journal, 고정 컨테이너 이름(`pickage-weekly-run`, `pickage-curated-dispatch`), MinIO 상태/이벤트다. 배포 연결 시 자식 stdout/stderr를 기존 journal로 그대로 전달하고, 고정 이름에 연결된 정리·상태 확인 경로를 보존해야 한다. 임의의 새 컨테이너가 기존 서버 대시보드에 자동 등록된다는 증거는 없다. 저장소 밖에서 설정된 수집기와 실제 서버 표시 여부는 이번 로컬 검증 범위 밖이다.

## 완료된 앞 단계를 보존하는 repository 복구

일반 runner는 코드가 바뀐 뒤 같은 run ID를 재사용하지 않는다. 이번 repository의 전체 입력 복사 제거와 workspace 수명 수정에는 별도 복구 진입점 `run_snapshot --request /opt/request.json --recover-repository`를 사용한다. 기존 bounded 컨테이너 실행 예시의 Python 인자에만 이 옵션을 추가한다.

이 복구는 원래 요청·컨테이너 내부 작업 경로·실행환경이 동일하고, snapshot/package_version/downloads 체크포인트와 게시된 파일이 모두 검증될 때만 동작한다. 허용 코드 변경은 `repository_metrics/duckdb_transform.py`, `orchestration/workspace.py` 두 파일이다. 원래 request envelope와 완료된3개 체크포인트는 고치지 않는다. 별도 `recoveries/repository-bounded-v1.json`에 이전/현재 코드 계약, 원본 체크포인트 SHA, 복구기 SHA를 고정하고 이후 repository/package_snapshot/dependents 결과를 연결한다.

같은 복구의 재시도도 동일 receipt를 요구하며 이미 완료한 후속 단계를 재사용한다. 완료 bundle 재실행은 체크포인트와 receipt 일치를 검증한다. 임의의 코드 변경을 승인하거나 예전 manifest에 현재 코드 hash를 덧씌우는 기능은 아니다. 원본과 다른 입력·runtime·허용 범위 밖 코드에는 새 실행이 필요하다. 실제 복구 기록은 작업 로그35와 로컬 `C:/pgb4`에 남긴다.

repository 복구로 package_snapshot까지 완료한 뒤 dependents 준비가 실패한 경우에는 `--recover-dependents`를 사용한다. 이 경로는 이전 repository receipt의 SHA와 완료5개 체크포인트를 고정하고 dependents만 실행한다. 현재 변경 허용 파일은 `orchestration/dependents_parallel.py`, `version_dependents/historical_input.py`, `version_dependents/historical_production_events.py`, `version_dependents/historical_parallel_input.py`, `version_dependents/historical_production_quality.py`다. 실행에 필요한 raw manifest·대상 목록을 pinned SHA로 검증하며, 앞 단계의 입력을 다시 준비하지 않는다. 새 `dependents-bounded-v2` receipt가 이전 receipt와 새 코드/복구기 hash를 연결한다. 실패한 v1 receipt는 유지한다. 게시 직전에 앞5개 checkpoint와 실제 산출물 SHA를 다시 검증한다. 두 recovery 옵션은 함께 사용할 수 없다.

실행기·검증기 실패뿐 아니라 게시 도중 실패도 FAILED 상태와 이벤트로 기록한다. 이미 완료된 dependents 체크포인트 또는 전체 bundle은 검증한 뒤 재사용하고 current 포인터/상태 기록을 복구한다. 과거 helper hash를 현재 파일 hash로 바꾸지 않으며, 같은 receipt로 다시 시작할 때는 그 receipt에 고정한 소스를 사용한다. 실제 두 번째 복구의 소스·입력·상태는 `C:/pgb5`에 보존한다.
