"""Atomic daily publisher for historical dependents-count results."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re

from pipeline.postgresql.postgres import PgLoader
from pipeline.preprocessing.requirements_resolution.policy import sha256
from pipeline.preprocessing.requirements_resolution.input import file_sha256
from pipeline.postgresql.version_dependents.historical_db_keys import check_lineage, _calendar_values, _date, _timestamp


LOCK_KEY = "hashtextextended('curated:version-dependents', 0)"


class HistoricalCountLoader(PgLoader):
    """Publish one snapshot atomically while preserving the service schema."""

    def start(self, metadata, execution_id, contract_sha256, attempt_id):
        if not isinstance(metadata, dict) or metadata.get('dataset') != 'version-dependents':
            raise ValueError('unsupported dataset')
        if not isinstance(execution_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', execution_id):
            raise ValueError('invalid execution ID')
        if not isinstance(attempt_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', attempt_id):
            raise ValueError('invalid attempt ID')
        if not isinstance(contract_sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', contract_sha256):
            raise ValueError('invalid contract hash')
        _date(metadata.get('snapshot')); _timestamp(metadata.get('snapshot_timestamp'))
        manifest = metadata.get('manifest')
        if not isinstance(manifest, dict) or metadata.get('manifest_sha256') != sha256(manifest):
            raise ValueError('manifest hash does not match manifest')
        if not isinstance(metadata.get('counts'), dict) or any(type(v) is not int or v < 0 for v in metadata['counts'].values()):
            raise ValueError('invalid expected counts')
        if metadata['counts'].get('package_version_snapshot') is None or metadata['counts'].get('identities') is None:
            raise ValueError('missing expected counts')
        calendar = _calendar_values(manifest.get('calendar'))
        if (metadata['snapshot'], _timestamp(metadata['snapshot_timestamp'])) not in calendar:
            raise ValueError('publication date/time is absent from the pinned calendar')
        self._metadata, self._execution_id, self._attempt_id = metadata, execution_id, attempt_id
        self._already_published = False
        if self._send(f'SELECT pg_try_advisory_lock({LOCK_KEY});') != ['t']:
            raise RuntimeError('another version-dependents load is active')
        q = self._literal
        prior_rows = self._send(f'SELECT row_to_json(e) FROM public.etl_load_execution e WHERE execution_id={q(execution_id)};')
        if prior_rows:
            prior = json.loads(prior_rows[0])
            same = (prior.get('dataset') == 'version-dependents' and prior.get('snapshot_at') == metadata['snapshot']
                    and prior.get('curated_run_id') == metadata['curated_run_id']
                    and prior.get('run_prefix') == metadata['run_prefix']
                    and prior.get('manifest_sha256') == metadata['manifest_sha256']
                    and prior.get('input_metadata') == manifest and prior.get('expected_counts') == metadata['counts'])
            if same:
                prior_stamp = datetime.fromisoformat(prior['snapshot_timestamp'].replace('Z', '+00:00'))
                wanted_stamp = datetime.fromisoformat(_timestamp(metadata['snapshot_timestamp']).replace('Z', '+00:00'))
                if prior_stamp.tzinfo is None:
                    prior_stamp = prior_stamp.replace(tzinfo=timezone.utc)
                same = prior_stamp.timestamp() == wanted_stamp.timestamp()
            if not same or (prior.get('contract_sha256') != contract_sha256 and prior.get('status') != 'PUBLISHED'):
                raise ValueError('execution_id already exists with different input or contract')
            self._already_published = prior.get('status') == 'PUBLISHED'
        self._send("BEGIN; "
                   "UPDATE public.etl_load_attempt a SET status='FAILED',phase='ABANDONED',error_message='Previous session ended before completion',completed_at=clock_timestamp() "
                   "FROM public.etl_load_execution e WHERE a.execution_id=e.execution_id AND e.dataset='version-dependents' AND a.status='PREPARING'; "
                   "UPDATE public.etl_load_execution SET status='FAILED',updated_at=clock_timestamp(),error_message='Previous session ended before completion' WHERE dataset='version-dependents' AND status='PREPARING'; "
                   "INSERT INTO public.etl_load_execution(execution_id,dataset,status,snapshot_at,snapshot_timestamp,curated_run_id,run_prefix,manifest_sha256,contract_sha256,input_metadata,expected_counts,active_attempt_id) VALUES (" +
                   ','.join(q(v) for v in (execution_id, 'version-dependents', 'PREPARING', metadata['snapshot'], metadata['snapshot_timestamp'], metadata['curated_run_id'], metadata['run_prefix'], metadata['manifest_sha256'], contract_sha256, manifest, metadata['counts'], attempt_id)) +
                   ") ON CONFLICT(execution_id) DO UPDATE SET status=CASE WHEN etl_load_execution.status='PUBLISHED' THEN 'PUBLISHED' ELSE 'PREPARING' END,active_attempt_id=EXCLUDED.active_attempt_id,error_message=NULL,updated_at=clock_timestamp(); "
                   "INSERT INTO public.etl_load_attempt(attempt_id,execution_id,status,phase,validation_contract_sha256) VALUES (" +
                   f"{q(attempt_id)},{q(execution_id)},'PREPARING','VALIDATE_INPUT',{q(contract_sha256)}); COMMIT;")
        self._registered = True
        return self._already_published

    def _copy_counts(self, path):
        source = Path(path)
        if source.is_symlink() or not source.is_file():
            raise ValueError('expected regular count COPY text file')
        with source.open('rb') as stream:
            size = stream.seek(0, 2)
            if size:
                stream.seek(-1, 2)
                if stream.read(1) != b'\n':
                    raise ValueError('COPY file must end with LF')
            stream.seek(0)
            self._process.stdin.write(b"COPY pg_temp._h7_counts(package_id,version,snapshot_at,dependents_count) FROM STDIN WITH (FORMAT text, NULL '\\N', ENCODING 'UTF8');\n")
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                self._process.stdin.write(block)
            self._process.stdin.write(b'\\.\n'); self._process.stdin.flush()
        self._send('SELECT 1;')

    def _validate_manifest_files(self, csv_files):
        records = self._metadata['manifest'].get('files')
        if not isinstance(records, list) or len(records) != 2:
            raise ValueError('manifest files are required')
        by_role = {r.get('role'): r for r in records if isinstance(r, dict)}
        if set(by_role) != {'identities', 'counts'} or set(csv_files) != set(by_role):
            raise ValueError('unexpected or duplicate file roles')
        result = {}
        for role in ('identities', 'counts'):
            path = Path(csv_files.get(role)) if isinstance(csv_files, dict) and role in csv_files else None
            record = by_role.get(role)
            if path is None or record is None or path.is_symlink() or not path.is_file():
                raise ValueError(f'missing {role} file or manifest record')
            size, digest = path.stat().st_size, file_sha256(path)
            expected_rows = self._metadata['counts']['identities' if role == 'identities' else 'package_version_snapshot']
            if (record.get('bytes') != size or record.get('sha256') != digest
                    or record.get('rows') != expected_rows):
                raise ValueError(f'{role} file does not match manifest')
            result[role] = {'path': str(path), 'bytes': size, 'sha256': digest}
        return result

    def _require(self, condition, message):
        self._send(f'DO $$ BEGIN IF NOT ({condition}) THEN RAISE EXCEPTION {self._literal(message)}; END IF; END $$;')

    def publish(self, csv_files, failpoint=None, before_commit=None):
        if not self._registered:
            raise RuntimeError('start() must be called before publish()')
        if failpoint not in (None, 'after_copy', 'after_insert', 'before_commit'):
            raise ValueError('unknown failpoint')
        m, q = self._metadata, self._literal
        expected = m['counts']['package_version_snapshot']; snapshot = q(m['snapshot'])
        quality = m['manifest'].get('quality', {})
        if quality.get('calculation_status') != 'COMPLETE' or quality.get('resolution_status') not in ('PARTIAL', 'COMPLETE'):
            raise ValueError('calculation quality is not publishable')
        _calendar_values(m['manifest'].get('calendar'))
        file_report = self._validate_manifest_files(csv_files)
        self._phase('COPY')
        self._send("CREATE TEMP TABLE _h7_identities(package_id integer NOT NULL CHECK(package_id>0),name varchar(300) NOT NULL CHECK(length(trim(name))>0)); CREATE TEMP TABLE _h7_counts(package_id integer NOT NULL CHECK(package_id>0),version varchar(100) NOT NULL CHECK(length(trim(version))>0),snapshot_at date NOT NULL,dependents_count integer NOT NULL CHECK(dependents_count>=0));")
        from pipeline.postgresql.version_dependents.historical_db_keys import copy_file
        copy_file(self, '_h7_identities', ('package_id', 'name'), csv_files['identities'])
        self._copy_counts(csv_files['counts'])
        self._validate_manifest_files(csv_files)
        if failpoint == 'after_copy': raise RuntimeError('injected failure after_copy')
        self._send('CREATE UNIQUE INDEX ON pg_temp._h7_identities(package_id); CREATE UNIQUE INDEX ON pg_temp._h7_identities(name); CREATE UNIQUE INDEX ON pg_temp._h7_counts(package_id,version,snapshot_at); ANALYZE pg_temp._h7_identities; ANALYZE pg_temp._h7_counts;')
        self._require(f'(SELECT count(*) FROM pg_temp._h7_identities)={m["counts"]["identities"]} AND (SELECT count(*) FROM pg_temp._h7_counts)={expected}', 'staging count mismatch')
        self._require(f'NOT EXISTS(SELECT 1 FROM pg_temp._h7_counts WHERE snapshot_at<>{snapshot}::date)', 'staging snapshot mismatch')
        aggregate = self._send('SELECT json_build_object(\'target_versions\',count(*),'
            '\'positive_target_versions\',count(*) FILTER(WHERE dependents_count>0),'
            '\'zero_target_versions\',count(*) FILTER(WHERE dependents_count=0),'
            '\'distinct_edges\',coalesce(sum(dependents_count),0)) FROM pg_temp._h7_counts;')
        if any(quality.get(k) != v for k,v in json.loads(aggregate[0]).items()):
            raise ValueError('staged counts differ from declared quality')
        self._send('BEGIN; LOCK TABLE public.package,public.version,public.snapshot,public.package_version_snapshot,public.etl_snapshot_reference,public.etl_load_execution,public.etl_load_attempt,public.etl_dataset_current IN SHARE ROW EXCLUSIVE MODE;')
        check_lineage(self, m['manifest']['lineage'], m['manifest']['calendar'])
        self._require('NOT EXISTS(SELECT 1 FROM pg_temp._h7_identities i LEFT JOIN public.package p USING(package_id) WHERE p.package_id IS NULL OR p.name IS DISTINCT FROM i.name)', 'database package ID/name mismatch')
        self._require('NOT EXISTS(SELECT 1 FROM pg_temp._h7_counts c LEFT JOIN public.version v USING(package_id,version) WHERE v.package_id IS NULL)', 'database version composite key is missing')
        self._require('NOT EXISTS(SELECT 1 FROM pg_temp._h7_counts c LEFT JOIN pg_temp._h7_identities i USING(package_id) WHERE i.package_id IS NULL)', 'count identity mismatch')
        published = self._send(f"SELECT manifest_sha256 FROM public.etl_load_execution WHERE dataset='version-dependents' AND status='PUBLISHED' AND snapshot_at={snapshot}::date;")
        if published and any(value != m['manifest_sha256'] for value in published): raise ValueError('snapshot already published from a different input')
        reverify = self._already_published or bool(published)
        if not reverify:
            self._require(f'NOT EXISTS(SELECT 1 FROM public.package_version_snapshot p JOIN pg_temp._h7_identities i USING(package_id) WHERE p.snapshot_at={snapshot}::date)', 'selected snapshot has orphan service rows')
            self._send('INSERT INTO public.package_version_snapshot(package_id,version,snapshot_at,dependents_count) SELECT package_id,version,snapshot_at,dependents_count FROM pg_temp._h7_counts;')
        self._require(f"NOT EXISTS(SELECT 1 FROM pg_temp._h7_counts c FULL JOIN (SELECT p.* FROM public.package_version_snapshot p JOIN pg_temp._h7_identities i USING(package_id) WHERE p.snapshot_at={snapshot}::date) s USING(package_id,version,snapshot_at) WHERE coalesce(c.snapshot_at,s.snapshot_at)={snapshot}::date AND (c.package_id IS NULL OR s.package_id IS NULL OR c.dependents_count IS DISTINCT FROM s.dependents_count))", 'stored count validation failed')
        self._require(f'(SELECT count(*) FROM public.package_version_snapshot p JOIN pg_temp._h7_identities i USING(package_id) WHERE p.snapshot_at={snapshot}::date) = {expected}', 'stored count row total differs')
        if failpoint == 'after_insert': raise RuntimeError('injected failure after_insert')
        self._counts = {'package_version_snapshot': expected, 'identities': m['counts']['identities'], 'verified_rows': expected}
        if before_commit: before_commit()
        self._validate_manifest_files(csv_files)
        if failpoint == 'before_commit': raise RuntimeError('injected failure before_commit')
        self._send(f"UPDATE public.etl_load_attempt SET status='{'REVERIFIED' if reverify else 'PUBLISHED'}',phase='COMMIT',actual_counts={q(self._counts)},quality_report={q(quality)},completed_at=clock_timestamp() WHERE attempt_id={q(self._attempt_id)} AND status='PREPARING'; UPDATE public.etl_load_execution SET status='PUBLISHED',actual_counts={q(self._counts)},error_message=NULL,updated_at=clock_timestamp() WHERE execution_id={q(self._execution_id)} AND active_attempt_id={q(self._attempt_id)};")
        if not reverify:
            self._send('INSERT INTO public.etl_dataset_current(dataset,execution_id,snapshot_at,manifest_sha256,manifest) VALUES (' + ','.join(q(v) for v in ('version-dependents', self._execution_id, m['snapshot'], m['manifest_sha256'], m['manifest'])) + ') ON CONFLICT(dataset) DO UPDATE SET execution_id=EXCLUDED.execution_id,snapshot_at=EXCLUDED.snapshot_at,manifest_sha256=EXCLUDED.manifest_sha256,manifest=EXCLUDED.manifest,published_at=clock_timestamp() WHERE etl_dataset_current.snapshot_at<=EXCLUDED.snapshot_at;')
        self._send('COMMIT;'); self.phase = 'COMPLETE'
        return {'status': 'PUBLISHED', 'action': 'REVERIFIED' if reverify else 'LOADED', 'counts': self._counts, 'execution_id': self._execution_id, 'attempt_id': self._attempt_id, 'files': file_report}

    def fail(self, error):
        if self._process and self._process.poll() is None:
            try: self._send('ROLLBACK;')
            except (RuntimeError, OSError): pass
        if not self._registered: return
        q = self._literal
        self._one_shot(f"BEGIN; UPDATE public.etl_load_attempt SET status='FAILED',phase={q(self.phase)},error_message={q(str(error)[-4000:])},completed_at=clock_timestamp() WHERE attempt_id={q(self._attempt_id)} AND status='PREPARING'; UPDATE public.etl_load_execution SET status='FAILED',error_message={q(str(error)[-4000:])},updated_at=clock_timestamp() WHERE execution_id={q(self._execution_id)} AND active_attempt_id={q(self._attempt_id)} AND status='PREPARING'; COMMIT;")
