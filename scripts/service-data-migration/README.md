# 서비스 데이터 이관 도구

`transfer.py`는 다섯 개의 서비스 테이블과 `package_version_snapshot`의 날짜별 자식 파티션을 하나의 PostgreSQL directory dump로 만들고, 파일별 SHA-256 검증 후 별도 후보 DB에 복원하기 위한 도구다.

이 도구는 서버 DB를 생성·삭제하거나 API의 `DB_URL`을 바꾸지 않는다. 후보 DB는 별도 준비 단계에서 만들어야 하며 이름은 반드시 `pickage_import_341_<run-id>` 형식이어야 한다. 후보 DB에 대상 테이블이 하나라도 있으면 복원을 거부한다. 실패한 복원은 같은 DB에 재시도하지 말고 새 후보 DB를 준비한다.

## 덤프

로컬 PostgreSQL 클라이언트에서 실행한다.

```powershell
python scripts/service-data-migration/transfer.py dump `
  --source-db pickage_267_full_defaulted `
  --archive-dir data/service-data-migration/341/run-20260914/archive `
  --jobs 4 `
  --compression zstd:1
```

Docker 안의 `pg_dump`를 사용할 때는 archive 경로가 컨테이너에도 마운트되어 있어야 한다. `--archive-dir`는 해시를 계산할 호스트 경로이고, `--container-archive-dir`는 archive 디렉터리를 담은 컨테이너 쪽 부모 경로다. 예를 들어 호스트의 `.../archive`가 컨테이너에서 `/work/archive`라면 `/work`를 지정한다. 덤프 후에는 컨테이너의 모든 archive 파일 SHA-256도 호스트 manifest와 비교한다.

```powershell
python scripts/service-data-migration/transfer.py dump `
  --container pickage-267-validation `
  --source-db pickage_267_full_defaulted `
  --archive-dir data/service-data-migration/341/run-20260914/archive `
  --container-archive-dir /transfer
```

`dump`는 기존 비어 있지 않은 archive를 덮어쓰지 않는다. `zstd:1`을 지원하지 않는 클라이언트에서는 `gzip:1`을 별도 새 디렉터리에 사용한다. 압축 directory dump는 중간 재개를 지원한다고 가정하지 않으며, 실패하면 새 archive를 만든다.

## 검증

```powershell
python scripts/service-data-migration/transfer.py verify `
  --archive-dir data/service-data-migration/341/run-20260914/archive
```

검증은 manifest의 파일 목록·크기·SHA-256과 `pg_restore --list`의 schema/table allowlist를 확인한다. 허용 대상은 `public`의 다섯 root table과 `vd193_reload_20260912_ready01.dYYYYMMDD` 자식 테이블뿐이다. archive에 다른 대상이 있으면 복원 전에 실패한다.

## 후보 복원

기존 서버 DB를 백업·복제한 후보에 같은 배포 revision의 Flyway validate(target=1)를 먼저 수행한다. `prepare_candidate.sql`은 후보 이름·실제 V1 성공 이력·소유권·다섯 테이블의 0행을 확인한 뒤 후보의 빈 테이블만 트랜잭션으로 제거한다. 데이터가 있거나 V2 이상인 후보는 거부한다. 원래 서버 DB에 실행하지 않는다.

`restore`는 V1 이력만 남은 후보를 받으며, 다른 애플리케이션 테이블이 있으면 거부한다. 아래 `--source-db`는 archive를 만든 원본 DB 이름이다. 서버에서는 `--user pickage` 등 실제 복원 역할을 지정한다.

```powershell
python scripts/service-data-migration/transfer.py restore `
  --archive-dir data/service-data-migration/341/run-20260914/archive `
  --candidate-db pickage_import_341_20260914a `
  --source-db pickage_267_full_defaulted `
  --service-db pickage `
  --jobs 2
```

복원은 `pre-data → data → post-data` 순서로 실행하고 각 단계의 시간을 `<후보DB>.restore-status.json`에 기록한다. 완료 상태 `RESTORED_UNVERIFIED`는 pg_restore 완료만 뜻하며 `ready_for_service=false`다. 이후 Flyway·구조·데이터·API 검증이 필요하다. 실패한 후보에 대한 이력은 덮어쓰지 않으며 새 후보 이름으로 다시 시작한다. 테이블별 중간 재개 기능은 아직 없다.

Docker 실행에서는 dump와 동일하게 `--container` 및 `--container-archive-dir`를 지정한다. 명령에는 비밀번호를 넣지 않으며 PostgreSQL의 `.pgpass` 또는 Docker 실행 환경의 기존 인증 방식을 사용한다. `PGHOST`/`PGPORT` 등의 환경은 명령을 실행하는 쪽에 설정한다. 호스트의 환경변수가 기존 컨테이너에 자동 전달되지는 않는다.

V4가 생성하는 세 인덱스가 archive에 이미 있으면 복원 전에 차단한다. 이번 구현은 해당 인덱스의 자동 제외를 지원하지 않는다. 기존 V4나 Flyway 이력을 수정해 우회하지 않는다.

Flyway V2~V6 적용 후 `validate_structure.sql`로 부모/자식 컬럼·기본값·제약·인덱스 상태를 검사한다. 이 검사는 행 수·합계 비교를 대신하지 않는다. 파일럿에서는 다섯 테이블의 모든 값을 비교하지만, 전체 데이터의 검증 기준 시점 고정과 전수 집계는 전체 실행 준비 단계에서 수행해야 한다.

## 로컬 통합 시험

Docker, Java 17 이상, Python 표준 라이브러리와 기존 애플리케이션의 Flyway/JDBC 런타임 JAR를 사용한다. 패키지 설치나 서버 접속은 하지 않는다.

```powershell
python -m unittest tests.test_service_data_migration -v
./scripts/service-data-migration/run-local-pilot.ps1 -Python python
```

`run-local-pilot.ps1`은 기록된 Flyway 11.14.1 등의 Gradle 캐시를 사용한다. 다른 환경은 `PICKAGE_341_JAVA_CLASSPATH`에 호환 런타임 JAR 경로들을 구분자로 연결해 지정한다. `LocalFlyway.java`는 loopback의 341 테스트 DB만 허용하는 시험용 실행기이며 서버 마이그레이션 실행기가 아니다.

시험은 고유 이름의 PostgreSQL 컨테이너(메모리 2GiB, loopback 임의 포트)를 만들고 종료 시 그 컨테이너와 볼륨만 제거한다. 기존 로컬 DB에서 react/pino/winston과 최근 날짜 세 개를 읽는다. 출력 CSV·압축 archive·로그·result.json은 Git에서 제외되는 `data/service-data-migration/`에 남는다.

이 시험은 FK가 닫힌 작은 표본의 정확성을 확인하는 용도다. 소스 추출은 여러 읽기 쿼리이므로 표본 추출 중 소스 쓰기가 없어야 한다. 전체 덤프는 한 pg_dump의 동기화 스냅샷을 사용한다. 전체 서버 소요 시간으로 표본 시간을 환산하지 않는다.

## 아직 실행하지 않은 범위

- 원본 컨테이너의 실제 대용량 archive 저장 경로/클라이언트 연결 준비. 위 Docker 예시는 해당 경로가 이미 마운트된 경우이며 기존 컨테이너의 마운트를 자동 변경하지 않는다.
- SSH/SFTP 이어받기 전송, 기존 서버 백업·후보 DB 생성, 서버 Flyway 실행기, 서비스 연결 전환.
- 서버 자원 측정, 전체 데이터 검증, 실패한 COPY의 테이블별 재개. 따라서 현재는 전체 이관 준비 완료 상태가 아니다.
