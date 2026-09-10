"""Freeze complete historical inputs against approved remote manifests."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from pipeline.curated.build import load_bronze
from pipeline.downloads.bronze import _read, _file_hash
from pipeline.postgresql.input import select_run
from pipeline.snapshot.input import read_candidate
from .history_policy import policy_document, policy_sha256
from .policy import canonical_bytes


def _required(s3, bucket, key):
    body = _read(s3, bucket, key)
    if body is None:
        raise ValueError('missing approved object: ' + key)
    return body


def _inside(root, relative):
    root = Path(root).resolve()
    if not isinstance(relative, str) or '\\' in relative or ':' in relative:
        raise ValueError('unsafe input path')
    parts = relative.split('/')
    if any(p in ('', '.', '..') for p in parts):
        raise ValueError('unsafe input path')
    path = root.joinpath(*parts)
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
        raise ValueError('missing or unsafe local input: ' + str(path))
    return path


def _verify_file(rec):
    path = Path(rec['local_path'])
    before = path.stat()
    size, digest = _file_hash(path)
    after = path.stat()
    if (size != rec['bytes'] or digest != rec['sha256'] or
            (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns)):
        raise ValueError('input changed or SHA differs: ' + str(path))
    return {**rec, 'mtime_ns': after.st_mtime_ns}


def revalidate_files(records, workers=4):
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(_verify_file, records))


def prepare(config, work_dir, s3, *, workers=4):
    """Use explicit run IDs and paths; publish nothing and never select latest."""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    base = config['population']
    population = select_run(s3, base['snapshot'], base['run_id'])
    if population['manifest_sha256'] != base['manifest_sha256']:
        raise ValueError('base population manifest changed')
    candidate = read_candidate(Path(config['candidate_path']))
    if candidate['candidate_sha256'] != config['candidate_sha256']:
        raise ValueError('candidate SHA mismatch')
    calendar = candidate['calendar']
    if not calendar or calendar[-1]['snapshot_at'] != base['snapshot']:
        raise ValueError('base population must anchor the end of the calendar')
    records, package_files = [], []
    for rec in population['_service_records']['package']:
        rel = rec['key'].split('/attempts/', 1)[1].split('/', 1)[1]
        path = _inside(config['curated_output_root'], rel)
        records.append({**rec, 'bucket': 'pickage-curated', 'role': 'package', 'local_path': str(path)})
        package_files.append(str(path))

    rp = config['repository']
    prefix = f"depsdev/v1/repository-metrics/snapshot={base['snapshot']}/run_id={rp['run_id']}"
    raw = _required(s3, 'pickage-curated', prefix + '/run_manifest.json')
    rmanifest = json.loads(raw)
    if (hashlib.sha256(raw).hexdigest() != rp['manifest_sha256'] or
            json.loads(_required(s3, 'pickage-curated', prefix + '/_SUCCESS')) !=
            {'manifest_sha256': rp['manifest_sha256']} or rmanifest.get('status') != 'PASSED' or
            rmanifest['input']['curated_manifest_sha256'] != base['manifest_sha256'] or
            rmanifest['input']['candidate_sha256'] != config['candidate_sha256']):
        raise ValueError('repository source is not the approved base input')
    candidate_files = []
    selected = [r for r in rmanifest['files'] if r['dataset'] == 'quality/candidates']
    if sum(r['rows'] for r in selected) != population['counts']['version']:
        raise ValueError('candidate population does not cover approved versions')
    for rec in selected:
        path = _inside(config['repository_local_root'], rec['path'])
        records.append({'key': prefix + '/' + rec['path'], 'bytes': rec['bytes'], 'sha256': rec['sha256'],
                        'bucket': 'pickage-curated', 'role': 'candidate', 'local_path': str(path)})
        candidate_files.append(str(path))

    projects, project_manifests = {}, {}
    def project_input(interval):
        day = interval['snapshot_at']
        run = config['projects_runs'][day]
        manifest, identity = load_bronze(s3, 'projects', day, run)
        found = []
        for rec in manifest['files']:
            name = rec['key'].split('/data/', 1)[1]
            path = _inside(config['projects_root'], 'snapshot=' + day + '/' + name)
            found.append({**rec, 'bucket': 'pickage-raw', 'role': 'projects', 'snapshot': day,
                          'local_path': str(path)})
        return day, found, {**identity, 'run_id': run, 'rows': manifest['row_count']}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for day, found, identity in pool.map(project_input, calendar):
            projects[day] = [r['local_path'] for r in found]
            project_manifests[day] = identity
            records.extend(found)

    download = config['downloads']
    dp = 'npm-downloads/v1/run_id=' + download['run_id']
    raw = _required(s3, 'pickage-raw', dp + '/run_manifest.json')
    if (hashlib.sha256(raw).hexdigest() != download['manifest_sha256'] or
            _required(s3, 'pickage-raw', dp + '/_SUCCESS') != (download['manifest_sha256'] + '\n').encode()):
        raise ValueError('download Bronze approval changed')
    dmanifest = json.loads(raw)
    daily, target, status = {}, [], []
    for rec in dmanifest['files']:
        role = rec.get('role')
        if role not in ('daily_parquet', 'target_csv', 'status_parquet'):
            continue
        path = _inside(config['downloads_root'], rec['path'])
        records.append({'bucket': 'pickage-raw', 'key': dp + '/data/' + rec['path'],
                        'bytes': rec['bytes'], 'sha256': rec['sha256'], 'local_path': str(path), 'role': role})
        if role == 'daily_parquet':
            match = re.search(r'(?:^|/)date=(\d{4}-\d{2}-\d{2})(?:/|$)', rec['path'])
            if not match:
                raise ValueError('daily file lacks an explicit date partition')
            daily.setdefault(match.group(1), []).append(str(path))
        elif role == 'target_csv':
            target.append(str(path))
        else:
            status.append(str(path))
    if len(target) != 1 or len(status) != 1 or not daily:
        raise ValueError('incomplete download input roles')
    keys = [(r['bucket'], r['key']) for r in records]
    if len(set(keys)) != len(keys):
        raise ValueError('duplicate source object')
    print(json.dumps({'phase': 'VERIFY_INPUT_SHA', 'files': len(records)}), flush=True)
    verified = revalidate_files(records, workers)
    # Only stable identities contribute to the hash. Paths and mtime are local verification evidence.
    stable_files = [{k: v for k, v in r.items() if k not in ('local_path', 'mtime_ns')} for r in verified]
    identity = {
        'format_version': 1, 'dataset': 'package-snapshot-history-input', 'policy': policy_document(),
        'policy_sha256': policy_sha256(),
        'population': {**base, 'snapshot_timestamp': population['snapshot_timestamp'],
                       'run_prefix': population['run_prefix'], 'counts': population['counts']},
        'repository': {**rp, 'run_prefix': prefix}, 'downloads': {**download, 'run_prefix': dp},
        'candidate': {'sha256': config['candidate_sha256']}, 'calendar': calendar,
        'projects': project_manifests, 'files': stable_files,
    }
    digest = hashlib.sha256(canonical_bytes(identity)).hexdigest()
    prepared = {'input_sha256': digest, 'input_manifest': identity, 'package_files': package_files,
                'candidate_files': candidate_files, 'project_files': projects, 'daily_files': daily,
                'target_file': target[0], 'status_file': status[0], 'available_start': min(daily),
                'available_end': max(daily), 'calendar': calendar, 'verified_files': verified,
                'verified_at': datetime.now(timezone.utc).isoformat(),
                'verification': 'LOCAL_FULL_SHA_MATCHES_PINNED_APPROVED_REMOTE_MANIFESTS'}
    existing = work_dir / 'prepared.json'
    if existing.exists() and json.loads(existing.read_text(encoding='utf-8'))['input_sha256'] != digest:
        raise ValueError('history work directory belongs to a different immutable input')
    existing.write_text(json.dumps(prepared, ensure_ascii=False, indent=2), encoding='utf-8')
    (work_dir / 'input-manifest.json').write_bytes(canonical_bytes(identity))
    return prepared
