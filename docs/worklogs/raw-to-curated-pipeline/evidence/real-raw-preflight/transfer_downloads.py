"""Copy the pinned downloads run using the existing immutable Bronze publisher.

Run from the experiment worktree. Requires a task-owned SSH tunnel on 19002.
Source credentials and server credentials are read locally and never logged.
No objects are deleted; existing different objects cause failure.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
import time

import boto3
from botocore.config import Config

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
from pipeline.downloads.bronze import publish, _json_bytes, _file_hash

RUN = 'downloads-278-20260909-v1'
PREFIX = 'npm-downloads/v1/run_id=' + RUN
BUCKET = 'pickage-raw'
SHA = '0617c12a1c810ecc11fcc01e281e375a8c1aa53bdb5ba57dab15a61120eec35d'
REPORT = Path(__file__).with_name('downloads-transfer.json')
CACHE = ROOT / 'data' / 'downloads-transfer' / RUN

def client(role, endpoint):
    path = Path('C:/Users/SSAFY/workspace/S15P21A506/pipeline/minio') / ('.env.'+role+'.local')
    env = dict(line.split('=',1) for line in path.read_text().splitlines()
               if line and not line.startswith('#') and '=' in line)
    return boto3.client('s3', endpoint_url=endpoint,
        aws_access_key_id=env['MINIO_ROOT_USER'], aws_secret_access_key=env['MINIO_ROOT_PASSWORD'],
        region_name='us-east-1', config=Config(connect_timeout=10, read_timeout=90,
            retries={'max_attempts':3}, max_pool_connections=8, s3={'addressing_style':'path'}))

def read(s3, key):
    body = s3.get_object(Bucket=BUCKET, Key=key)['Body']
    try: return body.read()
    finally: body.close()

def inventory(s3):
    return {r['Key']:r['Size'] for page in s3.get_paginator('list_objects_v2').paginate(
        Bucket=BUCKET, Prefix=PREFIX+'/') for r in page.get('Contents', [])}

report = {'started_at':datetime.now(timezone.utc).isoformat(),'status':'PREFLIGHT',
          'run_id':RUN,'bucket':BUCKET,'prefix':PREFIX,'manifest_sha256':SHA,
          'source_endpoint':'http://localhost:9000',
          'destination':'data server MinIO via task SSH tunnel 127.0.0.1:19002',
          'source_deleted':False,'db_modified':False,'curated_modified':False}

def save():
    tmp = REPORT.with_suffix('.tmp')
    tmp.write_text(json.dumps(report,indent=2),encoding='utf-8')
    tmp.replace(REPORT)

class ObservedDestination:
    def __init__(self, s3):
        self.s3=s3
        self.puts=0
    def __getattr__(self, name): return getattr(self.s3,name)
    def put_object(self, **kwargs):
        result=self.s3.put_object(**kwargs)
        if '/data/' in kwargs['Key']:
            self.puts+=1
            if self.puts % 100 == 0:
                report['data_puts']=self.puts
                save()
                print('Destination uploads:',self.puts,flush=True)
        return result

def main():
    started=time.monotonic()
    save()
    source=client('source','http://localhost:9000')
    dest=client('server','http://127.0.0.1:19002')
    try:
        manifest_body=read(source,PREFIX+'/run_manifest.json')
        assert hashlib.sha256(manifest_body).hexdigest()==SHA, 'Pinned source manifest changed'
        manifest=json.loads(manifest_body)
        assert _json_bytes(manifest)==manifest_body, 'Publisher would change manifest bytes'
        assert manifest['run_id']==RUN and manifest['dataset']=='npm-downloads'
        assert all(v is True for v in manifest['quality']['consistency_checks'].values())
        input_body=read(source,PREFIX+'/_INPUT.json')
        success_body=read(source,PREFIX+'/_SUCCESS')
        assert input_body==_json_bytes({'manifest_sha256':SHA})
        assert success_body==(SHA+'\n').encode('ascii')
        expected={PREFIX+'/data/'+f['path']:f['bytes'] for f in manifest['files']}
        assert len(expected)==len(manifest['files'])
        expected.update({PREFIX+'/run_manifest.json':len(manifest_body),
                         PREFIX+'/_INPUT.json':len(input_body),PREFIX+'/_SUCCESS':len(success_body)})
        assert inventory(source)==expected, 'Source run object inventory differs'
        existing=inventory(dest)
        assert not (set(existing)-set(expected)), 'Unexpected destination objects'
        report.update(initial_destination_objects=len(existing),data_file_count=len(manifest['files']),
                      data_bytes=sum(f['bytes'] for f in manifest['files']),object_count=len(expected),
                      total_object_bytes=sum(expected.values()),status='VERIFY_SOURCE')
        CACHE.mkdir(parents=True,exist_ok=True)
        def download(record):
            relative=PurePosixPath(record['path'])
            assert not relative.is_absolute() and relative.as_posix()==record['path']
            assert not any(part in ('..','.') for part in relative.parts)
            path=CACHE/relative
            assert path.resolve().is_relative_to(CACHE.resolve())
            if path.exists():
                assert _file_hash(path)==(record['bytes'],record['sha256']), 'Cached source changed'
                return
            path.parent.mkdir(parents=True,exist_ok=True)
            tmp=path.with_suffix(path.suffix+'.transfer-part')
            response=source.get_object(Bucket=BUCKET,Key=PREFIX+'/data/'+record['path'])['Body']
            checksum=hashlib.sha256();size=0
            try:
                with tmp.open('wb') as out:
                    for block in iter(lambda:response.read(1024*1024),b''):
                        out.write(block);checksum.update(block);size+=len(block)
            finally: response.close()
            assert (size,checksum.hexdigest())==(record['bytes'],record['sha256']), 'Source payload differs'
            tmp.replace(path)
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures=[pool.submit(download,f) for f in manifest['files']]
            for n,future in enumerate(as_completed(futures),1):
                future.result()
                if n%100==0 or n==len(futures):
                    report['source_files_get_sha256_verified']=n;save()
                    print('Source verified:',n,'/',len(futures),flush=True)
        def source_unchanged():
            assert read(source,PREFIX+'/run_manifest.json')==manifest_body
            assert read(source,PREFIX+'/_INPUT.json')==input_body
            assert read(source,PREFIX+'/_SUCCESS')==success_body
            assert inventory(source)==expected
        source_unchanged()
        report['status']='COPY_AND_VERIFY_DESTINATION';save()
        observed=ObservedDestination(dest)
        outcome=publish(observed,bucket=BUCKET,prefix=PREFIX,root=CACHE,manifest=manifest,
                        before_commit=source_unchanged)
        assert read(dest,PREFIX+'/run_manifest.json')==manifest_body
        assert read(dest,PREFIX+'/_INPUT.json')==input_body
        assert read(dest,PREFIX+'/_SUCCESS')==success_body
        assert inventory(dest)==expected
        source_unchanged()
        report.update(status='VERIFIED',publisher_result=outcome,data_puts=observed.puts,
            destination_files_get_sha256_verified=len(manifest['files']),
            exact_metadata_bytes_preserved=True,exact_object_inventory=True,
            verification='GET_SHA256_ALL_FILES',success_published_last=True)
        print('VERIFIED:',len(expected),'objects;',report['data_bytes'],'payload bytes',flush=True)
    except BaseException as error:
        report.update(status='FAILED',error_type=type(error).__name__,error=str(error))
        raise
    finally:
        report.update(finished_at=datetime.now(timezone.utc).isoformat(),
                      elapsed_seconds=round(time.monotonic()-started,3))
        save()

if __name__=='__main__': main()
