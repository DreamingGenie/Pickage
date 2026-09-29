import json
from pathlib import Path
root=Path('docs/worklogs/raw-to-curated-pipeline/evidence/bounded-ec2-runtime')
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
result={}
for node in ['app','data']:
 before=read(root/(node+'-before.json')); after=read(root/(node+'-after.json'))
 assert before['containers']==after['containers'], node+' existing containers changed'
 points=[json.loads(s) for s in (root/node/'guard.jsonl').read_text().splitlines()]
 assert all(p['issue'] is None for p in points)
 assert read(root/node/'guard-result.json')['reason']=='FINISHED'
 result[node]={'original_containers_unchanged':True,'original_container_count':len(before['containers']),'guard_samples':len(points),'min_available_gib':min(p['available_memory_bytes'] for p in points)/1024**3,'max_service_health_seconds':max(p.get('service_seconds',0) for p in points),'guard_issues':0}
events=[json.loads(s) for s in (root/'data/output-r3/events/app-20260915085525-0001').read_text(encoding='utf-8-sig').splitlines() if s]
tasks=[e for e in events if e['Event']=='SparkListenerTaskEnd']
metrics=[e['Task Metrics'] for e in tasks]
result['spark']={'task_count':len(tasks),'executor_hosts':sorted({e['Task Info']['Host'] for e in tasks}),'remote_shuffle_bytes_read':sum(m.get('Shuffle Read Metrics',{}).get('Remote Bytes Read',0) for m in metrics),'shuffle_bytes_written':sum(m.get('Shuffle Write Metrics',{}).get('Shuffle Bytes Written',0) for m in metrics),'executor_cpu_seconds':sum(m.get('Executor CPU Time',0) for m in metrics)/1e9,'result':read(root/'data/output-r3/ec2-smoke.json')}
assert len(result['spark']['executor_hosts'])==2 and result['spark']['remote_shuffle_bytes_read']>0
(root/'verification-summary.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
