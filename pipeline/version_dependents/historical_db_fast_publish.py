"""Durable daily COPY/constraint/partition publication into a separate reload schema.

Public reference and lineage tables are read only. Service cutover is deliberately
separate from building the replacement dataset. The original paused loader is not
modified, and each day's data and ETL receipt commit together.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
import json
from pathlib import Path
import re
import time
import uuid

from pipeline.postgresql.postgres import PgLoader
from pipeline.requirements_resolution.policy import sha256
from .historical_db_keys import _calendar_values, _date, _timestamp, check_lineage, copy_file
from .historical_db_publish import HistoricalCountLoader

COLUMNS = 'package_id,version,snapshot_at,dependents_count'
BODY = "(package_id integer NOT NULL,version varchar(100) NOT NULL,snapshot_at date NOT NULL,dependents_count integer NOT NULL DEFAULT 0 CONSTRAINT dependents_nonnegative CHECK(dependents_count>=0))"
HISTORY = ('etl_load_execution', 'etl_load_attempt', 'etl_dataset_current')


def target_schema(value):
    if not isinstance(value, str) or not re.fullmatch(r'vd193_reload_[a-z0-9_]{1,40}', value):
        raise ValueError('Use a dedicated vd193_reload_ schema')
    return value


class FastCountLoader(HistoricalCountLoader):
    def __init__(self, command, work_dir, schema, plan):
        super().__init__(command, work_dir)
        self.schema = target_schema(schema)
        if not isinstance(plan, dict) or plan.get('schema') != schema:
            raise ValueError('Plan target differs')
        self.plan = plan
        self.plan_sha = sha256(plan)
        self.generation_sha = sha256(plan['generation'])
        self.initialized = False

    def __enter__(self):
        super().__enter__()
        try:
            self._send("SET application_name='vd193-fast-reload';")
            for dataset in ('package-version', 'version-dependents'):
                if self._send(f"SELECT pg_try_advisory_lock(hashtextextended('curated:{dataset}',0));") != ['t']:
                    raise RuntimeError(f'Another {dataset} load is active')
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def table(self, name):
        if name not in (*HISTORY, 'package_version_snapshot', 'reload_plan', 'reload_partition') and not re.fullmatch(r'd\d{8}', name):
            raise ValueError('Unexpected reload relation')
        return f'{self.schema}.{name}'

    def scalar(self, sql):
        return self._send(sql)[0]

    def relation_contract(self, name):
        table = self.table(name)
        return json.loads(self.scalar(f"SELECT json_build_object('kind',relkind,'owner',relowner::bigint,'acl',relacl::text,'rls',relrowsecurity,'partition_key',pg_get_partkeydef(c.oid),'bound',pg_get_expr(relpartbound,c.oid),'columns',(SELECT json_agg(json_build_array(attname,format_type(atttypid,atttypmod),attnotnull,pg_get_expr(d.adbin,d.adrelid)) ORDER BY attnum) FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum WHERE a.attrelid=c.oid AND attnum>0 AND NOT attisdropped),'constraints',(SELECT json_agg(json_build_array(contype,pg_get_constraintdef(oid),convalidated,conparentid::bigint) ORDER BY conname) FROM pg_constraint WHERE conrelid=c.oid),'indexes',(SELECT json_agg(json_build_array(indisprimary,indisunique,indisvalid,indisready,indkey::text) ORDER BY indexrelid) FROM pg_index WHERE indrelid=c.oid)) FROM pg_class c WHERE oid='{table}'::regclass;"))

    def service_contract(self):
        """Pin the existing contract, including privileges and attached dependencies."""
        result = json.loads(self.scalar("SELECT json_build_object('columns',(SELECT json_agg(json_build_array(attname,format_type(atttypid,atttypmod),attnotnull,pg_get_expr(d.adbin,d.adrelid)) ORDER BY attnum) FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum WHERE a.attrelid='public.package_version_snapshot'::regclass AND attnum>0 AND NOT attisdropped),'constraints',(SELECT json_agg(pg_get_constraintdef(oid) ORDER BY conname) FROM pg_constraint WHERE conrelid='public.package_version_snapshot'::regclass),'oid','public.package_version_snapshot'::regclass::oid::bigint,'owner',pg_get_userbyid(relowner),'acl',relacl::text,'rls',relrowsecurity,'rules',relhasrules,'triggers',(SELECT count(*) FROM pg_trigger WHERE tgrelid=c.oid AND NOT tgisinternal)) FROM pg_class c WHERE oid='public.package_version_snapshot'::regclass;"))
        expected = [['package_id','integer',True,None], ['version','character varying(100)',True,None],
                    ['snapshot_at','date',True,None], ['dependents_count','integer',True,'0']]
        definitions = set(result['constraints'] or [])
        # 음수 금지 CHECK 는 V7(2026-09-15, S15P21A506-341)이 서비스 표에 붙였다.
        # 이 검사는 2026-09-12 에 쓰였으므로 그때는 없던 제약이다. 그대로 두면
        # V7 이후의 모든 DB(운영 포함)가 "네 열 계약과 다르다"며 적재를 거부한다.
        required = {'PRIMARY KEY (package_id, version, snapshot_at)',
                    'FOREIGN KEY (package_id, version) REFERENCES version(package_id, version)',
                    'FOREIGN KEY (snapshot_at) REFERENCES snapshot(snapshot_at)',
                    'CHECK ((dependents_count >= 0))'}
        if result['columns'] != expected or definitions != required or result['rls'] or result['rules'] or result['triggers']:
            raise ValueError('Service DDL differs from the verified four-column contract; review before reload')
        return result

    def inspect_target(self):
        self._require("current_setting('server_version_num')::integer>=160000 AND current_setting('server_version_num')::integer<170000 AND has_database_privilege(current_database(),'CREATE') AND has_schema_privilege('public','USAGE') AND has_table_privilege('public.version','SELECT') AND has_table_privilege('public.version','REFERENCES') AND has_table_privilege('public.snapshot','SELECT') AND has_table_privilege('public.snapshot','REFERENCES')", 'PostgreSQL version/permissions differ from verified reload environment')
        contract = self.service_contract()
        exists = self._send(f"SELECT nspowner=(SELECT oid FROM pg_roles WHERE rolname=current_user) FROM pg_namespace WHERE nspname={self._literal(self.schema)};")
        if not exists:
            return {'exists': False, 'completed_dates': 0, 'completed_rows': 0, 'service_contract': contract}
        if exists != ['t']:
            raise ValueError('Reload schema owner differs')
        saved = json.loads(self.scalar(f'SELECT row_to_json(p) FROM {self.table("reload_plan")} p WHERE singleton;'))
        if saved['plan'] != self.plan or saved['plan_sha'] != self.plan_sha or saved['service_contract'] != contract:
            raise ValueError('Stored reload plan/code/input/service contract differs')
        parent = self.table('package_version_snapshot')
        if int(self.scalar(f"SELECT '{parent}'::regclass::oid;")) != int(saved['parent_oid']):
            raise ValueError('Reload parent identity changed')
        if saved['target_contracts'] != {name:self.relation_contract(name) for name in ('package_version_snapshot',*HISTORY)}:
            raise ValueError('Reload parent/history schema constraints changed')
        self._require(f"NOT EXISTS(SELECT 1 FROM {self.table('reload_partition')} r FULL JOIN pg_inherits i ON i.inhrelid=r.child_oid AND i.inhparent='{parent}'::regclass WHERE (i.inhparent='{parent}'::regclass OR r.snapshot_at IS NOT NULL) AND (r.snapshot_at IS NULL OR i.inhrelid IS NULL))", 'Partition and receipt coverage differ')
        self._require(f"NOT EXISTS(SELECT 1 FROM {self.table('reload_partition')} r LEFT JOIN {self.table('etl_load_execution')} e USING(execution_id) WHERE e.status IS DISTINCT FROM 'PUBLISHED' OR e.snapshot_at IS DISTINCT FROM r.snapshot_at OR e.contract_sha256 IS DISTINCT FROM {self._literal(self.generation_sha)})", 'Receipt and execution disagree')
        receipts = json.loads(self.scalar(f"SELECT coalesce(json_agg(row_to_json(r) ORDER BY snapshot_at),'[]') FROM {self.table('reload_partition')} r;"))
        for receipt in receipts:
            day = receipt['snapshot_at']
            if day not in self.plan['dates'] or receipt['rows'] != self.plan['rows_by_date'][day]:
                raise ValueError('Receipt date/rows differ from planned population')
            name = 'd'+day.replace('-','')
            if self.relation_contract(name) != receipt['table_contract']:
                raise ValueError('Published partition constraints or date bounds changed')
            if int(self.scalar(f'SELECT count(*) FROM {self.table(name)};')) != receipt['rows']:
                raise ValueError('Stored row count differs from published receipt')
            entry = json.loads(self.scalar(f"SELECT row_to_json(e) FROM {self.table('etl_load_execution')} e WHERE execution_id={self._literal(receipt['execution_id'])};"))
            record = next((r for r in entry['input_metadata']['files'] if r['role']=='counts'), {})
            if (record.get('sha256') != receipt['input_sha'] or record.get('rows') != receipt['rows']
                    or entry['input_metadata']['quality'] != receipt['quality']
                    or sha256(entry['input_metadata']) != entry['manifest_sha256']):
                raise ValueError('Partition input/quality differs from execution manifest')
        stats = {'completed_dates':len(receipts), 'completed_rows':sum(r['rows'] for r in receipts)}
        pointers = json.loads(self.scalar(f"SELECT coalesce(json_agg(row_to_json(c)),'[]') FROM {self.table('etl_dataset_current')} c;"))
        if receipts:
            latest = receipts[-1]
            latest_execution = json.loads(self.scalar(f"SELECT row_to_json(e) FROM {self.table('etl_load_execution')} e WHERE execution_id={self._literal(latest['execution_id'])};"))
            if (len(pointers) != 1 or pointers[0]['dataset'] != 'version-dependents'
                    or pointers[0]['snapshot_at'] != latest['snapshot_at']
                    or pointers[0]['execution_id'] != latest['execution_id']
                    or pointers[0]['manifest_sha256'] != latest_execution['manifest_sha256']
                    or pointers[0]['manifest'] != latest_execution['input_metadata']):
                raise ValueError('Current pointer differs from latest published partition')
        elif pointers:
            raise ValueError('Current pointer exists without published partitions')
        ready = stats['completed_dates'] == self.plan['expected_dates'] and stats['completed_rows'] == self.plan['expected_rows']
        return {'exists': True, **stats, 'ready':ready, 'service_contract': contract,
                'value_check':'Counts and structure verified; full value comparison runs per date during resume/load'}

    def initialize(self):
        current = self.inspect_target()
        if current['exists']:
            self.initialized = True
            return current
        q = self._literal
        self._send('BEGIN;')
        try:
            self._send(f'CREATE SCHEMA {self.schema}; REVOKE ALL ON SCHEMA {self.schema} FROM PUBLIC;')
            self._send(f"CREATE TABLE {self.table('package_version_snapshot')}{BODY} PARTITION BY RANGE(snapshot_at);")
            self.add_keys('package_version_snapshot')
            # LIKE copies defaults/checks/indexes, not foreign keys. Recreate the
            # common ETL composite references inside this target only.
            for name in HISTORY:
                self._send(f'CREATE TABLE {self.table(name)} (LIKE public.{name} INCLUDING ALL);')
            execution, attempt, current_table = (self.table(name) for name in HISTORY)
            self._send(f'ALTER TABLE {attempt} ADD FOREIGN KEY(execution_id) REFERENCES {execution}(execution_id); ALTER TABLE {execution} ADD FOREIGN KEY(execution_id,active_attempt_id) REFERENCES {attempt}(execution_id,attempt_id) DEFERRABLE INITIALLY DEFERRED; ALTER TABLE {current_table} ADD FOREIGN KEY(dataset,execution_id,snapshot_at,manifest_sha256) REFERENCES {execution}(dataset,execution_id,snapshot_at,manifest_sha256);')
            self._send(f"CREATE TABLE {self.table('reload_plan')}(singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),plan_sha text NOT NULL,plan jsonb NOT NULL,service_contract jsonb NOT NULL,parent_oid oid NOT NULL,target_contracts jsonb NOT NULL); CREATE TABLE {self.table('reload_partition')}(snapshot_at date PRIMARY KEY,execution_id varchar(200) UNIQUE NOT NULL REFERENCES {execution}(execution_id),child_oid oid UNIQUE NOT NULL,input_sha text NOT NULL,rows bigint NOT NULL CHECK(rows>=0),quality jsonb NOT NULL,table_contract jsonb NOT NULL);")
            parent = self.table('package_version_snapshot')
            self._send(f'REVOKE ALL ON ALL TABLES IN SCHEMA {self.schema} FROM PUBLIC;')
            contracts = {name:self.relation_contract(name) for name in ('package_version_snapshot',*HISTORY)}
            self._send(f"INSERT INTO {self.table('reload_plan')} VALUES(true,{q(self.plan_sha)},{q(self.plan)},{q(current['service_contract'])},'{parent}'::regclass::oid,{q(contracts)}); COMMIT;")
        except BaseException:
            self._rollback()
            raise
        self.initialized = True
        return self.inspect_target()

    def add_keys(self, name):
        self._send(f'ALTER TABLE {self.table(name)} ADD PRIMARY KEY(package_id,version,snapshot_at);')
        self.add_foreign_keys(name)

    def add_foreign_keys(self, name):
        self._send(f'ALTER TABLE {self.table(name)} ADD CONSTRAINT version_fk FOREIGN KEY(package_id,version) REFERENCES public.version(package_id,version), ADD CONSTRAINT snapshot_fk FOREIGN KEY(snapshot_at) REFERENCES public.snapshot(snapshot_at);')

    def _phase(self, phase):
        self.phase = phase
        if self._registered:
            self._send(f"UPDATE {self.table('etl_load_attempt')} SET phase={self._literal(phase)} WHERE attempt_id={self._literal(self._attempt_id)};")

    def _rollback(self):
        if self._process and self._process.poll() is None:
            try:
                self._send('ROLLBACK;')
            except (RuntimeError, OSError):
                pass

    def validate_metadata(self, metadata):
        if metadata.get('dataset') != 'version-dependents':
            raise ValueError('Unsupported dataset')
        manifest = metadata.get('manifest')
        if not isinstance(manifest, dict) or metadata.get('manifest_sha256') != sha256(manifest):
            raise ValueError('Manifest hash mismatch')
        day, stamp = _date(metadata.get('snapshot')), _timestamp(metadata.get('snapshot_timestamp'))
        if day not in self.plan['dates'] or (day, stamp) not in _calendar_values(manifest.get('calendar')):
            raise ValueError('Date not in pinned calendar')
        counts = metadata.get('counts', {})
        if set(counts) != {'identities', 'package_version_snapshot'} or any(type(v) is not int or v < 0 for v in counts.values()):
            raise ValueError('Invalid counts')
        if counts['package_version_snapshot'] != self.plan['rows_by_date'][day]:
            raise ValueError('Date row count differs from plan')
        quality = manifest.get('quality', {})
        if quality.get('calculation_status') != 'COMPLETE' or quality.get('resolution_status') not in ('PARTIAL', 'COMPLETE'):
            raise ValueError('Calculation quality is not publishable')
        return day, quality

    def register(self, metadata, execution_id):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', execution_id):
            raise ValueError('Invalid execution ID')
        self._metadata, self._execution_id, self._attempt_id = metadata, execution_id, uuid.uuid4().hex
        self._registered = False
        q, e, a = self._literal, self.table('etl_load_execution'), self.table('etl_load_attempt')
        prior = self._send(f'SELECT row_to_json(e) FROM {e} e WHERE execution_id={q(execution_id)};')
        if prior:
            row = json.loads(prior[0])
            fields = {'dataset':'version-dependents','snapshot_at':metadata['snapshot'], 'curated_run_id':metadata['curated_run_id'],
                      'run_prefix':metadata['run_prefix'],'manifest_sha256':metadata['manifest_sha256'],
                      'input_metadata':metadata['manifest'],'expected_counts':metadata['counts'],'contract_sha256':self.generation_sha}
            if any(row.get(k) != v for k,v in fields.items()) or datetime.fromisoformat(row['snapshot_timestamp']) != datetime.fromisoformat(_timestamp(metadata['snapshot_timestamp']).replace('Z','+00:00')).replace(tzinfo=None):
                raise ValueError('Published input or code differs')
        values = [execution_id,'version-dependents','PREPARING',metadata['snapshot'],metadata['snapshot_timestamp'],
                  metadata['curated_run_id'],metadata['run_prefix'],metadata['manifest_sha256'],self.generation_sha,
                  metadata['manifest'],metadata['counts'],self._attempt_id]
        self._send(f"BEGIN; UPDATE {a} SET status='FAILED',phase='ABANDONED',completed_at=clock_timestamp(),error_message='Prior session ended' WHERE execution_id={q(execution_id)} AND status='PREPARING'; INSERT INTO {e}(execution_id,dataset,status,snapshot_at,snapshot_timestamp,curated_run_id,run_prefix,manifest_sha256,contract_sha256,input_metadata,expected_counts,active_attempt_id) VALUES({','.join(q(v) for v in values)}) ON CONFLICT(execution_id) DO UPDATE SET active_attempt_id=EXCLUDED.active_attempt_id,status=CASE WHEN etl_load_execution.status='PUBLISHED' THEN 'PUBLISHED' ELSE 'PREPARING' END,error_message=NULL,updated_at=clock_timestamp(); INSERT INTO {a}(attempt_id,execution_id,status,phase,validation_contract_sha256) VALUES({q(self._attempt_id)},{q(execution_id)},'PREPARING','VALIDATE_INPUT',{q(self.generation_sha)}); COMMIT;")
        self._registered = True

    def copy_counts_to(self, table, path):
        if table != 'pg_temp._h7_counts' and table != self.table('d'+self._metadata['snapshot'].replace('-','')):
            raise ValueError('COPY outside current date is forbidden')
        path = Path(path)
        with path.open('rb') as stream:
            if path.stat().st_size:
                stream.seek(-1, 2)
                if stream.read(1) != b'\n':
                    raise ValueError('COPY input must end with LF')
            stream.seek(0)
            self._process.stdin.write(f"COPY {table}({COLUMNS}) FROM STDIN WITH(FORMAT text,NULL '\\N',ENCODING 'UTF8');\n".encode())
            for block in iter(lambda: stream.read(1024*1024), b''):
                self._process.stdin.write(block)
            self._process.stdin.write(b'\\.\n')
            self._process.stdin.flush()
        self._send('SELECT 1;')

    def exact_values(self, table):
        self._require(f'NOT EXISTS(SELECT 1 FROM {table} t FULL JOIN pg_temp._h7_counts s USING(package_id,version,snapshot_at) WHERE t.package_id IS NULL OR s.package_id IS NULL OR t.dependents_count IS DISTINCT FROM s.dependents_count)', 'Stored values differ from pinned input')

    def publish_day(self, metadata, files, execution_id, before_commit, failpoint=None):
        if not self.initialized:
            raise RuntimeError('initialize() is required')
        if failpoint not in (None,'after_copy','after_attach','before_commit','after_commit'):
            raise ValueError('Unknown failpoint')
        day, quality = self.validate_metadata(metadata)
        if not callable(before_commit):
            raise ValueError('Source recheck callback is required')
        self.register(metadata, execution_id)
        started, metrics = time.perf_counter(), {}
        q, parent, child_name = self._literal, self.table('package_version_snapshot'), 'd'+day.replace('-','')
        child, receipt = self.table(child_name), self.table('reload_partition')
        try:
            self._validate_manifest_files(files)
            self._phase('PREPARE_DATE')
            self._send('BEGIN; LOCK TABLE public.package,public.version,public.snapshot,public.etl_snapshot_reference,public.etl_load_execution,public.etl_dataset_current IN SHARE MODE;')
            check_lineage(self, metadata['manifest']['lineage'], metadata['manifest']['calendar'])
            self._send("CREATE TEMP TABLE _h7_identities(package_id integer NOT NULL CHECK(package_id>0),name varchar(300) NOT NULL CHECK(length(trim(name))>0)) ON COMMIT DROP; CREATE TEMP TABLE _h7_counts(package_id integer NOT NULL CHECK(package_id>0),version varchar(100) NOT NULL CHECK(length(trim(version))>0),snapshot_at date NOT NULL,dependents_count integer NOT NULL CHECK(dependents_count>=0)) ON COMMIT DROP;")
            tick = time.perf_counter()
            copy_file(self, '_h7_identities', ('package_id','name'), files['identities'])
            self.copy_counts_to('pg_temp._h7_counts', files['counts'])
            self._send('CREATE UNIQUE INDEX ON pg_temp._h7_identities(package_id); CREATE UNIQUE INDEX ON pg_temp._h7_identities(name); CREATE UNIQUE INDEX ON pg_temp._h7_counts(package_id,version,snapshot_at); ANALYZE pg_temp._h7_identities; ANALYZE pg_temp._h7_counts;')
            metrics['staging_seconds'] = time.perf_counter()-tick
            expected = metadata['counts']['package_version_snapshot']
            self._require(f"(SELECT count(*) FROM pg_temp._h7_identities)={metadata['counts']['identities']} AND NOT EXISTS(SELECT 1 FROM pg_temp._h7_identities i LEFT JOIN public.package p USING(package_id) WHERE p.name IS DISTINCT FROM i.name) AND NOT EXISTS(SELECT 1 FROM pg_temp._h7_counts c LEFT JOIN pg_temp._h7_identities i USING(package_id) WHERE i.package_id IS NULL) AND NOT EXISTS(SELECT 1 FROM pg_temp._h7_counts WHERE snapshot_at<>{q(day)}::date)", 'Identity/date validation failed')
            actual = json.loads(self.scalar("SELECT json_build_object('target_versions',count(*),'positive_target_versions',count(*) FILTER(WHERE dependents_count>0),'zero_target_versions',count(*) FILTER(WHERE dependents_count=0),'distinct_edges',coalesce(sum(dependents_count),0)) FROM pg_temp._h7_counts;"))
            if actual['target_versions'] != expected or any(quality.get(k) != v for k,v in actual.items()):
                raise ValueError('Quality aggregates differ')
            self._send(f'LOCK TABLE {parent} IN SHARE UPDATE EXCLUSIVE MODE;')
            prior_rows = self._send(f'SELECT row_to_json(r) FROM {receipt} r WHERE snapshot_at={q(day)}::date;')
            prior = json.loads(prior_rows[0]) if prior_rows else None
            oid = self.scalar(f'SELECT to_regclass({q(child)})::oid;')
            if prior:
                if prior['execution_id'] != execution_id or str(prior['child_oid']) != oid or prior['rows'] != expected or prior['quality'] != quality or prior['input_sha'] != next(r['sha256'] for r in metadata['manifest']['files'] if r['role']=='counts'):
                    raise ValueError('Published partition receipt differs')
                self._send(f'LOCK TABLE {child} IN ACCESS EXCLUSIVE MODE;')
                self._require(f"EXISTS(SELECT 1 FROM pg_inherits WHERE inhrelid='{child}'::regclass AND inhparent='{parent}'::regclass)", 'Published partition is detached')
            else:
                if oid:
                    raise ValueError('Unrecorded date table exists; automatic replacement refused')
                self._send(f'CREATE TABLE {child}{BODY}; ALTER TABLE {child} ADD CONSTRAINT date_bound CHECK(snapshot_at={q(day)}::date); REVOKE ALL ON {child} FROM PUBLIC;')
                tick = time.perf_counter()
                self.copy_counts_to(child, files['counts'])
                metrics['copy_seconds'] = time.perf_counter()-tick
                if failpoint == 'after_copy':
                    raise RuntimeError('injected after_copy')
                tick = time.perf_counter()
                self._send(f'ALTER TABLE {child} ADD PRIMARY KEY(package_id,version,snapshot_at);')
                metrics['pk_seconds'] = time.perf_counter()-tick
                tick = time.perf_counter()
                self.add_foreign_keys(child_name)
                metrics['fk_seconds'] = time.perf_counter()-tick
            tick = time.perf_counter()
            self.exact_values(child)
            self._require(f"(SELECT count(*) FROM pg_constraint WHERE conrelid='{child}'::regclass AND contype='f' AND convalidated)=2 AND EXISTS(SELECT 1 FROM pg_index WHERE indrelid='{child}'::regclass AND indisprimary AND indisvalid)", 'Date PK/FK validation failed')
            metrics['value_verification_seconds'] = time.perf_counter()-tick
            if not prior:
                pk = self.scalar(f"SELECT indexrelid::text FROM pg_index WHERE indrelid='{child}'::regclass AND indisprimary;")
                tick = time.perf_counter()
                end = (date.fromisoformat(day)+timedelta(days=1)).isoformat()
                self._send(f'ALTER TABLE {parent} ATTACH PARTITION {child} FOR VALUES FROM ({q(day)}) TO ({q(end)});')
                metrics['attach_seconds'] = time.perf_counter()-tick
                self._require(f"EXISTS(SELECT 1 FROM pg_index WHERE indrelid='{child}'::regclass AND indexrelid={int(pk)} AND indisprimary AND indisvalid) AND (SELECT count(*) FROM pg_constraint WHERE conrelid='{child}'::regclass AND contype='f' AND convalidated AND conparentid<>0)=2", 'Attached constraints were not reused')
                if failpoint == 'after_attach':
                    raise RuntimeError('injected after_attach')
                file_sha = next(r['sha256'] for r in metadata['manifest']['files'] if r['role']=='counts')
                child_contract = self.relation_contract(child_name)
                self._send(f"INSERT INTO {receipt} VALUES({q(day)},{q(execution_id)},'{child}'::regclass::oid,{q(file_sha)},{expected},{q(quality)},{q(child_contract)}); ANALYZE {child};")
            tick = time.perf_counter()
            before_commit()
            self._validate_manifest_files(files)
            metrics['before_commit_seconds'] = time.perf_counter()-tick
            counts = {**metadata['counts'], 'verified_rows': expected}
            e, a, c = (self.table(n) for n in HISTORY)
            self._send(f"UPDATE {a} SET status={q('REVERIFIED' if prior else 'PUBLISHED')},phase='COMMIT',actual_counts={q(counts)},quality_report={q(quality)},completed_at=clock_timestamp() WHERE attempt_id={q(self._attempt_id)}; UPDATE {e} SET status='PUBLISHED',actual_counts={q(counts)},error_message=NULL,updated_at=clock_timestamp() WHERE execution_id={q(execution_id)} AND active_attempt_id={q(self._attempt_id)};")
            values = ['version-dependents',execution_id,day,metadata['manifest_sha256'],metadata['manifest']]
            self._send(f"INSERT INTO {c}(dataset,execution_id,snapshot_at,manifest_sha256,manifest) VALUES({','.join(q(v) for v in values)}) ON CONFLICT(dataset) DO UPDATE SET execution_id=EXCLUDED.execution_id,snapshot_at=EXCLUDED.snapshot_at,manifest_sha256=EXCLUDED.manifest_sha256,manifest=EXCLUDED.manifest,published_at=clock_timestamp() WHERE etl_dataset_current.snapshot_at<=EXCLUDED.snapshot_at;")
            if failpoint == 'before_commit':
                raise RuntimeError('injected before_commit')
            self._send('COMMIT;')
            if failpoint == 'after_commit':
                raise RuntimeError('injected lost_commit_response')
            metrics['total_seconds'] = time.perf_counter()-started
            self.phase = 'COMPLETE'
            return {'status':'PUBLISHED','action':'REVERIFIED' if prior else 'LOADED','counts':counts,
                    'execution_id':execution_id,'attempt_id':self._attempt_id,'metrics':metrics,
                    'target':child,'inserted_rows':0 if prior else expected}
        except BaseException as error:
            self.fail(error)
            raise

    def fail(self, error):
        self._rollback()
        if not self._registered:
            return
        q, a, e = self._literal, self.table('etl_load_attempt'), self.table('etl_load_execution')
        sql = f"BEGIN; UPDATE {a} SET status='FAILED',phase={q(self.phase)},error_message={q(str(error)[-3000:])},completed_at=clock_timestamp() WHERE attempt_id={q(self._attempt_id)} AND status='PREPARING'; UPDATE {e} SET status='FAILED',error_message={q(str(error)[-3000:])},updated_at=clock_timestamp() WHERE execution_id={q(self._execution_id)} AND active_attempt_id={q(self._attempt_id)} AND status='PREPARING'; COMMIT;"
        try:
            self._one_shot(sql)
        except (RuntimeError, OSError):
            # A dead DB is reconciled by the next registered attempt. Never
            # overwrite a committed PUBLISHED row after a lost COMMIT response.
            pass
