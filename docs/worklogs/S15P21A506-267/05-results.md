# 05. 결과와 검증

상태: **구현·전체 적재·DB 대조·동일 입력 재검증 완료** · [완료 기준](01-scope.md) · [작업 일지](04-work-log.md) · [문서 안내](README.md)

## 결과 요약

사용자가 확정한 서비스 5개 테이블 DDL을 유지하고, 승인 Curated 데이터를 격리 PostgreSQL에 게시했다. `version.dependency`는 **JSON NOT NULL DEFAULT** 그대로이며 원본 SQL NULL 25건만 COPY 시 기본 JSON으로 대체했다. 대체한 25개 버전과 원본 출처·대체 값·품질 파일 해시를 모두 추적할 수 있다.

| 항목 | 실제 결과 |
| --- | --- |
| 전체 적재 | `PUBLISHED` · package **11,080,940행**, version **54,188,349행** |
| 시간 | 2026-09-08 **13:45:30~14:44:19 KST**, **3,529초(58분 49초)** |
| 입력과 staging, 서비스 건수 | 두 테이블 모두 일치. 게시 전 서비스 0/0행 |
| DB 대조 | **12개 검사 통과**, 14:47:41 KST 완료 |
| dependency | 서비스 SQL NULL **0건**, 기본 JSON 대체 **25건/10개 패키지**, 품질 파일·DB 이력 일치 |
| 테스트 | 최종 PostgreSQL 단위 15개 + 실제 통합 16개 + 기존 Curated/MinIO 34개 = **65개 통과** |
| 동일 입력 재실행 | **58.235초**, `REVERIFIED` 완료. 전후 건수·게시 정보·품질 이력 등 **11개 검사 통과**, COPY 파일 0개 |
| 보존 | V1 원문·서비스 DDL 유지, MinIO 원본·완료 표시 변경 없음 |
| 환경 | PostgreSQL 16.14, `pickage-267-validation` 컨테이너의 `pickage_267_full_defaulted` DB |
| 브랜치 | `feat/S15P21A506-267-package-version-postgresql-load` · 커밋·push·MR 생성 미실행 |

처음에는 assistant가 nullable을 허용하는 잘못된 전제를 구현했다. 사용자 DDL 정정 후 기존 전체 실행을 약 29분 52초 시점에 취소하고 서비스 변경을 rollback했다. 이 시간은 위 **정정 후 성공 실행의 58분 49초와 별도**다. 초기 27개·중간 30개 테스트는 폐기된 계약의 역사적 기록이며 최종 65개에 중복 합산하지 않았다.

## 실제 변경 범위

| 파일 / 모듈 | 구현 결과 |
| --- | --- |
| `pipeline/postgresql/input.py` | 승인 run·manifest·정확한 파일 목록·SHA/크기·스키마·행 수·키·FK·길이·NUL·JSON 검증, COPY TEXT 변환, dependency SQL NULL 기본값 대체 및 품질 JSONL |
| `pipeline/postgresql/postgres.py` | 단일 psql 세션, 임시 staging COPY/검증, package→version 원자적 게시, 실행·attempt·current 이력, 잠금·충돌·실패 rollback·재시도·과거 입력 보호 |
| `pipeline/postgresql/load.py` | 명시적인 snapshot/run/execution/DB 선택, 검증 전용 모드, 실행 계약 해시, 단계·건수·시간·품질·오류 보고서 |
| `pipeline/postgresql/test_*.py` | 단위 15개·실제 PostgreSQL 통합 16개. 테스트별 전용 DB를 사용 |
| `V2__add_curated_load_execution.sql` | `etl_load_execution`, `etl_load_attempt`, `etl_dataset_current` 추가. 서비스 5개 테이블은 변경하지 않음 |
| `scripts/verify_package_version_load.py` | 읽기 전용 전체 건수·NULL/ordinal 통계·제약·표본 필드·기본값 대체 품질 이력 대조 |
| `pipeline/postgresql/README.md` 및 상위 안내 | 설치·실행·검증·재실행·복구 절차 |
| `docs/worklogs/S15P21A506-267/` | 범위·계획·이슈·작업 일지·최종 결과와 작은 검증 증거 보존 |

