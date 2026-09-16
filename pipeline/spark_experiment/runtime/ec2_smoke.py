"""Bounded runtime/shuffle check on the two EC2 experiment workers."""
import json
import os
import socket
import subprocess
import time
from pathlib import Path
from urllib.request import urlopen

from pyspark.sql import SparkSession


def executor_identity(rows):
    import platform
    import pyspark
    node = subprocess.check_output(['node', '--version'], text=True).strip()
    semver = subprocess.check_output(['node', '-e',
        "console.log(require('/usr/local/lib/node_modules/npm/node_modules/semver').satisfies('1.2.3','^1.0.0'))"], text=True).strip()
    yield {'hostname': socket.gethostname(), 'private_ip': os.environ['SPARK_LOCAL_IP'],
           'python': platform.python_version(), 'spark': pyspark.__version__,
           'node': node, 'semver_ok': semver == 'true', 'items': sum(1 for _ in rows)}


def main():
    expected = {'172.26.8.249', '172.26.6.235'}
    deadline = time.monotonic() + 60
    while True:
        with urlopen('http://172.26.8.249:18080/json/', timeout=3) as response:
            master = json.load(response)
        alive = {w['host'] for w in master['workers'] if w['state'] == 'ALIVE'}
        if alive == expected:
            break
        if time.monotonic() > deadline:
            raise RuntimeError('Expected one experimental worker on each EC2: ' + str(alive))
        time.sleep(1)
    spark = (SparkSession.builder.appName('pickage-ec2-runtime-20260915-a1')
             .master('spark://172.26.8.249:40014')
             .config('spark.driver.host', '172.26.8.249')
             .config('spark.driver.bindAddress', '172.26.8.249')
             .config('spark.driver.port', '40012')
             .config('spark.driver.blockManager.port', '40011')
             .config('spark.blockManager.port', '40013')
             .config('spark.port.maxRetries', '0')
             .config('spark.driver.memory', '512m')
             .config('spark.executor.memory', '1g')
             .config('spark.executor.cores', '1')
             .config('spark.cores.max', '2')
             .config('spark.default.parallelism', '2')
             .config('spark.ui.enabled', 'false')
             .config('spark.eventLog.enabled', 'true')
             .config('spark.eventLog.dir', 'file:///experiment/output/events')
             .config('spark.scheduler.barrier.maxConcurrentTasksCheck.interval', '2s')
             .config('spark.scheduler.barrier.maxConcurrentTasksCheck.maxFailures', '30')
             .getOrCreate())
    started = time.monotonic()
    try:
        sc = spark.sparkContext
        identities = sc.parallelize(range(2), 2).barrier().mapPartitions(executor_identity).collect()
        assert {r['private_ip'] for r in identities} == expected, identities
        assert all(r['semver_ok'] and r['spark'] == '3.5.3' for r in identities), identities
        sums = dict(sc.parallelize(range(10000), 8).map(lambda n: (n % 16, n)).reduceByKey(lambda a, b: a + b, 4).collect())
        assert sums == {k: sum(range(k, 10000, 16)) for k in range(16)}
        report = {'status': 'VERIFIED', 'scope': 'TWO_EC2_RUNTIME_AND_SHUFFLE_ONLY',
                  'app_id': sc.applicationId, 'workers': identities,
                  'input_rows': 10000, 'shuffle_groups': 16,
                  'elapsed_seconds': time.monotonic() - started,
                  'real_raw_performance_measured': False,
                  'minio_written': False, 'db_loaded': False}
        Path('/experiment/output/ec2-smoke.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(report))
    finally:
        spark.stop()


if __name__ == '__main__':
    main()
