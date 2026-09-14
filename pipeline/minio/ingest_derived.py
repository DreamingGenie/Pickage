"""Upload derived Parquet datasets to pickage-curated; verify every object by GET SHA-256.

deps.dev snapshots go through ingest_raw.py and API collector runs through
ingest_collector_raw.py, both into pickage-raw. This one takes the small
datasets that pipeline/duckdb/build_*.py computes from those originals. They
belong next to the Curated package/version output, not among the raw sources:
re-running the builder reproduces them, but only on a machine still holding the
tens of gigabytes of raw Parquet.

    python -m pipeline.minio.ingest_derived --dataset deprecated-replacement --dry-run
    python -m pipeline.minio.ingest_derived --dataset deprecated-replacement --run-id deprecated-replacement-20260914-v1
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import re
import uuid

from boto3.s3.transfer import TransferConfig
import duckdb

from pipeline.minio.ingest_raw import ROOT, client, digest, exists, put_once


BUCKET = 'pickage-curated'

# A dataset says where its Parquet is built locally, where it goes in the bucket,
# and which git README explains the columns. `notes` carries what someone holding
# only the bucket could not work out - precision, what was deliberately left out.
DATASETS = {
    'deprecated-replacement': {
        'root': 'data/deprecated_replacement',
        'prefix': 'depsdev/v1/deprecated-replacement',
        'snapshot': '2026-08-31',
        'builder': 'pipeline/duckdb/build_deprecated_dataset.py',
        'source': 'pickage-raw depsdev/v1 versions_full + pkg_project (snapshot=2026-08-31)',
        'readme': 'datasets/deprecated_replacement_260831/README.md',
        'jira': ['S15P21A506-272', 'S15P21A506-343'],
        'notes': [
            '폐기 문구에서 대체 패키지명을 정규식으로 뽑은 28,241행. 눈검사 기준 정밀도 85~90%,'
            ' replacement_confidence=high 만 쓰면 더 높다.',
            'replacement_repo_url 은 대체 패키지의 저장소 주소(24,868행). pkg_project 의'
            ' SOURCE_REPO_TYPE 매핑에서 만들었고, 매핑이 없는 334건은 원문 열만 있다.',
            '같은 내용의 CSV·JSONL 은 git datasets/deprecated_replacement_260831/ 에 있어 여기 올리지 않음.',
        ],
    },
}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dataset', choices=sorted(DATASETS), required=True)
    ap.add_argument('--snapshot', help='Source snapshot date. Default: the dataset entry')
    ap.add_argument('--run-id', default=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_')
                    + uuid.uuid4().hex[:8])
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.run_id) or not 1 <= args.workers <= 16:
        ap.error('Invalid run ID or workers (1..16)')

    spec = DATASETS[args.dataset]
    snapshot = args.snapshot or spec['snapshot']
    folder = ROOT / spec['root']
    files = sorted(folder.glob('*.parquet'))
    if not files:
        raise ValueError(f'No Parquet under {spec["root"]}: run {spec["builder"]} first')

    con = duckdb.connect()
    rows = {p.name: con.execute('SELECT sum(num_rows) FROM parquet_file_metadata(?)',
                                [str(p)]).fetchone()[0] for p in files}
    size = sum(p.stat().st_size for p in files)
    prefix = f'{spec["prefix"]}/snapshot={snapshot}/run_id={args.run_id}'
    print('RUN_ID=' + args.run_id, flush=True)
    print(f'{args.dataset}/{snapshot}: files={len(files)} bytes={size} rows={sum(rows.values())}',
          flush=True)
    for p in files:
        print(f'  {p.name}: {p.stat().st_size:,} bytes, {rows[p.name]:,} rows', flush=True)

    if not args.dry_run:
        s3 = client()
        completed = exists(s3, BUCKET, prefix + '/_SUCCESS')

        def upload(path):
            key = prefix + '/data/' + path.name
            with path.open('rb') as stream:
                checksum = digest(stream)
            if not exists(s3, BUCKET, key):
                # An already-finished run that is missing an object is not something
                # to quietly fill back in: _SUCCESS claims it was verified whole.
                if completed:
                    raise ValueError('Completed run missing object: ' + key)
                s3.upload_file(str(path), BUCKET, key,
                               ExtraArgs={'Metadata': {'sha256': checksum}},
                               Config=TransferConfig(use_threads=False))
            with s3.get_object(Bucket=BUCKET, Key=key)['Body'] as stream:
                actual = digest(stream)
            if actual != checksum:
                raise ValueError('Remote checksum mismatch: ' + key)
            return {'file': 'data/' + path.name, 'bytes': path.stat().st_size,
                    'sha256': checksum, 'rows': rows[path.name]}

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            records = list(pool.map(upload, files))
        # No upload timestamp here on purpose. put_once refuses to overwrite an
        # object whose bytes differ, so a manifest carrying the clock would make
        # re-running the same run ID fail instead of re-verifying what is there.
        result = {'contract_version': 1, 'run_id': args.run_id, 'status': 'PASSED',
                  'dataset': args.dataset, 'snapshot': snapshot,
                  'file_count': len(files), 'bytes': size, 'row_count': sum(rows.values()),
                  'verification': 'GET_SHA256_ALL_FILES',
                  'builder': spec['builder'], 'source': spec['source'],
                  'readme': spec['readme'], 'jira': spec['jira'], 'notes': spec['notes'],
                  'files': records}
        put_once(s3, BUCKET, prefix + '/run_manifest.json',
                 json.dumps(result, ensure_ascii=False, sort_keys=True).encode())
        put_once(s3, BUCKET, prefix + '/_SUCCESS', b'')

    print(json.dumps({'dataset': args.dataset, 'snapshot': snapshot, 'files': len(files),
                      'bytes': size, 'rows': sum(rows.values()), 'prefix': prefix,
                      'dry_run': args.dry_run}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
