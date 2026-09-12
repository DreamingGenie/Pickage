#!/bin/sh
#
# run-similarity-batch.sh — 유사도 배치 한 회차. **사람이 인자를 주지 않는다.**
#
# ⚠ 아직 뼈대다. 아래 "지금 없는 것" 이 갖춰지기 전에는 해당 단계에서 멈춘다.
#
# 무엇을 돌릴지는 **두 포인터가 정한다.** 새 것이 게시되면 다음 발화에서 알아서 집는다.
#
#     코퍼스   $AI_CORPUS_PREFIX/_current.json   →  run_id
#     모델     MLflow  <이름>@<별칭>              →  s3:// 경로
#
# 둘 다 안 바뀌었으면 **아무것도 하지 않고 0 으로 끝난다.** 타이머를 촘촘히 걸어도
# 헛돌지 않는다 — 스케줄러가 "새 것이 있나" 를 판단할 필요가 없다.
#
#     [timer] → 확정 → 이미 했나? → 예: exit 0
#                                 → 아니오: 스테이징 → 배치 → 회수
#
# 해석(JSON 파싱)은 **여기서** 한다. mc 를 담은 minio 이미지에는 sed·grep·jq·python 이
# 없어서(확인함) 컨테이너 안에서는 못 한다. 컨테이너에는 확정된 경로만 넘긴다.
#
# 절차 설명과 각 단계의 함정: README.md 의 "유사도 배치 돌리기"
#
# 사용 (인자 없음):
#   cd ~/S15P21A506/deploy/prod/data && sh run-similarity-batch.sh
#
# 종료 코드를 그대로 올린다. 스케줄러는 이 값만 보면 된다.
#
# ── 지금 없는 것 (갖춰지는 순서대로) ──────────────────────────
#   1. package_text 가 MinIO 에 없다 + _current.json 도 없다        → 데이터 파트
#   2. MLflow 에 등록된 모델이 없다 (GPU 가 아직 등록 안 함)         → AI 파트
#   3. 로더가 없다 — 산출물이 PostgreSQL 까지 못 간다               → 미정
#   4. 스케줄러가 없다. 위가 서면 timer 가 이 파일을 부르기만 하면 된다

set -eu

cd "$(dirname "$0")"

[ -f .env ] || { echo "run-similarity-batch.sh: .env 가 없습니다." >&2; exit 1; }
# shellcheck disable=SC1091
. ./.env

: "${AI_CORPUS_PREFIX:?.env 에 채울 것 — 코퍼스 prefix (run 은 여기서 붙이지 않는다)}"
: "${AI_DST_RESULT:?.env 에 채울 것 — 산출물을 둘 MinIO 경로}"
: "${AI_MODEL_NAME:?.env 에 채울 것 — MLflow 등록 모델 이름}"
: "${AI_MODEL_ALIAS:?.env 에 채울 것 — 쓸 별칭 (보통 production)}"
: "${MLFLOW_TRACKING_URI:?.env 에 채울 것 — 예: http://127.0.0.1:5000}"

mc() { docker compose exec -T minio sh -c "mc alias set l http://127.0.0.1:9000 \"\$MINIO_ROOT_USER\" \"\$MINIO_ROOT_PASSWORD\" >/dev/null && $1"; }

# ── 1. 코퍼스 run 확정 ────────────────────────────────────────
#
# _current.json 이 "완료된 최신 실행" 을 가리킨다 (depsdev 와 같은 관례).
# 그 값을 읽어 **확정하고, 산출물 경로에 박아 기록한다** — 그래야 나중에
# "이 결과가 어느 코퍼스에서 나왔나" 를 경로만 보고 안다.
#
# glob 으로 최신을 추측하지 않는다. 실패한 실행까지 집을 수 있다.

echo "[1/5] 코퍼스 확정"
CURRENT_JSON=$(mc "mc cat l/$AI_CORPUS_PREFIX/_current.json")
# TODO(별도 티켓): _current.json 의 실제 키 이름에 맞출 것. depsdev 는 완료 실행 경로와
#   manifest 해시를 담는다 — 데이터 파트가 package-text 에 게시할 때 형식을 맞춘다.
CORPUS_RUN=$(printf '%s' "$CURRENT_JSON" | sed -n 's/.*"run_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
[ -n "$CORPUS_RUN" ] || { echo "  _current.json 에서 run_id 를 못 읽었습니다." >&2; exit 1; }
echo "  run_id=$CORPUS_RUN"

# ── 2. 모델 확정 ──────────────────────────────────────────────
#
# MLflow 에 "<이름>@<별칭> 이 뭐냐" 고 묻는다. 승격이 일어나면 여기 답이 바뀌고
# 다음 회차가 새 모델로 돈다 — .env 를 고칠 일이 없다.
#
# 배치 이미지에는 mlflow 클라이언트가 없다(requirements.txt). 그래서 **호스트가**
# REST 로 묻고, 나온 s3:// 경로를 mc 에게 넘긴다.

echo "[2/5] 모델 확정"
MV_JSON=$(curl -fsS "$MLFLOW_TRACKING_URI/api/2.0/mlflow/registered-models/alias?name=$AI_MODEL_NAME&alias=$AI_MODEL_ALIAS")
MODEL_SRC=$(printf '%s' "$MV_JSON" | sed -n 's/.*"source"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
MODEL_VER=$(printf '%s' "$MV_JSON" | sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
[ -n "$MODEL_SRC" ] || { echo "  @$AI_MODEL_ALIAS 의 source 를 못 읽었습니다." >&2; exit 1; }
MODEL_PATH=${MODEL_SRC#s3://}          # mc 는 버킷/경로 형태를 받는다
echo "  v$MODEL_VER  $MODEL_PATH"

# ── 3. 이미 했나 ──────────────────────────────────────────────
#
# 산출물 경로에 **모델 버전과 코퍼스 run 을 둘 다** 박는다. 둘 중 하나만 바뀌어도
# 다른 회차다. _SUCCESS 가 있으면 끝난 것이므로 조용히 넘어간다.

OUT_RUN="model=v$MODEL_VER/corpus=$CORPUS_RUN"
echo "[3/5] 중복 확인  $OUT_RUN"
if mc "mc stat l/$AI_DST_RESULT/$OUT_RUN/_SUCCESS" >/dev/null 2>&1; then
  echo "  이미 처리됨. 할 일 없음."
  exit 0
fi

# ── 4. 스테이징 → 배치 → 회수 ─────────────────────────────────
#
# 확정된 경로를 환경변수로 넘긴다. compose 파일에는 날짜도 버전도 없다.

echo "[4/5] 스테이징"
docker compose run --rm \
  -e AI_CORPUS_PATH="$AI_CORPUS_PREFIX/$CORPUS_RUN/data" \
  -e AI_MODEL_PATH="$MODEL_PATH" \
  ai-stage

echo "[5/5] 배치"
# TODO(별도 티켓): --state 로 증분 재임베딩을 쓸지. 이전 회차 산출물의
#   text_hash_state.parquet 을 스테이징에 같이 받아 오면 된다.
# TODO(별도 티켓): --batch-size·--query-block 을 이 노드 실측으로 고정.
docker compose run --rm ai-similarity \
  --package-text /work/in/package_text.parquet \
  --model-dir    /work/in/model \
  --out          "/work/out/$OUT_RUN"

echo "      회수"
docker compose run --rm -e AI_RESULT_PATH="$AI_DST_RESULT" ai-collect

echo "완료: $AI_DST_RESULT/$OUT_RUN"
