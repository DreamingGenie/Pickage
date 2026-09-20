"""One observation date using task08 populations, resolver and SQL aggregation."""
import json
from pathlib import Path
import uuid

import duckdb

from pipeline.preprocessing.curated.storage import download_files, json_bytes, put_immutable, read_optional, upload_outputs, verify_files
from pipeline.preprocessing.requirements_resolution.bridge import NodeSession, discover_runtime
from pipeline.preprocessing.snapshot.policy import parse_timestamp
from pipeline.preprocessing.version_dependents.historical import WORKER
from pipeline.preprocessing.version_dependents.historical_input import build_populations, _micros
from pipeline.preprocessing.version_dependents.historical_production import _resolve_partition
from pipeline.preprocessing.version_dependents.historical_production_sql import aggregate_partition
from pipeline.preprocessing.orchestration.storage import BUCKET, pinned, required, sha

PREFIX = "depsdev/v1/version-dependents-single"


def calculate(con, *, files, snapshot, snapshot_timestamp, output, runtime=None):
    """Bounded disk-backed SQL; only one package's candidate set enters Python."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    runtime = runtime or discover_runtime()
    for table in ("package", "version", "requirements"):
        con.read_parquet([str(p) for p in files[table]], hive_partitioning=False).create_view("input_" + table)
    con.read_parquet([str(p) for p in files["versions_full"]], hive_partitioning=False).create_view("raw_versions")
    columns = {row[0] for row in con.execute("DESCRIBE raw_versions").fetchall()}
    # Absent extraction status is explicitly unknown, never defaulted to success.
    extra = "" if "dependency_error" in columns else ",NULL::BOOLEAN AS dependency_error"
    con.execute("CREATE VIEW input_versions_full AS SELECT *" + extra + " FROM raw_versions")
    con.read_parquet(str(files["targets"]), hive_partitioning=False).create_view("selected_names")
    if con.execute("SELECT count(*) FROM selected_names").fetchone()[0] == 0:
        raise ValueError("Empty dependents target selection")
    if con.execute("SELECT EXISTS(SELECT 1 FROM selected_names WHERE name IS NULL OR name<>trim(name) "
                   "OR name='' OR contains(name,chr(0)))").fetchone()[0]:
        raise ValueError("Invalid dependents target name")
    if con.execute("SELECT EXISTS(SELECT name FROM selected_names GROUP BY name HAVING count(*)<>1)").fetchone()[0]:
        raise ValueError("Duplicate dependents target name")
    stamp = parse_timestamp(snapshot_timestamp)
    prepared = build_populations(con, [{"snapshot_index": 0, "snapshot_at": snapshot,
        "snapshot_timestamp": snapshot_timestamp, "timestamp_us": _micros(stamp)}],
        snapshot_timestamp, runtime, output)
    # H1 eligibility and source semantics remain unchanged. Restrict only targets.
    con.execute("ALTER TABLE target_population RENAME TO all_target_population")
    con.execute("""CREATE TABLE target_population AS SELECT t.package_id,t.name,t.version,
                   t.birth_index,0::INTEGER partition_id FROM all_target_population t
                   JOIN selected_names s USING(name)""")
    con.execute("""CREATE TABLE target_names AS SELECT s.name,p.package_id,
                   p.package_id IS NOT NULL AS known_package,0::INTEGER partition_id
                   FROM selected_names s LEFT JOIN input_package p USING(name)""")
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
        declared_name,requirement,count(*)::BIGINT declaration_count,0::INTEGER partition_id
        FROM requested GROUP BY declared_name,requirement""")
    con.execute("""CREATE TABLE declarations AS SELECT r.*,l.lookup_id,0::INTEGER partition_id
        FROM requested r JOIN lookups l ON r.declared_name=l.declared_name
        AND r.requirement IS NOT DISTINCT FROM l.requirement""")
    with NodeSession(runtime, output / "resolution-node.log", worker=WORKER) as node:
        metadata = node.request({"op": "metadata"})
        resolution = _resolve_partition(con, node, metadata, 0, 1)
    aggregation = aggregate_partition(con, 1, 0)
    con.execute("""CREATE TABLE service_result AS
        SELECT v.package_id,v.version,?::DATE snapshot_at,
               CASE WHEN t.package_id IS NOT NULL THEN coalesce(c.dependents_count,0)::BIGINT
                    ELSE NULL::BIGINT END dependents_count
        FROM input_version v LEFT JOIN target_population t USING(package_id,version)
        LEFT JOIN p_counts c ON v.package_id=c.package_id AND v.version=c.version
                              AND c.start_index=0 AND c.end_index=1""", [snapshot])
    con.execute("""CREATE TABLE quality_result AS
        SELECT r.*,CASE WHEN t.package_id IS NOT NULL THEN NULL
                       WHEN s.name IS NULL THEN 'NOT_SELECTED_TARGET'
                       ELSE 'INELIGIBLE_TARGET_VERSION' END null_reason
        FROM service_result r JOIN input_package p USING(package_id)
        LEFT JOIN selected_names s ON p.name=s.name
        LEFT JOIN target_population t ON r.package_id=t.package_id AND r.version=t.version""")
    if con.execute("SELECT EXISTS(SELECT package_id,version FROM service_result GROUP BY 1,2 HAVING count(*)<>1)").fetchone()[0]:
        raise ValueError("Duplicate version dependents output key")
    output_rows = con.execute("SELECT count(*) FROM service_result").fetchone()[0]
    if output_rows != con.execute("SELECT count(*) FROM input_version").fetchone()[0]:
        raise ValueError("Version dependents population mismatch")
    unresolved = con.execute("SELECT count(*) FROM declarations d JOIN lookup_intervals i USING(lookup_id) "
                             "WHERE i.status<>'RESOLVED'").fetchone()[0]
    source_gaps = dict(zip(("missing_requirements", "null_dependency_list", "extraction_error", "unknown_extraction_status"),
        con.execute("SELECT count(*) FILTER(WHERE NOT requirements_present),count(*) FILTER(WHERE selected_list_null),"
                    "count(*) FILTER(WHERE dependency_error=true),count(*) FILTER(WHERE dependency_error IS NULL) "
                    "FROM source_population").fetchone()))
    directory = output / "outputs"
    directory.mkdir()
    records = []
    for table, role in (("service_result", "version_dependents"), ("quality_result", "quality"),
                        ("lookup_intervals", "resolution_lookup")):
        path = directory / (role + ".parquet")
        con.execute(f"COPY {table} TO ? (FORMAT PARQUET,COMPRESSION ZSTD)", [str(path)])
        schema = [list(row[:2]) for row in con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]).fetchall()]
        records.append({"path": path.name, "role": role, "schema": schema,
                        "row_count": con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]})
    quality = {"calculation_status": "COMPLETE", "resolution_status": "PARTIAL" if unresolved or any(source_gaps.values()) else "COMPLETE",
               "unresolved_declarations": unresolved, "source_gaps": source_gaps,
               "population": prepared["statistics"], "resolution": resolution, "aggregation": aggregation,
               "rows": output_rows, "zero_rows": con.execute("SELECT count(*) FROM service_result WHERE dependents_count=0").fetchone()[0],
               "null_rows": con.execute("SELECT count(*) FROM service_result WHERE dependents_count IS NULL").fetchone()[0],
               "runtime": metadata, "snapshot_count": 1}
    return directory, records, quality


