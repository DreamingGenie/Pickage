# Spec 템플릿 — 커뮤니티 백엔드 Phase

> 코드를 작성하기 전, 이 템플릿을 복사해 `specs/<Jira키>-<slug>.md`로 새 Spec을 작성하고
> 오세진 님의 승인을 먼저 받는다. Acceptance Criteria는 새로 쓰지 않고 해당 Jira 이슈의
> "완료 판단 기준"을 그대로 인용한다 — 정본은 Jira다.
>
> 작성 후 바로 승인 요청하지 않는다. 아래 "자체 검증" 절을 먼저 채운다
> ([`../AGENTS.md`](../AGENTS.md) Workflow Rules 2번).

## 0. 대상 Phase

- Jira: `S15P21A506-NNN` (링크)
- 브랜치: `api/feat/S15P21A506-NNN-<slug>` (`sh scripts/new-branch.sh api feat NNN <slug>`)
- 구현계획 문서 참고 절: [`../Pickage_GitHub커뮤니티_구현계획_260908.md`](../Pickage_GitHub커뮤니티_구현계획_260908.md) §…
- 선행 Phase: (없음 / Phase N)

## 1. 작업 개요

- 작업명 / 목표:
- Jira 이슈 "필요한 이유"·"영향 범위" 요약 (본문 재인용, 새로 해석하지 않는다):

## 2. 변경 대상 (Scope)

- 추가될 파일과 역할:
- 수정될 파일과 변경 사항:
- 범위 밖 — 이 Phase에서 하지 않을 일 (Jira "영향 범위"의 제외 항목 그대로):

## 3. 아키텍처 / 데이터 흐름

- 관련 기존 코드 패턴 (예: `domain/packages/PackageController.java`의 wrapper·snake_case 재사용 방식):
- 필요 시 Mermaid로 입력~출력 흐름 표현:

## 4. 예외 및 엣지 케이스

- Jira "세부 항목"의 각 체크박스를 어떻게 구현할지:
- 외부 의존성으로 남겨둘 것 ("확인 필요(외부 의존성)"로만 표시, 대신 fake/stub 사용):

## 5. 검증 계획

- [ ] 테스트 명령: `./gradlew test --tests "...")` 등 실제 실행 가능한 명령으로 적는다
- [ ] 격리 테스트 DB가 필요하면 방법 명시 (기존 애플리케이션 DB·로컬 seed 사용 금지)
- [ ] Jira "완료 판단 기준" 체크박스 각각을 어떤 테스트/확인으로 충족할지 매핑
- [ ] 시크릿 노출 여부 체크

## 6. 자체 검증 (승인 요청 전 필수)

Spec에 적은 파일 경로·클래스명·DTO 필드·migration 번호가 실제 코드/브랜치 상태와 맞는지
대조한 결과를 적는다.

- 확인한 실제 파일/패턴:
- 발견해 Spec에 반영한 차이:
- 이 Spec에서 아직 못 정한 것 (사용자 확인 필요 항목):

---
승인 후 이 줄 아래에 승인 일시와 승인자를 기록한다.
