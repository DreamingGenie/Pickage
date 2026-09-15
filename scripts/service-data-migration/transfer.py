#!/usr/bin/env python3
"""Selected dump, checksum verification and guarded candidate restore.

This tool intentionally does not create or replace a database.  A candidate
database must be prepared separately and must have none of the selected
tables before ``restore`` is run.  Failed restores are rebuilt in a fresh
candidate; this tool does not pretend that pg_restore is safely resumable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from pathlib import PurePosixPath
from typing import Iterable, Sequence


TOOL_VERSION = "1"
CHILD_SCHEMA = "vd193_reload_20260912_ready01"
ROOT_TABLES = (
    "package",
    "version",
    "snapshot",
    "package_snapshot",
    "package_version_snapshot",
)
CHILD_PATTERN = re.compile(r"^d\d{8}$")
CANDIDATE_PATTERN = re.compile(r"^pickage_import_341_[a-z0-9][a-z0-9_-]*$")
DB_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
# PostgreSQL's exported snapshot names are generated as two hexadecimal
# transaction identifiers followed by a decimal sequence number.  Keep this
# deliberately narrow: accepting arbitrary strings here would make a typo
# reach pg_dump after the archive directory has already been created.
SNAPSHOT_TOKEN_PATTERN = re.compile(r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{8}-[0-9]+$")
MANIFEST_NAME = "archive-manifest.json"


class TransferError(RuntimeError):
    """A checked failure which should result in a concise CLI error."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_snapshot_token(value: str | None) -> str | None:
    """Validate an optional token returned by ``pg_export_snapshot``."""
    if value is None:
        return None
    if not isinstance(value, str) or not SNAPSHOT_TOKEN_PATTERN.fullmatch(value):
        raise TransferError(
            "snapshot token must match PostgreSQL's exported form "
            "XXXXXXXX-XXXXXXXX-N"
        )
    return value


def archive_files(archive: Path) -> list[Path]:
    if not archive.is_dir():
        raise TransferError(f"archive directory does not exist: {archive}")
    entries = list(archive.iterdir())
    if archive.is_symlink() or any(path.is_symlink() or not path.is_file() for path in entries):
        raise TransferError("archive cannot contain symbolic links")
    return sorted(entries)


