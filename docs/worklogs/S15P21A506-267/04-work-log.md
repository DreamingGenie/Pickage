# 04. 실제 작업 일지

[작업 계획](02-plan.md) · [이슈 기록](03-issues.md) · [결과와 검증](05-results.md) · [문서 안내](README.md)

실제로 수행한 작업만 시간순으로 추가한다. 계획 변경은 02, 원인 조사와 해결 과정은 03에 기록하고 여기에서는 연결한다. 명령 성공과 완료 기준 충족을 별도로 판단한다.

## 작업 목록

| 기록 ID | 일시 | 연결 단계 | 실제 수행 내용 | 결과 | 근거 / 이슈 |
| --- | --- | --- | --- | --- | --- |
| W-001 | 2026-09-08 +09:00 | 문서 준비 | 작업 기록 6종 생성, docs 인덱스 연결 | 23개 상대 링크·UTF-8·공백 검사 통과 | 사용자 착수 요청 이전 턴의 실제 작업 |
| W-002 | 2026-09-08 12:42:55 +09:00 확인 기준 | P-01 | 현재 브랜치·선행 코드·V1·실행 환경과 MinIO 승인 manifest 조회 | 선행 통합 확인, 입력 메타 확인, dependency 제약 충돌 발견 | ISS-001, ISS-002 |
| W-003 | 2026-09-08 +09:00 | P-01~03 | 변경 파일·값 보존·COPY 전송·실행 이력·재시도 정책 확정, 독립 구현 착수 | 계획 기록 완료, 구현·DB 검증은 진행 중 | 01·02 문서 |
| W-004 | 2026-09-08 +09:00 | P-03, P-06 | 전용 PostgreSQL 컨테이너 생성, 테스트별 새 DB에 V1+V2 SQL 적용 | PostgreSQL 16.14, 연결·스키마 적용 성공. V1 서비스 DDL과 dependency NOT NULL/comment를 확인 | ISS-002, ISS-006 |
| W-005 | 2026-09-08 +09:00 | P-02~05 | 입력·psql 모듈·CLI·V2 구현, 실제 DB 테스트에서 발견한 실패 수정 | 초기 nullable contract 기준 27개 통과 기록. 사용자 DDL 정정 후 NOT NULL 거부·서비스 스키마 보존을 포함한 30개 중간 테스트도 통과 | ISS-003~006, V-001~002 |
| W-006 | 2026-09-08 13:03:30 +09:00 시작, 13:33:22 +09:00 취소 | P-06 | 승인 전체 입력을 빈 `pickage_267_full`에 적재 시작 후 사용자 DDL 확인으로 취소 | `FAILED`, `canceling statement due to user request`. rollback 후 package/version/current 0, dependency NOT NULL과 comment 복원 | ISS-006, V-004 대기 |
| W-007 | 2026-09-08 +09:00 | P-06 | 기존 Curated·MinIO 회귀 테스트와 Python compile 검사 | Curated 31개, MinIO 3개 통과 | V-003 |
| W-008 | 2026-09-08 13:37:11 +09:00 | P-03, P-06 | 사용자 DDL 정정 반영, 진행 중 전체 적재 취소 및 검증 DB 복원 | 취소 report `FAILED`, service package/version/current 0, dependency NOT NULL·comment 원복 | ISS-006, `evidence/cancelled-load.json` |
| W-009 | 2026-09-08 13:38:14 +09:00 이후 | P-04~06 | SQL NULL 거부·5개 서비스 테이블 DDL 보존·기본 JSON 품질 대체를 포함한 통합 검증 실행 | 최종 contract 테스트 31개, skip 0, 62.312초, `OK`; 기존 회귀 34개와 합쳐 현재 검증 범위 65개 | ISS-001, ISS-006, `evidence/postgresql-default-tests.json` |
| W-010 | 2026-09-08 13:50 +09:00 확인 기준 | P-06 | 새 execution `load-267-full-defaulted-v1` 전체 입력 검증·COPY 진행 상태 확인 | source·quality 25행 기록 통과, package staging 11,080,940행, version COPY 진행 상태를 확인. 이후 W-011에서 전체 PUBLISHED 완료 | V-004, W-011 |
| W-011 | 2026-09-08 13:45:30~14:44:19 +09:00 | P-06 | `load-267-full-defaulted-v1`로 승인 Curated 전체 24개 파일을 새 격리 DB에 적재 | `PUBLISHED`, 3,529초(58분 49초), package 11,080,940행·version 54,188,349행을 한 트랜잭션으로 커밋. dependency SQL NULL 25건은 기본 JSON으로 대체하고 품질 JSONL SHA를 기록 | ISS-001, ISS-007, `evidence/full-load.json` |
| W-012 | 2026-09-08 14:47:41 +09:00 | P-06 | 전체 적재 후 읽기 전용 verifier로 입력·DB 통계·표본·제약·품질 이력 대조 | 12개 검사 모두 `PASS`; 전체 건수/NULL 집계/ordinal 범위/제약과 166 package·185 version 표본 대조가 일치. 필드 값 대조는 표본 범위이며 전체 행 값 대조는 아님 | `evidence/full-data.json` |
| W-013 | 2026-09-08 14:51:21~14:52:19 +09:00 | P-06~07 | 동일 execution/input의 입력 전용 재검증 및 전후 상태 대조 | attempt `826f0037c0f943498a3eddf3544537f3`가 `REVERIFIED/PUBLISHED`로 완료. 11개 대조 모두 통과, current pointer·서비스 건수 불변, COPY 파일 0개, quality count/hash 동일 | ISS-004, `evidence/reverification.json` |

