"""Bounded sequential repository local[2] then two-EC2 2+2 experiment."""
import json
import os
from pathlib import Path
import socket
import subprocess
import time
from urllib.request import urlopen

from pipeline.spark_experiment.runtime import benchmark_data_host as host
from pipeline.spark_experiment.runtime import repository_profile_host as local
from pipeline.spark_experiment.runtime import weekly_priority

RUN = 'repository22-20260917-a1'
ROOT = Path('/home/ubuntu/pickage-experiments') / RUN
DEST = '/experiment/' + RUN
SOURCE = ROOT.parent / 'sample1000-ec2-20260916-a2/output'
SOURCE_DEST = '/experiment/sample1000-ec2-20260916-a2'


class Supervisor(host.Supervisor):
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
        cpu, memory = {'baseline': (2, '7680m'), 'spark': (1, '2048m'),
                       'worker': (2, '5632m'), 'master': (.25, '512m'),
                       'compare': (1, '2048m')}.get(name, (cpu, memory))
        extra = list(kwargs.pop('extra', ())) + ['--cpu-shares', '128',
            '--device-read-bps', '/dev/nvme0n1:32mb', '--device-write-bps', '/dev/nvme0n1:32mb']
        return super().start(name, cpu, memory, ['nice', '-n', '10', *entry], extra=extra, **kwargs)


def preflight():
    local.ROOT = ROOT
    result = local.preflight()
    for port in (40014, 18080, 17078, 18081, 40012, 40011, 40013):
        with socket.socket() as probe:
            probe.bind(('172.26.8.249', port))
    if not os.environ.get('AWS_ACCESS_KEY_ID') or not os.environ.get('AWS_SECRET_ACCESS_KEY'):
        raise RuntimeError('Experiment S3 credentials missing')
    if result['status'] != 'READY':
        raise RuntimeError('Preflight not ready: ' + json.dumps(result))
    return result