def write_json(path: Path, payload: dict) -> None:
    """Write JSON atomically, tolerating transient Windows sharing locks.

    A unique sibling temporary file avoids collisions with a reader or with
    another writer.  ``os.replace`` remains the only operation that changes
    the destination, so a failed write leaves its previous contents intact.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    try:
        with temporary.open("w", encoding="utf-8", newline="") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        attempts = 8 if os.name == "nt" else 1
        delay = 0.05
        for attempt in range(attempts):
            try:
                os.replace(temporary, path)
                return
            except OSError as exc:
                winerror = getattr(exc, "winerror", None)
                retryable = os.name == "nt" and winerror in {5, 32, 33}
                if not retryable or attempt + 1 == attempts:
                    raise
                time.sleep(delay)
                delay = min(delay * 2, 0.5)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def manifest_path(archive: Path) -> Path:
    return archive.parent / MANIFEST_NAME


def write_manifest(
    archive: Path,
    *,
    source_db: str,
    jobs: int,
    compression: str,
    snapshot: str | None = None,
) -> Path:
    files = [
        {"path": str(path.relative_to(archive)).replace(os.sep, "/"), "size": path.stat().st_size, "sha256": sha256_file(path)}
        for path in archive_files(archive)
    ]
    payload = {
        "tool_version": TOOL_VERSION,
        "created_at": utc_now(),
        "source_db": source_db,
        "format": "pg_dump-directory",
        "jobs": jobs,
        "compression": compression,
        "snapshot": validate_snapshot_token(snapshot),
        "root_tables": list(ROOT_TABLES),
        "child_schema": CHILD_SCHEMA,
        "files": files,
    }
    output = manifest_path(archive)
    write_json(output, payload)
    return output


def load_manifest(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TransferError(f"cannot read manifest: {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("format") != "pg_dump-directory" or payload.get("child_schema") != CHILD_SCHEMA:
        raise TransferError("manifest is not a service-data-migration archive")
    if tuple(payload.get("root_tables", ())) != ROOT_TABLES:
        raise TransferError("manifest target table allowlist does not match this tool")
    if not isinstance(payload.get("files"), list):
        raise TransferError("manifest files entry is missing")
    paths = []
    for entry in payload["files"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise TransferError("manifest has an invalid file entry")
        relative = entry["path"]
        if not re.fullmatch(r"(?:toc\.dat|[0-9]+\.dat(?:\.(?:gz|zst|lz4))?)", relative):
            raise TransferError("manifest contains an unsafe or unsupported file path")
        if type(entry.get("size")) is not int or entry["size"] < 0 or not isinstance(entry.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
            raise TransferError("manifest has an invalid file size or digest")
        paths.append(relative)
    if len(paths) != len(set(paths)) or "toc.dat" not in paths:
        raise TransferError("manifest contains duplicate paths or lacks toc.dat")
    return payload


def verify_manifest(archive: Path, path: Path | None = None) -> dict:
    manifest = load_manifest(path or manifest_path(archive))
    actual = {str(file.relative_to(archive)).replace(os.sep, "/"): file for file in archive_files(archive)}
    expected = {entry["path"]: entry for entry in manifest["files"]}
    if set(actual) != set(expected):
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        raise TransferError(f"archive file set differs; missing={missing[:3]} extra={extra[:3]}")
    for relative, entry in expected.items():
        file = actual[relative]
        size = file.stat().st_size
        digest = sha256_file(file)
        if size != entry.get("size") or digest != entry.get("sha256"):
            raise TransferError(f"archive checksum mismatch: {relative}")
    return manifest


def command_prefix(container: str | None) -> list[str]:
    return ["docker", "exec", container] if container else []


def display_command(command: Sequence[str]) -> str:
    return " ".join(shlex.quote(str(item)) for item in command)


def run_checked(command: Sequence[str], *, label: str, capture: bool = False) -> subprocess.CompletedProcess[str]:
    print(f"[{label}] {display_command(command)}", file=sys.stderr)
    try:
        result = subprocess.run(
            list(command),
            check=False,
            text=True,
            capture_output=capture,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise TransferError(f"{label} could not start: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip() if capture else "see command output"
        raise TransferError(f"{label} failed with exit code {result.returncode}: {detail[-1000:]}")
    return result


def client_command(binary: str, container: str | None, args: Iterable[str]) -> list[str]:
    flags = ["-X", "-v", "ON_ERROR_STOP=1"] if binary == "psql" else []
    return command_prefix(container) + [binary, *flags, *args]


def with_user(args: argparse.Namespace, command_args: Iterable[str]) -> list[str]:
    return ["--username", args.user, *command_args]


def archive_path_for_client(args: argparse.Namespace) -> str:
    if args.container and not args.container_archive_dir:
        raise TransferError("--container-archive-dir is required when using --container")
    if args.container:
        return str(PurePosixPath(args.container_archive_dir) / PurePosixPath(args.archive_dir.name))
    return str(args.archive_dir)


def expected_toc_lines(toc: str) -> None:
    """Reject a selected archive containing an unexpected schema/table.

    pg_restore's list format is intentionally parsed conservatively.  Object
    types not mentioning a table/schema are allowed because PostgreSQL emits
    comments and constraint/index records in several version-specific forms.
    """
    table_pattern = re.compile(r"\bTABLE(?:\s+DATA|\s+ATTACH)?\s+(\S+)\s+(\S+)")
    # pg_restore --list writes schema entries as ``SCHEMA - name``.
    schema_pattern = re.compile(r"\bSCHEMA\s+(?:-\s+)?(\S+)")
    root_seen: set[str] = set()
    root_data_seen: set[str] = set()
    child_data_seen = 0
    forbidden_index_names = {"idx_package_name_prefix", "idx_version_pkg_ordinal", "idx_pvs_pkg_snapshot"}
    forbidden_object_pattern = re.compile(r"\b(?:SEQUENCE|VIEW|MATERIALIZED VIEW|FOREIGN TABLE|TYPE|FUNCTION|PROCEDURE|TRIGGER|RULE)\b")
    for raw_line in toc.splitlines():
        line = raw_line.strip()
        # PG16 entries start with a dump id; leading ';' lines are comments.
        if not line or line.startswith(";"):
            continue
        if any(re.search(rf"\b{re.escape(name)}\b", line) for name in forbidden_index_names):
            raise TransferError("archive contains a V4 index; apply V4 separately instead")
        if forbidden_object_pattern.search(line):
            raise TransferError(f"archive contains an unsupported object: {line}")
        schema_match = schema_pattern.search(line)
        if schema_match:
            schema = schema_match.group(1).strip('"')
            if schema not in {"public", CHILD_SCHEMA}:
                raise TransferError(f"archive contains unexpected schema: {schema}")
        table_match = table_pattern.search(line)
        if not table_match:
            continue
        schema = table_match.group(1).strip('"')
        table = table_match.group(2).strip('"')
        allowed = schema == "public" and table in ROOT_TABLES
        allowed = allowed or (schema == CHILD_SCHEMA and bool(CHILD_PATTERN.fullmatch(table)))
        if not allowed:
            raise TransferError(f"archive contains unexpected table: {schema}.{table}")
        is_data = "TABLE DATA" in line
        if schema == "public" and table in ROOT_TABLES:
            root_seen.add(table)
            if is_data:
                root_data_seen.add(table)
        elif schema == CHILD_SCHEMA and CHILD_PATTERN.fullmatch(table) and is_data:
            child_data_seen += 1
    if set(ROOT_TABLES) != root_seen:
        raise TransferError(f"archive root table set is incomplete: {sorted(root_seen)}")
    expected_root_data = set(ROOT_TABLES[:-1])
    if root_data_seen != expected_root_data:
        raise TransferError(f"archive root data set is invalid: {sorted(root_data_seen)}")
    if child_data_seen == 0:
        raise TransferError("archive does not contain any partition child data")


def validate_toc(archive: Path, args: argparse.Namespace) -> str:
    archive_for_client = archive_path_for_client(args)
    command = client_command("pg_restore", args.container, with_user(args, ["--list", archive_for_client]))
    result = run_checked(command, label="archive TOC", capture=True)
    expected_toc_lines(result.stdout)
    return result.stdout


def verify_container_files(archive: Path, args: argparse.Namespace, manifest: dict | None = None) -> None:
    """Verify that a mounted container archive is the host archive."""
    if not args.container:
        return
    if manifest is None:
        manifest = load_manifest(manifest_path(archive))
    container_root = PurePosixPath(args.container_archive_dir) / PurePosixPath(archive.name)
    expected = {entry["path"]: entry["sha256"] for entry in manifest["files"]}
    files = list(expected)
    for start in range(0, len(files), 200):
        batch = files[start:start + 200]
        command = client_command("sha256sum", args.container, [str(container_root / PurePosixPath(relative)) for relative in batch])
        result = run_checked(command, label="container archive checksum", capture=True)
        received = {}
        for line in result.stdout.splitlines():
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                received[PurePosixPath(parts[1].strip()).relative_to(container_root).as_posix()] = parts[0]
        for relative in batch:
            if received.get(relative) != expected[relative]:
                raise TransferError(f"container archive checksum mismatch: {relative}")


def dump_archive(args: argparse.Namespace) -> Path:
    if not DB_NAME_PATTERN.fullmatch(args.source_db):
        raise TransferError("source DB must be a plain database name, not a connection URI")
    snapshot = validate_snapshot_token(getattr(args, "snapshot", None))
    archive = Path(args.archive_dir).resolve()
    if manifest_path(archive).exists():
        raise TransferError("run directory already has a manifest; choose a new run directory")
    if archive.exists():
        if any(archive.iterdir()):
            raise TransferError(f"refusing to overwrite non-empty archive: {archive}")
    else:
        archive.mkdir(parents=True)
    archive_for_client = archive_path_for_client(args)
    dump_args = [
        "--format=directory",
        f"--file={archive_for_client}",
        f"--dbname={args.source_db}",
        f"--jobs={args.jobs}",
        f"--compress={args.compression}",
        "--lock-wait-timeout=30s",
        "--no-owner",
        "--no-privileges",
    ]
    if snapshot is not None:
        dump_args.append(f"--snapshot={snapshot}")
    dump_args.extend(f"--table=public.{table}" for table in ROOT_TABLES[:-1])
    dump_args.append("--table-and-children=public.package_version_snapshot")
    started = time.monotonic()
    run_checked(client_command("pg_dump", args.container, with_user(args, dump_args)), label="pg_dump")
    validate_toc(archive, args)
    manifest = write_manifest(
        archive,
        source_db=args.source_db,
        jobs=args.jobs,
        compression=args.compression,
        snapshot=snapshot,
    )
    if args.container:
        verify_container_files(archive, args)
    print(json.dumps({"archive": str(archive), "manifest": str(manifest), "elapsed_seconds": round(time.monotonic() - started, 3)}))
    return archive


def assert_candidate(args: argparse.Namespace) -> None:
    candidate = args.candidate_db
    if not CANDIDATE_PATTERN.fullmatch(candidate):
        raise TransferError("candidate DB must match pickage_import_341_<run-id>")
    forbidden = {args.source_db, args.service_db}
    if candidate in forbidden:
        raise TransferError("candidate DB must differ from source and service DB")
    for label, value in (("candidate", candidate), ("source", args.source_db), ("service", args.service_db)):
        if not DB_NAME_PATTERN.fullmatch(value):
            raise TransferError(f"{label} DB must be a plain database name, not a connection URI")


def assert_candidate_empty(args: argparse.Namespace) -> None:
    query = (
        "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE (n.nspname='public' AND c.relname IN "
        "('package','version','snapshot','package_snapshot','package_version_snapshot')) "
        f"OR (n.nspname='{CHILD_SCHEMA}' AND c.relname ~ '^d[0-9]{{8}}$');"
    )
    command = client_command("psql", args.container, with_user(args, ["--dbname", args.candidate_db, "--tuples-only", "--no-align", "--command", query]))
    result = run_checked(command, label="candidate emptiness", capture=True)
    value = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    if value != "0":
        raise TransferError("candidate already contains selected tables; rebuild a fresh candidate")
    unknown_query = (
        "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname NOT IN ('pg_catalog','information_schema') "
        "AND n.nspname !~ '^pg_toast' AND n.nspname !~ '^pg_temp' "
        "AND c.relkind IN ('r','p','v','m','f','S') "
        "AND NOT (n.nspname='public' AND c.relname='flyway_schema_history');"
    )
    unknown = run_checked(
        client_command("psql", args.container, with_user(args, ["--dbname", args.candidate_db, "--tuples-only", "--no-align", "--command", unknown_query])),
        label="candidate object allowlist",
        capture=True,
    )
    unknown_value = unknown.stdout.strip().splitlines()[-1] if unknown.stdout.strip() else ""
    if unknown_value != "0":
        raise TransferError("candidate contains objects outside Flyway history; rebuild a clean candidate")
    history_query = (
        "SELECT (count(*)=1 AND count(*) FILTER (WHERE version='1' AND type='SQL' "
        "AND success AND checksum IS NOT NULL)=1)::text FROM public.flyway_schema_history;"
    )
    history = run_checked(client_command("psql", args.container, with_user(args, [
        "--dbname", args.candidate_db, "--tuples-only", "--no-align", "--command", history_query
    ])), label="candidate V1 history", capture=True)
    if history.stdout.strip() != "true":
        raise TransferError("candidate requires genuine successful V1 history; run candidate preparation first")


def restore_archive(args: argparse.Namespace) -> None:
    assert_candidate(args)
    archive = Path(args.archive_dir).resolve()
    manifest = verify_manifest(archive, Path(args.manifest) if args.manifest else None)
    if args.candidate_db == manifest.get("source_db"):
        raise TransferError("candidate is the archive source database")
    validate_toc(archive, args)
    verify_container_files(archive, args, manifest)
    assert_candidate_empty(args)
    archive_for_client = archive_path_for_client(args)
    status_path = archive.parent / (args.candidate_db + ".restore-status.json")
    if status_path.exists():
        raise TransferError("candidate has a prior restore attempt; use a new candidate")
    status = {"candidate_db": args.candidate_db, "archive": str(archive), "started_at": utc_now(),
              "pid": os.getpid(), "status": "RUNNING", "ready_for_service": False, "phases": []}
    write_json(status_path, status)
    schema_sql = f'CREATE SCHEMA IF NOT EXISTS "{CHILD_SCHEMA}";'
    try:
        run_checked(client_command("psql", args.container, with_user(args, ["--dbname", args.candidate_db, "--command", schema_sql])), label="create child schema")
    except TransferError as exc:
        status["failed_phase"] = "create child schema"
        status["error"] = str(exc)
        status["failed_at"] = utc_now()
        status["status"] = "FAILED"
        write_json(status_path, status)
        raise
    for section in ("pre-data", "data", "post-data"):
        started = time.monotonic()
        restore_args = [
            "--dbname", args.candidate_db,
            "--section", section,
            "--no-owner",
            "--no-privileges",
            "--exit-on-error",
            "--jobs", str(args.jobs),
            archive_for_client,
        ]
        try:
            run_checked(client_command("pg_restore", args.container, with_user(args, restore_args)), label=f"restore {section}")
        except TransferError as exc:
            status["failed_phase"] = section
            status["error"] = str(exc)
            status["failed_at"] = utc_now()
            status["status"] = "FAILED"
            write_json(status_path, status)
            raise
        status["phases"].append({"name": section, "completed_at": utc_now(), "elapsed_seconds": round(time.monotonic() - started, 3)})
        write_json(status_path, status)
    status["completed_at"] = utc_now()
    status["status"] = "RESTORED_UNVERIFIED"
    write_json(status_path, status)
    print(json.dumps(status))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    dump = sub.add_parser("dump", help="create a new selected pg_dump directory archive")
    dump.add_argument("--source-db", required=True)
    dump.add_argument("--user", default="postgres")
    dump.add_argument("--archive-dir", type=Path, required=True)
    dump.add_argument("--jobs", type=int, default=4)
    dump.add_argument("--compression", default="zstd:1", choices=("zstd:1", "gzip:1"))
    dump.add_argument("--snapshot", type=validate_snapshot_token,
                      help="PostgreSQL exported snapshot token from pg_export_snapshot()")
    dump.add_argument("--container")
    dump.add_argument("--container-archive-dir")

    command = sub.add_parser("verify", help="verify an archive and its SHA-256 manifest")
    command.add_argument("--archive-dir", type=Path, required=True)
    command.add_argument("--manifest", type=Path)
    command.add_argument("--user", default="postgres")
    command.add_argument("--container")
    command.add_argument("--container-archive-dir")

    restore = sub.add_parser("restore", help="restore a verified archive into a fresh candidate database")
    restore.add_argument("--archive-dir", type=Path, required=True)
    restore.add_argument("--manifest", type=Path)
    restore.add_argument("--candidate-db", required=True)
    restore.add_argument("--source-db", required=True)
    restore.add_argument("--service-db", required=True)
    restore.add_argument("--user", default="postgres")
    restore.add_argument("--jobs", type=int, default=2)
    restore.add_argument("--container")
    restore.add_argument("--container-archive-dir")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if getattr(args, "jobs", 1) < 1:
            raise TransferError("jobs must be at least 1")
        if args.command == "dump":
            dump_archive(args)
        elif args.command == "verify":
            archive = Path(args.archive_dir).resolve()
            manifest = verify_manifest(archive, Path(args.manifest) if args.manifest else None)
            validate_toc(archive, args)
            verify_container_files(archive, args, manifest)
            print(json.dumps({"ok": True, "files": len(manifest["files"]), "archive": str(archive)}))
        else:
            restore_archive(args)
        return 0
    except TransferError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
