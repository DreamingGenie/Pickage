# 01. 작업 정의와 변경 범위

상태: **구현·전체 적재·읽기 전용 검증·동일 입력 재실행 검증 완료** · 작성 기준: 사용자 요구사항과 아래에 기록한 확정 계약 · [문서 안내](README.md)

소스 입력 검증과 격리 PostgreSQL의 경계값·실패·재시도·Curated 생성기 연계 샘플은 통과했고, 전체
서비스 DDL은 사용자가 제공한 V1 계약과 동일하며 `version.dependency`는 `NOT NULL`이다.
근거는 [`test_input.py`](../../../pipeline/postgresql/test_input.py), [`test_load.py`](../../../pipeline/postgresql/test_load.py),
[`test_postgres.py`](../../../pipeline/postgresql/test_postgres.py), [`test_integration.py`](../../../pipeline/postgresql/test_integration.py)의
실행 결과와 [05 결과 기록](05-results.md)의 V-002다.
초기 nullable 가정의 전체 적재는 사용자 DDL 계약을 반영하기 전에 취소했으며 `FAILED`와 rollback을 확인했다.
이후 기본 JSON 대체와 품질 이력 기록 정책을 반영한 새 contract로 package 11,080,940행과 version 54,188,349행을 커밋했다. dependency SQL NULL 25건은 기본 JSON으로 대체됐고 10개 package에 대한 품질 이력이 기록됐다. 전체 입력·DB 대조는 [full-load](evidence/full-load.json), [full-data](evidence/full-data.json)와 [05 결과와 검증](05-results.md)에 남겼다.

## 목표와 필요한 작업

승인된 Curated Parquet의 package·version을 로컬 PostgreSQL에 검증 후 적재하고, 후속 적재에서도 쓸 수 있는 실행 이력·트랜잭션·재실행 보호 기반을 마련한다.

| 작업 ID | 해야 하는 일 | 연결 계획 |
| --- | --- | --- |
| T-01 | 선행 Curated 구현·Flyway 스키마 통합과 컬럼·타입·식별자 계약 확인 | P-01 |
| T-02 | 승인 manifest, `_SUCCESS`, 서비스 파일 목록·크기·해시·스키마 검증 | P-02 |
| T-03 | 실행 이력·dataset 상태·DB의 현재 게시 정보 설계 및 신규 마이그레이션 | P-03 |
| T-04 | 실행별 staging과 COPY, 필드·키·참조 검증 구현 | P-04 |
| T-05 | 트랜잭션 반영, 실패 이력, 재시도·동시 실행·과거 입력 보호 구현 | P-05 |
| T-06 | 샘플·경계값·오류 주입·전체 적재 검증 | P-06 |
| T-07 | 설치·실행·복구 및 실제 결과를 팀원용 문서로 정리 | P-07 |

## 포함·제외 범위

| 구분 | 범위 |
| --- | --- |
| 입력 | 명시적으로 선택하고 승인 여부를 검증한 run의 `package/data`, `version/data` |
| 출력 | 로컬 PostgreSQL `package`, `version`, 필요한 staging·공통 실행 관리 스키마 |
| 변경 허용 영역 | 적재 파이프라인, MinIO 읽기, 신규 Flyway 마이그레이션, 검증·실행 문서 |
| 제외 | 다른 세 서비스 테이블 적재, 지표 계산, 원본 재수집, Spark 전처리 이관, 운영 서버 배포 |
| 보존 조건 | 기존 V1 수정 금지, Curated ID 보존, MinIO 원본·완료 표시 보존, 실제 데이터 DB에서 TRUNCATE·샘플 seed 실행 금지 |
| 서비스 적재 제외 파일 | `package_ids/data`, `quality/*` |

## 변경 예상 파일과 영향

구체적인 경로·함수·테이블명은 코드 확인 후 채운다. 예상 변경은 완료 시 [최종 변경 목록](05-results.md)과 대조한다.

