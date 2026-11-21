#!/bin/sh
#
# run-pipeline-tests.sh — pipeline/ 의 빠른 층 파이썬 시험을 한 번에 돌린다.
#
# 사용: sh scripts/run-pipeline-tests.sh            (python 이 PATH 에 있을 때)
#       PYTHON=.venv-bq/Scripts/python.exe sh scripts/run-pipeline-tests.sh
#
# 의존성: pip install -r pipeline/collectors/requirements.txt -r pipeline/minio/requirements.txt
#
# **외부 서비스를 부르지 않는 시험만 넣는다.** BigQuery·GCS·MinIO·PostgreSQL 이 필요한 시험은
# 각 폴더 README 의 절차로 따로 돌린다(예: WEEKLY_MINIO_TEST=1 인 pipeline/weekly 의 느린 층은
# 여기서 skip 된다).
#
# 폴더마다 따로 discover 하는 이유: pipeline/ 에는 __init__.py 가 없고 폴더마다 collect.py·
# to_parquet.py 처럼 같은 이름의 모듈이 있어, 한 프로세스에서 전부 import 하면 먼저 잡힌
# 모듈이 뒤의 시험에 섞인다(README "데이터 파이프라인" 절이 pytest pipeline 을 쓰지 않는 이유).
#
# 여기 없는 폴더(pipeline/downloads · preprocessing · postgresql · monitor 등)는 PySpark·
# PostgreSQL·상대 import 전제가 달라 이 스크립트의 범위가 아니다.

set -eu

cd "$(dirname "$0")/.."
PY="${PYTHON:-python}"
export PYTHONIOENCODING=utf-8

# 시험 파일이 없는 폴더는 건너뛴다. Python 3.12 의 unittest 는 시험 0개면 종료 코드 5 다.
FLAT_DIRS="
pipeline/collectors/bigquery
pipeline/collectors/registry
pipeline/collectors/keywords
pipeline/duckdb
pipeline/dependent_transitions
pipeline/migration_pairs
pipeline/removal_reasons
"

failed=""
run() {
  echo "── $1"
  shift
  if ! "$@"; then
    failed="$failed\n  $*"
  fi
}

for d in $FLAT_DIRS; do
  if ls "$d"/test_*.py >/dev/null 2>&1; then
    run "$d" "$PY" -m unittest discover -s "$d" -p "test_*.py"
  else
    echo "── $d (시험 파일 없음, 건너뜀)"
  fi
done

# 패키지 경로로 import 하는 폴더. 저장소 루트를 top-level 로 준다.
run "pipeline/weekly" "$PY" -m unittest discover -s pipeline/weekly -t . -p "test_*.py"

# pipeline/minio 는 한 파일만 상대 import 를 쓴다. 나머지는 폴더를 sys.path 에 올려 읽는다.
run "pipeline/minio (flat)" "$PY" -m unittest discover -s pipeline/minio -p "test_[!m]*.py"
run "pipeline/minio (package)" "$PY" -m unittest pipeline.minio.test_manifest_hash

if [ -n "$failed" ]; then
  printf "\n실패한 묶음:$failed\n" >&2
  exit 1
fi
echo "모든 묶음 통과"
