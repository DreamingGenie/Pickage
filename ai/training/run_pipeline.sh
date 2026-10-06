#!/usr/bin/env bash
#
# jupyter05(GPU, sudo 없음) 전용 재학습 파이프라인
#
# ── 왜 원본에서 바뀌었는지 ─────────────────────────────────────────────
# 원래 확정 설계(0904 문서 3.4절)는 GPU↔EC2 #1 연결에 Tailscale을 쓰는 걸
# 전제로 했지만, jupyter05는 여러 팀이 공유하는 서버라 sudo가 막혀있어
# Tailscale 데몬 설치가 불가능함(이전에 확인함). 그래서 이미 갖고 있는
# EC2 #1 SSH pem 키로 "SSH 로컬 포트 포워딩" 터널을 열어 그 안에서만
# MinIO(9000)·MLflow(5000)에 접근하는 방식으로 대체함.
#   - mc/ssh 모두 사용자 권한만으로 실행 가능 (sudo 불필요)
#   - EC2 #1 보안그룹은 22번(SSH)만 관리 IP에 열려있으면 되고,
#     9000/5000을 외부에 노출할 필요가 없음 (터널이 SSH 채널 안에서 감)
#
# 원본 대비 구조 변경:
#   1) EC2 raw 폴더 rsync 방식 → MinIO(curated/training_pairs)에서 pull
#   2) parquet→CSV 무조건 변환 → 실제 학습 스크립트 입력 포맷 확인 후 채우는 자리로 변경(TODO)
#   3) 학습 후 LoRA를 곧장 EC2에 rsync+symlink → LoRA merge → ONNX export → MLflow 등록 흐름으로 변경
#      (merge_and_export_onnx_v6.py, gpu_export_and_register.py를 그대로 호출하는 구조)
#
# ── 아직 확인 안 된 것들 (추측으로 채우지 않음, 실행 전 꼭 확인) ──────────
#   - MINIO_ACCESS_KEY / MINIO_SECRET_KEY / MINIO_TRAINING_PAIRS_PATH: 실제 값 필요
#   - EC2_HOST가 정말 EC2 #1(MinIO/MLflow가 있는 배치 노드)이 맞는지 (EC2 #2는 서빙 전용이라 여긴 없음)
#   - finetune_bge_small_lora.py가 --data로 CSV/JSONL/parquet 중 뭘 기대하는지
#   - EC2 #1에 MLflow(5000)가 실제로 배포됐는지 — 마지막 확인 시점엔 미배포였음.
#     안 됐으면 5단계(register_mlflow)는 실패함. 인프라 트랙에 먼저 확인할 것.
#
# 사용법:
#   ./run_pipeline.sh                # 전체 실행 (터널→pull→학습→export→MLflow 등록)
#   ./run_pipeline.sh --no-train     # 터널 열고 데이터만 받기 (학습은 직접)
#   ./run_pipeline.sh --register-only  # 이미 만든 ONNX만 MLflow에 등록
#
set -euo pipefail

# ─── 설정 ────────────────────────────────────────────────────────────────
EC2_HOST="${EC2_HOST:-ubuntu@<EC2-1-호스트를-채우세요>}"   # ⚠️ EC2 #1(MinIO·MLflow) 주소인지 재확인
SSH_KEY="${SSH_KEY:-$HOME/.ssh/lora_key.pem}"               # jupyter05에 업로드해둔 EC2 #1용 pem 키

MINIO_LOCAL_PORT="${MINIO_LOCAL_PORT:-9000}"
MLFLOW_LOCAL_PORT="${MLFLOW_LOCAL_PORT:-5000}"
MINIO_ENDPOINT="http://localhost:${MINIO_LOCAL_PORT}"      # 터널을 통해서만 접근 가능
MLFLOW_TRACKING_URI="http://localhost:${MLFLOW_LOCAL_PORT}" # 터널을 통해서만 접근 가능

MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY:?MinIO access key를 환경변수로 채워주세요}"
MINIO_SECRET_KEY="${MINIO_SECRET_KEY:?MinIO secret key를 환경변수로 채워주세요}"
MINIO_TRAINING_PAIRS_PATH="${MINIO_TRAINING_PAIRS_PATH:-curated/training_pairs}"  # ⚠️ 실제 버킷 경로 확인 필요

WORK="${WORK:-$HOME/work}"
DATA_DIR="$WORK/training_pairs"
LORA_DIR="${LORA_DIR:-$WORK/lora_out}"
ONNX_DIR="${ONNX_DIR:-$WORK/onnx_out}"

# ⚠️ 아래 세 CMD는 실제 스크립트 인자 스펙 확인 후 채우세요. 지금은 자리만 잡아둔 추정값입니다.
TRAIN_CMD="${TRAIN_CMD:-python3 finetune_bge_small_lora.py --data $DATA_DIR --output $LORA_DIR}"
EXPORT_CMD="${EXPORT_CMD:-python3 merge_and_export_onnx_v6.py --lora $LORA_DIR --output $ONNX_DIR}"
REGISTER_CMD="${REGISTER_CMD:-python3 gpu_export_and_register.py --onnx $ONNX_DIR}"

