"""Guarded driver entry for the real two-EC2 Spark comparison run.

The initial barrier action proves that tasks execute on both expected workers.
The Spark job then reuses that same SparkContext. A companion report separates
barrier/startup evidence from event-log evidence for the selected data stages.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import threading
import time


EXPECTED_WORKERS = frozenset({"172.26.8.249", "172.26.6.235"})
STAGES = ("package_version", "downloads", "repository", "package_snapshot", "dependents")
MAX_HEARTBEAT_AGE_SECONDS = 25


def fresh_control(root: Path, *, now: float | None = None) -> bool:
    try:
        state = json.loads((root / "supervisor-heartbeat.json").read_text(encoding="utf-8"))
        age = (time.time() if now is None else now) - float(state["time"])
        return 0 <= age < MAX_HEARTBEAT_AGE_SECONDS
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


def validate_paths(run_id: str, manifest: str, output: str, telemetry: Path,
                   events: Path, summary: Path) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", run_id):
        raise ValueError("Invalid experiment run id")
    for label, location in (("manifest", manifest), ("output", output)):
        if not location.startswith("s3a://pickage-curated/experiments/"):
            raise ValueError(f"{label} must stay under the experiment bucket prefix")
        if "?" in location or "#" in location:
            raise ValueError(f"{label} must not include a query or fragment")
        path = location.removeprefix("s3a://pickage-curated/").split("?", 1)[0].split("#", 1)[0]
        parts = path.split("/")
        if any(part in ("", ".", "..") for part in parts):
            raise ValueError(f"Unsafe {label} path")
    output_parts = output.removeprefix("s3a://pickage-curated/").split("/")
    if output_parts[:2] != ["experiments", run_id] or len(output_parts) < 3:
        raise ValueError("output must be below this run's unique experiments/<run-id> prefix")
    root = Path("/experiment").resolve()
    for label, location in (("telemetry", telemetry), ("events", events), ("summary", summary)):
        resolved = location.resolve()
        try:
            relative = resolved.relative_to(root)
        except ValueError as error:
            raise ValueError(f"{label} path must be inside /experiment") from error
        if not relative.parts or run_id not in relative.parts:
            raise ValueError(f"{label} path must include this run id")
    if telemetry == events or telemetry in events.parents or events in telemetry.parents:
        raise ValueError("telemetry and Spark event logs must use separate directories")


def validate_barrier_hosts(rows: list[dict], expected=EXPECTED_WORKERS) -> dict:
    hosts = [row.get("private_ip") for row in rows]
    actual = set(hosts)
    if len(rows) != len(expected) or len(hosts) != len(actual) or actual != set(expected):
        raise RuntimeError(f"Two-EC2 barrier did not execute once on each expected worker: {rows}")
    return {"expected_workers": sorted(expected), "observed_workers": sorted(actual),
            "partition_count": len(rows), "verified": True}


def summarize_data_stage_hosts(event_logs: list[dict], selected_stages: list[str]) -> dict:
    per_stage = {name: {"task_count": 0, "hosts": set()} for name in selected_stages}
    completed_logs = 0
    malformed = 0
    for log in event_logs:
        completed_logs += int(bool(log.get("completed")))
        malformed += int(log.get("malformed_line_count", 0) or 0)
        for stage in log.get("stages", []):
            name = stage.get("job_group_id") or stage.get("stage_name")
            if name not in per_stage:
                continue
            row = per_stage[name]
            row["task_count"] += int(stage.get("task_count", 0) or 0)
            # The parser reports executor IDs at stage granularity and host/IP
            # mappings application-wide. Attribute each stage's executors.
            executor_ids = set(stage.get("executors", []))
            row["hosts"].update(item["host"] for item in log.get("executors", [])
                                if item.get("executor_id") in executor_ids and item.get("host"))
    rows = {name: {"task_count": value["task_count"], "hosts": sorted(value["hosts"])}
            for name, value in per_stage.items()}
    observed = {host for row in rows.values() for host in row["hosts"]}
    has_tasks = any(row["task_count"] for row in rows.values())
    verified = (completed_logs > 0 and malformed == 0 and has_tasks
                and set(EXPECTED_WORKERS).issubset(observed))
    return {"per_stage": rows, "observed_hosts": sorted(observed),
            "completed_event_logs": completed_logs, "malformed_line_count": malformed,
            "verified": verified}


def _executor_identity(rows):
    import os
    import socket
    from pyspark import TaskContext

    context = TaskContext.get()
    # The host workers are launched with the private EC2 address in this env var;
    # Spark's registered host name is also recorded for cross-checking.
    yield {"partition_id": context.partitionId(), "private_ip": os.environ.get("SPARK_LOCAL_IP"),
           "resolved_ip": socket.gethostbyname(socket.gethostname()), "hostname": socket.gethostname(),
           "items": sum(1 for _ in rows)}


def _watch_supervisor(control: Path) -> None:
    while True:
        if not fresh_control(control):
            print("CLUSTER_BENCHMARK_ABORT: supervisor heartbeat unavailable", flush=True)
            os._exit(70)
        time.sleep(3)


def run(args) -> dict:
    validate_paths(args.run_id, args.manifest, args.output, args.telemetry_dir,
                   args.events_dir, args.summary)
    wait_for_start(args.control_dir, timeout=args.start_timeout)
    watcher = threading.Thread(target=_watch_supervisor, args=(args.control_dir,), daemon=True)
    watcher.start()

    master = os.environ.get("SPARK_MASTER_URL")
    if not master or not master.startswith("spark://"):
        raise RuntimeError("SPARK_MASTER_URL must name the dedicated standalone experiment master")
    if args.events_dir.exists() or args.telemetry_dir.exists() or args.summary.exists():
        raise FileExistsError("Experiment telemetry/event/report paths must be new")
    args.events_dir.mkdir(parents=True)
    args.telemetry_dir.parent.mkdir(parents=True, exist_ok=True)

    from pyspark.sql import SparkSession
    builder = (SparkSession.builder.appName("pickage-real-two-ec2-benchmark-" + args.run_id)
               .master(master)
               .config("spark.driver.memory", os.environ.get("SPARK_DRIVER_MEMORY", "1g"))
               .config("spark.driver.host", os.environ.get("SPARK_DRIVER_HOST", "172.26.8.249"))
               .config("spark.driver.bindAddress", os.environ.get("SPARK_DRIVER_BIND", "172.26.8.249"))
               .config("spark.executor.memory", os.environ.get("SPARK_EXECUTOR_MEMORY", "2g"))
               .config("spark.executor.cores", "1")
               .config("spark.cores.max", "2")
               .config("spark.default.parallelism", str(args.partitions))
               .config("spark.sql.shuffle.partitions", str(args.partitions))
               .config("spark.scheduler.barrier.maxConcurrentTasksCheck.interval", "2s")
               .config("spark.scheduler.barrier.maxConcurrentTasksCheck.maxFailures", "30")
               .config("spark.eventLog.enabled", "true")
               .config("spark.eventLog.dir", args.events_dir.resolve().as_uri())
               .config("spark.eventLog.compress", "false")
               .config("spark.eventLog.rolling.enabled", "false")
               .config("spark.hadoop.mapreduce.fileoutputcommitter.marksuccessfuljobs", "false"))
    for env_name, conf_name in (("SPARK_DRIVER_PORT", "spark.driver.port"),
                                ("SPARK_DRIVER_BLOCK_MANAGER_PORT", "spark.driver.blockManager.port"),
                                ("SPARK_BLOCK_MANAGER_PORT", "spark.blockManager.port"),
                                ("SPARK_PORT_MAX_RETRIES", "spark.port.maxRetries")):
        if env_name in os.environ:
            builder = builder.config(conf_name, os.environ[env_name])
    if os.environ.get("SPARK_UI_ENABLED", "false").lower() == "false":
        builder = builder.config("spark.ui.enabled", "false")

    started = time.monotonic()
    try:
        spark = builder.getOrCreate()
    except BaseException as error:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(json.dumps({"format_version": 1, "run_id": args.run_id,
            "scope": "REAL_RAW_TWO_EC2_SPARK_BENCHMARK", "status": "FAILED",
            "startup_and_probe_seconds": time.monotonic() - started,
            "startup_error": {"type": type(error).__name__, "message": str(error)},
            "production_publication": False, "db_loaded": False}, indent=2) + "\n",
            encoding="utf-8")
        raise
    spark.sparkContext.setLogLevel("ERROR")
    # Capture this while the context is live. job.main may stop the shared
    # context during its cleanup, after which accessing applicationId raises.
    application_id = spark.sparkContext.applicationId
    conf = spark.sparkContext.getConf()
    resource_profile = {
        "driver_heap_config": conf.get("spark.driver.memory", "unknown"),
        "driver_runtime_max_heap_bytes": int(
            spark.sparkContext._jvm.java.lang.Runtime.getRuntime().maxMemory()),
        "executor_heap_config": conf.get("spark.executor.memory", "unknown"),
        "executor_cores_config": conf.get("spark.executor.cores", "unknown"),
        "total_cores_config": conf.get("spark.cores.max", "unknown"),
        "container_caps_are_set_by_supervisor": True,
    }
    barrier_started = time.monotonic()
    try:
        barrier_rows = (spark.sparkContext.parallelize(range(len(EXPECTED_WORKERS)), len(EXPECTED_WORKERS))
                        .barrier().mapPartitions(_executor_identity).collect())
        barrier = validate_barrier_hosts(barrier_rows)
        barrier["seconds"] = time.monotonic() - barrier_started
        barrier["application_id"] = application_id
        startup_and_probe_seconds = time.monotonic() - started
        print("CLUSTER_BENCHMARK_BARRIER_VERIFIED " + json.dumps(barrier, sort_keys=True), flush=True)

        from pipeline.preprocessing.experiments.spark.job import STAGES
        unknown = [stage for stage in args.stages if stage not in STAGES]
        if unknown or len(args.stages) != len(set(args.stages)):
            raise ValueError("Unknown or duplicate selected stage: " + ",".join(unknown))
        from pipeline.preprocessing.experiments.spark.job import main as run_job
        job_args = ["--manifest", args.manifest, "--engine", "spark", "--output", args.output,
                    "--stages", ",".join(args.stages), "--partitions", str(args.partitions),
                    "--telemetry-dir", str(args.telemetry_dir)]
        job_error = None
        try:
            result_code = run_job(job_args)
            if result_code:
                job_error = RuntimeError("Spark preprocessing job returned " + str(result_code))
        except BaseException as error:
            job_error = error
        finally:
            # job.main owns the shared SparkContext cleanup. Event files are parsed
            # only after it stops the context so executor summaries are final.
            # stop() is idempotent; avoid touching SparkContext after job.main
            # has performed its own cleanup.
            spark.stop()

        from pipeline.preprocessing.experiments.spark.telemetry import parse_event_log
        logs = [parse_event_log(path) for path in sorted(args.events_dir.iterdir())
                if path.is_file() and not path.name.startswith(".")]
        data_evidence = summarize_data_stage_hosts(logs, args.stages)
        summary = {"format_version": 1, "run_id": args.run_id,
                   "scope": "REAL_RAW_TWO_EC2_SPARK_BENCHMARK",
                   "status": "COMPUTED" if job_error is None and data_evidence["verified"] else "FAILED",
                   "application_id": application_id,
                   "startup_and_probe_seconds": startup_and_probe_seconds,
                   "barrier_probe": barrier,
                   "resource_profile": resource_profile,
                   "selected_stages": args.stages,
                   "real_data_stage_execution": data_evidence,
                   "event_log_summaries": logs,
                   "job_error": ({"type": type(job_error).__name__, "message": str(job_error)}
                                 if job_error else None),
                   "output": args.output, "manifest": args.manifest,
                   "production_publication": False, "db_loaded": False}
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(json.dumps(summary, ensure_ascii=False, sort_keys=True,
                                           indent=2, default=str) + "\n", encoding="utf-8")
        print("CLUSTER_BENCHMARK_RESULT " + json.dumps(summary, ensure_ascii=False,
                                                       sort_keys=True, default=str), flush=True)
        if job_error is not None:
            raise job_error
        if not data_evidence["verified"]:
            raise RuntimeError("Selected real-data stages lack complete event-log evidence on both EC2 workers")
        return summary
    except BaseException:
        # If the barrier or setup fails before job.main, retain a local failure
        # record. No outputs outside the experimental S3 prefix are touched.
        if not args.summary.exists():
            args.summary.parent.mkdir(parents=True, exist_ok=True)
            args.summary.write_text(json.dumps({"format_version": 1, "run_id": args.run_id,
                "scope": "REAL_RAW_TWO_EC2_SPARK_BENCHMARK", "status": "FAILED",
                "application_id": application_id,
                "startup_and_probe_seconds": time.monotonic() - started,
                "production_publication": False, "db_loaded": False}, indent=2) + "\n",
                encoding="utf-8")
        spark.stop()
        raise


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--telemetry-dir", type=Path, required=True)
    parser.add_argument("--events-dir", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--control-dir", type=Path, default=Path("/control"))
    parser.add_argument("--start-timeout", type=int, default=90)
    parser.add_argument("--partitions", type=int, default=64)
    parser.add_argument("--stages", default=",".join(STAGES))
    args = parser.parse_args(argv)
    args.stages = args.stages.split(",")
    if args.partitions < 2 or args.start_timeout < 1:
        parser.error("partitions must be >=2 and start-timeout must be >=1")
    return args


def main(argv=None) -> int:
    run(parse_args(argv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
