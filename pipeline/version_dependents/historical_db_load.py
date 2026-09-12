"""H7 full-key preflight and atomic, resumable daily PostgreSQL publication."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time
import uuid

from pipeline.requirements_resolution.input import file_sha256
from pipeline.requirements_resolution.policy import sha256
from .historical_artifact import _publish_json, _path
from .historical_job import _status
from .artifact import _reject_reparse_ancestors
from .historical_db_source import FullSource
from .historical_db_keys import verify_keys
from .historical_db_publish import HistoricalCountLoader


def contract():
    paths = [Path(__file__).with_name(n) for n in ('historical_db_load.py', 'historical_db_source.py',
             'historical_db_keys.py', 'historical_db_publish.py', 'historical_db_prepare.py')]
    paths.append(Path(__file__).parents[1]/'postgresql/postgres.py')
    return {p.name: file_sha256(p) for p in paths}


def publish_date(command, work_dir, metadata, files, execution_id, generation, recheck, failpoint=None):
    def before_commit():
        if contract() != generation:
            raise ValueError('Loader code changed during execution')
        recheck()
        for r in metadata['manifest']['files']:
            path = files[r['role']]
            if file_sha256(path) != r['sha256'] or path.stat().st_size != r['bytes']:
                raise ValueError('COPY source changed during publication')
    with HistoricalCountLoader(command, work_dir) as database:
        try:
            database.start(metadata, execution_id, sha256(generation), uuid.uuid4().hex)
            return database.publish(files, failpoint=failpoint, before_commit=before_commit)
        except BaseException as error:
            database.fail(error)
            raise


def load(*, run_dir, manifest_sha256, output, command, publish=False, dates=None, execution_prefix='vd193'):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,120}', execution_prefix):
        raise ValueError('Invalid execution prefix')
    root, source_root = _path(output), _path(run_dir)
    _reject_reparse_ancestors(root)
    prepared = _path(json.loads((source_root/'input_location.json').read_bytes())['prepared_dir'])
    for protected in (source_root.parent, prepared):
        if root.is_relative_to(protected) or protected.is_relative_to(root):
            raise ValueError('Load output overlaps the preserved calculation')
    generation = contract()
    plan = {'source_run_dir': str(source_root), 'source_run_manifest_sha256': manifest_sha256,
            'db_command': command, 'dates': sorted(dates) if dates is not None else None,
            'execution_prefix': execution_prefix, 'contract': generation}
    root.mkdir(parents=True, exist_ok=True)
    plan_path = root/'load-plan.json'
    if plan_path.exists():
        if json.loads(plan_path.read_bytes()) != plan:
            raise ValueError('Resume plan differs from its original source, target, dates or code')
    else:
        _publish_json(plan_path, plan)
    attempt = root/('attempt-'+uuid.uuid4().hex)
    started = time.monotonic()
    def event(phase, **fields):
        state = {'at':datetime.now(timezone.utc).isoformat(),'phase':phase,**fields}
        with (root/'progress.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(state)+'\n')
        _status(root/'status.json', state)
    event('SOURCE_OPEN', publish=publish)
    source = None
    try:
        source = FullSource(source_root,manifest_sha256,attempt)
        chosen = [r['snapshot_at'] for r in source.calendar] if dates is None else sorted(dates)
        if (not chosen or len(set(chosen)) != len(chosen)
                or not set(chosen) <= {r['snapshot_at'] for r in source.calendar}):
            raise ValueError('Specify unique dates from the source calendar')
        event('KEY_VALIDATION', **source.expected)
        report = verify_keys(command,attempt,source.identity_file,source.version_file,
                             source.calendar,source.lineage,source.expected)
        source.recheck()
        _publish_json(attempt/'key-verification.json',report)
        event('KEYS_VERIFIED', **source.expected)
        results=[]
        if publish:
            for day in chosen:
                event('PREPARE_DATE', snapshot=day)
                metadata,files=source.prepare_date(day)
                # Source hash prevents accidentally resuming another calculation under the same prefix.
                execution_id=f'{execution_prefix}-{manifest_sha256[:16]}-{day.replace("-", "")}'
                result=publish_date(command,attempt,metadata,files,execution_id,generation,source.recheck)
                results.append({'snapshot':day,**result})
                _publish_json(attempt/(day+'.json'), {'metadata':metadata,'result':result})
                event('DATE_VERIFIED', snapshot=day,action=result['action'])
        result={'status':'PUBLISHED' if publish else 'KEYS_VERIFIED',
                'scope':'FULL_CALENDAR' if len(chosen)==len(source.calendar) else 'SELECTED_DATES',
                'resolution_status':'PARTIAL','source_ready_for_load':False,
                'elapsed_seconds':time.monotonic()-started,'key_verification':report,
                'dates':results,'attempt_dir':str(attempt),'source_run_manifest_sha256':manifest_sha256}
        _publish_json(attempt/'result.json',result)
        _status(root/'result.json',result)
        event('COMPLETE',status=result['status'])
        return result
    except BaseException as error:
        event('FAILED',error=str(error))
        raise
    finally:
        if source is not None:
            source.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',required=True)
    parser.add_argument('--manifest-sha256',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--container',required=True)
    parser.add_argument('--database',required=True)
    parser.add_argument('--user',default='postgres')
    parser.add_argument('--publish',action='store_true',help='Write dates atomically; default only validates keys')
    parser.add_argument('--date',action='append',dest='dates')
    parser.add_argument('--execution-prefix',default='vd193')
    args=parser.parse_args()
    result=load(run_dir=args.run_dir,manifest_sha256=args.manifest_sha256,output=args.output,
                command=['docker','exec','-i',args.container,'psql','-U',args.user,'-d',args.database],
                publish=args.publish,dates=args.dates,execution_prefix=args.execution_prefix)
    print(json.dumps({k:v for k,v in result.items() if k not in ('dates','key_verification')},ensure_ascii=False))


if __name__=='__main__':
    main()
