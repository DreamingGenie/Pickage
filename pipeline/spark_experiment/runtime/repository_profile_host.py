"""Prepared data-EC2-only profiling run. --check never launches a container."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time

from . import benchmark_data_host as host
from . import weekly_priority

RUN = 'repository-profile1000-20260917-a1'
SOURCE_RUN = 'sample1000-ec2-20260916-a2'
ROOT = Path('/home/ubuntu/pickage-experiments') / RUN
SOURCE = ROOT.parent / SOURCE_RUN / 'output'
DEST = '/experiment/' + RUN
SOURCE_DEST = '/experiment/' + SOURCE_RUN
MANIFEST_SHA = '47a2cea179b368577891005102785ca801ee413b3df6e9abf9118c4bd45c11f6'


def preflight():
    if socket.gethostname() != 'ip-172-26-8-249':
        raise RuntimeError('This preparation is for the data EC2 only')
    raw = (SOURCE / 'local-manifest.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA:
        raise ValueError('Frozen manifest changed')
    manifest = json.loads(raw)
    if manifest['sample']['package_rows'] != 1000:
        raise ValueError('Wrong sample population')
    for item in manifest['input_files']:
        relative = Path(item['path']).relative_to(SOURCE_DEST)
        path = (SOURCE / relative).resolve()
        if not path.is_relative_to(SOURCE.resolve()):
            raise ValueError('Input escaped source directory')
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        if path.stat().st_size != item['bytes'] or digest.hexdigest() != item['sha256']:
            raise ValueError('Frozen input changed: ' + str(relative))
    reference = json.loads((SOURCE / 'baseline/report.json').read_bytes())
    if reference['status'] != 'COMPUTED' or reference['input_identity'] != manifest['input_identity']:
        raise ValueError('Reference run is not complete or has different inputs')
    host.command('docker', 'image', 'inspect', host.IMAGE)
    ready = json.loads((ROOT / 'prepared.json').read_bytes())
    for relative, expected in ready['code_files_sha256'].items():
        if hashlib.sha256((ROOT / 'code' / relative).read_bytes()).hexdigest() != expected:
            raise ValueError('Prepared code changed: ' + relative)
    names = host.command('docker', 'ps', '--format', '{{.Names}}').splitlines()
    allowed = {'pickage-data-mlflow-1', 'pickage-data-spark-worker-1-1',
               'pickage-data-spark-master-1', 'pickage-data-minio-1', weekly_priority.WEEKLY}
    competing = [name for name in names if name not in allowed]
    weekly = weekly_priority.observe()
    weekly_issue = weekly_priority.violation(weekly)
    free = shutil.disk_usage(ROOT).free
    return {'status': 'READY' if not competing and not weekly_issue and free >= 30 * 1024**3 else 'WAITING',
            'weekly': weekly, 'weekly_issue': weekly_issue,
            'competing_containers': competing, 'free_disk_bytes': free,
            'manifest_sha256': MANIFEST_SHA, 'input_identity': manifest['input_identity'],
            'sample': manifest['sample'], 'container_cpu_limit': 2,
            'cpu_shares': 128, 'nice': 10, 'disk_read_write_limit_mib_s_each': 32,
            'container_memory_mib': 7680, 'spark_master': 'local[2]', 'jvm_heap': '4g',
            'db_loaded': False, 'production_publication': False}


class WeeklyPrioritySupervisor(host.Supervisor):
    def __init__(self, weekly):
        super().__init__()
        self.weekly = weekly
        self.deadline = time.monotonic() + 30 * 60

    def check(self):
        super().check()
        current = weekly_priority.observe()
        issue = weekly_priority.violation(current, self.weekly)
        with (ROOT / 'weekly-guard.jsonl').open('a') as stream:
            stream.write(json.dumps(dict(current, issue=issue)) + '\n')
        self.weekly = current
        if issue:
            raise RuntimeError(issue)

    def start(self, name, cpu, memory, entry, **kwargs):
        # Bound contention while retaining local[2] and the original JVM heap.
        return super().start(name, 2, memory, ['nice', '-n', '10', *entry], **kwargs)


def run():
    check = preflight()
    if check['status'] != 'READY':
        raise RuntimeError('Experiment must wait: ' + json.dumps(check))
    if (ROOT / 'result.json').exists() or (ROOT / 'output').exists():
        raise FileExistsError('Run already started; prepare a new run directory instead of overwriting')
    if host.command('docker', 'ps', '-aq', '--filter', 'label=pickage.experiment=' + RUN):
        raise RuntimeError('Experiment container already exists')
    # Reuse the existing bounded launcher without changing its original module file.
    host.RUN, host.ROOT, host.CODE = RUN, ROOT, ROOT / 'code'
    host.OUT, host.DEST = ROOT / 'output', DEST
    supervisor = WeeklyPrioritySupervisor(check['weekly'])
    supervisor.result['resource_policy'] = check
    host.OUT.mkdir()
    host.OUT.chmod(0o777)
    (host.OUT / 'tmp').mkdir()
    (host.OUT / 'tmp').chmod(0o777)
    env = dict(os.environ, PICKAGE_EXPERIMENT_RUN=RUN, PICKAGE_GUARD_SECONDS='21600',
               PICKAGE_GUARD_PEER_HEALTH='https://j15a506.p.ssafy.io/actuator/health',
               PYTHONPATH=str(host.CODE))
    try:
        supervisor.guard = subprocess.Popen(
            ['python3', '-m', 'pipeline.spark_experiment.runtime.ec2_guard'], cwd=host.CODE, env=env,
            stdout=(ROOT / 'guard.log').open('w'), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        for _ in range(20):
            path = ROOT / 'guard.jsonl'
            if path.exists() and path.stat().st_size:
                break
            time.sleep(1)
        supervisor.check()
        entry = ['python3', '-m', 'pipeline.spark_experiment.runtime.repository_profile_entry',
                 '--manifest', SOURCE_DEST + '/local-manifest.json', '--manifest-sha256', MANIFEST_SHA,
                 '--previous-report', SOURCE_DEST + '/baseline/report.json',
                 '--output', DEST + '/profile', '--control', '/control']
        supervisor.phase('baseline', entry, [
            '--mount', f'type=bind,source={SOURCE},target={SOURCE_DEST},readonly',
            '-e', 'SPARK_LOCAL_IP=127.0.0.1', '--cpu-shares', '128',
            '--device-read-bps', '/dev/nvme0n1:32mb',
            '--device-write-bps', '/dev/nvme0n1:32mb'])
        report = json.loads((host.OUT / 'profile/repository-comparison.json').read_bytes())
        events = json.loads((host.OUT / 'profile/repository-spark-summary.json').read_bytes())
        actions = json.loads((host.OUT / 'profile/repository-actions-summary.json').read_bytes())
        if report['status'] != 'EQUAL' or events['incomplete_log'] or not events['profile_job_count'] or actions['unfinished_actions']:
            raise RuntimeError('Comparison or diagnostics incomplete')
        supervisor.result['status'] = 'COMPLETE'
    except BaseException as error:
        supervisor.result.update(status='FAILED', error={'type': type(error).__name__, 'message': str(error)})
    finally:
        errors = []
        for name in list(supervisor.owned):
            try:
                supervisor.finish(name)
            except Exception as error:
                errors.append(str(error))
        (ROOT / 'guard.done').touch()
        if supervisor.guard:
            try:
                supervisor.guard.wait(timeout=15)
            except subprocess.TimeoutExpired:
                supervisor.guard.terminate()
        supervisor.result.update(finished_at=time.time(), cleanup_errors=errors)
        if errors:
            supervisor.result['status'] = 'FAILED'
        host.save(ROOT / 'result.json', supervisor.result)
        host.save(ROOT / 'status.json', supervisor.result)
    return 0 if supervisor.result['status'] == 'COMPLETE' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.check:
        print(json.dumps(preflight(), indent=2))
        return 0
    return run()


if __name__ == '__main__':
    raise SystemExit(main())
