"""Bounded resolver throughput benchmark for one real H5-A target package.

The benchmark is intentionally a measurement tool, not a production runner.
It resolves 59 deterministic H5-A lookups across the full calendar and records
the production worker's framing and process-resource costs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

import duckdb

from pipeline.requirements_resolution.bridge import discover_runtime
from pipeline.requirements_resolution.input import file_sha256
from pipeline.requirements_resolution.policy import canonical_bytes
from .historical_production import MeasuredNode, batches, current_memory

PACKAGE = "@octopusdeploy/type-utils"
LOOKUPS = 59
RUNTIME_KEYS = ("node_version", "semver_version", "package_arg_version", "semver_sha256",
                "package_arg_sha256", "dependency_closure_sha256", "options",
                "equal_precedence_tie")


def _parquet(con, path, columns, where="", params=None):
    return con.execute(f"SELECT {columns} FROM read_parquet(?) {where}",
                       [str(Path(path).resolve()), *(params or [])]).fetchall()


def _latest(intervals, index):
    return next((row for row in intervals if row["start_index"] <= index < row["end_index"]), None)


def _runtime_equal(left, right):
    return all(left.get(key) == right.get(key) for key in RUNTIME_KEYS)


def benchmark(*, h1_dir: Path, profile_dir: Path, output: Path, package_name=PACKAGE,
              runtime=None) -> dict:
    """Run only the bounded 59-lookup benchmark and write an exclusive report."""
    h1_dir, profile_dir, output = Path(h1_dir).resolve(), Path(profile_dir).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError("benchmark output already exists")
    started = time.monotonic()
    with duckdb.connect() as con:
        calendar = _parquet(con, h1_dir / "calendar.parquet", "snapshot_index,snapshot_at,snapshot_timestamp::VARCHAR")
        candidates = _parquet(con, h1_dir / "target_population.parquet", "package_id,name,version,birth_index",
                              "WHERE name=? ORDER BY birth_index,version", [package_name])
        candidates = [(int(pid), str(name), str(version), int(birth)) for pid, name, version, birth in candidates]
        lookups = _parquet(con, profile_dir / "lookup_workload.parquet", "lookup_id,declared_name,requirement,declaration_count,first_source_birth",
                           "WHERE declared_name=? AND requirement IS NOT NULL ORDER BY sha256(requirement) LIMIT 59", [package_name])
        lookups = [(int(i), str(name), req, int(count), int(first)) for i, name, req, count, first in lookups]
    if not candidates:
        raise ValueError("benchmark target package has no H1 candidates")
    if len(lookups) < LOOKUPS:
        raise ValueError(f"benchmark target has fewer than {LOOKUPS} H5-A lookups")
    lookups = sorted(lookups, key=lambda row: hashlib.sha256(row[2].encode("utf-8")).hexdigest())[:LOOKUPS]
    n = len(calendar)
    production_candidates = [{"version": version, "birth_index": birth} for _pid, _name, version, birth in candidates]
    latest_versions = [version for _pid, _name, version, birth in candidates if birth <= n - 1]
    if not latest_versions:
        raise ValueError("benchmark target has no latest candidates")
    runtime = runtime or discover_runtime()
    output.parent.mkdir(parents=True, exist_ok=True)
    node_log = output.with_name(output.name + ".production-node.log")
    legacy_log = output.with_name(output.name + ".legacy-node.log")
    bounds = None
    production_results = {}
    production_metrics = None
    memory_before = current_memory()
    with MeasuredNode(runtime, node_log, worker=Path(__file__).with_name("historical_semver_worker.cjs")) as node:
        metadata = node.request({"op": "metadata"})
        bounds = metadata["bounds"]
        requested = [(lookup_id, requirement) for lookup_id, _name, requirement, _count, _first in lookups]
        for items, message in batches(package_name, production_candidates, requested,
                                      known_package=True, snapshot_count=n, bounds=bounds):
            reply = node.request(message)
            if reply.get("rejected") or reply.get("accepted") != production_candidates:
                raise ValueError("production benchmark candidate validation changed")
            if len(reply.get("lookups", [])) != len(items):
                raise ValueError("production benchmark lookup response length mismatch")
            for (lookup_id, requirement), result in zip(items, reply["lookups"]):
                if result.get("requirement") != requirement:
                    raise ValueError("production benchmark requirement changed")
                production_results[lookup_id] = result
        production_metrics = dict(node.metrics)
    memory_after = current_memory()
    legacy_results = {}
    with MeasuredNode(runtime, legacy_log) as node:
        legacy_meta = node.request({"op": "metadata"})
        node.request({"op": "start", "name": package_name})
        for start in range(0, len(latest_versions), 4096):
            node.request({"op": "candidates", "versions": latest_versions[start:start + 4096]})
        for start in range(0, len(lookups), 256):
            batch = lookups[start:start + 256]
            replies = node.request({"op": "resolve", "requirements": [row[2] for row in batch]})
            # MeasuredNode records exact UTF-8 request/response bytes.
            if len(replies) != len(batch):
                raise ValueError("legacy benchmark lookup response length mismatch")
            for row, result in zip(batch, replies):
                if result.get("requirement") != row[2]:
                    raise ValueError("legacy benchmark requirement changed")
                legacy_results[row[0]] = result
    latest_index = n - 1
    comparisons = []
    for lookup_id, _name, requirement, _count, _first in lookups:
        production = _latest(production_results[lookup_id]["intervals"], latest_index)
        legacy = legacy_results[lookup_id]
        prod_tuple = None if production is None else (production["status"], production["normalized_range"], production["target_version"])
        legacy_tuple = (legacy["status"], legacy["normalized_range"], legacy["target_version"])
        comparisons.append({"lookup_id": lookup_id, "requirement": requirement,
                            "production_latest": prod_tuple, "legacy_latest": legacy_tuple,
                            "match": prod_tuple == legacy_tuple})
    mismatches = [row for row in comparisons if not row["match"]]
    report = {"scope": "BOUNDED_59_LOOKUP_BENCHMARK", "package_name": package_name,
              "method": "PRODUCTION_229_DATE_BATCHES_VS_LEGACY_LATEST",
              "full_selected_execution": False, "snapshot_count": n,
              "candidate_count": len(candidates), "lookup_count": len(lookups),
              "selection": "first 59 sorted by sha256(requirement)",
              "bounds": bounds, "production_runtime": metadata, "legacy_runtime": legacy_meta,
              "runtime_contract_match": _runtime_equal(metadata, legacy_meta),
              "production_metrics": production_metrics, "legacy_metrics": dict(node.metrics),
              "memory_before": memory_before, "memory_after": memory_after,
              "comparisons": comparisons, "mismatch_count": len(mismatches),
              "elapsed_seconds": time.monotonic() - started,
              "inputs": {"h1_dir": str(h1_dir), "profile_dir": str(profile_dir),
                         "h1_calendar_sha256": file_sha256(h1_dir / "calendar.parquet"),
                         "profile_lookup_sha256": file_sha256(profile_dir / "lookup_workload.parquet")}}
    if mismatches or not _runtime_equal(metadata, legacy_meta):
        raise ValueError("benchmark legacy comparison failed: " + json.dumps(
            {"mismatch_count": len(mismatches), "runtime_contract_match": _runtime_equal(metadata, legacy_meta)}, ensure_ascii=False))
    output.mkdir(parents=True, exist_ok=False)
    report_path = output / "benchmark_report.json"
    report_path.write_bytes(canonical_bytes(report))
    report["report_path"] = str(report_path)
    report["report_sha256"] = file_sha256(report_path)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--h1-dir", type=Path, required=True)
    parser.add_argument("--profile-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(benchmark(**vars(args)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
