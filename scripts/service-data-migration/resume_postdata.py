#!/usr/bin/env python3
"""Safely resume post-data objects for an existing 341 candidate database.

The original restore is deliberately not resumed by replaying an entire
``post-data`` section.  This command reconciles the candidate with a
schema-only reference restored from the *same* archive, replays only missing
catalog objects, refreshes statistics, and records a checkpoint before the
expensive foreign-key validation is attempted.

The command is intentionally conservative: an unexpected or semantically
different object stops the run.  It never drops objects, edits pg_catalog, or
changes the service database.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import Callable, Iterable, Sequence

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from transfer import CHILD_SCHEMA, CANDIDATE_PATTERN, TransferError, verify_manifest, write_json, verify_container_files, expected_toc_lines
except ImportError:  # pragma: no cover - allows direct package-style imports
    from .transfer import CHILD_SCHEMA, CANDIDATE_PATTERN, TransferError, verify_manifest, write_json


ROOT_TABLES = {"package", "version", "snapshot", "package_snapshot", "package_version_snapshot"}
SERVICE_DB = "pickage"
SCHEMA_NAMES = {"public", CHILD_SCHEMA}
TOC_CONSTRAINT_RE = re.compile(r"\bCONSTRAINT\s+(\S+)\s+(\S+)\s+(\S+)")
TOC_INDEX_RE = re.compile(r"\b(INDEX ATTACH|INDEX)\s+(\S+)\s+(\S+)")


def normalize_sql(value: str) -> str:
    """Normalize catalog-rendered SQL without changing its meaning."""
    return value.strip()


def archive_identity(archive: Path, manifest_path: Path | None = None) -> dict:
    """Return a cheap, stable identity bound to every archive file.

    ``verify_manifest`` has already checked every file.  Hashing the manifest
    binds the checkpoint to the complete file list and each file digest while
    avoiding a second 10 GiB archive read on normal resume.
    """
    manifest = manifest_path or archive.parent / "archive-manifest.json"
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    return {"archive_name": archive.name, "manifest_sha256": digest}


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def validate_data_receipt(work_dir: Path, candidate: str) -> None:
    path = work_dir / f"{candidate}.restore-status.json"
    if not path.exists():
        raise ResumeError(f"completed data restore receipt is missing: {path}")
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResumeError(f"invalid data restore receipt: {exc}") from exc
    names = {phase.get("name") for phase in receipt.get("phases", []) if isinstance(phase, dict)}
    if receipt.get("candidate_db") not in (None, candidate) or "data" not in names:
        raise ResumeError("data restore receipt does not prove a completed data phase")


def validate_reference_receipt(path: Path | None, reference_db: str, toc_sha256: str) -> None:
    if path is None:
        return
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResumeError(f"invalid reference receipt: {exc}") from exc
    if receipt.get("reference_db") != reference_db or receipt.get("archive_toc_sha256") != toc_sha256:
        raise ResumeError("reference catalog receipt is not bound to this archive TOC")


def _object_key(row: dict) -> tuple:
    if row["kind"] == "constraint":
        return (row["kind"], row["schema"], row["table"], row["name"])
    if row["kind"] == "index":
        return (row["kind"], row["schema"], row["name"])
    return (row["kind"], row["schema"], row.get("parent_schema", row["schema"]), row["child"], row["parent"])


def catalog_diff(expected: dict, actual: dict, *, allow_invalid_parent_pk: bool = True) -> dict:
    """Compare semantic catalog snapshots and return missing/mismatched objects.

    OIDs and filenodes are deliberately absent from the snapshot contract.
    The only intermediate exception is the partitioned PVS parent primary-key
    index, which is invalid until all child indexes are attached.
    """
    result = {"missing": [], "mismatched": [], "extra": []}
    for kind in ("constraints", "indexes", "inherits"):
        wanted = {_object_key(row): row for row in expected.get(kind, [])}
        found = {_object_key(row): row for row in actual.get(kind, [])}
        for key in sorted(wanted):
            if key not in found:
                result["missing"].append(wanted[key])
                continue
            before, after = wanted[key], found[key]
            comparable = {k: v for k, v in before.items() if k not in {"oid", "index_oid", "filenode"}}
            received = {k: v for k, v in after.items() if k not in {"oid", "index_oid", "filenode"}}
            if kind == "indexes" and allow_invalid_parent_pk:
                parent = before.get("table") == "package_version_snapshot" and before.get("is_primary")
                if parent:
                    comparable.pop("indisvalid", None)
                    comparable.pop("indisready", None)
                    received.pop("indisvalid", None)
                    received.pop("indisready", None)
            if kind == "constraints":
                comparable["definition"] = normalize_sql(str(comparable.get("definition", "")))
                received["definition"] = normalize_sql(str(received.get("definition", "")))
            if kind == "indexes":
                comparable["definition"] = normalize_sql(str(comparable.get("definition", "")))
                received["definition"] = normalize_sql(str(received.get("definition", "")))
            if comparable != received:
                result["mismatched"].append({"expected": before, "actual": after})
        for key in sorted(found.keys() - wanted.keys()):
            result["extra"].append(found[key])
    return result


def missing_table_attachments(diff: dict) -> list[dict]:
    """Table partition attachments are pre-data objects and never replayed."""
    return [row for row in diff.get("missing", [])
            if row.get("kind") == "inherits" and re.fullmatch(r"d\d{8}", row.get("child", ""))]


def parse_toc_lines(toc: str) -> list[dict]:
    """Parse the object-bearing portion of a pg_restore list output."""
    parsed = []
    for line in toc.splitlines():
        if not line.strip() or line.lstrip().startswith(";"):
            continue
        object_id = line.split(";", 1)[0].strip()
        if not object_id.isdigit():
            continue
        constraint = TOC_CONSTRAINT_RE.search(line)
        if constraint:
            schema, table, name = constraint.groups()
            parsed.append({"id": object_id, "kind": "constraint", "schema": schema.strip('"'),
                           "table": table.strip('"'), "name": name.strip('"'), "line": line})
            continue
        index = TOC_INDEX_RE.search(line)
        if index:
            kind, schema, name = index.groups()
            parsed.append({"id": object_id, "kind": kind.lower().replace(" ", "_"),
                           "schema": schema.strip('"'), "name": name.strip('"'), "line": line})
    return parsed


def select_toc_lines(toc: str, expected: dict, actual: dict, *, include_foreign_keys: bool) -> list[str]:
    """Select missing index/constraint/attachment records in dependency order."""
    diff = catalog_diff(expected, actual)
    missing_constraints = {_object_key(x) for x in diff["missing"] if x.get("kind") == "constraint"}
    missing_indexes = {_object_key(x) for x in diff["missing"] if x.get("kind") == "index"}
    expected_constraints = {_object_key(x): x for x in expected.get("constraints", [])}
    actual_inherits = {_object_key(x) for x in actual.get("inherits", [])}
    selected: list[dict] = []
    for item in parse_toc_lines(toc):
        if item["schema"] not in SCHEMA_NAMES:
            continue
        if item["kind"] == "constraint":
            candidates = [x for x in expected_constraints.values()
                          if x.get("schema") == item["schema"] and x.get("table") == item.get("table")
                          and x.get("name") == item["name"]]
            if not candidates or _object_key(candidates[0]) not in missing_constraints:
                continue
            if not include_foreign_keys and candidates[0].get("contype") == "f":
                continue
            selected.append(item)
        elif item["kind"] == "index":
            if any(x.get("schema") == item["schema"] and x.get("name") == item["name"]
                   for x in diff["missing"] if x.get("kind") == "index"):
                selected.append(item)
        elif item["kind"] == "index_attach":
            # pg_restore identifies an attachment by its child index name.
            if not any(x.get("child") == item["name"] for x in actual.get("inherits", [])):
                selected.append(item)
    # Index creation must precede INDEX ATTACH; pg_restore's own TOC order is
    # retained within each group.
    return [item["line"] for group in ("constraint", "index", "index_attach")
            for item in selected if item["kind"] == group]


CATALOG_SQL = f"""
WITH target AS (
  SELECT c.oid, n.nspname AS schema_name, c.relname
  FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
  WHERE (n.nspname='public' AND c.relname IN ('package','version','snapshot','package_snapshot','package_version_snapshot'))
     OR (n.nspname='{CHILD_SCHEMA}' AND c.relname ~ '^d[0-9]{{8}}$')
),
constraints AS (
  SELECT json_agg(json_build_object('kind','constraint','schema',n.nspname,'table',c.relname,
    'name',con.conname,'contype',con.contype,'definition',pg_get_constraintdef(con.oid),
    'convalidated',con.convalidated,'index_name',NULLIF(con.conindid::regclass::text,'-'))) AS value
  FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace
  WHERE con.conrelid IN (SELECT oid FROM target)),
