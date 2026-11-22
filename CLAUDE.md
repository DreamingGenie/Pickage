# S15P21A506 — Pickage

> **상태(2026-11-22) — 이 절이 아래 모든 절과 `AGENTS.md`보다 우선한다.**
> - 팀 프로젝트(SSAFY 빅데이터 분산, 6인)는 2026-10에 끝났고 운영 서버는 2026-10-02에 정리했다. 남은 한계는 [`docs/알려진_한계_261121.md`](docs/알려진_한계_261121.md).
> - origin = GitHub `DreamingGenie/Pickage`(공개, 기본 브랜치 `develop`). 원본 SSAFY GitLab은 원격명 `gitlab`으로 남아 있다 — **push하지 않는다.**
> - 지금은 전진 혼자 가끔 손보는 저장소다. **Jira는 쓰지 않는다.** `AGENTS.md`의 Jira 조회·생성·전이(1·3·6절)와 GitLab MR 템플릿·push 옵션(2·5절)은 팀 시절 기록이라 따르지 않는다.

## 지금 작업하는 방법

1. **브랜치**: `<part>/<type>/<작업내용>` — Jira 키 없이. `part`·`type` 목록은 아래 1절(= `AGENTS.md` 4.2절) 그대로 쓴다.
   `origin/develop`에서 딴다: `git switch -c data/fix/<작업내용> origin/develop`. (`scripts/new-branch.sh`는 Jira 번호를 요구하므로 쓰지 않는다.)
2. **커밋**: `type: subject` — 콜론 뒤에만 공백, 50자 이내, 끝에 마침표 없음. Jira 키를 붙이지 않는다.
3. **훅**: `.githooks/`의 `commit-msg`·`pre-push`는 Jira 키를 전제한다(`pre-push`는 키 없는 새 브랜치를 거부한다). 종료 뒤에는 켜지 않는다 — 새로 clone해도 `scripts/setup-hooks.*`를 돌리지 않고, 켜져 있으면 `git config --unset core.hooksPath`. 훅 파일은 팀 시절 기록으로 둔다.
4. **반영**: GitHub PR → `develop`. 리뷰어가 없으므로 머지 전에 `develop`과의 diff를 직접 본다. 머지 커밋 본문은 비운다. 공개 저장소라 커밋·PR에 AI 공동작성 표시를 넣지 않는다.
5. 아래 1~3절은 팀 시절 규칙이다. 1절의 `part`·`type` 표와 2절의 커밋 형식(키 제외)만 지금도 쓴다.

---

# 팀 시절 규칙 (2026-09 ~ 10 — 기록)

팀 협업 규칙 정본은 [`AGENTS.md`](AGENTS.md) 다 (이 파일 끝에서 import 한다).
아래는 그중 **실제로 가장 자주 어긋나는 세 가지**를 바로 지킬 수 있게 앞으로 뽑아 둔 것이다.

## 1. 브랜치 — 만들기 전에 반드시 확인

```
<part>/<type>/<issue_no>-작업내용
```

- `part` — `frontend` `api` `data` `ai` `worker` `infra` `docs` `plan` (**담당 파트. 폴더명이 아니다**)
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
- **MR 본문은 `.gitlab/merge_request_templates/default.md` 의 섹션을 전부 채운다.**
  `-o merge_request.description=` 로 쓰지 말 것 — 개행이 안 들어가 템플릿을 못 지킨다.
  제목만 push 옵션으로 주고, 본문은 웹 편집의 플레인텍스트 모드에서 채운다 (AGENTS.md 2·5번 항목)

---

@AGENTS.md
