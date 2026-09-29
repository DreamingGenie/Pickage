# 통합 정합성 검증 준비 도구

9번 작업의 작은 정답 데이터와 검증 SQL, **명시적으로 복사한 native 입력의 연결 코드**를 준비한다.
기존 기본 CLI는 합성 fixture를 DuckDB 메모리에서만 검사한다. 별도 native CLI의 지원 형식과
작은 파일 검사 범위는 [native 입력 안내](NATIVE_INPUT.md)를 따른다.
기존 합성/native CLI에는 DB 연결·네트워크·Docker·서비스 쓰기 기능이 없다.
2026-09-14 추가한 실제 검증 경로는 Docker의 psql로 로컬 DB를 읽기 전용 조회한다.
범위·명령·제약은 [실제 검증 실행 안내](REAL_INPUT.md)를 따른다.
기존 `duckdb` 의존성을 사용하고, 스레드 1개·메모리 128 MB·디스크 spill 0 B로 제한한다.

## 실행

저장소 루트에서 기존 DuckDB가 설치된 Python으로 실행한다.

```powershell
python -B -m pipeline.integrity_validation --output data/integrity-demo-01
python -B -m unittest discover -s pipeline/integrity_validation -t . -v
```

별도 worktree에 Python 환경이 없으면 원래 저장소의 `.venv-bq/Scripts/python.exe`를
실행 파일로 지정한다. 작업 디렉터리는 이 worktree를 유지한다. 새 의존성 설치는 필요 없다.

`--fixture <JSON>`으로 2 MiB·전체 5,000행 이하의 작은 예제를 지정할 수 있다.
입력 포맷은 [정답 예제](fixtures/normal.json), 열 계약은 [schema.py](schema.py)를 따른다.
행의 모든 열을 명시해야 하며 필드 부재와 명시적 `null`을 구분한다. JSON 타입 열은 JSON을
담은 문자열 또는 SQL NULL을 뜻하는 `null`이다. 예를 들어 문자열 `"null"`은 JSON null이다.
naive timestamp는 V1 서비스 저장 방식에 맞춰 UTC로 해석하며, 기존 snapshot 정책 parser로
microsecond를 보존한다. 별도 원천의 시간 의미를 이 adapter로 자동 승인하지 않는다.

종료 코드는 0(합성 데이터 PASS), 1(위반 탐지), 2(입력·실행·출력 오류)다.
SQL 검사 중 오류도 ERROR 보고서에 남는다. 같은 출력 디렉터리로 재실행하면 이전 결과를
덮어쓰지 않고 거부한다. 입력/출력 준비 오류는 stderr로 보고하며 성공 보고서를 만들지 않는다.

## 생성 결과

| 파일 | 용도 |
| --- | --- |
| `report.json` | 검사별 결과·입력 SHA·검증 코드 SHA·PARTIAL 품질·미실행 항목 |
| `report.md` | 사람이 읽는 결과 |
| `integrity_checks.sql` | 나중에 별도 PostgreSQL 검증 환경에서 실행할 SELECT 모음 |
| `schema_catalog.sql` | 실제 열 타입·기본값·순서 있는 PK/FK·인덱스 수집 SQL |
| `query_plans.sql` | 현재 백엔드의 다운로드 추이·의존 수 추이·버전 분포 조회 계획 템플릿 |
| `evidence_contract.md` | SQL의 `validation.*` 근거 입력 계약과 아직 필요한 연결 |

SQL 파일은 psql용 `ON_ERROR_STOP`, 읽기 전용 transaction, timeout, ROLLBACK으로 감싼다.
실행 대상은 전체 테이블이므로 현재 DB 성능 실험 중에는 실행하지 않는다. 이 단계에서는
최초 준비 단계에서는 PostgreSQL 구문·catalog 대조·실행계획을 실측하지 않았다. `validation.*`의 근거 준비도
후속 작업이며 SQL 파일은 해당 테이블이나 뷰를 만들지 않는다.
`query_plans.sql`은 `EXPLAIN`만 사용하므로 실제 소요시간·buffer·WAL 측정이 아니다.
실측은 8번 실험과 적재가 끝난 뒤 별도 계획에 따라 진행한다.

fixture 파일 SHA는 원문 바이트, content SHA는 정규화 JSON, validator SHA는 검사 코드와
사용한 timestamp 정책을 식별한다. 이 해시를 과거 원천 산출물의 생성 계약으로 기록하지 않는다.

## 검증하는 의미와 한계

- 서비스 5개 테이블의 행 수, 키 중복, 참조 관계, NULL·비음수·문자열 길이를 검사한다.
- package_snapshot은 승인한 전체 package 모집단, PVS는 별도로 선정한 target 버전 집합에 맞춘다.
- 직접 count는 target별 `DISTINCT(source_package_id, source_version)`이다.
  source는 target 선정 목록 밖의 패키지와 여러 버전을 포함한다. 중복 선언은 한 번만 센다.
- target의 실제 0은 계산 COMPLETE·유효 target·성공한 직접 관계 없음과 함께 확인한다.
  resolution PARTIAL은 성공 관계 기준 count와 별도로 보존한다.
  미해석 선언 수가 0이어도 다른 source 품질 누락으로 PARTIAL일 수 있어 이를 자동 승격하지 않는다.
- 선택된 target와 edge의 source 시각을 정확한 snapshot timestamp와 비교한다.
  공개 version 테이블에 미래 버전이 존재하는 것만으로 실패시키지 않는다.
- NULL/0은 독립 정답 지표와 비교한다. 실제 `[P,S)` 일별 원천, 저장소 관측 시각,
  npm semver 해석 자체를 이 fixture로 다시 검증한 것은 아니다.

합성 검사 보고서는 `SYNTHETIC_FIXTURE_ONLY`, `ready_for_publication=false`, `task_09_complete=false`다.
기존 loader 호출을 모킹해서 실제 rollback/retry 검증인 것처럼 보고하지 않는다. 기존
입력 validator를 우회하는 범용 manifest 승인기도 추가하지 않는다. 승인된 native run,
파일 전체 SHA, 실제 스키마·참조·값, loader 장애/재시도, 조회 성능은 후속 검증 항목이다.
공급된 target·edge·PVS·기대 행 수가 함께 누락되면 이 도구의 내부 대조만으로는 발견할 수 없다.
빈 target 입력을 포함한 원천 모집단의 완전성은 독립 승인 manifest 연결 후 별도로 입증해야 한다.

작업 범위와 수행 결과: [작업 기록](../../docs/worklogs/09-integrity-validation/README.md).
