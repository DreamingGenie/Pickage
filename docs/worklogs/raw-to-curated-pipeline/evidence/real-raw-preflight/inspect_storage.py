"""Read-only metadata inventory. Credentials stay in memory; stdout is JSON evidence."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

p = argparse.ArgumentParser()
p.add_argument('--env', required=True)
p.add_argument('--endpoint', required=True)
p.add_argument('--scope', choices=['server', 'local'], required=True)
a = p.parse_args()
env = {}
for line in Path(a.env).read_text().splitlines():
    if line.strip() and not line.lstrip().startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
s3 = boto3.client('s3', endpoint_url=a.endpoint,
    aws_access_key_id=env['MINIO_ROOT_USER'], aws_secret_access_key=env['MINIO_ROOT_PASSWORD'],
    region_name='us-east-1', config=Config(connect_timeout=5, read_timeout=20,
    retries={'max_attempts':2}, s3={'addressing_style':'path'}))
result = {'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'scope':a.scope, 'endpoint':a.endpoint, 'read_only':True, 'inventories':[], 'metadata':[]}

def inventory(bucket, prefix):
    records = []
    for page in s3.get_paginator('list_objects_v2').paginate(Bucket=bucket, Prefix=prefix):
        records.extend({'key':r['Key'], 'bytes':r['Size'], 'etag':r['ETag'],
                        'modified':r['LastModified'].isoformat()} for r in page.get('Contents', []))
    result['inventories'].append({'bucket':bucket,'prefix':prefix,'objects':records,
                                 'bytes':sum(r['bytes'] for r in records)})
    return records

def metadata(bucket, key):
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
    except ClientError as error:
        if error.response['Error']['Code'] in ['NoSuchKey','404']:
            result['metadata'].append({'bucket':bucket,'key':key,'exists':False})
            return None
        raise
    raw = response['Body'].read()
    record = {'bucket':bucket,'key':key,'exists':True,'bytes':len(raw),
              'sha256':hashlib.sha256(raw).hexdigest(),'version_id':response.get('VersionId'),
              'body_utf8':raw.decode('utf-8')}
    result['metadata'].append(record)
    try: return json.loads(raw)
    except ValueError: return None

result['bucket_versioning'] = {b:s3.get_bucket_versioning(Bucket=b).get('Status','Disabled')
                               for b in ['pickage-raw','pickage-curated']}
if a.scope == 'server':
    objects = inventory('pickage-raw','depsdev/v1/')
    current = [r['key'] for r in objects if r['key'].endswith('/run_manifest.json')
               and '/snapshot=2026-08-31/' in r['key']
               and any('/'+t+'/' in r['key'] for t in ['versions_full','requirements','projects'])]
    days = sorted({r['key'].split('snapshot=')[1].split('/')[0] for r in objects
                   if '/projects/snapshot=' in r['key'] and r['key'].endswith('/run_manifest.json')})
    previous = max(d for d in days if d < '2026-08-31')
    result['projects_calendar_dates'] = days
    result['previous_projects_snapshot'] = previous
    selected = current + [r['key'] for r in objects if '/projects/snapshot='+previous+'/' in r['key']
                          and r['key'].endswith('/run_manifest.json')]
    obj_map = {r['key']:r for r in objects}
    result['selected_checks'] = []
    for key in selected:
        manifest = metadata('pickage-raw', key)
        prefix = key.rsplit('/',1)[0]
        metadata('pickage-raw', prefix+'/_SUCCESS')
        metadata('pickage-raw', prefix+'/source_manifest.json')
        files = manifest.get('files',[])
        missing = [f['key'] for f in files if f['key'] not in obj_map]
        wrong_size = [f['key'] for f in files if f['key'] in obj_map and obj_map[f['key']]['bytes'] != f['bytes']]
        result['selected_checks'].append({'key':key,'status':manifest.get('status'),
           'verification':manifest.get('verification'),'file_count':len(files),
           'data_bytes':sum(f['bytes'] for f in files),'missing':missing,'size_mismatches':wrong_size,
           'payload_sha256_rechecked':False})
    curated = inventory('pickage-curated','depsdev/v1/package-version/')
    for r in curated:
        if r['key'].endswith('/run_manifest.json') or r['key'].endswith('/_current.json'):
            metadata('pickage-curated',r['key'])
else:
    inventory('pickage-raw','depsdev/v1/requirements/snapshot=2026-08-31/')
downloads = inventory('pickage-raw','npm-downloads/v1/')
inventory('pickage-raw','targets/')
for r in downloads:
    if r['key'].endswith(('/run_manifest.json','/_SUCCESS','/_INPUT.json')):
        metadata('pickage-raw',r['key'])
print(json.dumps(result, ensure_ascii=False))
