"""Read-only host/container preflight; excludes environment and command secrets."""
import datetime
import json
import shutil
import socket
import subprocess
from pathlib import Path

def run(args):
    r = subprocess.run(args, text=True, capture_output=True, timeout=25)
    return {'exit_code':r.returncode, 'stdout':r.stdout, 'stderr':r.stderr}

memory = {}
for line in Path('/proc/meminfo').read_text().splitlines():
    name, value = line.split(':',1)
    if name in ['MemTotal','MemAvailable','SwapTotal','SwapFree']:
        memory[name] = int(value.split()[0]) * 1024
ids = run(['docker','ps','-q'])['stdout'].split()
containers = []
for cid in ids:
    d = json.loads(run(['docker','inspect',cid])['stdout'])[0]
    h = d['HostConfig']
    containers.append({'name':d['Name'].lstrip('/'),'image':d['Config']['Image'],'image_id':d['Image'],
        'status':d['State']['Status'],'health':d['State'].get('Health',{}).get('Status'),
        'oom_killed':d['State']['OOMKilled'],'started_at':d['State']['StartedAt'],
        'memory_limit':h['Memory'],'memory_swap_limit':h['MemorySwap'],'nano_cpus':h['NanoCpus'],
        'network_mode':h['NetworkMode'],'ports':d['NetworkSettings']['Ports']})
workers = [c['name'] for c in containers if 'spark-worker' in c['name']]
runtime = {}
for worker in workers:
    runtime[worker] = run(['docker','exec',worker,'sh','-c',
        'python3 --version; java -version; command -v node; node --version; cat /opt/spark/RELEASE'])
disk = shutil.disk_usage('/home/ubuntu')
result = {'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'hostname':socket.gethostname(),'read_only':True,'logical_cpus':int(run(['nproc'])['stdout']),
    'memory_bytes':memory,'disk_bytes':dict(zip(['total','used','free'],disk)),
    'loadavg':Path('/proc/loadavg').read_text().strip(),'containers':containers,
    'container_stats':run(['docker','stats','--no-stream','--format','{{json .}}']),
    'spark_worker_runtime':runtime,
    'host_tools':run(['sh','-c','python3 --version; command -v node; node --version; command -v mc']),
    'kernel':run(['uname','-r']),
    'timers':run(['systemctl','list-timers','--all','--no-pager','--plain'])}
print(json.dumps(result))
