#!/bin/sh
set -eu

mc alias set local "${MINIO_ENDPOINT:-http://minio:9000}" \
  "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null

mc mb --ignore-existing \
  local/pickage-raw \
  local/pickage-curated \
  local/pickage-vectors \
  local/pickage-mlflow-artifacts \
  local/pickage-quarantine
