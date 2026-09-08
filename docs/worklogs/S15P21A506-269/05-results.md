# 05. 결과와 검증

**Projects에서 추출한 스냅샷 229개를 267 전체 데이터 DB `pickage_267_full_defaulted`에 반영했다.**
2026-09-08 14:59:39 +09:00 기준 최초 신규 229행, 동일 SQL 재실행 신규 0행이며 전체 날짜 집합이
입력과 일치한다. 기존 격리 PostgreSQL에서의 적재·재실행·오류 롤백 검증도 통과했다.
267 공통 실행 이력 및 서비스 준비 상태 연결은 남아 있으므로 **269 전체 티켓은 부분 완료**다.

## 실제 변경

| 파일 / 범위 | 변경 내용 |
| --- | --- |
| `pipeline/snapshot/policy.py`, `__init__.py` | UTC 시각/날짜 구분, 직전 P, `[P,S)` coverage·NULL 사유, 정확 Projects 관측·같은 snapshot 버전 대상 정책 |
| `pipeline/snapshot/projects.py` | Projects manifest 및 모든 Parquet의 SnapshotAt footer 통계·행 수 검사, 원천 목록·manifest/footer 해시 |
| `pipeline/snapshot/build.py` | 고정 calendar·정책/입력 해시·로컬 상태 산출물, 명시적 날짜 INSERT SQL |
| `pipeline/snapshot/test_*.py` | 순수 정책·입력·산출물 테스트 및 새 격리 PostgreSQL 검증 |
| `pipeline/snapshot/README.md` | 실행 방법, 적용 정책과 공식 계약 구분, 267/후속 연결·제한 |
| `docs/worklogs/S15P21A506-269/` | 267 형식의 기록 6개 및 검증 증거 |
| [267 문서 안내](../S15P21A506-267/README.md), [267 작업 정의](../S15P21A506-267/01-scope.md) | 임시 계획 문서 참조를 커밋에 포함되는 작업 정의·실행 안내로 교체 |

기존 loader·V1/V2 및 267 실행 이력/검증 증거는 보존했으며, 이번에는 문서 참조만 수정했다.
최초 병행 구현과 DB 적재는 267 브랜치에서 수행했고, 이후 사용자가
`feat/S15P21A506-269-snapshot-contract-load` 브랜치로 분리했다.
후속 승인으로 대상 DB의 snapshot 날짜만 추가했으며 실행 증거는 아래 V-004에 보존한다.
커밋·push·MR·Jira 갱신은 수행하지 않았다.

## 완료 기준별 판정

| 기준 | 판정 | 실제 근거 / 한계 |
| --- | --- | --- |
| AC-01 원천 시각·계보·UTC 날짜 | 통과 | V-002. 모든 선택 Projects 파일의 timestamp·날짜·NULL 통계·manifest 행 수 확인. 전체 파일 SHA나 지표 값 전수 대조는 아님 |
| AC-02 순서·중복·P 독립성 | 통과 | V-001. 입력 순서와 무관한 정렬, 중복 instant 제거, 같은 UTC DATE 충돌 거부, P는 고정 목록에서 계산 |
| AC-03 기간·누락·실제 0 구분 | 통과 | V-001. 14일·인접 경계·최초·범위 밖·missing_dates 검사. 실제 합계 계산은 다운로드 구간 집계 범위 |
| AC-04 미래 관측·과거 대상 제한 | 통과 | V-001. 미래/이전 Projects 값 자동 선택 없음, 다른 snapshot 버전의 eligible은 미확인 |
| AC-05 버전·해시·범위 | 통과 | V-002. candidate의 정책/입력/SQL 해시와 목록을 보존. DB 공통 이력 연결은 후속 |
| AC-06 독립·실제 원천 검증 | 통과 | V-001~003. 17 단위 + 3 실제 PostgreSQL 테스트, skip 0. V-004에서 267 대상 DB의 229개 날짜 반영·재실행 확인 |
| 269 전체 범위 | 부분 완료 | 날짜 DB 반영 및 시간 정책·후속 통합 요구사항 문서화 완료. 공통 실행 이력·dataset 준비 상태·다운로드 구간 집계·저장소 지표 생성·requirements 대상 버전 해석·버전별 dependents 집계 실행 코드 연결 미구현 |

## V-001 — 독립 테스트