RUN_NAME="${RUN_NAME:-lora_$(date +%Y%m%d_%H%M)}"
TUNNEL_PID=""
# ─────────────────────────────────────────────────────────────────────────

SSH="ssh -i $SSH_KEY -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15"
say() { echo -e "\n[$(date +%H:%M:%S)] $*"; }

MODE="${1:-all}"

# ─── 0) SSH 터널 (Tailscale 대체) ─────────────────────────────────────────
open_tunnel() {
  say "0/5  EC2 #1로 SSH 터널 여는 중 (MinIO:$MINIO_LOCAL_PORT → 9000, MLflow:$MLFLOW_LOCAL_PORT → 5000)"
  $SSH -N \
       -L "${MINIO_LOCAL_PORT}:localhost:9000" \
       -L "${MLFLOW_LOCAL_PORT}:localhost:5000" \
       "$EC2_HOST" &
  TUNNEL_PID=$!
  sleep 3
  if ! kill -0 "$TUNNEL_PID" 2>/dev/null; then
    echo "!! SSH 터널이 바로 끊겼습니다. EC2_HOST/SSH_KEY, 또는 EC2 #1 보안그룹(22번 포트, 관리 IP 허용)을 확인하세요."
    exit 1
  fi
  echo "     터널 PID=$TUNNEL_PID"
}

close_tunnel() {
  if [ -n "$TUNNEL_PID" ] && kill -0 "$TUNNEL_PID" 2>/dev/null; then
    say "SSH 터널 종료 (PID=$TUNNEL_PID)"
    kill "$TUNNEL_PID" 2>/dev/null || true
  fi
}
trap close_tunnel EXIT

# ─── 1) MinIO에서 training_pairs 받기 ────────────────────────────────────
# mc가 로컬에 없다면 sudo 없이 사용자 폴더에 설치 가능:
#   curl https://dl.min.io/client/mc/release/linux-amd64/mc -o ~/bin/mc && chmod +x ~/bin/mc
pull_training_pairs() {
  say "1/5  MinIO에서 training_pairs 받는 중"
  mkdir -p "$DATA_DIR"
  mc alias set ec2minio "$MINIO_ENDPOINT" "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY" >/dev/null
  mc mirror "ec2minio/${MINIO_TRAINING_PAIRS_PATH}" "$DATA_DIR"
  local n
  n=$(find "$DATA_DIR" -type f | wc -l)
  echo "     파일 $n 개 수신"
  [ "$n" -gt 0 ] || { echo "!! 받은 파일이 없습니다. MINIO_TRAINING_PAIRS_PATH 경로를 확인하세요."; exit 1; }
}

# ─── 2) 학습 데이터 포맷 준비 ─────────────────────────────────────────────
# ⚠️ 원본 스크립트는 parquet→CSV로 무조건 변환했지만, finetune_bge_small_lora.py가
# 실제로 CSV를 받는지 JSONL(예: train_combined_v6.jsonl과 같은 포맷)을 받는지
# 확인되지 않아 임의로 변환 로직을 넣지 않았습니다. 확인 후 이 함수를 채우세요.
prepare_training_format() {
  say "2/5  학습 데이터 포맷 준비"
  echo "     TODO: finetune_bge_small_lora.py --data 인자의 실제 기대 포맷 확인 후 변환 로직 작성"
}

# ─── 3) 학습 ─────────────────────────────────────────────────────────────
train() {
  say "3/5  학습 시작: $TRAIN_CMD"
  mkdir -p "$LORA_DIR"
  eval "$TRAIN_CMD"
}

# ─── 4) LoRA merge + ONNX export ─────────────────────────────────────────
export_onnx() {
  say "4/5  LoRA merge + ONNX export: $EXPORT_CMD"
  mkdir -p "$ONNX_DIR"
  eval "$EXPORT_CMD"
}

# ─── 5) MLflow 등록 ───────────────────────────────────────────────────────
# ⚠️ 마지막 확인 시점 기준 EC2 #1의 MLflow(5000)는 미배포 상태였습니다.
# 인프라 트랙에 배포 완료 여부 먼저 확인 후 이 단계를 실행하세요.
register_mlflow() {
  say "5/5  MLflow 등록: $REGISTER_CMD"
  MLFLOW_TRACKING_URI="$MLFLOW_TRACKING_URI" RUN_NAME="$RUN_NAME" eval "$REGISTER_CMD"
}

# ─── 실행 ─────────────────────────────────────────────────────────────────
case "$MODE" in
  --register-only) open_tunnel; register_mlflow ;;
  --no-train)       open_tunnel; pull_training_pairs; prepare_training_format ;;
  all|"")           open_tunnel; pull_training_pairs; prepare_training_format; train; export_onnx; register_mlflow ;;
  *) echo "usage: $0 [--no-train|--register-only]"; exit 1 ;;
esac

say "파이프라인 완료 ($RUN_NAME)"
