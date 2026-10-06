"""Load one approved Curated package/version run into an explicitly chosen DB.

Run from repository root: python -m pipeline.postgresql.load --help
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
import uuid

import duckdb

from pipeline.preprocessing.curated.storage import json_bytes
from pipeline.minio.ingest_raw import client
from pipeline.postgresql.input import prepare, select_run
from pipeline.postgresql.postgres import PgLoader


ROOT = Path(__file__).resolve().parents[2]
SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,100}\Z")


def contract_sha256() -> str:
    """Bind a retry to the code, database migrations and DuckDB implementation."""
    digest = hashlib.sha256()
    paths = sorted(Path(__file__).parent.glob("*.py"))
    paths = [path for path in paths if not path.name.startswith("test_")]
    paths += [ROOT / "pipeline/preprocessing/common/curated_input.py"]
    paths += sorted((ROOT / "backend/src/main/resources/db/migration").glob("V*.sql"))
    for path in paths:
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_text(encoding="utf-8").encode())
        digest.update(b"\0")
    digest.update(json_bytes({"format": "postgres-copy-text-v1", "duckdb": duckdb.__version__}))
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_report(path: Path, report: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    temporary.replace(path)


def run(s3, snapshot: str, curated_run_id: str, execution_id: str,
        work_dir: Path, command: list[str] | None, *, workers: int = 4,
        threads: int = 4, memory: str = "4GB", verify_only: bool = False,
        failpoint: str | None = None) -> dict:
    if not SAFE_ID.fullmatch(execution_id):
        raise ValueError("execution ID must contain 1-100 letters, digits, underscores or hyphens")
    if not 1 <= workers <= 16 or not 1 <= threads <= 32:
        raise ValueError("workers must be 1-16 and threads must be 1-32")
    if not verify_only and not command:
        raise ValueError("an explicit PostgreSQL command is required")
    attempt_id = uuid.uuid4().hex
    root = Path(work_dir).resolve() / execution_id / attempt_id
    root.mkdir(parents=True, exist_ok=False)
    path = root / "execution_report.json"
    started = time.monotonic()
    report = {"execution_id": execution_id, "attempt_id": attempt_id,
              "started_at": utc_now(), "status": "PREPARING", "phase": "SELECT_INPUT",
              "mode": "VERIFY_ONLY" if verify_only else "LOAD",
              "snapshot": snapshot, "curated_run_id": curated_run_id,
              "contract_sha256": contract_sha256(), "report_path": str(path)}
    _write_report(path, report)
    print(f"Execution {execution_id}, attempt {attempt_id}: selecting approved input", flush=True)
    try:
        metadata = select_run(s3, snapshot, curated_run_id)
        report["input"] = metadata
        report["phase"] = "VALIDATE_INPUT"
        _write_report(path, report)
        if verify_only:
            prepared = prepare(s3, metadata, root, workers, threads, memory, export_csv=False)
            report.update(status="VERIFIED", validation=prepared["validation"], counts=prepared["counts"],
                          quality=prepared.get("quality", {}))
        else:
            with PgLoader(command, root) as database:
                try:
                    already_published = database.start(metadata, execution_id, report["contract_sha256"], attempt_id)
                    print("Validating files, schema, keys and field values", flush=True)
                    prepared = prepare(s3, metadata, root, workers, threads, memory,
                                       export_csv=not already_published)
                    report.update(validation=prepared["validation"], quality=prepared.get("quality", {}), phase="PUBLISH")
                    _write_report(path, report)
                    database.record_quality(report["quality"])
                    print("Reverifying published input" if already_published else "COPY to staging and publish", flush=True)
                    result = database.reverified() if already_published else database.publish(
                        prepared["csv_files"], prepared["counts"], failpoint=failpoint)
                    report.update(result)
                except BaseException as error:
                    try:
                        database.fail(error)
                    except Exception as history_error:
                        report["failure_history_error"] = str(history_error)
                    raise
        report["phase"] = "COMPLETE"
    except BaseException as error:
        report.update(status="FAILED", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        report.update(finished_at=utc_now(), elapsed_seconds=round(time.monotonic() - started, 3))
        _write_report(path, report)
        print(f"{report['status']}: {path}", flush=True)
    return report


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--snapshot", required=True)
    result.add_argument("--curated-run-id", required=True)
    result.add_argument("--execution-id", required=True)
    result.add_argument("--work-dir", type=Path, default=ROOT / "data/postgresql")
    result.add_argument("--verify-only", action="store_true", help="validate input without connecting to PostgreSQL")
    target = result.add_mutually_exclusive_group()
    target.add_argument("--docker-container", help="existing local PostgreSQL container")
    target.add_argument("--psql", help="path to local psql executable; connection settings use libpq environment")
    result.add_argument("--database", help="explicit database name (required unless --verify-only)")
    result.add_argument("--db-user", default="postgres")
    result.add_argument("--workers", type=int, default=4)
    result.add_argument("--threads", type=int, default=4)
    result.add_argument("--memory-limit", default="4GB")
    return result


def main() -> int:
    arguments = parser()
    args = arguments.parse_args()
    command = None
    if not args.verify_only:
        if not args.database or not (args.docker_container or args.psql):
            arguments.error("--database and either --docker-container or --psql are required")
        # Accept a database name only: libpq also accepts credential-bearing DSNs
        # in -d, which would expose secrets through command lines and reports.
        if not SAFE_ID.fullmatch(args.database) or not SAFE_ID.fullmatch(args.db_user):
            arguments.error("database and user must be simple names; use libpq environment for authentication")
        if args.docker_container:
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", args.docker_container):
                arguments.error("invalid Docker container name")
            command = ["docker", "exec", "-i", args.docker_container, "psql"]
        else:
            command = [args.psql]
        command += ["-U", args.db_user, "-d", args.database]
    try:
        run(client(), args.snapshot, args.curated_run_id, args.execution_id,
            args.work_dir, command, workers=args.workers, threads=args.threads,
            memory=args.memory_limit, verify_only=args.verify_only)
    except Exception as error:
        print(f"Load failed ({type(error).__name__}); see the execution report for details", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
