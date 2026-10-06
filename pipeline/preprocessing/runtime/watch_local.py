"""Record a local container's events without repeatedly polling its process.

The container emits one resource sample per minute. This consumer blocks on
Docker's log stream and preserves a compact status file for the operator.
"""
import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re
import subprocess
from datetime import datetime, timezone


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--container', required=True)
    parser.add_argument('--evidence-dir', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'pickage-bounded-[a-z0-9-]+', args.container):
        raise ValueError('Expected an explicitly named bounded experiment container')
    root = args.evidence_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    state = {'status': 'RUNNING', 'phase': 'STARTING', 'container': args.container}
    target = root / 'status.json'

    def save():
        state['updated_at'] = datetime.now(timezone.utc).isoformat()
        temporary = target.with_suffix('.tmp')
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(target)

    logger = logging.getLogger('bounded-local')
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(root / 'pipeline.log', maxBytes=10_000_000,
                                  backupCount=2, encoding='utf-8')
    logger.addHandler(handler)
    save()
    try:
        with subprocess.Popen(['docker', 'logs', '--follow', args.container],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', errors='replace') as process:
            for line in process.stdout:
                logger.info(line.rstrip())
                if not line.startswith('{'):
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get('event') == 'PIPELINE_RESOURCES':
                    state.update(event)
                elif event.get('event') == 'PIPELINE_FAILED':
                    state.update(status='FAILED', error=event)
                elif event.get('event') == 'PIPELINE_COMPLETE':
                    state.update(status='CURATED_COMPLETE', phase='CURATED_COMPLETE')
                else:
                    continue
                save()
            if process.wait() != 0:
                raise RuntimeError('Docker log stream failed; inspect the container directly')
        result = subprocess.run(['docker', 'wait', args.container], capture_output=True,
                                text=True, check=True)
        state['exit_code'] = int(result.stdout.strip())
        state['status'] = 'CURATED_COMPLETE' if state['exit_code'] == 0 else 'FAILED'
        state['db_loaded'] = False
        save()
    except Exception as error:
        state.update(status='MONITOR_FAILED', error=str(error))
        save()
        raise
    finally:
        handler.close()


if __name__ == '__main__':
    main()
