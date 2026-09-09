# S15P21A506 — Pickage

팀 협업 규칙 정본은 [`AGENTS.md`](AGENTS.md) 다 (이 파일 끝에서 import 한다).
아래는 그중 **실제로 가장 자주 어긋나는 세 가지**를 바로 지킬 수 있게 앞으로 뽑아 둔 것이다.

## 1. 브랜치 — 만들기 전에 반드시 확인

```
<part>/<type>/<issue_no>-작업내용
```

- `part` — `frontend` `api` `data` `ai` `worker` `infra` `docs` (**담당 파트. 폴더명이 아니다**)
- `type` — `feat` `fix` `refactor` `test` `chore` `docs` `style` `config`
- `issue_no` — Jira 키 전체. `S15P21A506-290` (숫자만 쓰지 않는다)

`git switch -c` 를 직접 쓰지 말고 헬퍼를 쓴다. `origin/develop` 최신 상태에서 분기해 준다.

```bash
sh scripts/new-branch.sh data feat 290 downloads-bronze-ingest
# → data/feat/S15P21A506-290-downloads-bronze-ingest
```

`part` 를 빠뜨린 `feat/S15P21A506-290-...` 는 규칙 위반이다.
**2026-09-09 이전에 만들어진 브랜치는 전부 이 위반 형태이므로, 기존 브랜치명을 보고
새 브랜치 이름을 정하지 말 것.** `.githooks/pre-push` 가 새 브랜치 첫 push 에서 거부한다.

## 2. 커밋

```
type: subject (S15P21A506-290)
```

- 콜론 **뒤에만** 공백 (`feat: …`, `feat : …` 아님). subject 50자 이내, 끝에 마침표 없음
- Jira 키는 제목 맨 끝 괄호. 브랜치명에 키가 있으면 `.githooks/commit-msg` 가 자동으로 넣는다
- 본문에는 어떻게가 아니라 **무엇을·왜** 바꿨는지 쓴다

## 3. 착수·반영

- 코드/문서 작업 전에 Jira 이슈를 찾거나 만들고, **그 키로 브랜치를 딴다** (절차는 AGENTS.md 3번 항목)
- 병합 흐름은 `기능 브랜치 → develop → main`. `develop`·`main` 에 직접 push 하지 않고 MR로 리뷰받는다
- MR·Jira 본문은 한국어로 쓴다 (AGENTS.md 2번 항목)

---

@AGENTS.md
