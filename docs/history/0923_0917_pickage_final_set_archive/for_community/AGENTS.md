# GitHub 커뮤니티 백엔드 — Harness 운영 규칙

이 문서는 루트 [`AGENTS.md`](../../../../AGENTS.md)·[`CLAUDE.md`](../../../../CLAUDE.md)를 대체하지 않는다.
Git 브랜치·커밋·Jira 연동·MR 템플릿은 항상 루트 규칙을 그대로 따르고, 이 문서는 그 위에
**커뮤니티 백엔드 작업**(에픽 [`S15P21A506-323`](https://ssafy.atlassian.net/browse/S15P21A506-323))
에만 적용되는 Harness 규칙 — Phase 분할, Spec, Verify Loop — 을 추가한다.

`C:\Users\SSAFY\Desktop\til\agent&harness\README.md`의 Harness Engineering 흐름을 이 도메인에
맞게 구체화한 것이다. 원본 흐름:

```text
프로젝트 공통 규칙 정의 -> PRD 작성 -> Spec 작성 -> Harness Workflow 설계
  -> Phase 분할 -> Verify Loop 설계 -> Agent 역할 매핑 -> 완료 기준 정의
-> Phase 단위 실행 -> 사람 리뷰 -> 문서 업데이트 -> 작은 단위 commit -> 다음 Phase
```

## 이 문서 세트 자체의 보호 규칙

이 파일과 [`phases/README.md`](phases/README.md)·[`specs/TEMPLATE.md`](specs/TEMPLATE.md)는
오세진 님의 명시적 요청 없이 임의로 완화하거나 구조를 바꾸지 않는다. 내용을 바꿔야 할 근거를
찾으면 먼저 이유를 설명하고 승인을 받는다.

## 필독 문서 (구현 전에 반드시 읽는다)

1. 루트 [`AGENTS.md`](../../../../AGENTS.md) — Git·Jira·MR 컨벤션 (공통 규칙, 최우선)
2. PRD/Spec 원본: [`Pickage_GitHub커뮤니티_구현계획_260908.md`](Pickage_GitHub커뮤니티_구현계획_260908.md)
   — "무엇을 왜" 수준까지는 이 문서가 정본이다. Phase별 Spec은 이 문서를 새로 쓰지 않고
   해당 절만 인용·요약한다.
3. `phases/README.md` — 현재 Phase, 순서, 의존관계, 상태
4. 착수하려는 Phase의 `specs/<이슈키>-*.md`
5. 해당 Jira 이슈 본문의 "완료 판단 기준" — Acceptance Criteria는 여기가 정본이며 Spec에
   중복해서 새로 쓰지 않는다.

## 수정 가능 범위

- `backend/src/main/java/com/ssafy/pickage/domain/community/**` (신규 도메인 패키지 —
  기존 `domain/packages/`와 같은 평면 구조: 루트에 Controller/Service/Repository, `dto/`
  하위에 응답 DTO)
- `backend/src/main/resources/db/migration/V5__community.sql` (착수 시점 develop의 다음
  빈 번호가 V5가 아니면 그 번호로 조정 — 기존 V1~V4는 절대 수정하지 않는다)
- `backend/src/test/java/com/ssafy/pickage/domain/community/**`
- `docs/history/0923_0917_pickage_final_set_archive/for_community/**` (이 문서 세트)

범위 밖 — 손대기 전 반드시 이유와 범위를 먼저 설명하고 승인받는다:

- `deploy/local/seed/*.sql` 세 파일 — `community_snapshot` TRUNCATE 추가가 필요하지만
  공용 seed는 인프라 담당 경계다. [`S15P21A506-314`](https://ssafy.atlassian.net/browse/S15P21A506-314)
  본문에도 "공용 seed 변경의 인프라 경계는 이번 배정에서 보호"라고 명시돼 있다.
- `compose.yaml`, `.env.example`, Spring `application.yaml`의 외부 연동 설정
  (`GITHUB_COMMUNITY_TOKEN`, `GMS_*`) — 인프라 담당 영역
- `frontend/**` — 프론트 담당(rysud0125, [`S15P21A506-316`](https://ssafy.atlassian.net/browse/S15P21A506-316))
- GMS 실제 프로토콜·prompt·AI 평가 — 외부 의존성. "확인 필요(외부 의존성)"로 표시만 하고
  fake client로 대체해 진행한다 ([`S15P21A506-317`](https://ssafy.atlassian.net/browse/S15P21A506-317) 본문 참고)
- `domain/packages/**` 기존 코드 — 재사용은 하되(공통 wrapper·`message` 처리·snake_case),
  다시 구현하거나 수정하지 않는다

## Workflow Rules

1. **WIP = 1**: `phases/README.md`에서 "진행 중"으로 표시된 Phase가 이미 있으면 새 Phase를
   시작하지 않는다.
2. **Spec 승인 전 자체 검증**: Spec을 쓴 뒤 곧바로 승인을 요청하지 않는다. Spec에 적은
   파일 경로·클래스명·DTO 필드가 실제 코드(`domain/packages/**` 패턴, 기존 migration)와
   맞는지 먼저 대조하고, 어긋나면 Spec을 고친 뒤 승인을 요청한다.
3. **Plan에 없는 파일은 수정하지 않는다.** 꼭 필요하면 먼저 이유를 설명하고 승인받는다.
4. **테스트·빌드 없이 완료로 보지 않는다.** Verify Loop(아래)를 전부 거쳐야 "완료"다.
5. **완료 기준은 새로 쓰지 않는다.** 각 Phase의 Acceptance Criteria는 해당 Jira 이슈의
   "완료 판단 기준" 섹션이 정본이다. Spec·Phase 기록에서는 그 섹션을 인용만 한다.
6. **외부 의존성은 확정하지 않는다.** GMS 실연동, 인프라 secret 등 다른 담당이 결정할
   내용은 Spec/Phase 기록에 "확인 필요(외부 의존성)"로만 표시하고, fake/stub으로 우회해
   진행한다. 이 프로젝트에서는 이미 각 Jira 이슈 본문(212/213/314/317/315)에 이 경계가
   명시돼 있으므로 그 경계를 넘지 않는다.
7. **Git·Jira 연동은 루트 규칙 그대로.** 브랜치는 `api/feat/<이슈키>-작업내용`
   (`sh scripts/new-branch.sh api feat <이슈번호> <설명>`), 커밋은 `type: subject (이슈키)`,
   Phase 하나당 최소 1개 이상의 작은 commit으로 나눈다. MR은 Phase 완료 시점에 만들고
   본문은 루트 MR 템플릿 섹션을 그대로 채운다.

## Verify Loop

```text
Coding -> Test -> Review -> Verify -> Decide
```

| 단계 | 하는 일 | 이 프로젝트에서의 구체화 |
| --- | --- | --- |
| Coding | 현재 Phase 범위만 구현 | 위 "수정 가능 범위" 밖은 건드리지 않는다 |
| Test | 관련 테스트·빌드 실행 | `backend`: `./gradlew test` (관련 클래스) 및 필요 시 격리 테스트 DB 통합 테스트. 실패를 성공처럼 보고하지 않는다 |
| Review | 코드 품질·범위 초과·구조 문제 확인 | `/code-review` 스킬로 diff 검토 (별도 서브에이전트 관점 확보) |
| Verify | Acceptance Criteria 대조 | 해당 Jira 이슈의 "완료 판단 기준" 체크박스를 하나씩 대조 |
| Decide | 통과/재작업/범위조정 결정 | 오세진 님의 최종 리뷰 후 커밋·Phase 기록·Jira 상태 전이 |

## Agent 역할 매핑

1인 백엔드 개발 + Claude Code 세션이므로 별도 인스턴스를 여러 개 두지 않는다. 대신 같은
세션 안에서 아래 역할을 순서대로 명시적으로 전환한다 (역할이 섞이지 않도록 각 단계 결과를
먼저 보고한 뒤 다음 역할로 넘어간다).

| 역할 | 입력 | 책임 | 금지 |
| --- | --- | --- | --- |
| Researcher | 기존 코드, Jira 이슈 본문, 구현계획 문서 | Spec 작성 전 관련 파일·기존 패턴 조사 | 근거 없이 구현 방향 확정 |
| Planner (=Spec 작성) | 조사 결과, PRD | `specs/<이슈키>-*.md` 작성 | 코드 직접 수정 |
| Coder | 승인된 Spec | 정해진 파일만 구현 | Spec에 없는 파일·기능 확장 |
| Tester | 변경 코드 | 테스트·빌드 실행, 실패 원인 분석 | 실패 무시·과장 보고 |
| Reviewer | diff, Spec | 범위 초과·구조 문제·회귀 위험 확인 (`/code-review`) | 새 기능 임의 추가 |
| Verifier | 구현+테스트 결과 | Jira "완료 판단 기준" 대조 | Agent의 "완료" 선언만 보고 통과 |
| Documenter | 위 전체 결과 | `phases/<phase>.md` 기록, `phases/README.md` 갱신 | 실제와 다른 기록 |

각 Phase는 사람(오세진 님)이 Decide 단계에서 최종 승인해야 "완료"로 표시한다.

## 문서 갱신 규칙

- Phase 기록은 Phase가 끝난 뒤 새 파일로 만든다. 기존 기록은 덮어쓰지 않는다.
- `phases/README.md`는 Phase 상태가 바뀔 때마다(착수/완료) 갱신한다.
- PRD/Spec 원본(`Pickage_GitHub커뮤니티_구현계획_260908.md`)의 내용이 실제로 바뀌어야 하면
  바로 고치지 않고 무엇을·왜 바꿀지 먼저 제안한다 — [[feedback_plan_vs_impl_reeval]] 원칙과
  동일.
