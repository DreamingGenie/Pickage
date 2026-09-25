#!/bin/sh
# S15P21A506-475 3단계 — 유사도 배치 리허설 한 회 (로컬 Docker, 운영과 같은 조건).
#
# 운영 compose 의 ai-similarity 와 같게: mem_limit = memswap_limit(스왑 0), 4 CPU, uid 1000,
# 인자는 run-similarity-batch.sh 의 [5/6] 과 같은 세 개(+ 실험별 추가 인자).
# 입력은 전부 data/rehearsal475/ 의 SHA 검증된 사본. 운영에는 아무것도 쓰지 않는다.
#
# 사용 (저장소 루트, Git Bash):
#   sh docs/worklogs/S15P21A506-475/phase3_run.sh <run_id> <package_text> <dependents|none> <mem> [추가 인자...]
# 예:
#   sh .../phase3_run.sh R1 data/keywords/package_text/package_text_2026-09-08.parquet \
#      data/rehearsal475/inputs/dependents_candidate_pool.parquet 2g
set -eu
RUN=$1; TEXT=$2; DEPS=$3; MEM=$4; shift 4
IMAGE=pickage-ai-similarity:f416bde3-local
ROOT=$(pwd)
W=data/rehearsal475/runs/$RUN
E=docs/worklogs/S15P21A506-475/evidence/phase3/$RUN
rm -rf "$W"; mkdir -p "$W/in/model" "$W/out" "$E"
cp "$TEXT" "$W/in/package_text.parquet"
[ "$DEPS" = none ] || cp "$DEPS" "$W/in/package_dependents.parquet"
cp data/rehearsal475/inputs/model/* "$W/in/model/"
# 선택: STATE=<이전 실행의 text_hash_state.parquet> 를 주면 /work/in/state.parquet 로 둔다
# (관문만 바꾼 비교 실험에서 재임베딩을 건너뛰려고. 인자에 --state /work/in/state.parquet 를 함께 준다)
[ -n "${STATE:-}" ] && cp "$STATE" "$W/in/state.parquet"
( cd "$W/in" && sha256sum package_text.parquet model/model.onnx $( [ "$DEPS" = none ] || echo package_dependents.parquet ) ) > "$E/inputs.sha256"

NAME=rehearsal475-$RUN
docker rm -f "$NAME" >/dev/null 2>&1 || true
WIN=$(cd "$W" && pwd -W)
START=$(date +%s)
# 진입점만 sh 로 감싸 배치 종료 뒤 cgroup 의 memory.peak(최고 사용량, 바이트)를 찍는다.
# 배치 명령·인자는 이미지 ENTRYPOINT 와 같다. OOM 이면 python 만 죽고 sh 는 남아 값을 찍는다.
# --cpuset-cpus: --cpus 만 주면 컨테이너가 호스트 코어 16개를 그대로 보고 onnxruntime 이 그만큼
# 스레드·작업 메모리를 잡는다. EC2 #1 은 실제 4 vCPU 라 보이는 코어도 4개로 맞춘다.
MSYS_NO_PATHCONV=1 docker run -d --name "$NAME" --memory "$MEM" --memory-swap "$MEM" --cpus 4 --cpuset-cpus 0-3 \
  -v "$WIN:/work" --entrypoint sh "$IMAGE" -c \
  'python similarity_batch_pipeline.py "$@"; rc=$?; echo "CGROUP_MEMORY_PEAK=$(cat /sys/fs/cgroup/memory.peak 2>/dev/null)"; echo "BATCH_EXIT=$rc"; exit $rc' sh \
  --package-text /work/in/package_text.parquet --model-dir /work/in/model --out /work/out/result "$@" >/dev/null

echo "t_sec,mem_usage,mem_pct,cpu_pct" > "$E/mem.csv"
while [ "$(docker inspect -f '{{.State.Running}}' "$NAME")" = true ]; do
  S=$(docker stats --no-stream --format '{{.MemUsage}},{{.MemPerc}},{{.CPUPerc}}' "$NAME" 2>/dev/null || true)
  [ -n "$S" ] && echo "$(( $(date +%s) - START )),$S" >> "$E/mem.csv"
  sleep 1
done
END=$(date +%s)
docker logs "$NAME" > "$E/batch.log" 2>&1
docker inspect -f 'exit={{.State.ExitCode}} oom_killed={{.State.OOMKilled}} started={{.State.StartedAt}} finished={{.State.FinishedAt}}' "$NAME" > "$E/state.txt"
docker rm "$NAME" >/dev/null
echo "wall_sec=$(( END - START )) mem=$MEM args=$*" >> "$E/state.txt"
[ -f "$W/out/result/run_manifest.json" ] && cp "$W/out/result/run_manifest.json" "$E/"
ls -la "$W/out/result" > "$E/out-files.txt" 2>&1 || true
grep -E "CGROUP_MEMORY_PEAK|BATCH_EXIT" "$E/batch.log" >> "$E/state.txt" || true
cat "$E/state.txt"