def run():
    check = preflight()
    if (ROOT / 'output').exists() or (ROOT / 'result.json').exists():
        raise FileExistsError('Run already started')
    host.RUN, host.ROOT, host.CODE, host.OUT, host.DEST = RUN, ROOT, ROOT / 'code', ROOT / 'output', DEST
    supervisor = Supervisor(check['weekly'])
    supervisor.result['scope'] = 'REPOSITORY_ONLY_LOCAL2_VS_TWO_EC2_2_PLUS_2'
    supervisor.result['resources'] = {'baseline_cpu': 2, 'baseline_heap': '4g',
        'executor_cores_each': 2, 'executor_heap_each': '4g', 'executor_container_mib_each': 5632,
        'driver_cpu': 1, 'driver_heap': '1g', 'driver_container_mib': 2048,
        'master_cpu': .25, 'master_container_mib': 512,
        'swap_extra_bytes': 0, 'disk_read_write_mib_s_each_container': 32}
    host.OUT.mkdir()
    host.OUT.chmod(0o777)
    for name in ('tmp', 'worker', 'local'):
        (host.OUT / name).mkdir()
        (host.OUT / name).chmod(0o777)
    env = dict(os.environ, PICKAGE_EXPERIMENT_RUN=RUN, PICKAGE_GUARD_SECONDS='1800',
               PICKAGE_GUARD_PEER_HEALTH='https://j15a506.p.ssafy.io/actuator/health', PYTHONPATH=str(host.CODE))
    mounts = ['--mount', f'type=bind,source={SOURCE},target={SOURCE_DEST},readonly']
    try:
        supervisor.guard = subprocess.Popen(['python3', '-m', 'pipeline.spark_experiment.runtime.ec2_guard'],
            cwd=host.CODE, env=env, stdin=subprocess.DEVNULL, stdout=(ROOT / 'guard.log').open('w'), stderr=subprocess.STDOUT)
        for _ in range(20):
            path = ROOT / 'guard.jsonl'
            if path.exists() and path.stat().st_size:
                break
            time.sleep(1)
        supervisor.check()
        supervisor.phase('baseline', ['python3', '-m', 'pipeline.spark_experiment.runtime.repository22_entry', 'baseline'],
                         mounts + ['-e', 'SPARK_LOCAL_IP=127.0.0.1'])
        supervisor.start('master', .25, '512m', ['/opt/spark/bin/spark-class',
            'org.apache.spark.deploy.master.Master', '--host', '172.26.8.249', '--port', '40014', '--webui-port', '18080'],
            extra=['-e', 'SPARK_DAEMON_MEMORY=256m'])
        supervisor.start('worker', 2, '5632m', ['/opt/spark/bin/spark-class',
            'org.apache.spark.deploy.worker.Worker', 'spark://172.26.8.249:40014', '--host', '172.26.8.249',
            '--port', '17078', '--webui-port', '18081', '--cores', '2', '--memory', '4096M'],
            extra=['-e', 'SPARK_DAEMON_MEMORY=256m', '-e', 'SPARK_WORKER_DIR=' + DEST + '/worker',
                   '-e', 'SPARK_LOCAL_DIRS=' + DEST + '/local'])
        workers = []
        for _ in range(60):
            supervisor.check()
            try:
                with urlopen('http://172.26.8.249:18080/json/', timeout=2) as response:
                    workers = [w for w in json.load(response)['workers'] if w['state'] == 'ALIVE']
                if {w['host'] for w in workers} == {'172.26.8.249', '172.26.6.235'} and all(w['cores'] == 2 for w in workers):
                    break
            except OSError:
                pass
            time.sleep(3)
        else:
            raise RuntimeError('Both two-core workers did not register')
        host.save(ROOT / 'registered-workers.json', {'workers': workers})
        conf = {'spark.hadoop.fs.s3a.endpoint': 'http://172.26.8.249:9000',
                'spark.hadoop.fs.s3a.path.style.access': 'true', 'spark.hadoop.fs.s3a.connection.ssl.enabled': 'false',
                'spark.hadoop.fs.s3a.aws.credentials.provider': 'com.amazonaws.auth.EnvironmentVariableCredentialsProvider',
                'spark.executorEnv.PYTHONPATH': '/workspace:/opt/spark/python:/opt/spark/python/lib/py4j-0.10.9.7-src.zip',
                'spark.executorEnv.PYSPARK_PYTHON': '/usr/local/bin/python3',
                'spark.driver.host': '172.26.8.249', 'spark.driver.bindAddress': '172.26.8.249',
                'spark.driver.port': '40012', 'spark.driver.blockManager.port': '40011',
                'spark.blockManager.port': '40013', 'spark.port.maxRetries': '0', 'spark.ui.enabled': 'false',
                'spark.local.dir': DEST + '/local'}
        entry = ['/opt/spark/bin/spark-submit', '--master', 'spark://172.26.8.249:40014',
                 '--driver-memory', '1g', '--executor-memory', '4g', '--executor-cores', '2', '--total-executor-cores', '4']
        for key, value in conf.items():
            entry += ['--conf', key + '=' + value]
        entry += ['/workspace/pipeline/spark_experiment/runtime/repository22_entry.py', 'spark']
        supervisor.phase('spark', entry, mounts)
        supervisor.finish('worker')
        supervisor.finish('master')
        for _ in range(20):
            supervisor.check()
            try:
                with socket.create_connection(('172.26.6.235', 40014), timeout=2):
                    pass
            except OSError:
                break
            time.sleep(3)
        else:
            raise RuntimeError('App worker did not stop after master')
        supervisor.phase('compare', ['python3', '-m', 'pipeline.spark_experiment.runtime.repository22_entry', 'compare'], mounts)
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
        if errors:
            supervisor.result['status'] = 'FAILED'
        supervisor.result.update(finished_at=time.time(), cleanup_errors=errors)
        host.save(ROOT / 'result.json', supervisor.result)
        host.save(ROOT / 'status.json', supervisor.result)
    return 0 if supervisor.result['status'] == 'COMPLETE' else 1


if __name__ == '__main__':
    raise SystemExit(run())
