"""Adapter from the weekly single-snapshot stage to the weighted CPU runner.

The historical parallel runner owns partition scheduling, durable receipts and
weighted event aggregation.  This module only adapts the weekly stage's pinned
Parquet inputs to that runner and converts its one-date history back to the
stage output contract.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from pipeline.preprocessing.requirements_resolution.bridge import discover_runtime
from pipeline.preprocessing.snapshot.policy import parse_timestamp
from pipeline.preprocessing.version_dependents.historical_input import build_populations, _micros
from pipeline.preprocessing.version_dependents.historical_production_events import validate_weighted_inputs
from pipeline.preprocessing.version_dependents import historical_parallel as parallel
from pipeline.preprocessing.version_dependents import historical_parallel_input as parallel_input
from pipeline.preprocessing.version_dependents.historical_production_input import partition_for, connection
from pipeline.preprocessing.requirements_resolution.input import file_sha256
from pipeline.preprocessing.requirements_resolution.policy import sha256


PARTITION_COUNT = 128


def _sql_literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def _load_weekly_views(con, files):
    for table in ("package", "version", "requirements"):
        con.read_parquet([str(p) for p in files[table]], hive_partitioning=False).create_view("input_" + table)
    con.read_parquet([str(p) for p in files["versions_full"]], hive_partitioning=False).create_view("raw_versions")
    columns = {row[0] for row in con.execute("DESCRIBE raw_versions").fetchall()}
    extra = "" if "dependency_error" in columns else ",NULL::BOOLEAN AS dependency_error"
    con.execute("CREATE OR REPLACE VIEW input_versions_full AS SELECT *" + extra + " FROM raw_versions")
    con.read_parquet(str(files["targets"]), hive_partitioning=False).create_view("selected_names")
    if con.execute("SELECT count(*) FROM selected_names").fetchone()[0] == 0:
        raise ValueError("Empty dependents target selection")
    if con.execute("SELECT EXISTS(SELECT 1 FROM selected_names WHERE name IS NULL OR name<>trim(name) OR name='' OR contains(name,chr(0)))").fetchone()[0]:
        raise ValueError("Invalid dependents target name")
    if con.execute("SELECT EXISTS(SELECT name FROM selected_names GROUP BY name HAVING count(*)<>1)").fetchone()[0]:
        raise ValueError("Duplicate dependents target name")


def _prepare_tables(con, *, snapshot, snapshot_timestamp, output):
    """Build the exact weekly populations, assigning stable 128-way ownership."""
    runtime = discover_runtime()
    Path(output).mkdir(parents=True, exist_ok=True)
    names = [r[0] for r in con.execute("SELECT name FROM selected_names ORDER BY name").fetchall()]
    con.execute("CREATE TEMP TABLE selected_partition AS SELECT value.name, value.partition_id FROM (SELECT unnest(from_json(?,?)) AS value)", [
        json.dumps([{"name": name, "partition_id": partition_for(name, PARTITION_COUNT)} for name in names]),
        '[{"name":"VARCHAR","partition_id":"INTEGER"}]'])
    stamp = parse_timestamp(snapshot_timestamp)
    prepared = build_populations(
        con,
        [{"snapshot_index": 0, "snapshot_at": snapshot,
          "snapshot_timestamp": snapshot_timestamp, "timestamp_us": _micros(stamp)}],
        snapshot_timestamp, runtime, output,
    )
    con.execute("ALTER TABLE target_population RENAME TO all_target_population")
    con.execute("""CREATE TABLE target_population AS
        SELECT t.package_id,t.name,t.version,t.birth_index,
               s.partition_id
        FROM all_target_population t JOIN selected_partition s USING(name)""")
    con.execute("""CREATE TABLE target_names AS
        SELECT s.name,p.package_id,p.package_id IS NOT NULL AS known_package,
               sp.partition_id
        FROM selected_names s JOIN selected_partition sp USING(name)
        LEFT JOIN input_package p USING(name)""")
    con.execute("""CREATE TABLE requested AS
        WITH expanded AS (SELECT Name AS source_name,Version AS source_version,
           unnest(Dependencies) AS item,
           (generate_subscripts(Dependencies,1)-1)::BIGINT original_declaration_index
           FROM input_requirements)
        SELECT p.source_package_id,p.source_version,p.source_name,p.birth_index,p.dependency_error,
               e.original_declaration_index,e.item.Name declared_name,e.item.Requirement requirement
        FROM expanded e JOIN source_population p USING(source_name,source_version)
        JOIN selected_names t ON e.item.Name=t.name""")
    con.execute("""CREATE TABLE lookups AS SELECT
        (row_number() OVER(ORDER BY declared_name,requirement NULLS FIRST)-1)::BIGINT lookup_id,
        declared_name,requirement,count(*)::BIGINT declaration_count,
        0::INTEGER first_source_birth, sp.partition_id
        FROM requested r JOIN selected_partition sp ON sp.name=r.declared_name
        GROUP BY declared_name,requirement,sp.partition_id""")
    con.execute("""CREATE TABLE declarations AS
        SELECT r.*,l.lookup_id,l.partition_id
        FROM requested r JOIN lookups l ON r.declared_name=l.declared_name
        AND r.requirement IS NOT DISTINCT FROM l.requirement""")
    # The resolver/weighted validator expects the same source identity checks as
    # the normal historical production input adapter.
    validate_weighted_inputs(con, 1)
    return prepared, runtime


def _write_prepared(con, prepared_dir, *, snapshot, snapshot_timestamp, selected_names, identity, metadata):
    prepared_dir.mkdir(parents=True, exist_ok=False)
    # Expose the views expected by the existing physical shard writer.
    for table in parallel_input.TABLES:
        con.execute(f"CREATE OR REPLACE VIEW {table}_source AS SELECT * FROM {table}")
    partitions, totals = parallel_input._write_shards(con, prepared_dir, PARTITION_COUNT)
    calendar = [{"snapshot_at": snapshot, "snapshot_timestamp": snapshot_timestamp}]
    chosen = sorted(selected_names)
    selection = {"chosen_names": chosen, "chosen_count": len(chosen), "chosen_names_sha256": sha256(chosen)}
    generation = parallel_input.contract()
    plan = {"format": parallel_input.FORMAT, "scope": "FULL_SELECTED", "source_dir": str(prepared_dir.parent),
            "source_manifest_sha256": sha256(identity),
            "weekly_metadata": metadata,
            "selection": selection, "calendar": calendar,
            "observed_snapshot_timestamp": snapshot_timestamp, "policy": parallel_input.POLICY,
            "partition_count": PARTITION_COUNT, "generation_contract": generation,
            "ready_for_load": False}
    parallel_input._publish_json(prepared_dir / "input_plan.json", plan)
    manifest = {**plan, "preparation_status": "COMPLETE", "count_status": "NOT_COMPUTED",
                "partitions": partitions,
                "files": {r["name"]: r for p in partitions.values() for r in p["files"].values()},
                "rows": totals, "partition_count": PARTITION_COUNT,
                "input_plan_sha256": file_sha256(prepared_dir / "input_plan.json")}
    parallel_input._publish_json(prepared_dir / "input_manifest.json", manifest)
    digest = file_sha256(prepared_dir / "input_manifest.json")
    return prepared_dir, digest


def _materialize_stage_outputs(con, *, files, root, prepared, run_result, snapshot, metadata):
    run_dir = Path(run_result["run_dir"])
    result = json.loads((run_dir / "run_manifest.json").read_bytes())
    directory = parallel.old._within(run_dir, result["cache"]["directory"])
    con.read_parquet(str(directory / "cache" / "count_intervals.parquet"), hive_partitioning=False).create_view("parallel_counts")
    quality_row = con.execute("SELECT quality_json FROM read_parquet(?) WHERE snapshot_index=0",
                              [str(directory / "cache" / "quality.parquet")]).fetchone()
    aggregate_quality = json.loads(quality_row[0])
    manifest = json.loads((prepared / "input_manifest.json").read_bytes())
    for table, view in (("target_population", "parallel_targets"), ("target_names", "parallel_names")):
        paths = [str(prepared / part["files"][table]["name"]) for part in manifest["partitions"].values()
                 if part["status"] == "READY"]
        con.read_parquet(paths, hive_partitioning=False).create_view(view)
    lookup_paths = [str(parallel.old._within(run_dir, receipt["attempt"]) / "lookup_intervals.parquet")
                    for receipt in result["partitions"]]
    con.read_parquet(lookup_paths, hive_partitioning=False).create_view("parallel_lookup")
    output = root / "outputs"
    output.mkdir(exist_ok=True)
    con.execute("""CREATE TEMP VIEW service_result AS
        SELECT v.package_id,v.version,""" + _sql_literal(snapshot) + """::DATE snapshot_at,
        CASE WHEN t.package_id IS NOT NULL THEN coalesce(c.dependents_count,0)::BIGINT ELSE NULL::BIGINT END dependents_count
        FROM input_version v LEFT JOIN parallel_targets t USING(package_id,version)
        LEFT JOIN parallel_counts c ON v.package_id=c.package_id AND v.version=c.version
                                   AND c.start_index=0 AND c.end_index=1""")
    con.execute("""CREATE TEMP VIEW quality_result AS
        SELECT r.*,CASE WHEN t.package_id IS NOT NULL THEN NULL
        WHEN s.name IS NULL THEN 'NOT_SELECTED_TARGET' ELSE 'INELIGIBLE_TARGET_VERSION' END null_reason
        FROM service_result r JOIN input_package p USING(package_id)
        LEFT JOIN selected_names s ON p.name=s.name
        LEFT JOIN parallel_targets t ON r.package_id=t.package_id AND r.version=t.version""")
    if con.execute("SELECT EXISTS(SELECT package_id,version FROM service_result GROUP BY 1,2 HAVING count(*)<>1)").fetchone()[0]:
        raise ValueError("Duplicate version dependents output key")
    if con.execute("SELECT count(*) FROM service_result").fetchone()[0] != con.execute("SELECT count(*) FROM input_version").fetchone()[0]:
        raise ValueError("Version dependents population mismatch")
    records = []
    for table, role in (("service_result", "version_dependents"), ("quality_result", "quality"),
                        ("parallel_lookup", "resolution_lookup")):
        path = output / (role + ".parquet")
        con.execute(f"COPY (SELECT * FROM {table} ORDER BY ALL) TO {_sql_literal(path)} (FORMAT PARQUET,COMPRESSION ZSTD)")
        schema = [list(row[:2]) for row in con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]).fetchall()]
        records.append({"path": path.name, "role": role, "schema": schema,
                        "row_count": con.execute("SELECT count(*) FROM read_parquet(?)", [str(path)]).fetchone()[0]})
    unresolved = aggregate_quality["unresolved_declarations"]
    gaps = metadata["source_gaps"]
    quality = {"calculation_status": "COMPLETE",
               "resolution_status": "PARTIAL" if unresolved or any(gaps.values()) else "COMPLETE",
               "unresolved_declarations": unresolved, "source_gaps": gaps,
               "population": metadata["population"], "aggregation": aggregate_quality,
               "resolution": {"backend": "cpu", "algorithm": "weighted-events-v2"},
               "runtime": json.loads((run_dir / "run_plan.json").read_bytes())["runtime"],
               "resources": run_result["resources"], "rows": records[0]["row_count"],
               "zero_rows": con.execute("SELECT count(*) FROM service_result WHERE dependents_count=0").fetchone()[0],
               "null_rows": con.execute("SELECT count(*) FROM service_result WHERE dependents_count IS NULL").fetchone()[0],
               "snapshot_count": 1, "engine": "historical_parallel_cpu_weighted"}
    return output, records, quality


def _identity(files, snapshot, snapshot_timestamp):
    return {"snapshot": snapshot, "snapshot_timestamp": snapshot_timestamp,
            "files": {key: [{"sha256": file_sha256(Path(p)), "bytes": Path(p).stat().st_size}
                            for p in (value if isinstance(value, list) else [value])]
                      for key, value in sorted(files.items())},
            "adapter_sha256": file_sha256(Path(__file__)), "runner_contract": parallel.contract()}


def calculate(con=None, *, files, snapshot, snapshot_timestamp, output, workers=2, threads=2,
              memory_limit="2GB", max_temp_size="100GB"):
    """Take ownership of the caller connection; phases use one bounded budget."""
    if con is not None:
        con.close()
    settings = dict(threads=threads, memory_limit=memory_limit, max_temp_size=max_temp_size)
    parallel._settings(workers, **settings)
    output = Path(output).absolute()
    output.mkdir(parents=True, exist_ok=True)
    identity = _identity(files, snapshot, snapshot_timestamp)
    identity_path = output / "identity.json"
    if identity_path.exists():
        if json.loads(identity_path.read_bytes()) != identity:
            raise ValueError("Existing parallel input identity or code differs")
    else:
        parallel_input._publish_json(identity_path, identity)
    ready_path = output / "input-ready.json"
    if ready_path.exists():
        ready = json.loads(ready_path.read_bytes())
        if ready["identity_sha256"] != sha256(identity):
            raise ValueError("Prepared input identity differs")
        prepared = parallel.old._within(output, ready["directory"])
        digest = ready["manifest_sha256"]
    else:
        attempt = output / ("prep-" + uuid.uuid4().hex[:12])
        attempt.mkdir()
        with connection(attempt / "working.duckdb", **settings) as prepare_con:
            _load_weekly_views(prepare_con, files)
            population, _ = _prepare_tables(prepare_con, snapshot=snapshot,
                snapshot_timestamp=snapshot_timestamp, output=attempt)
            gaps = dict(zip(("missing_requirements", "null_dependency_list", "extraction_error", "unknown_extraction_status"),
                prepare_con.execute("SELECT count(*) FILTER(WHERE NOT requirements_present),"
                    "count(*) FILTER(WHERE selected_list_null),count(*) FILTER(WHERE dependency_error=true),"
                    "count(*) FILTER(WHERE dependency_error IS NULL) FROM source_population").fetchone()))
            selected = [r[0] for r in prepare_con.execute("SELECT name FROM selected_names ORDER BY name").fetchall()]
            prepared, digest = _write_prepared(prepare_con, attempt / "input", snapshot=snapshot,
                snapshot_timestamp=snapshot_timestamp, selected_names=selected, identity=identity,
                metadata={"population": population["statistics"], "source_gaps": gaps})
        # Validate only after releasing the preparation database's buffers.
        parallel_input.verify_inputs(prepared, digest, **settings)
        ready = {"directory": prepared.relative_to(output).as_posix(), "manifest_sha256": digest,
                 "identity_sha256": sha256(identity)}
        parallel_input._publish_json(ready_path, ready)
        # Verified input shards are the resume boundary; the preparation DB is
        # only scratch and can otherwise duplicate many GB of the same input.
        (attempt / "working.duckdb").unlink()
    input_manifest = parallel_input._manifest(prepared, digest)
    if input_manifest["source_manifest_sha256"] != sha256(identity):
        raise ValueError("Prepared input source identity differs")
    run_dir = output / "parallel-run"
    result = parallel.run(prepared_dir=prepared, manifest_sha256=digest, output=run_dir,
                          workers=workers, **settings, history_layout="grouped",
                          allow_full_selected=True, resume=run_dir.exists())
    if result.get("run_status") != "COMPLETE":
        raise RuntimeError("Parallel dependents run did not complete: " + json.dumps(result, sort_keys=True))
    parallel.verify_run(run_dir=run_dir, manifest_sha256=result["run_manifest_sha256"], **settings)
    # The prepared files are verified by run() on every retry. Recheck original
    # file bytes before publishing an output derived from those pinned inputs.
    if _identity(files, snapshot, snapshot_timestamp) != identity:
        raise ValueError("Dependents input or code changed during execution")
    with connection(output / ("export-" + uuid.uuid4().hex[:12] + ".duckdb"), **settings) as export_con:
        _load_weekly_views(export_con, files)
        return _materialize_stage_outputs(export_con, files=files, root=output, prepared=prepared,
            run_result=result, snapshot=snapshot, metadata=parallel_input._manifest(prepared, digest)["weekly_metadata"])
