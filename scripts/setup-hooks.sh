#!/bin/sh
# 저장소 git hook 활성화 (클론 후 1회만 실행)
set -e
cd "$(dirname "$0")/.."
git config core.hooksPath .githooks
chmod +x .githooks/* 2>/dev/null || true
echo "git hook 활성화 완료 (core.hooksPath = .githooks)"
echo "  commit-msg : 커밋 제목 형식·Jira 키"
echo "  pre-push   : 새 브랜치 이름 규칙"
