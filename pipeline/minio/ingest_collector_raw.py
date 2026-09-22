"""Upload local collector runs unchanged; verify every object by GET SHA-256.

deps.dev snapshots go through ingest_raw.py. This handles the API collectors,
whose runs share one shape: data/<source>/raw/run=<date>/ holding gzipped JSONL
parts next to the collector's own manifest.json.

    python -m pipeline.minio.ingest_collector_raw --source keywords --dry-run
    python -m pipeline.minio.ingest_collector_raw --source keywords --run-id keywords-20260909-v1

A run may be split across shards (registry 4분할 수집, S15P21A506-366): run=<date>-s1 … -sN.
Those are one collection, so they go under one collected_date=<date> with the shard kept in the
object path (data/shard=sN/part-*.jsonl.gz). An unsharded run keeps the old layout byte for byte.
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
# 샤드 회차는 날짜와 -sN 사이에 라벨을 둘 수 있다 — run=2026-09-22-additions-s1
# (S15P21A506-452). 같은 날 회차가 둘 이상이거나 어떤 대상을 받았는지 폴더 이름으로
# 구분하려는 것이다. **collected_date 는 여전히 앞의 날짜다.** 적재기의 파티션 검증이 날짜만
# 받고, 라벨까지 파티션에 넣으면 같은 날 수집분이 버킷에서 갈라진다.
# 라벨을 허용하기 전에는 그런 폴더가 DATED_RUN·SHARD_RUN 어느 쪽에도 안 걸려 네 개가 통째로
# 빠졌고, 입고가 'No collector runs selected' 로 끝났다.
# smoke run 은 날짜가 앞에 없어(run=smoke-2026-09-08) 여기 걸리지 않는다. 그대로다.
SHARD_RUN = re.compile(r'run=(\d{4}-\d{2}-\d{2})(?:-[A-Za-z0-9]+)*-s(\d+)')
# 샤드 수는 대상 CSV 이름이 말해 준다 (rank_top100k_20260902-s1of4.csv). 폴더가 몇 개 있는지로
# 판단하면 s3 폴더를 빠뜨린 채 올려도 통과한다 — 원본의 1/4 이 빠진 것을 _SUCCESS 가 덮는다.
SHARD_TARGETS = re.compile(r'-s(\d+)of(\d+)\.csv$')


def shard_of(folder_name):
    """폴더 이름 → (collected_date, 샤드 번호 또는 None)."""
    m = SHARD_RUN.fullmatch(folder_name)
    if m:
        return m.group(1), int(m.group(2))
    return folder_name.removeprefix('run='), None


def shard_total(manifest):
    """수집기 manifest 의 targets 경로에서 전체 샤드 수를 읽는다. 모르면 None."""
    name = (manifest.get('targets') or '').replace(chr(92), '/').rsplit('/', 1)[-1]
    m = SHARD_TARGETS.search(name)
    return int(m.group(2)) if m else None


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
    folders = [p for p in folders
               if DATED_RUN.fullmatch(p.name) or SHARD_RUN.fullmatch(p.name)]
    if args.run:
        # 날짜를 주면 그 날짜의 단일 run 이든 샤드 전부든 잡는다. 샤드 하나만 따로 올리면
        # 그 collected_date 에 _SUCCESS 가 찍혀 1/N 짜리 원본이 완전한 것으로 보인다.
        folders = [p for p in folders if shard_of(p.name)[0] == args.run]
    if not folders:
        raise ValueError('No collector runs selected under ' + source['root'])
    groups = {}
    for p in folders:
        groups.setdefault(shard_of(p.name)[0], []).append(p)
    print('RUN_ID=' + args.run_id, flush=True)
    s3 = None if args.dry_run else client()
    total_files = total_bytes = 0
    for collected_date, members in sorted(groups.items()):
        # members = [(샤드 번호 또는 None, 폴더, manifest 바이트, manifest)]
        # 섞임 검사를 정렬보다 먼저 한다. None 과 int 를 같이 정렬하면 TypeError 로 죽어서
        # "샤드와 단일이 섞였다" 가 아니라 파이썬 내부 오류만 보인다.
        indexes = [shard_of(f.name)[1] for f in members]
        if None in indexes and any(i is not None for i in indexes):
            raise ValueError(f'{collected_date}: 샤드 run 과 단일 run 이 섞여 있다 — '
                             + ', '.join(sorted(f.name for f in members)))
        sharded = indexes[0] is not None
        members = sorted(((i, f, (f / 'manifest.json').read_bytes())
                          for i, f in zip(indexes, members)), key=lambda t: t[0] or 0)
        members = [(idx, f, raw, json.loads(raw)) for idx, f, raw in members]
        files = []            # [(샤드 번호 또는 None, 경로)]
        details = []
        for idx, folder, _, original in members:
            parts = sorted(folder.glob('part-*.jsonl.gz'))
            complete, detail = source['done'](original)
            run = folder.name.removeprefix('run=')
            details.append(detail)
            if not parts:
                raise ValueError('Source has no parts: ' + str(folder))
            if original.get('run') != run:
                raise ValueError(f'Manifest run {original.get("run")!r} != folder {run!r}')
            # A partial run must never be published: _SUCCESS would later read as a
            # verified complete original, and nothing downstream would question it.
            if not original.get('final') or not complete:
                raise ValueError(f'Collection incomplete {folder}: final={original.get("final")} {detail}')
            files += [(idx, p) for p in parts]
        if sharded:
            # 샤드가 하나라도 빠지면 그만큼의 원본이 통째로 없는 채 완료 표시가 찍힌다.
            totals = {shard_total(o) for *_, o in members}
            if totals != {len(members)} or None in totals:
                raise ValueError(f'{collected_date}: 샤드 {sorted(i for i, *_ in members)} 가 있는데 '
                                 f'대상 CSV 는 전체 {totals} 개라고 한다')
            if sorted(i for i, *_ in members) != list(range(1, len(members) + 1)):
                raise ValueError(f'{collected_date}: 샤드 번호가 1..N 이 아니다')
        size = sum(p.stat().st_size for _, p in files)
        detail = ' | '.join(details)
        prefix = f'{source["prefix"]}/collected_date={collected_date}/run_id={args.run_id}'
        print(f'{args.source}/{collected_date}: shards={len(members) if sharded else 1} '
              f'files={len(files)} bytes={size} {detail}', flush=True)
        if not args.dry_run:
            completed = exists(s3, BUCKET, prefix + '/_SUCCESS')

            def upload(item):
                idx, path = item
                key = prefix + ('/data/' if idx is None else f'/data/shard=s{idx}/') + path.name
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
                      'source': args.source, 'collected_date': collected_date,
                      'file_count': len(files), 'bytes': size,
                      'verification': 'GET_SHA256_ALL_FILES',
                      'files': records}
            # 수집기 manifest 는 바꾸지 않고 그대로 올린다. 샤드는 원본이 넷이므로 합성하지 않고
            # 넷을 각각 보존한다 — 합쳐 쓰면 어느 샤드가 무엇을 받았는지 되돌릴 수 없다.
            if sharded:
                result['shards'] = len(members)
                result['source_manifest_sha256'] = {
                    f's{idx}': hashlib.sha256(raw).hexdigest() for idx, _, raw, _ in members}
                for idx, _, raw, _ in members:
                    put_once(s3, BUCKET, prefix + f'/source_manifest/shard=s{idx}.json', raw)
            else:
                result['source_manifest_sha256'] = hashlib.sha256(members[0][2]).hexdigest()
                put_once(s3, BUCKET, prefix + '/source_manifest.json', members[0][2])
            put_once(s3, BUCKET, prefix + '/run_manifest.json',
                     json.dumps(result, sort_keys=True).encode())
            put_once(s3, BUCKET, prefix + '/_SUCCESS', b'')
        total_files += len(files)
        total_bytes += size
    print(json.dumps({'source': args.source, 'runs': len(groups), 'files': total_files,
                      'bytes': total_bytes, 'dry_run': args.dry_run}), flush=True)


if __name__ == '__main__':
    main()
