"""Unattended, isolated real-data baseline -> weekly -> Spring DB experiment.

Source S3 only receives GET/HEAD/LIST. All writes target a dedicated localhost
MinIO. Runtime configuration and frozen code live outside the repository.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import threading
import time
import traceback
import uuid

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic(path, value):
    path = Path(path)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
    try:
        for attempt in range(6):
            try:
                os.replace(temp, path)
                return
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(0.1 * (attempt + 1))
    finally:
        temp.unlink(missing_ok=True)


def client(endpoint, user, password):
    return boto3.client('s3', endpoint_url=endpoint, aws_access_key_id=user,
                        aws_secret_access_key=password, region_name='us-east-1',
                        config=Config(connect_timeout=10, read_timeout=90,
                                      retries={'max_attempts': 4, 'mode': 'standard'},
                                      s3={'addressing_style': 'path'}))


class Experiment:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.config = json.loads((self.root / 'config.json').read_text(encoding='utf-8'))
        # Never accept a remote destination or the user's normal local MinIO.
        if self.config['destination'] not in ('http://127.0.0.1:19030', 'http://127.0.0.1:19040', 'http://127.0.0.1:19050'):
            raise ValueError('Only the dedicated local experiment MinIO is allowed')
        credentials = {}
        for line in Path(self.config['source_env']).read_text(encoding='utf-8-sig').splitlines():
            if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                credentials[key.strip()] = value.strip().strip('"').strip("'")
        self.source = client(self.config['source'], credentials['MINIO_ROOT_USER'], credentials['MINIO_ROOT_PASSWORD'])
        self.local = client(self.config['destination'], 'real914-local', 'real914-local-only')
        cache_endpoint = {'http://127.0.0.1:19040': 'http://127.0.0.1:19030',
                          'http://127.0.0.1:19050': 'http://127.0.0.1:19040'}.get(self.config['destination'])
        self.cached_raw = client(cache_endpoint, 'real914-local', 'real914-local-only') if cache_endpoint else None
        self.state = {'status': 'RUNNING', 'pid': os.getpid(), 'started_at': now(),
                      'phase': 'STARTING', 'target_snapshot': '2026-09-14',
                      'baseline_snapshot': '2026-08-31', 'server_writes': False}
        self.lock = threading.Lock()
        self.stop = threading.Event()
        timing_path = self.root / 'timings.json'
        self.timings = json.loads(timing_path.read_text()) if timing_path.exists() else []

    def update(self, **values):
        with self.lock:
            self.state.update(values, heartbeat_at=now(), free_gib=round(shutil.disk_usage(self.root).free / 2**30, 1))
            atomic(self.root / 'status.json', self.state)

    def heartbeat(self):
        while not self.stop.wait(10):
            try:
                self.update()
            except OSError as error:
                print(now(), 'HEARTBEAT_WRITE_RETRY', str(error), file=sys.stderr, flush=True)

    @contextmanager
    def phase(self, name):
        self.update(phase=name, phase_started_at=now())
        print(now(), 'START', name, flush=True)
        start = time.perf_counter()
        result = 'FAILED'
        try:
            yield
            result = 'COMPLETE'
        finally:
            record = {'phase': name, 'status': result, 'seconds': round(time.perf_counter() - start, 3), 'finished_at': now()}
            self.timings.append(record)
            atomic(self.root / 'timings.json', self.timings)
            print(json.dumps(record), flush=True)

    def inventory(self):
        path = self.root / 'inventory.json'
        if path.exists():
            return json.loads(path.read_text())
        groups = {}
        for label, snapshot, run_id, version, download in [
            ('baseline', '2026-08-31', 'bronze-20260907-v1', 'versions_full', 'downloads-278-20260909-v1'),
            ('weekly', '2026-09-14', 'bronze-weekly-20260914', 'versions_min', 'downloads-weekly-20260914')]:
            prefixes = [f'depsdev/v1/{table}/snapshot={snapshot}/run_id={run_id}/' for table in (version, 'requirements', 'projects')]
            prefixes.append(f'npm-downloads/v1/run_id={download}/')
            rows = []
            for prefix in prefixes:
                for page in self.source.get_paginator('list_objects_v2').paginate(Bucket='pickage-raw', Prefix=prefix):
                    rows.extend({'key': x['Key'], 'bytes': x['Size'], 'etag': x['ETag']} for x in page.get('Contents', []))
                keys = {r['key'] for r in rows}
                for suffix in ('run_manifest.json', '_SUCCESS'):
                    if prefix + suffix not in keys:
                        raise ValueError('Missing completed source: ' + prefix + suffix)
            groups[label] = rows
        atomic(path, groups)
        return groups

    def copy(self, label, rows):
        total = sum(row['bytes'] for row in rows)
        done = 0
        for index, row in enumerate(rows):
            key = row['key']
            self.update(copy_group=label, copy_objects_done=index, copy_objects_total=len(rows),
                        copy_bytes_done=done, copy_bytes_total=total, current_object=key)
            head = self.source.head_object(Bucket='pickage-raw', Key=key)
            if head['ETag'] != row['etag'] or head['ContentLength'] != row['bytes']:
                raise ValueError('Pinned source object changed: ' + key)
            try:
                existing = self.local.head_object(Bucket='pickage-raw', Key=key)
            except ClientError as error:
                if error.response['Error']['Code'] not in ('404', 'NoSuchKey', 'NotFound'):
                    raise
                existing = None
            if existing and existing['ContentLength'] == row['bytes'] and existing.get('Metadata', {}).get('source-etag') == row['etag'].strip('"'):
                done += row['bytes']
                continue
            if shutil.disk_usage(self.root).free < 60 * 2**30:
                raise RuntimeError('Less than 60 GiB free; stopping before next transfer')
            temporary = self.root / 'transfer.part'
            reader, read_etag = self.source, row['etag']
            if self.cached_raw is not None:
                try:
                    cached = self.cached_raw.head_object(Bucket='pickage-raw', Key=key)
                    if (cached['ContentLength'] == row['bytes'] and
                            cached.get('Metadata', {}).get('source-etag') == row['etag'].strip('"')):
                        reader, read_etag = self.cached_raw, cached['ETag']
                except ClientError as error:
                    if error.response['Error']['Code'] not in ('404', 'NoSuchKey', 'NotFound'):
                        raise
            for attempt in range(3):
                try:
                    response = reader.get_object(Bucket='pickage-raw', Key=key, IfMatch=read_etag)
                    digest = hashlib.sha256()
                    size = 0
                    with response['Body'] as body, temporary.open('wb') as output:
                        for block in iter(lambda: body.read(4 * 1024 * 1024), b''):
                            output.write(block)
                            digest.update(block)
                            size += len(block)
                    if size != row['bytes']:
                        raise ValueError('Transfer size mismatch: ' + key)
                    self.local.upload_file(str(temporary), 'pickage-raw', key,
                        ExtraArgs={'Metadata': {'source-etag': row['etag'].strip('"'), 'sha256': digest.hexdigest()}})
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    time.sleep(5 * (attempt + 1))
            temporary.unlink()
            done += row['bytes']
        self.update(copy_objects_done=len(rows), copy_bytes_done=done)

    def request(self, label):
        from pipeline.preprocessing.orchestration.weekly_request import build_request, _ref, _project_timestamp, _target_ref
        from pipeline.preprocessing.orchestration.contracts import validate_request
        path = self.root / (label + '-request.json')
        if path.exists():
            return validate_request(json.loads(path.read_text()))
        options = {'workers': 2, 'threads': 2, 'memory_limit': '4GB', 'repository_engine': 'duckdb',
                   'repository_max_temp_directory_size': '100GB'}
        baseline_id = self.config.get('baseline_run_id', 'b831')
        weekly_id = self.config.get('weekly_run_id', 'w914')
        if label == 'weekly':
            request = build_request(self.local, '2026-09-14', weekly_id, self.root / 'w', options=options)
        else:
            snapshot, run_id = '2026-08-31', 'bronze-20260907-v1'
            raw = {table: _ref(self.local, 'pickage-raw', f'depsdev/v1/{table}/snapshot={snapshot}/run_id={run_id}/run_manifest.json')
                   for table in ('versions_full', 'requirements', 'projects')}
            raw['downloads'] = _ref(self.local, 'pickage-raw', 'npm-downloads/v1/run_id=downloads-278-20260909-v1/run_manifest.json', extras={'run_id': 'downloads-278-20260909-v1'})
            project = json.loads(self.local.get_object(Bucket='pickage-raw', Key=raw['projects']['key'])['Body'].read())
            downloads = json.loads(self.local.get_object(Bucket='pickage-raw', Key=raw['downloads']['key'])['Body'].read())
            target = _target_ref(self.local, downloads, snapshot, baseline_id, self.root / 'w')
            # V1 targets are explicitly raw references; copy our locally derived
            # target bytes to local raw, without changing any source manifest.
            target_body = self.local.get_object(Bucket=target['bucket'], Key=target['key'])['Body'].read()
            target = {**target, 'bucket': 'pickage-raw', 'key': f'targets/{baseline_id}.parquet'}
            self.local.put_object(Bucket=target['bucket'], Key=target['key'], Body=target_body)
            request = {'format_version': 1, 'snapshot': snapshot, 'run_id': baseline_id, 'bronze_run_id': run_id,
                       'snapshot_timestamp': _project_timestamp(self.local, project), 'raw_refs': raw,
                       'calendar_refs': [{**raw['projects'], 'snapshot': snapshot, 'run_id': run_id}],
                       'parent': None, 'targets': {'dependents': target}, 'options': options}
        validate_request(request)
        atomic(path, request)
        return request

    def preprocess(self, label, request):
        from pipeline.preprocessing.orchestration import runner
        def execute(name, req, completed, s3, work):
            with self.phase(label + ':stage:' + name):
                return runner._default_executor(name, req, completed, s3, work)
        return runner.run(request, self.local, self.root / 'w', _executor=execute)

    def run(self):
        self.update()
        thread = threading.Thread(target=self.heartbeat, daemon=True)
        thread.start()
        try:
            for bucket in ('pickage-raw', 'pickage-curated'):
                try:
                    self.local.head_bucket(Bucket=bucket)
                except ClientError as error:
                    if error.response['Error']['Code'] not in ('404', 'NoSuchBucket', 'NotFound'):
                        raise
                    self.local.create_bucket(Bucket=bucket)
            with self.phase('PIN_INPUT_INVENTORY'):
                inventory = self.inventory()
            sys.path.insert(0, str(self.root))
            import db_setup
            db_setup.configure(self.root, self.config['destination'])
            for label in ('baseline', 'weekly'):
                with self.phase(label + ':COPY_RAW'):
                    self.copy(label, inventory[label])
                with self.phase(label + ':BUILD_REQUEST'):
                    request = self.request(label)
                with self.phase(label + ':PREPROCESS_TOTAL'):
                    self.preprocess(label, request)
                from pipeline.preprocessing.orchestration.runner import run_prefix
                prefix = run_prefix(request)
                body = self.local.get_object(Bucket='pickage-curated', Key=prefix + '/run_manifest.json')['Body'].read()
                with self.phase(label + ':SPRING_DB_LOAD'):
                    result = db_setup.load(self.root / 'src', prefix, hashlib.sha256(body).hexdigest(), label)
                    atomic(self.root / (label + '-db-result.json'), result)
            self.update(status='COMPLETE', phase='COMPLETE', finished_at=now())
        except BaseException as error:
            self.update(status='FAILED', error_type=type(error).__name__, error=str(error), finished_at=now())
            traceback.print_exc()
            raise
        finally:
            self.stop.set()
            thread.join(timeout=12)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='C:/pg914')
    args = parser.parse_args()
    root = Path(args.root)
    # Prevent accidental double starts, including starts after the chat closes.
    import msvcrt
    with (root / 'experiment.lock').open('a+b') as handle:
        handle.seek(0)
        if not handle.read(1):
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        Experiment(root).run()


if __name__ == '__main__':
    main()
