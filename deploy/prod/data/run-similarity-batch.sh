#!/bin/sh
#
# run-similarity-batch.sh — 유사도 배치 한 회차. **사람이 인자를 주지 않는다.**
#
# ⚠ 아직 뼈대다. 아래 "지금 없는 것" 이 갖춰지기 전에는 해당 단계에서 멈춘다.
#
# 무엇을 돌릴지는 **두 포인터가 정한다.** 새 것이 게시되면 다음 발화에서 알아서 집는다.
#
#     코퍼스   $AI_CORPUS_PREFIX/_current.json   →  run_path(코퍼스 경로) + run_id(산출물 이름)
#     모델     MLflow  <이름>@<별칭>              →  s3:// 경로
#
# 둘 다 안 바뀌었으면 **아무것도 하지 않고 0 으로 끝난다.** 타이머를 촘촘히 걸어도
# 헛돌지 않는다 — 스케줄러가 "새 것이 있나" 를 판단할 필요가 없다.
#
#     [timer] → 확정 → 이미 했나? → 예: exit 0
#                                 → 아니오: 스테이징 → 배치 → 회수 → 포인터
#
# 회수까지 끝나면 **산출물 쪽에도 _current.json 을 찍는다** (S15P21A506-371).
# app 노드의 로더가 보는 것이 그 객체 하나다 — 버킷을 훑지 않는다.
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
#   1. MLflow 에 등록된 모델이 없다 (GPU 가 아직 등록 안 함)         → AI 파트
#   2. 스케줄러가 없다. 위가 서면 timer 가 이 파일을 부르기만 하면 된다
#
#   (로더는 붙었다 — app 노드의 similarity-loader 가 아래 [6/6] 이 찍는
#    _current.json 을 보고 스스로 게시한다. S15P21A506-371)
#
#   (package_text 와 _current.json 은 2026-09-14 게시됐다 — S15P21A506-348)

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