기존 미추적 파일이나 다른 작업의 변경은 이 목록에 포함하지 않는다. 다른 세 서비스 테이블의 데이터 적재, 지표 계산, Spark 전환, 운영 배포는 이번 범위에 포함하지 않았다.

## 완료 기준별 판정

| 기준 | 판정 | 근거 |
| --- | --- | --- |
| AC-01 승인 입력·파일 무결성 | 통과 | 승인 manifest와 서비스 파일 24개, 4,534,618,749 bytes의 해시·스키마·행 수·필드 검증 통과 |
| AC-02 입력/staging/service 건수 | 통과 | package 11,080,940·version 54,188,349로 모두 일치 — V-004 |
| AC-03 ID·PK·UNIQUE·FK·충돌 | 통과 | 전체 입력 키·참조 검사, staging 검사, 실제 DB 제약 유효성 및 충돌 통합 테스트 |
| AC-04 JSON·NULL·시간·문자열 | 통과 | 전체 NULL/ordinal 통계, package 166개·version 185개 표본 필드, SQL NULL 기본값 대체 25건 전부와 경계값 테스트 — V-002/V-004 |
| AC-05 재실행·실행 ID 보호 | 통과 | 실제 동일 입력 `REVERIFIED`, 전후 서비스 건수와 current 동일; 다른 계약·입력의 ID 재사용 거부 통합 테스트 — V-005 |
| AC-06 원자성·실패 이력 | 통과 | 중간 실패 주입과 실제 초기 전체 실행 취소 시 서비스 0/0·current 0으로 rollback |
| AC-07 과거 입력·동시 실행 | 통과 | advisory lock, snapshot/lineage, 과거 재검증 current 보존, 지연 실패 방어 통합 테스트 |
| AC-08 원본·V1 보존·문서 | 통과 | V1 원문 동일, 5개 서비스 테이블 21개 컬럼·11개 제약 보존, 읽기 전용 MinIO 사용과 실행·복구 문서 |

## 검증 증거

### V-001 — 단위 검증

최종 계약 기준 입력·CLI·COPY 형식 단위 테스트 **15개**가 통과했다. marker/manifest/hash/size/schema/count, 중복·FK·문자열·NUL·ordinal·JSON, 기본 JSON 대체와 품질 파일을 검증했다.

### V-002 — 실제 PostgreSQL 통합 검증

PostgreSQL 16.14에서 테스트마다 `pickage_267_test_<uuid>` DB를 생성해 **통합 16개**를 실행했다. 단위 검증과 함께 **31개, skip 0, 62.312초, 종료 코드 0**으로 통과했다.

- V1/V2 적용 전후 5개 서비스 테이블의 컬럼·기본값·제약·comment 일치.
- staging의 명시적 dependency SQL NULL 거부, loader의 SQL NULL→기본 JSON 대체 및 DB roundtrip.
- SQL NULL과 JSON `null`·빈 객체/배열 구분, 개행·백슬래시·마이크로초 timestamp 보존.
- 품질 JSONL의 행 식별자·count·SHA·DB attempt 연결, 재검증 시 품질 기록 유지.
- package 반영 후 실패 rollback, 재시도, ID↔name 충돌, 실행 ID 보호, 잠금과 과거 입력 보호.

증거: [postgresql-default-tests.json](evidence/postgresql-default-tests.json). 로컬 로그는 `data/postgresql/verification/postgresql-default-tests.log`, SHA-256 `674891966e04717320ee00aca41cf532798ef9d8b859524da6c5b99750d3f62e`다.

검증한 계약 SHA-256은 `9015ee602ad3be709b23df4f1d09745b129cd002beb99084226a309832e64bd2`이며 전체 적재와 동일하다. 애플리케이션 DB와 seed는 사용하지 않았다.

