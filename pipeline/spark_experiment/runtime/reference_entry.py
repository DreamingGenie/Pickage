"""Container entry: wait for host monitors, then compute offline reference inputs."""
import json
import os
from pathlib import Path
import threading
import time


def fresh_control(root):
    state = json.loads((root / 'supervisor-heartbeat.json').read_text())
    return time.time() - state['time'] < 25


def main():
    control = Path('/control')
    deadline = time.monotonic() + 90
    while not (control / 'start.signal').exists():
        if time.monotonic() > deadline:
            raise RuntimeError('Host monitors did not become ready')
        time.sleep(1)
    if not fresh_control(control):
        raise RuntimeError('Host supervisor is not fresh')

    def watch():
        while True:
            try:
                if not fresh_control(control):
                    raise RuntimeError('stale supervisor')
            except Exception:
                print('REFERENCE_ABORT: supervisor heartbeat unavailable', flush=True)
                os._exit(70)
            time.sleep(3)

    threading.Thread(target=watch, daemon=True).start()
    # Existing resolver discovery expects npm next to the Node executable.
    # This link is inside the disposable container; neither host nor image changes.
    alias = Path('/usr/local/bin/node_modules')
    if not alias.exists():
        alias.symlink_to('/usr/local/lib/node_modules', target_is_directory=True)
    from pipeline.requirements_resolution.bridge import discover_runtime
    discover_runtime()
    events = Path('/experiment/events')
    events.mkdir(exist_ok=False)
    os.environ['PYSPARK_SUBMIT_ARGS'] = (
        '--conf spark.eventLog.enabled=true --conf spark.eventLog.compress=false '
        '--conf spark.eventLog.rolling.enabled=false '
        '--conf spark.eventLog.dir=file:///experiment/events pyspark-shell')
    from pipeline.spark_experiment.__main__ import main as prepare
    print('REFERENCE_STARTED', time.time(), flush=True)
    return prepare(['prepare-frozen', '--manifest', '/frozen/raw-inputs.json',
                    '--work-dir', '/experiment/reference'])


if __name__ == '__main__':
    raise SystemExit(main())
