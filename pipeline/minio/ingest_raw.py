"""Upload local deps.dev snapshots unchanged; verify every object by GET SHA-256."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from pathlib import Path
import uuid

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.config import Config
from botocore.exceptions import ClientError
import duckdb

ROOT = Path(__file__).resolve().parents[2]


def digest(stream):
    h = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b''):
        h.update(block)
    return h.hexdigest()


def client():
    # PICKAGE_MINIO_ENV picks the credentials file; unset means local .env.
    # The server file points at the SSH tunnel port rather than 9000, so forgetting
    # the tunnel fails to connect instead of quietly writing to local MinIO.
    name = os.environ.get('PICKAGE_MINIO_ENV', '.env')
    path = Path(__file__).parent / name
    if Path(name).name != name or not path.is_file():
        raise SystemExit(f'MinIO credentials not found: pipeline/minio/{name}\n'
                         'Local: copy .env.example to .env\n'
                         'Server: see pipeline/minio/README.md')
    env = dict(line.split('=', 1) for line in path.read_text().splitlines()
               if line and not line.startswith('#'))
    # Not MINIO_ENDPOINT: that name belongs to init-buckets.sh, which runs inside
    # the compose network and resolves http://minio:9000. This one is a host address.
    endpoint = env.get('PICKAGE_S3_ENDPOINT', 'http://localhost:9000')
    # PICKAGE_S3_* is the name to use. MINIO_ROOT_* is the old one and still read:
    # .env / .env.server / .env.data carry it, and repository_metrics/build.py and
    # requirements_resolution/build.py open those same files by that name. Renaming
    # only here would break them; the loader file uses the new name because a scoped
    # account under a ROOT key invites reusing the root credentials (S15P21A506-385).
    access = env.get('PICKAGE_S3_ACCESS_KEY') or env.get('MINIO_ROOT_USER')
    secret = env.get('PICKAGE_S3_SECRET_KEY') or env.get('MINIO_ROOT_PASSWORD')
    if not access or not secret:
        raise SystemExit(f'MinIO credentials are empty: pipeline/minio/{name}\n'
                         'Fill PICKAGE_S3_ACCESS_KEY and PICKAGE_S3_SECRET_KEY\n'
                         'See pipeline/minio/README.md')
    # Printed so the destination is visible in every run log.
    print(f'PICKAGE_S3_ENDPOINT={endpoint} ({name})', flush=True)
    return boto3.client('s3', endpoint_url=endpoint,
                        aws_access_key_id=access,
                        aws_secret_access_key=secret,
                        region_name='us-east-1',
                        config=Config(retries={'mode': 'standard', 'max_attempts': 5},
                                      max_pool_connections=16,
                                      s3={'addressing_style': 'path'}))


def exists(s3, bucket, key):
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        if e.response['Error']['Code'] in ('404', 'NoSuchKey'):
            return False
        raise


def put_once(s3, bucket, key, body):
    if exists(s3, bucket, key):
        with s3.get_object(Bucket=bucket, Key=key)['Body'] as stream:
            if stream.read() != body:
                raise ValueError('Existing object differs: ' + key)
    else:
        s3.put_object(Bucket=bucket, Key=key, Body=body, IfNoneMatch='*')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dataset', choices=['projects', 'pkg_project', 'requirements', 'versions_full'])
    ap.add_argument('--snapshot')
    ap.add_argument('--run-id', default=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:8])
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.run_id) or not 1 <= args.workers <= 16:
        ap.error('Invalid run ID or workers (1..16)')
    sources = sorted((ROOT / 'data/raw').glob('*/snapshot=*'))
    sources = [p for p in sources if (not args.dataset or p.parent.name == args.dataset)
               and (not args.snapshot or p.name == 'snapshot=' + args.snapshot)]
    if not sources:
        raise ValueError('No source snapshots selected')
    print('RUN_ID=' + args.run_id, flush=True)
    con = duckdb.connect()
    s3 = None if args.dry_run else client()
    bucket = 'pickage-raw'
    total_files = total_bytes = total_rows = 0
    for folder in sources:
        manifest_bytes = (folder / '_MANIFEST.json').read_bytes()
        original = json.loads(manifest_bytes)
        files = sorted(folder.glob('*.parquet'))
        size = sum(p.stat().st_size for p in files)
        rows = con.execute('SELECT sum(num_rows) FROM parquet_file_metadata(?)',
                           [[str(p) for p in files]]).fetchone()[0]
        if not files or original.get('status') != 'done' or original.get('verify') != 'ok':
            raise ValueError('Source incomplete: ' + str(folder))
        for actual, expected in [(len(files), original['gcs_files']),
                                 (size, original['gcs_bytes']), (rows, original['rows'])]:
            if actual != expected:
                raise ValueError(f'Source mismatch {folder}: {actual} != {expected}')
        table = folder.parent.name
        # Projects includes multiple hosting providers, not an npm-only entity table.
        prefix = f'depsdev/v1/{table}/snapshot={original["snapshot"]}/run_id={args.run_id}'
        print(f'{table}/{folder.name}: files={len(files)} bytes={size} rows={rows}', flush=True)
        if not args.dry_run:
            completed = exists(s3, bucket, prefix + '/_SUCCESS')

            def upload(path):
                key = prefix + '/data/' + path.name
                with path.open('rb') as stream:
                    checksum = digest(stream)
                present = exists(s3, bucket, key)
                if not present:
                    if completed:
                        raise ValueError('Completed run missing object: ' + key)
                    s3.upload_file(str(path), bucket, key,
                                   ExtraArgs={'Metadata': {'sha256': checksum}},
                                   Config=TransferConfig(use_threads=False))
                with s3.get_object(Bucket=bucket, Key=key)['Body'] as stream:
                    actual = digest(stream)
                if actual != checksum:
                    raise ValueError('Remote checksum mismatch: ' + key)
                return {'key': key, 'bytes': path.stat().st_size, 'sha256': checksum}

            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                records = list(pool.map(upload, files))
            result = {'contract_version': 1, 'run_id': args.run_id, 'status': 'PASSED',
                      'table': table, 'snapshot': original['snapshot'], 'row_count': rows,
                      'file_count': len(files), 'bytes': size, 'verification': 'GET_SHA256_ALL_FILES',
                      'source_manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(),
                      'files': records}
            put_once(s3, bucket, prefix + '/source_manifest.json', manifest_bytes)
            put_once(s3, bucket, prefix + '/run_manifest.json',
                     json.dumps(result, sort_keys=True).encode())
            put_once(s3, bucket, prefix + '/_SUCCESS', b'')
        total_files += len(files)
        total_bytes += size
        total_rows += rows
    print(json.dumps({'snapshots': len(sources), 'files': total_files, 'bytes': total_bytes,
                      'rows': total_rows, 'dry_run': args.dry_run}), flush=True)


if __name__ == '__main__':
    main()
