"""Run fixed stage inputs with either engine; no production publications."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import sys
import time
from urllib.parse import urlsplit

STAGES = ("package_version", "downloads", "repository", "package_snapshot", "dependents")
GROUPS = {
    "package_version": ["package/data", "version/data", "package_ids/data", "quality/repository_selection",
                        "quality/excluded_versions", "quality/dependency_issues", "quality/metadata_issues"],
    "downloads": ["interval_downloads.parquet", "daily_quality.parquet", "unmatched_packages.parquet"],
    "repository": ["metric/data", "quality/selection", "quality/candidates", "quality/project_observations",
                   "quality/project_conflicts", "quality/unmapped_projects"],
    "package_snapshot": ["package_snapshot.parquet", "package_identity.parquet", "quality.parquet"],
    "dependents": ["version_dependents", "quality", "resolution_lookup"],
}


def code_sha():
    root = Path(__file__).resolve().parents[2]
    digest = hashlib.sha256()
    for path in sorted((root / "pipeline").rglob("*")):
        if path.is_file() and path.suffix in (".py", ".cjs") and "node_modules" not in path.parts:
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
    return digest.hexdigest()


def node_runtime():
    root = Path(__file__).resolve().parents[1]
    npm = os.environ.get("EXPERIMENT_NPM_MODULES", "/usr/local/lib/node_modules/npm/node_modules")
    return {"node": os.environ.get("EXPERIMENT_NODE", "/usr/local/bin/node"),
            "semver_module": npm + "/semver", "package_arg_module": npm + "/npm-package-arg",
            "worker": os.environ.get("EXPERIMENT_NODE_WORKER", str(root / "version_dependents/historical_semver_worker.cjs")),
            "classifier_worker": os.environ.get("EXPERIMENT_CLASSIFIER_WORKER", str(root / "requirements_resolution/semver_worker.cjs"))}


def spark_session(partitions, event_dir=None):
    from pyspark.sql import SparkSession
    builder = (SparkSession.builder.appName("pickage-preprocessing-experiment")
             .config("spark.sql.session.timeZone", "UTC")
             .config("spark.sql.caseSensitive", "true")
             .config("spark.sql.parquet.outputTimestampType", "TIMESTAMP_MICROS")
             .config("spark.sql.shuffle.partitions", str(partitions))
             .config("spark.sql.adaptive.enabled", "true")
             .config("spark.hadoop.mapreduce.fileoutputcommitter.marksuccessfuljobs", "false"))
    if event_dir:
        builder = (builder.config('spark.eventLog.enabled', 'true')
                   .config('spark.eventLog.dir', event_dir.as_uri())
                   .config('spark.eventLog.compress', 'false')
                   .config('spark.eventLog.rolling.enabled', 'false'))
    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")
    return spark


def read_json(location, spark=None):
    if location.startswith("s3a://"):
        jvm = spark._jvm
        path = jvm.org.apache.hadoop.fs.Path(location)
        stream = path.getFileSystem(spark._jsc.hadoopConfiguration()).open(path)
        try:
            return json.loads(jvm.org.apache.commons.io.IOUtils.toString(stream, "UTF-8"))
        finally:
            stream.close()
    return json.loads(Path(location).read_bytes())


def verify_manifest(manifest, spark=None):
    """Verify bytes in the execution environment, including shared S3A inputs."""
    if manifest.get("format_version") != 1 or not manifest.get("input_files"):
        raise ValueError("Invalid frozen input manifest")
    for record in manifest["input_files"]:
        location = record["path"]
        if location.startswith("s3a://"):
            path = spark._jvm.org.apache.hadoop.fs.Path(location)
            fs = path.getFileSystem(spark._jsc.hadoopConfiguration())
            size = fs.getFileStatus(path).getLen()
            stream = fs.open(path)
            try:
                digest = spark._jvm.org.apache.commons.codec.digest.DigestUtils.sha256Hex(stream)
            finally:
                stream.close()
        else:
            path = Path(location)
            size = path.stat().st_size
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1048576), b""):
                    digest.update(block)
            digest = digest.hexdigest()
        if size != record["bytes"] or digest != record["sha256"]:
            raise ValueError("Frozen experiment input changed: " + location)


def write_json(location, value, spark=None):
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, default=str)
    if location.startswith("s3a://"):
        jvm = spark._jvm
        path = jvm.org.apache.hadoop.fs.Path(location)
        stream = path.getFileSystem(spark._jsc.hadoopConfiguration()).create(path, False)
        try:
            stream.write(bytearray(body.encode()))
        finally:
            stream.close()
    else:
        path = Path(location)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as stream:
            stream.write(body)


def baseline(name, inputs, output, threads, memory):
    import duckdb
    if name == "package_version":
        from pipeline.curated.transform import transform
        with duckdb.connect(config={"threads": threads, "memory_limit": memory}) as con:
            con.execute("SET temp_directory=?", [output + "-scratch"])
            return transform(con, output=Path(output), **inputs)
    if name == "downloads":
        from pipeline.downloads_interval.aggregate import aggregate
        return aggregate(inputs, Path(output), threads=threads, memory_limit=memory)
    if name == "package_snapshot":
        from pipeline.package_snapshot.build import _build
        records, quality = _build(inputs, Path(output), threads=threads, memory_limit=memory)
        return {"files": records, "quality": quality}
    if name == "repository":
        from pipeline.repository_metrics.runtime import create_spark
        from pipeline.repository_metrics.transform import transform
        spark = create_spark(Path(output + "-runtime"), threads=threads,
                             driver_memory=memory.lower().replace("gb", "g").replace("mb", "m"))
        try:
            return transform(spark, inputs, Path(output))
        finally:
            spark.stop()
    from pipeline.orchestration.dependents import calculate
    runtime = node_runtime()
    runtime = {key: runtime[key] for key in ("node", "semver_module", "package_arg_module")}
    with duckdb.connect(config={"threads": threads, "memory_limit": memory}) as con:
        con.execute("SET temp_directory=?", [output + "-scratch"])
        directory, records, quality = calculate(con, output=Path(output), runtime=runtime, **inputs)
        return {"files": records, "quality": quality}


def spark_stage(name, spark, inputs, output):
    if name == "package_version":
        from .package_version import transform
        return transform(spark, output=output, **inputs)
    if name == "downloads":
        from .downloads import aggregate
        return aggregate(spark, inputs, output)
    if name == "repository":
        from .repository import transform
        return transform(spark, inputs, output)
    if name == "package_snapshot":
        from .package_snapshot import transform
        return transform(spark, inputs, output)
    from .dependents import calculate
    return calculate(spark, output=output, runtime=node_runtime(), **inputs)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--engine", choices=("baseline", "spark"), required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--stages", default=",".join(STAGES))
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--partitions", type=int, default=4)
    parser.add_argument("--memory", default="2GB")
    parser.add_argument("--telemetry-dir", type=Path,
                        help="Dedicated local directory for cgroup samples and Spark event logs")
    args = parser.parse_args(argv)
    names = args.stages.split(",")
    if any(name not in STAGES for name in names) or len(names) != len(set(names)):
        parser.error("unknown or duplicate stage")
    if args.output.startswith("s3a://"):
        remote = urlsplit(args.output)
        if (remote.netloc != "pickage-curated" or not remote.path.startswith("/experiments/")
                or any(p in ("", ".", "..") for p in remote.path.strip("/").split("/"))
                or remote.query or remote.fragment or args.engine != "spark"
                or args.telemetry_dir is None):
            parser.error("remote Spark output must use pickage-curated/experiments/<unique-run> and --telemetry-dir")
    from .telemetry import Sampler, read_snapshot, snapshot_delta, parse_event_log
    event_dir = None
    original_submit_args = os.environ.get('PYSPARK_SUBMIT_ARGS')
    if args.telemetry_dir:
        args.telemetry_dir = args.telemetry_dir.resolve()
        args.telemetry_dir.mkdir(parents=True, exist_ok=False)
        event_dir = args.telemetry_dir / 'events'
        event_dir.mkdir()
        if args.engine == 'baseline':
            # The existing repository stage starts a local Spark session. Configure
            # its event log through the process environment, without editing it.
            flags = ['--conf', 'spark.eventLog.enabled=true', '--conf',
                     'spark.eventLog.dir=' + event_dir.as_uri(), '--conf',
                     'spark.eventLog.compress=false', '--conf', 'spark.eventLog.rolling.enabled=false']
            os.environ['PYSPARK_SUBMIT_ARGS'] = shlex.join(flags) + ' ' + (original_submit_args or 'pyspark-shell')
    start = time.perf_counter()
    report = {"engine": args.engine, "scope": "FIXED_STAGE_INPUT_COMPARISON", "status": "RUNNING",
              "python": platform.python_version(), "code_sha256": code_sha(), "stages": {},
              "settings": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
              "cpu_seconds": None, "peak_process_memory_bytes": None,
              "executor_memory_bytes": None, "db_loaded": False, "production_publication": False}
    spark = None
    sampler = None
    stage_error = None
    stage_traceback = None
    try:
        sampler = Sampler().start()
        if args.engine == "spark":
            spark = spark_session(args.partitions, event_dir)
            report.update(spark_version=spark.version, master=spark.sparkContext.master,
                          application_id=spark.sparkContext.applicationId)
        report["startup_seconds"] = time.perf_counter() - start
        manifest = read_json(args.manifest, spark)
        verification_start = time.perf_counter()
        verify_manifest(manifest, spark)
        report["input_verification_seconds"] = time.perf_counter() - verification_start
        report["input_identity"] = manifest.get("input_identity", hashlib.sha256(json.dumps(
            {"request": manifest["source_request"], "files": sorted(
                (r["sha256"], r["bytes"]) for r in manifest["input_files"])}, sort_keys=True).encode()).hexdigest())
        for name in names:
            began = time.perf_counter()
            before_stage = read_snapshot()
            if spark:
                spark.sparkContext.setJobGroup(name, 'Preprocessing stage: ' + name)
            output = args.output.rstrip("/") + "/" + name
            value = (spark_stage(name, spark, manifest["stages"][name], output) if spark else
                     baseline(name, manifest["stages"][name], output, args.threads, args.memory))
            report["stages"][name] = {"seconds": time.perf_counter() - began, "output": output,
                                     "result": value, "container_counters": snapshot_delta(before_stage, read_snapshot())}
            if spark:
                spark.catalog.clearCache()
            print("EXPERIMENT_STAGE_COMPLETE", name, report["stages"][name]["seconds"], flush=True)
        report["status"] = "COMPUTED"
    except BaseException as error:
        stage_error = error
        stage_traceback = sys.exc_info()[2]
        report.update(status="FAILED", error={"type": type(error).__name__, "message": str(error)})
    finally:
        cleanup_errors = []

        def cleanup(label, action):
            try:
                return action()
            except BaseException as error:
                cleanup_errors.append({"step": label, "type": type(error).__name__, "message": str(error)})
                return None

        # Hadoop S3 report writing needs the live context. Its failure must not
        # prevent local telemetry collection or environment restoration.
        remote_output = args.output.startswith('s3a://')
        if remote_output:
            report['job_seconds'] = time.perf_counter() - start
            report['telemetry_companion'] = str(args.telemetry_dir/'report-with-telemetry.json')
            cleanup("provisional_remote_report", lambda: write_json(
                args.output.rstrip('/') + '/report.json', report, spark))
        if spark:
            cleanup("spark_stop", spark.stop)
        measured = cleanup("sampler_stop", sampler.stop) if sampler else None
        if measured is None and sampler:
            measured = cleanup("sampler_snapshot_fallback", sampler.summary)
        report['job_seconds'] = time.perf_counter() - start
        if measured is not None:
            delta = measured['delta']
            usage = delta['cpu']['usage_usec'] if delta else None
            peaks = [s['memory']['peak'] for s in measured['samples'] if s['memory']['peak'] is not None]
            report['telemetry'] = {'sample_count': measured['sample_count'], 'container_delta': delta,
                                   'container_cpu_seconds': usage / 1e6 if usage is not None else None,
                                   'container_peak_memory_bytes': max(peaks) if peaks else None,
                                   'scope': 'CURRENT_CONTAINER_ONLY; distributed executors require per-host monitor',
                                   'limitations': measured['samples'][0]['limitations'] if measured['samples'] else {}}
            if args.telemetry_dir:
                cleanup("local_samples_save", lambda: (args.telemetry_dir/'samples.json').write_text(
                    json.dumps(measured), encoding='utf-8'))
                try:
                    report['telemetry']['spark_event_logs'] = [parse_event_log(p) for p in sorted(event_dir.iterdir())
                        if p.is_file() and not p.name.startswith('.')]
                except BaseException as error:
                    cleanup_errors.append({"step": "event_log_parse", "type": type(error).__name__, "message": str(error)})
                report['cleanup_errors'] = cleanup_errors
                cleanup("local_telemetry_report_save", lambda: (args.telemetry_dir/'report-with-telemetry.json').write_text(
                    json.dumps(report, default=str), encoding='utf-8'))
        report['cleanup_errors'] = cleanup_errors
        if not remote_output:
            cleanup("local_report_save", lambda: write_json(args.output.rstrip('/') + '/report.json', report))
        if original_submit_args is None:
            cleanup("environment_restore", lambda: os.environ.pop('PYSPARK_SUBMIT_ARGS', None))
        else:
            cleanup("environment_restore", lambda: os.environ.__setitem__('PYSPARK_SUBMIT_ARGS', original_submit_args))
        report['cleanup_errors'] = cleanup_errors
        if cleanup_errors and report['status'] == 'COMPUTED':
            report['status'] = 'CLEANUP_FAILED'
        if args.telemetry_dir and measured is not None:
            cleanup("final_local_telemetry_report_save", lambda: (args.telemetry_dir/'report-with-telemetry.json').write_text(
                json.dumps(report, default=str), encoding='utf-8'))
        if not remote_output and cleanup_errors:
            cleanup("final_local_report_save", lambda: write_json(args.output.rstrip('/') + '/report.json', report))
    if stage_error is not None:
        raise stage_error.with_traceback(stage_traceback)
    if cleanup_errors:
        raise RuntimeError("experiment cleanup failed: " + "; ".join(
            error['step'] + ": " + error['message'] for error in cleanup_errors))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