indexes AS (
  SELECT json_agg(json_build_object('kind','index','schema',n.nspname,'table',c.relname,
    'name',i.relname,'definition',pg_get_indexdef(i.oid),'indisvalid',x.indisvalid,
    'indisready',x.indisready,'is_primary',x.indisprimary,'is_unique',x.indisunique)) AS value
  FROM pg_index x JOIN pg_class i ON i.oid=x.indexrelid JOIN pg_class c ON c.oid=x.indrelid
    JOIN pg_namespace n ON n.oid=i.relnamespace
  WHERE x.indrelid IN (SELECT oid FROM target)),
inherits AS (
  SELECT json_agg(json_build_object('kind','inherits','schema',np.nspname,
    'parent_schema',npp.nspname,'child',cp.relname,'parent',pp.relname)) AS value
  FROM pg_inherits h JOIN pg_class cp ON cp.oid=h.inhrelid JOIN pg_class pp ON pp.oid=h.inhparent
    JOIN pg_namespace np ON np.oid=cp.relnamespace JOIN pg_namespace npp ON npp.oid=pp.relnamespace
  WHERE np.nspname IN ('public','{CHILD_SCHEMA}')
    AND (cp.relname ~ '^d[0-9]{{8}}(?:_pkey)?$' OR pp.relname IN ('package_version_snapshot','package_version_snapshot_pkey')))
