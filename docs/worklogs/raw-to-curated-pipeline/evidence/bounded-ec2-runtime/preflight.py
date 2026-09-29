import json, subprocess, socket, urllib.request, time
from pathlib import Path

def cmd(args):
 p=subprocess.run(args,capture_output=True,text=True,timeout=15); return {'code':p.returncode,'out':p.stdout,'err':p.stderr}
ids=cmd(['docker','ps','-q'])['out'].split()
containers=[]
for cid in ids:
 d=json.loads(cmd(['docker','inspect',cid])['out'])[0]
 containers.append({'id':d['Id'],'name':d['Name'],'image':d['Image'],'started_at':d['State']['StartedAt'],'health':d['State'].get('Health',{}).get('Status'),'running':d['State']['Running'],'oom':d['State']['OOMKilled'],'restart_count':d['RestartCount']})
health={}
urls=['http://127.0.0.1:8080/actuator/health'] if socket.gethostname().endswith('6-235') else ['http://127.0.0.1:9000/minio/health/live','http://172.26.8.249:8080/json/']
for url in urls:
 try:
  t=time.monotonic()
  with urllib.request.urlopen(url,timeout=3) as r: body=r.read().decode()
  health[url]={'elapsed_s':time.monotonic()-t,'body':body}
 except Exception as e: health[url]={'error':str(e)}
print(json.dumps({'hostname':socket.gethostname(),'containers':containers,'health':health,'ports':cmd(['ss','-ltnH']),'memory':Path('/proc/meminfo').read_text(),'cpu_pressure':Path('/proc/pressure/cpu').read_text(),'io_pressure':Path('/proc/pressure/io').read_text(),'load':Path('/proc/loadavg').read_text(),'images':cmd(['docker','images','--format','{{.Repository}}:{{.Tag}} {{.ID}}'])}))
