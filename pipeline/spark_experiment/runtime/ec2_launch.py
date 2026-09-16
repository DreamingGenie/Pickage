"""One-shot launcher for the approved bounded EC2 runtime check; no deployment edits."""
import argparse
import json
import os
import socket
import subprocess
import time
from pathlib import Path
from urllib.request import urlopen

RUN = 'ec2-runtime-20260915-a1'
ROOT = Path('/home/ubuntu/pickage-experiments') / RUN
IMAGE = 'pickage-spark-experiment:runtime-3.5.3'


def command(args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=30).strip()


def check_guard():
    assert not (ROOT / 'guard-result.json').exists(), 'Run guard has already ended'
    os.kill(int((ROOT / 'guard.pid').read_text()), 0)
    lines = (ROOT / 'guard.jsonl').read_text().splitlines()
    latest = json.loads(lines[-1])
    assert time.time() - latest['time'] < 15 and latest['issue'] is None, latest
    assert latest['available_memory_bytes'] >= 4 * 1024**3


def start(role, ip, cpu, memory, args, mounts=()):
    check_guard()
    name = RUN + '-' + role
    image = json.loads((ROOT / 'image-loaded.json').read_text())['image_id']
    launch = ['docker', 'run', '-d', '--pull', 'never', '--name', name,
              '--hostname', name, '--label', 'pickage.experiment=' + RUN,
              '--network', 'host', '--restart', 'no', '--cpus', cpu,
              '--memory', memory, '--memory-swap', memory, '--pids-limit', '256',
              '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
              '--log-opt', 'max-size=10m', '--log-opt', 'max-file=1',
              '-e', 'SPARK_LOCAL_IP=' + ip, '-e', 'SPARK_DAEMON_MEMORY=256m']
    for mount in mounts:
        launch += ['--mount', mount]
    cid = command(launch + [image, *args])
    (ROOT / (role + '-launch.json')).write_text(json.dumps({'command': launch + [image, *args], 'container_id': cid}))
    return name


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['daemons', 'driver'])
    parser.add_argument('--attempt', type=int, default=1, choices=range(1, 10))
    parsed = parser.parse_args()
    action = parsed.action
    is_data = socket.gethostname() == 'ip-172-26-8-249'
    assert is_data or socket.gethostname() == 'ip-172-26-6-235'
    ip = '172.26.8.249' if is_data else '172.26.6.235'
    if action == 'daemons':
        ports = [40011, 40012, 40013, 40014, 17078, 18080, 18081] if is_data else [40013, 40014, 18081]
        for port in ports:
            with socket.socket() as probe:
                probe.bind((ip, port))
        if is_data:
            start('master', ip, '0.25', '512m', ['/opt/spark/bin/spark-class',
                'org.apache.spark.deploy.master.Master', '--host', ip, '--port', '40014', '--webui-port', '18080'])
            deadline = time.monotonic() + 60
            while True:
                try:
                    with urlopen('http://172.26.8.249:18080/json/', timeout=2) as response:
                        assert json.load(response)['status'] == 'ALIVE'
                    break
                except Exception:
                    if time.monotonic() > deadline:
                        raise
                    time.sleep(1)
        start('worker-data' if is_data else 'worker-app', ip, '1', '2g',
              ['/opt/spark/bin/spark-class', 'org.apache.spark.deploy.worker.Worker',
               'spark://172.26.8.249:40014', '--host', ip, '--port', '17078' if is_data else '40014',
               '--webui-port', '18081', '--cores', '1', '--memory', '1536M'])
        print('EXPERIMENT_DAEMONS_STARTED ' + ip)
    else:
        assert is_data, 'The experiment driver runs on data only'
        output = ROOT / ('output-r' + str(parsed.attempt))
        (output / 'events').mkdir(parents=True, exist_ok=False)
        # Only this empty experiment mount is writable to the image's root user
        # with all capabilities dropped. Do not change any production directory.
        output.chmod(0o777)
        (output / 'events').chmod(0o777)
        name = start('driver-r' + str(parsed.attempt), ip, '0.75', '1g', ['python3', '/ec2_smoke.py'],
                     [f'type=bind,source={ROOT}/ec2_smoke.py,target=/ec2_smoke.py,readonly',
                      f'type=bind,source={output},target=/experiment/output'])
        try:
            result = subprocess.check_output(['docker', 'wait', name], text=True, timeout=180).strip()
            log = command(['docker', 'logs', name])
            (ROOT / ('driver-r' + str(parsed.attempt) + '.log')).write_text(log)
            assert result == '0', log[-5000:]
            print((output / 'ec2-smoke.json').read_text())
        finally:
            command(['docker', 'stop', '--time', '5', name])


if __name__ == '__main__':
    main()
