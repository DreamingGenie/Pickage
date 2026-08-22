# S15P21A506 팀 공통 에이전트 규칙 (초안)

이 문서는 아직 팀 전체 합의가 끝나지 않은 **초안**입니다. 현재는 아래 "기록 언어 규칙"과
"작업 전 Jira 연동 워크플로우"만 확정되어 있습니다. Git 브랜치/커밋 컨벤션, MR 템플릿/리뷰
규칙, 스펙 주도 개발 여부 등 나머지 협업 규칙은 팀원들과 논의 후 이 문서에 추가합니다.

## 1. Jira 프로젝트 정보

- Cloud: `ssafy.atlassian.net`
- Project Key: `S15P21A506`
- Board(Timeline): https://ssafy.atlassian.net/jira/software/c/projects/S15P21A506/boards/14925/timeline
- 이슈 유형 (한글 이름으로 JQL 검색하면 `이슈 유형 = 에픽` 같은 쿼리가 실패하는 경우가 있어
  **ID로 검색하는 것을 권장**):
  | 이름 | ID |
  | --- | --- |
  | 에픽 (Epic) | `10000` |
  | 스토리 (Story) | `10001` |
  | 작업 (Task) | `10002` |
  | 하위 작업 (Subtask) | `10003` |
  | 버그 (Bug) | `10004` |
- 에픽 연결: `createJiraIssue`의 `parent` 파라미터에 에픽 키(예: `S15P21A506-20`)를 지정
  (classic 프로젝트라 내부적으로 `customfield_10014` 에픽 링크 필드와 동기화됨)
- 스프린트 연결: `customfield_10020` (스프린트 ID 정수 단일값, 예: `53719`. 배열로 감싸면
  `createJiraIssue`에서 "스프린트에 유효한 값을 지정하세요" 오류 발생) — `additional_fields`로 지정

## 2. 기록 언어 규칙 — MR / Jira (확정)

에이전트가 생성하는 Merge Request와 Jira 이슈는 **한국어로 기록**합니다.
영어로만 작성하면 팀원들이 리뷰/추적하기 어렵기 때문입니다.

- **Merge Request**
  - 제목(title): 영어 가능 (커밋 메시지 컨벤션과 맞춰도 무방)
  - 본문(description): **반드시 한국어**로 작성 — 변경 이유, 주요 변경 내용,
    영향 범위, 확인/테스트 방법 등을 팀원이 읽고 리뷰할 수 있게 기술
- **Jira 이슈**
  - 제목, 설명, 코멘트 전부 **한국어**로 작성 (`createJiraIssue`,
    `addCommentToJiraIssue` 등으로 생성/갱신하는 모든 텍스트 포함)

커밋 메시지 자체의 언어(영어/한국어)는 이 규칙과 별개이며 기존 관례를 따릅니다.

**구현 참고 (에이전트용):** `git push -o merge_request.description="..."`는
실제 개행문자를 포함할 수 없다(git이 거부함). 여러 항목을 나열해야 하는 본문은
줄바꿈 대신 번호(`1)`, `2)`...)나 가운뎃점(`·`) 구분자로 한 줄에 작성하거나,
push 이후 GitLab 웹 UI/API로 본문을 갱신한다. 이때 저장된 git 자격증명을
추출해 API를 직접 호출하는 것은 지양한다.

## 3. 작업 전 Jira 연동 워크플로우 (AI 에이전트 필수 준수)

코드/문서 작업을 시작하기 전, 반드시 아래 절차를 따릅니다.

1. **기존 이슈 검색**: `searchJiraIssuesUsingJql`로 작업 내용과 관련된 이슈가 이미 있는지 확인합니다.
   ```
   project = S15P21A506 AND text ~ "<키워드>" ORDER BY created DESC
   ```
2. **있으면 연결**: 찾은 이슈 키를 작업 기준으로 삼습니다. 착수 시 `addCommentToJiraIssue`로
   진행 사실을 남기고, 필요하면 `transitionJiraIssue`로 상태를 "진행 중"으로 바꿉니다.
3. **없으면 생성 후 연결**:
   - 현재 진행 가능한 에픽 확인 (완료되지 않은 에픽만):
     ```
     project = S15P21A506 AND issuetype = 10000 AND statusCategory != Done ORDER BY created ASC
     ```
     작업 내용과 가장 맞는 에픽을 고릅니다. 애매하면 추측하지 말고 사용자에게 물어봅니다.
   - 현재 활성 스프린트 확인:
     ```
     project = S15P21A506 AND sprint in openSprints()
     ```
     반환된 이슈 중 아무거나 `customfield_10020` 필드를 읽어 활성 스프린트 id를 확인합니다
     (스프린트는 주 단위로 바뀌므로 매번 새로 조회 — 하드코딩 금지).
   - `createJiraIssue`로 이슈를 생성하며 `parent`에 위에서 고른 에픽 키를,
     `additional_fields`에 `{"customfield_10020": <sprintId>}`를 지정합니다.
4. **작업 종료 후**: 완료되면 `transitionJiraIssue`로 상태를 "완료"로 전이하고,
   필요하면 `addCommentToJiraIssue`로 결과를 요약합니다.

## 4. 향후 추가 예정 (팀 합의 필요)

- Git 브랜치/커밋 컨벤션
- MR(Merge Request) 템플릿 및 리뷰 규칙 (기록 언어는 2번 항목에서 확정됨 — 템플릿 구조/리뷰어 지정 등 나머지만 남음)
- 스펙 주도 개발(Spec-Driven Development) 여부
- 시크릿/보안 관리 규칙