echo "[1/6] 코퍼스 확정"
CURRENT_JSON=$(mc "mc cat l/$AI_CORPUS_PREFIX/_current.json")
# 포인터는 값을 둘 싣는다 (S15P21A506-348). 쓰임이 달라서 나뉘어 있다.
#   run_path  prefix 상대 경로. 코퍼스를 찾는 데만 쓴다 (collected_date=…/run_id=…)
#   run_id    평평한 이름. 산출물 경로에 박는다 — 여기에 '/' 가 들어가면
#             /work/out 의 깊이가 달라져 ai-collect 의 _SUCCESS 게시가 어긋난다
CORPUS_RUN=$(printf '%s' "$CURRENT_JSON" | sed -n 's/.*"run_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
CORPUS_PATH=$(printf '%s' "$CURRENT_JSON" | sed -n 's/.*"run_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
[ -n "$CORPUS_RUN" ]  || { echo "  _current.json 에서 run_id 를 못 읽었습니다." >&2; exit 1; }
[ -n "$CORPUS_PATH" ] || { echo "  _current.json 에서 run_path 를 못 읽었습니다." >&2; exit 1; }
echo "  run_id=$CORPUS_RUN  run_path=$CORPUS_PATH"

# ── 2. 모델 확정 ──────────────────────────────────────────────
#
# MLflow 에 "<이름>@<별칭> 이 뭐냐" 고 묻는다. 승격이 일어나면 여기 답이 바뀌고
# 다음 회차가 새 모델로 돈다 — .env 를 고칠 일이 없다.
#
# 배치 이미지에는 mlflow 클라이언트가 없다(requirements.txt). 그래서 **호스트가**
# REST 로 묻고, 나온 s3:// 경로를 mc 에게 넘긴다.

echo "[2/6] 모델 확정"
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
echo "[3/6] 중복 확인  $OUT_RUN"
if mc "mc stat l/$AI_DST_RESULT/$OUT_RUN/_SUCCESS" >/dev/null 2>&1; then
  echo "  이미 처리됨. 할 일 없음."
  exit 0
fi

# ── 4. 스테이징 → 배치 → 회수 ─────────────────────────────────
#
# 확정된 경로를 환경변수로 넘긴다. compose 파일에는 날짜도 버전도 없다.

echo "[4/6] 스테이징"
docker compose run --rm \
  -e AI_CORPUS_PATH="$AI_CORPUS_PREFIX/$CORPUS_PATH/data" \
  -e AI_MODEL_PATH="$MODEL_PATH" \
  ai-stage

echo "[5/6] 배치"
# TODO(별도 티켓): --state 로 증분 재임베딩을 쓸지. 이전 회차 산출물의
#   text_hash_state.parquet 을 스테이징에 같이 받아 오면 된다.
# TODO(별도 티켓): --batch-size·--query-block 을 이 노드 실측으로 고정.
#
# --max-rank 100000: 다운로드 상위 10만 위 안의 패키지만 코퍼스로 쓴다 (S15P21A506-172).
#   package_text 의 rank 는 수집 시점 다운로드 내림차순 위치다. 이 인자가 없으면 컷이
#   꺼져 92만 행 전체가 후보가 된다 (옵션 기본값이 컷 없음이다).
#   결번이 있어 행수는 10만보다 적고, dependents·릴리스 경과·deprecated 조건과는
#   교집합이다 — 2026-09-08 parquet 실측으로 자격 통과가 29,098 → 17,833 이 된다.
docker compose run --rm ai-similarity \
  --package-text /work/in/package_text.parquet \
  --model-dir    /work/in/model \
  --out          "/work/out/$OUT_RUN" \
  --max-rank     100000

echo "      회수"
docker compose run --rm -e AI_RESULT_PATH="$AI_DST_RESULT" ai-collect

# ── 6. 완료 포인터 ────────────────────────────────────────────
#
# app 노드의 로더가 보는 것은 이 객체 하나다 (S15P21A506-371). 버킷을 훑어
# 최신을 추측하는 대신, "끝난 최신 회차는 이것" 을 여기서 못 박는다 —
# [1/6] 이 코퍼스 포인터를 읽는 것과 같은 관례다.
#
# ⚠ ai-collect 가 성공한 **뒤에만** 찍는다. 그 단계가 업로드와 _SUCCESS 를
#   모두 마친 뒤에야 돌아오므로, 포인터가 있다는 것은 회차가 온전하다는 뜻이다.
#   set -e 라 회수가 실패하면 여기까지 오지 않는다.
#
# 파싱은 [1/6] 과 같은 이유로 **호스트에서** 한다 — minio 이미지에는
# sed·grep·jq·python 이 없다.

echo "[6/6] 포인터"
# 첫 회차에는 포인터가 없다. mc cat 이 실패해도 멈추지 않게 받아 둔다.
PREV_JSON=$(mc "mc cat l/$AI_DST_RESULT/_current.json" 2>/dev/null || true)
PREV_RUN=$(printf '%s' "$PREV_JSON" \
           | sed -n 's/.*"run_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
# 뒤로 되돌리지 않는다. 모델 버전은 숫자로, 코퍼스는 문자열(수집일이 들어가
# 사전식 비교가 곧 시간 순서 — S15P21A506-348 관례)로 각각 비교한다.
# 두 값을 이어붙인 문자열 전체를 사전식으로만 비교하면 모델 버전이 v9→v10
# 처럼 자릿수가 늘 때 오판된다 (S15P21A506-376).
if [ -n "$PREV_RUN" ] && ! sh lib/pointer-is-newer.sh "$PREV_RUN" "$OUT_RUN"; then
  echo "      포인터가 더 최신이라 그대로 둡니다: $PREV_RUN"
else
  echo "      manifest_sha256 계산"
  # watch.py 의 needs_publish() 가 이 값으로 재발행 여부를 가른다. load.py 가
  # 나중에 같은 파일을 받아 계산하는 값과 바이트 단위로 같아야 하므로,
  # ingest-weekly 의 boto3 클라이언트로 원본 바이트를 그대로 받아 해시한다
  # (S15P21A506-376). mc cat 을 셸 변수에 담아 해시하면 후행 개행이 잘려나갈
  # 수 있어 load.py 가 나중에 계산하는 값과 어긋날 위험이 있다 — 그래서 쓰지 않는다.
  MANIFEST_SHA256=$(docker compose run --rm --entrypoint python ingest-weekly \
    -m pipeline.minio.manifest_hash \
    --bucket "$AI_DST_RESULT" --key "$OUT_RUN/run_manifest.json" | tail -n1)
  [ -n "$MANIFEST_SHA256" ] || { echo "  manifest_sha256 을 계산하지 못했습니다." >&2; exit 1; }

  POINTER=$(printf '{"run_path":"%s","run_id":"%s","published_at":"%s","manifest_sha256":"%s"}' \
            "$OUT_RUN" "$CORPUS_RUN" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$MANIFEST_SHA256")
  mc "printf '%s' '$POINTER' | mc pipe l/$AI_DST_RESULT/_current.json"
  echo "      $OUT_RUN  sha256=$MANIFEST_SHA256"
fi

echo "완료: $AI_DST_RESULT/$OUT_RUN"
