"""Run engines sequentially with equal container caps and alternate order."""
import json
from pathlib import Path
import shutil
import subprocess
import time
import uuid

from pipeline.preprocessing.experiments.spark.compare import compare
from pipeline.preprocessing.experiments.spark.job import STAGES
from pipeline.preprocessing.experiments.spark.prepare import verify_inputs
from pipeline.preprocessing.common.paths import REPO_ROOT

ROOT = REPO_ROOT


def remap(value, source, target):
    if isinstance(value, dict):
        return {key: remap(item, source, target) for key, item in value.items()}
    if isinstance(value, list):
        return [remap(item, source, target) for item in value]
    if isinstance(value, str) and value.replace("\\", "/").startswith(source.rstrip("/") + "/"):
        return target.rstrip("/") + value.replace("\\", "/")[len(source.rstrip("/")):]
    return value


def benchmark(manifest_path, *, image="pickage-spark-experiment:local", repetitions=1,
              threads=2, memory="2GB", container_memory="6g", stages=STAGES, engines=("baseline", "spark")):
    if not 1 <= repetitions <= 20 or not 1 <= threads <= 16:
        raise ValueError("Invalid repetition or thread count")
    path = Path(manifest_path).resolve()
    root = path.parent
    manifest = json.loads(path.read_bytes())
    verify_inputs(manifest)
    image_id = subprocess.check_output(["docker", "image", "inspect", image, "--format", "{{.Id}}"], text=True).strip()
    batch = root / ("b-" + uuid.uuid4().hex[:8])
    batch.mkdir()
    # Freeze source too: an editor change between trials must not change one engine.
    code = batch / "code"
    shutil.copytree(ROOT / "pipeline", code / "pipeline",
                    ignore=shutil.ignore_patterns("node_modules", "__pycache__", "*.pyc"))
    container_batch = "/experiment/" + batch.name
    invocation = remap(manifest, root.as_posix(), "/experiment")
    (batch / "input.json").write_text(json.dumps(invocation), encoding="utf-8")
    summary = {"scope": "FIXED_STAGE_INPUT_COMPARISON", "image_id": image_id, "trials": [],
               "limits": {"cpus": threads, "container_memory": container_memory, "engine_memory": memory},
               "cache_policy": "fresh output/process; host and object-store caches uncontrolled",
               "performance_claim": "NO_PRODUCTION_SPEEDUP_CLAIM", "end_to_end_ingestion_measured": False}
    try:
        for repeat in range(repetitions):
            reports = {}
            order = list(engines) if repeat % 2 == 0 else list(reversed(engines))
            trial = {"order": order, "runs": {}}
            summary["trials"].append(trial)
            for engine in order:
                verify_inputs(manifest)
                name = f"r{repeat + 1}-{engine}"
                output = container_batch + "/" + name
                command = ["docker", "run", "--rm", "--name", "pickage-exp-" + uuid.uuid4().hex[:12],
                    "--cpus", str(threads), "--memory", container_memory, "--memory-swap", container_memory,
                    "--network", "none", "-e", "SPARK_LOCAL_IP=127.0.0.1",
                    "-e", "PYTHONPATH=/workspace:/opt/spark/python:/opt/spark/python/lib/py4j-0.10.9.7-src.zip",
                    "--mount", f"type=bind,source={code},target=/workspace,readonly",
                    "--mount", f"type=bind,source={root},target=/experiment", image_id]
                if engine == "spark":
                    command += ["/opt/spark/bin/spark-submit", "--master", f"local[{threads}]",
                                "--driver-memory", memory.lower().replace("gb", "g").replace("mb", "m"),
                                "/workspace/pipeline/preprocessing/experiments/spark/submit.py"]
                else:
                    command += ["python3", "-m", "pipeline.preprocessing.experiments.spark.job"]
                command += ["--manifest", container_batch + "/input.json", "--engine", engine,
                            "--output", output, "--threads", str(threads), "--memory", memory,
                            "--telemetry-dir", output + "-telemetry",
                            "--stages", ",".join(stages)]
                started = time.perf_counter()
                with (batch / (name + ".log")).open("w", encoding="utf-8") as log:
                    result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
                elapsed = time.perf_counter() - started
                trial["runs"][engine] = {"process_seconds": elapsed, "exit_code": result.returncode}
                if result.returncode:
                    raise RuntimeError("Experiment failed; inspect " + str(batch / (name + ".log")))
                report = json.loads((batch / name / "report.json").read_bytes())
                reports[engine] = remap(report, "/experiment", root.as_posix())
                trial["runs"][engine]["report"] = reports[engine]
            if set(reports) == {"baseline", "spark"}:
                checked = compare(reports["baseline"], reports["spark"], batch / ("compare-" + str(repeat + 1)))
                trial["comparison"] = checked
                trial["valid_result_comparison"] = checked["status"] == "EQUAL"
                trial["speed_ratio_baseline_over_spark"] = (
                    trial["runs"]["baseline"]["process_seconds"] / trial["runs"]["spark"]["process_seconds"]
                    if checked["status"] == "EQUAL" else None)
                if checked["status"] != "EQUAL":
                    raise ValueError("Outputs differ; performance comparison is invalid: " + str(batch))
        summary["status"] = "VERIFIED" if set(engines) == {"baseline", "spark"} else "COMPUTED_ONLY"
    except BaseException as error:
        summary.update(status="FAILED", error=str(error))
        raise
    finally:
        (batch / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return batch / "summary.json"
