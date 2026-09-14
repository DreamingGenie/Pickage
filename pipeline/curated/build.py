"""Build package/version Parquet from an approved local MinIO Bronze run.

Run from the project root: python -m pipeline.curated.build --help
"""
import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import tempfile
import uuid

import duckdb

from pipeline.minio.ingest_raw import client
from pipeline.curated.storage import (
    compare_and_swap_json, download_files, json_bytes, put_immutable,
    read_optional, upload_outputs, verify_files, writer_lock,
)
from pipeline.curated.transform import ValidationError, transform

ROOT = Path(__file__).resolve().parents[2]
PREFIX = 'depsdev/v1/package-version'
RAW_BUCKET = 'pickage-raw'
CURATED_BUCKET = 'pickage-curated'
CURRENT = PREFIX + '/_current.json'
LOCK = PREFIX + '/_writer.lock'
_UNPINNED_PARENT = object()


def _hash(body):
    return hashlib.sha256(body).hexdigest()


def _required(s3, bucket, key):
    obj = read_optional(s3, bucket, key)
    if obj is None:
        raise ValidationError('Required object missing: ' + key)
    return obj


def _records(records, prefix):
    if not isinstance(records, list) or not records:
        raise ValidationError('Manifest has no files')
    seen = set()
    for row in records:
        key, size, checksum = row.get('key'), row.get('bytes'), row.get('sha256')
        if (not isinstance(key, str) or not key.startswith(prefix + '/') or
                '\\' in key or any(x in ('', '.', '..') for x in key.split('/')) or
                not key.endswith('.parquet') or key in seen or
                type(size) is not int or size <= 0 or
                not isinstance(checksum, str) or not re.fullmatch('[0-9a-f]{64}', checksum)):
            raise ValidationError('Malformed file record in manifest')
        seen.add(key)
    return records


def load_bronze(s3, table, snapshot, run_id):
    prefix = f'depsdev/v1/{table}/snapshot={snapshot}/run_id={run_id}'
    if _required(s3, RAW_BUCKET, prefix + '/_SUCCESS')[0] != b'':
        raise ValidationError('Unexpected Bronze success marker')
    body = _required(s3, RAW_BUCKET, prefix + '/run_manifest.json')[0]
    manifest = json.loads(body)
    expected = {'contract_version': 1, 'status': 'PASSED', 'table': table,
                'snapshot': snapshot, 'run_id': run_id, 'verification': 'GET_SHA256_ALL_FILES'}
    if any(manifest.get(k) != v for k, v in expected.items()):
        raise ValidationError('Unapproved Bronze manifest: ' + table)
    records = _records(manifest.get('files'), prefix + '/data')
    if manifest.get('file_count') != len(records) or manifest.get('bytes') != sum(r['bytes'] for r in records):
        raise ValidationError('Bronze manifest file totals mismatch: ' + table)
    source = _required(s3, RAW_BUCKET, prefix + '/source_manifest.json')[0]
    if _hash(source) != manifest.get('source_manifest_sha256'):
        raise ValidationError('Bronze source manifest checksum mismatch: ' + table)
    original = json.loads(source)
    if (original.get('status') != 'done' or original.get('verify') != 'ok' or
            original.get('snapshot') != snapshot or original.get('table') != table or
            original.get('rows') != manifest.get('row_count') or
            original.get('gcs_files') != len(records) or
            original.get('gcs_bytes') != manifest.get('bytes')):
        raise ValidationError('Bronze source contract mismatch: ' + table)
    return manifest, {'key': prefix + '/run_manifest.json', 'sha256': _hash(body)}


def _validated_manifest(prefix, body):
    manifest = json.loads(body)
    if manifest.get('status') != 'PASSED' or manifest.get('contract_version') != 1:
        raise ValidationError('Unapproved Curated manifest')
    _records(manifest.get('files'), prefix + '/attempts')
    if not any('/package_ids/data/' in r['key'] for r in manifest['files']):
        raise ValidationError('Completed run has no ID registry')
    return manifest


def completed_run(s3, prefix):
    marker = read_optional(s3, CURATED_BUCKET, prefix + '/_SUCCESS')
    if marker is None:
        return None
    body = _required(s3, CURATED_BUCKET, prefix + '/run_manifest.json')[0]
    if json.loads(marker[0]) != {'manifest_sha256': _hash(body)}:
        raise ValidationError('Curated completion marker mismatch')
    return _validated_manifest(prefix, body), body


