# A506 팀의 빅데이터 분산 프로젝트

에이전트·팀 협업 규칙(초안): [`.agents/AGENTS.md`](.agents/AGENTS.md)

## 개발 환경 셋업

클론 직후 **1회만** 실행하세요. 커밋 메시지에 Jira 이슈 키를 강제하는 git hook이 켜집니다.

```bash
# macOS / Linux / Git Bash
sh scripts/setup-hooks.sh
```

```bat
:: Windows CMD / PowerShell
scripts\setup-hooks.bat
```

### 커밋 메시지 규칙

제목 맨 끝에 Jira 키를 괄호로 붙입니다.

```
feat: deps.dev BigQuery 수집기 추가 (S15P21A506-122)
```

훅은 **브랜치명에 Jira 키가 있을 때만** 동작합니다.

- `feat/S15P21A506-122-bq-collector` → 메시지에 키가 없으면 **자동 삽입**. 키를 엉뚱한 위치에 쓰면 거부.
- `develop`, `chore/project-setting` 등 키 없는 브랜치 → 검사하지 않음.
- Merge / Revert / fixup! 커밋 → 검사 제외.
