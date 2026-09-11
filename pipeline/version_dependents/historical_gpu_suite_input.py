"""Read-only loader for the bounded CPU/GPU resolver comparison suite.

The loader turns one pinned production preparation and its weighted production
run into an in-memory, package-oriented input.  It deliberately validates the
stored oracle before returning it; it never calls the production verifier (that
verifier creates a temporary database and recomputes the whole sample).
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import duckdb

from pipeline.requirements_resolution.input import file_sha256
from pipeline.requirements_resolution.policy import sha256
from .historical import _check_lookup
from .historical_artifact import _path, _read_json
from .historical_production import WEIGHTED_ALGORITHM, _read_partition, contract as production_contract
from .historical_production_input import verify_inputs

MAX_PACKAGES = 32
MAX_LOOKUPS = 100_000
MAX_ORACLE_ROWS = 3_000_000
MAX_SNAPSHOTS = 4096


def _within(root: Path, value: str | Path) -> Path:
    root = _path(root)
    path = _path(root / value)
    if not path.is_relative_to(root):
        raise ValueError("stored path escapes its run")
    return path


def _safe_file(path: Path) -> Path:
    path = _path(path)
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"stored input is missing or unsafe: {path}")
    return path


def _read_table(con: duckdb.DuckDBPyConnection, path: Path, table: str) -> None:
    _safe_file(path)
    con.read_parquet(str(path), hive_partitioning=False).create_view(table, replace=True)


def _interval_paths(root: Path, run_manifest: dict[str, Any], plan_sha: str,
                    expected_names: dict[int, list[str]]) -> tuple[list[Path], list[dict[str, Any]], list[Path]]:
    paths, receipts, protected = [], [], []
    seen = set()
    for item in run_manifest.get("partitions", []):
        pid = int(item["partition_id"])
        if pid in seen:
            raise ValueError("duplicate partition in run manifest")
        seen.add(pid)
        names = expected_names.get(pid)
        if names is None or names != item.get("names"):
            raise ValueError("run partition name coverage differs from run manifest")
        receipt = _read_partition(root, plan_sha, pid, names, WEIGHTED_ALGORITHM)
        if receipt is None:
            raise ValueError(f"missing completed partition: {pid}")
        if receipt != item:
            raise ValueError(f"run manifest partition receipt differs from completed partition: {pid}")
        receipts.append(receipt)
        attempt = _within(root, receipt["attempt"])
        complete = _safe_file(root / "partitions" / f"{pid:03d}" / "complete.json")
        protected.append(complete)
        receipt_path = _safe_file(attempt / "receipt.json")
        protected.append(receipt_path)
        records = _read_json(receipt_path).get("files", [])
        for record in records:
            protected.append(_safe_file(attempt / record["name"]))
        paths.append(_safe_file(attempt / "lookup_intervals.parquet"))
    if set(expected_names) != {int(x["partition_id"]) for x in run_manifest["partitions"]}:
        raise ValueError("partition coverage is incomplete")
    return paths, receipts, protected


def load_suite(*, prepared_dir: Path, oracle_run_dir: Path,
               oracle_manifest_sha256: str) -> dict[str, Any]:
    """Load and validate a bounded stored lookup oracle for a GPU experiment."""
    prepared_dir, root = _path(prepared_dir), _path(oracle_run_dir)
    if prepared_dir.is_relative_to(root) or root.is_relative_to(prepared_dir):
        raise ValueError("prepared input and oracle run must be separate")
    _safe_file(root / "run_plan.json")
    _safe_file(root / "run_manifest.json")
    if file_sha256(root / "run_manifest.json") != oracle_manifest_sha256:
        raise ValueError("oracle run manifest SHA mismatch")
    plan = _read_json(root / "run_plan.json")
    run_manifest = _read_json(root / "run_manifest.json")
    if (plan.get("format") != "historical-production-run-v2"
            or plan.get("algorithm") != WEIGHTED_ALGORITHM
            or plan.get("scope") != "SAMPLE"
            or plan.get("full_selected_scope") is not False
            or plan.get("upstream_resolution_status") != "PARTIAL"
            or plan.get("ready_for_load") is not False
            or plan.get("generation_contract") != production_contract(WEIGHTED_ALGORITHM)
            or _path(plan.get("prepared_dir", "")) != prepared_dir):
        raise ValueError("GPU suite requires the stored weighted production plan")
    if run_manifest.get("run_status") != "COMPLETE" or run_manifest.get("ready_for_load") is not False:
        raise ValueError("oracle run is not a complete non-loadable run")
    if run_manifest.get("plan_sha256") != sha256(plan):
        raise ValueError("run manifest does not pin run plan")
    manifest_sha = plan.get("input_manifest_sha256")
    if not isinstance(manifest_sha, str):
        raise ValueError("run plan has no input manifest SHA")
    prepared = verify_inputs(prepared_dir, manifest_sha)
    calendar = prepared["calendar"]
    if not 1 <= len(calendar) <= MAX_SNAPSHOTS:
        raise ValueError("GPU suite calendar bound exceeded")
    target_names = sorted(prepared["selection"]["chosen_names"] or [])
    if len(target_names) > MAX_PACKAGES:
        raise ValueError("GPU suite is limited to 32 packages")

    expected_names: dict[int, list[str]] = defaultdict(list)
    with duckdb.connect(config={"threads": 2, "memory_limit": "1GB"}) as con:
        for table in ("target_names", "target_population", "lookups", "declarations"):
            _read_table(con, prepared_dir / f"{table}.parquet", table)
        actual_names = [str(x[0]) for x in con.execute("SELECT name FROM target_names ORDER BY name").fetchall()]
        if actual_names != target_names:
            raise ValueError("target-name selection coverage differs from input manifest")
        for pid, name in con.execute("SELECT partition_id,name FROM target_names ORDER BY partition_id,name").fetchall():
            expected_names[int(pid)].append(str(name))
        lookup_count, declaration_count = con.execute("SELECT count(*),coalesce(sum(declaration_count),0) FROM lookups").fetchone()
        if lookup_count > MAX_LOOKUPS:
            raise ValueError("GPU suite lookup bound exceeded")
        plan_names = {int(pid): sorted(names) for pid, names in plan.get("partitions", {}).items()}
        if plan_names != {pid: sorted(names) for pid, names in expected_names.items()}:
            raise ValueError("run plan partition coverage differs from prepared target names")
        interval_paths, receipts, partition_protected = _interval_paths(root, run_manifest, sha256(plan), expected_names)
        if not interval_paths:
            raise ValueError("oracle has no lookup interval partitions")
        parquet_list = "[" + ",".join("'" + str(p).replace("'", "''") + "'" for p in interval_paths) + "]"
        con.execute("CREATE VIEW oracle_intervals AS SELECT * FROM read_parquet(" + parquet_list + ", hive_partitioning=false)")
        oracle_rows = int(con.execute("SELECT count(*) FROM oracle_intervals").fetchone()[0])
        if oracle_rows > MAX_ORACLE_ROWS:
            raise ValueError("GPU suite oracle row bound exceeded")
        n = len(calendar)
        if con.execute("SELECT count(*) FROM lookups").fetchone()[0] != con.execute("SELECT count(DISTINCT lookup_id) FROM oracle_intervals").fetchone()[0]:
            raise ValueError("oracle lookup coverage differs from prepared lookups")
        if con.execute("SELECT count(*) FROM (SELECT lookup_id FROM lookups GROUP BY lookup_id HAVING count(*)<>1)").fetchone()[0]:
            raise ValueError("duplicate lookup_id in prepared lookups")
        if con.execute("SELECT count(*) FROM (SELECT package_id,version FROM target_population GROUP BY package_id,version HAVING count(*)<>1)").fetchone()[0]:
            raise ValueError("duplicate candidate package-version")
        workload_bad = con.execute("""SELECT count(*) FROM target_names t
          LEFT JOIN (SELECT name,count(*) n FROM target_population GROUP BY name) p USING(name)
          LEFT JOIN (SELECT declared_name,count(*) q,coalesce(sum(declaration_count),0) d FROM lookups GROUP BY declared_name) l
            ON l.declared_name=t.name
          WHERE coalesce(p.n,0)<>t.candidate_count OR coalesce(l.q,0)<>t.expected_lookups
             OR coalesce(l.d,0)<>t.expected_declarations
             OR EXISTS (SELECT 1 FROM target_population x WHERE x.name=t.name AND (x.package_id IS DISTINCT FROM t.package_id))""").fetchone()[0]
        if workload_bad:
            raise ValueError("prepared package identity or workload totals differ")
        # Every interval is checked for date coverage, target identity, birth, and status.
        bad = con.execute("""SELECT count(*) FROM oracle_intervals o
          LEFT JOIN lookups l USING(lookup_id)
          LEFT JOIN target_population p ON p.package_id=o.target_package_id AND p.version=o.target_version
          LEFT JOIN target_names t ON t.name=l.declared_name
          WHERE l.lookup_id IS NULL OR o.start_index<0 OR o.end_index<=o.start_index OR o.end_index>?
             OR (o.status='RESOLVED' AND (o.target_package_id IS NULL OR o.target_version IS NULL OR p.package_id IS NULL OR p.birth_index>o.start_index OR p.name<>l.declared_name OR t.package_id IS DISTINCT FROM o.target_package_id))
             OR (o.status<>'RESOLVED' AND (o.target_package_id IS NOT NULL OR o.target_version IS NOT NULL))""", [n]).fetchone()[0]
        if bad:
            raise ValueError("oracle contains invalid interval identity or status")
        # Use the same complete-calendar checker as the production worker.
        grouped = defaultdict(list)
        for lookup_id, start, end, status, _normalized, _pid, version in con.execute(
                "SELECT lookup_id,start_index,end_index,status,normalized_range,target_package_id,target_version "
                "FROM oracle_intervals ORDER BY lookup_id,start_index").fetchall():
            grouped[int(lookup_id)].append({"start_index": int(start), "end_index": int(end),
                                            "status": status, "target_version": version})
        for rows in grouped.values():
            _check_lookup(rows, n)
        target_rows = con.execute("SELECT name,package_id,known_package,candidate_count,expected_lookups,expected_declarations FROM target_names ORDER BY name").fetchall()
        lookup_rows = con.execute("SELECT lookup_id,declared_name,requirement FROM lookups ORDER BY declared_name,lookup_id").fetchall()
        pop_rows = con.execute("SELECT name,package_id,version,birth_index FROM target_population ORDER BY name,birth_index,version").fetchall()
        oracle_rows_data = con.execute("SELECT lookup_id,start_index,end_index,status,normalized_range,target_package_id,target_version FROM oracle_intervals ORDER BY lookup_id,start_index").fetchall()

    by_name = {name: {"name": name, "package_id": None if pid is None else int(pid), "known_package": bool(known),
                      "candidates": [], "lookups": [], "oracle": {}, "expected_declarations": int(decl)}
               for name, pid, known, _c, _l, decl in target_rows}
    for name, pid, version, birth in pop_rows:
        if by_name[name]["package_id"] != (None if pid is None else int(pid)):
            raise ValueError("candidate package identity changed while loading")
        by_name[name]["candidates"].append({"version": version, "birth_index": int(birth)})
    lookup_name = {}
    for lookup_id, name, requirement in lookup_rows:
        item = {"lookup_id": int(lookup_id), "requirement": requirement}
        by_name[name]["lookups"].append((int(lookup_id), requirement))
        lookup_name[int(lookup_id)] = name
    for lookup_id, start, end, status, normalized, pid, version in oracle_rows_data:
        by_name[lookup_name[int(lookup_id)]]["oracle"].setdefault(int(lookup_id), []).append({
            "start_index": int(start), "end_index": int(end), "status": status,
            "normalized_range": normalized, "target_package_id": None if pid is None else int(pid),
            "target_version": version})
    for package in by_name.values():
        package["lookups"].sort(key=lambda x: x[0])
        package["oracle"] = dict(sorted(package["oracle"].items()))
    protected = {}
    for path in [root / "run_plan.json", root / "run_manifest.json", prepared_dir / "input_manifest.json", prepared_dir / "input_plan.json",
                 *[prepared_dir / f"{table}.parquet" for table in ("target_names", "target_population", "lookups", "declarations")]]:
        protected[str(path)] = file_sha256(_safe_file(path))
    protected.update({str(p): file_sha256(p) for p in partition_protected})
    return {"packages": [by_name[name] for name in sorted(by_name)], "calendar": calendar,
            "provenance": {"protected_files_sha256": protected, "stored_runtime": plan["runtime"],
                           "input_manifest_sha256": manifest_sha, "oracle_manifest_sha256": oracle_manifest_sha256,
                           "source": "stored production lookup intervals", "contract": WEIGHTED_ALGORITHM},
            "input_rows": {"target_names": len(target_rows), "target_population": len(pop_rows),
                           "lookups": len(lookup_rows), "declarations": int(declaration_count),
                           "oracle_intervals": len(oracle_rows_data)}}


def reverify_protected_files(suite: dict[str, Any]) -> None:
    for path, expected in suite["provenance"]["protected_files_sha256"].items():
        if file_sha256(_safe_file(Path(path))) != expected:
            raise ValueError("protected suite input changed: " + path)