## W-006 — 전체 적재 실행 기준

- 실제 명령: `.venv-bq/Scripts/python.exe -m pipeline.postgresql.load --snapshot 2026-08-31 --curated-run-id curated-20260907-v2 --execution-id load-267-full-v1 --docker-container pickage-267-validation --database pickage_267_full --work-dir data/postgresql --threads 8 --memory-limit 6GB --workers 4`
- attempt: `e94e37c1c1c942b58276106ffa9eac97`.
- 입력 manifest SHA-256: `a537f84bae78c9209e56deddb24d94cdef606d06e0e563f93ddb67e3843e71b3`.
- 실행 계약 SHA-256: `fe5fc2e387e2d726007a8b0524a0050d472c6ec1e4600e46699edb91f84f9153`.
- 로컬 실행 보고서: `data/postgresql/load-267-full-v1/e94e37c1c1c942b58276106ffa9eac97/execution_report.json`.
- DB 초기화: 정보 스키마 조회로 public 테이블 0개를 확인한 뒤 당시 저장소 V1·V2 SQL을 한 트랜잭션으로 적용했다. 사용자 DDL 정정 후 nullable 변경은 폐기하고 V1 서비스 DDL 및 dependency NOT NULL/comment를 복원했다. Flyway 엔진을 직접 실행한 결과는 아니며, 애플리케이션 자동 적용과 구분한다.
- 실행 결과: 1,792.078초 후 PUBLISH 단계에서 취소되어 `FAILED`로 기록됐다. rollback 뒤 package 0, version 0, current 0을 확인했고 dependency NOT NULL과 원래 comment를 복원했다. MinIO 원본·관리 파일은 변경하지 않았다.
- 후속: 이 실행의 contract `fe5fc2e387e2d726007a8b0524a0050d472c6ec1e4600e46699edb91f84f9153`는 nullable 구현 기준의 폐기된 중간 contract다. 기본 JSON 품질 대체 구현 후 새 execution ID와 새 contract로 재실행한다.

## W-011 — 최종 전체 적재

- 실제 실행 ID: `load-267-full-defaulted-v1`; attempt: `9974ae24e2504510937cea4a12952041`.
- 시작 / 종료: `2026-09-08 13:45:30 +09:00` / `2026-09-08 14:44:19 +09:00`; 3,529초(58분 49초).
- 입력: snapshot `2026-08-31`, run `curated-20260907-v2`, manifest SHA-256 `a537f84bae78c9209e56deddb24d94cdef606d06e0e563f93ddb67e3843e71b3`, contract SHA-256 `9015ee602ad3be709b23df4f1d09745b129cd002beb99084226a309832e64bd2`.
- 대상: `pickage_267_full_defaulted` / `pickage-267-validation`.
- 결과: status `PUBLISHED`, action `LOADED`. package 11,080,940행, version 54,188,349행. 품질 대체 25행/10개 package, JSONL SHA-256 `d3281a270d4fa875ec16e23201937b4a33b9da2f396ebcd4c1b91b89491e48bb`.
- 근거: [full-load.json](evidence/full-load.json), 실행 원본 report의 SHA-256 `2314d647389754e9d973ac584ab9c9e8a18b0b2b3f35e2c953c2db9351093ad3`.