- 명령: `.\.venv-bq\Scripts\python.exe -m unittest pipeline.snapshot.test_policy pipeline.snapshot.test_projects pipeline.snapshot.test_build -v`
- 최종 결과: **17 tests, failures 0, errors 0, skipped 0**, 테스트 러너 0.351초. 최초 16개 실행은 중간 기록이며 중복 합산하지 않는다.
- 범위: timestamp 정밀도/offset/naive adapter, 14일 불규칙 간격, 중복 시각·DATE 충돌,
  coverage 경계·NULL 사유, 미래 Projects·과거 모집단, 잘못된 manifest/NULL/timestamp/date/행 수,
  footer만 읽는 해시 처리, candidate 해시·명시적 SQL·잘못된 입력의 출력 차단.
- actual 0은 missing_dates가 아니라는 입력 계약을 검사했다. 일별 다운로드 값의 생성 계보와 합계는 이 테스트가 증명하지 않는다.
- [최종 실행 요약·코드 해시](evidence/unit-tests.json) · [최종 테스트 로그](evidence/unit-tests.log).
  2026-09-08 14:42:26 +09:00에 TIMESTAMPTZ offset 처리와 footer 읽기 크기 회귀 검증을 포함해 실행했다.

## V-002 — 실제 Projects 전체 메타데이터

2026-09-08 14:34:41 +09:00에 `data/raw/projects`를 읽어 생성했다.

| 측정 항목 | 실제 결과 |
| --- | ---: |
| snapshot / manifest | 229 |
| Parquet / row group | 1,879 / 1,879 |
| 원본 파일 크기 합계 | 18,858,352,794 bytes |
| footer에서 확인한 Projects 행 수 합계 | 834,887,141 |
| 날짜 범위 | 2022-05-08 ~ 2026-08-31 |
| 직전 P / 현재 S | 2026-08-24 / 2026-08-31 |
| 해당 날짜 구간 | `[2026-08-24,2026-08-31)` — 24~30일, 7일 |
| 실제 현재 원천 시각 | `2026-08-31T21:01:10.517131Z` |
| 실제 이전 원천 시각 | `2026-08-24T21:01:08.477988Z` |

간격 분포는 1일 5개, 3일 2개, 4일 3개, 6일 21개, 7일 174개, 8일 17개,
10일 3개, 11일 1개, 14일 1개, 18일 1개다. 나머지 첫 날짜 하나는 P가 없다.
따라서 고정 7일 계산은 이 실제 입력의 계약과 맞지 않는다.

증거: [원천 요약·해시](evidence/projects-source-summary.json), [전체 날짜와 P](evidence/snapshot-calendar.json),
[229개 날짜 INSERT SQL](evidence/snapshot-dates.sql).
전체 파일별 목록은 로컬 `data/snapshot/S15P21A506-269/projects-v1/projects-inventory.json`에 보관한다.
후보 상태는 `LOCAL_VALIDATED`이며 `db_published=false`, `service_ready=false`다.

검증은 정상 Parquet footer가 선언한 timestamp/행 수를 확인한 것이다. 전체 지표 행을 스캔하거나
전체 원본 파일 SHA를 계산하지 않았다. raw 파일·완료 표시는 변경하지 않았다.
실제 입력 생성 이후 추가한 TIMESTAMPTZ `+HH` 어댑터·오류 메시지 수정은 기존 TIMESTAMP
입력의 날짜/시각 정책과 SQL을 바꾸지 않았다. 해당 추가 입력 형식은 V-001의 실제 Parquet fixture로 검증했다.

## V-003 — 실제 PostgreSQL 적재와 재시도

기존 검증 컨테이너에 **새 `pickage_269_test_<uuid>` DB를 테스트마다 생성**했다.
V1·V2를 그 DB에 읽어 적용했고, 모든 테스트 종료 후 해당 DB를 삭제했다.

- 실제 source candidate/SQL 해시와 229개 날짜를 대조한 뒤 INSERT를 두 번 실행했다.
- 매번 정확히 같은 229개 날짜가 존재함을 조회해 확인했다.
- 별도 작은 사례에서 기존 기준 날짜를 보존하고 재실행 중복이 없음을 확인했다.
- INSERT와 COMMIT 사이에 오류를 넣었을 때 전체 날짜 INSERT가 rollback됨을 확인했다.
- package/version 및 공통 실행 이력/current 게시 행은 0건 그대로임을 확인했다.

결과: **3 tests, failures 0, errors 0, skipped 0**, 테스트 러너 9.572초.
[실행 요약](evidence/postgresql-tests.json) · [테스트 로그](evidence/postgresql-tests.log)

V-003 자체는 격리 검증 DB의 성공이다. 이후 승인된 267 전체 데이터 DB 날짜 반영은 V-004로 구분한다.
Flyway 엔진 기동도 실행하지 않았으며 V1·V2 SQL을 검증 DB에 직접 적용했다.

## 합류 시 남은 작업

