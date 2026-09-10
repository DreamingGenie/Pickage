# S15P21A506-283 작업 공간 준비 기록

작성일: 2026-09-09 (Asia/Seoul)

## 변경 범위와 결과

사용자가 만든 원격 브랜치 `feat/S15P21A506-283-requirements-snapshot`을 추적하는 로컬 브랜치와 별도 worktree를 준비했다. 이번 범위는 작업 공간과 문서 준비다. requirements 해석 구현, 대량 계산, MinIO 게시, DB 적재는 수행하지 않았다.

| 작업 | 폴더 | 브랜치 |
| --- | --- | --- |
| 04 다운로드 구간 집계 | `C:/Users/SSAFY/workspace/S15P21A506` | `feat/S15P21A506-278-downloads-bronze-ingest` |
| 05 저장소 지표 | `C:/Users/SSAFY/workspace/S15P21A506-05-repository-metrics` | `codex/05-repository-metrics` |
| 07 requirements 해석 | `C:/Users/SSAFY/workspace/S15P21A506-283-requirements-snapshot` | `feat/S15P21A506-283-requirements-snapshot` |

## 계획과 실제 수행

1. 기존 worktree와 브랜치, 새 폴더 및 로컬 브랜치 이름의 중복 여부를 확인했다.
2. 사용자 지정 원격 브랜치를 fetch하고 시작 커밋을 확인했다.
3. 해당 원격 브랜치에서 로컬 추적 브랜치와 worktree를 생성했다.
4. Git에 포함되지 않은 `docs/jira/db-loading` 문서 12개를 명시적으로 복사하고 각 복사본의 SHA-256을 검증했다.
5. 이 기록과 새 worktree 전용 `AGENTS.md`를 추가했다.
6. 새 브랜치의 HEAD와 upstream, 기존 04/05 브랜치와 HEAD 및 Git index 해시를 읽기 전용으로 검증했다.

시작 커밋은 `fb2f8387c4a34e58693cad58cda24fd835eba0a8`이다. 이 커밋에는 package/version 적재 `077da74`와 snapshot 재실행 보정 `8187cfe`가 모두 포함되어 있다. 이미 커밋된 03 다운로드 코드도 기준 브랜치에 포함되어 있지만 기존 폴더에서 진행 중인 미커밋 04 코드와 05 worktree의 변경은 복사하지 않았다.

## 입력과 출력 경계

아래는 준비 시 디렉터리 존재가 확인된 입력 후보다. 입력 승인, snapshot 일치, manifest와 파일 해시 검증은 실제 07 실행 전에 수행한다.

| 입력 후보 | 읽기 전용 참조 경로 |
| --- | --- |
| requirements | `C:/Users/SSAFY/workspace/S15P21A506/data/raw/requirements/snapshot=2026-08-31` |
| versions_full | `C:/Users/SSAFY/workspace/S15P21A506/data/raw/versions_full/snapshot=2026-08-31` |
| Curated package/version | `C:/Users/SSAFY/workspace/S15P21A506/data/curated/curated-20260907-v2-oxudhdl5` |
| snapshot 기준일 후보 | `C:/Users/SSAFY/workspace/S15P21A506/data/snapshot/S15P21A506-269/projects-v1` |

원본 데이터, 가상환경, 자격증명 파일은 복사하지 않았다. 새 결과와 임시 파일은 07 worktree의 `data/requirements-resolution/<run-id>/` 등 별도 경로에 생성한다. 읽기 전용은 작업 규칙이며 파일시스템 ACL로 강제한 격리는 아니다. 시스템 자원과 외부 서비스는 공유된다.

## 이슈와 해결

- 작업 문서가 미추적 상태여서 원격 브랜치 checkout에 포함되지 않았다. 티켓 11개와 색인 1개만 복사했다. 문서 사본은 자동 동기화되지 않으므로 후속 구현에서 최신 결정과 대조한다.
- 기존 04 작업의 branch를 전환하지 않고 새 worktree를 추가했다. 04/05의 branch, HEAD, Git index SHA-256은 생성 전후 동일했다.
- 07의 peer/optional, 배포일 NULL 등 미확정 정책은 구현 단계의 결정 항목이다. 이번 폴더 준비에서 정책을 확정하지 않았다.

## 확인된 상태와 남은 작업

- 07 branch와 upstream 연결, 원격과 같은 HEAD, 선행 커밋 포함, 복사 문서 12개의 SHA-256 일치를 확인했다.
- 기존 04 index SHA-256: `2CFDBA17F7ADC90DFA967FFD65F99398E4CF22AB6833681F95F128AC39FC67D7`.
- 기존 05 index SHA-256: `9FED3A1864787619AE9DD43844DAF732F9511D9A54A922565DC0F1BA60887D18`.
- 준비 문서는 미커밋 상태로 남겼으며 commit/push는 수행하지 않았다.
- 애플리케이션 코드 변경이 없어 구현 테스트는 실행하지 않았다. 07 파이프라인 구현, 소규모 검증과 실제 계산은 후속 작업이다.
- 이 작업에서 계속 진행할 때 도구 작업 경로를 07 worktree로 명시한다. worktree 생성이 현재 Codex 작업의 앱 연결 경로를 자동으로 변경한 것은 아니다.
