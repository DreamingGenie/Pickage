"""Prepare an offline Spark standalone-cluster experiment bundle.

This module only verifies and copies local files.  The generated launcher is
the explicit operator step that uploads the frozen inputs and starts Spark.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import uuid

from pipeline.preprocessing.common.paths import REPO_ROOT

ROOT = REPO_ROOT
REMOTE_ROOT = "s3a://pickage-curated/experiments"


def verify_inputs(manifest):
    """Load the preparation verifier lazily so bundle inspection stays offline."""
    from pipeline.preprocessing.experiments.spark.prepare import verify_inputs as prepare_verify_inputs
    return prepare_verify_inputs(manifest)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _remote_remap(value, source_root: str, remote_root: str):
    if isinstance(value, dict):
        return {key: _remote_remap(item, source_root, remote_root) for key, item in value.items()}
    if isinstance(value, list):
        return [_remote_remap(item, source_root, remote_root) for item in value]
    if isinstance(value, str):
        normalized = value.replace("\\", "/")
        prefix = source_root.rstrip("/") + "/"
        if normalized.startswith(prefix):
            relative = normalized[len(prefix):]
            return remote_root.rstrip("/") + "/inputs/" + relative
    return value


def _safe_relative(path: Path, root: Path) -> str:
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise ValueError("Frozen input is outside manifest root: " + str(path)) from error
    if not relative.parts or any(part in ("", ".", "..") for part in relative.parts):
        raise ValueError("Invalid frozen input relative path")
    return PurePosixPath(*relative.parts).as_posix()


def _launcher(bundle_name: str, manifest_name: str) -> str:
    return f'''#!/usr/bin/env bash
set -euo pipefail

: "${{SPARK_MASTER:?Set SPARK_MASTER, for example spark://172.26.8.249:7077}}"
: "${{NODE_RUNTIME_ROOT:?Set NODE_RUNTIME_ROOT to the identical Node runtime mount on every worker}}"
: "${{MINIO_ALIAS:?Set MINIO_ALIAS to an mc alias configured for MinIO}}"
: "${{PYTHONPATH:?Set PYTHONPATH to the read-only code mount visible on driver and workers}}"

BUNDLE_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
CODE_ROOT="${{CODE_ROOT:-$BUNDLE_DIR/code}}"
SPARK_SUBMIT="${{SPARK_SUBMIT:-/opt/spark/bin/spark-submit}}"
REMOTE_PREFIX="s3a://pickage-curated/experiments/{bundle_name}"
MC_TARGET="${{MINIO_ALIAS}}/pickage-curated/experiments/{bundle_name}"
DRIVER_MEMORY="${{DRIVER_MEMORY:-1g}}"
EXECUTOR_MEMORY="${{EXECUTOR_MEMORY:-2g}}"
EXECUTOR_CORES="${{EXECUTOR_CORES:-1}}"
TOTAL_EXECUTOR_CORES="${{TOTAL_EXECUTOR_CORES:-2}}"
TELEMETRY_DIR="${{TELEMETRY_DIR:-$BUNDLE_DIR/telemetry}}"
PYSPARK_PYTHON="${{PYSPARK_PYTHON:-python3}}"

test -d "$CODE_ROOT"
test -x "$NODE_RUNTIME_ROOT/bin/node"
test -f "$BUNDLE_DIR/{manifest_name}"

# A retry must use a newly prepared bundle. Never overwrite an existing run.
if mc stat "$MC_TARGET/{manifest_name}" >/dev/null 2>&1 || mc stat "$MC_TARGET/output/report.json" >/dev/null 2>&1; then
  echo "Refusing existing experiment manifest or output report: $MC_TARGET" >&2
  exit 1
fi

# Uploading inputs is deliberately explicit and happens before Spark starts.
mc cp --recursive "$BUNDLE_DIR/inputs/" "$MC_TARGET/inputs/"
mc cp "$BUNDLE_DIR/{manifest_name}" "$MC_TARGET/{manifest_name}"

export PYTHONPATH="$CODE_ROOT:$PYTHONPATH"
export EXPERIMENT_NODE="$NODE_RUNTIME_ROOT/bin/node"
export EXPERIMENT_NPM_MODULES="${{EXPERIMENT_NPM_MODULES:-$NODE_RUNTIME_ROOT/lib/node_modules/npm/node_modules}}"
export EXPERIMENT_NODE_WORKER="$CODE_ROOT/pipeline/preprocessing/version_dependents/historical_semver_worker.cjs"
export EXPERIMENT_CLASSIFIER_WORKER="$CODE_ROOT/pipeline/preprocessing/requirements_resolution/semver_worker.cjs"
export PYSPARK_PYTHON

"$SPARK_SUBMIT" --master "$SPARK_MASTER" --deploy-mode client \
  --driver-memory "$DRIVER_MEMORY" --executor-memory "$EXECUTOR_MEMORY" \
  --executor-cores "$EXECUTOR_CORES" --total-executor-cores "$TOTAL_EXECUTOR_CORES" \
  --conf "spark.executorEnv.PYTHONPATH=$PYTHONPATH" \
  --conf "spark.executorEnv.PYSPARK_PYTHON=$PYSPARK_PYTHON" \
  --conf spark.hadoop.mapreduce.fileoutputcommitter.marksuccessfuljobs=false \
  "$CODE_ROOT/pipeline/preprocessing/experiments/spark/submit.py" \
  --manifest "$REMOTE_PREFIX/{manifest_name}" --engine spark \
  --output "$REMOTE_PREFIX/output" --telemetry-dir "$TELEMETRY_DIR" --stages package_version,downloads,repository,package_snapshot,dependents

# The Spark job suppresses Hadoop _SUCCESS markers. Publication remains an
# operator responsibility; this preparation launcher never writes one.
'''


def build_cluster_bundle(manifest_path, output_dir):
    """Create and return a local, offline cluster preparation bundle.

    The source preparation manifest is verified before any copy.  The returned
    bundle contains all unique frozen inputs under their manifest-root-relative
    paths, a complete Python/Node source tree, and a remote-path manifest.
    """
    manifest_path = Path(manifest_path).resolve()
    output_dir = Path(output_dir).resolve()
    source_manifest = json.loads(manifest_path.read_bytes())
    verify_inputs(source_manifest)
    if not isinstance(source_manifest.get("input_files"), list):
        raise ValueError("Frozen experiment manifest input_files must be a list")

    bundle_name = "cluster-" + uuid.uuid4().hex
    bundle = output_dir / bundle_name
    bundle.mkdir(parents=True, exist_ok=False)
    inputs_dir = bundle / "inputs"
    code_dir = bundle / "code"
    inputs_dir.mkdir()
    code_dir.mkdir()

    copied = []
    seen = set()
    root_text = manifest_path.parent.as_posix()
    remote_prefix = f"{REMOTE_ROOT}/{bundle_name}"
    for record in source_manifest["input_files"]:
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            raise ValueError("Frozen experiment input record has no path")
        source = Path(record["path"]).resolve()
        if source in seen:
            continue
        seen.add(source)
        relative = _safe_relative(source, manifest_path.parent)
        target = inputs_dir.joinpath(*PurePosixPath(relative).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        actual_hash = _sha256(target)
        expected_hash = record.get("sha256")
        if actual_hash != expected_hash or target.stat().st_size != record.get("bytes"):
            raise ValueError("Frozen input changed during bundle copy: " + relative)
        copied.append({"path": f"{remote_prefix}/inputs/{relative}", "relative_path": relative,
                       "bytes": target.stat().st_size, "sha256": actual_hash})

    for source in sorted((ROOT / "pipeline").rglob("*")):
        if not source.is_file() or source.suffix not in (".py", ".cjs"):
            continue
        if any(part in {".git", "node_modules", "__pycache__"} for part in source.parts):
            continue
        relative = source.relative_to(ROOT)
        target = code_dir.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    remote_manifest = _remote_remap(source_manifest, root_text, remote_prefix)
    remote_manifest["input_files"] = copied
    remote_manifest["bundle"] = {"bundle_id": bundle_name, "remote_prefix": remote_prefix,
                                  "production_writes": False, "_SUCCESS_published": False}
    manifest_name = "cluster_manifest.json"
    (bundle / manifest_name).write_text(json.dumps(remote_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    launcher = bundle / "launch_cluster.sh"
    launcher.write_text(_launcher(bundle_name, manifest_name), encoding="utf-8", newline="\n")
    try:
        launcher.chmod(0o755)
    except OSError:
        pass
    (bundle / "README.md").write_text(
        "# 오프라인 Spark 실험 번들\n\n"
        "`launch_cluster.sh` 실행 전에 `MINIO_ALIAS`, `SPARK_MASTER`, `NODE_RUNTIME_ROOT`, "
        "그리고 드라이버·모든 executor에서 보이는 읽기 전용 `PYTHONPATH`를 설정한다.\n\n"
        "자원 기본값은 `DRIVER_MEMORY=1g`, `EXECUTOR_MEMORY=2g`, `EXECUTOR_CORES=1`, "
        "`TOTAL_EXECUTOR_CORES=2`이며 실행 전에 환경 변수로 조정할 수 있다. 모든 노드의 "
        "Node 런타임에는 semver와 npm-package-arg가 있어야 하고 Python 버전도 같아야 한다. "
        "Spark 3.5.3 standalone client 실행을 전제로 한다. 입력 업로드는 운영자가 명시적으로 "
        "수행하는 단계이며 네트워크·서버 호출은 이 생성 함수에서 하지 않는다. 이 번들의 서버 "
        "런타임 동작은 아직 검증되지 않았다. launcher는 `_SUCCESS`를 게시하지 않는다.\n\n"
        "재시도는 같은 출력 prefix를 덮어쓰지 않도록 새 번들을 생성한다. `.cjs` worker를 실행하므로 "
        "코드는 zip으로 가정하지 않고 소스 디렉터리로 공유한다.\n",
        encoding="utf-8",
    )
    return bundle


__all__ = ["build_cluster_bundle"]