1. 267 공통 실행 이력에 snapshot-reference 입력 목록 해시·정책 버전/해시·원천 timestamp를 연결한다.
2. 날짜 반영은 V-004에서 완료했다. 이번 로컬 실행 증거를 공통 DB 실행 이력과 연결하고, 이후 적재는 날짜와 실행 이력을 함께 확정하도록 통합한다.
3. snapshot 날짜 등록과 필수 dataset별 준비/PUBLISHED를 구분하고 서비스의 완료 snapshot 선택에 연결한다.
4. 다운로드 구간 집계·저장소 지표 생성·requirements 대상 버전 해석·버전별 dependents 집계의 후속 실행 코드를 [스냅샷 시간 정책과 연동 기준](../../../pipeline/snapshot/README.md)에 맞춰 연결한다. 동일 후보 목록·정책 버전·해시를 참조하고, 각 과거 시점 package/version 원천 확보 여부는 별도로 판정한다.

후속 실행은 현재 후보를 그대로 참조하거나 새 Projects 입력을 새 디렉터리로 생성한다.
입력 목록 변경으로 P가 달라지면 입력 해시도 달라지므로 기존 기간을 조용히 덮어쓰지 않는다.

## V-004 — 267 전체 데이터 DB의 실제 날짜 반영

사용자의 "그럼 그것도 진행해봐" 승인에 따라 기존 전체 데이터 DB를 대상으로 수행했다.
이 DB는 운영 서버의 DB가 아니라 로컬 `pickage-267-validation` 컨테이너의
`pickage_267_full_defaulted`다. 이번에는 새 테스트 DB로 대체하지 않았으며 삽입한 날짜를 유지한다.

| 항목 | 실제 결과 |
| --- | --- |
| 실행 완료 | 2026-09-08 14:59:39 +09:00 |
| 실행 ID | `snapshot-dates-269-d8443b957afa4ed9aba7f0e20f299e6b` |
| 최초 상태 / 추가 / 최종 상태 | snapshot 0행 / 신규 229행 / 229행 |
| 같은 SQL 재실행 | 신규 0행, 최종 229행 |
| 날짜 범위 | 2022-05-08 ~ 2026-08-31 |
| 집합 검사 | 입력 229개와 DB 날짜 전체가 정확히 일치. COMMIT 전 및 별도 연결의 COMMIT 후 조회로 확인 |
| 잠금·실행 제한 | 트랜잭션 내 lock_timeout 2초, statement_timeout 30초. 날짜 집합 불일치는 커밋 전 오류 |
| package/version 보호 | 해당 테이블 DML·스키마 변경 없음. 기존 dataset current와 실행 상태/건수는 전후 동일 |
| 공통 실행 이력 | 이번 snapshot-reference 실행을 공통 ETL 테이블에 쓰지는 않음. 로컬 실행 증거 보존 |

입력 재확인에서 현재 Projects의 manifest 229개, 파일 1,879개의 정확한 목록·크기·mtime·footer SHA가
고정 inventory와 일치했고, candidate·정책·SQL 해시와 재생성 calendar도 일치했다.
실행 전 snapshot은 DATE PK 하나만 있었고 별도 사용자 trigger/rule이나 다른 세션의 snapshot 잠금이 없었다.
267의 package-version 실행은 PUBLISHED임을 확인했다.

증거: [입력 재확인](evidence/verification-before-db-insert.json),
[실제 실행·전후 조회·재실행 기록](evidence/snapshot-dates-269-d8443b957afa4ed9aba7f0e20f299e6b.json),
[실제로 실행한 SQL](evidence/snapshot-dates-269-d8443b957afa4ed9aba7f0e20f299e6b.sql).

이전 candidate는 입력 산출물이므로 `LOCAL_VALIDATED`와 `db_published=false`를 그대로 보존했다.
실제 DB 날짜 커밋 여부는 별도 실행 기록의 `COMMITTED_AND_VERIFIED`로 구분한다.
스냅샷 날짜 등록은 모든 지표가 준비됐거나 서비스 snapshot 공개가 완료됐다는 뜻이 아니다.

## 검토 및 정적 확인

독립 검토에서 DuckDB 원래 오류를 가리는 메시지, TIMESTAMPTZ의 `+00` 표기 처리,
footer 읽기 크기를 충분히 검사하지 않는 테스트를 보완했다. 코드 8개 파일 AST 문법 검사,
compileall 및 새 문서의 로컬 링크 검사가 통과했다. 이 모듈용 별도 lint/typecheck 설정은 없으며
검증 도구를 추가 설치하지 않았다. 통합 테스트는 환경 미지정 시 skip되지만 이번 실행은 skip 0을
추가 성공 조건으로 검사했다. 실패하거나 생략된 테스트를 성공 개수에 포함하지 않았다.
