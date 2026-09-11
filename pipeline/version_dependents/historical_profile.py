"""H5-A: profile pinned real inputs without computing historical counts."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time

import duckdb

from pipeline.requirements_resolution.input import file_sha256, reverify_inputs
from pipeline.requirements_resolution.policy import canonical_bytes
from .artifact import _reject_reparse_ancestors, _reparse, _validate_sha
from .historical_artifact import _publish_json
from .historical_input import verify_historical_inputs
from .historical_profile_queries import profile_tables, verify_profile_tables


FORMAT = "historical-workload-profile-v1"


def _read(path):
    path = Path(path).absolute()
    _reject_reparse_ancestors(path)
    if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("Missing or oversized profile input manifest")
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError("Manifest must be an object")
    return value


def _contract():
    root = Path(__file__).resolve().parents[2]
    names = ("historical_profile.py", "historical_profile_queries.py", "historical_job.py",
             "historical_input.py", "historical_artifact.py", "historical_cache.py", "artifact.py",
             "historical_semver_worker.cjs")
    paths = [Path(__file__).with_name(name) for name in names]
    paths += [root / "pipeline" / name for name in (
        "requirements_resolution/input.py", "requirements_resolution/policy.py",
        "snapshot/policy.py", "postgresql/input.py")]
    return {str(path.relative_to(root).as_posix()): file_sha256(path) for path in paths}


def _event(output, phase, **extra):
    with (output / "progress.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(canonical_bytes({"at": datetime.now(timezone.utc).isoformat(),
                                      "phase": phase, **extra}).decode())


def _inputs(input_dir, expected_sha):
    _validate_sha(expected_sha, "H1 manifest SHA")
    path = Path(input_dir).absolute() / "input_manifest.json"
    manifest = _read(path)
    if file_sha256(path) != expected_sha:
        raise ValueError("H1 input manifest SHA mismatch")
    if (manifest.get("preparation_status") != "COMPLETE" or manifest.get("count_status") != "NOT_COMPUTED"
            or manifest.get("ready_for_load") is not False or not manifest.get("local_files_verified")):
        raise ValueError("H1 input status mismatch")
    raw_path = Path(manifest["input_manifest"]["path"])
    raw = _read(raw_path)
    if (file_sha256(raw_path) != manifest["input_manifest"]["sha256"]
            or raw != manifest.get("raw_input_manifest_preserved")
            or raw.get("input_sha256") != manifest["input_manifest"]["input_sha256"]):
        raise ValueError("H1 preserved raw input identity mismatch")
    calendar_path = Path(manifest["calendar_manifest"]["path"])
    _read(calendar_path)
    if file_sha256(calendar_path) != manifest["calendar_manifest"]["sha256"]:
        raise ValueError("H1 calendar SHA mismatch")
    if not manifest.get("code_sha256"):
        raise ValueError("Missing H1 generation contract")
    for name, digest in manifest["code_sha256"].items():
        if file_sha256(Path(name)) != digest:
            raise ValueError("H1 generation code differs: " + name)
    return manifest, raw


def _record(con, path):
    if _reparse(path) or not path.is_file():
        raise ValueError("Missing or unsafe profile output")
    rows = con.execute("SELECT count(*) FROM read_parquet(?,hive_partitioning=false)", [str(path)]).fetchone()[0]
    schema = [list(row[:2]) for row in con.execute("DESCRIBE SELECT * FROM read_parquet(?,hive_partitioning=false)", [str(path)]).fetchall()]
    return {"name": path.name, "bytes": path.stat().st_size, "sha256": file_sha256(path), "rows": rows, "schema": schema}


def build_profile(*, input_dir, input_manifest_sha256, output, threads=8,
                  memory_limit="8GB", max_temp_size="100GB"):
    start = time.monotonic()
    input_dir, output = Path(input_dir).absolute(), Path(output).absolute()
    _reject_reparse_ancestors(output)
    if type(threads) is not int or not 1 <= threads <= 8:
        raise ValueError("Use 1..8 threads")
    if any(not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]*(?:MB|GB)", value)
           for value in (memory_limit, max_temp_size)):
        raise ValueError("Explicit memory/temp size in MB or GB is required")
    manifest, raw = _inputs(input_dir, input_manifest_sha256)
    protected = [input_dir, *(Path(name).resolve() for name in raw["sources"].values())]
    if any(output.is_relative_to(path) or path.is_relative_to(output) for path in protected):
        raise ValueError("Profile output overlaps input")
    contract = _contract()
    output.mkdir(parents=True, exist_ok=False)
    plan = {"format": FORMAT, "scope": "H5_INPUT_WORKLOAD_PROFILE", "input_dir": str(input_dir),
            "input_manifest_sha256": input_manifest_sha256, "raw_manifest": manifest["input_manifest"],
            "calendar_manifest": manifest["calendar_manifest"], "policy_sha256": manifest["policy_sha256"],
            "generation_contract": contract, "duckdb_version": duckdb.__version__,
            "threads": threads, "memory_limit": memory_limit, "max_temp_size": max_temp_size,
            "count_status": "NOT_COMPUTED", "ready_for_load": False}
    _publish_json(output / "profile_plan.json", plan)
    _event(output, "VERIFY_H1_AND_RAW_INPUTS")
    verify_historical_inputs(input_dir, input_manifest_sha256)
    reverify_inputs(raw)
    before = {str(Path(r["path"])): (Path(r["path"]).stat().st_size, Path(r["path"]).stat().st_mtime_ns)
              for r in raw["file_records"]}
    with duckdb.connect(str(output / "working.duckdb"), config={"threads": threads, "memory_limit": memory_limit}) as con:
        con.execute("SET TimeZone='UTC'")
        con.execute("SET enable_progress_bar=false")
        con.execute("SET preserve_insertion_order=false")
        con.execute("SET temp_directory=?", [str(output / "scratch")])
        con.execute("SET max_temp_directory_size=?", [max_temp_size])
        for table in ("source_population", "target_population"):
            con.read_parquet(str(input_dir / (table + ".parquet")), hive_partitioning=False).create_view(table)
        for table in ("requirements", "package"):
            con.read_parquet(raw["files"][table], hive_partitioning=False).create_view("input_" + table)
        _event(output, "PROFILE_LOOKUPS_AND_CANDIDATES")
        statistics = profile_tables(con, output=output, snapshot_count=manifest["snapshot_count"],
                                    on_stage=lambda phase: _event(output, phase))
        if statistics["source_declarations"] != manifest["statistics"]["selected_declarations_latest"]:
            raise ValueError("Profile declaration count differs from H1 manifest")
        _event(output, "VERIFY_PROFILE_OUTPUTS")
        verified = verify_profile_tables(con, output, statistics)
        records = [_record(con, path) for path in sorted(output.glob("*.parquet"))]
    _event(output, "REVERIFY_INPUT_IDENTITY")
    reverify_inputs(raw)
    verify_historical_inputs(input_dir, input_manifest_sha256)
    if (any((Path(p).stat().st_size, Path(p).stat().st_mtime_ns) != stat for p, stat in before.items())
            or _inputs(input_dir, input_manifest_sha256) != (manifest, raw) or _contract() != contract):
        raise ValueError("Input or generation contract changed during profiling")
    result_manifest = {**plan, "profile_status": "COMPLETE", "statistics": statistics, "verification": verified,
                       "files": records, "elapsed_seconds": time.monotonic() - start,
                       "profile_plan_sha256": file_sha256(output / "profile_plan.json"),
                       "next_step": "MEASURE_REAL_RESOLUTION_SAMPLES_AND_SET_FULL_RUN_BUDGET"}
    _publish_json(output / "profile_manifest.json", result_manifest)
    result = {"output": str(output), "profile_status": "COMPLETE", "count_status": "NOT_COMPUTED",
              "ready_for_load": False, "manifest_sha256": file_sha256(output / "profile_manifest.json")}
    _publish_json(output / "result.json", result)
    _event(output, "PROFILE_COMPLETE", elapsed_seconds=result_manifest["elapsed_seconds"])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["build"])
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--input-manifest-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--memory-limit", default="8GB")
    parser.add_argument("--max-temp-size", default="100GB")
    args = vars(parser.parse_args())
    args.pop("command")
    if "H5_SUPERVISOR_PID" in os.environ:
        from .historical_job import _start_parent_guard
        _start_parent_guard(int(os.environ["H5_SUPERVISOR_PID"]), args["output"].absolute().parent)
    output_existed = args["output"].exists()
    try:
        print(json.dumps(build_profile(**args), ensure_ascii=True))
    except BaseException as error:
        output = args["output"]
        if not output_existed and output.is_dir() and not (output / "error.json").exists():
            _publish_json(output / "error.json", {"status": "FAILED", "type": type(error).__name__,
                                                "message": str(error)[:2000], "count_status": "NOT_COMPUTED"})
        raise


if __name__ == "__main__":
    main()
