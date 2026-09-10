# 07 requirements 구현 범위와 작업 계획

작성일: 2026-09-09. 상태: 확정 정책으로 전체 계산을 완료했으며 결과와 검증 제한을 기록했다. 실제 결과는 05-full-run.md와 06-computation-results.md에 기록한다.

## 목표와 변경 범위

같은 snapshot의 승인된 Bronze requirements와 Curated package/version을 연결하여 모든 대상 source 릴리스 버전의 의존성 선언을 보존하고, npm semver를 만족하는 최대 target 버전을 결정한다. 08이 사용할 관계 Parquet, 선언별 해석 결과, source별 입력 완전성, 품질 사유와 불변 실행 manifest를 생성한다.

새 구현과 테스트는 `pipeline/requirements_resolution/`에 둔다. 작업 기록은 본 디렉터리, 티켓 수정은 `docs/jira/db-loading/07-requirements-resolution.md`로 제한한다. 공통 파이프라인, 04/05 worktree, 기존 package ID 및 서비스 DDL은 유지한다. PostgreSQL 적재와 dependents_count 계산은 08의 범위다.

## 확정 계약

| 항목 | 현재 상태 |
| --- | --- |
| source 집합 | 대표 버전으로 축소하지 않고 모든 eligible 릴리스 사용 |
| target 해석 | 같은 snapshot의 eligible 릴리스 중 실제 npm semver 최대 만족 버전; ordinal 대체 금지 |
| 시점 | `snapshot-time-v1`, 정확한 SnapshotAt 일치 및 T 이후 source/target 배제 |
| 패키지 식별 | 정확한 npm 이름과 기존 package_id, source/target 버전 원문 보존 |
| 의존성 종류 | 사용자 확정: 일반 dependencies만 계산. peer/optional 원본은 승인 Bronze 계보에 보존하고 제외 사유·개수를 기록 |
| 배포일 NULL | 07 source/target에서 제외 |
| 해석 실패 | PARTIAL 결과와 품질 사유 보존 |
| alias/tag/비레지스트리 | 자동 추정하지 않고 별도 미지원/미해석 사유로 보존 |

정책에 의존하지 않는 입력 검증과 명시적 정책 설정 구조부터 구현한다. 실제 계산은 선택한 정책 문서와 해시를 기록한 후 수행한다. 같은 입력과 정책에서 중복 선언은 선언 산출물에 보존하되 최종 edge는 티켓의 복합 grain으로 중복 제거한다.

## 처리 구조와 대안

설계 검토안: Spark가 모든 source 버전과 선언/후보를 Parquet로 준비하고, 호스트의 장기 실행 Node 프로세스가 패키지별 후보와 고유 제약식을 실제 npm semver로 처리한다. 이어 Spark가 해석 결과를 모든 선언에 연결해 최종 산출물과 품질 집계를 만든다. 전체 그래프를 드라이버 메모리에 수집하거나 관계마다 프로세스를 실행하지 않는다.

현재 설치된 Spark 컨테이너, npm 번들 semver, 기존 Python DuckDB/boto3 환경을 활용한다. 새 라이브러리를 설치하지 않는다. Node와 Spark가 다른 실행 환경에 있으므로 파일/manifest로 단계를 연결한다. 간단한 DuckDB 단독 파이프라인도 가능하지만 대규모 관계 join을 Spark로 처리하려는 기존 티켓 방향을 따른다. 최종 모듈 경계는 독립 설계 검토 후 확정한다.

## 실행 순서

| 단계 | 내용 | 완료 증거 | 상태 |
| --- | --- | --- | --- |
| P1 | 원본/Curated 승인 계약, 설치 런타임, 정책 선택 확인 | 입력 스키마·manifest 및 결정 기록 | 입력·런타임 확인, 사용자 정책 확정 |
| P2 | 입력 선택·로컬 파일 검증, npm bridge 및 정책 구현 | 입력 훼손·시간·ID·semver 경계 테스트 | 구현 및 테스트 통과 |
| P3 | Spark 선언/후보 생성 및 edge/품질 산출물 구현 | 모든 source 버전·NULL/empty·미해석·중복 키 검증 | 구현 및 실제 Spark 테스트 통과 |
| P4 | 불변 실행·재검증·07 전용 게시 구현 | manifest/해시/완료 표시·실패/재실행 테스트 | 로컬 및 메모리 S3 검증 통과; 실제 게시 미실행 |
| P5 | 격리된 전체 흐름 fixture와 독립 코드 검토 | 실제 Spark+Node 실행, 문제 수정 및 재검증 | 실제 통합 실행·재검증·복구 통과, 독립 검토 CLEAR |
| P6 | 실제 입력 사전 검증·자원 확인 후 전체 계산과 결과 검증 | 실제 run 결과, 행 수·품질·입력 계보·원격 게시 여부 분리 | 전체 계산 완료, PARTIAL 결과와 결과·footer 검증 기록, 게시 미실행 |
| P7 | 티켓·실행 문서·08 소비 계약 정리 | 완료 기준별 증거, 미실행/미확인 항목 표시 | 완료, 전체 계산 및 게시 미실행 명시 |

## 검증 기준

- 정상적인 빈 배열과 requirements 행 누락/NULL 배열을 구분한다.
- 범위/exact/union/tilde/caret/prerelease/build metadata 동률, alias/tag/file/git/잘못된 이름과 제약식을 검증한다.
- 동일 패키지의 여러 source 버전과 정확한 스코프 이름을 보존하고 source/target 미래 배포를 배제한다.
- 이름/ID·버전 복합키 중복, 원천 계보 불일치, 파일 누락/변조/경로 이탈은 실패한다.
- edge 복합키, 선언별 상태 및 source별 coverage 집계가 서로 일치해야 한다.
- 재실행은 고정 입력·정책·코드와 기존 산출물을 검증하고, 훼손되거나 불일치한 완료 결과를 덮어쓰지 않는다.
- 실제 입력의 일부를 검사한 결과를 전체 처리 성공으로 표시하지 않는다. PARTIAL은 후속 count의 완전성을 보장하지 않는다.

## 자원과 외부 상태

준비 시 PC는 논리 CPU 22개, 메모리 약 64GiB 중 약 28GiB가 비어 있었다. 값은 실행 중 변하므로 대량 계산 전에 다시 확인한다. 초기 Spark 실행은 CPU 2개·컨테이너 메모리 6GiB로 제한하고 임시 파일을 07 출력 경로에 둔다. 원본은 읽기 전용 마운트한다.

원격 상태는 승인 입력의 작은 manifest 조회부터 확인한다. 07 전용 게시 외의 기존 MinIO 객체·포인터와 DB는 변경하지 않는다. commit/push는 이번 구현 착수 범위에 포함하지 않았다.