| 파일 / 모듈 / 테이블 | 현재 역할·상태 | 예정 변경 | 영향받는 호출부·데이터 | 호환성·복구 고려 |
| --- | --- | --- | --- | --- |
| `pipeline/postgresql/input.py` 및 입력 테스트 | 신규 | 승인 run 선택·해시·파일·스키마·값 검증과 COPY 전송 파일 생성 | Curated 서비스 파일 읽기 | 기존 storage 재사용, MinIO 쓰기 없음 |
| `pipeline/postgresql/postgres.py` 및 DB 테스트 | 신규 | psql 세션·staging·키 검증·원자적 게시·실패/재실행 보호 | package·version·공통 실행 이력 | 기존 Python 의존성과 Docker psql 사용 |
| `pipeline/postgresql/load.py` 및 CLI 테스트 | 신규 | 명시적 run/DB/실행 ID를 받는 실행 진입점과 로컬 결과 기록 | 로컬 배치 실행 | 검증 전용 모드 제공, DB 대상을 명시 |
| `backend/src/main/resources/db/migration/V2__add_curated_load_execution.sql` | 신규 | 공통 실행 관리 스키마만 추가 | 새 마이그레이션을 적용한 DB | V1 서비스 DDL 불변, `version.dependency NOT NULL` 유지, ISS-006 참조 |
| `scripts/verify_package_version_load.py` | 신규 | 완료된 전체 적재의 입력 해시·건수·NULL 집계·필드 표본을 읽기 전용으로 대조 | 전용 검증 DB·로컬 입력 캐시 | 서비스 데이터 쓰기 없음 |
| `pipeline/postgresql/README.md`, 파이프라인·로컬 안내, 이 작업 기록 | 추가·수정 | 실행·실패 복구·검증 근거·후속 계약 | 팀원 실행·인계 | 실제 측정과 미검증 항목 구분 |

## 착수 전에 확인한 계약

