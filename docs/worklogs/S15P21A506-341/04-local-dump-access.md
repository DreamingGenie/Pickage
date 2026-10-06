# 로컬 원본 DB 덤프 연결 준비

이 문서는 해당 단계 당시의 계획·검증 기록이다. 이후 서버 복원과 서비스 DB 전환을 완료했으며, 현재 상태와 검증 범위는 [최종 결과](12-final-result.md)를 따른다. 당시 실패·미실행 기록은 이력으로 보존한다.

## 목적

`pickage-267-validation`은 `network=none`이고 호스트 포트를 공개하지 않으므로 호스트에서 바로 `pg_dump`를 실행할 수 없다. `local_dump_client.py`는 원본 컨테이너의 데이터 볼륨을 다시 마운트하거나 원본 컨테이너를 재생성하지 않고, 원본과 네트워크 네임스페이스만 공유하는 PostgreSQL 클라이언트를 준비한다.

보조 컨테이너의 호스트 마운트는 지정한 archive 디렉터리 하나(`/work`)뿐이다. 원본의 비밀번호가 설정된 환경에서는 비밀번호를 명령행에 넣지 않고 subprocess 환경의 `PGPASSWORD`와 Docker의 `--env PGPASSWORD` 전달만 사용한다. 출력과 JSON 결과에는 비밀번호를 포함하지 않는다.

## 실행

```powershell
python scripts/service-data-migration/local_dump_client.py `
  --archive-dir data/service-data-migration/341/local-dump-probe start

python scripts/service-data-migration/local_dump_client.py probe
python scripts/service-data-migration/local_dump_client.py dump-schema
python scripts/service-data-migration/local_dump_client.py stop
```

`start`는 동일한 작업 라벨과 원본 이름을 가진 보조 컨테이너가 있으면 설정을 확인한 뒤 재사용한다. `stop`은 이 라벨과 원본 라벨이 모두 일치할 때만 해당 이름의 보조 컨테이너를 제거한다.

전체 덤프는 준비된 보조 컨테이너를 기존 `transfer.py dump`의 `--container`로 사용한다. 현재 보조 컨테이너는 `local-dump-probe`를 `/work`로 마운트했으므로, 실제 archive도 그 디렉터리 아래에 둔다. 다른 실행 디렉터리를 사용하려면 기존 보조 컨테이너를 `stop`한 뒤 새 `--archive-dir`로 `start`해야 하며, 실행 중인 보조 컨테이너의 마운트는 자동으로 바꾸지 않는다.

```powershell
python scripts/service-data-migration/transfer.py dump `
  --container pickage-341-local-dump-client-pickage-267-validation `
  --source-db pickage_267_full_defaulted `
  --archive-dir data/service-data-migration/341/local-dump-probe/archive `
  --container-archive-dir /work `
  --jobs 4 `
  --compression zstd:1
```

## 확인 결과

- 원본 컨테이너 상태: 실행 중, `network=none`, 데이터 볼륨 `/var/lib/postgresql/data` 하나만 유지
- 보조 컨테이너 연결: `127.0.0.1` 공유 네트워크로 `pg_isready` 성공
- PostgreSQL: `pickage_267_full_defaulted` 연결 성공
- 원본 `package_version_snapshot` 행 수: `1,007,084,608`
- zstd 압축 옵션: 실제 `pg_dump --compress=zstd:1 --schema-only` 실행 성공
- 선택 테이블·자식 파티션 스키마 덤프: `271,351` bytes 생성
- 전체 데이터 덤프와 서버 접근은 이 확인에서 실행하지 않음

생성된 `data/service-data-migration/` 아래 파일은 실행 산출물이며 Git에 커밋하지 않는다.
