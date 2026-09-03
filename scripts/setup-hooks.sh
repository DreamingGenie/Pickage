#!/bin/sh
# 저장소 git hook 활성화 (클론 후 1회만 실행)
set -e
cd "$(dirname "$0")/.."
git config core.hooksPath .githooks
chmod +x .githooks/* 2>/dev/null || true
echo "git hook 활성화 완료 (core.hooksPath = .githooks)"
