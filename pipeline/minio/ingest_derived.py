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
    'migration-pairs-dev': {
        'root': 'data/migration_pairs_dev',
        # deps.dev 가 아니라 npm registry 수집분에서 나온 것이라 npm-registry/v1 아래에 둔다
        # (원본 수집분은 ingest_collector_raw.py 가 같은 접두사에 넣는다).
        'prefix': 'npm-registry/v1/migration-pairs-dev',
        # 이 모듈의 경로는 snapshot= 을 쓴다. 여기 값은 deps.dev 스냅샷이 아니라
        # 원천이 된 registry 수집 실행 날짜다(collected_date 와 같은 뜻).
        'snapshot': '2026-09-09',
        'builder': 'pipeline/duckdb/build_migration_pairs.py --source registry --kind dev',
        'source': 'pickage-raw npm-registry/v1 collected_date=2026-09-09 (의존 선언·발행시각) '
                  '+ depsdev/v1 versions_full snapshot=2026-08-31 (source_repo 만, publisher 판정용)',
        'readme': 'datasets/migration_pairs_dev_260914/README.md',
        'jira': ['S15P21A506-280', 'S15P21A506-349', 'S15P21A506-136'],
        'notes': [
            '개발용 의존(devDependencies) 기준 이동쌍. 실행용 의존 기준 결과는 같은 버킷의'
            ' depsdev/v1/migration-pairs/ 에 있다. 모집단이 달라(상위 10만 vs npm 전수)'
            ' 두 결과의 수치를 더하거나 lift 를 비교하면 안 된다.',
            '모집단은 다운로드 순위 상위 10만이다. 그 밖의 패키지가 도구를 어떻게 바꿨는지는 알 수 없다.',
            '제거 판정에서 같은 전이의 Dependencies·Peer·Optional 로 옮겨진 이름은 재분류로 보고 뺐다(27,732건).',
            '쌍 CSV 3종(strict 766·recommended 506·all 6,770)과 재분류 정정 측정 결과는'
            ' git datasets/migration_pairs_dev_260914/ 에 있어 여기 올리지 않음.',
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
