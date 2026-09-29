#!/bin/sh
# 수집은 건너뛰고 차단된 Curated 회차만 다시 선택한다.
# 주간 timer와 같은 flock을 사용하므로 수집·전처리 회차와 겹치지 않는다.

set -eu
cd "$(dirname "$0")"
REPO=$(cd ../../.. && pwd)
INGEST_CONTAINER=pickage-weekly-run
CONTAINER=pickage-curated-dispatch
LOCK=/tmp/pickage-weekly.lock

if [ "$#" -ne 2 ] || [ "$1" != "--retry-snapshot" ]; then
  echo "사용법: sh run-curated-retry.sh --retry-snapshot YYYY-MM-DD" >&2
  exit 2
fi
case "$2" in
  ????-??-??) ;;
  *) echo "run-curated-retry.sh: 스냅샷은 YYYY-MM-DD 형식이어야 합니다." >&2; exit 2 ;;
esac

[ -f .env ] || {
  echo "run-curated-retry.sh: .env 가 없습니다." >&2
  exit 1
}
[ -f "$REPO/pipeline/minio/.env.data" ] || {
  echo "run-curated-retry.sh: pipeline/minio/.env.data 가 없습니다." >&2
  exit 1
}

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "[curated] weekly 수집 또는 전처리가 이미 돌고 있습니다 ($LOCK)." >&2
  exit 0
fi

if docker rm -f "$INGEST_CONTAINER" >/dev/null 2>&1; then
  echo "[curated] 지난 발화의 수집 컨테이너가 남아 있어 치웠습니다 ($INGEST_CONTAINER)."
fi
if docker rm -f "$CONTAINER" >/dev/null 2>&1; then
  echo "[curated] 지난 발화의 컨테이너가 남아 있어 치웠습니다 ($CONTAINER)."
fi

exec docker compose run --rm --name "$CONTAINER" curated-dispatch "$@"