def execute_stage(request, completed, s3, work_dir):
    if request.get("options", {}).get("dependents_engine", "parallel") == "parallel":
        return _execute_parallel_stage(request, completed, s3, work_dir)
    workers = request.get("options", {}).get("workers", 2)
    prefix = f"{PREFIX}/snapshot={request['snapshot']}/run_id={request['run_id']}"
    identity = {"request": request, "population_manifest_sha256": completed["package_version"]["manifest_sha256"]}
    root = Path(work_dir) / "dependents"
    root.mkdir(parents=True, exist_ok=True)
    manifest_key = prefix + "/run_manifest.json"
    existing = read_optional(s3, BUCKET, manifest_key)
    if existing is not None:
        body = existing[0]
        manifest = json.loads(body)
        if manifest.get("identity") != identity or manifest.get("status") != "PASSED":
            raise ValueError("Dependents run input identity differs")
        verify_files(s3, BUCKET, manifest["files"], workers=workers)
    else:
        files = {}
        for table in ("requirements", "versions_full"):
            from pipeline.preprocessing.orchestration.contracts import version_table
            ref = request["raw_refs"][version_table(request) if table == "versions_full" else table]
            raw = json.loads(pinned(s3, ref))
            files[table] = download_files(s3, ref["bucket"], raw["files"], root / "cache", workers=workers)
        population = completed["package_version"]
        for table in ("package", "version"):
            records = [row for row in population["files"] if f"/{table}/data/" in row["key"]]
            if not records:
                raise ValueError("Missing Curated population files: " + table)
            files[table] = download_files(s3, BUCKET, records, root / "cache", workers=workers)
        from pipeline.preprocessing.orchestration.intake import hydrate_ref
        files["targets"] = hydrate_ref(s3, request["targets"]["dependents"], root / "targets.parquet")
        attempt = root / ("attempt-" + uuid.uuid4().hex)
        attempt.mkdir()
        options = request.get("options", {})
        with duckdb.connect(str(attempt / "working.duckdb"), config={
                "threads": options.get("threads", 2), "memory_limit": options.get("memory_limit", "2GB")}) as con:
            con.execute("SET TimeZone='UTC'")
            con.execute("SET preserve_insertion_order=false")
            con.execute("SET temp_directory=?", [str(attempt / "scratch")])
            directory, schemas, quality = calculate(con, files=files, snapshot=request["snapshot"],
                snapshot_timestamp=request["snapshot_timestamp"], output=attempt)
        records = upload_outputs(s3, BUCKET, prefix + "/attempts/" + attempt.name, directory, workers=workers)
        for record in records:
            schema = next(row for row in schemas if record["key"].endswith("/" + row["path"]))
            record.update(schema)
        manifest = {"format_version": 1, "dataset": "version-dependents-single", "status": "PASSED",
                    "identity": identity, "run_id": request["run_id"], "snapshot": request["snapshot"],
                    "files": records, "quality": quality, "db_loaded": False,
                    "metric": "DISTINCT_SOURCE_PACKAGE_VERSION_PER_TARGET_VERSION_AND_SNAPSHOT",
                    "dependency_kind": "dependencies"}
        body = json_bytes(manifest)
        put_immutable(s3, BUCKET, manifest_key, body)
    marker = json_bytes({"manifest_sha256": sha(body)})
    put_immutable(s3, BUCKET, prefix + "/_SUCCESS", marker)
    return {"stage": "dependents", "run_id": request["run_id"], "snapshot": request["snapshot"],
            "bucket": BUCKET, "prefix": prefix, "manifest_key": manifest_key, "manifest_sha256": sha(body),
            "marker_key": prefix + "/_SUCCESS", "marker_sha256": sha(marker), "files": manifest["files"],
            "quality": manifest["quality"], "metadata": {"snapshot_count": 1}}


