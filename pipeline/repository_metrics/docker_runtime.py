"""Run only the Spark transform inside a pinned, resource-bounded container."""
import json
from pathlib import Path
import subprocess
import uuid

from .policy import canonical_bytes

IMAGE = "apache/spark@sha256:936ff39fd63e2bb5ed064f0fbe1518198473f1cdbfa2f863d087a9a8e58116ba"
ROOT = Path(__file__).resolve().parents[2]


def transform_docker(inputs, output, *, threads=2, driver_memory="4g"):
    output = Path(output).resolve()
    attempt = output.parent
    mappings = [(Path(inputs["sources"][key]).resolve(), target) for key, target in (
        ("curated_outputs", "/input/curated"), ("versions_dir", "/input/versions"),
        ("projects_dir", "/input/projects"))]
    files = {}
    for table, paths in inputs["files"].items():
        files[table] = []
        for text in paths:
            path = Path(text).resolve()
            matches = [(source, target) for source, target in mappings if path.is_relative_to(source)]
            if len(matches) != 1:
                raise ValueError("Input path does not have one read-only container mapping")
            source, target = matches[0]
            files[table].append(target + "/" + path.relative_to(source).as_posix())
    invocation = {"snapshot": inputs["snapshot"], "snapshot_timestamp": inputs["snapshot_timestamp"],
                  "files": files, "counts": inputs["counts"], "threads": threads, "driver_memory": driver_memory}
    with (attempt / "spark-invocation.json").open("xb") as stream:
        stream.write(canonical_bytes(invocation))
    command = ["docker", "run", "--rm", "--name", "pickage-repo-metrics-" + uuid.uuid4().hex[:12],
               "--cpus", str(threads), "--memory", "6g", "--network", "none",
               "-e", "PYTHONPATH=/workspace", "-e", "PYTHONDONTWRITEBYTECODE=1",
               "-e", "SPARK_LOCAL_IP=127.0.0.1", "-e", "SPARK_LOCAL_HOSTNAME=localhost",
               "--mount", f"type=bind,source={ROOT},target=/workspace,readonly",
               "--mount", f"type=bind,source={attempt},target=/run", "--workdir", "/workspace"]
    for source, target in mappings:
        command += ["--mount", f"type=bind,source={source},target={target},readonly"]
    command += [IMAGE, "/opt/spark/bin/spark-submit", "--master", f"local[{threads}]",
                "--driver-memory", driver_memory, "/workspace/pipeline/repository_metrics/spark_job.py",
                "--input", "/run/spark-invocation.json", "--output", "/run/outputs", "--result", "/run/spark-result.json"]
    log_path = attempt / "spark-driver.log"
    print(f"Spark transform running in isolated container; log: {log_path}", flush=True)
    with log_path.open("xb") as log:
        completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"Spark container failed with exit {completed.returncode}; see {log_path}")
    result = json.loads((attempt / "spark-result.json").read_bytes())
    result["runtime"].update(engine="docker", image=IMAGE, cpus=threads, memory_limit="6g")
    return result
