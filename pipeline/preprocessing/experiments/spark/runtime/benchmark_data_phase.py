"""Guarded data-host phases around the shared-input two-EC2 benchmark."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time

RUN = 'sample1000-ec2-20260916-a2'
ROOT = Path('/experiment') / RUN
PREFIX = 'experiments/' + RUN
BUCKET = 'pickage-curated'
TRANSFER_MIB_PER_SECOND = 16


def client():
    import boto3
    from botocore.config import Config
    return boto3.client('s3', endpoint_url='http://172.26.8.249:9000', region_name='us-east-1',
                        config=Config(connect_timeout=5, read_timeout=60,
                                      retries={'max_attempts': 2}, s3={'addressing_style': 'path'}))


def remap(value, paths):
    if isinstance(value, dict):
        return {k: remap(v, paths) for k, v in value.items()}
    if isinstance(value, list):
        return [remap(v, paths) for v in value]
    return paths.get(value, value) if isinstance(value, str) else value


def write_json(path, value):
    with path.open('x', encoding='utf-8') as out:
        json.dump(value, out, indent=2, default=str)


def shared_input_key(record):
    # Both downloads engines validate the Hive date against the physical date.
    match = re.search(r'(?:^|/)date=(\d{4}-\d{2}-\d{2})(?:/|$)', Path(record['path']).as_posix())
    partition = 'date=' + match.group(1) + '/' if match else ''
    return PREFIX + '/inputs/' + partition + record['sha256'] + Path(record['path']).suffix


class RateLimit:
    """Enforce an average transfer ceiling with at most one read-chunk burst."""
    def __init__(self, mib_per_second=TRANSFER_MIB_PER_SECOND):
        if type(mib_per_second) is not int or not 1 <= mib_per_second <= 50:
            raise ValueError('Transfer rate must be 1..50 MiB/s')
        self.rate = mib_per_second * 1024**2
        self.started = time.monotonic()
        self.bytes = 0

    def account(self, size):
        self.bytes += size
        delay = self.bytes / self.rate - (time.monotonic() - self.started)
        if delay > 0:
            time.sleep(delay)


def prepare():
    from pipeline.preprocessing.experiments.spark.runtime.sample_stage_inputs import sample_manifest
    from pipeline.preprocessing.experiments.spark.job import code_sha
    from boto3.s3.transfer import TransferConfig
    began = time.monotonic()
    source = Path('/source-manifest.json')
    if hashlib.sha256(source.read_bytes()).hexdigest() != '4d5005e4c5cd4e7fa77df7b2ef736007c05b118dc7d5ca1b513b606335735713':
        raise ValueError('Pinned full-input manifest changed')
    manifest_path = sample_manifest(source, ROOT / 'prepared', code_sha(), limit=1000)
    manifest = json.loads(Path(manifest_path).read_bytes())
    import duckdb
    from pipeline.preprocessing.package_snapshot.build import validate_inputs
    with duckdb.connect(config={'memory_limit': '1GB', 'threads': 1}) as con:
        validate_inputs(con, manifest['stages']['package_snapshot'])
    print('SAMPLE_SNAPSHOT_INPUTS_VALIDATED', flush=True)
    # Path remapping is transport-only. Keep the adapter identity, which pins
    # source manifests and the benchmark code identity as well as input bytes.
    write_json(ROOT / 'local-manifest.json', manifest)
    s3 = client()
    s3.put_object(Bucket=BUCKET, Key=PREFIX + '/_CLAIM.json',
                  Body=json.dumps({'run_id': RUN, 'input_identity': manifest['input_identity']}).encode(),
                  IfNoneMatch='*')
    frozen = json.loads(Path('/frozen/raw-inputs.json').read_bytes())
    reusable = {(f['sha256'], f['bytes']): f['shared_uri'] for f in frozen['input_files']}
    paths, transferred = {}, {}
    cfg = TransferConfig(max_concurrency=1, use_threads=False, multipart_chunksize=8*1024**2,
                         max_bandwidth=TRANSFER_MIB_PER_SECOND*1024**2)
    for i, f in enumerate(manifest['input_files']):
        identity = (f['sha256'], f['bytes'])
        if identity in reusable:
            uri = reusable[identity]
            _, _, bucket, key = uri.split('/', 3)
            if s3.head_object(Bucket=bucket, Key=key)['ContentLength'] != f['bytes']:
                raise ValueError('Frozen shared input size changed')
        else:
            if identity not in transferred:
                key = shared_input_key(f)
                s3.upload_file(f['path'], BUCKET, key, Config=cfg)
                if s3.head_object(Bucket=BUCKET, Key=key)['ContentLength'] != f['bytes']:
                    raise ValueError('Uploaded input size differs')
                transferred[identity] = 's3a://' + BUCKET + '/' + key
            uri = transferred[identity]
        paths[f['path']] = uri
        if (i+1) % 25 == 0:
            print('INPUT_SHARED', i+1, len(manifest['input_files']), flush=True)
    shared = remap(manifest, paths)
    payload = json.dumps(shared, sort_keys=True).encode()
    s3.put_object(Bucket=BUCKET, Key=PREFIX+'/manifest.json', Body=payload, IfNoneMatch='*')
    write_json(ROOT/'shared-manifest.json', shared)
    write_json(ROOT/'prepare-result.json', {'status': 'READY', 'seconds': time.monotonic()-began,
        'input_identity': manifest['input_identity'], 'file_count': len(paths),
        'new_uploaded_bytes': sum(k[1] for k in transferred),
        'upload_rate_limit_mib_per_second': TRANSFER_MIB_PER_SECOND,
        'stages': list(manifest['stages']), 'sample': manifest.get('sample')})


def baseline():
    from pipeline.preprocessing.experiments.spark.job import main as job
    os.environ['PYSPARK_SUBMIT_ARGS'] = '--driver-memory 4g pyspark-shell'
    return job(['--manifest', str(ROOT/'local-manifest.json'), '--engine', 'baseline',
                '--output', str(ROOT/'baseline'), '--telemetry-dir', str(ROOT/'baseline-telemetry'),
                '--threads', '2', '--memory', '4GB', '--partitions', '16'])


def compare():
    from pipeline.preprocessing.experiments.spark.runtime.bounded_compare import compare as exact_compare
    from pipeline.preprocessing.experiments.spark.job import GROUPS
    baseline_report = json.loads((ROOT/'baseline/report.json').read_bytes())
    spark_report = json.loads((ROOT/'telemetry/report-with-telemetry.json').read_bytes())
    cluster = json.loads((ROOT/'cluster-summary.json').read_bytes())
    if cluster.get('status') != 'COMPUTED':
        raise ValueError('Distributed execution was not verified')
    s3 = client()
    destination = ROOT / 'spark-results'
    destination.mkdir(exist_ok=False)
    limiter = RateLimit()
    source_prefix = PREFIX+'/spark-output/'
    for page in s3.get_paginator('list_objects_v2').paginate(Bucket=BUCKET, Prefix=source_prefix):
        for item in page.get('Contents', []):
            key = item['Key']
            if not key.endswith('.parquet'):
                continue
            relative = key[len(source_prefix):]
            if any(p in ('', '.', '..') for p in relative.split('/')):
                raise ValueError('Unsafe result key')
            path = destination / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as out:
                body = s3.get_object(Bucket=BUCKET, Key=key)['Body']
                try:
                    for chunk in iter(lambda: body.read(1024**2), b''):
                        out.write(chunk)
                        limiter.account(len(chunk))
                finally:
                    body.close()
            if path.stat().st_size != item['Size']:
                raise ValueError('Downloaded output differs in size')
    spark_local = copy.deepcopy(spark_report)
    for stage in spark_local['stages']:
        spark_local['stages'][stage]['output'] = str(destination/stage)
    result = exact_compare(baseline_report, spark_local, ROOT/'comparison')
    write_json(ROOT/'comparison-result.json', result)
    if result['status'] != 'EQUAL':
        raise ValueError('Baseline and Spark outputs differ')
    write_json(ROOT/'benchmark-result.json', {'status': 'VERIFIED', 'comparison': result,
        'sample': json.loads((ROOT/'local-manifest.json').read_bytes()).get('sample'),
        'baseline_stage_seconds': {k: v['seconds'] for k,v in baseline_report['stages'].items()},
        'spark_stage_seconds': {k: v['seconds'] for k,v in spark_report['stages'].items()},
        'result_download_bytes': limiter.bytes,
        'result_download_rate_limit_mib_per_second': TRANSFER_MIB_PER_SECOND,
        'input_identity': baseline_report['input_identity'], 'repetitions': 1,
        'scope': 'FIXED_STAGE_INPUT_TWO_EC2_COMPARISON', 'db_loaded': False,
        'production_publication': False})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=('prepare', 'baseline', 'compare'))
    args = parser.parse_args()
    from pipeline.preprocessing.experiments.spark.runtime.repository_retry_entry import wait_for_start, fresh_control
    control = Path('/control')
    wait_for_start(control)
    def watch():
        while True:
            if not fresh_control(control):
                os._exit(70)
            time.sleep(3)
    threading.Thread(target=watch, daemon=True).start()
    print('BENCHMARK_PHASE_STARTED', args.phase, flush=True)
    return {'prepare': prepare, 'baseline': baseline, 'compare': compare}[args.phase]()


if __name__ == '__main__':
    main()
