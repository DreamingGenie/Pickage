"""Production daily writer that reuses verification of freshly written files.

Keep the original H4 implementation byte-stable: its code is pinned by historical
inputs. Existing/resumed files still pass H4's complete value verification.
"""
from __future__ import annotations

from pathlib import Path
import uuid

from pipeline.preprocessing.requirements_resolution.input import file_sha256
from pipeline.preprocessing.requirements_resolution.policy import sha256
from pipeline.preprocessing.version_dependents import historical_artifact as base
from pipeline.preprocessing.version_dependents import historical_production_daily as daily
from pipeline.preprocessing.version_dependents.historical_production_cache import verify_cache, verify_cache_bytes


def _plan(cache_dir, cache_sha, cache):
    return {**base._plan(cache_dir, cache_sha, cache),
            "production_writer_sha256": file_sha256(Path(__file__)),
            "production_cache_sha256": file_sha256(Path(__file__).with_name("historical_production_cache.py")),
            "production_daily_sha256": file_sha256(Path(__file__).with_name("historical_production_daily.py"))}


def _check_generation(plan):
    if (base._contract() != plan["generation_contract"]
            or file_sha256(Path(__file__)) != plan["production_writer_sha256"]
            or file_sha256(Path(__file__).with_name("historical_production_cache.py")) != plan["production_cache_sha256"]
            or file_sha256(Path(__file__).with_name("historical_production_daily.py")) != plan["production_daily_sha256"]):
        raise ValueError("Production daily writer generation changed")


def _write_snapshot(con, *, run_dir, cache, plan, index):
    """Verify values once, recheck bytes, then publish the completion marker."""
    day_dir = base._path(run_dir / ("snapshot=" + plan["calendar"][index]["snapshot_at"]))
    attempt = base._path(day_dir / "attempts" / uuid.uuid4().hex)
    attempt.mkdir(parents=True, exist_ok=False)
    summary = daily._expected_tables(con, cache, plan, index)
    info = {}
    for filename, table in zip(base.FILES, ("expected_counts", "expected_quality", "expected_lineage")):
        target = attempt / filename
        order = " ORDER BY package_id, version" if table == "expected_counts" else ""
        con.execute(f"COPY (SELECT * FROM {table}{order}) TO {base._sql_literal(target)} (FORMAT PARQUET, COMPRESSION ZSTD)")
        info[filename] = base._file_info(con, target)
    manifest = {"format": base.FORMAT, "run_plan_sha256": sha256(plan), "cache_manifest_sha256": plan["cache_manifest_sha256"],
                "snapshot_index": index, **plan["calendar"][index], "attempt_id": attempt.name,
                "files": info, "quality_summary": summary, "ready_for_load": False}
    path = attempt / "snapshot_manifest.json"
    base._publish_json(path, manifest)
    manifest_sha = file_sha256(path)
    verified = daily._verify_snapshot(con, attempt, cache, plan, index, manifest_sha)
    # Retain byte integrity up to publication without repeating SQL scans,
    # schema inspection, expected-table creation, or bidirectional EXCEPT ALL.
    for filename, record in verified["files"].items():
        target = base._path(attempt / filename)
        if target.stat().st_size != record["bytes"] or file_sha256(target) != record["sha256"]:
            raise ValueError("Snapshot file changed after verification: " + filename)
    if file_sha256(base._path(path)) != manifest_sha:
        raise ValueError("Fresh snapshot manifest changed after verification")
    _check_generation(plan)
    anchor = {"snapshot_at": plan["calendar"][index]["snapshot_at"], "attempt_id": attempt.name,
              "manifest_sha256": manifest_sha, "run_plan_sha256": sha256(plan)}
    marker = day_dir / "complete.json"
    base._publish_json(marker, anchor)
    return {**anchor, "complete_sha256": file_sha256(marker),
            "quality_summary": verified["quality_summary"]}


