"""Run only the failed repository stage against its pinned reference inputs."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time


INPUT_MANIFEST = Path(
    "/experiment/reference/w/ref/repository/ref/attempts/"
    "3d37fdbdba9f48c49fdbe0ccbef18662/input-manifest.json"
)
INPUT_MANIFEST_SHA256 = "fb7e451424a6b49297ffd40ffe730b70fed5bf891bb911d5a9153e6e8cf8ed48"
EXPECTED_REPOSITORY_CODE_SHA256 = "fe7382112c5278249bf9f7d8f26304b208ae89c8e898afdc635fdc36d24bf7ef"
PREVIOUS_CODE = Path("/previous-code")
CURRENT_CODE = Path("/workspace")
CONTROL = Path("/control")
OUTPUT = Path("/experiment/repository-retry")
TELEMETRY = Path("/experiment/retry-telemetry")
FIXED_MANIFEST = Path("/experiment/retry-input-manifest.json")
HEAP = "4g"


def fresh_control(root: Path, *, now: float | None = None) -> bool:
    try:
        state = json.loads((root / "supervisor-heartbeat.json").read_text())
        age = (time.time() if now is None else now) - float(state["time"])
        return 0 <= age < 25
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return False


def wait_for_start(control: Path, *, timeout: int = 90, interval: float = 1) -> None:
    deadline = time.monotonic() + timeout
    while not (control / "start.signal").exists():
        if time.monotonic() >= deadline:
            raise RuntimeError("Host monitors did not become ready")
        time.sleep(interval)
    if not fresh_control(control):
        raise RuntimeError("Host supervisor is not fresh")


def repository_code_sha256(root: Path) -> str:
    """Match repository_metrics.build.code_sha256 for an arbitrary checkout."""
    root = root.resolve()
    paths = list((root / "pipeline/preprocessing/repository_metrics").glob("*.py"))
    paths += [root / p for p in (
        "pipeline/preprocessing/curated/repository.py", "pipeline/preprocessing/curated/storage.py",
        "pipeline/preprocessing/curated/build.py", "pipeline/minio/ingest_raw.py",
        "pipeline/postgresql/input.py", "pipeline/preprocessing/common/curated_input.py", "pipeline/preprocessing/snapshot/policy.py",
        "pipeline/preprocessing/snapshot/projects.py", "pipeline/preprocessing/snapshot/input.py", "pipeline/preprocessing/snapshot/build.py")]
    checksum = hashlib.sha256()
    for path in sorted(p for p in paths if not p.name.startswith("test_")):
        checksum.update(path.relative_to(root).as_posix().encode() + b"\0")
        checksum.update(path.read_bytes() + b"\0")
    return checksum.hexdigest()


def build_stage_manifest(input_manifest: dict, *, manifest_sha256: str,
                         previous_code_sha256: str, current_code_sha256: str) -> dict:
    if previous_code_sha256 != current_code_sha256:
        raise ValueError("Repository implementation/runtime source contract differs from reference")
    if not isinstance(input_manifest, dict) or input_manifest.get("format_version") != 1:
        raise ValueError("Invalid pinned repository input manifest")
    records = input_manifest.get("file_records")
    if not isinstance(records, list) or not records:
        raise ValueError("Pinned repository input manifest has no file records")
    inventory = []
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            raise ValueError("Malformed pinned input file record")
        inventory.append({"path": record["path"], "bytes": record["bytes"],
                          "sha256": record["sha256"]})
    return {
        "format_version": 1,
        "source_request": {"scope": "REPOSITORY_STAGE_RETRY_ONLY",
                            "input_manifest_sha256": manifest_sha256,
                            "repository_code_sha256": current_code_sha256},
        "input_identity": hashlib.sha256(json.dumps(
            {"manifest_sha256": manifest_sha256, "files": sorted(
                (r["sha256"], r["bytes"]) for r in inventory)},
            sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "input_files": inventory,
        "stages": {"repository": input_manifest},
    }


def verify_pinned_manifest(path: Path, expected_sha256: str) -> tuple[dict, str]:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_sha256:
        raise ValueError("Pinned repository input manifest SHA256 mismatch")
    return json.loads(raw), digest


def verify_heap(runtime_max: int, requested_bytes: int) -> None:
    if runtime_max < requested_bytes:
        raise RuntimeError(f"JVM maxMemory below requested heap: {runtime_max} < {requested_bytes}")


def main() -> int:
    wait_for_start(CONTROL)

    def watch_supervisor():
        while True:
            if not fresh_control(CONTROL):
                print("REPOSITORY_RETRY_ABORT: supervisor heartbeat unavailable", flush=True)
                os._exit(70)
            time.sleep(3)

    threading.Thread(target=watch_supervisor, daemon=True).start()

    _, manifest_sha = verify_pinned_manifest(INPUT_MANIFEST, INPUT_MANIFEST_SHA256)
    old_hash = repository_code_sha256(PREVIOUS_CODE)
    current_hash = repository_code_sha256(CURRENT_CODE)
    if old_hash != EXPECTED_REPOSITORY_CODE_SHA256 or current_hash != EXPECTED_REPOSITORY_CODE_SHA256:
        raise ValueError("Repository implementation/runtime source contract differs from reference")
    original = json.loads(INPUT_MANIFEST.read_text())
    from pipeline.preprocessing.repository_metrics.input import reverify_inputs
    reverify_inputs(original)

    if OUTPUT.exists() or TELEMETRY.exists() or FIXED_MANIFEST.exists():
        raise FileExistsError("Repository retry output path already exists")
    fixed = build_stage_manifest(original, manifest_sha256=manifest_sha,
                                 previous_code_sha256=old_hash,
                                 current_code_sha256=current_hash)
    with FIXED_MANIFEST.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(fixed, sort_keys=True, indent=2) + "\n")
    requested = 4 * 1024**3
    # A separate JVM probe verifies the setting without leaving a Py4J gateway
    # alive that could prevent the measured job from receiving event-log flags.
    probe_code = (
        "import json; from pipeline.preprocessing.repository_metrics.runtime import create_spark; "
        "s=create_spark('/experiment/heap-probe',threads=2,driver_memory='4g',shuffle_partitions=16); "
        "print('HEAP_PROBE_JSON:'+json.dumps({'max_memory':int(s.sparkContext._jvm.java.lang.Runtime.getRuntime().maxMemory())})); "
        "s.stop()"
    )
    probe_env = dict(os.environ)
    probe_env["PYSPARK_SUBMIT_ARGS"] = "--driver-memory 4g pyspark-shell"
    probe = subprocess.run([sys.executable, "-c", probe_code], cwd=CURRENT_CODE,
                           env=probe_env, capture_output=True, text=True, timeout=180)
    if probe.returncode != 0:
        raise RuntimeError("JVM heap probe failed: " + probe.stderr[-2000:])
    marker = next((line.removeprefix("HEAP_PROBE_JSON:") for line in probe.stdout.splitlines()
                   if line.startswith("HEAP_PROBE_JSON:")), None)
    if marker is None:
        raise RuntimeError("JVM heap probe did not report maxMemory")
    max_memory = int(json.loads(marker)["max_memory"])
    verify_heap(max_memory, requested)

    flags = ["--driver-memory", HEAP, "--conf", "spark.eventLog.enabled=true",
             "--conf", "spark.eventLog.compress=false", "--conf",
             "spark.eventLog.rolling.enabled=false", "--conf",
             "spark.eventLog.dir=file:///experiment/retry-telemetry/events"]
    os.environ["PYSPARK_SUBMIT_ARGS"] = " ".join(flags) + " pyspark-shell"

    print(json.dumps({"event": "REPOSITORY_RETRY_HEAP_CONFIRMED", "runtime_max_memory": max_memory,
                      "requested_minimum": requested, "input_manifest_sha256": manifest_sha,
                      "repository_code_sha256": current_hash}, sort_keys=True), flush=True)
    from pipeline.preprocessing.experiments.spark.job import main as run_job
    return run_job(["--manifest", str(FIXED_MANIFEST), "--engine", "baseline",
                    "--stages", "repository", "--threads", "2", "--memory", "4GB",
                    "--output", str(OUTPUT), "--telemetry-dir", str(TELEMETRY)])


if __name__ == "__main__":
    raise SystemExit(main())