def _execute_parallel_stage(request, completed, s3, work_dir):
    """Run the durable weighted CPU coordinator and publish the same stage contract."""
    from pipeline.preprocessing.orchestration.dependents_parallel import calculate
    options = request.get("options", {})
    threads = options.get("threads", 2)
    workers = options.get("dependents_workers", min(2, threads))
    io_workers = options.get("workers", 2)
    memory_limit = options.get("memory_limit", "2GB")
    max_temp_size = options.get("dependents_max_temp_size", "100GB")
    prefix = f"{PREFIX}/snapshot={request['snapshot']}/run_id={request['run_id']}"
    identity = {"request": request, "population_manifest_sha256": completed["package_version"]["manifest_sha256"]}
    root = Path(work_dir) / "dependents"
    root.mkdir(parents=True, exist_ok=True)
    manifest_key = prefix + "/run_manifest.json"
    existing = read_optional(s3, BUCKET, manifest_key)
    if existing is None:
        files = {}
        for table in ("requirements", "versions_full"):
            from pipeline.preprocessing.orchestration.contracts import version_table
            ref = request["raw_refs"][version_table(request) if table == "versions_full" else table]
            raw = json.loads(pinned(s3, ref)); files[table] = download_files(s3, ref["bucket"], raw["files"], root / "cache", workers=io_workers)
        population = completed["package_version"]
        for table in ("package", "version"):
            records = [row for row in population["files"] if f"/{table}/data/" in row["key"]]
            if not records: raise ValueError("Missing Curated population files: " + table)
            files[table] = download_files(s3, BUCKET, records, root / "cache", workers=io_workers)
        from pipeline.preprocessing.orchestration.intake import hydrate_ref
        files["targets"] = hydrate_ref(s3, request["targets"]["dependents"], root / "targets.parquet")
        attempt = root / "parallel-attempt"
        attempt.mkdir(exist_ok=True)
        directory, schemas, quality = calculate(
            files=files, snapshot=request["snapshot"], snapshot_timestamp=request["snapshot_timestamp"],
            output=attempt, workers=workers, threads=threads,
            memory_limit=memory_limit, max_temp_size=max_temp_size)
        records = upload_outputs(s3, BUCKET, prefix + "/attempts/parallel", directory, workers=io_workers)
        for record in records:
            schema = next(row for row in schemas if record["key"].endswith("/" + row["path"])); record.update(schema)
        manifest = {"format_version": 1, "dataset": "version-dependents-single", "status": "PASSED", "identity": identity, "run_id": request["run_id"], "snapshot": request["snapshot"], "files": records, "quality": quality, "db_loaded": False, "metric": "DISTINCT_SOURCE_PACKAGE_VERSION_PER_TARGET_VERSION_AND_SNAPSHOT", "dependency_kind": "dependencies", "engine": "historical_parallel_cpu_weighted"}
        body = json_bytes(manifest); put_immutable(s3, BUCKET, manifest_key, body)
    else:
        body = existing[0]; manifest = json.loads(body)
        if manifest.get("identity") != identity or manifest.get("status") != "PASSED": raise ValueError("Dependents run input identity differs")
        verify_files(s3, BUCKET, manifest["files"], workers=io_workers)
    marker = json_bytes({"manifest_sha256": sha(body)}); put_immutable(s3, BUCKET, prefix + "/_SUCCESS", marker)
    return {"stage": "dependents", "run_id": request["run_id"], "snapshot": request["snapshot"], "bucket": BUCKET, "prefix": prefix, "manifest_key": manifest_key, "manifest_sha256": sha(body), "marker_key": prefix + "/_SUCCESS", "marker_sha256": sha(marker), "files": manifest["files"], "quality": manifest["quality"], "metadata": {"snapshot_count": 1, "engine": "historical_parallel_cpu_weighted"}}