def build_history(*, cache_dir, cache_sha256, output, resume=False, max_snapshots=None):
    """Verify fresh files once; verify every reused date before new work begins."""
    if max_snapshots is not None and (type(max_snapshots) is not int or max_snapshots <= 0):
        raise ValueError("max_snapshots must be positive")
    cache_dir, run_dir = base._path(cache_dir), base._path(output)
    if cache_dir.is_relative_to(run_dir) or run_dir.is_relative_to(cache_dir):
        raise ValueError("Cache and run directories must be separate")
    base._validate_sha(cache_sha256, "cache manifest SHA")
    cache = verify_cache(cache_dir, cache_sha256)
    plan = _plan(cache_dir, cache_sha256, cache)
    if resume:
        if not run_dir.is_dir():
            raise ValueError("Resume requires an existing run")
    else:
        run_dir.mkdir(parents=True, exist_ok=False)
    with base._run_lock(run_dir):
        plan_path = run_dir / "run_plan.json"
        if plan_path.exists():
            if base._read_json(plan_path) != plan:
                raise ValueError("Run input, calendar, or generation contract differs; use a new run")
        else:
            if any(p.name != ".writer.lock" and not p.name.startswith("run_plan.json.tmp-") for p in run_dir.iterdir()):
                raise ValueError("Existing output has no valid generation plan")
            base._publish_json(plan_path, plan)
        if file_sha256(plan_path) != sha256(plan):
            raise ValueError("Run plan byte identity mismatch")
        completed, written, reused = [], [], []
        with base._connection() as con:
            daily._load_views(con, cache_dir, cache)
            pending = []
            for index, row in enumerate(plan["calendar"]):
                existing = daily._read_completed(con, run_dir, cache, plan, index)
                if existing is not None:
                    completed.append(existing)
                    reused.append(row["snapshot_at"])
                else:
                    pending.append(index)
            if (run_dir / "run_manifest.json").exists():
                if pending or base._read_json(run_dir / "run_manifest.json") != base._completed_manifest(plan, completed):
                    raise ValueError("Published run manifest differs from completed snapshots")
            for index in pending[:max_snapshots]:
                _check_generation(plan)
                completed.append(_write_snapshot(con, run_dir=run_dir, cache=cache, plan=plan, index=index))
                written.append(plan["calendar"][index]["snapshot_at"])
        completed.sort(key=lambda row: row["snapshot_at"])
        verify_cache_bytes(cache_dir, cache_sha256, cache)
        _check_generation(plan)
        complete = len(completed) == len(plan["calendar"])
        manifest_path = run_dir / "run_manifest.json"
        if complete and not manifest_path.exists():
            base._publish_json(manifest_path, base._completed_manifest(plan, completed))
        days = [row["snapshot_at"] for row in completed]
        return {"run_dir": str(run_dir), "run_status": "COMPLETE" if complete else "INCOMPLETE",
                "completed_dates": days, "pending_dates": [row["snapshot_at"] for row in plan["calendar"] if row["snapshot_at"] not in days],
                "written_dates": written, "reused_dates": reused,
                "run_plan_sha256": file_sha256(plan_path),
                "run_manifest_sha256": file_sha256(manifest_path) if complete else None, "ready_for_load": False}


def verify_history(*, run_dir, cache_dir, cache_sha256, run_manifest_sha256):
    """Independently verify all files, including the production writer identity."""
    run_dir, cache_dir = base._path(run_dir), base._path(cache_dir)
    base._validate_sha(run_manifest_sha256, "run manifest SHA")
    cache = verify_cache(cache_dir, cache_sha256)
    plan = _plan(cache_dir, cache_sha256, cache)
    if base._read_json(run_dir / "run_plan.json") != plan or file_sha256(run_dir / "run_plan.json") != sha256(plan):
        raise ValueError("Run plan input or generation contract mismatch")
    manifest_path = run_dir / "run_manifest.json"
    if file_sha256(manifest_path) != run_manifest_sha256:
        raise ValueError("Run manifest SHA mismatch")
    completed = []
    with base._connection() as con:
        daily._load_views(con, cache_dir, cache)
        for index in range(len(plan["calendar"])):
            row = daily._read_completed(con, run_dir, cache, plan, index)
            if row is None:
                raise ValueError("Run is incomplete")
            completed.append(row)
    if base._read_json(manifest_path) != base._completed_manifest(plan, completed):
        raise ValueError("Run manifest and snapshot completion records differ")
    verify_cache_bytes(cache_dir, cache_sha256, cache)
    _check_generation(plan)
    return {"run_dir": str(run_dir), "run_status": "COMPLETE", "snapshots_verified": len(completed),
            "run_manifest_sha256": run_manifest_sha256, "ready_for_load": False,
            "verification_scope": "NORMALIZED_CACHE_AND_DAILY_ARTIFACTS"}
