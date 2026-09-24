# PostgreSQL 적재기 bounded runtime

이 runtime은 Curated PostgreSQL 적재기만 별도 실행한다. loader 전용 ext4 loop image는 최대 4,000,000,000 bytes이며, Java heap은 512MiB, DuckDB native memory는 4GB로 고정한다. 전처리 scratch를 해제한 뒤 실행한다. 이 wrapper가 직접 제한하는 것은 loader 공간이며, DB WAL/staging/temp와 나머지 로그·임시공간은 호출자가 별도로 제한하고50GB 합계에 포함해야 한다. 로컬 실험의40GB DB cap과 검증용 최대42GB 설정을 운영 반복 실행의 합산 예산으로 그대로 사용하지 않는다.

```bash
CTX=/srv/pickage/bounded-loader-context
mkdir -p "$CTX/pipeline/preprocessing/runtime"
cp pipeline/preprocessing/runtime/Dockerfile.loader \
   pipeline/preprocessing/runtime/bounded_workspace.sh \
   pipeline/preprocessing/runtime/resource_budget.sh \
   pipeline/preprocessing/runtime/run_loader.sh "$CTX/pipeline/preprocessing/runtime/"
docker build -t pickage-curated-loader:bounded-<commit> \
  -f "$CTX/pipeline/preprocessing/runtime/Dockerfile.loader" "$CTX"
docker run --rm --name pickage-bounded-loader --privileged --read-only --tmpfs /tmp:size=64m \
  --tmpfs /run:size=16m --memory=8g --memory-swap=8g --cpus=2 \
  --log-opt max-size=10m --log-opt max-file=3 \
  -v pickage-loader-work:/var/lib/pickage-bounded \
  -v "$PWD/curated-loader.jar:/opt/loader/curated-loader.jar:ro" \
  -v "$PWD/loader.properties:/opt/loader/loader.properties:ro" \
  -e BOUNDED_WORKSPACE_BYTES=4000000000 \
  -e LOADER_PROPERTIES=/opt/loader/loader.properties \
  pickage-curated-loader:bounded-<commit> \
  /usr/local/bin/run_loader
```

wrapper는 임시 파일과 작업 디렉터리를 bounded workspace 아래에만 만들고, `DB_RESULT` 한 줄을 stdout으로 남긴다. Java 종료 코드는 그대로 반환한다. 컨테이너 메모리 상한은 8GiB지만 loader filesystem scratch cap은 10진수4GB이며 Java heap은 512MiB다. 정상·실패 종료 후 supervisor가 unmount하고 자동 해제된 loop 연결을 확인한 뒤 scratch image를 삭제한다. jar와 properties는 read-only mount로만 제공한다.

`loader.properties`의 JDBC와 MinIO 주소는 컨테이너 안에서 도달 가능한 주소여야 한다. 같은 Docker network에서는 서비스 별칭을 쓰고, 운영의 서로 다른 EC2 간에는 도달 가능한 사설 주소를 쓴다. 로컬 Windows의 `host.docker.internal` 포트 경유는 실험에서 전송 병목이 있었으므로 같은 호스트의 MinIO/DB에는 직접 Docker network 연결을 사용했다. 운영 주소와 자격증명은 [backend/CURATED_LOAD.md](../../../backend/CURATED_LOAD.md)의 계약으로 주입한다.

이 예시의 단일 실행에는 `mode=once`, 완료 bundle prefix와 manifest SHA가 필요하다. `mode=poll`은 별도 상시 실행 방식이며, MinIO COMPLETE만 보고 즉시 시작하면 전처리 scratch가 아직 해제되지 않은 순간과 겹칠 수 있다. 과거36/40/4GB 프로파일은 전처리 종료와 scratch 제거 후 loader를 시작해야 한다. 현재28/17/4GB는 역할별 컨테이너·볼륨을 하나씩 유지하면 동시에 실행해도 로그 예약을 포함해49.5GB다. 2026-09-23 로컬에서 새17GB DB cap으로8/31 초기 적재와9/14 전체 weekly 적재를 모두 성공시켰다. DB 처리 공간 표본 최고14.783GB, loader0.388GB이며 두 실행 모두exit0/OOM없음과scratch삭제를 확인했다. 실제 서버 실행은 하지 않았다. Java exit0 외에도 `DB_RESULT`와 정확한 bundle SHA의 DB PUBLISHED 이력을 확인한다.
