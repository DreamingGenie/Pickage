# Bounded PostgreSQL 개념검증

이 runtime은 별도 PostgreSQL 컨테이너의 WAL·staging·SQL 임시 파일을 전용 ext4 loop image에 제한한다. 최종 `PGDATA`는 별도 named volume에 보존한다. 현재 최대17,000,000,000bytes이며 전처리28GB+loader4GB+로그0.5GB와 동시에 존재해도 역할별 하나의 volume이라는 전제에서 합계49.5GB다. 기존 운영 DB를 자동 이전하거나 기존 image를 포맷하는 기능이 아니다.

`BOUNDED_POSTGRES_BYTES`로 상한을 더 낮출 수 있다(기본·최대17GB). 기존40GB image는 크기 불일치로 거부하며 자동 축소하지 않는다. 과거 로컬 전체 적재는40GB cap에서 성공했고 실제 DB processing 표본 최고14.78GB였다. 이 결과가17GB cap에서의 전체 적재 성공을 증명하지는 않는다. offline 이전 backup도 처리 공간이므로 전처리·loader를 정지한 별도 이전 단계에서 원본 WAL+대상17GB+로그를 합산해야 한다.

기존 DB를 연결할 때는 `POSTGRES_BASE`를 기존 DB와 같은 PostgreSQL·libc/ICU 기반 이미지 digest로 빌드하고 `POSTGRES_USER`, `POSTGRES_DB`를 지정한다. 기본 digest는 로컬 baseline과 같은glibc2.41 이미지다. 다른 환경에 임의로 적용하지 않는다. wrapper는 TCP 준비 후 `datcollversion`과 `pg_database_collation_actual_version`을 비교하고 불일치하면 종료한다. 경고를 없애려고 `REFRESH COLLATION VERSION`만 실행해서는 안 된다. 기존 인덱스가 다른 정렬 규칙으로 변경됐을 수 있으므로 호환 환경 복원과 인덱스 검증이 먼저다.

```bash
CTX=/srv/pickage/bounded-build-context
mkdir -p "$CTX/pipeline/preprocessing/runtime"
cp pipeline/preprocessing/runtime/Dockerfile.postgres \
   pipeline/preprocessing/runtime/bounded_postgres.sh \
   pipeline/preprocessing/runtime/resource_budget.sh \
   pipeline/preprocessing/runtime/postgres_import_wal.sh "$CTX/pipeline/preprocessing/runtime/"
docker build -t pickage-postgres:bounded-<commit> \
  -f "$CTX/pipeline/preprocessing/runtime/Dockerfile.postgres" "$CTX"
docker volume create pickage-postgres-bounded-volume
docker volume create pickage-postgres-bounded-data
docker run --rm --name pickage-postgres-bounded --privileged --read-only \
  --tmpfs /run:size=64m --tmpfs /tmp:size=64m \
  --memory=4g --memory-swap=4g --cpus=2 \
  --log-opt max-size=10m --log-opt max-file=3 \
  -e POSTGRES_DB=pickage -e POSTGRES_USER=pickage \
  -e POSTGRES_PASSWORD=local-only \
  -v pickage-postgres-bounded-volume:/var/lib/pickage-postgres-bounded \
  -v pickage-postgres-bounded-data:/var/lib/postgresql/data \
  -p 127.0.0.1:15442:5432 pickage-postgres:bounded-<commit>
```

`--privileged`는 loop mount를 위한 컨테이너 전체 설정이다. PostgreSQL은 공식 entrypoint의 `gosu postgres`로 별도 uid에서 실행된다. loop mount를 허용하지 않는 환경에서는 이 실행기가 중단된다.

초기화 시 `POSTGRES_INITDB_WALDIR`가 `/run/pickage-postgres-bounded/wal`을 가리킨다. 기존 PGDATA를 가져올 때는 `POSTGRES_IMPORT_MODE=offline`을 명시해야 하며, clean shutdown·PG_VERSION 16·WAL checksum 검증을 통과한 경우에만 backup과 symlink가 생성된다. 이후 동일 컨테이너 재시작에서는 정확한 bounded WAL symlink를 재사용한다. 다른 WAL 경로는 거부한다.

WAL만 옮기면 staging과 SQL 정렬 임시 파일은 제한되지 않는다. 적재기를 시작하기 전에 Flyway 테이블이 있는 **지정한 bounded 실험 DB**에 다음 설정을 적용한다. 기존 staging이 비어 있고 작을 때만 테이블·인덱스를 옮기며, 서비스 테이블은 이동하지 않는다. DB와 사용자는 실제 loader 설정과 일치시킨다.

```bash
docker exec -i pickage-postgres-bounded psql -X -U pickage -d pickage \
  < pipeline/preprocessing/runtime/configure_bounded_staging.sql
```

새 loader 연결부터 `temp_tablespaces=curated_work`가 적용된다. 8GB `temp_file_limit`도17GB filesystem 안에서 사용하며 별도로8GB를 추가 배정하지 않는다. offline 이전 시 WAL backup과 복사본이 잠시 함께 있으므로 그 크기도 합산한다. checksum·기동·기존 완료 행·CHECKPOINT 검증 후 backup을 정리한 뒤에만 loader를 시작한다.

재시작 회귀 검증은 `python pipeline/preprocessing/runtime/test_postgres_restart.py --image pickage-postgres:bounded-<commit>`로 실행한다. 테스트가 만든 별도 fixture 컨테이너·volume만 사용한다.

실험에서는 새 volume만 사용해 ENOSPC fixture를 만들고, 정상 종료 후 같은 image를 재마운트해 마지막 fixture 행이 보존되는지 확인한다. image는 WAL/staging 내구성을 위해 자동 삭제하지 않는다. PostgreSQL은 WAL 디스크가 가득 차면 정상 처리와 복구가 멈출 수 있으므로, 실제 운영 적용은 별도 승인·백업·용량 검증 뒤에만 한다. 참고: https://www.postgresql.org/docs/16/disk-full.html
