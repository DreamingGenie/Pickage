"""Adapter from the weekly single-snapshot stage to the weighted CPU runner.

The historical parallel runner owns partition scheduling, durable receipts and
weighted event aggregation.  This module only adapts the weekly stage's pinned
Parquet inputs to that runner and converts its one-date history back to the
stage output contract.
"""
from __future__ import annotations

import json
import shutil
import uuid
from time import perf_counter
from pathlib import Path

from pipeline.preprocessing.requirements_resolution.bridge import discover_runtime
from pipeline.preprocessing.snapshot.policy import parse_timestamp
from pipeline.preprocessing.version_dependents.historical_input import (
    _classify_versions, _validate_relations, _micros)
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


def _prepare_tables_bounded(con, *, snapshot, snapshot_timestamp, output, names):
    """Prepare the weekly selected declarations without a full wide join.

    Historical reconstruction remains the general oracle.  The weekly adapter
    only needs selected target declarations, so package/version/raw/
    requirements joins are processed in bounded name buckets while preserving
    the complete source population statistics.
    """
    runtime = discover_runtime()
    root = Path(output)
    staging = root / "bounded-staging"
    staging.mkdir(parents=True, exist_ok=True)
    _validate_relations(con, snapshot_timestamp)
    stamp = parse_timestamp(snapshot_timestamp)
    stamp_us = _micros(stamp)
    con.execute("CREATE OR REPLACE TEMP VIEW version_basis AS SELECT version FROM input_version")
    runtime_metadata = _classify_versions(runtime=runtime, con=con, output=root)
    con.execute("DROP VIEW version_basis")
    con.execute("CREATE TEMP TABLE selected_partition AS SELECT value.name, value.partition_id FROM (SELECT unnest(from_json(?,?)) AS value)", [
        json.dumps([{"name": name, "partition_id": partition_for(name, PARTITION_COUNT)} for name in names]),
        '[{"name":"VARCHAR","partition_id":"INTEGER"}]'])
    source_versions = declarations = missing = null_lists = errors = unknown = targets = 0
    prerelease_targets = invalid_targets = 0
    target_parts, requested_parts = [], []
    package_count = int(con.execute("SELECT count(*) FROM input_package").fetchone()[0])
    bucket_count = min(16, max(1, (package_count + 249_999) // 250_000))
    for bucket in range(bucket_count):
        bucket_started = perf_counter()
        predicate = f"hash(name) % {bucket_count} = {bucket}"
        con.execute(f"CREATE OR REPLACE TEMP VIEW bucket_package AS SELECT package_id,name FROM input_package WHERE {predicate}")
        con.execute(f"CREATE OR REPLACE TEMP VIEW bucket_version AS SELECT v.package_id,p.name,v.version,v.published_at FROM input_version v JOIN bucket_package p USING(package_id)")
        con.execute(f"CREATE OR REPLACE TEMP VIEW bucket_raw AS SELECT * FROM input_versions_full WHERE hash(Name) % {bucket_count} = {bucket}")
        con.execute(f"CREATE OR REPLACE TEMP VIEW bucket_requirements AS SELECT Name,Version,Dependencies,Name IS NOT NULL AS requirements_present,Name IS NOT NULL AND Dependencies IS NULL AS selected_list_null,coalesce(array_length(Dependencies),0)::BIGINT AS declaration_count,array_length(PeerDependencies)::BIGINT AS excluded_peer_count,array_length(OptionalDependencies)::BIGINT AS excluded_optional_count FROM input_requirements WHERE {predicate}")
        con.execute("""CREATE OR REPLACE TEMP TABLE bucket_birth AS
            SELECT v.package_id,v.name,v.version,v.published_at AS published_at_raw,
                   v.published_at AS published_at,epoch_us(v.published_at) AS published_at_us,
                   r.dependency_error,r.Name AS raw_name,r.is_release,r.published_at AS raw_published_at,
                   CASE WHEN epoch_us(v.published_at)<=? THEN 0::INTEGER END AS birth_index,
                   s.target_status
            FROM bucket_version v JOIN semver_classification s USING(version)
            LEFT JOIN bucket_raw r ON v.name=r.Name AND v.version=r.Version""", [stamp_us])
        if con.execute("SELECT 1 FROM bucket_birth WHERE raw_name IS NULL OR is_release IS DISTINCT FROM true OR published_at IS DISTINCT FROM raw_published_at LIMIT 1").fetchone():
            raise ValueError("Curated version lacks matching raw release/date provenance")
        con.execute("""CREATE OR REPLACE TEMP TABLE bucket_source AS
            SELECT v.package_id AS source_package_id,v.name AS source_name,v.version AS source_version,
                   v.published_at_raw,v.published_at,v.published_at_us,v.birth_index,v.dependency_error,
                   coalesce(r.requirements_present,false) requirements_present,
                   coalesce(r.selected_list_null,false) selected_list_null,
                   coalesce(r.declaration_count,0)::BIGINT declaration_count,
                   r.excluded_peer_count,r.excluded_optional_count
            FROM bucket_birth v LEFT JOIN bucket_requirements r ON v.name=r.Name AND v.version=r.Version
            WHERE v.birth_index IS NOT NULL""")
        row = con.execute("SELECT count(*),coalesce(sum(declaration_count),0),count(*) FILTER(WHERE NOT requirements_present),count(*) FILTER(WHERE selected_list_null),count(*) FILTER(WHERE dependency_error=true),count(*) FILTER(WHERE dependency_error IS NULL) FROM bucket_source").fetchone()
        source_versions += int(row[0]); declarations += int(row[1]); missing += int(row[2]); null_lists += int(row[3]); errors += int(row[4]); unknown += int(row[5])
        target_counts = con.execute("SELECT count(*) FILTER(WHERE birth_index IS NOT NULL AND target_status='ELIGIBLE'),count(*) FILTER(WHERE birth_index IS NOT NULL AND target_status='PRERELEASE_TARGET'),count(*) FILTER(WHERE birth_index IS NOT NULL AND target_status='INVALID_TARGET_SEMVER') FROM bucket_birth").fetchone()
        targets += int(target_counts[0]); prerelease_targets += int(target_counts[1]); invalid_targets += int(target_counts[2])
        target_path = staging / f"target-{bucket:02d}.parquet"
        con.execute("""COPY (SELECT b.package_id,b.name,b.version,b.birth_index,s.partition_id
                    FROM bucket_birth b JOIN selected_partition s USING(name)
                    WHERE b.birth_index IS NOT NULL AND b.target_status='ELIGIBLE') TO ? (FORMAT PARQUET, COMPRESSION ZSTD)""", [str(target_path)])
        target_parts.append(str(target_path))
        requested_path = staging / f"requested-{bucket:02d}.parquet"
        con.execute("""COPY (WITH expanded AS (
                    SELECT r.Name AS source_name,r.Version AS source_version,
                           unnest(r.Dependencies) AS item,
                           (generate_subscripts(r.Dependencies,1)-1)::BIGINT original_declaration_index
                    FROM bucket_requirements r)
                SELECT p.source_package_id,p.source_version,p.source_name,p.birth_index,p.dependency_error,
                       e.original_declaration_index,e.item.Name declared_name,e.item.Requirement requirement
                FROM expanded e JOIN bucket_source p USING(source_name,source_version)
                JOIN selected_names t ON e.item.Name=t.name) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)""", [str(requested_path)])
        requested_parts.append(str(requested_path))
        con.execute("DROP TABLE bucket_source")
        con.execute("DROP TABLE bucket_birth")
        print(
            "DEPENDENTS_PREP_BUCKET "
            f"bucket={bucket + 1}/{bucket_count} "
            f"input_rows={int(con.execute('SELECT count(*) FROM bucket_version').fetchone()[0])} "
            f"elapsed_seconds={perf_counter() - bucket_started:.3f}",
            flush=True,
        )
    if not target_parts:
        raise ValueError("No bounded target shards")
    con.read_parquet(target_parts, hive_partitioning=False).create_view("target_population", replace=True)
    con.read_parquet(requested_parts, hive_partitioning=False).create_view("requested", replace=True)
    con.execute("CREATE TEMP TABLE target_names AS SELECT s.name,p.package_id,p.package_id IS NOT NULL AS known_package,sp.partition_id FROM selected_names s JOIN selected_partition sp USING(name) LEFT JOIN input_package p USING(name)")
    con.execute("""CREATE TABLE lookups AS SELECT
        (row_number() OVER (ORDER BY declared_name,requirement NULLS FIRST)-1)::BIGINT lookup_id,
        declared_name,requirement,count(*)::BIGINT declaration_count,0::INTEGER first_source_birth,sp.partition_id
        FROM requested r JOIN selected_partition sp ON sp.name=r.declared_name
        GROUP BY declared_name,requirement,sp.partition_id""")
    # Keep the complete declaration relation over the narrow staging shards;
    # copying hundreds of millions of rows into the preparation DB duplicates
    # the physical input shards that are written immediately afterwards.
    con.execute("""CREATE TEMP VIEW declarations AS SELECT r.*,l.lookup_id,l.partition_id
        FROM requested r JOIN lookups l ON r.declared_name=l.declared_name
        AND r.requirement IS NOT DISTINCT FROM l.requirement""")
    validate_weighted_inputs(con, 1)
    stats = {"curated_versions": int(con.execute("SELECT count(*) FROM input_version").fetchone()[0]),
             "null_publication_versions": int(con.execute("SELECT count(*) FROM input_version WHERE published_at IS NULL").fetchone()[0]),
             "after_last_snapshot_versions": 0, "eligible_sources": source_versions,
             "eligible_targets": targets, "prerelease_targets_excluded": prerelease_targets,
             "invalid_semver_targets_excluded": invalid_targets, "dense_target_snapshot_keys": targets,
             "source_snapshot_keys": source_versions, "selected_declarations_latest": declarations,
             "unique_original_version_strings": int(con.execute("SELECT count(*) FROM semver_classification").fetchone()[0])}
    stats["after_last_snapshot_versions"] = stats["curated_versions"] - stats["null_publication_versions"] - source_versions
    return ({"statistics": stats,
             "source_gaps": {"missing_requirements": missing, "null_dependency_list": null_lists,
                              "extraction_error": errors, "unknown_extraction_status": unknown}},
            runtime_metadata)


def _prepare_tables(con, *, snapshot, snapshot_timestamp, output):
    """Build the exact weekly populations, assigning stable 128-way ownership."""
    Path(output).mkdir(parents=True, exist_ok=True)
    names = [r[0] for r in con.execute("SELECT name FROM selected_names ORDER BY name").fetchall()]
    return _prepare_tables_bounded(con, snapshot=snapshot,
                                   snapshot_timestamp=snapshot_timestamp,
                                   output=output, names=names)


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
    # Materialize the two large service outputs in package buckets.  A single
    # global service_result view caused DuckDB to re-plan and spill the same
    # full population for validation, quality, and both ordered writes.
    package_count = int(con.execute("SELECT count(*) FROM input_package").fetchone()[0])
    bucket_count = min(16, max(1, (package_count + 249_999) // 250_000))
    stage = root / (".materialize-stage-" + uuid.uuid4().hex[:12])
    stage.mkdir(parents=True, exist_ok=False)
    version_parts, quality_parts = [], []
    service_rows = duplicate_keys = zero_rows = null_rows = 0
    try:
        expected_rows = int(con.execute("SELECT count(*) FROM input_version").fetchone()[0])
        for bucket in range(bucket_count):
            started = perf_counter()
            predicate = f"hash(p.name) % {bucket_count} = {bucket}"
            con.execute(f"""CREATE OR REPLACE TEMP VIEW materialize_versions AS
                SELECT v.package_id,v.version,p.name
                FROM input_version v JOIN input_package p USING(package_id)
                WHERE {predicate}""")
            con.execute(f"""CREATE OR REPLACE TEMP VIEW materialize_packages AS
                SELECT package_id,name FROM input_package p WHERE {predicate}""")
            con.execute(f"""CREATE OR REPLACE TEMP VIEW materialize_targets AS
                SELECT t.* FROM parallel_targets t WHERE hash(t.name) % {bucket_count} = {bucket}""")
            con.execute(f"""CREATE OR REPLACE TEMP VIEW materialize_counts AS
                SELECT c.* FROM parallel_counts c JOIN input_package p USING(package_id)
                WHERE {predicate}""")
            con.execute("""CREATE OR REPLACE TEMP VIEW materialize_service AS
                SELECT v.package_id,v.version,""" + _sql_literal(snapshot) + """::DATE snapshot_at,
                CASE WHEN t.package_id IS NOT NULL THEN coalesce(c.dependents_count,0)::BIGINT
                     ELSE NULL::BIGINT END dependents_count
                FROM materialize_versions v
                LEFT JOIN materialize_targets t USING(package_id,version)
                LEFT JOIN materialize_counts c ON v.package_id=c.package_id AND v.version=c.version
                    AND c.start_index=0 AND c.end_index=1""")
            con.execute("""CREATE OR REPLACE TEMP VIEW materialize_quality AS
                SELECT r.*,CASE WHEN t.package_id IS NOT NULL THEN NULL
                WHEN s.name IS NULL THEN 'NOT_SELECTED_TARGET' ELSE 'INELIGIBLE_TARGET_VERSION' END null_reason
                FROM materialize_service r JOIN materialize_packages p USING(package_id)
                LEFT JOIN selected_names s ON p.name=s.name
                LEFT JOIN materialize_targets t ON r.package_id=t.package_id AND r.version=t.version""")
            version_path = stage / f"version_dependents-{bucket:02d}.parquet"
            quality_path = stage / f"quality-{bucket:02d}.parquet"
            con.execute(f"COPY (SELECT * FROM materialize_service ORDER BY ALL) TO {_sql_literal(version_path)} (FORMAT PARQUET,COMPRESSION ZSTD)")
            # Reuse the written shard for validation and quality projection so
            # the large service join is evaluated once per bucket.
            con.execute(f"CREATE OR REPLACE TEMP VIEW materialize_service AS SELECT * FROM read_parquet({_sql_literal(version_path)})")
            con.execute(f"COPY (SELECT * FROM materialize_quality ORDER BY ALL) TO {_sql_literal(quality_path)} (FORMAT PARQUET,COMPRESSION ZSTD)")
            version_parts.append(str(version_path))
            quality_parts.append(str(quality_path))
            bucket_rows, bucket_zero, bucket_null = con.execute(
                "SELECT count(*),count(*) FILTER(WHERE dependents_count=0),"
                "count(*) FILTER(WHERE dependents_count IS NULL) FROM read_parquet(?)",
                [str(version_path)]).fetchone()
            bucket_rows = int(bucket_rows)
            bucket_dupes = int(con.execute("SELECT count(*) FROM (SELECT package_id,version FROM materialize_service GROUP BY 1,2 HAVING count(*)<>1)").fetchone()[0])
            service_rows += bucket_rows
            duplicate_keys += bucket_dupes
            zero_rows += int(bucket_zero)
            null_rows += int(bucket_null)
            print(
                "DEPENDENTS_OUTPUT_BUCKET "
                f"bucket={bucket + 1}/{bucket_count} rows={bucket_rows} "
                f"elapsed_seconds={perf_counter() - started:.3f}",
                flush=True,
            )
            if bucket_dupes:
                raise ValueError("Duplicate version dependents output key")
        if duplicate_keys or service_rows != expected_rows:
            raise ValueError("Version dependents population mismatch")
        records = []
        for paths, role in ((version_parts, "version_dependents"), (quality_parts, "quality")):
            path = output / (role + ".parquet")
            con.execute(f"COPY (SELECT * FROM read_parquet(?)) TO {_sql_literal(path)} (FORMAT PARQUET,COMPRESSION ZSTD)", [paths])
            schema = [list(row[:2]) for row in con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]).fetchall()]
            records.append({"path": path.name, "role": role, "schema": schema,
                            "row_count": con.execute("SELECT count(*) FROM read_parquet(?)", [str(path)]).fetchone()[0]})
            if records[-1]["row_count"] != service_rows:
                raise ValueError("Version dependents output row count mismatch")
        if records[-1]["row_count"] != service_rows:
            raise ValueError("Quality output row count mismatch")
        path = output / "resolution_lookup.parquet"
        con.execute(f"COPY (SELECT * FROM parallel_lookup) TO {_sql_literal(path)} (FORMAT PARQUET,COMPRESSION ZSTD)")
        schema = [list(row[:2]) for row in con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]).fetchall()]
        records.append({"path": path.name, "role": "resolution_lookup", "schema": schema,
                        "row_count": con.execute("SELECT count(*) FROM read_parquet(?)", [str(path)]).fetchone()[0]})
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    unresolved = aggregate_quality["unresolved_declarations"]
    gaps = metadata["source_gaps"]
    quality = {"calculation_status": "COMPLETE",
               "resolution_status": "PARTIAL" if unresolved or any(gaps.values()) else "COMPLETE",
               "unresolved_declarations": unresolved, "source_gaps": gaps,
               "population": metadata["population"], "aggregation": aggregate_quality,
               "resolution": {"backend": "cpu", "algorithm": "weighted-events-v2"},
               "runtime": json.loads((run_dir / "run_plan.json").read_bytes())["runtime"],
               "resources": run_result["resources"], "rows": records[0]["row_count"],
               "zero_rows": zero_rows,
               "null_rows": null_rows,
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
            gaps = population["source_gaps"]
            selected = [r[0] for r in prepare_con.execute("SELECT name FROM selected_names ORDER BY name").fetchall()]
            prepared, digest = _write_prepared(prepare_con, attempt / "input", snapshot=snapshot,
                snapshot_timestamp=snapshot_timestamp, selected_names=selected, identity=identity,
                metadata={"population": population["statistics"], "source_gaps": gaps})
        shutil.rmtree(attempt / "bounded-staging", ignore_errors=True)
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
                          # This single-snapshot adapter has a much smaller
                          # workspace than the historical backfill runner's
                          # default 20GB free-space reserve.
                          min_free_bytes=2_000_000_000,
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
