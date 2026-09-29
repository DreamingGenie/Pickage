"""Write and resume verified daily Parquet bundles from pinned history caches."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import tempfile
import uuid

import duckdb

from pipeline.preprocessing.requirements_resolution.input import file_sha256
from pipeline.preprocessing.requirements_resolution.policy import canonical_bytes, sha256
from pipeline.preprocessing.snapshot.policy import parse_timestamp
from pipeline.preprocessing.version_dependents.artifact import _reject_reparse_ancestors, _reparse, _sql_literal, _validate_sha
from pipeline.preprocessing.version_dependents.historical_cache import create_fixture_cache, generation_contract, verify_cache


FORMAT = "historical-daily-artifact-v1"
FILES = ("counts.parquet", "quality.parquet", "lineage.parquet")
MODE = "HISTORICAL_RECONSTRUCTION_FROM_FIXED_INPUT"
METRIC = "DISTINCT_SOURCE_VERSIONS_ON_RESOLVED_DIRECT_REQUIREMENTS"
_MAX_JSON_BYTES = 16 * 1024 * 1024


def _path(path):
    path = Path(path).absolute()
    _reject_reparse_ancestors(path)
    return path.resolve()


def _read_json(path):
    path = Path(path)
    if _reparse(path) or not path.is_file():
        raise ValueError("Missing or unsafe manifest: " + str(path))
    try:
        if path.stat().st_size > _MAX_JSON_BYTES:
            raise ValueError("Oversized manifest (maximum 16 MiB): " + str(path))
        with path.open("rb") as stream:
            body = stream.read(_MAX_JSON_BYTES + 1)
        # A file can grow after the initial stat.  The bounded read catches
        # growth observed during the read; the second stat catches growth
        # that happened just after the read returned.
        if len(body) > _MAX_JSON_BYTES or path.stat().st_size > _MAX_JSON_BYTES:
            raise ValueError("Oversized manifest (maximum 16 MiB): " + str(path))
    except FileNotFoundError as error:
        raise ValueError("Missing or unsafe manifest: " + str(path)) from error
    return json.loads(body)


def _publish_json(path, body):
    """Publish under the run lock; interrupted temporary files are harmless."""
    if path.exists():
        raise ValueError("Refusing to replace published metadata: " + str(path))
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    with temporary.open("xb") as stream:
        stream.write(canonical_bytes(body))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


@contextmanager
def _run_lock(run_dir):
    """Kernel lock is released by the OS on process death, including Windows."""
    path = _path(run_dir) / ".writer.lock"
    if _reparse(path):
        raise ValueError("Unsafe writer lock")
    with path.open("a+b") as stream:
        if stream.seek(0, 2) == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise RuntimeError("Another writer holds this historical run lock") from error
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _contract():
    return {"cache_generation": generation_contract(),
            "writer_sha256": file_sha256(Path(__file__)), "duckdb_version": duckdb.__version__}


@contextmanager
def _connection():
    with tempfile.TemporaryDirectory(prefix="historical-artifact-scratch-") as scratch:
        with duckdb.connect(config={"threads": 2, "memory_limit": "1GB"}) as con:
            con.execute("SET temp_directory=?", [scratch])
            con.execute("SET max_temp_directory_size='4GB'")
            yield con


def _plan(cache_dir, cache_sha, cache):
    return {"format": FORMAT, "cache_dir": str(cache_dir), "cache_manifest_sha256": cache_sha,
            "calendar": cache["calendar"], "generation_contract": _contract(), "ready_for_load": False}


def _load_views(con, cache_dir):
    for view, name in (("cache_counts", "count_intervals.parquet"),
                       ("cache_targets", "target_population.parquet"), ("cache_quality", "quality.parquet")):
        con.execute(f"CREATE VIEW {view} AS SELECT * FROM read_parquet({_sql_literal(cache_dir / name)}, hive_partitioning=false)")


def _json_table(con, name, body, schema):
    if name not in {"expected_quality", "expected_lineage"}:
        raise ValueError("Unknown output table")
    con.execute(f"CREATE OR REPLACE TEMP TABLE {name} AS SELECT unnest(from_json(?,?), recursive:=true)",
                [json.dumps([body], ensure_ascii=True), json.dumps([schema])])


def _expected_tables(con, cache, plan, index):
    day = plan["calendar"][index]["snapshot_at"]
    stamp = parse_timestamp(plan["calendar"][index]["snapshot_timestamp"]).isoformat(timespec="microseconds").replace("+00:00", "Z")
    plan_sha = sha256(plan)
    con.execute(f"""CREATE OR REPLACE TEMP VIEW expected_counts AS
        SELECT package_id, version, DATE '{day}' AS snapshot_at, TIMESTAMPTZ '{stamp}' AS snapshot_timestamp,
               dependents_count::INTEGER AS dependents_count
        FROM cache_counts WHERE start_index <= {index} AND {index} < end_index""")
    positive, total, maximum = con.execute("SELECT count(*),coalesce(sum(dependents_count),0),coalesce(max(dependents_count),0) FROM expected_counts").fetchone()
    original = con.execute("SELECT quality_json FROM cache_quality WHERE snapshot_index=?", [index]).fetchone()
    if original is None:
        raise ValueError("Missing cache snapshot quality")
    q = json.loads(original[0])
    targets = con.execute("SELECT count(*) FROM cache_targets WHERE birth_index<=?", [index]).fetchone()[0]
    if targets != q["target_versions"] or total != q["distinct_edges"] or positive > targets:
        raise ValueError("Cache count/quality/population mismatch")
    summary = {"source_versions": q["source_versions"], "target_versions": targets,
               "positive_target_versions": positive, "zero_target_versions": targets - positive,
               "selected_declarations": q["selected_declarations"], "resolved_declarations": q["resolved_declarations"],
               "unresolved_declarations": q["unresolved_declarations"], "distinct_edges": total,
               "duplicate_resolved_declarations": q["duplicate_resolved_declarations"],
               "max_dependents_count": maximum}
    body = {"run_plan_sha256": plan_sha, "snapshot_at": day, "snapshot_timestamp": stamp,
            "calculation_status": "COMPLETE", "resolution_status": q["resolution_status"],
            "ready_for_load": False, **summary, "quality_json": canonical_bytes(q).decode("utf-8")}
    schema = {"run_plan_sha256": "VARCHAR", "snapshot_at": "DATE", "snapshot_timestamp": "TIMESTAMPTZ",
              "calculation_status": "VARCHAR", "resolution_status": "VARCHAR", "ready_for_load": "BOOLEAN",
              **{key: "BIGINT" for key in summary}, "quality_json": "VARCHAR"}
    _json_table(con, "expected_quality", body, schema)
    lineage = {"run_plan_sha256": plan_sha, "cache_manifest_sha256": plan["cache_manifest_sha256"],
               **cache["lineage"], "snapshot_at": day, "snapshot_timestamp": stamp,
               "observed_snapshot_timestamp": cache["observed_snapshot_timestamp"], "calculation_mode": MODE,
               "metric_definition": METRIC, "verification_scope": "NORMALIZED_HISTORY_TABLES_ONLY",
               "generation_contract_sha256": sha256(plan["generation_contract"]), "ready_for_load": False}
    schema = {key: "VARCHAR" for key in lineage}
    schema.update(snapshot_at="DATE", snapshot_timestamp="TIMESTAMPTZ", observed_snapshot_timestamp="TIMESTAMPTZ",
                  ready_for_load="BOOLEAN")
    _json_table(con, "expected_lineage", lineage, schema)
    return {**summary, "resolution_status": q["resolution_status"]}


def _file_info(con, path):
    if _reparse(path) or not path.is_file():
        raise ValueError("Missing or unsafe output file: " + str(path))
    query = f"SELECT * FROM read_parquet({_sql_literal(path)},hive_partitioning=false)"
    schema = [[row[0], row[1]] for row in con.execute("DESCRIBE " + query).fetchall()]
    rows = con.execute("SELECT count(*) FROM (" + query + ")").fetchone()[0]
    return {"bytes": path.stat().st_size, "sha256": file_sha256(path), "rows": rows, "schema": schema}


def _verify_snapshot(con, attempt, cache, plan, index, expected_sha):
    attempt = _path(attempt)
    if not re.fullmatch("[0-9a-f]{32}", attempt.name):
        raise ValueError("Invalid attempt identity")
    path = attempt / "snapshot_manifest.json"
    manifest = _read_json(path)
    if file_sha256(path) != expected_sha:
        raise ValueError("Snapshot manifest SHA mismatch")
    if {p.name for p in attempt.iterdir()} != {*FILES, "snapshot_manifest.json"}:
        raise ValueError("Snapshot attempt file set mismatch")
    summary = _expected_tables(con, cache, plan, index)
    required = {"format": FORMAT, "run_plan_sha256": sha256(plan), "cache_manifest_sha256": plan["cache_manifest_sha256"],
                "snapshot_index": index, **plan["calendar"][index], "attempt_id": attempt.name,
                "quality_summary": summary, "ready_for_load": False}
    if set(manifest) != set(required) | {"files"} or any(manifest.get(k) != v for k, v in required.items()):
        raise ValueError("Snapshot manifest identity or quality mismatch")
    if set(manifest["files"]) != set(FILES):
        raise ValueError("Snapshot manifest has unexpected output files")
    for filename, table in zip(FILES, ("expected_counts", "expected_quality", "expected_lineage")):
        target = attempt / filename
        actual_info = _file_info(con, target)
        if actual_info != manifest["files"][filename]:
            raise ValueError("Snapshot file SHA/schema/row count mismatch: " + filename)
        expected_schema = [[row[0], row[1]] for row in con.execute("DESCRIBE " + table).fetchall()]
        if actual_info["schema"] != expected_schema:
            raise ValueError("Snapshot file schema mismatch: " + filename)
        actual = f"SELECT * FROM read_parquet({_sql_literal(target)},hive_partitioning=false)"
        mismatch = con.execute(f"""SELECT EXISTS (
            (SELECT * FROM {table} EXCEPT ALL {actual}) UNION ALL
            ({actual} EXCEPT ALL SELECT * FROM {table}))""").fetchone()[0]
        if mismatch:
            raise ValueError("Snapshot values differ from pinned cache: " + filename)
    return manifest


def _write_snapshot(con, *, run_dir, cache, plan, index):
    day_dir = _path(run_dir / ("snapshot=" + plan["calendar"][index]["snapshot_at"]))
    attempt = _path(day_dir / "attempts" / uuid.uuid4().hex)
    attempt.mkdir(parents=True, exist_ok=False)
    summary = _expected_tables(con, cache, plan, index)
    info = {}
    for filename, table in zip(FILES, ("expected_counts", "expected_quality", "expected_lineage")):
        target = attempt / filename
        order = " ORDER BY package_id, version" if table == "expected_counts" else ""
        con.execute(f"COPY (SELECT * FROM {table}{order}) TO {_sql_literal(target)} (FORMAT PARQUET, COMPRESSION ZSTD)")
        info[filename] = _file_info(con, target)
    manifest = {"format": FORMAT, "run_plan_sha256": sha256(plan), "cache_manifest_sha256": plan["cache_manifest_sha256"],
                "snapshot_index": index, **plan["calendar"][index], "attempt_id": attempt.name,
                "files": info, "quality_summary": summary, "ready_for_load": False}
    _publish_json(attempt / "snapshot_manifest.json", manifest)
    manifest_sha = file_sha256(attempt / "snapshot_manifest.json")
    _verify_snapshot(con, attempt, cache, plan, index, manifest_sha)
    if _contract() != plan["generation_contract"]:
        raise ValueError("Generation code changed during snapshot writing")
    anchor = {"snapshot_at": plan["calendar"][index]["snapshot_at"], "attempt_id": attempt.name,
              "manifest_sha256": manifest_sha, "run_plan_sha256": sha256(plan)}
    _publish_json(day_dir / "complete.json", anchor)
    return anchor


def _read_completed(con, run_dir, cache, plan, index):
    day = plan["calendar"][index]["snapshot_at"]
    day_dir = _path(run_dir / ("snapshot=" + day))
    marker = day_dir / "complete.json"
    if not marker.exists():
        return None
    anchor = _read_json(marker)
    if (set(anchor) != {"snapshot_at", "attempt_id", "manifest_sha256", "run_plan_sha256"}
            or anchor["snapshot_at"] != day or anchor["run_plan_sha256"] != sha256(plan)
            or not isinstance(anchor["attempt_id"], str) or not re.fullmatch("[0-9a-f]{32}", anchor["attempt_id"])):
        raise ValueError("Snapshot completion marker identity mismatch")
    _validate_sha(anchor["manifest_sha256"], "snapshot manifest SHA")
    manifest = _verify_snapshot(con, day_dir / "attempts" / anchor["attempt_id"], cache, plan, index, anchor["manifest_sha256"])
    return {**anchor, "complete_sha256": file_sha256(marker), "quality_summary": manifest["quality_summary"]}


def _completed_manifest(plan, completed):
    return {"format": FORMAT, "run_status": "COMPLETE", "run_plan_sha256": sha256(plan),
            "cache_manifest_sha256": plan["cache_manifest_sha256"], "ready_for_load": False,
            "completed": completed, "snapshot_count": len(completed),
            "positive_count_rows": sum(row["quality_summary"]["positive_target_versions"] for row in completed)}


def build_history(*, cache_dir, cache_sha256, output, resume=False, max_snapshots=None):
    """Resume output dates only after exact input and generation identity checks."""
    if max_snapshots is not None and (type(max_snapshots) is not int or max_snapshots <= 0):
        raise ValueError("max_snapshots must be positive")
    cache_dir, run_dir = _path(cache_dir), _path(output)
    if cache_dir.is_relative_to(run_dir) or run_dir.is_relative_to(cache_dir):
        raise ValueError("Cache and run directories must be separate")
    _validate_sha(cache_sha256, "cache manifest SHA")
    cache = verify_cache(cache_dir, cache_sha256)
    plan = _plan(cache_dir, cache_sha256, cache)
    if resume:
        if not run_dir.is_dir():
            raise ValueError("Resume requires an existing run")
    else:
        run_dir.mkdir(parents=True, exist_ok=False)
    with _run_lock(run_dir):
        plan_path = run_dir / "run_plan.json"
        if plan_path.exists():
            if _read_json(plan_path) != plan:
                raise ValueError("Run input, calendar, or generation contract differs; use a new run")
        else:
            if any(p.name != ".writer.lock" and not p.name.startswith("run_plan.json.tmp-") for p in run_dir.iterdir()):
                raise ValueError("Existing output has no valid generation plan")
            _publish_json(plan_path, plan)
        if file_sha256(plan_path) != sha256(plan):
            raise ValueError("Run plan byte identity mismatch")
        completed, written, reused = [], [], []
        with _connection() as con:
            _load_views(con, cache_dir)
            # Verify all existing dates before creating additional output.
            pending = []
            for index, row in enumerate(plan["calendar"]):
                existing = _read_completed(con, run_dir, cache, plan, index)
                if existing is not None:
                    completed.append(existing)
                    reused.append(row["snapshot_at"])
                else:
                    pending.append(index)
            if (run_dir / "run_manifest.json").exists():
                if pending or _read_json(run_dir / "run_manifest.json") != _completed_manifest(plan, completed):
                    raise ValueError("Published run manifest differs from completed snapshots")
            for index in pending[:max_snapshots]:
                _write_snapshot(con, run_dir=run_dir, cache=cache, plan=plan, index=index)
                completed.append(_read_completed(con, run_dir, cache, plan, index))
                written.append(plan["calendar"][index]["snapshot_at"])
        completed.sort(key=lambda row: row["snapshot_at"])
        verify_cache(cache_dir, cache_sha256)
        if _contract() != plan["generation_contract"]:
            raise ValueError("Generation code changed during run")
        complete = len(completed) == len(plan["calendar"])
        manifest_path = run_dir / "run_manifest.json"
        if complete and not manifest_path.exists():
            _publish_json(manifest_path, _completed_manifest(plan, completed))
        days = [row["snapshot_at"] for row in completed]
        return {"run_dir": str(run_dir), "run_status": "COMPLETE" if complete else "INCOMPLETE",
                "completed_dates": days, "pending_dates": [row["snapshot_at"] for row in plan["calendar"] if row["snapshot_at"] not in days],
                "written_dates": written, "reused_dates": reused,
                "run_plan_sha256": file_sha256(plan_path),
                "run_manifest_sha256": file_sha256(manifest_path) if complete else None, "ready_for_load": False}


def verify_history(*, run_dir, cache_dir, cache_sha256, run_manifest_sha256):
    """Read-only verification against pinned cache and run manifest hashes."""
    run_dir, cache_dir = _path(run_dir), _path(cache_dir)
    _validate_sha(run_manifest_sha256, "run manifest SHA")
    cache = verify_cache(cache_dir, cache_sha256)
    plan = _plan(cache_dir, cache_sha256, cache)
    if _read_json(run_dir / "run_plan.json") != plan or file_sha256(run_dir / "run_plan.json") != sha256(plan):
        raise ValueError("Run plan input or generation contract mismatch")
    manifest_path = run_dir / "run_manifest.json"
    if file_sha256(manifest_path) != run_manifest_sha256:
        raise ValueError("Run manifest SHA mismatch")
    completed = []
    with _connection() as con:
        _load_views(con, cache_dir)
        for index in range(len(plan["calendar"])):
            row = _read_completed(con, run_dir, cache, plan, index)
            if row is None:
                raise ValueError("Run is incomplete")
            completed.append(row)
    if _read_json(manifest_path) != _completed_manifest(plan, completed):
        raise ValueError("Run manifest and snapshot completion records differ")
    verify_cache(cache_dir, cache_sha256)
    if _contract() != plan["generation_contract"]:
        raise ValueError("Generation code changed during verification")
    return {"run_dir": str(run_dir), "run_status": "COMPLETE", "snapshots_verified": len(completed),
            "run_manifest_sha256": run_manifest_sha256, "ready_for_load": False,
            "verification_scope": "NORMALIZED_CACHE_AND_DAILY_ARTIFACTS"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument("--cache-dir", type=Path, required=True)
    build.add_argument("--cache-sha256", required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--resume", action="store_true")
    build.add_argument("--max-snapshots", type=int)
    verify = commands.add_parser("verify")
    verify.add_argument("--run-dir", type=Path, required=True)
    verify.add_argument("--cache-dir", type=Path, required=True)
    verify.add_argument("--cache-sha256", required=True)
    verify.add_argument("--run-manifest-sha256", required=True)
    example = commands.add_parser("demo")
    example.add_argument("--fixture", type=Path, required=True)
    example.add_argument("--output", type=Path, required=True)
    args = vars(parser.parse_args())
    command = args.pop("command")
    if command == "build":
        result = build_history(**args)
    elif command == "verify":
        result = verify_history(**args)
    else:
        output = _path(args["output"])
        output.mkdir(parents=True, exist_ok=False)
        cache = create_fixture_cache(args["fixture"], output / "cache")
        first = build_history(cache_dir=output / "cache", cache_sha256=cache["manifest_sha256"],
                              output=output / "run", max_snapshots=1)
        final = build_history(cache_dir=output / "cache", cache_sha256=cache["manifest_sha256"],
                              output=output / "run", resume=True)
        verification = verify_history(run_dir=output / "run", cache_dir=output / "cache", cache_sha256=cache["manifest_sha256"],
                                      run_manifest_sha256=final["run_manifest_sha256"])
        result = {"synthetic_data_only": True, "cache": cache, "first": first, "final": final, "verification": verification}
        _publish_json(output / "demo_receipt.json", result)
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