### V-003 — 기존 파이프라인 회귀·보존 확인

기존 Curated **31개(16.264초)**, MinIO **3개**가 통과했다. 별도 회귀 원문 로그는 보존하지 않았으며 당시 도구 실행 관측과 [회귀 증거 요약](evidence/source-and-regressions.json)을 남겼다. 이 요약의 loader 계약 해시는 초기 구현 시점이므로 현재 계약 근거로 사용하지 않는다.

현재 코드 및 V1 보존은 [final-source-contract.json](evidence/final-source-contract.json)으로 구분한다. V1 바이트 SHA-256은 `9bcbd29365e3f5d2334501414ada4916157bd18401c6f58a2a02fc7c1715ee70`이다.

전체 실행 후에도 Python compile, Git diff 검사, V1 원문 동일성, 실행 당시 loader 계약 일치를 [최종 검사](evidence/final-checks.json)에서 다시 확인했다. 문서의 UTF-8·공백·SHA 길이·로컬 링크 검사도 통과했다.

### V-004 — 승인 Curated 전체 적재와 DB 대조

| 식별 정보 | 값 |
| --- | --- |
| bucket / run | `pickage-curated` / `curated-20260907-v2` |
| snapshot / 공급자 관측 시각 | `2026-08-31` / `2026-08-31T21:01:10.517131` |
| source attempt | `1fc06062562448e1b7278aa03b964fff` |
| manifest SHA-256 | `a537f84bae78c9209e56deddb24d94cdef606d06e0e563f93ddb67e3843e71b3` |
| loader execution / attempt | `load-267-full-defaulted-v1` / `9974ae24e2504510937cea4a12952041` |
| 상태 | `PUBLISHED`, action `LOADED`, phase `COMPLETE` |
| 입력 / COPY TEXT | 24개 파일, 4,534,618,749 bytes / 20,025,861,474 bytes |

| 대상 | 입력 기대 행 수 | staging 실제 행 수 | 서비스 반영 전 | 서비스 반영 후 | 판정 |
| --- | ---: | ---: | ---: | ---: | --- |
| package | 11,080,940 | 11,080,940 | 0 | 11,080,940 | 일치 |
| version | 54,188,349 | 54,188,349 | 0 | 54,188,349 | 일치 |

읽기 전용 verifier는 **12개 검사 모두 통과**했다. 전체 건수·NULL 통계·ordinal 범위가 기대값과 같고 package/version의 PK·UNIQUE·FK는 validated 상태다. package **166개**, version **185개** 표본은 모든 필드가 입력과 일치했다. 원본 dependency SQL NULL **25개 전부**가 이 표본에 포함된다.

| 통계 | source | DB |
| --- | ---: | ---: |
| package.repo_url SQL NULL | 2,778,319 | 2,778,319 |
| version.published_at SQL NULL | 7,015,400 | 7,015,400 |
| version.description SQL NULL | 6,647,883 | 6,647,883 |
| version.deprecated SQL NULL | 51,818,365 | 51,818,365 |
| version.licenses SQL NULL / JSON null | 0 / 0 | 0 / 0 |
| version.dependency SQL NULL | 25 | **0 — 승인한 기본 JSON 대체** |
| version.dependency JSON null | 0 | 0 |
| ordinal 최소 / 최대 | 1 / 37,328 | 1 / 37,328 |

품질 파일에는 25행/10개 패키지의 원본 SQL NULL, package ID·이름·version, replacement, source run·manifest 해시가 있다. 파일 SHA-256은 `d3281a270d4fa875ec16e23201937b4a33b9da2f396ebcd4c1b91b89491e48bb`이며 로컬 보고서와 DB attempt `quality_report`가 일치한다.

증거: [전체 적재](evidence/full-load.json), [DB 대조](evidence/full-data.json), [품질 25건](evidence/dependency-defaulted.jsonl), [서비스 DDL 확인](evidence/defaulted-db-schema.json).