SELECT json_build_object('constraints',COALESCE((SELECT value FROM constraints),'[]'::json),
  'indexes',COALESCE((SELECT value FROM indexes),'[]'::json),
  'inherits',COALESCE((SELECT value FROM inherits),'[]'::json));
"""


class ResumeError(RuntimeError):
    pass


class Runner:
    def __init__(self, args: argparse.Namespace):
        self.args = args

    def docker(self, binary: str, *values: str, container: str | None = None) -> list[str]:
        return ["docker", "exec", "-i", container or self.args.postgres_container, binary, *values]

    def psql(self, db: str, query: str) -> str:
        command = self.docker("psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", self.args.user,
                              "-d", db, "-qAt", "-c", query)
        result = subprocess.run(command, text=True, capture_output=True, check=False, encoding="utf-8")
        if result.returncode:
            raise ResumeError((result.stderr or result.stdout)[-4000:])
        return result.stdout.strip()

    def catalog(self, db: str) -> dict:
        value = self.psql(db, CATALOG_SQL)
        return json.loads(value or "{}")

    def toc(self) -> str:
        archive_path = self.args.archive_client_path
        command = self.docker("pg_restore", "--list", archive_path, container=self.args.client_container)
        result = subprocess.run(command, text=True, capture_output=True, check=False, encoding="utf-8")
        if result.returncode:
            raise ResumeError((result.stderr or result.stdout)[-4000:])
        return result.stdout

    def restore_list(self, lines: list[str]) -> None:
        if not lines:
            return
        archive_path = self.args.archive_client_path
        command = self.docker("pg_restore", "-U", self.args.user, "-d", self.args.candidate_db,
                              "--no-owner", "--no-privileges", "--exit-on-error", "--use-list=/dev/stdin",
                              archive_path, container=self.args.client_container)
        result = subprocess.run(command, input="\n".join(lines) + "\n", text=True,
                                capture_output=True, check=False, encoding="utf-8")
        if result.returncode:
            raise ResumeError((result.stderr or result.stdout)[-5000:])

    def vacuum_analyze(self, actual: dict) -> int:
        names = ["public.version"] + [f'{CHILD_SCHEMA}.{row["table"]}'
                                       for row in actual.get("indexes", [])
                                       if row.get("schema") == CHILD_SCHEMA and row.get("table")]
        # The constraint list repeats each child; preserve order and avoid
        # issuing a VACUUM for a table that appears more than once.
        names = list(dict.fromkeys(names))
        for name in names:
            write_json(Path(self.args.output_dir) / 'maintenance-status.json',
                       {'status': 'RUNNING', 'current_table': name, 'completed_tables': names.index(name),
                        'total_tables': len(names), 'updated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
            self.psql(self.args.candidate_db, f"VACUUM (ANALYZE) {name};")
        write_json(Path(self.args.output_dir) / 'maintenance-status.json',
                   {'status': 'COMPLETE', 'completed_tables': len(names), 'total_tables': len(names)})
        return len(names)

    def benchmark(self, actual: dict) -> dict:
        leaves = sorted({row["table"] for row in actual.get("constraints", [])
                         if row.get("schema") == CHILD_SCHEMA and row.get("table")})
        if not leaves:
            return {"status": "NO_LEAF"}
        selected = [self.args.benchmark_leaf] if self.args.benchmark_leaf else list(dict.fromkeys([leaves[0], leaves[len(leaves)//2], leaves[-1]]))
        samples = [self.benchmark_leaf(leaf) for leaf in selected]
        return {'status': 'PASS' if all(s['status'] == 'PASS' for s in samples) else 'NEEDS_REVIEW',
                'samples': samples, 'supports_improved_fk': all(s.get('supports_improved_fk') for s in samples)}

    def benchmark_leaf(self, leaf):
        query = (f"SET statement_timeout='{int(self.args.benchmark_timeout_seconds)}s'; "
                 "SET work_mem='64MB'; SET hash_mem_multiplier=1; "
                 "SET max_parallel_workers_per_gather=0; "
                 "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) "
                 f"SELECT fk.package_id, fk.version FROM ONLY {CHILD_SCHEMA}.{leaf} fk "
                 "LEFT JOIN ONLY public.version pk ON pk.package_id=fk.package_id AND pk.version=fk.version "
                 "WHERE pk.package_id IS NULL AND fk.package_id IS NOT NULL AND fk.version IS NOT NULL;")
        try:
            raw = self.psql(self.args.candidate_db, query)
            # psql also prints the result of the preceding SET command.  The
            # JSON plan is the first JSON array in the output.
            start = raw.find("[")
            if start < 0:
                raise ResumeError("EXPLAIN returned no JSON plan")
            plan = json.loads(raw[start:])
            return {"status": "PASS", "leaf": leaf, "plan": plan,
                    "supports_improved_fk": plan_supports_improved_fk(plan)}
        except ResumeError as exc:
            return {"status": "TIMEOUT_OR_ERROR", "leaf": leaf, "error": str(exc),
                    "supports_improved_fk": False}


def plan_supports_improved_fk(plan: object) -> bool:
    """Require a sort-free plan and a zero-heap-fetch version IOS node."""
    nodes: list[dict] = []

    def walk(value: object) -> None:
        if isinstance(value, dict):
            if "Node Type" in value:
                nodes.append(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(plan)
    if any(node.get("Node Type") in ("Sort", "Incremental Sort") for node in nodes):
        return False
    scans = [n for n in nodes if n.get('Relation Name')]
    return (any(n['Relation Name'] == 'version' for n in scans)
            and any(n['Relation Name'].startswith('d') for n in scans)
            and all(n.get('Node Type') == 'Index Only Scan' and n.get('Heap Fetches') == 0
                    and 'Actual Rows' in n for n in scans))


def assert_safe_args(args: argparse.Namespace) -> None:
    if not CANDIDATE_PATTERN.fullmatch(args.candidate_db):
        raise ResumeError("candidate DB must match pickage_import_341_<run-id>")
    if args.candidate_db in {args.source_db, args.service_db, SERVICE_DB}:
        raise ResumeError("candidate DB must differ from source and service DB")
    if args.candidate_db == args.reference_db:
        raise ResumeError("candidate and reference DB must differ")
    if not CANDIDATE_PATTERN.fullmatch(args.reference_db):
        raise ResumeError('Reference must also be an isolated 341 database')
    if args.benchmark_leaf and not re.fullmatch(r'd[0-9]{8}', args.benchmark_leaf):
        raise ResumeError('Invalid benchmark leaf')
    if args.through == "all" and args.benchmark_timeout_seconds < 1:
        raise ResumeError("benchmark timeout must be positive")


def no_candidate_backends(runner: Runner) -> None:
    candidate = runner.args.candidate_db.replace("'", "''")
    reference = runner.args.reference_db.replace("'", "''")
    query = ("SELECT count(*) FROM pg_stat_activity "
             f"WHERE datname IN ('{candidate}','{reference}') AND pid<>pg_backend_pid() "
             "AND backend_type='client backend';")
    value = runner.psql("postgres", query)
    if value.strip() != "0":
        raise ResumeError("existing PostgreSQL sessions are present; quiesce old restore workers first")


def load_checkpoint(path: Path, identity: dict, candidate: str) -> dict | None:
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResumeError(f"invalid resume checkpoint: {exc}") from exc
    if state.get("candidate_db") != candidate or state.get("archive_identity") != identity:
        raise ResumeError("resume checkpoint identity does not match archive or candidate")
    return state


def run(args: argparse.Namespace, runner: Runner | None = None) -> dict:
    assert_safe_args(args)
    args.archive = Path(args.archive_dir).resolve()
    if not args.archive.is_dir():
        raise ResumeError(f"archive does not exist: {args.archive}")
    manifest = verify_manifest(args.archive, Path(args.manifest) if args.manifest else None)
    if manifest['source_db'] != args.source_db or args.candidate_db == manifest['source_db']:
        raise ResumeError('Archive source identity differs')
    verify_container_files(args.archive, SimpleNamespace(container=args.client_container,
                           container_archive_dir=str(PurePosixPath(args.archive_client_path).parent)), manifest)
    identity = archive_identity(args.archive, Path(args.manifest) if args.manifest else None)
    checkpoint_path = Path(args.output_dir).resolve() / "resume-status.json"
    validate_data_receipt(Path(args.work_dir).resolve(), args.candidate_db)
    checkpoint = load_checkpoint(checkpoint_path, identity, args.candidate_db)
    resumed_prepared = bool(checkpoint and checkpoint.get("status") == "PREPARED")
    runner = runner or Runner(args)
    no_candidate_backends(runner)
    toc = runner.toc()
    expected_toc_lines(toc)
    receipt_path = Path(args.reference_receipt) if args.reference_receipt else Path(args.output_dir).resolve() / 'reference-receipt.json'
    if not receipt_path.exists():
        raise ResumeError('Reference receipt is required')
    validate_reference_receipt(receipt_path, args.reference_db, hashlib.sha256((args.archive / 'toc.dat').read_bytes()).hexdigest())
    expected = runner.catalog(args.reference_db)
    actual = runner.catalog(args.candidate_db)
    if checkpoint and checkpoint.get("status") == "COMPLETE":
        final = catalog_diff(expected, actual, allow_invalid_parent_pk=False)
        if final["missing"] or final["mismatched"] or final["extra"]:
            raise ResumeError("completed checkpoint no longer matches candidate catalog")
        return checkpoint
    if checkpoint and checkpoint.get("status") == "PREPARED" and args.through == "prepare":
        prepared = catalog_diff(expected, actual, allow_invalid_parent_pk=False)
        if prepared["mismatched"] or prepared["extra"] or any(x.get("contype") != "f" for x in prepared["missing"]):
            raise ResumeError("prepared checkpoint no longer matches candidate catalog")
        return checkpoint
    if resumed_prepared and args.through == "all" and not checkpoint.get("ready_for_fk"):
        raise ResumeError("checkpoint benchmark does not support the improved FK plan; review it before --through all")
    initial = catalog_diff(expected, actual)
    if initial["mismatched"] or initial["extra"]:
        raise ResumeError("candidate catalog has mismatched or unexpected objects")
    if missing_table_attachments(initial):
        raise ResumeError("candidate is missing table partition attachments; post-data resume is unsafe")
    toc = runner.toc()
    receipt_path = Path(args.reference_receipt) if args.reference_receipt else Path(args.output_dir).resolve() / "reference-receipt.json"
    if not receipt_path.exists():
        raise ResumeError(f"reference catalog receipt is missing: {receipt_path}")
    validate_reference_receipt(receipt_path, args.reference_db,
                               hashlib.sha256((args.archive / "toc.dat").read_bytes()).hexdigest())
    selected = select_toc_lines(toc, expected, actual,
                                include_foreign_keys=args.through == "all" and resumed_prepared)
    state = checkpoint or {"status": "RUNNING", "candidate_db": args.candidate_db,
             "reference_db": args.reference_db, "archive_identity": identity,
             "archive_manifest": manifest.get("created_at"),
             "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "phases": []}
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    state["objects"] = [{"id": item["id"], "kind": item["kind"], "schema": item["schema"],
                          "name": item["name"], "status": "PLANNED"}
                         for item in parse_toc_lines("\n".join(selected))]
    write_json(checkpoint_path, state)
    try:
        for index, line in enumerate(selected):
            state['status'] = 'RUNNING'
            state['current_object'] = state['objects'][index]
            state['updated_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
            write_json(checkpoint_path, state)
            at = time.monotonic()
            runner.restore_list([line])
            state["objects"][index]["status"] = "APPLIED"
            state['objects'][index]['elapsed_seconds'] = round(time.monotonic()-at, 3)
            state["objects"][index]["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            write_json(checkpoint_path, state)
        actual = runner.catalog(args.candidate_db)
        after_objects = catalog_diff(expected, actual, allow_invalid_parent_pk=False)
        if after_objects["mismatched"] or after_objects["extra"] or any(x.get("contype") != "f" for x in after_objects["missing"]):
            raise ResumeError("non-FK post-data objects remain missing or mismatched after replay")
        state["phases"].append({"name": "restore_missing_postdata", "objects": len(selected)})

        needs_prepare = not resumed_prepared
        if needs_prepare:
            state["vacuum_tables"] = runner.vacuum_analyze(actual)
            state["phases"].append({"name": "vacuum_analyze", "tables": state["vacuum_tables"]})
            state["benchmark"] = runner.benchmark(actual)
            write_json(Path(args.output_dir) / "benchmark.json", state["benchmark"])
            state["phases"].append({"name": "benchmark_fk_plan", "status": state["benchmark"]["status"]})
            state["ready_for_fk"] = bool(state["benchmark"].get("supports_improved_fk"))
            state["status"] = "PREPARED"
            write_json(checkpoint_path, state)
            if args.through == "prepare" or not state["ready_for_fk"]:
                if args.through == "all" and not state["ready_for_fk"]:
                    state["status"] = "NEEDS_REVIEW"
                    state["error"] = "benchmark did not prove an improved FK plan"
                    write_json(checkpoint_path, state)
                return state

            # A fresh --through all run passed the same gate as a resumed run;
            # only now select and restore the foreign-key constraints.
            expected = runner.catalog(args.reference_db)
            actual = runner.catalog(args.candidate_db)
            fk_lines = select_toc_lines(toc, expected, actual, include_foreign_keys=True)
            runner.restore_list(fk_lines)
            state["phases"].append({"name": "restore_missing_fk", "objects": len(fk_lines)})
        else:
            state["phases"].append({"name": "restore_missing_fk", "objects": len(selected)})

        final = catalog_diff(expected, runner.catalog(args.candidate_db), allow_invalid_parent_pk=False)
        if final["missing"] or final["mismatched"] or final["extra"]:
            raise ResumeError("candidate catalog is incomplete after FK replay")
        state["status"] = "COMPLETE"
        state["ready_for_fk"] = True
        state["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        write_json(checkpoint_path, state)
        return state
    except BaseException as exc:
        state["status"] = "FAILED"
        state["error"] = str(exc)
        state["failed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        write_json(checkpoint_path, state)
        raise


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--work-dir", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--archive-dir", type=Path, required=True)
    p.add_argument("--manifest", type=Path)
    p.add_argument("--candidate-db", required=True)
    p.add_argument("--reference-db", required=True)
    p.add_argument("--source-db", required=True)
    p.add_argument("--service-db", default=SERVICE_DB)
    p.add_argument("--postgres-container", required=True)
    p.add_argument("--client-container", required=True,
                   help="container with pg_restore and the read-only archive mount")
    p.add_argument("--user", default="postgres")
    p.add_argument("--archive-client-path", default="/work/archive")
    p.add_argument("--reference-receipt", type=Path)
    p.add_argument("--through", choices=("prepare", "all"), default="prepare")
    p.add_argument("--benchmark-leaf")
    p.add_argument("--benchmark-timeout-seconds", type=int, default=60)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    try:
        result = run(parser().parse_args(argv))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ResumeError, TransferError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