def _code_hash():
    h = hashlib.sha256()
    for filename in ('build.py', 'storage.py', 'transform.py', 'repository.py'):
        h.update(filename.encode())
        # Line endings do not change the transformation contract across OSes.
        h.update((Path(__file__).parent / filename).read_text(encoding='utf-8').encode())
    return h.hexdigest()


def _check_initial_registry(s3, own_prefix):
    """A missing current pointer must not silently reset an existing ID registry."""
    token = None
    while True:
        kwargs = {'Bucket': CURATED_BUCKET, 'Prefix': PREFIX + '/snapshot='}
        if token:
            kwargs['ContinuationToken'] = token
        page = s3.list_objects_v2(**kwargs)
        for row in page.get('Contents', []):
            if row['Key'].endswith('/_SUCCESS') and row['Key'] != own_prefix + '/_SUCCESS':
                raise ValidationError('Current pointer missing but completed runs exist; restore the ID lineage first')
        if not page.get('IsTruncated'):
            return
        token = page['NextContinuationToken']


def _publish_pointer(s3, prefix, manifest_body, request, old_pointer):
    new = {'run_prefix': prefix, 'manifest_sha256': _hash(manifest_body),
           'snapshot': request['snapshot']}
    current = json.loads(old_pointer[0]) if old_pointer else None
    if current == new:
        return
    if current != request['parent']:
        # A completed older run can be verified, but must not roll back current IDs.
        raise ValidationError('Current run advanced; refusing to replace its ID lineage')
    compare_and_swap_json(s3, CURATED_BUCKET, CURRENT, new,
                          old_pointer[1] if old_pointer else None)


