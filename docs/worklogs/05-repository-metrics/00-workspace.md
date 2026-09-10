# 05 작업 폴더 분리 기록

작성일: 2026-09-09 (Asia/Seoul)

## 변경 범위와 목적

03 다운로드 Bronze 작업이 실행 중인 기존 폴더를 유지하면서 05 저장소 지표 작업용 Git worktree와 브랜치를 추가했다. 이번 범위는 작업 공간 준비이며, 05 파이프라인 구현과 데이터 적재는 수행하지 않았다.

| 용도 | 경로 / 기준 |
| --- | --- |
| 03 기존 폴더 | `C:/Users/SSAFY/workspace/S15P21A506` |
| 03 확인 브랜치 | `feat/S15P21A506-278-downloads-bronze-ingest` |
| 05 새 폴더 | `C:/Users/SSAFY/workspace/S15P21A506-05-repository-metrics` |
| 05 브랜치 | `codex/05-repository-metrics` |
| 공통 시작 커밋 | `e3a8a6240b1edd1fb45dedc0d4a9a9cbc3bdf074` |

## 실제 진행한 작업

1. 원래 폴더의 branch, HEAD, worktree 목록과 미커밋 파일 목록을 읽었다.
2. 별도 worktree를 공통 커밋에서 생성했다. 기존 폴더의 미커밋 코드와 Git index는 복사하거나 변경하지 않았다.
3. 기존 폴더에서 미추적 상태인 `docs/jira/db-loading/*.md` 12개를 새 폴더에 복사하고 각 파일의 SHA-256 일치를 확인했다. 이는 2026-09-09 문서 사본이며 이후 두 폴더의 편집은 자동 동기화되지 않는다.
4. 새 폴더에 `AGENTS.md`와 이 분리 기록을 추가했다. commit/push는 수행하지 않았다.

## 입력과 출력 경계

다음은 원래 폴더에 존재하는 입력 위치다. 실행 전 manifest와 입력 계보를 다시 검증한다.

| 입력 | 읽기 전용 참조 위치 |
| --- | --- |
| Projects | `C:/Users/SSAFY/workspace/S15P21A506/data/raw/projects` |
| versions_full | `C:/Users/SSAFY/workspace/S15P21A506/data/raw/versions_full/snapshot=2026-08-31` |
| 기존 Curated 후보 | `C:/Users/SSAFY/workspace/S15P21A506/data/curated/curated-20260907-v2-oxudhdl5` |
| 스냅샷 후보와 inventory | `C:/Users/SSAFY/workspace/S15P21A506/data/snapshot/S15P21A506-269/projects-v1` |

- 새 출력과 임시 데이터는 05 폴더의 `data/repository-metrics/<run-id>/` 등 별도 경로에 저장한다.
- 대용량 데이터, 가상환경, 자격증명 파일은 복사하지 않았다. 가상환경 설정은 구현에 필요한 실행 환경을 확정할 때 수행한다.
- 원래 폴더로 향하는 junction/symlink를 만들지 않았다. 읽기 전용은 사용 규칙이며 파일시스템 ACL로 강제한 격리는 아니다.
- 파일과 Git index는 worktree별로 분리되지만 Git의 commit/branch 정보와 시스템 자원, 외부 DB/MinIO는 공유된다.

## 이슈와 해결

- 진행 중인 03 변경이 원래 폴더에 있으므로 현재 폴더의 branch를 바꾸지 않고 새 worktree를 만들었다.
- 티켓 문서는 아직 Git에 없어 자동 checkout되지 않았다. 12개 문서만 명시적으로 복사했다.
- 별도 `S15P21A506-278` 폴더가 존재하지만 조사 시 비어 있었다. 다른 세션의 준비 경로일 수 있어 이번 작업에서는 사용하거나 변경하지 않았다.

## 검증과 남은 작업

- 새 worktree 생성 성공, 시작 커밋과 브랜치 확인, 복사 문서 12개의 SHA-256 일치를 확인했다.
- 05의 구현 테스트, 대량 계산, MinIO 게시, DB 적재는 실행하지 않았다.
- 새 폴더 생성은 기존 채팅의 앱 연결 경로를 자동으로 변경하지 않는다. 이 채팅에서 이어갈 때 도구의 작업 경로를 05 폴더로 명시한다. 별도 채팅을 새로 열 때도 이 폴더를 작업 대상으로 지정한다.
- 구현 착수 시 작업 계획과 완료 기준, 승인 입력을 이 기록과 별도로 구체화한다.
