"""One bounded reference run on the data host; survives SSH disconnection."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

RUN = os.environ.get('PICKAGE_EXPERIMENT_RUN', 'reference-20260915-a2')
if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', RUN):
    raise ValueError('Invalid experiment run label')
MODE = os.environ.get('PICKAGE_REFERENCE_MODE', 'reference')
if MODE not in ('reference', 'repository-retry'):
    raise ValueError('Unknown reference mode')
ROOT = Path('/home/ubuntu/pickage-experiments') / RUN
PREVIOUS = Path('/home/ubuntu/pickage-experiments/reference-20260915-a2')
FROZEN = Path('/home/ubuntu/pickage-experiments/raw-freeze-20260915-b1/payload/frozen')
IMAGE = 'sha256:e3ca9ccf92c2c9fa0022920acab1713e6d35a0529e5ab6ac4f0a38428f955479'
MANIFEST_SHA = 'f5408949993f6e2f2c53edab74e8c30848aa98db1a1843ff6b89f1868a0b0de7'
SECONDS = 6 * 3600


def command(*args):
    return subprocess.check_output(args, text=True, timeout=20).strip()


def save(name, value):
    temp = ROOT / (name + '.tmp')
    temp.write_text(json.dumps(value, indent=2))
    temp.replace(ROOT / name)


def stop_reason(now, heartbeat_time, disk_free, guard_alive, monitor_alive):
    if not guard_alive:
        return 'SERVICE_GUARD_EXITED'
    if not monitor_alive:
        return 'RESOURCE_MONITOR_EXITED'
    if now - heartbeat_time > 20:
        return 'SERVICE_GUARD_STALE'
    if disk_free < 30 * 1024**3:
        return 'DISK_FREE_BELOW_30_GIB'
    return None


def computation_complete(output, mode):
    if mode == 'reference':
        return (output / 'reference/experiment.json').is_file()
    report = output / 'repository-retry/report.json'
    return report.is_file() and json.loads(report.read_text()).get('status') == 'COMPUTED'


def main():
    import hashlib
    assert hashlib.sha256((FROZEN / 'raw-inputs.json').read_bytes()).hexdigest() == MANIFEST_SHA
    assert shutil.disk_usage(ROOT).free > 90 * 1024**3
    assert not (ROOT / 'result.json').exists()
    assert not command('docker', 'ps', '-aq', '--filter', 'label=pickage.experiment=' + RUN)
    retry = MODE == 'repository-retry'
    memory = '7680m' if retry else '5632m'
    output = ROOT / 'output'
    output.mkdir(exist_ok=False)
    # cap-drop ALL also removes root's DAC override: the container must have
    # explicit write permission on these host-user-owned experiment directories.
    output.chmod(0o777)
    scratch = output / 'tmp'
    scratch.mkdir()
    scratch.chmod(0o777)
    env = {**os.environ, 'PICKAGE_EXPERIMENT_RUN': RUN, 'PICKAGE_GUARD_SECONDS': str(SECONDS),
           'PICKAGE_GUARD_PEER_HEALTH': 'https://j15a506.p.ssafy.io/actuator/health',
           'PYTHONPATH': str(ROOT / 'code')}
    guard = monitor = logs = None
    cid = None
    result = {'status': 'STARTING', 'run_id': RUN,
              'scope': 'REPOSITORY_STAGE_RETRY_ONLY' if retry else 'BASELINE_REFERENCE_PREPARATION',
              'started_at': time.time(), 'image': IMAGE, 'input_manifest_sha256': MANIFEST_SHA,
              'container_memory': memory, 'swap_bytes': 0, 'mode': MODE,
              'production_publication': False, 'db_loaded': False}
    save('status.json', result)
    try:
        guard = subprocess.Popen(['python3', '-m', 'pipeline.spark_experiment.runtime.ec2_guard'],
            cwd=ROOT / 'code', env=env, stdin=subprocess.DEVNULL,
            stdout=(ROOT / 'guard.log').open('w'), stderr=subprocess.STDOUT)
        for _ in range(20):
            if (ROOT / 'guard.jsonl').exists() and (ROOT / 'guard.jsonl').stat().st_size:
                break
            if guard.poll() is not None:
                raise RuntimeError('Service guard failed at startup')
            time.sleep(1)
        initial = json.loads((ROOT / 'guard.jsonl').read_text().splitlines()[-1])
        assert initial['issue'] is None and time.time() - initial['time'] < 10
        cmd = ['docker', 'run', '-d', '--pull', 'never', '--name', RUN + '-job',
            '--label', 'pickage.experiment=' + RUN, '--network', 'none', '--cpus', '3',
            '--memory', memory, '--memory-swap', memory, '--pids-limit', '512',
            '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--restart', 'no',
            '--log-opt', 'max-size=20m', '--log-opt', 'max-file=3',
            '--mount', f'type=bind,source={ROOT}/code,target=/workspace,readonly',
            '--mount', f'type=bind,source={FROZEN},target=/frozen,readonly',
            '--mount', f'type=bind,source={output},target=/experiment',
            '--mount', f'type=bind,source={ROOT},target=/control,readonly',
            '-e', 'SPARK_LOCAL_IP=127.0.0.1', '-e', 'TMPDIR=/experiment/tmp',
            '-e', 'PYTHONUNBUFFERED=1']
        if retry:
            cmd += ['--mount', f'type=bind,source={PREVIOUS}/output/reference,target=/experiment/reference,readonly',
                    '--mount', f'type=bind,source={PREVIOUS}/code,target=/previous-code,readonly']
        entry = 'repository_retry_entry' if retry else 'reference_entry'
        cmd += [IMAGE, 'python3', '-m', 'pipeline.spark_experiment.runtime.' + entry]
        cid = command(*cmd)
        save('launch.json', {'command': cmd, 'container_id': cid, 'supervisor_pid': os.getpid()})
        logs = subprocess.Popen(['docker', 'logs', '-f', cid], stdin=subprocess.DEVNULL,
            stdout=(ROOT / 'job.log').open('w'), stderr=subprocess.STDOUT)
        monitor = subprocess.Popen(['sudo', '-n', 'env', 'PYTHONPATH=' + str(ROOT / 'code'),
            'python3', '-m', 'pipeline.spark_experiment.runtime.monitor_container',
            '--container', RUN + '-job', '--run-id', RUN, '--output', str(ROOT / 'metrics'),
            '--duration-seconds', str(SECONDS)], stdin=subprocess.DEVNULL,
            stdout=(ROOT / 'monitor.log').open('w'), stderr=subprocess.STDOUT)
        for _ in range(20):
            path = ROOT / 'metrics/container-metrics.jsonl'
            if path.exists() and path.stat().st_size:
                break
            if monitor.poll() is not None:
                raise RuntimeError('Resource monitor failed at startup')
            time.sleep(1)
        assert path.exists() and path.stat().st_size > 0
        save('supervisor-heartbeat.json', {'time': time.time()})
        (ROOT / 'start.signal').touch()
        result.update(status='RUNNING', container_id=cid)
        save('status.json', result)
        deadline = time.monotonic() + SECONDS
        while True:
            state = json.loads(command('docker', 'inspect', '--format', '{{json .State}}', cid))
            if not state['Running']:
                result['container_state'] = state
                result['status'] = 'COMPLETE' if state['ExitCode'] == 0 and computation_complete(output, MODE) else 'FAILED'
                break
            point = json.loads((ROOT / 'guard.jsonl').read_text().splitlines()[-1])
            reason = stop_reason(time.time(), point['time'], shutil.disk_usage(ROOT).free,
                                 guard.poll() is None, monitor.poll() is None)
            if time.time() - path.stat().st_mtime > 20:
                reason = 'RESOURCE_MONITOR_STALE'
            if time.monotonic() >= deadline:
                reason = 'TIME_LIMIT_6_HOURS'
            if reason:
                result.update(status='ABORTED', reason=reason)
                break
            save('supervisor-heartbeat.json', {'time': time.time()})
            time.sleep(3)
    except BaseException as error:
        result.update(status='FAILED', error={'type': type(error).__name__, 'message': str(error)})
    finally:
        cleanup_errors = []
        if cid:
            try:
                info = json.loads(command('docker', 'inspect', cid))[0]
                assert info['Config']['Labels']['pickage.experiment'] == RUN
                if info['State']['Running']:
                    command('docker', 'stop', '--time', '10', cid)
                result['container_state'] = json.loads(command('docker', 'inspect', '--format', '{{json .State}}', cid))
            except Exception as error:
                cleanup_errors.append(str(error))
        (ROOT / 'guard.done').touch()
        for process in (monitor, guard, logs):
            if process:
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    cleanup_errors.append('Child process did not finish promptly')
        if cid:
            try:
                command('docker', 'rm', cid)
            except Exception as error:
                cleanup_errors.append(str(error))
        result.update(finished_at=time.time(), cleanup_errors=cleanup_errors)
        save('result.json', result)
        save('status.json', result)


if __name__ == '__main__':
    main()
