"""Upload local collector runs unchanged; verify every object by GET SHA-256.

deps.dev snapshots go through ingest_raw.py. This handles the API collectors,
whose runs share one shape: data/<source>/raw/run=<date>/ holding gzipped JSONL
parts next to the collector's own manifest.json.

    python -m pipeline.minio.ingest_collector_raw --source keywords --dry-run
    python -m pipeline.minio.ingest_collector_raw --source keywords --run-id keywords-20260909-v1
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import re
import uuid

from boto3.s3.transfer import TransferConfig

from pipeline.minio.ingest_raw import ROOT, client, digest, exists, put_once


# Both check the counters are actually present. Reading them as absent-means-fine
# would let an unrecognised manifest shape pass as a complete collection.
def keywords_done(manifest):
    planned, done = manifest.get('pages_planned'), manifest.get('pages_done')
    return bool(planned) and planned == done, f'pages {done}/{planned}'


def registry_done(manifest):
    status = manifest.get('tasks_by_status') or {}
    pending = status.get('pending', 0)
    return bool(status) and pending == 0, f'tasks {status} pending={pending}'


# A collector's manifest reports progress in its own terms, so completeness is
# per source. `final` alone is not enough: it is written on every checkpoint.
SOURCES = {
    'keywords': {'root': 'data/keywords/raw', 'prefix': 'ecosystems-keywords/v1',
                 'done': keywords_done},
    'registry': {'root': 'data/registry/raw', 'prefix': 'npm-registry/v1',
                 'done': registry_done},
}

BUCKET = 'pickage-raw'

# Collector runs sit next to smoke runs (run=smoke-2026-09-08) in one directory.
# Sweeping "everything" would publish trial data into the bucket that holds
# collection originals, so a sweep takes dated runs only.
DATED_RUN = re.compile(r'run=\d{4}-\d{2}-\d{2}')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source', choices=sorted(SOURCES), required=True)
    ap.add_argument('--run', help='Collector run date, e.g. 2026-09-08. Default: every run found')
    ap.add_argument('--run-id', default=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_')
                    + uuid.uuid4().hex[:8])
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.run_id) or not 1 <= args.workers <= 16:
        ap.error('Invalid run ID or workers (1..16)')
    source = SOURCES[args.source]
    folders = sorted((ROOT / source['root']).glob('run=*'))
    if args.run:
        folders = [p for p in folders if p.name == 'run=' + args.run]
    else:
        folders = [p for p in folders if DATED_RUN.fullmatch(p.name)]
    if not folders:
        raise ValueError('No collector runs selected under ' + source['root'])
    print('RUN_ID=' + args.run_id, flush=True)
    s3 = None if args.dry_run else client()
    total_files = total_bytes = 0
    for folder in folders:
        manifest_bytes = (folder / 'manifest.json').read_bytes()
        original = json.loads(manifest_bytes)
        # Only the collected payload. The checkpoint DB and logs are the
        # collector's working state, not source data, and they keep changing.
        files = sorted(folder.glob('part-*.jsonl.gz'))
        size = sum(p.stat().st_size for p in files)
        complete, detail = source['done'](original)
        run = folder.name.removeprefix('run=')
        if not files:
            raise ValueError('Source has no parts: ' + str(folder))
        if original.get('run') != run:
            raise ValueError(f'Manifest run {original.get("run")!r} != folder {run!r}')
        # A partial run must never be published: _SUCCESS would later read as a
        # verified complete original, and nothing downstream would question it.
        if not original.get('final') or not complete:
            raise ValueError(f'Collection incomplete {folder}: final={original.get("final")} {detail}')
        prefix = f'{source["prefix"]}/collected_date={run}/run_id={args.run_id}'
        print(f'{args.source}/{run}: files={len(files)} bytes={size} {detail}', flush=True)
        if not args.dry_run:
            completed = exists(s3, BUCKET, prefix + '/_SUCCESS')

            def upload(path):
                key = prefix + '/data/' + path.name
                with path.open('rb') as stream:
                    checksum = digest(stream)
                if not exists(s3, BUCKET, key):
                    if completed:
                        raise ValueError('Completed run missing object: ' + key)
                    s3.upload_file(str(path), BUCKET, key,
                                   ExtraArgs={'Metadata': {'sha256': checksum}},
                                   Config=TransferConfig(use_threads=False))
                with s3.get_object(Bucket=BUCKET, Key=key)['Body'] as stream:
                    actual = digest(stream)
                if actual != checksum:
                    raise ValueError('Remote checksum mismatch: ' + key)
                return {'key': key, 'bytes': path.stat().st_size, 'sha256': checksum}

            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                records = list(pool.map(upload, files))
            result = {'contract_version': 1, 'run_id': args.run_id, 'status': 'PASSED',
                      'source': args.source, 'collected_date': run,
                      'file_count': len(files), 'bytes': size,
                      'verification': 'GET_SHA256_ALL_FILES',
                      'source_manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(),
                      'files': records}
            put_once(s3, BUCKET, prefix + '/source_manifest.json', manifest_bytes)
            put_once(s3, BUCKET, prefix + '/run_manifest.json',
                     json.dumps(result, sort_keys=True).encode())
            put_once(s3, BUCKET, prefix + '/_SUCCESS', b'')
        total_files += len(files)
        total_bytes += size
    print(json.dumps({'source': args.source, 'runs': len(folders), 'files': total_files,
                      'bytes': total_bytes, 'dry_run': args.dry_run}), flush=True)


if __name__ == '__main__':
    main()
