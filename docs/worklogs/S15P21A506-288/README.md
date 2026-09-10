# S15P21A506-288 — 패키지 스냅샷 지표 통합·PostgreSQL 적재

이미 게시된 다운로드 구간 합계와 저장소의 stars·open_issues를 같은 패키지·기준일로 연결해
`package_snapshot`에 적재하는 작업이다. 전체 승인 패키지를 유지하고, 부분합·NULL·실제 0과
각 지표의 품질 근거를 함께 추적한다.

**현재 상태: 초도 2026-08-31 적재·검증과 배포일 기준으로 재구성한 전체 229개 기준일의 로컬 PostgreSQL 적재를 완료했다. 최종 결과는 646,219,939행이며, 과거 이력 구현·관련 테스트 61개·대표 3개 날짜의 독립 원천 대조도 통과했다.**

| 항목 | 확인 내용 |
| --- | --- |
| 연결 티켓 | S15P21A506-288. 브랜치명에서 확인했으며 원격 Jira 제목·설명·상태는 미확인 |
| 현재 브랜치 | `feat/S15P21A506-288-package_snapshot-postgresql` |
| 시작 HEAD | `110ba9c481558cbcf82c809ec4a5179dca588ce8` |
| 분기 기준 | 다운로드 구간 집계 브랜치에서 분기. 시작 HEAD는 해당 브랜치에 develop을 병합한 커밋과 동일 |
| 착수 확인 | 2026-09-09, 한국 표준시(+09:00) |
| 다운로드 구현 | 커밋 `4468b6c`, 현재 브랜치에 포함 |
| 저장소 지표 구현 | `codex/05-repository-metrics`, 커밋 `885f897858370632df0f8bad3e897eac02a2f4f3`. 병합 커밋 `f951c54`로 현재 브랜치에 포함 |
| 초도 대상 | S=`2026-08-31`, 다운로드 구간 `[2026-08-24,2026-08-31)` |
| 실행 범위 | 초도 한 기준일 완료 후 전체 229개 기준일의 로컬 적재로 확장. 운영 서버 적용은 별도 |

두 선행 산출물의 승인 상태와 실제 파일을 이번 작업에서 다시 검증했으며,
통합 Curated와 로컬 PostgreSQL 게시·재실행·독립 전수 대조까지 완료했다.

| 문서 | 역할 |
| --- | --- |
| [01 작업 범위](01-scope.md) | 목표·대상·보존 조건·완료 기준 |
| [02 작업 계획](02-plan.md) | 선행 조건·구현·검증·실제 적재 순서 |
| [03 이슈](03-issues.md) | 미확인 사항·설계 쟁점·해결 조건 |
| [04 작업 일지](04-work-log.md) | 실제 수행한 내용과 확인 근거 |
| [05 결과](05-results.md) | 선행 실측 참고값과 이번 작업의 검증 상태 |
| [06 통합 적재 계약](06-load-contract.md) | 승인 입력·컬럼 매핑·품질·게시·재실행 계약 |
| [07 직접 조회 SQL](07-inspect.sql) | DB 실행 이력·건수·실제 지표·품질 근거 조회 |
| [08 전체 기간 적재](08-full-history-plan.md) | 전체 달력·원천 조사, 이력 구성 기준과 날짜별 적재 계획 |
| [09 전체 기간 조회 SQL](09-inspect-history.sql) | 날짜별 실행 진행 상황·재구성 이력·실제 서비스 값 조회 |
| [10 통합 MR 본문](10-merge-request.md) | 다운로드·저장소 지표·통합 적재의 변경 범위와 검증 결과 |
| [11 리뷰 보완 작업](11-review-fixes.md) | 재검증 계약·품질 공통 형식의 변경 범위와 검증 결과 |
| [12 백엔드 인계 메모](12-backend-history-handoff.md) | 재구성 이력 표시·저장소 변경 시 증감 비교 조건과 확인 예시 |
| [13 품질 공통 형식](13-quality-schema.md) | 새 quality 컬럼 계약과 기존 승인 파일의 읽기 호환 |
| [전체 기간 최종 검증](evidence/history-full-load-validation.json) | 229개 기준일·646,219,939행과 기존 최신 값·포인터 보존 확인 |
| [선행 입력 기록](evidence/input-handoff.json) | 선택할 run·manifest SHA·기존 측정값·확인 범위 |
| [병합·검증 기록](evidence/merge-validation.json) | 합류 커밋·코드 해시·테스트·변경 및 보존 범위 |

P는 작업 단계, AC는 완료 기준, ISS는 이슈, W는 수행 기록, V는 검증 기록의 식별자다.
문서 파일의 숫자는 읽기 순서이며, 다른 임시 계획 문서의 작업 번호를 뜻하지 않는다.

## 선행 자료와 기록 원칙

- [다운로드 구간 집계 결과](../S15P21A506-278/08-interval-results.md)와 [모듈 안내](../../../pipeline/downloads_interval/README.md).
- [package·version 적재 기반](../../../pipeline/postgresql/README.md)과 [실제 적재 기록](../S15P21A506-267/05-results.md).
- [스냅샷 실행 이력 계약](../S15P21A506-269/06-history-contract.md)과 [스냅샷 모듈](../../../pipeline/snapshot/README.md).
- [서비스 테이블 DDL](../../../backend/src/main/resources/db/migration/V1__init.sql).
- [저장소 지표 모듈](../../../pipeline/repository_metrics/README.md)과
  [선행 실행 증거](../05-repository-metrics/03-measured-evidence.json). 코드·문서를 합류하고 승인된 기존 MinIO 산출물을 통합 입력으로 소비했다.

`input-handoff.json`과 `documentation-check.json`은 착수 문서 작성 당시의 기록을 보존한다.
그 이후의 브랜치 합류와 검증 상태는 `merge-validation.json` 및 작업 일지에서 확인한다.

실행하지 않은 항목은 미실행으로 남기고, 테스트·원격 객체 검증·DB 적재를 구분해 기록한다.
원본 데이터·인증정보·개인 실행 파일은 문서에 복사하지 않는다. 기존 선행 작업의 완료 증거를
덮어쓰지 않고 이 티켓의 새 실행 증거를 추가한다.