## W-012 — 전체 적재 읽기 전용 검증

- `2026-09-08 14:47:41 +09:00`에 `scripts/verify_package_version_load.py`를 실행했다.
- 12개 검사를 모두 통과했다. package/version 전체 건수와 NULL 집계, ordinal 범위, PK·UNIQUE·FK, dependency NOT NULL, 실행 identity, quality 파일 hash·25행·DB 이력을 대조했다.
- package 166행과 version 185행 표본에는 25개 기본 JSON 대체 행이 포함됐다. 전체 필드 값 동일성은 검증하지 않았고 verifier의 표본 대조 범위로 제한한다.
- 근거: [full-data.json](evidence/full-data.json).

## W-013 — 동일 입력 재검증

- 시작 / 종료: `2026-09-08 14:51:21 +09:00` / `2026-09-08 14:52:19 +09:00`; 58.235초.
- attempt `826f0037c0f943498a3eddf3544537f3`, action `REVERIFIED`, status `PUBLISHED`, scope `INPUT_ONLY`, `is_current_input=true`.
- 동일 manifest·contract·quality SHA를 확인했고, current pointer와 published_at, package/version 건수, dependency SQL NULL 0건이 변하지 않았다. 새 COPY export는 0개이며 quality 25행과 SHA `d3281a270d4fa875ec16e23201937b4a33b9da2f396ebcd4c1b91b89491e48bb`가 기존과 같다.
- 11개 후속 대조가 모두 통과했다. 근거: [reverification.json](evidence/reverification.json).

## W-002 — 착수 조사에서 확인한 결과

- 코드: `2dccbf58774cc073b0c31859f634e05c0f91a6e7`. 기존 미추적 파일·문서는 README의 시작 상태에 보존했다.
- 실행 환경: `.venv-bq` Python 3.12.12. DuckDB·boto3는 설치되어 있고 psycopg·pyarrow·pytest는 없다. 새 의존성을 추가하지 않는 경로를 선택했다.
- 실제 조회: `pipeline.curated.build.completed_run`으로 명시한 MinIO run의 manifest와 `_SUCCESS` 해시 일치를 확인했다. 원본 쓰기 없음.
- 입력: run `curated-20260907-v2`, snapshot `2026-08-31`, 공급자 시각 `2026-08-31T21:01:10.517131`, attempt `1fc06062562448e1b7278aa03b964fff`.
- manifest 기대값: package 11,080,940 / version 54,188,349 / invalid requirements 25. 아직 이번 실행의 Parquet 전체 검증·DB 측정값은 아니다.
- Docker: 범위 확장 후 조회 성공, MinIO 건강 상태 확인. PostgreSQL 서버는 새로 준비해야 한다.

## 작업 상세 양식

### W-XXX — [실제 수행한 작업 제목]

- 시작 / 종료 시각: `[시간대 포함]`
- 수행자 / 연결 단계·이슈: `[작성 필요]`
- 작업 목적: `[작성 필요]`
- 코드 기준: `[커밋 SHA, 미커밋 변경이 있으면 파일·패치 근거]`
- 환경 / 작업 디렉터리 / 도구 버전: `[작성 필요]`
- 입력 식별 정보: `[run·attempt·snapshot·manifest/계약 해시 등, 해당 없으면 사유]`
- 대상 DB / 적재 실행 ID: `[인증정보를 제외한 식별 정보]`

#### 실제 변경·실행

| 파일 / 대상 | 실제 변경 또는 수행 | 이유 | 계획과의 차이 |
| --- | --- | --- | --- |
| `[작성 필요]` | `[작성 필요]` | `[작성 필요]` | `[없음 또는 변경 기록 연결]` |

실행한 명령·쿼리: `[실제 명령을 코드 블록으로 기록. 미실행 명령은 넣지 않는다.]`

#### 관측 결과와 근거

- 실행 종료 코드 / 처리 건수·소요 시간 / 상태 변화: `[측정한 항목만 기록]`
- 예상 결과와 실제 결과의 차이: `[작성 필요]`
- 검증 결과 / 근거 파일·로그·쿼리 출력: `[V-XXX 또는 증거 위치]`
- 실패·재시도 / 되돌린 변경·복구 결과: `[ISS-XXX 연결 또는 해당 없음]`
- 이번 작업으로 완료한 것: `[검증 범위 안에서 작성]`
- 남은 작업 / 다음 단계: `[작성 필요]`
