"""Bounded old/new daily writer benchmark on one pinned cache."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

import duckdb

from pipeline.requirements_resolution.input import file_sha256
from pipeline.requirements_resolution.policy import canonical_bytes


def _load_baseline(path: Path):
    name = "pipeline.version_dependents._baseline_daily_writer"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("unable to load baseline writer")
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _bytes(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def _paths(run: Path):
    result = {}
    for marker in sorted(run.glob("snapshot=*/complete.json")):
        body = json.loads(marker.read_bytes()); day = marker.parent.name
        result[day] = marker.parent / "attempts" / body["attempt_id"]
    return result


def _compare(old: Path, new: Path) -> dict:
    old_paths, new_paths = _paths(old), _paths(new)
    if list(old_paths) != list(new_paths):
        raise ValueError("completed date sets differ")
    checks = []
    excludes = {"quality.parquet": ["run_plan_sha256"],
                "lineage.parquet": ["run_plan_sha256", "generation_contract_sha256"]}
    with duckdb.connect() as con:
        for day in old_paths:
            for filename in ("counts.parquet", "quality.parquet", "lineage.parquet"):
                left, right = old_paths[day] / filename, new_paths[day] / filename
                columns = [str(row[0]) for row in con.execute("DESCRIBE SELECT * FROM read_parquet(?,hive_partitioning=false)", [str(left)]).fetchall()]
                selected = [c for c in columns if c not in excludes.get(filename, [])]
                projection = ",".join('"' + c.replace('"', '""') + '"' for c in selected)
                mismatch = con.execute(
                    f"SELECT count(*) FROM ((SELECT {projection} FROM read_parquet(?,hive_partitioning=false) EXCEPT ALL SELECT {projection} FROM read_parquet(?,hive_partitioning=false)) UNION ALL "
                    f"(SELECT {projection} FROM read_parquet(?,hive_partitioning=false) EXCEPT ALL SELECT {projection} FROM read_parquet(?,hive_partitioning=false)))",
                    [str(left), str(right), str(right), str(left)]).fetchone()[0]
                checks.append({"day": day, "file": filename, "match": not mismatch})
    if not all(row["match"] for row in checks):
        raise ValueError("published Parquet values differ")
    return {"checks": len(checks), "all_match": True}


def _child(args):
    cache = Path(args.cache_dir).resolve(); output = Path(args.output).resolve()
    if output.exists(): raise ValueError("output already exists")
    from .historical_production import contract, current_memory, WEIGHTED_ALGORITHM
    generation = contract(WEIGHTED_ALGORITHM)
    if file_sha256(cache / "cache_manifest.json") != args.cache_sha:
        raise ValueError("cache SHA differs")
    pinned = json.loads((cache / "cache_manifest.json").read_bytes())
    limits = {"target_population.parquet": 100000, "count_intervals.parquet": 1000000}
    if len(pinned["calendar"]) > 4096 or any(r["rows"] > limits.get(r["name"],4096) for r in pinned["files"]):
        raise ValueError("cache exceeds bounded benchmark scope")
    if args.child_mode == "baseline":
        baseline = Path(args.baseline).resolve(); meta = json.loads((baseline.parents[3] / "baseline.json").read_bytes())
        expected = next(x["sha256"] for x in meta["files"] if x["path"].endswith("historical_production_writer.py"))
        if file_sha256(baseline) != expected: raise ValueError("baseline writer SHA mismatch")
        h4 = meta["h4_generation"]
        from . import historical_cache as hc, historical_artifact as ha
        if hc.generation_contract() != h4: raise ValueError("H4 generation contract changed")
        writer = _load_baseline(baseline)
        from . import historical_cache
        verify_fn = historical_cache.verify_cache
    else:
        from . import historical_production_writer as writer
        from . import historical_production_cache as pc
        verify_fn = pc.verify_cache
    started = time.monotonic(); manifest = verify_fn(cache, args.cache_sha)
    verify_seconds = time.monotonic() - started
    started = time.monotonic(); result = writer.build_history(cache_dir=cache, cache_sha256=args.cache_sha, output=output)
    build_seconds = time.monotonic() - started
    started = time.monotonic(); verified = writer.verify_history(run_dir=output, cache_dir=cache,
        cache_sha256=args.cache_sha, run_manifest_sha256=result["run_manifest_sha256"])
    independent_seconds = time.monotonic() - started
    report = {"mode": args.child_mode, "cache_sha256": args.cache_sha, "manifest_format": manifest.get("format"),
              "completed_dates": result["completed_dates"], "verify_seconds": verify_seconds,
              "build_seconds": build_seconds, "independent_verify_seconds": independent_seconds,
              "output_bytes": _bytes(output), "run_result": result, "verify_result": verified,
              "production_cache_sha256": manifest.get("production_cache_sha256"),
              "run_plan_sha256": result["run_plan_sha256"], "generation": generation,
              "memory": current_memory(), "full_selection_executed": False}
    if generation != contract(WEIGHTED_ALGORITHM):
        raise ValueError("generation changed during benchmark")
    (output / "benchmark_child.json").write_bytes(canonical_bytes(report))
    return report


def benchmark(*, cache_dir: Path, cache_sha: str, output: Path, baseline: Path, repeats: int = 1, resume: bool = False) -> dict:
    if repeats not in (1, 3): raise ValueError("repeats must be 1 or 3")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=resume)
    reports = []
    for repeat in range(repeats):
        order = ("baseline", "current") if repeat % 2 == 0 else ("current", "baseline")
        pair = {}
        for mode in order:
            out = output / f"repeat={repeat}" / mode
            if resume and (out / "benchmark_child.json").exists():
                saved = json.loads((out / "benchmark_child.json").read_bytes())
                from .historical_production import contract, WEIGHTED_ALGORITHM
                if (saved["mode"] != mode or saved["cache_sha256"] != cache_sha
                        or saved["generation"] != contract(WEIGHTED_ALGORITHM)
                        or file_sha256(out / "run_manifest.json") != saved["run_result"]["run_manifest_sha256"]):
                    raise ValueError("benchmark checkpoint differs from current input or code")
                pair[mode] = saved
                continue
            command = [sys.executable, "-B", "-m", "pipeline.version_dependents.historical_daily_benchmark",
                       "--child-mode", mode, "--cache-dir", str(cache_dir), "--cache-sha", cache_sha,
                       "--output", str(out), "--baseline", str(baseline)]
            out.parent.mkdir(parents=True, exist_ok=True)
            with (out.parent / (mode + ".log")).open("wb") as log:
                completed = subprocess.run(command, cwd=Path.cwd(), stdout=log, stderr=subprocess.STDOUT)
            if completed.returncode:
                raise RuntimeError(f"{mode} child failed; see {out.parent / (mode + '.log')}")
            pair[mode] = json.loads((out / "benchmark_child.json").read_bytes())
        pair["comparison"] = _compare(Path(pair["baseline"]["run_result"]["run_dir"]),
                                       Path(pair["current"]["run_result"]["run_dir"]))
        reports.append(pair)
        print(json.dumps({"finished_repeat": repeat, "baseline_seconds": pair["baseline"]["build_seconds"], "current_seconds": pair["current"]["build_seconds"]}), flush=True)
    report = {"scope": "O4_DAILY_WRITER_BENCHMARK", "cache_dir": str(cache_dir),
              "cache_sha256": cache_sha, "repeats": repeats, "runs": reports,
              "baseline_sha256": file_sha256(baseline), "h4_baseline": True}
    report["median_seconds"] = {mode: {key: statistics.median(pair[mode][key] for pair in reports)
        for key in ("verify_seconds","build_seconds","independent_verify_seconds")} for mode in ("baseline","current")}
    (output / "benchmark_report.json").write_bytes(canonical_bytes(report))
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--cache-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--child-mode", choices=("baseline", "current"))
    args = parser.parse_args()
    if args.child_mode:
        result = _child(args)
    else:
        options = vars(args)
        options.pop("child_mode")
        result = benchmark(**options)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
