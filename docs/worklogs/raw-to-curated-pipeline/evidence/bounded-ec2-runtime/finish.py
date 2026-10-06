import json,subprocess,time
from pathlib import Path
root=Path('/home/ubuntu/pickage-experiments/ec2-runtime-20260915-a1')
label='pickage.experiment=ec2-runtime-20260915-a1'
ids=subprocess.check_output(['docker','ps','-aq','--filter','label='+label],text=True).split()
observed=json.loads(subprocess.check_output(['docker','inspect',*ids],text=True))
clean=[]
for d in observed:
 assert (d['Config'].get('Labels') or {}).get('pickage.experiment')=='ec2-runtime-20260915-a1'
 clean.append({'id':d['Id'],'name':d['Name'],'image':d['Image'],'started_at':d['State']['StartedAt'],'status':d['State']['Status'],'oom_killed':d['State']['OOMKilled'],'memory':d['HostConfig']['Memory'],'memory_swap':d['HostConfig']['MemorySwap'],'nano_cpus':d['HostConfig']['NanoCpus']})
(root/'containers.json').write_text(json.dumps(clean,indent=2))
(root/'guard.done').touch()
deadline=time.monotonic()+30
while not (root/'guard-result.json').exists():
 assert time.monotonic()<deadline, 'Guard cleanup timed out'
 time.sleep(1)
for cid in ids:
 state=json.loads(subprocess.check_output(['docker','inspect',cid],text=True))[0]
 assert not state['State']['Running'], 'Guard did not stop own container'
subprocess.run(['docker','rm',*ids],check=True,capture_output=True)
assert not subprocess.check_output(['docker','ps','-aq','--filter','label='+label],text=True).strip()
print((root/'guard-result.json').read_text())
