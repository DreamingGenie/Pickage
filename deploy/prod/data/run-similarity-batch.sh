#!/bin/sh
#
# run-similarity-batch.sh — 유사도 배치 한 회차를 처음부터 끝까지 돌린다
#
# ⚠ **아직 뼈대다.** .env 의 AI_SRC_CORPUS · AI_SRC_MODEL · AI_DST_RESULT 가 비어 있으면
#    compose 가 어느 변수인지 말하고 거부한다. 채우는 것은 별도 티켓 —
#    지금 올려 둔 이유는 전체 실행 흐름을 한 파일에서 보이게 하는 것이다.
#
# 배치 한 회차는 잡 하나가 아니라 네 단계다.
#
#     [Spark 배치]  →  1 스테이징  →  2 배치  →  3 회수  →  [로더]
#      (이 파일 밖)      ai-stage    ai-similarity  ai-collect   (app 노드, 미구현)
#
# 세 단계 모두 compose 서비스다. `docker run` 으로 빼면 네트워크·볼륨 이름·env_file 을
# 손으로 다시 대야 하고, 그러다 자격증명을 빠뜨리면 mc 가 빈 값으로 붙는다.
#
# 잡이 s3:// 를 직접 읽고 쓰게 되면 **1·3 단계가 통째로 사라지고** 이 파일은
# 2단계 한 줄로 줄어든다. 그때 systemd timer 가 그 한 줄을 직접 불러도 된다.
#
# 절차 설명과 각 단계의 함정: README.md 의 "유사도 배치 돌리기"
#
# 사용:
#   cd ~/S15P21A506/deploy/prod/data && sh run-similarity-batch.sh
#
# set -e 라 어느 단계에서 죽어도 거기서 끝나고 종료 코드가 그대로 올라간다.
# 스케줄러를 붙일 때 이 값으로 성공·실패를 판단하면 된다 — 로그를 파싱할 이유가 없다.

set -eu

cd "$(dirname "$0")"

RUN_ID="${RUN_ID:-$(date +%Y%m%d)}"

echo "[1/3] 스테이징"
docker compose run --rm ai-stage

echo "[2/3] 배치  run=$RUN_ID"
# TODO(별도 티켓): --state 를 붙여 증분 재임베딩을 쓸지 정한다.
#   이전 회차의 text_hash_state.parquet 을 어디에 보관할지가 먼저다.
# TODO(별도 티켓): --batch-size·--query-block 을 이 노드 실측으로 고정한다.
#   메모리를 지배하는 둘이다 — OOM 이 나면 mem_limit 보다 이쪽을 먼저 줄인다.
docker compose run --rm ai-similarity \
  --package-text /work/in/package_text.parquet \
  --model-dir    /work/in/model \
  --out          "/work/out/$RUN_ID"

echo "[3/3] 회수"
docker compose run --rm ai-collect

echo "완료: run=$RUN_ID"
