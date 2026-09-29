"""Bounded, sequential comparison of legacy and weighted aggregation kernels.

Uses saved resolver intervals from a pinned SAMPLE run. It measures aggregation
and global quality, not input preparation, resolution, H4 writing, or DB loading.
"""
from __future__ import annotations
from pipeline.preprocessing.common.paths import REPO_ROOT

import argparse
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time

from pipeline.preprocessing.requirements_resolution.input import file_sha256
from pipeline.preprocessing.requirements_resolution.policy import sha256
from pipeline.preprocessing.version_dependents.historical_cache import _record, generation_contract
from pipeline.preprocessing.version_dependents.historical_production import DEFAULT_ALGORITHM, WEIGHTED_ALGORITHM, _part_files, contract, current_memory
from pipeline.preprocessing.version_dependents.historical_production_input import connection, open_inputs, verify_inputs
from pipeline.preprocessing.version_dependents.historical_production_sql import aggregate_partition, finalize_quality


def _json(path):
    return json.loads(Path(path).read_bytes())


def _inputs(source_run):
    root = Path(source_run).resolve()
    plan = _json(root / "run_plan.json")
    if plan.get("scope") != "SAMPLE" or plan.get("format") != "historical-production-run-v1":
        raise ValueError("benchmark requires a saved legacy SAMPLE run")
    old = plan["generation_contract"]
    if (old["h4_generation"] != generation_contract()
            or old["sql_sha256"] != file_sha256((REPO_ROOT / 'pipeline/preprocessing/version_dependents/historical_production_sql.py'))):
        raise ValueError("baseline aggregation or upstream generation changed")
    manifest = verify_inputs(plan["prepared_dir"], plan["input_manifest_sha256"])
    limits = {"target_names": 32, "declarations": 5_000_000,
              "lookups": 2_000, "target_population": 100_000}
    if any(manifest["rows"][name] > limit for name, limit in limits.items()):
        raise ValueError("benchmark sample exceeds bounded comparison scope")
    intervals = []
    for part, names in plan["partitions"].items():
        parent = root / "partitions" / f"{int(part):03d}"
        marker = _json(parent / "complete.json")
        attempt = (parent / marker["attempt"]).resolve()
        if not attempt.is_relative_to(parent):
            raise ValueError("baseline attempt escaped partition")
        if file_sha256(attempt / "receipt.json") != marker["receipt_sha256"]:
            raise ValueError("baseline receipt changed")
        receipt = _json(attempt / "receipt.json")
        if receipt["plan_sha256"] != sha256(plan) or receipt["names"] != names:
            raise ValueError("baseline partition differs from plan")
        path = attempt / "lookup_intervals.parquet"
        expected = next(r for r in receipt["files"] if r["name"] == path.name)
        if _record(path) != expected:
            raise ValueError("baseline lookup intervals changed")
        intervals.append((int(part), path))
    return plan, manifest, intervals


