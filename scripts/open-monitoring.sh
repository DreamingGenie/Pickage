#!/bin/sh
#
# open-monitoring.sh — 서버 모니터링 화면 열기 (macOS / Linux / Git Bash)
#
#   sh scripts/open-monitoring.sh [ssh대상]
#
# SSH 터널을 열고 브라우저로 "지금 어때" 화면을 띄웁니다.
# 끝낼 때는 Ctrl+C. 그러면 터널이 끊깁니다.
#
# 대상과 키는 환경변수로도 줍니다:
#   PICKAGE_SSH_TARGET=ubuntu@j15a506.p.ssafy.io
#   PICKAGE_SSH_KEY=~/.ssh/pickage.pem
#
# 설명: deploy/prod/monitoring/README.md

set -e

TARGET="${1:-${PICKAGE_SSH_TARGET:-ubuntu@j15a506.p.ssafy.io}}"
PORT=19999
URL="http://127.0.0.1:${PORT}/status.html"

command -v ssh >/dev/null 2>&1 || { echo "ssh 를 찾을 수 없습니다." >&2; exit 1; }

# 이미 열려 있으면 터널을 또 열지 않는다. 두 번 열면 ssh 가
# "bind: Address already in use" 만 찍고 **포워딩 없이 계속 돌아서**,
# 사람은 연결된 줄 알고 "열었는데 왜 안 되지" 를 한참 본다.
#
# ⚠ nc 로 검사하지 않는다 — Git Bash 에 nc 가 없어서 검사가 통째로 건너뛰어진다(확인함).
#   curl 은 Git Bash·macOS·Ubuntu 에 다 있다.
OPEN_ONLY=0
if command -v curl >/dev/null 2>&1; then
  if curl -s -o /dev/null --max-time 2 "http://127.0.0.1:${PORT}/api/v1/info"; then
    echo "${PORT} 번이 이미 열려 있습니다. 브라우저만 엽니다."
    OPEN_ONLY=1
  fi
fi

open_browser() {
  if   command -v open        >/dev/null 2>&1; then open "$URL"
  elif command -v xdg-open    >/dev/null 2>&1; then xdg-open "$URL"
  elif command -v powershell  >/dev/null 2>&1; then powershell -NoProfile -Command "Start-Process '$URL'"
  else echo "브라우저를 직접 여세요: $URL"
  fi
}

if [ "$OPEN_ONLY" = "1" ]; then
  open_browser
  exit 0
fi

echo "서버에 연결합니다: ${TARGET}"
echo
echo "  - 잠시 뒤 브라우저가 열립니다. 처음 몇 초는 빨간 화면일 수 있는데,"
echo "    연결되면 저절로 바뀝니다."
echo "  - 다 보셨으면 Ctrl+C 를 누르세요. 그래야 터널이 끊깁니다."
echo

open_browser

if [ -n "$PICKAGE_SSH_KEY" ]; then
  exec ssh -N -L "127.0.0.1:${PORT}:127.0.0.1:${PORT}" -i "$PICKAGE_SSH_KEY" "$TARGET"
else
  exec ssh -N -L "127.0.0.1:${PORT}:127.0.0.1:${PORT}" "$TARGET"
fi
