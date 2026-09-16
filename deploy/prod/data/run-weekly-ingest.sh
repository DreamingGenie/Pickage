#!/bin/sh
#
# run-weekly-ingest.sh — 주간 수집 한 회차. **사람이 인자를 주지 않는다.**
#
# 무엇을 할지는 두 가지가 정한다. 스케줄러는 "새 것이 있나" 를 판단하지 않는다.
#
#     회차       그 주 월요일 (deps.dev 스냅샷 날짜)
#     상태       pickage-raw/_ops/weekly/<week_of>/run.json
#
# 할 일이 없으면 **아무것도 하지 않고 0 으로 끝난다.** 그래서 타이머를 10분마다 걸어도
# 헛돌지 않는다 — 대부분의 발화는 MinIO 객체를 하나 읽고 끝난다. BigQuery 는 실제로
# 실행할 때만 건드린다(Snapshots 조회는 쿼리당 최소 과금 10 MB다).
#
# **이 파일은 판단하지 않는다.** 잠금을 걸고 컨테이너를 부를 뿐이다. 유예·26시간 회수·
# BLOCKED·우편함 판정은 전부 컨테이너 안(pipeline/weekly/run.py)에 있다. 옆의
# run-similarity-batch.sh 가 호스트에서 sed 로 JSON 을 파싱하는 것은 mc 를 담은 minio
# 이미지에 python 이 없어서인데, 수집 이미지에는 있다.
#
# 절차 설명과 각 단계의 함정: README.md 의 "주간 수집" · pipeline/weekly/README.md
#
# 사용 (인자 없음):
#   cd ~/S15P21A506/deploy/prod/data && sh run-weekly-ingest.sh
#
# 진단할 때만 인자를 준다. 그대로 컨테이너에 넘어간다:
#   sh run-weekly-ingest.sh --dry-run
#   sh run-weekly-ingest.sh --only gcs_sync
#
# 종료 코드를 그대로 올린다. 스케줄러는 이 값만 보면 된다.
#   0 = 할 일이 없었거나 끝까지 갔다
#   1 = 단계가 실패했다 (다음 발화가 이어받는다. 연속 10회면 BLOCKED)

set -eu

cd "$(dirname "$0")"
REPO=$(cd ../../.. && pwd)

# 회차마다 같은 이름을 쓴다. **이름이 없으면 죽일 대상을 찾을 수 없다** — 아래 잠금 절을 볼 것.
#
# ⚠ **환경변수로 덮어쓸 수 있게 두지 않는다.** systemd/pickage-weekly.service 의
#   ExecStopPost 가 같은 이름을 지우는데, 그쪽은 유닛 파일에 박혀 있다. 여기만 바뀌면
#   타임아웃으로 죽였을 때 systemd 가 엉뚱한 이름을 지우고 **진짜 컨테이너는 살아남는다** —
#   두 겹 정리가 막으려던 상황이 정확히 그것이다. 이름을 바꾸려면 두 파일을 같이 고칠 것.
CONTAINER=pickage-weekly-run
# ⚠ 이 경로도 환경변수로 덮어쓸 수 없다. systemd 의 ExecStopPost 가 `flock -n` 으로 같은
#   파일을 보고 "지금 도는 회차가 있는가" 를 판단한다(systemd/pickage-weekly.service).
#   여기만 바뀌면 그쪽은 늘 빈 잠금을 잡아 **남의 컨테이너를 지운다.**
LOCK=/tmp/pickage-weekly.lock

[ -f .env ] || {
  echo "run-weekly-ingest.sh: .env 가 없습니다. .env.example 을 복사해 채우세요." >&2
  exit 1
}

# compose 가 못 잡아 주는 것. 자격증명은 환경변수가 아니라 **파일**로 읽는다
# (pipeline/minio/ingest_raw.py 의 client()). 없으면 수집기가 한참 뒤 S3 단계에서야 죽는다.
[ -f "$REPO/pipeline/minio/.env.data" ] || {
  echo "run-weekly-ingest.sh: pipeline/minio/.env.data 가 없습니다." >&2
  echo "  cp pipeline/minio/.env.data.example pipeline/minio/.env.data 후 값을 채우세요." >&2
  exit 1
}

# ── 잠금 — 두 겹이어야 한다 ───────────────────────────────────
#
# 한 회차가 23시간쯤 걸린다(상위 10만 중 스코프 54.6%는 벌크를 못 써서 개별 호출, IP 지속
# 한도 분당 약 40건). 10분 타이머가 그 위에 또 띄우면 같은 checkpoint.sqlite 를 두
# 프로세스가 쓰고 같은 IP 에서 npm 을 두 배로 두드린다.
#
# ⚠ **flock 만으로는 부족하다.** flock 은 호스트 프로세스만 막는데, 여기서 실제 작업은
#   컨테이너 안에서 돈다. systemd 가 TimeoutStartSec 으로 ExecStart 를 죽이면 그건
#   `docker compose run` **클라이언트**를 죽이는 것이지 컨테이너가 아니다. 잠금은
#   풀리고 컨테이너는 계속 돈다 — 다음 발화가 그 위에 하나를 더 띄운다.
#
#   그래서 이름을 고정하고 시작할 때 남은 것을 치운다. systemd 쪽에도 같은 정리를
#   ExecStopPost 로 걸어 둔다(systemd/pickage-weekly.service).
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "[weekly] 이미 돌고 있습니다 ($LOCK). 이번 발화는 건너뜁니다."
  exit 0
fi

# 잠금을 잡은 뒤에만 친다. 잠금을 못 잡았다는 것은 정상 실행이 돌고 있다는 뜻이라,
# 그때 치면 남의 회차를 죽인다.
if docker rm -f "$CONTAINER" >/dev/null 2>&1; then
  echo "[weekly] 지난 발화의 컨테이너가 남아 있어 치웠습니다 ($CONTAINER)."
fi

# exec 로 넘긴다 — 셸이 교체되지만 fd 9 는 물려받으므로 잠금은 끝까지 유지된다.
# `run` 은 서비스 이름을 직접 대면 profiles 를 알아서 켠다.
exec docker compose run --rm --name "$CONTAINER" ingest-weekly "$@"
