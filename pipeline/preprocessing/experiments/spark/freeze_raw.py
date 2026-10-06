"""Freeze producer-approved raw bytes only; never execute preprocessing."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import time

from pipeline.preprocessing.curated.build import load_bronze
from pipeline.preprocessing.curated.storage import json_bytes
from pipeline.preprocessing.downloads_interval.input import _bronze
from pipeline.preprocessing.orchestration.contracts import validate_request


def sha(body):
    return hashlib.sha256(body).hexdigest()


def safe_key(key):
    if (not isinstance(key, str) or not key or '\\' in key or '\x00' in key or ':' in key
            or PurePosixPath(key).is_absolute() or PurePosixPath(key).as_posix() != key
            or any(p in ('', '.', '..') for p in key.split('/'))):
        raise ValueError('Unsafe object key')
    return key


class MetadataReads:
    def __init__(self, source):
        self.source, self.bodies = source, {}

    def get_object(self, *, Bucket, Key):
        identity = (Bucket, Key)
        if identity not in self.bodies:
            stream = self.source.get_object(Bucket=Bucket, Key=Key)['Body']
            try:
                self.bodies[identity] = stream.read()
            finally:
                stream.close()
        body = self.bodies[identity]
        return {'Body': io.BytesIO(body), 'ContentLength': len(body)}


def plan_raw(s3, request):
    request = validate_request(request)
    if request['parent'] is not None:
        raise ValueError('This raw-only freeze supports the selected bootstrap scenario only')
    cache = MetadataReads(s3)
    records = {}

    def add(bucket, key, size, checksum):
        safe_key(key)
        if bucket != 'pickage-raw' or type(size) is not int or size < 0 or not re.fullmatch('[0-9a-f]{64}', checksum):
            raise ValueError('Invalid pinned object')
        row = {'bucket': bucket, 'key': key, 'bytes': size, 'sha256': checksum}
        old = records.setdefault((bucket, key), row)
        if old != row:
            raise ValueError('Conflicting pinned object')

    refs = [(name, request['snapshot'], request['bronze_run_id'], request['raw_refs'][name])
            for name in ('versions_full', 'requirements')]
    refs += [('projects', r['snapshot'], r['run_id'], r) for r in request['calendar_refs']]
    for table, snapshot, run, ref in refs:
        manifest, verified = load_bronze(cache, table, snapshot, run)
        if verified['key'] != ref['key'] or verified['sha256'] != ref['sha256']:
            raise ValueError('Pinned Bronze manifest differs')
        for row in manifest['files']:
            add('pickage-raw', row['key'], row['bytes'], row['sha256'])
    downloads = request['raw_refs']['downloads']
    manifest, prefix = _bronze(cache, downloads['run_id'], downloads['sha256'])
    for row in manifest['files']:
        add('pickage-raw', prefix + '/data/' + safe_key(row['path']), row['bytes'], row['sha256'])
    target = request['targets']['dependents']
    target_size = s3.head_object(Bucket=target['bucket'], Key=target['key'])['ContentLength']
    add(target['bucket'], target['key'], target_size, target['sha256'])
    for (bucket, key), body in cache.bodies.items():
        add(bucket, key, len(body), sha(body))
    files = sorted(records.values(), key=lambda r: (r['bucket'], r['key']))
    return {'format_version': 1, 'scope': 'RAW_ONLY_NO_PREPROCESSING', 'source_request': request,
            'objects': files, 'file_count': len(files), 'bytes': sum(r['bytes'] for r in files),
            'input_identity': sha(json_bytes({'request': request, 'objects': files}))}


class TransferBudget:
    def __init__(self, mib_per_second):
        if not 1 <= mib_per_second <= 50:
            raise ValueError('Transfer cap must be 1..50 MiB/s')
        self.rate, self.started, self.bytes = mib_per_second * 1024**2, time.monotonic(), 0

    def account(self, size):
        self.bytes += size
        delay = self.bytes / self.rate - (time.monotonic() - self.started)
        if delay > 0:
            time.sleep(delay)


def freeze(s3, request, root, prefix, *, mib_per_second=30, check=lambda: None):
    safe_key(prefix)
    if not re.fullmatch(r'experiments/[A-Za-z0-9_-]+/inputs', prefix):
        raise ValueError('Only a dedicated experiment input prefix is allowed')
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=False)
    plan = plan_raw(s3, request)
    (root / 'plan.json').write_bytes(json_bytes(plan))
    bucket = 'pickage-curated'
    check()
    # Unique run ownership: retries use a new prefix, never overwrite previous copies.
    s3.put_object(Bucket=bucket, Key=prefix + '/_CLAIM.json', Body=json_bytes(plan), IfNoneMatch='*')
    budget = TransferBudget(mib_per_second)
    files, started = [], time.monotonic()
    for n, record in enumerate(plan['objects'], 1):
        check()
        source = {k: record[k] for k in ('bucket', 'key')}
        relative = 'objects/' + source['bucket'] + '/' + source['key']
        destination = prefix + '/' + relative
        info = s3.head_object(Bucket=source['bucket'], Key=source['key'])
        if info['ContentLength'] != record['bytes']:
            raise ValueError('Source size changed')
        # S3 copies original bytes directly; a later GET validates the copied bytes
        # against the producer SHA and writes the baseline's identical local file.
        s3.copy_object(Bucket=bucket, Key=destination,
                       CopySource={'Bucket': source['bucket'], 'Key': source['key']},
                       CopySourceIfMatch=info['ETag'])
        budget.account(record['bytes'])
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        digest, size = hashlib.sha256(), 0
        result = s3.get_object(Bucket=bucket, Key=destination)
        try:
            with path.open('xb') as output:
                for chunk in iter(lambda: result['Body'].read(1024**2), b''):
                    check()
                    digest.update(chunk); size += len(chunk); output.write(chunk)
                    budget.account(len(chunk))
        finally:
            result['Body'].close()
        if size != record['bytes'] or digest.hexdigest() != record['sha256']:
            raise ValueError('Copied object SHA/size differs: ' + record['key'])
        files.append({**record, 'path': str(path), 'relative_path': relative,
                      'shared_uri': f's3a://{bucket}/{destination}'})
        if n % 25 == 0 or n == plan['file_count']:
            progress = {'objects_verified': n, 'objects_total': plan['file_count'],
                        'verified_bytes': sum(f['bytes'] for f in files), 'elapsed_s': time.monotonic()-started}
            (root / 'progress.json').write_bytes(json_bytes(progress))
            print(json.dumps(progress), flush=True)
    # Inspect only Projects footer statistics; do not read/transform their rows.
    import duckdb
    from pipeline.preprocessing.snapshot.projects import _inspect_file
    from pipeline.preprocessing.snapshot.policy import parse_timestamp
    projects = []
    with duckdb.connect(config={'threads': 1, 'memory_limit': '256MB'}) as con:
        for f in files:
            if f['key'].startswith('depsdev/v1/projects/') and f['key'].endswith('.parquet'):
                observed = _inspect_file(con, Path(f['path']), root)
                if '/snapshot=' + request['snapshot'] + '/' in f['key']:
                    if parse_timestamp(observed['snapshot_timestamp']) != parse_timestamp(request['snapshot_timestamp']):
                        raise ValueError('Selected snapshot timestamp differs from raw Projects')
                projects.append(observed)
    frozen = {**plan, 'status': 'VERIFIED', 'input_files': files, 'shared_prefix': f's3a://{bucket}/{prefix}',
              'verification': 'COPIED_OBJECT_GET_SHA256_AND_LOCAL_SAME_BYTES', 'projects_metadata': projects,
              'transfer_budget_mib_per_second': mib_per_second, 'elapsed_seconds': time.monotonic()-started,
              'all_five_stage_inputs_ready': False, 'preprocessing_executed': False, 'db_loaded': False,
              'production_publication': False}
    body = json_bytes(frozen)
    check()
    s3.put_object(Bucket=bucket, Key=prefix+'/raw-inputs.json', Body=body, IfNoneMatch='*')
    remote = s3.get_object(Bucket=bucket, Key=prefix+'/raw-inputs.json')['Body']
    try:
        if remote.read() != body:
            raise ValueError('Frozen manifest upload differs')
    finally:
        remote.close()
    (root/'raw-inputs.json').write_bytes(body)
    return frozen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--prefix', required=True)
    parser.add_argument('--mib-per-second', type=int, default=30)
    parser.add_argument('--guard-root', type=Path, required=True)
    args = parser.parse_args()
    import boto3
    from botocore.config import Config
    client = boto3.client('s3', endpoint_url=os.environ['PICKAGE_S3_ENDPOINT'],
                          region_name='us-east-1', config=Config(connect_timeout=5, read_timeout=30,
                          retries={'max_attempts': 2}, s3={'addressing_style': 'path'}))
    last_check = [0.0]
    def healthy():
        if time.monotonic() - last_check[0] < 1:
            return
        if (args.guard_root/'guard-result.json').exists():
            raise RuntimeError('Service guard ended; stop preparation')
        points = (args.guard_root/'guard.jsonl').read_text().splitlines()
        latest = json.loads(points[-1])
        if time.time()-latest['time'] > 20 or latest['issue'] is not None:
            raise RuntimeError('Service guard is stale or unhealthy')
        last_check[0] = time.monotonic()
    result = freeze(client, json.loads(args.request.read_bytes()), args.root, args.prefix,
                    mib_per_second=args.mib_per_second, check=healthy)
    print(json.dumps({k: result[k] for k in ('status', 'file_count', 'bytes', 'input_identity', 'shared_prefix')}))


if __name__ == '__main__':
    main()
