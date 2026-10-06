"""Read-only PostgreSQL evidence collection via the local Docker psql client."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import time


TABLES = "('package','version','snapshot','package_snapshot','package_version_snapshot')"
DATASETS = "('package-version','snapshot-reference','package-snapshot','version-dependents')"


def query(container: str, database: str, sql: str, *, timeout=60):
    for value in (container, database):
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValueError("Explicit local container/database identifier required")
    # SQL is repository-owned. Even a mistaken write fails under both session and
    # transaction read-only settings; no loader context manager is invoked.
    command = ["docker", "exec", "-i", "-e",
               "PGOPTIONS=-c default_transaction_read_only=on -c application_name=integrity09-readonly",
               container, "psql", "-X", "-q", "-A", "-t", "-U", "postgres", "-d", database,
               "-v", "ON_ERROR_STOP=1", "-f", "-"]
    transaction = ("BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;\n"
                   f"SET LOCAL statement_timeout='{int(timeout)}s'; SET LOCAL lock_timeout='2s';\n"
                   "SET LOCAL max_parallel_workers_per_gather=0; SET LOCAL work_mem='32MB';\n"
                   "SET LOCAL TimeZone='UTC';\n" + sql + ";\nROLLBACK;\n")
    started = time.perf_counter()
    result = subprocess.run(command, input=transaction, capture_output=True, text=True,
                            encoding="utf-8", timeout=timeout + 15)
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    if len(result.stdout.encode("utf-8")) > 64 * 1024 * 1024:
        raise ValueError("Metadata response exceeds 64 MiB")
    return json.loads(result.stdout), round(time.perf_counter() - started, 3)


def rows(sql):
    return "SELECT coalesce(jsonb_agg(to_jsonb(q)), '[]'::jsonb) FROM (" + sql + ") q"


def metadata_queries(source_schema):
    if not re.fullmatch(r"[a-z][a-z0-9_]+", source_schema):
        raise ValueError("Invalid receipt schema")
    return {
        "identity": "SELECT jsonb_build_object('database',current_database(),'system_identifier',"
                    "(SELECT system_identifier::text FROM pg_control_system()),'read_only',"
                    "current_setting('transaction_read_only'),'server_version',current_setting('server_version'))",
        "columns": rows("SELECT c.relname AS table_name,a.attname AS name,format_type(a.atttypid,a.atttypmod) AS type,"
                        "a.attnotnull AS not_null,pg_get_expr(d.adbin,d.adrelid) AS default_value "
                        "FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
                        "LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum "
                        f"WHERE n.nspname='public' AND c.relname IN {TABLES} AND a.attnum>0 AND NOT a.attisdropped "
                        "ORDER BY c.relname,a.attnum"),
        "constraints": rows("SELECT t.relname AS table_name,c.conname AS name,c.contype AS type,c.convalidated AS validated,"
                            "pg_get_constraintdef(c.oid) AS definition,"
                            "ARRAY(SELECT a.attname FROM unnest(c.conkey) WITH ORDINALITY k(num,ord) "
                            "JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=k.num ORDER BY ord) AS columns,"
                            "rn.nspname AS target_schema,rt.relname AS target_table,"
                            "ARRAY(SELECT a.attname FROM unnest(c.confkey) WITH ORDINALITY k(num,ord) "
                            "JOIN pg_attribute a ON a.attrelid=c.confrelid AND a.attnum=k.num ORDER BY ord) AS target_columns "
                            "FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace "
                            "LEFT JOIN pg_class rt ON rt.oid=c.confrelid LEFT JOIN pg_namespace rn ON rn.oid=rt.relnamespace "
                            f"WHERE n.nspname='public' AND t.relname IN {TABLES} ORDER BY t.relname,c.conname"),
        "snapshots": rows("SELECT snapshot_at FROM public.snapshot ORDER BY snapshot_at"),
        "references": rows("SELECT * FROM public.etl_snapshot_reference ORDER BY execution_id,snapshot_at"),
        "executions": rows("SELECT execution_id,dataset,status,snapshot_at,snapshot_timestamp,curated_run_id,run_prefix,"
                           "manifest_sha256,contract_sha256,input_metadata,expected_counts,actual_counts,active_attempt_id "
                           f"FROM public.etl_load_execution WHERE dataset IN {DATASETS} ORDER BY dataset,snapshot_at,execution_id LIMIT 1001"),
        "attempts": rows("SELECT a.* FROM public.etl_load_attempt a JOIN public.etl_load_execution e "
                         "ON e.execution_id=a.execution_id AND e.active_attempt_id=a.attempt_id "
                         f"WHERE e.dataset IN {DATASETS} ORDER BY e.dataset,e.snapshot_at,e.execution_id LIMIT 1001"),
        "current": rows(f"SELECT * FROM public.etl_dataset_current WHERE dataset IN {DATASETS} ORDER BY dataset"),
        "partitions": rows("SELECT c.oid,c.relname,n.nspname AS schema_name,pg_get_expr(c.relpartbound,c.oid) AS boundary "
                           "FROM pg_inherits i JOIN pg_class c ON c.oid=i.inhrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
                           "WHERE i.inhparent='public.package_version_snapshot'::regclass ORDER BY c.relname"),
        "receipts": rows(f"SELECT * FROM {source_schema}.reload_partition ORDER BY snapshot_at"),
    }


def collect(container, database, source_schema, output: Path):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    result, times = {}, {}
    queries = metadata_queries(source_schema)
    for name, sql in queries.items():
        (output / (name + ".sql")).write_text(sql + ";\n", encoding="utf-8")
        result[name], times[name] = query(container, database, sql)
        if isinstance(result[name], list) and len(result[name]) >= 1001 and name in ("executions", "attempts"):
            raise ValueError("History exceeds explicit metadata record limit")
        (output / (name + ".json")).write_text(json.dumps(result[name], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Metadata {name}: {times[name]}s", flush=True)
    (output / "timings.json").write_text(json.dumps(times, indent=2) + "\n", encoding="utf-8")
    return result
