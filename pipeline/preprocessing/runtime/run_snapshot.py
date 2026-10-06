"""Execute one pinned request inside the kernel-limited scratch filesystem."""
import argparse
import json
import os
from pathlib import Path
import tempfile

import boto3
from botocore.config import Config

from pipeline.preprocessing.orchestration.runner import run
from pipeline.preprocessing.runtime.resource_events import resource_events


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--recover-repository', action='store_true',
                        help='Explicitly retain verified earlier stages under a separate recovery receipt')
    parser.add_argument('--recover-dependents', action='store_true',
                        help='Recover only dependents from five verified stage checkpoints')
    args = parser.parse_args()
    root = Path(os.environ['BOUNDED_WORKSPACE']).resolve()
    limit = int(os.environ['BOUNDED_SCRATCH_LIMIT_BYTES'])
    if not root.is_dir() or not 0 < limit <= 28_000_000_000:
        raise ValueError('A kernel-limited owned workspace is required')
    temporary = root / 'tmp'
    temporary.mkdir(exist_ok=True)
    os.environ['TMPDIR'] = str(temporary)
    tempfile.tempdir = str(temporary)
    request = json.loads(args.request.read_text())
    if request.get('options', {}).get('work_cleanup') != 'stage':
        raise ValueError('Bounded execution requires stage cleanup')
    s3 = boto3.client('s3', endpoint_url=os.environ['PICKAGE_BOUNDED_S3_ENDPOINT'],
        aws_access_key_id=os.environ['PICKAGE_BOUNDED_S3_ACCESS_KEY'],
        aws_secret_access_key=os.environ['PICKAGE_BOUNDED_S3_SECRET_KEY'],
        region_name='us-east-1', config=Config(s3={'addressing_style': 'path'},
            retries={'max_attempts': 4, 'mode': 'standard'}, connect_timeout=10, read_timeout=90))
    with resource_events(root, root / 'work', request['run_id'], limit):
        try:
            if args.recover_repository and args.recover_dependents:
                raise ValueError('Recovery mode flags are mutually exclusive')
            if args.recover_dependents:
                from pipeline.preprocessing.runtime.recover_dependents import recover
                bundle = recover(request, s3, root / 'work')
            elif args.recover_repository:
                from pipeline.preprocessing.runtime.recover_repository import recover
                bundle = recover(request, s3, root / 'work')
            else:
                bundle = run(request, s3, root / 'work')
            print(json.dumps({'event': 'PIPELINE_COMPLETE', 'run_id': request['run_id'],
                'snapshot': request['snapshot'], 'stages': list(bundle['stages'])}), flush=True)
        except BaseException as error:
            print(json.dumps({'event': 'PIPELINE_FAILED', 'run_id': request['run_id'],
                'error_type': type(error).__name__, 'error': str(error)}), flush=True)
            raise


if __name__ == '__main__':
    main()
