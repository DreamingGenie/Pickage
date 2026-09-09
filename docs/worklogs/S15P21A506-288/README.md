# S15P21A506-288 — 패키지 스냅샷 지표 통합·PostgreSQL 적재

이미 게시된 다운로드 구간 합계와 저장소의 stars·open_issues를 같은 패키지·기준일로 연결해
`package_snapshot`에 적재하는 작업이다. 전체 승인 패키지를 유지하고, 부분합·NULL·실제 0과
각 지표의 품질 근거를 함께 추적한다.

**현재 상태: 저장소 지표 브랜치 합류·병합 검증 완료. 통합 산출물 구현·DB 적재는 미착수.**

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
| 실행 범위 | 초도 한 기준일의 로컬 검증·적재. 과거 전체 기간·운영 서버 적용은 제외 |

저장소 지표 코드가 커밋된 사실과 산출물의 승인 상태는 별개로 확인한다. 두 선행 산출물은
완료 기록이 있지만, 이번 작업의 입력 재검증과 PostgreSQL 게시가 끝났다는 의미는 아니다.

| 문서 | 역할 |
| --- | --- |
| [01 작업 범위](01-scope.md) | 목표·대상·보존 조건·완료 기준 |
| [02 작업 계획](02-plan.md) | 선행 조건·구현·검증·실제 적재 순서 |
| [03 이슈](03-issues.md) | 미확인 사항·설계 쟁점·해결 조건 |
| [04 작업 일지](04-work-log.md) | 실제 수행한 내용과 확인 근거 |
| [05 결과](05-results.md) | 선행 실측 참고값과 이번 작업의 검증 상태 |
| [06 통합 적재 계약](06-load-contract.md) | 승인 입력·컬럼 매핑·품질·게시·재실행 계약 |
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
  [선행 실행 증거](../05-repository-metrics/03-measured-evidence.json). 코드와 문서를 합류했으며 실제 산출물은 기존 MinIO 실행을 소비할 예정이다.

`input-handoff.json`과 `documentation-check.json`은 착수 문서 작성 당시의 기록을 보존한다.
그 이후의 브랜치 합류와 검증 상태는 `merge-validation.json` 및 작업 일지에서 확인한다.

실행하지 않은 항목은 미실행으로 남기고, 테스트·원격 객체 검증·DB 적재를 구분해 기록한다.
원본 데이터·인증정보·개인 실행 파일은 문서에 복사하지 않는다. 기존 선행 작업의 완료 증거를
덮어쓰지 않고 이 티켓의 새 실행 증거를 추가한다.
