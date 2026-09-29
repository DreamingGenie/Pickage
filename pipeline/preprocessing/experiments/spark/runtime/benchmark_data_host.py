"""Own only the isolated data-host benchmark containers and bounded monitors."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
from urllib.request import urlopen

RUN = 'sample1000-ec2-20260916-a2'
ROOT = Path('/home/ubuntu/pickage-experiments') / RUN
CODE = ROOT / 'code'
OUT = ROOT / 'output'
DEST = '/experiment/' + RUN
IMAGE = 'sha256:e3ca9ccf92c2c9fa0022920acab1713e6d35a0529e5ab6ac4f0a38428f955479'
JARS = ('hadoop-aws-3.3.4.jar', 'aws-java-sdk-bundle-1.12.262.jar')


def command(*args):
    return subprocess.check_output(args, text=True, timeout=30).strip()


def save(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2, default=str))
    tmp.replace(path)


class Supervisor:
    def __init__(self):
        self.deadline = time.monotonic() + 6 * 3600
        self.guard = None
        self.owned = {}
        self.control = None
        self.result = {'status': 'STARTING', 'run_id': RUN, 'started_at': time.time(),
                       'production_publication': False, 'db_loaded': False, 'phases': {}}

    def check(self):
        if time.monotonic() >= self.deadline:
            raise RuntimeError('TIME_LIMIT_6_HOURS')
        if self.guard.poll() is not None:
            raise RuntimeError('SERVICE_GUARD_EXITED')
        path = ROOT / 'guard.jsonl'
        if not path.exists() or time.time() - path.stat().st_mtime > 20:
            raise RuntimeError('SERVICE_GUARD_STALE')
        if shutil.disk_usage(ROOT).free < 30 * 1024**3:
            raise RuntimeError('DISK_FREE_BELOW_30_GIB')
        for name, row in self.owned.items():
            metrics = ROOT / ('metrics-' + name) / 'container-metrics.jsonl'
            state = json.loads(command('docker', 'inspect', '--format', '{{json .State}}', row['id']))
            if state['Running'] and (row['monitor'].poll() is not None or
                                     time.time() - metrics.stat().st_mtime > 20):
                raise RuntimeError('RESOURCE_MONITOR_FAILED_' + name)
            if name in ('master', 'worker') and not state['Running']:
                raise RuntimeError('SPARK_DAEMON_STOPPED_' + name)
        if self.control:
            save(self.control / 'supervisor-heartbeat.json', {'time': time.time()})

    def start(self, name, cpu, memory, entry, *, network='host', extra=(), gated=False):
        control = ROOT / ('control-' + name)
        control.mkdir()
        cmd = ['docker', 'run', '-d', '--pull', 'never', '--name', RUN + '-' + name,
               '--label', 'pickage.experiment=' + RUN, '--network', network, '--restart', 'no',
               '--cpus', str(cpu), '--memory', memory, '--memory-swap', memory,
               '--pids-limit', '512', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
               '--log-opt', 'max-size=20m', '--log-opt', 'max-file=3',
               '--mount', f'type=bind,source={CODE},target=/workspace,readonly',
               '--mount', f'type=bind,source={OUT},target={DEST}',
               '--mount', f'type=bind,source={control},target=/control,readonly',
               '-e', 'PYTHONPATH=/workspace:/opt/spark/python:/opt/spark/python/lib/py4j-0.10.9.7-src.zip', '-e', 'PYTHONUNBUFFERED=1',
               '-e', 'TMPDIR=' + DEST + '/tmp', '-e', 'SPARK_LOCAL_IP=172.26.8.249']
        for jar in JARS:
            cmd += ['--mount', f'type=bind,source={ROOT}/jars/{jar},target=/opt/spark/jars/{jar},readonly']
        for env in ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_DEFAULT_REGION'):
            if env in os.environ:
                cmd += ['-e', env]
        cmd += list(extra) + [IMAGE] + entry
        cid = command(*cmd)
        logs = subprocess.Popen(['docker', 'logs', '-f', cid], stdout=(ROOT/(name+'.log')).open('w'),
                                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        monitor = subprocess.Popen(['sudo', '-n', 'env', 'PYTHONPATH=' + str(CODE), 'python3', '-m',
            'pipeline.preprocessing.experiments.spark.runtime.monitor_container', '--container', RUN+'-'+name,
            '--run-id', RUN, '--output', str(ROOT/('metrics-'+name)), '--duration-seconds', '21600'],
            stdout=(ROOT/(name+'-monitor.log')).open('w'), stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL)
        self.owned[name] = {'id': cid, 'monitor': monitor, 'logs': logs}
        save(ROOT/(name+'-launch.json'), {'command': cmd, 'container_id': cid})
        samples = ROOT/('metrics-'+name)/'container-metrics.jsonl'
        for _ in range(25):
            if samples.exists() and samples.stat().st_size:
                break
            if monitor.poll() is not None:
                raise RuntimeError('Resource monitor startup failed: ' + name)
            time.sleep(1)
        else:
            raise RuntimeError('Resource monitor sample missing: ' + name)
        if gated:
            self.control = control
            self.check()
            (control/'start.signal').touch()
        return cid

    def finish(self, name):
        row = self.owned.pop(name)
        info = json.loads(command('docker', 'inspect', row['id']))[0]
        assert info['Config']['Labels']['pickage.experiment'] == RUN
        if info['State']['Running']:
            command('docker', 'stop', '--time', '10', row['id'])
        state = json.loads(command('docker', 'inspect', '--format', '{{json .State}}', row['id']))
        for proc in (row['monitor'], row['logs']):
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.terminate()
        command('docker', 'rm', row['id'])
        return state

    def phase(self, name, entry=None, extra=()):
        self.result.update(status='RUNNING', phase=name)
        save(ROOT/'status.json', self.result)
        started = time.time()
        cpu, memory = (1, '2048m') if name == 'prepare' else (3, '7680m')
        if name == 'spark':
            cpu, memory = .75, '1536m'
        entry = entry or ['python3', '-m', 'pipeline.preprocessing.experiments.spark.runtime.benchmark_data_phase', name]
        if name == 'baseline':
            # Java resolves the OS hostname even when Spark binds to loopback.
            # With no network interface Docker may omit that hosts entry.
            hostname = RUN + '-baseline'
            extra = [*extra, '--hostname', hostname, '--add-host', hostname + ':127.0.0.1']
        cid = self.start(name, cpu, memory, entry, network='none' if name == 'baseline' else 'host',
                         extra=extra, gated=True)
        while True:
            self.check()
            state = json.loads(command('docker', 'inspect', '--format', '{{json .State}}', cid))
            if not state['Running']:
                break
            time.sleep(3)
        self.control = None
        state = self.finish(name)
        self.result['phases'][name] = {'seconds': time.time()-started, 'state': state}
        save(ROOT/'status.json', self.result)
        if state['ExitCode'] or state['OOMKilled']:
            raise RuntimeError('Phase failed: '+name)

    def run(self):
        assert socket.gethostname() == 'ip-172-26-8-249'
        assert not (ROOT/'result.json').exists()
        assert not command('docker', 'ps', '-aq', '--filter', 'label=pickage.experiment='+RUN)
        assert shutil.disk_usage(ROOT).free > 90 * 1024**3
        for port in (40014, 18080, 17078, 18081, 40012, 40011, 40013):
            with socket.socket() as probe:
                probe.bind(('172.26.8.249', port))
        OUT.mkdir()
        OUT.chmod(0o777)
        for name in ('tmp', 'worker', 'local'):
            (OUT/name).mkdir()
            (OUT/name).chmod(0o777)
        env = dict(os.environ, PICKAGE_EXPERIMENT_RUN=RUN, PICKAGE_GUARD_SECONDS='21600',
            PICKAGE_GUARD_PEER_HEALTH='https://j15a506.p.ssafy.io/actuator/health', PYTHONPATH=str(CODE))
        self.guard = subprocess.Popen(['python3', '-m', 'pipeline.preprocessing.experiments.spark.runtime.ec2_guard'],
            cwd=CODE, env=env, stdout=(ROOT/'guard.log').open('w'), stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL)
        try:
            for _ in range(20):
                p = ROOT/'guard.jsonl'
                if p.exists() and p.stat().st_size:
                    break
                time.sleep(1)
            self.check()
            mounts = []
            for source, target in (
                ('raw-freeze-20260915-b1/payload/frozen', '/frozen'),
                ('reference-20260915-a2/output/reference', '/experiment/reference'),
                ('repository-heap4g-20260915-a1/output', '/retry-source'),
                ('repository-heap4g-20260915-a1/output/repository-retry', '/experiment/repository-retry')):
                mounts += ['--mount', f'type=bind,source=/home/ubuntu/pickage-experiments/{source},target={target},readonly']
            mounts += ['--mount', f'type=bind,source={ROOT}/metadata,target=/metadata,readonly']
            mounts += ['--mount', 'type=bind,source=/home/ubuntu/pickage-experiments/benchmark-ec2-20260916-a1/output/local-manifest.json,target=/source-manifest.json,readonly']
            self.phase('prepare', extra=mounts)
            self.start('master', .25, '512m', ['/opt/spark/bin/spark-class',
                'org.apache.spark.deploy.master.Master', '--host', '172.26.8.249', '--port', '40014',
                '--webui-port', '18080'], extra=['-e', 'SPARK_DAEMON_MEMORY=256m'])
            self.start('worker', 1, '2816m', ['/opt/spark/bin/spark-class',
                'org.apache.spark.deploy.worker.Worker', 'spark://172.26.8.249:40014',
                '--host', '172.26.8.249', '--port', '17078', '--webui-port', '18081',
                '--cores', '1', '--memory', '2048M'], extra=['-e', 'SPARK_DAEMON_MEMORY=256m',
                '-e', 'SPARK_WORKER_DIR='+DEST+'/worker', '-e', 'SPARK_LOCAL_DIRS='+DEST+'/local'])
            for _ in range(60):
                self.check()
                try:
                    with urlopen('http://172.26.8.249:18080/json/', timeout=2) as response:
                        workers = json.load(response)['workers']
                    if {w['host'] for w in workers if w['state'] == 'ALIVE'} == {'172.26.8.249', '172.26.6.235'}:
                        break
                except OSError:
                    pass
                time.sleep(3)
            else:
                raise RuntimeError('Both EC2 workers did not register')
            conf = {'spark.hadoop.fs.s3a.endpoint': 'http://172.26.8.249:9000',
                'spark.hadoop.fs.s3a.path.style.access': 'true',
                'spark.hadoop.fs.s3a.connection.ssl.enabled': 'false',
                'spark.hadoop.fs.s3a.aws.credentials.provider': 'com.amazonaws.auth.EnvironmentVariableCredentialsProvider',
                'spark.executorEnv.PYTHONPATH': '/workspace:/opt/spark/python:/opt/spark/python/lib/py4j-0.10.9.7-src.zip', 'spark.executorEnv.PYSPARK_PYTHON': '/usr/local/bin/python3',
                'spark.local.dir': DEST+'/local', 'spark.driver.port': '40012',
                'spark.driver.blockManager.port': '40011', 'spark.blockManager.port': '40013',
                'spark.port.maxRetries': '0', 'spark.ui.enabled': 'false'}
            entry = ['/opt/spark/bin/spark-submit', '--master', 'spark://172.26.8.249:40014',
                     '--driver-memory', '1g', '--executor-memory', '2g', '--executor-cores', '1', '--total-executor-cores', '2']
            for key, value in conf.items():
                entry += ['--conf', key+'='+value]
            prefix = 's3a://pickage-curated/experiments/'+RUN
            entry += ['/workspace/pipeline/preprocessing/experiments/spark/runtime/cluster_benchmark_entry.py',
                '--run-id', RUN, '--manifest', prefix+'/manifest.json', '--output', prefix+'/spark-output',
                '--telemetry-dir', DEST+'/telemetry', '--events-dir', DEST+'/cluster-events',
                '--summary', DEST+'/cluster-summary.json', '--partitions', '16']
            self.phase('spark', entry, ['-e', 'SPARK_MASTER_URL=spark://172.26.8.249:40014'])
            assert json.loads((OUT/'cluster-summary.json').read_text())['status'] == 'COMPUTED'
            self.finish('worker')
            self.finish('master')
            for _ in range(30):
                self.check()
                try:
                    with socket.create_connection(('172.26.6.235', 40014), timeout=2):
                        pass
                except OSError:
                    break
                time.sleep(3)
            else:
                raise RuntimeError('App worker did not stop before baseline')
            self.phase('baseline', extra=mounts+['-e', 'SPARK_LOCAL_IP=127.0.0.1'])
            self.phase('compare')
            assert json.loads((OUT/'benchmark-result.json').read_text())['status'] == 'VERIFIED'
            self.result['status'] = 'COMPLETE'
        except BaseException as error:
            self.result.update(status='FAILED', error={'type': type(error).__name__, 'message': str(error)})
        finally:
            errors = []
            for name in list(self.owned):
                try:
                    self.result['phases'].setdefault(name, {})['final_state'] = self.finish(name)
                except Exception as error:
                    errors.append(str(error))
            (ROOT/'guard.done').touch()
            try:
                self.guard.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.guard.terminate()
            self.result.update(finished_at=time.time(), cleanup_errors=errors)
            save(ROOT/'result.json', self.result)
            save(ROOT/'status.json', self.result)


if __name__ == '__main__':
    Supervisor().run()