def _kernel(source_run, output, algorithm):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    validation_started = time.perf_counter()
    plan, manifest, interval_files = _inputs(source_run)
    validation_seconds = time.perf_counter() - validation_started
    weighted = algorithm == WEIGHTED_ALGORITHM
    n = len(manifest["calendar"])
    saved, measurements = [], []
    settings = {"threads": 4, "memory_limit": "4GB", "max_temp_size": "40GB"}
    generation = contract(algorithm)
    with connection(output / "working.duckdb", **settings) as con:
        open_inputs(con, plan["prepared_dir"], manifest)
        if weighted:
            from pipeline.preprocessing.version_dependents.historical_production_events import aggregate_partition_weighted, validate_weighted_inputs
            from pipeline.preprocessing.version_dependents.historical_production_quality import finalize_quality_weighted
            t = time.perf_counter()
            validate_weighted_inputs(con, n)
            global_seconds = time.perf_counter() - t
        else:
            global_seconds = 0.0
        for pid, path in interval_files:
            con.execute("CREATE OR REPLACE TEMP TABLE lookup_intervals AS SELECT * FROM read_parquet(?,hive_partitioning=false)", [str(path)])
            t = time.perf_counter()
            details = (aggregate_partition_weighted(con, n, pid, global_validated=True) if weighted
                       else aggregate_partition(con, n, pid))
            elapsed = time.perf_counter() - t
            samples = {}
            if weighted:
                source_table = "p_source_summary"
            else:
                source_table = "p_source_deltas"
            samples["source_intermediate_rows"] = con.execute("SELECT count(*) FROM " + source_table).fetchone()[0]
            samples["count_intervals"] = con.execute("SELECT count(*) FROM p_counts").fetchone()[0]
            measurements.append({"partition_id": pid, "aggregate_seconds": elapsed,
                                 "metrics": details, **samples})
            # Keep compact outputs for global merging, as the runner does.
            files = {}
            for suffix, table in _part_files(algorithm).items():
                if suffix == "lookup_intervals":
                    continue
                dest = output / f"p{pid}-{suffix}.parquet"
                con.execute(f"COPY {table} TO ? (FORMAT PARQUET,COMPRESSION ZSTD)", [str(dest)])
                files[suffix] = str(dest)
            saved.append(files)
        for suffix, table in (("counts", "all_counts"), ("status_deltas", "all_status_deltas"),
                              *(((("source_summary", "all_source_summary"),) if weighted else
                                 (("sources", "all_sources"), ("source_deltas", "all_source_deltas"))))):
            con.read_parquet([p[suffix] for p in saved], hive_partitioning=False).create_view(table)
        t = time.perf_counter()
        summary = finalize_quality_weighted(con, n) if weighted else finalize_quality(con, n)
        finalize_seconds = time.perf_counter() - t
        # This expansion contains only final positive target/version/date counts.
        for suffix, query in {
            "counts": f"SELECT package_id,version,snapshot_index,dependents_count FROM history_count_intervals JOIN range({int(n)}) s(snapshot_index) ON start_index<=snapshot_index AND snapshot_index<end_index ORDER BY 1,2,3",
            "quality": "SELECT * FROM history_quality ORDER BY snapshot_index",
            "targets": "SELECT * FROM history_target_population ORDER BY package_id,version",
        }.items():
            con.execute(f"COPY ({query}) TO ? (FORMAT PARQUET,COMPRESSION ZSTD)", [str(output / (suffix + ".parquet"))])
    if generation != contract(algorithm):
        raise ValueError("generation changed during benchmark")
    report = {"algorithm": algorithm, "scope": "SAMPLE_SAVED_LOOKUP_AGGREGATION_AND_QUALITY",
              "input_manifest_sha256": plan["input_manifest_sha256"], "generation": generation,
              "rows": manifest["rows"], "snapshot_count": n, "partitions": measurements,
              "input_validation_seconds": validation_seconds, "global_validation_seconds": global_seconds,
              "aggregate_seconds": sum(m["aggregate_seconds"] for m in measurements),
              "finalize_seconds": finalize_seconds, "summary": summary,
              "memory": current_memory(), "settings": settings,
              "output_bytes": sum(p.stat().st_size for p in output.glob("*.parquet")),
              "db_load_included": False, "input_preparation_included": False,
              "resolver_included": False, "daily_writer_included": False}
    report["kernel_seconds"] = report["aggregate_seconds"] + finalize_seconds + global_seconds
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def benchmark(source_run, output, repeats=3):
    if repeats not in (1, 3):
        raise ValueError("repeats must be 1 or 3")
    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    reports = []
    for repeat in range(repeats):
        order = (DEFAULT_ALGORITHM, WEIGHTED_ALGORITHM) if repeat % 2 == 0 else (WEIGHTED_ALGORITHM, DEFAULT_ALGORITHM)
        for algorithm in order:
            child = root / f"r{repeat}-{algorithm}"
            command = [sys.executable, "-B", "-m", __name__.replace("__main__", "pipeline.preprocessing.experiments.dependents.historical_weighted_benchmark"),
                       "--source-run", str(Path(source_run).resolve()), "--output", str(child), "--kernel", "--algorithm", algorithm]
            with (root / f"{child.name}.log").open("wb") as log:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
            reports.append({"directory": str(child), **_json(child / "report.json")})
            print(json.dumps({"finished": child.name, "seconds": reports[-1]["kernel_seconds"]}), flush=True)
    import duckdb
    baseline = reports[0]
    with duckdb.connect() as con:
        for report in reports[1:]:
            for name in ("counts", "quality", "targets"):
                left = str(Path(baseline["directory"]) / (name + ".parquet"))
                right = str(Path(report["directory"]) / (name + ".parquet"))
                difference = con.execute("""SELECT count(*) FROM (
                    (SELECT * FROM read_parquet(?) EXCEPT ALL SELECT * FROM read_parquet(?))
                    UNION ALL (SELECT * FROM read_parquet(?) EXCEPT ALL SELECT * FROM read_parquet(?)))""",
                    [left, right, right, left]).fetchone()[0]
                if difference:
                    raise ValueError(f"{name} mismatch: {report['directory']}: {difference}")
    medians = {algorithm: statistics.median(r["kernel_seconds"] for r in reports if r["algorithm"] == algorithm)
               for algorithm in (DEFAULT_ALGORITHM, WEIGHTED_ALGORITHM)}
    result = {"scope": "SAMPLE_SAVED_LOOKUP_AGGREGATION_AND_QUALITY", "repeats": repeats,
              "source_run": str(Path(source_run).resolve()), "reports": reports,
              "median_seconds": medians, "mismatches": 0,
              "speedup": medians[DEFAULT_ALGORITHM] / medians[WEIGHTED_ALGORITHM],
              "reduction_percent": 100 * (1 - medians[WEIGHTED_ALGORITHM] / medians[DEFAULT_ALGORITHM]),
              "full_selection_executed": False, "db_load_included": False,
              "memory_scope": "fresh process peak per kernel including its input validation"}
    (root / "comparison.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--kernel", action="store_true")
    parser.add_argument("--algorithm", choices=(DEFAULT_ALGORITHM, WEIGHTED_ALGORITHM))
    args = parser.parse_args()
    result = (_kernel(args.source_run, args.output, args.algorithm) if args.kernel
              else benchmark(args.source_run, args.output, args.repeats))
    print(json.dumps(result, indent=2))