| 항목 | 기록할 내용 | 현재 판정 / 근거 |
| --- | --- | --- |
| 선행 구현 통합 | Curated 출력과 Flyway 대상의 실제 연결 | 확인. Curated 출력은 `transform.py`의 `package/data`·`version/data` export([`pipeline/curated/transform.py`](../../../pipeline/curated/transform.py)), 입력기는 이 두 서비스 경로만 선택([`pipeline/postgresql/input.py`](../../../pipeline/postgresql/input.py))한다. V1 대상은 [`V1__init.sql`](../../../backend/src/main/resources/db/migration/V1__init.sql), 적재 이력·NULL 보완은 [`V2__add_curated_load_execution.sql`](../../../backend/src/main/resources/db/migration/V2__add_curated_load_execution.sql)이다. 시작 HEAD `2dccbf58774cc073b0c31859f634e05c0f91a6e7`에 선행 구현이 포함되어 별도 merge 없이 진행했다. |
| 행 단위와 식별자 | package·version 행의 grain과 동일성 | 확인. package는 패키지명 하나, version은 `(package_id, version)` 하나다. Curated가 `package_ids`에서 ID를 유지·부여하고([`transform.py`](../../../pipeline/curated/transform.py)), 출력 FK·version 중복을 검사한다([`transform.py`](../../../pipeline/curated/transform.py)). PostgreSQL PK·UNIQUE·FK는 [`V1__init.sql`](../../../backend/src/main/resources/db/migration/V1__init.sql), staging 유일성·FK는 [`postgres.py`](../../../pipeline/postgresql/postgres.py)에서 재검사한다. |
| 컬럼 매핑 | 원천 물리 컬럼, Curated 물리 컬럼, PostgreSQL 타입·NULL·빈 값·JSON·길이/NUL 규칙 | 확인. 아래 [package/version 컬럼 매핑](#packageversion-컬럼-매핑)에 Curated Parquet의 정확한 컬럼명·타입과 원천 물리 컬럼, PG 대상 및 예외를 기록했다. 입력 스키마 상수는 [`pipeline/postgresql/input.py`](../../../pipeline/postgresql/input.py)이고, 실제 필드 검사는 [`input.py`](../../../pipeline/postgresql/input.py)이다. |
| 시간 의미 | snapshot 날짜, 공급자 관측 시각, version 배포 시각, DB 실행 시각 구분 | 확인. `--snapshot`/경로 날짜는 DATE이고, Curated `report.snapshot_timestamp`는 timezone 없는 공급자 `SnapshotAt` 마이크로초 값이다([`input.py`](../../../pipeline/postgresql/input.py), [`transform.py`](../../../pipeline/curated/transform.py)). `version.published_at`은 별도 원천 필드이며, 실행 `created_at`·`updated_at`·`published_at`은 DB clock 값이다([`V2__add_curated_load_execution.sql`](../../../backend/src/main/resources/db/migration/V2__add_curated_load_execution.sql)). |
| 게시·실행 계약 | 입력 run, 실행 ID, manifest·계약 해시, MinIO 완료와 DB 게시 상태 구분 | 확인. `_SUCCESS`가 manifest SHA-256과 일치하고 `status=PASSED`, `verification=GET_SHA256_ALL_FILES`인 run만 선택한다([`input.py`](../../../pipeline/postgresql/input.py)). 실행 report는 `PREPARING`에서 시작하고([`load.py`](../../../pipeline/postgresql/load.py)), DB는 `etl_load_execution`·`etl_load_attempt`·`etl_dataset_current`를 게시 트랜잭션에 기록한다([`postgres.py`](../../../pipeline/postgresql/postgres.py)). |
| 기존 DB와 충돌 | seed·기존 데이터, ID/name 충돌, 오래된 입력·동시 실행·재검증 | 확인. 기존 package ID/name 충돌은 게시 전에 거부하고([`postgres.py`](../../../pipeline/postgresql/postgres.py)), 오래된 snapshot·연결되지 않은 같은 snapshot·동시 실행 lock을 검사한다([`postgres.py`](../../../pipeline/postgresql/postgres.py)). 통합 테스트는 애플리케이션 DB·seed와 분리된 DB만 만든다([`test_integration.py`](../../../pipeline/postgresql/test_integration.py)). |

## package/version 컬럼 매핑

아래 표에서 `Curated 물리 컬럼`은 PostgreSQL로 보내기 직전의 승인 Parquet 컬럼명·DuckDB
논리 타입이다. `원천 물리 컬럼`은 Curated가 읽는 Bronze Parquet의 실제 컬럼명이며, Curated
변환으로 이름·ID·JSON·저장소 값이 바뀌는 경우 그 관계를 함께 적었다. PostgreSQL loader는
표에 적힌 모든 대상 컬럼을 COPY 열 목록으로 명시한다([`pipeline/postgresql/postgres.py`](../../../pipeline/postgresql/postgres.py));
DB 컬럼 DEFAULT에 누락 값을 맡기지 않는다.

| 대상 행 / Curated 물리 컬럼(정확한 이름·타입) | 원천 물리 컬럼과 변환 | PostgreSQL 대상 | NULL·빈 값·JSON·검증 기준 |
| --- | --- | --- | --- |
| `package.package_id` / `package_id INTEGER` | `raw_versions.Name VARCHAR`를 ID 대장 `package_ids.package_id INTEGER`로 연결. 새 ID는 기존 최대값 다음에 부여하고 기존 ID는 유지([`transform.py`](../../../pipeline/curated/transform.py)). | `public.package.package_id INT NOT NULL PRIMARY KEY` | NULL·0 이하·`INT` 초과 거부([`input.py`](../../../pipeline/postgresql/input.py)); 임의 재발급하지 않음. |
| `package.name` / `name VARCHAR` | `raw_versions.Name VARCHAR`의 유효 릴리스 집합을 패키지 단위로 중복 제거한 값(`packages.name`). | `public.package.name VARCHAR(300) NOT NULL UNIQUE` | NULL·trim 후 빈 문자열·NUL·300자 초과 거부. 빈 문자열은 유효한 package 이름으로 보존하지 않음. |
| `package.repo_url` / `repo_url VARCHAR` | `raw_versions.source_repo VARCHAR`를 정규화하고 eligible version의 `ordinal DESC`, `published_at DESC NULLS LAST`, `Version ASC`로 한 주소를 선택([`transform.py`](../../../pipeline/curated/transform.py)). 후보가 없으면 Curated NULL. | `public.package.repo_url VARCHAR(200)` | NULL 허용. loader는 NULL이 아닌 값의 200자 초과·NUL을 거부하지만 빈 문자열 자체는 별도 금지하지 않는다([`input.py`](../../../pipeline/postgresql/input.py)); Curated 정규화 결과와 구분한다. |
| `version.version` / `version VARCHAR` | `raw_versions.Version VARCHAR`의 eligible 릴리스 값. | `public.version.version VARCHAR(100) NOT NULL`, `(package_id, version)` PK 일부 | NULL·trim 후 빈 문자열·NUL·100자 초과 거부([`input.py`](../../../pipeline/postgresql/input.py)). 빈 문자열을 NULL로 바꾸지 않는다. |
| `version.package_id` / `package_id INTEGER` | `raw_versions.Name`을 `package_ids.name`으로 매핑한 ID. | `public.version.package_id INT NOT NULL`, `FK_PACKAGE_VERSION` | NULL·범위 오류·package 출력에 없는 ID 거부. |
| `version.published_at` / `published_at TIMESTAMP` | `raw_versions.published_at TIMESTAMP`; snapshot 이후 릴리스만 제외하고 NULL은 eligible로 유지([`transform.py`](../../../pipeline/curated/transform.py)). | `public.version.published_at TIMESTAMP` | NULL 보존. timezone을 붙이거나 snapshot 시각으로 채우지 않는다. COPY는 `%Y-%m-%d %H:%M:%S.%f`로 마이크로초까지 포맷([`input.py`](../../../pipeline/postgresql/input.py)). |
| `version.ordinal` / `ordinal BIGINT` | `raw_versions.ordinal BIGINT`를 `BIGINT`로 명시 변환. | `public.version.ordinal BIGINT NOT NULL` | NULL·음수 거부. V1의 `DEFAULT 0`은 loader가 사용하지 않으며, 입력 ordinal을 항상 COPY한다([`postgres.py`](../../../pipeline/postgresql/postgres.py)). |
| `version.description` / `description VARCHAR` | `raw_versions.Description VARCHAR`; NUL이 포함된 값은 Curated에서 해당 필드만 NULL로 변환하고 `quality/metadata_issues`에 기록([`transform.py`](../../../pipeline/curated/transform.py)). | `public.version.description TEXT` | NULL과 빈 문자열은 구분해 보존. loader 단계에서 남은 NUL은 거부([`input.py`](../../../pipeline/postgresql/input.py)). |
| `version.licenses` / `licenses JSON` | `raw_versions.Licenses VARCHAR[]`를 `to_json`으로 JSON 값으로 변환([`transform.py`](../../../pipeline/curated/transform.py)). | `public.version.licenses JSON` | SQL NULL, JSON `null`, `[]`, `{}`를 합치지 않는다. NULL이 아닌 값은 `json_valid` 검사([`input.py`](../../../pipeline/postgresql/input.py)). |
| `version.deprecated` / `deprecated VARCHAR` | `raw_versions.Deprecated VARCHAR`를 문자열로 유지. | `public.version.deprecated TEXT` | NULL과 빈 문자열은 구분해 보존. NUL은 Curated/loader 검증에서 거부([`transform.py`](../../../pipeline/curated/transform.py), [`input.py`](../../../pipeline/postgresql/input.py)). |
| `version.dependency` / `dependency JSON` | `raw_requirements.Dependencies`, `PeerDependencies`, `OptionalDependencies` STRUCT 배열을 `dependencies`, `peerDependencies`, `optionalDependencies` 객체로 변환한다. 현재 Curated run의 invalid dependency는 25건이며, 원천 requirements는 존재하지만 invalid이다([`transform.py`](../../../pipeline/curated/transform.py)). | `public.version.dependency JSON NOT NULL DEFAULT '{...}'` | SQL NULL은 허용하지 않는다. V1의 NOT NULL·DEFAULT·comment를 유지하고 staging/service에서도 NULL을 거부한다. COPY에서만 기본 JSON `{"dependencies":{},"peerDependencies":{},"optionalDependencies":{}}`으로 대체하고 원본 NULL·ID/version·run 해시를 품질 JSONL에 기록한다. |

### 날짜와 provenance 컬럼은 version 데이터와 분리한다

| 의미 | 물리 컬럼·위치 | PostgreSQL 표현 | 처리 기준 |
| --- | --- | --- | --- |
| 스냅샷 기준일 | Curated 경로 `snapshot={date}`, manifest request `snapshot`, CLI `--snapshot` | `etl_load_execution.snapshot_at DATE` | ISO DATE로 일치 검증. version의 `published_at`을 대체하지 않음. |
| 원천 공급자 관측 시각 | Bronze `raw_versions.SnapshotAt`·`raw_requirements.SnapshotAt`, Curated `report.snapshot_timestamp` | `etl_load_execution.snapshot_timestamp TIMESTAMP` | 두 입력의 정확한 값이 같아야 하며 timezone 없는 마이크로초를 보존. `published_at`과 별도 provenance다([`transform.py`](../../../pipeline/curated/transform.py), [`V2__add_curated_load_execution.sql`](../../../backend/src/main/resources/db/migration/V2__add_curated_load_execution.sql)). |
| 적재 시스템 시각 | DB가 생성하는 `created_at`, `updated_at`, `etl_dataset_current.published_at` | `TIMESTAMPTZ` | 서버 `clock_timestamp()` 값. 원천 배포·공급자 관측 시각으로 해석하지 않음. |

`published_at`, `snapshot_timestamp`, 실행 시스템 시각은 서로 다른 시계와 의미를 갖는다.
이 값을 하나의 날짜나 timezone으로 합쳐 비교하지 않는다.

## 완료 판단 기준

| ID | 기대하는 결과 | 검증 결과 기록 |
| --- | --- | --- |
| AC-01 | 승인·manifest·파일 크기/해시·스키마 오류를 서비스 변경 전에 거부 | [05 결과와 검증](05-results.md) |
| AC-02 | 빈 검증 DB의 package·version 건수가 선택한 입력 manifest와 일치 | 동일 |
| AC-03 | ID 대응·PK·패키지명 유일성·FK 보존, 기존 ID 충돌은 임의 재발급·덮어쓰기 없이 실패 | 동일 |
| AC-04 | ordinal·배포일·JSON·NULL·빈 문자열 및 합의한 시간 처리 보존 | 동일 |
| AC-05 | 같은 입력 재실행 시 중복·ID 변경 없음, 같은 실행 ID의 다른 입력·계약 거부 | 동일 |
| AC-06 | 중간 실패 시 부분 반영 없음, 데이터와 PUBLISHED 함께 커밋, 실패 이력 확인 가능 | 동일 |
| AC-07 | 과거 입력의 최신 속성 덮어쓰기와 동시 실행 충돌 방지 | 동일 |
| AC-08 | 원본·완료 표시·V1 보존, 실제 DB의 TRUNCATE·샘플 seed 미실행, 팀원용 실행·복구 문서 제공 | 동일 |

`curated-20260907-v2`의 manifest와 이번 DB의 실제 측정값은 package 11,080,940행, version 54,188,349행으로 일치했다. dependency는 원본 SQL NULL 25건을 loader에서 기본 JSON으로 대체했으므로 원본 통계와 DB 통계를 구분한다. 입력 run이 달라지면 manifest 기준으로 기대값을 다시 정한다. 검증기의 필드 값 대조는 표본 기반이며, 전체 건수·NULL 집계·키·제약 검사는 전체 기준이다.

## 범위 변경 이력

아래 최초 기록의 `V2에서 NOT NULL 해제`는 사용자 DDL 확인 전에 작성한 폐기된 중간안이다. 현재
계약은 V1 서비스 DDL을 완전히 보존하고, V2에는 실행 관리만 추가하며, loader COPY에서 invalid
dependency 25개를 기본 JSON으로 대체하고 품질 이력에 기록하는 것이다. 원본 Curated 행과
버전은 유지하며 SQL NULL을 서비스 테이블에 보내지 않는다. 기본 JSON은
`{"dependencies":{},"peerDependencies":{},"optionalDependencies":{}}`이다.

초기 구현에서는 assistant가 원천 NULL 보존을 우선한다고 판단해 V2에서 NOT NULL을 해제했다.
사용자가 서비스 DDL을 명확히 정정하자 해당 적재를 취소·롤백하고 이 변경을 제거했다.
이후 사용자가 NULL 25건의 기본 JSON 대체와 품질 이력 기록을 선택했다. 최종 구현은
서비스 DDL을 유지하며 이 선택을 따른다. 자세한 경위와 검증은 [ISS-001·ISS-006](03-issues.md)에 기록한다.

| 일시 | 변경 전 → 변경 후 | 이유·결정 근거 | 영향받는 작업·완료 기준 | 연결 이슈 / 작업 기록 |
| --- | --- | --- | --- | --- |
| 2026-09-08 초기 구현, 이후 폐기 | V2에서 NOT NULL 해제 | assistant가 원천 NULL 보존을 우선한 판단. 사용자 DDL과 달라 폐기 | T-01, T-03, T-04 | ISS-001, ISS-006 |
| 2026-09-08 사용자 DDL 정정 | V2의 서비스 ALTER·COMMENT 제거, 검증 DB 원복 | 제공된 5개 서비스 테이블 DDL을 그대로 유지 | AC-04, AC-08 | W-008, V-002 |
| 2026-09-08 사용자 처리 방침 확정 | dependency SQL NULL을 기본 JSON으로 대체하고 품질 이력 추가 | 원본 버전·ID·MinIO 파일 유지, 대체한 행을 추적 가능하게 기록 | AC-02, AC-04, AC-05 | W-009~010, V-002, V-004 |
