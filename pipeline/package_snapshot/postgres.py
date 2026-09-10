"""Publish one complete package snapshot with lineage and atomic history."""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re

from pipeline.postgresql.postgres import PgLoader

LOCK_KEY = "hashtextextended('curated:package-snapshot', 0)"
COLUMNS = {
    'package_snapshot': 'package_id,snapshot_at,downloads,stars,open_issues',
    'package_identity': 'package_id,name',
}


class PackageSnapshotLoader(PgLoader):
    def start(self, metadata, execution_id, contract_sha256, attempt_id):
        for value in (execution_id, attempt_id):
            if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', value):
                raise ValueError('invalid execution or attempt ID')
        for value in (metadata['manifest_sha256'], contract_sha256):
            if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value):
                raise ValueError('invalid manifest or contract hash')
        if metadata['dataset'] != 'package-snapshot':
            raise ValueError('unsupported dataset')
        count = metadata['counts']['package_snapshot']
        if type(count) is not int or count <= 0:
            raise ValueError('population must be nonempty')
        self._metadata = metadata
        self._execution_id, self._attempt_id = execution_id, attempt_id
        if self._send(f'SELECT pg_try_advisory_lock({LOCK_KEY});') != ['t']:
            raise RuntimeError('another package-snapshot load is active')
        self.phase = 'REGISTER'
        q = self._literal
        existing = self._send('SELECT row_to_json(e) FROM public.etl_load_execution e '
                              f'WHERE execution_id={q(execution_id)};')
        self._already_published = False
        if existing:
            prior = json.loads(existing[0])
            identity = {'dataset': metadata['dataset'], 'snapshot_at': metadata['snapshot'],
                        'curated_run_id': metadata['curated_run_id'], 'run_prefix': metadata['run_prefix'],
                        'manifest_sha256': metadata['manifest_sha256'],
                        'input_metadata': metadata['manifest'], 'expected_counts': metadata['counts']}
            same_input = (all(prior[k] == value for k, value in identity.items()) and
                          datetime.fromisoformat(prior['snapshot_timestamp']) ==
                          datetime.fromisoformat(metadata['snapshot_timestamp']))
            # A published execution is the immutable record of the input that
            # produced the service rows.  A later validation may use a newer
            # compatible loader contract; keep that original publication hash
            # and record the newer hash on the attempt below.
            allow_published_contract_change = prior['status'] == 'PUBLISHED' and same_input
            if (not same_input or
                    (prior['contract_sha256'] != contract_sha256 and
                     not allow_published_contract_change)):
                raise ValueError('execution_id already exists with different input or contract')
            self._already_published = prior['status'] == 'PUBLISHED'
        else:
            allow_published_contract_change = False
        published = self._send('SELECT contract_sha256 FROM public.etl_load_execution '
                               "WHERE dataset='package-snapshot' AND manifest_sha256="
                               f"{q(metadata['manifest_sha256'])} AND status='PUBLISHED' LIMIT 1;")
        if published and published[0] != contract_sha256 and not allow_published_contract_change:
            raise ValueError('published input has a different load contract; use a new approved input run')
        values = [execution_id, 'package-snapshot', 'PREPARING', metadata['snapshot'],
                  metadata['snapshot_timestamp'], metadata['curated_run_id'], metadata['run_prefix'],
                  metadata['manifest_sha256'], contract_sha256, metadata['manifest'], metadata['counts'], attempt_id]
        self._send("BEGIN; UPDATE public.etl_load_attempt a SET status='FAILED',phase='ABANDONED', "
                   "error_message='Previous session ended before completion',completed_at=clock_timestamp() "
                   "FROM public.etl_load_execution e WHERE a.execution_id=e.execution_id "
                   "AND e.dataset='package-snapshot' AND a.status='PREPARING'; "
                   "UPDATE public.etl_load_execution SET status='FAILED',updated_at=clock_timestamp(), "
                   "error_message='Previous session ended before completion' "
                   "WHERE dataset='package-snapshot' AND status='PREPARING'; "
                   "INSERT INTO public.etl_load_execution "
                   "(execution_id,dataset,status,snapshot_at,snapshot_timestamp,curated_run_id,run_prefix,"
                   "manifest_sha256,contract_sha256,input_metadata,expected_counts,active_attempt_id) VALUES (" +
                   ','.join(q(v) for v in values) + ") ON CONFLICT(execution_id) DO UPDATE SET "
                   "status=CASE WHEN etl_load_execution.status='PUBLISHED' THEN 'PUBLISHED' ELSE 'PREPARING' END,"
                   "active_attempt_id=EXCLUDED.active_attempt_id,error_message=NULL,updated_at=clock_timestamp(); "
                   "INSERT INTO public.etl_load_attempt "
                   "(attempt_id,execution_id,status,phase,validation_contract_sha256) VALUES (" +
                   f"{q(attempt_id)},{q(execution_id)},'PREPARING','VALIDATE_INPUT',{q(contract_sha256)}); COMMIT;")
        self._registered = True
        return self._already_published

    def _copy_role(self, role, files):
        if role not in COLUMNS or not files:
            raise ValueError('missing COPY role')
        for value in files:
            path = Path(value)
            if path.is_symlink() or not path.is_file() or not path.name.endswith('.copy.tsv'):
                raise ValueError('expected regular COPY text file')
            with path.open('rb') as source:
                source.seek(0, 2)
                if source.tell():
                    source.seek(-1, 2)
                    if source.read() != b'\n':
                        raise ValueError('COPY file must end with LF')
                source.seek(0)
                process = self._process
                process.stdin.write((f'COPY pg_temp.{role}_input ({COLUMNS[role]}) '
                                     "FROM STDIN WITH (FORMAT text, DELIMITER E'\\t', NULL '\\N');\n").encode())
                for chunk in iter(lambda: source.read(1024 * 1024), b''):
                    process.stdin.write(chunk)
                process.stdin.write(b'\\.\n')
                process.stdin.flush()
                self._send('SELECT 1;')

    def _require(self, condition, message):
        self._send(f'DO $$ BEGIN IF NOT ({condition}) THEN RAISE EXCEPTION '
                   f'{self._literal(message)}; END IF; END $$;')

    def _lineage(self):
        m, q = self._metadata, self._literal
        sources = m['manifest']['input_manifest']
        interval = m['manifest']['interval']
        population = sources['population']
        self._require(
            "EXISTS (SELECT 1 FROM public.etl_dataset_current c JOIN public.etl_load_execution e "
            "ON e.execution_id=c.execution_id WHERE c.dataset='package-version' AND e.status='PUBLISHED' "
            f"AND c.snapshot_at={q(m['snapshot'])}::date AND c.manifest_sha256={q(population['manifest_sha256'])} "
            f"AND e.manifest_sha256={q(population['manifest_sha256'])} "
            f"AND e.curated_run_id={q(population['run_id'])} "
            f"AND e.snapshot_timestamp={q(m['snapshot_timestamp'])}::timestamp)",
            'package-version current input does not match approved population')
        previous = interval['previous_snapshot_at']
        previous_check = '' if previous is None else (
            " AND EXISTS (SELECT 1 FROM public.etl_snapshot_reference p WHERE p.execution_id=r.execution_id "
            f"AND p.snapshot_at={q(previous)}::date "
            f"AND p.snapshot_timestamp={q(interval['previous_snapshot_timestamp'])}::timestamptz)")
        self._require(
            "EXISTS (SELECT 1 FROM public.etl_snapshot_reference r JOIN public.etl_load_execution e "
            "ON e.execution_id=r.execution_id WHERE e.dataset='snapshot-reference' AND e.status='PUBLISHED' "
            f"AND e.manifest_sha256={q(sources['candidate']['sha256'])} AND r.snapshot_at={q(m['snapshot'])}::date "
            f"AND r.snapshot_timestamp={q(interval['snapshot_timestamp'])}::timestamptz "
            f"AND r.previous_snapshot_at IS NOT DISTINCT FROM {q(previous)}::date{previous_check})",
            'snapshot-reference lineage or exact interval does not match approved input')

    def publish(self, csv_files, failpoint=None, before_commit=None):
        if not self._registered:
            raise RuntimeError('start() must be called before publish()')
        if failpoint not in (None, 'after_copy', 'after_insert', 'before_commit'):
            raise ValueError('unknown failpoint')
        m, q = self._metadata, self._literal
        expected, snapshot = m['counts']['package_snapshot'], q(m['snapshot'])
        self._phase('COPY')
        self._send('CREATE TEMP TABLE package_identity_input (package_id int NOT NULL,name text NOT NULL); '
                   'CREATE TEMP TABLE package_snapshot_input (package_id int NOT NULL,snapshot_at date NOT NULL,'
                   'downloads bigint CHECK(downloads>=0),stars int CHECK(stars>=0),open_issues int CHECK(open_issues>=0));')
        for role in COLUMNS:
            self._copy_role(role, csv_files[role])
        if failpoint == 'after_copy':
            raise RuntimeError('injected failure after_copy')
        self._phase('VALIDATE_STAGING')
        self._send('CREATE UNIQUE INDEX ON package_identity_input(package_id); '
                   'CREATE UNIQUE INDEX ON package_identity_input(name); '
                   'CREATE UNIQUE INDEX ON package_snapshot_input(package_id,snapshot_at); '
                   'ANALYZE package_identity_input; ANALYZE package_snapshot_input;')
        self._require(f'(SELECT count(*) FROM pg_temp.package_identity_input)={expected} AND '
                      f'(SELECT count(*) FROM pg_temp.package_snapshot_input)={expected}', 'staging count mismatch')
        self._require(f'NOT EXISTS (SELECT 1 FROM pg_temp.package_snapshot_input '
                      f'WHERE snapshot_at<>{snapshot}::date)', 'staging snapshot mismatch')
        self._require('NOT EXISTS (SELECT 1 FROM pg_temp.package_snapshot_input s '
                      'FULL JOIN pg_temp.package_identity_input i USING(package_id) '
                      'WHERE s.package_id IS NULL OR i.package_id IS NULL)', 'staging population mismatch')
        self._phase('PUBLISH')
        # SnapshotLoader locks references before inserting dates; use the same order.
        self._send('BEGIN; LOCK TABLE public.package IN SHARE MODE; '
                   'LOCK TABLE public.etl_snapshot_reference IN SHARE MODE; '
                   'LOCK TABLE public.snapshot IN SHARE MODE; '
                   'LOCK TABLE public.package_snapshot,public.etl_load_execution,public.etl_load_attempt,'
                   'public.etl_dataset_current IN SHARE ROW EXCLUSIVE MODE;')
        # A new validator hash is allowed for a published input, but incompatible
        # serving column types/nullability are not. Ignore unrelated added columns.
        self._require("(SELECT count(*) FROM (VALUES ('package_id','integer',true),"
                      "('snapshot_at','date',true),('downloads','bigint',false),"
                      "('stars','integer',false),('open_issues','integer',false)) "
                      "AS expected(name,type_name,not_null) JOIN pg_attribute a "
                      "ON a.attrelid='public.package_snapshot'::regclass AND a.attname=expected.name "
                      "WHERE a.attnum>0 AND NOT a.attisdropped "
                      "AND format_type(a.atttypid,a.atttypmod)=expected.type_name "
                      "AND a.attnotnull=expected.not_null)=5",
                      'service schema differs from package-snapshot contract')
        self._lineage()
        self._require('NOT EXISTS (SELECT 1 FROM pg_temp.package_identity_input i '
                      'LEFT JOIN public.package p USING(package_id) WHERE p.package_id IS NULL '
                      'OR p.name IS DISTINCT FROM i.name)', 'database package ID/name mismatch')
        self._require(f'EXISTS(SELECT 1 FROM public.snapshot WHERE snapshot_at={snapshot}::date)',
                      'missing service snapshot')
        published = self._send('SELECT manifest_sha256 FROM public.etl_load_execution '
                              f"WHERE dataset='package-snapshot' AND status='PUBLISHED' AND snapshot_at={snapshot}::date;")
        if any(sha != m['manifest_sha256'] for sha in published):
            raise ValueError('snapshot already published from a different input')
        reverify = self._already_published or bool(published)
        if not reverify:
            self._require(f'NOT EXISTS(SELECT 1 FROM public.package_snapshot WHERE snapshot_at={snapshot}::date)',
                          'snapshot already contains rows without matching published provenance')
            self._send('INSERT INTO public.package_snapshot (' + COLUMNS['package_snapshot'] + ') '
                       'SELECT ' + COLUMNS['package_snapshot'] + ' FROM pg_temp.package_snapshot_input ORDER BY package_id;')
        if failpoint == 'after_insert':
            raise RuntimeError('injected failure after_insert')
        # This runs on retries too: missing, extra or changed service rows are errors, not repairs.
        self._require('NOT EXISTS (SELECT 1 FROM pg_temp.package_snapshot_input i FULL JOIN '
                      f'(SELECT * FROM public.package_snapshot WHERE snapshot_at={snapshot}::date) s '
                      'USING(package_id,snapshot_at) WHERE i.package_id IS NULL OR s.package_id IS NULL '
                      'OR ROW(i.downloads,i.stars,i.open_issues) IS DISTINCT FROM '
                      'ROW(s.downloads,s.stars,s.open_issues))', 'service values differ from approved snapshot')
        self._counts = {'package_snapshot': expected, 'inserted': 0 if reverify else expected,
                        'verified_rows': expected}
        quality = {'manifest_sha256': m['manifest_sha256'], 'run_prefix': m['run_prefix'],
                   'input_manifest': m['manifest']['input_manifest'],
                   'files': m['manifest'].get('files', []), 'summary': m['manifest'].get('quality', {}),
                   'verification_scope': 'ALL_SERVICE_ROWS_NULL_SAFE'}
        # Network checks happen before the DB commit while predecessor/service locks are held.
        if before_commit:
            before_commit()
        if failpoint == 'before_commit':
            raise RuntimeError('injected failure before_commit')
        state = 'REVERIFIED' if reverify else 'PUBLISHED'
        first_counts = '' if self._already_published else f',actual_counts={q(self._counts)}'
        self._send("UPDATE public.etl_load_attempt SET "
                   f"status={q(state)},phase='COMMIT',actual_counts={q(self._counts)},quality_report={q(quality)},"
                   f"completed_at=clock_timestamp() WHERE attempt_id={q(self._attempt_id)} AND status='PREPARING'; "
                   "UPDATE public.etl_load_execution SET status='PUBLISHED',error_message=NULL,"
                   f"updated_at=clock_timestamp(){first_counts} WHERE execution_id={q(self._execution_id)} "
                   f"AND active_attempt_id={q(self._attempt_id)};")
        if not self._already_published:
            self._send('INSERT INTO public.etl_dataset_current '
                       '(dataset,execution_id,snapshot_at,manifest_sha256,manifest) VALUES (' +
                       ','.join(q(v) for v in ('package-snapshot', self._execution_id, m['snapshot'],
                                              m['manifest_sha256'], m['manifest'])) +
                       ') ON CONFLICT(dataset) DO UPDATE SET execution_id=EXCLUDED.execution_id,'
                       'snapshot_at=EXCLUDED.snapshot_at,manifest_sha256=EXCLUDED.manifest_sha256,'
                       'manifest=EXCLUDED.manifest,published_at=clock_timestamp() '
                       'WHERE etl_dataset_current.snapshot_at<=EXCLUDED.snapshot_at;')
        self._send('COMMIT;')
        self.phase = 'VERIFY_COMMIT'
        proof = json.loads(self._one_shot("SELECT json_build_object('database',current_database(),"
            "'status',e.status,'attempt_status',a.status,'actual_counts',a.actual_counts) "
            'FROM public.etl_load_execution e JOIN public.etl_load_attempt a '
            f'ON a.attempt_id=e.active_attempt_id WHERE e.execution_id={q(self._execution_id)};'))
        if proof['status'] != 'PUBLISHED' or proof['attempt_status'] != state:
            raise RuntimeError('post-commit execution verification failed')
        self.phase = 'COMPLETE'
        return {'status': 'PUBLISHED', 'action': 'REVERIFIED' if reverify else 'LOADED',
                'counts': self._counts, 'execution_id': self._execution_id, 'attempt_id': self._attempt_id,
                'verification_scope': 'ALL_SERVICE_ROWS_NULL_SAFE', 'db_verification': proof}
