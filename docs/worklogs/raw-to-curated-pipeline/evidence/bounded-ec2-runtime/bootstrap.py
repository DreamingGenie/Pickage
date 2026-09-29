import hashlib,json,subprocess,sys
from pathlib import Path
root=Path('/home/ubuntu/pickage-experiments/ec2-runtime-20260915-a1')
assert not (root/'guard-result.json').exists(), 'Do not reuse finished run'
assert hashlib.file_digest((root/'runtime.tar.gz').open('rb'),'sha256').hexdigest()=='178604d0bfd4d400f17416d95ceba803fbbdb3024465f491fade2ff9125cb0ad'
log=(root/'guard.log').open('w')
guard=subprocess.Popen(['python3',str(root/'ec2_guard.py')],stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
(root/'guard.pid').write_text(str(guard.pid))
p=subprocess.run(['nice','-n','10','ionice','-c','3','docker','load','--input',str(root/'runtime.tar.gz')],capture_output=True,text=True,timeout=180)
assert p.returncode==0, p.stderr
info=json.loads(subprocess.check_output(['docker','image','inspect','pickage-spark-experiment:runtime-3.5.3'],text=True))[0]
assert info['Id'] in ['sha256:1b9cac7cee8b870c5bfcb2a2c9dea5fa873af42a59442bce067adcedff02124b','sha256:e3ca9ccf92c2c9fa0022920acab1713e6d35a0529e5ab6ac4f0a38428f955479'], info['Id']
result={'image_id':info['Id'],'archive_sha256':'178604d0bfd4d400f17416d95ceba803fbbdb3024465f491fade2ff9125cb0ad','guard_pid':guard.pid,'load':p.stdout}
(root/'image-loaded.json').write_text(json.dumps(result)); print(json.dumps(result))