**검증 한계:** 행 수·NULL 통계·입력 키와 참조는 전체 범위를 검사했다. 필드 값 동일성은 위 표본 대조이며 모든 행의 모든 필드를 전수 비교한 결과는 아니다. SHA는 바이트·입력 식별의 증거이며 변환 의미의 정확성을 단독으로 보장하지 않는다.

### V-005 — 동일 입력 재실행

같은 입력·execution ID·계약으로 새 attempt `826f0037c0f943498a3eddf3544537f3`를 실행해 **58.235초**에 `REVERIFIED`로 완료했다(14:51:21~14:52:19 KST). 후속 읽기 전용 검사 **11개 모두 통과**했다.

- 서비스 실제 건수는 전후 package 11,080,940·version 54,188,349로 동일하고 dependency SQL NULL은 0건이다.
- manifest와 게시 시각을 포함한 DB current가 동일하며 최초 execution은 `PUBLISHED`를 유지한다.
- attempt 이력은 최초 `PUBLISHED`와 새 `REVERIFIED` 두 건이다. 새 COPY 파일은 0개다.
- 품질 25건의 해시가 최초 실행과 같고 새 DB attempt의 품질 이력도 로컬 보고서와 일치한다.

증거: [동일 입력 재실행 및 전후 대조](evidence/reverification.json).

`REVERIFIED`의 검증 범위는 `INPUT_ONLY`다. 이 attempt의 입력 건수를 서비스 전체 재측정으로 해석하지 않으며, 별도 읽기 전용 SQL로 실제 서비스 건수와 current 보존을 확인한다.

## 지연 원인과 이슈 처리 결과

| 이슈 | 처리 결과 |
| --- | --- |
| ISS-001 / ISS-006 dependency DDL 충돌 | 잘못된 nullable 구현을 폐기하고 사용자 DDL 유지. 원본 25개 version은 보존하며 loader에서만 기본 JSON과 품질 이력 적용. 전체 DB 대조 통과 |
| 최초 전체 실행 취소 | 약 29분 52초 후 취소·rollback. 이전 DB package/version/current 0, NOT NULL/comment 복원 확인. [취소 기록](evidence/cancelled-load.json) |
| ISS-002~ISS-005 환경·COPY·상태 관리·fixture 문제 | 구현 수정 후 최종 단위·실제 통합 테스트 통과. 상세는 [이슈 기록](03-issues.md) |
| ISS-007 전체 적재 시간 | 정정 후 전체 실행 58분 49초. staging COPY 이후 서비스 `INSERT SELECT ... ON CONFLICT` 단계에서 PK/FK·인덱스를 유지하며 처리했다. version 반영 SQL에 약 39분이 걸렸고 진행 중 약 1코어 사용을 관측했다. 세부 비용별 프로파일링은 하지 않았으며, 빈 DB 최초 적재 최적화는 후속 작업 |
| Flyway / 애플리케이션 기동 | 격리 DB에 V1/V2 SQL을 실제 적용했으나 Flyway 엔진 및 Spring 기동은 실행하지 않음. 해당 환경의 자동 migration 동작은 별도 확인 필요 |

## 인계 정보

- 설치·실행·복구: [PostgreSQL 적재 안내](../../../pipeline/postgresql/README.md).
- 결과 DB: `pickage-267-validation` 컨테이너 / `pickage_267_full_defaulted`. 전용 volume `pickage_267_validation_pgdata`를 보존했다. 외부 포트는 노출하지 않았다.
- 원본·report·cache·COPY·stderr: `data/postgresql/load-267-full-defaulted-v1/<attempt_id>/`. 대형 파일은 Git에서 제외하고 작은 결과·품질 증거는 이 문서의 `evidence/`에 보존한다.
- 서비스 DDL은 V1 원문 그대로다. V2는 공통 실행 관리 테이블만 추가한다. 후속 snapshot·지표 적재는 별도 작업이다.
- 아직 수행하지 않은 범위: Flyway 엔진/Spring 기동 검증, 운영 배포, 커밋·push·MR 생성.
