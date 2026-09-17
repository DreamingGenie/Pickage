"""Short-lived guard: only containers bearing this run label can be stopped."""
import json
import os
import re
import socket
import subprocess
import time
from pathlib import Path
from urllib.request import urlopen

RUN = os.environ.get('PICKAGE_EXPERIMENT_RUN', 'ec2-runtime-20260915-a1')
if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', RUN):
    raise ValueError('Invalid experiment run label')
ROOT = Path('/home/ubuntu/pickage-experiments') / RUN


def docker(*args):
    return subprocess.check_output(['docker', *args], text=True, timeout=10)


def stop_own():
    ids = docker('ps', '-q', '--filter', 'label=pickage.experiment=' + RUN).split()
    if ids:
        docker('stop', '--time', '5', *ids)


def main():
    app = socket.gethostname().endswith('6-235')
    url = 'http://127.0.0.1:8080/actuator/health' if app else 'http://127.0.0.1:9000/minio/health/live'
    initial = json.loads(docker('inspect', *docker('ps', '-q').split()))
    original = {d['Id']: d['RestartCount'] for d in initial
                if (d['Config'].get('Labels') or {}).get('pickage.experiment') != RUN}
    duration = int(os.environ.get('PICKAGE_GUARD_SECONDS', '600'))
    if not 60 <= duration <= 86400:
        raise ValueError('Guard duration must be 60..86400 seconds')
    deadline = time.monotonic() + duration
    failures = 0
    reason = 'TIME_LIMIT'
    with (ROOT / 'guard.jsonl').open('w') as out:
        try:
            while time.monotonic() < deadline:
                if (ROOT / 'guard.done').exists():
                    reason = 'FINISHED'
                    break
                mem = {line.split(':')[0]: int(line.split()[1])*1024
                       for line in Path('/proc/meminfo').read_text().splitlines()}
                observed = {'time': time.time(), 'available_memory_bytes': mem['MemAvailable']}
                issue = None
                try:
                    t = time.monotonic()
                    with urlopen(url, timeout=2) as response:
                        body = response.read()
                    observed['service_seconds'] = time.monotonic() - t
                    if app and json.loads(body).get('status') != 'UP':
                        issue = 'SERVICE_NOT_UP'
                    if observed['service_seconds'] > 1:
                        issue = 'SERVICE_RESPONSE_OVER_1S'
                    peer = os.environ.get('PICKAGE_GUARD_PEER_HEALTH')
                    if peer:
                        t = time.monotonic()
                        with urlopen(peer, timeout=2) as response:
                            peer_body = json.load(response)
                        observed['peer_service_seconds'] = time.monotonic() - t
                        if peer_body.get('status') != 'UP' or observed['peer_service_seconds'] > 1:
                            issue = 'PEER_SERVICE_UNHEALTHY_OR_SLOW'
                    for d in json.loads(docker('inspect', *original)):
                        if not d['State']['Running'] or d['RestartCount'] != original[d['Id']]:
                            issue = 'EXISTING_CONTAINER_CHANGED'
                        if d['State'].get('Health', {}).get('Status') == 'unhealthy':
                            issue = 'EXISTING_CONTAINER_UNHEALTHY'
                    if not app:
                        with urlopen('http://172.26.8.249:8080/json/', timeout=2) as response:
                            prod = json.load(response)
                        if prod.get('activeapps') or prod.get('activedrivers'):
                            issue = 'PRODUCTION_SPARK_JOB_STARTED'
                except Exception as error:
                    issue = type(error).__name__
                failures = failures + 1 if issue else 0
                observed['issue'] = issue
                observed['consecutive_issues'] = failures
                out.write(json.dumps(observed) + '\n'); out.flush()
                if mem['MemAvailable'] < 4 * 1024**3 or failures >= 3:
                    reason = 'MEMORY_BELOW_4G' if mem['MemAvailable'] < 4 * 1024**3 else issue
                    break
                time.sleep(2)
        finally:
            stop_own()
            (ROOT / 'guard-result.json').write_text(json.dumps({'reason': reason, 'run': RUN}))


if __name__ == '__main__':
    main()
