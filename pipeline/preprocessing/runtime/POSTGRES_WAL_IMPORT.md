# 기존 PostgreSQL WAL 이전 절차

이 도구는 운영 DB에 자동 적용되지 않는 offline migration 준비물이다. `POSTGRES_IMPORT_MODE=offline`을 명시하고, PostgreSQL이 정지된 별도 fixture에서만 실행한다.

사전 조건은 PostgreSQL 16, `pg_controldata`의 `Database cluster state: shut down`, 원본 `pg_wal`이 symlink가 아닌 내부 디렉터리, 비어 있는 bounded WAL target이다. 원본 WAL 파일을 bounded target으로 복사한 뒤 파일별 SHA-256 manifest를 비교하고, 성공한 경우에만 원본 디렉터리를 `pg_wal.import-backup-<UTC>`로 rename하고 target symlink를 게시한다. backup은 새 runtime이 기동하고 `CHECKPOINT`와 row 보존을 확인할 때까지 삭제하지 않는다.

```bash
POSTGRES_IMPORT_MODE=offline /usr/local/bin/postgres_import_wal
```

이 helper는 bounded PostgreSQL 컨테이너 내부의 고정 경로만 사용한다. 원본은 `/var/lib/postgresql/data`, 대상은 `/run/pickage-postgres-bounded/wal`이며 `PGDATA`·target 경로를 환경변수로 바꾸지 않는다. `bounded_postgres.sh`가 `POSTGRES_IMPORT_MODE=offline`을 받고 기존 WAL이 내부 디렉터리일 때만 mount 후 호출한다. 이미 정확한 bounded 경로의 symlink인 경우에는 재시작 시 다시 이전하지 않는다.

원본 PGDATA와 backup은 read-only 백업 경로로 별도 보존하고, 실제 서비스 볼륨에는 이 명령을 직접 실행하지 않는다. 현재 `C:/pg914r3` 실험 DB나 서버 DB에는 적용하지 않았다.
