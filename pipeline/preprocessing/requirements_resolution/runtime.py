"""Resource-limited Spark jobs with read-only input and code mounts."""
from __future__ import annotations
from pipeline.preprocessing.common.paths import REPO_ROOT

import json
from pathlib import Path
import subprocess
import uuid

from pipeline.preprocessing.requirements_resolution.policy import canonical_bytes

IMAGE = "apache/spark@sha256:936ff39fd63e2bb5ed064f0fbe1518198473f1cdbfa2f863d087a9a8e58116ba"
ROOT = REPO_ROOT


def run_stage(stage, inputs, policy, stage_dir, *, prepared_dir=None, bridge_dir=None,
              run_id, threads=2, driver_memory="4g", container_memory="6g", shuffle_partitions=32):
    if stage not in ("prepare", "finalize") or type(threads) is not int or not 1 <= threads <= 8:
        raise ValueError("Invalid Spark stage or CPU limit")
    if driver_memory != "4g" or container_memory != "6g" or not 1 <= shuffle_partitions <= 256:
        raise ValueError("Use the verified 4g driver/6g container memory limits and 1..256 partitions")
    stage_dir = Path(stage_dir).resolve()
    sources = [(Path(value).resolve(), "/input/" + key) for key, value in inputs["sources"].items()]
    for path, _ in sources:
        if stage_dir.is_relative_to(path) or path.is_relative_to(stage_dir):
            raise ValueError("Spark output overlaps input root")
    stage_dir.mkdir(parents=True, exist_ok=False)
    adapted = dict(inputs)
    adapted["files"] = {}
    for table, paths in inputs["files"].items():
        adapted["files"][table] = []
        for value in paths:
            path = Path(value).resolve()
            matches = [(root, target) for root, target in sources if path.is_relative_to(root)]
            if len(matches) != 1:
                raise ValueError("Spark input file lacks one unambiguous read-only mapping")
            root, target = matches[0]
            adapted["files"][table].append(target + "/" + path.relative_to(root).as_posix())
    invocation = {"stage": stage, "inputs": adapted, "policy": policy, "run_id": run_id,
                  "shuffle_partitions": shuffle_partitions}
    if stage == "finalize":
        if prepared_dir is None or bridge_dir is None:
            raise ValueError("Finalization requires prepared and bridge outputs")
        sources += [(Path(prepared_dir).resolve(), "/input/prepared"),
                    (Path(bridge_dir).resolve(), "/input/bridge")]
        invocation.update(prepared_dir="/input/prepared", bridge_dir="/input/bridge")
    (stage_dir / "invocation.json").write_bytes(canonical_bytes(invocation))
    command = ["docker", "run", "--rm", "--pull", "never", "--name", "pickage-requirements-" + uuid.uuid4().hex[:12],
               "--cpus", str(threads), "--memory", container_memory, "--network", "none",
               "-e", "PYTHONPATH=/workspace", "-e", "PYTHONDONTWRITEBYTECODE=1",
               "-e", "SPARK_LOCAL_IP=127.0.0.1", "-e", "SPARK_LOCAL_HOSTNAME=localhost",
               "--mount", f"type=bind,source={ROOT / 'pipeline' / 'preprocessing' / 'requirements_resolution'},target=/workspace/pipeline/preprocessing/requirements_resolution,readonly",
               "--mount", f"type=bind,source={ROOT / 'pipeline' / 'preprocessing' / 'snapshot'},target=/workspace/pipeline/preprocessing/snapshot,readonly",
               "--mount", f"type=bind,source={stage_dir},target=/run", "--workdir", "/workspace"]
    for source, target in sources:
        command += ["--mount", f"type=bind,source={source},target={target},readonly"]
    command += [IMAGE, "/opt/spark/bin/spark-submit", "--master", f"local[{threads}]",
                "--driver-memory", driver_memory, "/workspace/pipeline/preprocessing/requirements_resolution/spark_job.py"]
    log_path = stage_dir / "spark-driver.log"
    print(f"Spark {stage} starting; log: {log_path}", flush=True)
    with log_path.open("xb") as log:
        completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False)
    if completed.returncode:
        raise RuntimeError(f"Spark {stage} failed ({completed.returncode}); see {log_path}")
    result = json.loads((stage_dir / "result.json").read_bytes())
    result["runtime"] = {"engine": "docker", "image": IMAGE, "threads": threads,
                         "driver_memory": driver_memory, "container_memory": container_memory,
                         "shuffle_partitions": shuffle_partitions}
    return result
