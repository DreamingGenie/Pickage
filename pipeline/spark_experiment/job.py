"""Run fixed stage inputs with either engine; no production publications."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
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


def spark_session(partitions):
    from pyspark.sql import SparkSession
    spark = (SparkSession.builder.appName("pickage-preprocessing-experiment")
             .config("spark.sql.session.timeZone", "UTC")
             .config("spark.sql.caseSensitive", "true")
             .config("spark.sql.parquet.outputTimestampType", "TIMESTAMP_MICROS")
             .config("spark.sql.shuffle.partitions", str(partitions))
             .config("spark.sql.adaptive.enabled", "true")
             .config("spark.hadoop.mapreduce.fileoutputcommitter.marksuccessfuljobs", "false")
             .getOrCreate())
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
    args = parser.parse_args(argv)
    names = args.stages.split(",")
    if any(name not in STAGES for name in names) or len(names) != len(set(names)):
        parser.error("unknown or duplicate stage")
    if args.output.startswith("s3a://"):
        remote = urlsplit(args.output)
        if (remote.netloc != "pickage-curated" or not remote.path.startswith("/experiments/")
                or any(p in ("", ".", "..") for p in remote.path.strip("/").split("/"))
                or remote.query or remote.fragment or args.engine != "spark"):
            parser.error("remote Spark output must use pickage-curated/experiments/<unique-run>")
    start = time.perf_counter()
    report = {"engine": args.engine, "scope": "FIXED_STAGE_INPUT_COMPARISON", "status": "RUNNING",
              "python": platform.python_version(), "code_sha256": code_sha(), "stages": {},
              "settings": vars(args), "cpu_seconds": None, "peak_process_memory_bytes": None,
              "executor_memory_bytes": None, "db_loaded": False, "production_publication": False}
    spark = None
    try:
        if args.engine == "spark":
            spark = spark_session(args.partitions)
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
            output = args.output.rstrip("/") + "/" + name
            value = (spark_stage(name, spark, manifest["stages"][name], output) if spark else
                     baseline(name, manifest["stages"][name], output, args.threads, args.memory))
            report["stages"][name] = {"seconds": time.perf_counter() - began, "output": output, "result": value}
            if spark:
                spark.catalog.clearCache()
            print("EXPERIMENT_STAGE_COMPLETE", name, report["stages"][name]["seconds"], flush=True)
        report["status"] = "COMPUTED"
    except BaseException as error:
        report.update(status="FAILED", error={"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        report["job_seconds"] = time.perf_counter() - start
        write_json(args.output.rstrip("/") + "/report.json", report, spark)
        if spark:
            spark.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
