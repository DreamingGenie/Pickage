"""Register exactly the pinned target Parquet; requires task SSH tunnel 19002."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import boto3
from botocore.config import Config
import duckdb

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
from pipeline.downloads.bronze import _same_or_put, _read
from pipeline.orchestration.contracts import validate_request

EVIDENCE = Path(__file__).parent

def inspect(path):
    with duckdb.connect(config={'threads':1, 'memory_limit':'256MB'}) as con:
        schema = con.execute('DESCRIBE SELECT * FROM read_parquet(?, hive_partitioning=false)', [str(path)]).fetchall()
        counts = con.execute("SELECT count(*), count(DISTINCT name), count(*) FILTER "
            "(WHERE name IS NULL OR trim(name)='' OR name<>trim(name) OR contains(name,chr(0))) "
            "FROM read_parquet(?, hive_partitioning=false)", [str(path)]).fetchone()
    assert [(r[0],r[1]) for r in schema] == [('name','VARCHAR')], 'Wrong target schema'
    assert counts == (99996,99996,0), 'Target names changed or invalid'
    return {'schema':[['name','VARCHAR']], 'rows':counts[0], 'unique_names':counts[1], 'invalid_names':counts[2]}

def main():
    selected = json.loads((EVIDENCE/'targets-selection.json').read_text())
    request = json.loads((EVIDENCE/'request.pending.json').read_text())
    validate_request(request)
    ref = request['targets']['dependents']
    assert ref == {'bucket':'pickage-raw', 'key':selected['proposed_server_key'], 'sha256':selected['output_sha256']}
    source = Path(selected['output_path'])
    body = source.read_bytes()
    assert len(body)==selected['output_bytes'] and hashlib.sha256(body).hexdigest()==ref['sha256']
    inspect(source)
    env_path = Path('C:/Users/SSAFY/workspace/S15P21A506/pipeline/minio/.env.server.local')
    env = dict(line.split('=',1) for line in env_path.read_text().splitlines()
               if line and not line.startswith('#') and '=' in line)
    s3 = boto3.client('s3', endpoint_url='http://127.0.0.1:19002',
        aws_access_key_id=env['MINIO_ROOT_USER'], aws_secret_access_key=env['MINIO_ROOT_PASSWORD'],
        region_name='us-east-1', config=Config(connect_timeout=10,read_timeout=30,
            retries={'max_attempts':2},s3={'addressing_style':'path'}))
    report = {'started_at':datetime.now(timezone.utc).isoformat(), 'status':'REGISTERING',
              'destination':'data server MinIO via task SSH tunnel 19002', **ref}
    report_path = EVIDENCE/'targets-registration.json'
    try:
        report_path.write_text(json.dumps(report,indent=2),encoding='utf-8')
        created = _same_or_put(s3, ref['bucket'], ref['key'], body)
        remote = _read(s3, ref['bucket'], ref['key'])
        assert remote == body, 'Server bytes differ'
        downloaded = source.with_name('dependents-targets.server-verified.parquet')
        downloaded.write_bytes(remote)
        verified = inspect(downloaded)
        report.update(status='VERIFIED', action='CREATED' if created else 'REVERIFIED_EXISTING',
                      bytes=len(remote), **verified, verification='GET_SHA256_AND_PARQUET_VALIDATION',
                      server_sha256=hashlib.sha256(remote).hexdigest(),request_reference_matches=True)
    except BaseException as error:
        report.update(status='FAILED', error_type=type(error).__name__,error=str(error))
        raise
    finally:
        report['finished_at']=datetime.now(timezone.utc).isoformat()
        report_path.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))

if __name__=='__main__': main()
