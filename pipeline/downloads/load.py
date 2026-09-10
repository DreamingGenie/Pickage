"""Validate existing npm downloads and publish a verified immutable MinIO run."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
import uuid

from pipeline.minio.ingest_raw import client, digest
from .input import discover_source, inspect_source
from .lineage import inspect_lineage
from .bronze import publish


ROOT = Path(__file__).resolve().parents[2]
SAFE_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}')


def encoded(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def contract_sha256() -> str:
    paths = [p for p in Path(__file__).parent.glob('*.py') if not p.name.startswith('test_')]
    paths.append(ROOT / 'pipeline/minio/ingest_raw.py')
    checksum = hashlib.sha256(b'npm-downloads-bronze-v1\0')
    for path in sorted(paths):
        checksum.update(path.relative_to(ROOT).as_posix().encode() + b'\0')
        checksum.update(path.read_text(encoding='utf-8').encode() + b'\0')
    return checksum.hexdigest()


def unchanged(root: Path, manifest: dict) -> None:
    """Recheck the selected file set and bytes immediately before publication."""
    discovered = discover_source(root, manifest['source_run'], manifest['target_name'])
    expected = sorted((f['path'], f['role']) for f in manifest['files'])
    actual = sorted((f['path'], f['role']) for f in discovered['files'])
    if actual != expected or discovered['excluded'] != manifest['excluded']:
        raise ValueError('source inventory changed during validation or upload')
    for record in manifest['files']:
        path = root / record['path']
        with path.open('rb') as stream:
            checksum = digest(stream)
        if path.stat().st_size != record['bytes'] or checksum != record['sha256']:
            raise ValueError('source content changed: ' + record['path'])


def build_manifest(root: Path, source_run: str, target_name: str, run_id: str) -> dict:
    prepared = inspect_source(root, source_run, target_name)
    lineage = inspect_lineage(root, prepared['files'], source_run)
    raw_stats = {record['path']: record for record in lineage['raw_files']}
    expected_raw = {record['path'] for record in prepared['files'] if record['role'] == 'raw_response'}
    if set(raw_stats) != expected_raw or len(raw_stats) != len(lineage['raw_files']):
        raise ValueError('raw response statistics do not cover the selected input files')
    for record in prepared['files']:
        if record['role'] == 'raw_response':
            stats = raw_stats[record['path']]
            for field in ('row_count', 'min_date', 'max_date'):
                record[field] = stats[field]
            record.pop('statistics_unavailable_reason', None)
            record.pop('statistics_note', None)
    manifest = {**prepared, 'run_id': run_id, 'contract_sha256': contract_sha256(), 'lineage': lineage,
                'required_remote_verification': 'GET_SHA256_ALL_FILES'}
    unchanged(root, manifest)
    return manifest


def write_report(path: Path, report: dict) -> None:
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def run(source_root: Path, source_run: str, run_id: str, work_dir: Path, *,
        target_name: str = 'targets_top100k_20260902.csv', verify_only: bool = False,
        s3=None, bucket: str = 'pickage-raw', failpoint: str | None = None) -> dict:
    if not isinstance(run_id, str) or not SAFE_ID.fullmatch(run_id):
        raise ValueError('invalid Bronze run ID')
    if not isinstance(source_run, str) or not SAFE_ID.fullmatch(source_run):
        raise ValueError('invalid source run ID')
    source_root = source_root.resolve(strict=True)
    work_dir = work_dir.resolve()
    if work_dir == source_root or source_root in work_dir.parents:
        raise ValueError('execution artifacts must be outside the source directory')
    attempt_id = uuid.uuid4().hex
    run_dir = work_dir / run_id
    if run_dir.is_symlink() or (run_dir.exists() and not run_dir.is_dir()):
        raise ValueError('run artifact path must be a normal directory')
    if run_dir.resolve().parent != work_dir:
        raise ValueError('run artifact path escapes the work directory')
    attempt_dir = run_dir / attempt_id
    attempt_dir.mkdir(parents=True, exist_ok=False)
    report_path = attempt_dir / 'execution_report.json'
    started = time.monotonic()
    report = {'dataset': 'npm-downloads', 'run_id': run_id, 'source_run': source_run,
              'attempt_id': attempt_id, 'status': 'PREPARING', 'phase': 'VALIDATE_INPUT',
              'mode': 'VERIFY_ONLY' if verify_only else 'INGEST',
              'started_at': datetime.now(timezone.utc).isoformat(), 'report_path': str(report_path)}
    write_report(report_path, report)
    try:
        manifest = build_manifest(source_root, source_run, target_name, run_id)
        manifest_bytes = encoded(manifest)
        manifest_path = attempt_dir / 'input-manifest.json'
        manifest_path.write_bytes(manifest_bytes)
        report.update(manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
                      manifest_path=str(manifest_path), contract_sha256=manifest['contract_sha256'],
                      file_count=len(manifest['files']), input_bytes=sum(f['bytes'] for f in manifest['files']),
                      quality=manifest['quality'], lineage=manifest['lineage']['summary'])
        if verify_only:
            report.update(status='VERIFIED', action='VERIFIED_LOCAL')
        else:
            report['phase'] = 'PUBLISH_BRONZE'
            write_report(report_path, report)
            prefix = f'npm-downloads/v1/run_id={run_id}'
            result = publish(client() if s3 is None else s3, bucket=bucket, prefix=prefix,
                             root=source_root, manifest=manifest, failpoint=failpoint,
                             before_commit=lambda: unchanged(source_root, manifest))
            report.update(result)
            report.update(bucket=bucket, prefix=prefix)
        report['phase'] = 'COMPLETE'
    except BaseException as error:
        report.update(status='FAILED', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        report.update(finished_at=datetime.now(timezone.utc).isoformat(),
                      elapsed_seconds=round(time.monotonic() - started, 3))
        write_report(report_path, report)
        print(f"{report['status']}: {report_path}", flush=True)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--source-run', required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--target-name', default='targets_top100k_20260902.csv')
    parser.add_argument('--work-dir', type=Path, default=ROOT / 'data/downloads/executions')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    try:
        run(args.source_root, args.source_run, args.run_id, args.work_dir,
            target_name=args.target_name, verify_only=args.verify_only)
    except Exception as error:
        print(f'Ingest failed ({type(error).__name__}); see the execution report for details', flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