def run(s3, snapshot, bronze_run_id, run_id, work_dir, workers=4, threads=4, memory='4GB',
        *, expected_parent=_UNPINNED_PARENT):
    """One writer, immutable attempts, last-step pointer publication; no raw writes."""
    for value in (bronze_run_id, run_id):
        if not re.fullmatch(r'[A-Za-z0-9_-]+', value):
            raise ValueError('Invalid run ID')
    if date.fromisoformat(snapshot).isoformat() != snapshot:
        raise ValueError('Expected ISO snapshot date')
    if not 1 <= workers <= 16 or not 1 <= threads <= 32:
        raise ValueError('Invalid workers/threads')
    root = Path(work_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    prefix = f'{PREFIX}/snapshot={snapshot}/run_id={run_id}'
    print(f'Curated run: {run_id}; snapshot: {snapshot}', flush=True)
    with writer_lock(s3, CURATED_BUCKET, LOCK, uuid.uuid4().hex):
        sources, fingerprints = {}, {}
        for table in ('versions_full', 'requirements'):
            sources[table], fingerprints[table] = load_bronze(s3, table, snapshot, bronze_run_id)
        old_pointer = read_optional(s3, CURATED_BUCKET, CURRENT)
        parent = json.loads(old_pointer[0]) if old_pointer else None
        if expected_parent is not _UNPINNED_PARENT and parent != expected_parent:
            own_request = read_optional(s3, CURATED_BUCKET, prefix + '/request.json')
            own_retry = (parent is not None and parent.get('run_prefix') == prefix and
                         own_request is not None and json.loads(own_request[0]).get('parent') == expected_parent)
            if not own_retry:
                raise ValidationError('Current ID parent differs from the pinned pipeline request')
        if parent is None:
            _check_initial_registry(s3, prefix)
        existing_request = read_optional(s3, CURATED_BUCKET, prefix + '/request.json')
        request = {'contract_version': 1, 'snapshot': snapshot, 'bronze_run_id': bronze_run_id,
                   'run_id': run_id, 'sources': fingerprints, 'code_sha256': _code_hash(),
                   'duckdb_version': duckdb.__version__, 'parent': parent}
        if existing_request:
            stored = json.loads(existing_request[0])
            # Retry uses its original parent even if this run is now current.
            request['parent'] = stored.get('parent')
            if stored != request:
                raise ValidationError('Run ID already belongs to different inputs/code; use a new run ID')
        else:
            put_immutable(s3, CURATED_BUCKET, prefix + '/request.json', json_bytes(request))
        done = completed_run(s3, prefix)
        if done:
            manifest, body = done
            if manifest.get('request') != request:
                raise ValidationError('Completed run request mismatch')
            print('Completed run: verifying all existing output objects', flush=True)
            verify_files(s3, CURATED_BUCKET, manifest['files'], workers=workers)
            if parent == request['parent'] or (parent and parent.get('run_prefix') == prefix):
                _publish_pointer(s3, prefix, body, request, old_pointer)
            print('Completed run verified; no data regenerated', flush=True)
            return manifest
        if parent != request['parent']:
            raise ValidationError('Previous run changed during failed run; use a new run ID')
        if parent and parent['snapshot'] > snapshot:
            raise ValidationError('Refusing to publish an older snapshot over the current run')
        prepared = read_optional(s3, CURATED_BUCKET, prefix + '/run_manifest.json')
        if prepared:
            # Recover a crash after the immutable manifest was uploaded, before
            # the completion marker/current pointer. Never overwrite that manifest.
            manifest = _validated_manifest(prefix, prepared[0])
            if manifest.get('request') != request:
                raise ValidationError('Prepared run request mismatch')
            verify_files(s3, CURATED_BUCKET, manifest['files'], workers=workers)
            put_immutable(s3, CURATED_BUCKET, prefix + '/_SUCCESS',
                          json_bytes({'manifest_sha256': _hash(prepared[0])}))
            _publish_pointer(s3, prefix, prepared[0], request, old_pointer)
            return manifest
        cache = root / 'cache'
        previous_ids = None
        if parent:
            parent_prefix = parent.get('run_prefix', '')
            if not parent_prefix.startswith(PREFIX + '/snapshot='):
                raise ValidationError('Invalid parent run prefix')
            previous = completed_run(s3, parent_prefix)
            if previous is None or _hash(previous[1]) != parent.get('manifest_sha256'):
                raise ValidationError('Previous ID mapping is not from a verified completed run')
            records = [r for r in previous[0]['files'] if '/package_ids/data/' in r['key']]
            previous_ids = download_files(s3, CURATED_BUCKET, records, cache, workers=workers)
        inputs = {}
        for table, source in sources.items():
            print(f'Input: verifying {table} ({source["file_count"]} files)', flush=True)
            inputs[table] = download_files(s3, RAW_BUCKET, source['files'], cache, workers=workers)
        attempt = uuid.uuid4().hex
        local = Path(tempfile.mkdtemp(prefix=run_id + '-', dir=root))
        output = local / 'outputs'
        with duckdb.connect(str(local / 'work.duckdb'), config={'threads': threads, 'memory_limit': memory}) as con:
            for table, files in inputs.items():
                n = con.execute('SELECT sum(num_rows) FROM parquet_file_metadata(?)',
                                [[str(p) for p in files]]).fetchone()[0]
                if n != sources[table]['row_count']:
                    raise ValidationError('Parquet row count differs from manifest: ' + table)
            report = transform(con, inputs['versions_full'], inputs['requirements'],
                               previous_ids, snapshot, output)
        print('Publishing: uploading and GET-verifying Curated files', flush=True)
        records = upload_outputs(s3, CURATED_BUCKET, prefix + '/attempts/' + attempt,
                                 output, workers=workers)
        manifest = {'contract_version': 1, 'status': 'PASSED', 'request': request,
                    'report': report, 'files': records, 'verification': 'GET_SHA256_ALL_FILES'}
        body = json_bytes(manifest)
        # No mutable pointer is touched until output validation and upload verification succeed.
        put_immutable(s3, CURATED_BUCKET, prefix + '/run_manifest.json', body)
        put_immutable(s3, CURATED_BUCKET, prefix + '/_SUCCESS',
                      json_bytes({'manifest_sha256': _hash(body)}))
        _publish_pointer(s3, prefix, body, request, old_pointer)
        print(json.dumps({'status': 'PASSED', 'run_prefix': prefix, 'report': report}, ensure_ascii=False), flush=True)
        return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', required=True)
    parser.add_argument('--bronze-run-id', required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--work-dir', type=Path, default=ROOT / 'data/curated')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--threads', type=int, default=4)
    parser.add_argument('--memory-limit', default='4GB')
    args = parser.parse_args()
    run(client(), args.snapshot, args.bronze_run_id, args.run_id, args.work_dir,
        args.workers, args.threads, args.memory_limit)


if __name__ == '__main__':
    main()
