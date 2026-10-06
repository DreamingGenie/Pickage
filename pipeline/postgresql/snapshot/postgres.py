"""Publish a frozen calendar and its execution lineage in one transaction."""
from __future__ import annotations

import json
import re

from pipeline.postgresql.postgres import PgLoader


LOCK_KEY = "hashtextextended('snapshot:reference', 0)"
SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,100}\Z")


class SnapshotLoader(PgLoader):
    """Reuse psql transport/failure recording, never package/version publishing."""

    def __enter__(self):
        super().__enter__()
        try:
            self._send("SET lock_timeout='2s'; SET statement_timeout='30s';")
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def start(self, metadata, execution_id, contract_sha256, attempt_id):
        for value in (execution_id, attempt_id):
            if not isinstance(value, str) or not SAFE_ID.fullmatch(value):
                raise ValueError("invalid execution or attempt ID")
        for value in (metadata['manifest_sha256'], contract_sha256):
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
                raise ValueError("invalid input or contract hash")
        if metadata['dataset'] != 'snapshot-reference':
            raise ValueError("unsupported dataset")
        self._metadata = metadata
        self._execution_id, self._attempt_id = execution_id, attempt_id
        if self._send(f"SELECT pg_try_advisory_lock({LOCK_KEY});") != ['t']:
            raise RuntimeError("another snapshot-reference load is active")
        self.phase = 'REGISTER'
        literal = self._literal
        existing = self._send("SELECT row_to_json(e) FROM public.etl_load_execution e "
                              f"WHERE execution_id={literal(execution_id)};")
        self._already_published = False
        if existing:
            prior = json.loads(existing[0])
            identity = {'dataset': 'snapshot-reference', 'snapshot_at': None,
                        'snapshot_timestamp': None, 'curated_run_id': None,
                        'manifest_sha256': metadata['manifest_sha256'],
                        'run_prefix': metadata['run_prefix'], 'input_metadata': metadata['manifest'],
                        'expected_counts': metadata['counts']}
            if any(prior[key] != value for key, value in identity.items()):
                raise ValueError("execution_id already exists with different input")
            self._already_published = prior['status'] == 'PUBLISHED'
            if not self._already_published and prior['contract_sha256'] != contract_sha256:
                raise ValueError("unfinished execution has a different load contract")
        values = [execution_id, 'snapshot-reference', 'PREPARING', metadata['run_prefix'],
                  metadata['manifest_sha256'], contract_sha256, metadata['manifest'],
                  metadata['counts'], attempt_id]
        self._send("BEGIN; "
                   "UPDATE public.etl_load_attempt a SET status='FAILED',phase='ABANDONED', "
                   "error_message='Previous session ended before completion',completed_at=clock_timestamp() "
                   "FROM public.etl_load_execution e WHERE a.execution_id=e.execution_id "
                   "AND e.dataset='snapshot-reference' AND a.status='PREPARING'; "
                   "UPDATE public.etl_load_execution SET status='FAILED',updated_at=clock_timestamp(), "
                   "error_message='Previous session ended before completion' "
                   "WHERE dataset='snapshot-reference' AND status='PREPARING'; "
                   "INSERT INTO public.etl_load_execution "
                   "(execution_id,dataset,status,run_prefix,manifest_sha256,contract_sha256,"
                   "input_metadata,expected_counts,active_attempt_id) VALUES (" +
                   ','.join(literal(v) for v in values) + ") ON CONFLICT(execution_id) DO UPDATE SET "
                   "status=CASE WHEN etl_load_execution.status='PUBLISHED' THEN 'PUBLISHED' ELSE 'PREPARING' END, "
                   "active_attempt_id=EXCLUDED.active_attempt_id,error_message=NULL,updated_at=clock_timestamp(); "
                   "INSERT INTO public.etl_load_attempt "
                   "(attempt_id,execution_id,status,phase,validation_contract_sha256) VALUES (" +
                   f"{literal(attempt_id)},{literal(execution_id)},'PREPARING','VALIDATE_DATABASE',"
                   f"{literal(contract_sha256)}); COMMIT;")
        self._registered = True
        return self._already_published

    def _validate_dates(self):
        self._send("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_temp.snapshot_input i "
                   "LEFT JOIN public.snapshot s USING(snapshot_at) WHERE s.snapshot_at IS NULL) "
                   "THEN RAISE EXCEPTION 'Missing candidate snapshot date'; END IF; END $$;")

    def _validate_membership(self):
        run_id = self._literal(self._execution_id)
        columns = 'snapshot_at,snapshot_timestamp,previous_snapshot_at'
        self._send(f"DO $$ BEGIN IF EXISTS ((SELECT {columns} FROM pg_temp.snapshot_input "
                   f"EXCEPT SELECT {columns} FROM public.etl_snapshot_reference WHERE execution_id={run_id}) "
                   f"UNION ALL (SELECT {columns} FROM public.etl_snapshot_reference WHERE execution_id={run_id} "
                   f"EXCEPT SELECT {columns} FROM pg_temp.snapshot_input)) "
                   "THEN RAISE EXCEPTION 'Execution calendar does not match frozen input'; END IF; END $$;")

    def publish(self, calendar, failpoint=None):
        if not self._registered:
            raise RuntimeError("start() must be called before publish()")
        if calendar != self._metadata['manifest']['candidate']['calendar']:
            raise ValueError("calendar differs from registered input")
        if failpoint not in (None, 'after_dates', 'after_references', 'before_commit'):
            raise ValueError("unknown failpoint")
        self._phase('VALIDATE_DATABASE')
        literal = self._literal
        # The serialized input is data, never executable SQL from the candidate.
        self._send("CREATE TEMP TABLE snapshot_input (snapshot_at date PRIMARY KEY, "
                   "snapshot_timestamp timestamptz NOT NULL,previous_snapshot_at date); "
                   "INSERT INTO pg_temp.snapshot_input SELECT snapshot_at,snapshot_timestamp,previous_snapshot_at "
                   f"FROM jsonb_to_recordset({literal(calendar)}::jsonb) "
                   "AS x(snapshot_at date,snapshot_timestamp timestamptz,previous_snapshot_at date);")
        if int(self._send("SELECT count(*) FROM pg_temp.snapshot_input;")[0]) != self._metadata['counts']['snapshot']:
            raise ValueError("calendar count mismatch")
        self._phase('PUBLISH')
        self._send("BEGIN; LOCK TABLE public.etl_snapshot_reference IN SHARE ROW EXCLUSIVE MODE;")
        self._send("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_temp.snapshot_input i "
                   "JOIN public.etl_snapshot_reference r USING(snapshot_at) "
                   "JOIN public.etl_load_execution e ON e.execution_id=r.execution_id "
                   "WHERE e.status='PUBLISHED' AND r.snapshot_timestamp<>i.snapshot_timestamp) "
                   "THEN RAISE EXCEPTION 'Snapshot date already has a different observed instant'; "
                   "END IF; END $$;")
        # Already published means verify only: never silently repair missing rows.
        inserted = 0
        if not self._already_published:
            inserted = int(self._send(
                "WITH inserted AS (INSERT INTO public.snapshot(snapshot_at) "
                "SELECT snapshot_at FROM pg_temp.snapshot_input ORDER BY snapshot_at "
                "ON CONFLICT(snapshot_at) DO NOTHING RETURNING snapshot_at) SELECT count(*) FROM inserted;")[0])
        if failpoint == 'after_dates':
            self._send("SELECT 1/0;")
        self._validate_dates()
        if not self._already_published:
            self._send("INSERT INTO public.etl_snapshot_reference "
                       "(execution_id,snapshot_at,snapshot_timestamp,previous_snapshot_at) "
                       f"SELECT {literal(self._execution_id)},snapshot_at,snapshot_timestamp,previous_snapshot_at "
                       "FROM pg_temp.snapshot_input ORDER BY snapshot_at;")
        if failpoint == 'after_references':
            self._send("SELECT 1/0;")
        self._validate_membership()
        count = self._metadata['counts']['snapshot']
        self._counts = {'snapshot': count, 'inserted': inserted, 'existing': count-inserted,
                        'reference_rows': count}
        state = 'REVERIFIED' if self._already_published else 'PUBLISHED'
        # A retry's observed counts belong to the attempt; first-publication counts stay historical.
        update_counts = '' if self._already_published else f",actual_counts={literal(self._counts)}"
        self._send("UPDATE public.etl_load_attempt SET "
                   f"status={literal(state)},phase='COMMIT',actual_counts={literal(self._counts)},"
                   "completed_at=clock_timestamp() "
                   f"WHERE attempt_id={literal(self._attempt_id)} AND status='PREPARING'; "
                   "UPDATE public.etl_load_execution SET status='PUBLISHED',error_message=NULL,"
                   f"updated_at=clock_timestamp(){update_counts} WHERE execution_id={literal(self._execution_id)} "
                   f"AND active_attempt_id={literal(self._attempt_id)};")
        if failpoint == 'before_commit':
            self._send("SELECT 1/0;")
        self._send("COMMIT;")
        self.phase = 'COMPLETE'
        # Re-query on another connection, rather than treating a local JSON as DB proof.
        proof = json.loads(self._one_shot("SELECT json_build_object("
            "'database',current_database(),'status',e.status,'attempt_status',a.status,"
            "'reference_rows',(SELECT count(*) FROM public.etl_snapshot_reference r "
            "WHERE r.execution_id=e.execution_id)) FROM public.etl_load_execution e "
            "JOIN public.etl_load_attempt a ON a.attempt_id=e.active_attempt_id "
            f"WHERE e.execution_id={literal(self._execution_id)};"))
        if proof['status'] != 'PUBLISHED' or proof['attempt_status'] != state or proof['reference_rows'] != count:
            raise RuntimeError("post-commit execution verification failed")
        action = 'REVERIFIED' if self._already_published else ('LOADED' if inserted else 'LINKED_EXISTING')
        return {'status': 'PUBLISHED', 'action': action, 'counts': self._counts,
                'execution_id': self._execution_id, 'attempt_id': self._attempt_id,
                'db_verification': proof, 'service_ready': False}
