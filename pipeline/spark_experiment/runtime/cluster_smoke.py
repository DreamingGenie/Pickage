"""Validate a local standalone Spark cluster and Node semver on its workers."""
import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

from pyspark.sql import SparkSession


def wait_for_workers(expected):
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            with urlopen("http://master:8080/json/", timeout=2) as response:
                workers = json.load(response).get("workers", [])
            alive = [worker for worker in workers if worker.get("state") == "ALIVE"]
            if len(alive) >= expected:
                return
        except Exception:
            pass
        time.sleep(1)
    raise TimeoutError(f"Spark master did not register {expected} workers")


def inspect_partition(rows):
    check_semver = (
        "const s=require('/usr/local/lib/node_modules/npm/node_modules/semver');"
        "process.stdout.write(String(s.valid('1.2.3')))"
    )
    node_version = subprocess.run(["/usr/local/bin/node", "--version"],
                                  check=True, capture_output=True, text=True).stdout.strip()
    semver = subprocess.run(["/usr/local/bin/node", "-e", check_semver],
                            check=True, capture_output=True, text=True).stdout
    java_output = subprocess.run(["java", "-version"], check=True,
                                 capture_output=True, text=True).stderr.splitlines()[0]
    java_match = re.search(r'"([^"]+)"', java_output)
    java_version = java_match.group(1) if java_match else java_output
    count = sum(1 for _ in rows)
    yield {"hostname": socket.gethostname(), "items": count,
           "python_version": sys.version.split()[0], "java_version": java_version,
           "node_version": node_version, "node_semver_1_2_3": semver == "1.2.3"}


def main():
    workers = int(os.environ.get("SPARK_WORKER_COUNT", "2"))
    parallelism = int(os.environ.get("SPARK_PARALLELISM", str(workers)))
    wait_for_workers(workers)
    spark = (SparkSession.builder.appName("local-two-worker-runtime-smoke")
             .master(os.environ.get("SPARK_MASTER_URL", "spark://master:7077"))
             .config("spark.cores.max", str(workers))
             .config("spark.executor.cores", "1")
             .config("spark.executor.instances", str(workers))
             .config("spark.task.cpus", "1")
             .config("spark.driver.memory", "512m")
             .config("spark.driver.host", socket.gethostbyname(socket.gethostname()))
             .getOrCreate())
    try:
        results = (spark.sparkContext.parallelize(range(parallelism), parallelism)
                   .barrier().mapPartitions(inspect_partition).collect())
        hosts = sorted({record["hostname"] for record in results})
        evidence = {"master": os.environ.get("SPARK_MASTER_URL", "spark://master:7077"),
                    "expected_workers": workers, "partitions": parallelism,
                    "task_results": results, "worker_hostnames": hosts,
                    "distinct_workers_observed": len(hosts),
                    "node_semver_passed": all(r["node_semver_1_2_3"] for r in results),
                    "runtime_versions": [{key: record[key] for key in
                                          ("hostname", "python_version", "java_version", "node_version")}
                                         for record in results]}
        if len(hosts) < workers or not evidence["node_semver_passed"]:
            raise RuntimeError("Tasks did not validate distinct workers and Node semver: " + json.dumps(evidence))
        target = Path(os.environ["SPARK_RESULT_PATH"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(evidence, sort_keys=True))
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
