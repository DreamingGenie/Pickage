"""Guarded repository-only 2+2 core comparison entry point.

The host supervisors own the experiment directory and start signal.  This
module only runs one phase, leaving production services and the old frozen
sample untouched.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import socket
import threading
import time

from pipeline.preprocessing.experiments.spark.runtime.benchmark_data_phase import RateLimit, client
from pipeline.preprocessing.experiments.spark.runtime.repository_profile import Recorder, summarize_actions
from pipeline.preprocessing.experiments.spark.runtime.repository_profile_summary import write_summary
from pipeline.preprocessing.experiments.spark.runtime.repository_retry_entry import fresh_control, wait_for_start


RUN = "repository22-20260917-a1"
ROOT = Path("/experiment") / RUN
SOURCE_ROOT = Path("/experiment/sample1000-ec2-20260916-a2")
SOURCE = SOURCE_ROOT / "local-manifest.json"
SHARED_SOURCE = SOURCE_ROOT / "shared-manifest.json"
SOURCE_SHA256 = "47a2cea179b368577891005102785ca801ee413b3df6e9abf9118c4bd45c11f6"
BUCKET = "pickage-curated"
PREFIX = f"experiments/{RUN}"
EXPECTED_WORKERS = frozenset({"172.26.8.249", "172.26.6.235"})
EXPECTED_EXECUTOR_CORES = "2"
EXPECTED_TOTAL_CORES = "4"
CONTROL = Path("/control")


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_frozen_inputs() -> tuple[dict, dict, str]:
    raw = SOURCE.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != SOURCE_SHA256:
        raise ValueError("Pinned frozen baseline manifest changed")
    baseline = json.loads(raw)
    shared = _json(SHARED_SOURCE)
    if baseline.get("input_identity") != shared.get("input_identity"):
        raise ValueError("Baseline and shared manifests have different input_identity")
    baseline_files = sorted((row.get("sha256"), row.get("bytes"))
                            for row in baseline.get("input_files", []))
    shared_files = sorted((row.get("sha256"), row.get("bytes"))
                          for row in shared.get("input_files", []))
    if baseline_files != shared_files:
        raise ValueError("Baseline and shared manifests have different input inventory")
    if baseline.get("stages", {}).get("repository", {}).get("counts") != \
            shared.get("stages", {}).get("repository", {}).get("counts"):
        raise ValueError("Baseline and shared manifests have different repository counts")
    if baseline.get("sample", {}).get("package_rows") != 1000:
        raise ValueError("Expected the frozen 1,000-package sample")
    return baseline, shared, digest


def _watch(root: Path) -> None:
    while True:
        if not fresh_control(root):
            print("REPOSITORY22_ABORT: supervisor heartbeat unavailable", flush=True)
            os._exit(70)
        time.sleep(3)


def gate(control: Path = CONTROL) -> threading.Thread:
    wait_for_start(control)
    thread = threading.Thread(target=_watch, args=(control,), daemon=True)
    thread.start()
    return thread


def _executor_identity(rows):
    from pyspark import TaskContext

    context = TaskContext.get()
    private_ip = os.environ.get("SPARK_LOCAL_IP")
    try:
        resolved_ip = socket.gethostbyname(socket.gethostname())
    except OSError:
        resolved_ip = None
    yield {"partition_id": context.partitionId(), "private_ip": private_ip,
           "resolved_ip": resolved_ip, "hostname": socket.gethostname(),
           "items": sum(1 for _ in rows)}


def validate_barrier(rows: list[dict]) -> dict:
    observed = [row.get("private_ip") or row.get("resolved_ip") for row in rows]
    if len(rows) != 4 or any(observed.count(host) != 2 for host in EXPECTED_WORKERS):
        raise RuntimeError(f"Expected four barrier tasks, two on each EC2 worker: {rows}")
    if set(observed) != set(EXPECTED_WORKERS):
        raise RuntimeError(f"Unexpected barrier worker hosts: {rows}")
    return {"verified": True, "task_count": len(rows),
            "workers": {host: observed.count(host) for host in sorted(EXPECTED_WORKERS)}}


def _event_files(path: Path) -> list[Path]:
    return sorted(p for p in path.rglob("*") if p.is_file() and not p.name.startswith("."))


def verify_profile_summary(summary: dict) -> None:
    if summary.get("incomplete_log") or summary.get("malformed_line_count"):
        raise RuntimeError("Repository Spark event log is incomplete")
    profiles = [row for row in summary.get("profiles", [])
                if row.get("action") not in ("spark.startup", "spark.shutdown")]
    hosts = set(summary.get("repository_task_executor_hosts", []))
    for row in profiles:
        if row.get("successful_task_count", 1) > 0:
            hosts.update(row.get("hosts", []))
    for event_log in summary.get("event_log_summaries", []):
        executor_hosts = {str(item.get("executor_id")): item.get("host")
                          for item in event_log.get("executors", [])
                          if item.get("host")}
        for stage in event_log.get("stages", []):
            if str(stage.get("job_group_id", "")).startswith("repository-profile:"):
                hosts.update(executor_hosts.get(str(executor)) for executor in
                             stage.get("executors", []) if executor_hosts.get(str(executor)))
    # repository_profile_summary normally reports executor hosts when its
    # event parser has executor metadata.  Require the real repository tasks,
    # not merely the four-task barrier, to reach both workers.
    if not (profiles and EXPECTED_WORKERS.issubset(hosts)):
        raise RuntimeError("Repository profile has no task evidence from both EC2 workers")


def run_baseline(root: Path = ROOT) -> dict:
    baseline, _, digest = verify_frozen_inputs()
    output, telemetry = root / "baseline", root / "baseline-telemetry"
    action_file = root / "baseline-actions.jsonl"
    if output.exists() or telemetry.exists() or action_file.exists():
        raise FileExistsError("Baseline experiment output already exists")
    root.mkdir(parents=True, exist_ok=True)
    old_submit = os.environ.get("PYSPARK_SUBMIT_ARGS")
    os.environ["PYSPARK_SUBMIT_ARGS"] = "--driver-memory 4g pyspark-shell"
    try:
        from pipeline.preprocessing.experiments.spark.job import main as run_job
        with Recorder(action_file).install():
            run_job(["--manifest", str(SOURCE), "--engine", "baseline", "--stages", "repository",
                     "--threads", "2", "--memory", "4GB", "--partitions", "16",
                     "--output", str(output), "--telemetry-dir", str(telemetry)])
    finally:
        if old_submit is None:
            os.environ.pop("PYSPARK_SUBMIT_ARGS", None)
        else:
            os.environ["PYSPARK_SUBMIT_ARGS"] = old_submit
    report = _json(output / "report.json")
    if report.get("input_identity") != baseline.get("input_identity"):
        raise ValueError("Baseline input identity changed")
    (root / "baseline-actions-summary.json").write_text(
        json.dumps(summarize_actions(action_file), indent=2), encoding="utf-8")
    baseline_events = telemetry / "events"
    if baseline_events.exists():
        write_summary(baseline_events, root / "baseline-spark-summary.json")
    return {"status": report.get("status"), "input_identity": report["input_identity"],
            "manifest_sha256": digest, "report": str(output / "report.json")}


def run_spark(root: Path = ROOT) -> dict:
    _, shared, digest = verify_frozen_inputs()
    output_uri = f"s3a://{BUCKET}/{PREFIX}/spark-output"
    telemetry, events = root / "spark-telemetry", root / "cluster-events"
    action_file = root / "spark-actions.jsonl"
    summary_path = root / "repository-spark-summary.json"
    if telemetry.exists() or events.exists() or action_file.exists() or summary_path.exists():
        raise FileExistsError("Spark experiment output already exists")
    root.mkdir(parents=True, exist_ok=True)
    events.mkdir(parents=True)
    _, _, manifest_digest = verify_frozen_inputs()
    claim_client = client()
    claim_client.put_object(
        Bucket=BUCKET, Key=PREFIX + "/_CLAIM.json",
        Body=json.dumps({"run_id": RUN, "manifest_sha256": manifest_digest,
                         "input_identity": shared.get("input_identity")},
                        sort_keys=True).encode(), IfNoneMatch="*")
    started = time.monotonic()
    spark = None
    barrier = None
    try:
        from pipeline.preprocessing.experiments.spark import job
        spark = job.spark_session(16, events)
        conf = spark.sparkContext.getConf()
        if (conf.get("spark.executor.cores") != EXPECTED_EXECUTOR_CORES or
                conf.get("spark.cores.max") != EXPECTED_TOTAL_CORES):
            raise RuntimeError("Spark submission did not provide expected 2/4 core settings")
        barrier = validate_barrier(spark.sparkContext.parallelize(range(4), 4)
                                   .barrier().mapPartitions(_executor_identity).collect())
        startup_probe = time.monotonic() - started
        print("REPOSITORY22_BARRIER_VERIFIED " + json.dumps(barrier, sort_keys=True), flush=True)
        original_session = job.spark_session
        # Reuse the already configured distributed context so startup and the
        # barrier are measured outside the repository stage exactly once.
        job.spark_session = lambda partitions, event_dir=None: spark
        try:
            with Recorder(action_file).install():
                job.main(["--manifest", str(SHARED_SOURCE), "--engine", "spark",
                          "--stages", "repository", "--partitions", "16",
                          "--output", output_uri, "--telemetry-dir", str(telemetry)])
        finally:
            job.spark_session = original_session
        spark = None  # job.main owns and has stopped the shared session
        summary = write_summary(events, summary_path)
        # repository_profile_summary carries action metrics; the event parser
        # carries executor-to-host attribution. Keep both in one local record.
        from pipeline.preprocessing.experiments.spark.telemetry import parse_event_log
        summary["event_log_summaries"] = [parse_event_log(path) for path in _event_files(events)]
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8")
        verify_profile_summary(summary)
    finally:
        if spark is not None:
            spark.stop()
    report = _read_s3_json(client(), f"{PREFIX}/spark-output/report.json")
    if report.get("input_identity") != shared.get("input_identity"):
        raise ValueError("Spark input identity changed")
    (root / "spark-actions-summary.json").write_text(
        json.dumps(summarize_actions(action_file), indent=2), encoding="utf-8")
    (root / "spark-run.json").write_text(json.dumps({
        "status": report.get("status"), "input_identity": report["input_identity"],
        "manifest_sha256": digest, "startup_and_probe_seconds": startup_probe,
        "barrier": barrier, "report": f"s3a://{BUCKET}/{PREFIX}/spark-output/report.json",
        "repository_stage_seconds": report.get("stages", {}).get("repository", {}).get("seconds")
    }, indent=2), encoding="utf-8")
    return report


def _read_s3_json(s3, key: str) -> dict:
    body = s3.get_object(Bucket=BUCKET, Key=key)["Body"]
    try:
        return json.loads(body.read())
    finally:
        body.close()


def download_outputs(root: Path, s3) -> tuple[Path, int]:
    destination = root / "spark-results"
    destination.mkdir(exist_ok=False)
    limiter = RateLimit(16)
    source_prefix = PREFIX + "/spark-output/"
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=source_prefix):
        for item in page.get("Contents", []):
            key = item["Key"]
            if not key.endswith(".parquet"):
                continue
            relative = key[len(source_prefix):]
            if any(part in ("", ".", "..") for part in relative.split("/")):
                raise ValueError("Unsafe Spark output key")
            path = destination / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as out:
                body = s3.get_object(Bucket=BUCKET, Key=key)["Body"]
                try:
                    for chunk in iter(lambda: body.read(1024 * 1024), b""):
                        out.write(chunk)
                        limiter.account(len(chunk))
                finally:
                    body.close()
            if path.stat().st_size != item["Size"]:
                raise ValueError("Downloaded Spark output differs in size")
    return destination, limiter.bytes


def compare(root: Path = ROOT) -> dict:
    baseline = _json(root / "baseline/report.json")
    spark = _read_s3_json(client(), f"{PREFIX}/spark-output/report.json")
    if baseline.get("input_identity") != spark.get("input_identity"):
        raise ValueError("Comparison inputs differ")
    destination, downloaded = download_outputs(root, client())
    local_spark = copy.deepcopy(spark)
    for stage in local_spark.get("stages", {}):
        local_spark["stages"][stage]["output"] = str(destination / stage)
    from pipeline.preprocessing.experiments.spark.runtime.bounded_compare import compare as exact_compare
    comparison = exact_compare(baseline, local_spark, root / "comparison")
    result = {"status": "VERIFIED" if comparison["status"] == "EQUAL" else "FAILED",
              "comparison": comparison, "input_identity": baseline["input_identity"],
              "baseline_stage_seconds": {k: v["seconds"] for k, v in baseline["stages"].items()},
              "spark_stage_seconds": {k: v["seconds"] for k, v in spark["stages"].items()},
              "startup_and_probe_seconds": _json(root / "spark-run.json").get("startup_and_probe_seconds"),
              "result_download_bytes": downloaded, "result_download_rate_limit_mib_per_second": 16,
              "scope": "REPOSITORY_ONLY_TWO_EC2_2_PLUS_2_COMPARISON",
              "db_loaded": False, "production_publication": False}
    (root / "comparison-result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    if result["status"] != "VERIFIED":
        raise ValueError("Baseline and Spark repository outputs differ")
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("baseline", "spark", "compare"))
    args = parser.parse_args(argv)
    gate()
    print("REPOSITORY22_PHASE_STARTED " + args.mode, flush=True)
    if args.mode == "baseline":
        result = run_baseline()
    elif args.mode == "spark":
        result = run_spark()
    else:
        result = compare()
    print("REPOSITORY22_PHASE_COMPLETE " + json.dumps(result, default=str, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
