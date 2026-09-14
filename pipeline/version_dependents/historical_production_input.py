"""Pinned, target-scoped production input without reducing the source universe."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import re
import shutil
import time

import duckdb

from pipeline.requirements_resolution.input import file_sha256
from pipeline.requirements_resolution.policy import canonical_bytes, sha256
from .artifact import _validate_sha
from .historical_artifact import _path, _publish_json, _read_json
from .historical_cache import _calendar, _record
from .historical_input import verify_historical_inputs
from .historical_profile import _contract as profile_contract, _inputs


FORMAT = "historical-production-input-v1"
TABLES = ("target_names", "target_population", "lookups", "declarations")
POLICY = {
    "source": "ALL_H1_ELIGIBLE_SOURCE_VERSIONS_REFERENCING_SELECTED_TARGETS",
    "target": "EXACT_DOWNLOAD_SELECTION_NAMES_ALL_H1_ELIGIBLE_VERSIONS",
    "kind": "dependencies", "null_publication": "EXCLUDED_BY_H1",
    "metric": "DISTINCT_SOURCE_PACKAGE_VERSION_PER_TARGET_VERSION_AND_SNAPSHOT",
    "unresolved": "PRESERVE_PARTIAL", "upstream_resolution_status": "PARTIAL",
    "partition": "SHA256_UTF8_NAME_FIRST_16_HEX_MOD_N",
}


def contract():
    return {"input_adapter_sha256": file_sha256(Path(__file__)),
            "profile_generation": profile_contract(), "duckdb_version": duckdb.__version__}


def partition_for(name, partitions):
    if type(partitions) is not int or not 1 <= partitions <= 256:
        raise ValueError("partition_count must be 1..256")
    if not isinstance(name, str) or not name or name != name.strip() or "\x00" in name:
        raise ValueError("Invalid target name")
    return int(hashlib.sha256(name.encode("utf-8")).hexdigest()[:16], 16) % partitions


def selection(path, expected_sha256, *, sample_names=None, full_selected=False):
    path = _path(path)
    _validate_sha(expected_sha256, "selection CSV SHA")
    if file_sha256(path) != expected_sha256:
        raise ValueError("Selection CSV SHA mismatch")
    if full_selected == (sample_names is not None):
        raise ValueError("Choose explicit sample_names or full_selected=True")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if "name" not in (reader.fieldnames or []):
            raise ValueError("Selection CSV requires name")
        names = [row["name"] for row in reader]
    for name in names:
        partition_for(name, 1)
    unique = sorted(set(names))
    if not unique:
        raise ValueError("Empty target selection")
    if sample_names is not None:
        if (not isinstance(sample_names, list) or not sample_names or len(sample_names) > 32
                or any(not isinstance(name, str) for name in sample_names)
                or len(sample_names) != len(set(sample_names))):
            raise ValueError("Explicit sample must contain 1..32 unique names")
        if not set(sample_names) <= set(unique):
            raise ValueError("Sample contains a name outside the pinned selection")
        chosen = sorted(sample_names)
    else:
        chosen = unique
    return chosen, {"path": str(path), "sha256": expected_sha256,
                    "csv_rows": len(names), "unique_names": len(unique),
                    "unique_names_sha256": sha256(unique),
                    "chosen_names": chosen if sample_names is not None else None,
                    "chosen_count": len(chosen), "chosen_names_sha256": sha256(chosen)}


def connection(path, *, threads=4, memory_limit="4GB", max_temp_size="40GB"):
    if type(threads) is not int or not 1 <= threads <= 8:
        raise ValueError("Use 1..8 threads")
    for value in (memory_limit, max_temp_size):
        if not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]*(?:MB|GB)", value):
            raise ValueError("Explicit memory/temp size in MB or GB is required")
    path = _path(path)
    con = duckdb.connect(str(path), config={"threads": threads, "memory_limit": memory_limit})
    con.execute("SET TimeZone='UTC'")
    con.execute("SET enable_progress_bar=false")
    con.execute("SET preserve_insertion_order=false")
    con.execute("SET temp_directory=?", [str(path.parent / (path.stem + "-scratch"))])
    con.execute("SET max_temp_directory_size=?", [max_temp_size])
    return con


def event(output, phase, **values):
    with (Path(output) / "progress.jsonl").open("ab") as stream:
        stream.write(canonical_bytes({"at_unix": time.time(), "phase": phase, **values}))


def _verify_used_raw(raw):
    paths = {str(Path(p).resolve()) for table in ("requirements", "package") for p in raw["files"][table]}
    records = {str(Path(r["path"]).resolve()): r for r in raw["file_records"]}
    if not paths <= records.keys():
        raise ValueError("Used raw file is absent from pinned inventory")
    for name in sorted(paths):
        record = records[name]
        path = _path(name)
        if path.stat().st_size != record["bytes"] or file_sha256(path) != record["sha256"]:
            raise ValueError("Used raw input changed: " + name)
    return len(paths)


def _verify_profile(path, expected_sha, h1_sha):
    path = _path(path)
    _validate_sha(expected_sha, "profile manifest SHA")
    if file_sha256(path) != expected_sha:
        raise ValueError("Profile manifest SHA mismatch")
    manifest = _read_json(path)
    if (manifest.get("profile_status") != "COMPLETE"
            or manifest.get("input_manifest_sha256") != h1_sha
            or manifest.get("generation_contract") != profile_contract()):
        raise ValueError("Profile status, H1 input, or generation contract mismatch")
    if (len(manifest.get("files", [])) != 2 or {r["name"] for r in manifest["files"]}
            != {"lookup_workload.parquet", "package_workload.parquet"}):
        raise ValueError("Profile output inventory must contain exactly two files")
    for record in manifest["files"]:
        file = path.parent / record["name"]
        if record["name"] not in {"lookup_workload.parquet", "package_workload.parquet"}:
            raise ValueError("Unexpected profile output")
        if file.stat().st_size != record["bytes"] or file_sha256(file) != record["sha256"]:
            raise ValueError("Profile output SHA mismatch")
    return manifest


def prepare_tables(con, names, *, partition_count):
    """Use already pinned H1/raw/profile views; keep every matching source version."""
    payload = [{"name": name, "partition_id": partition_for(name, partition_count)} for name in names]
    con.execute("CREATE TEMP TABLE selected AS SELECT unnest(from_json(?,?), recursive:=true)",
                [json.dumps(payload), '[{"name":"VARCHAR","partition_id":"INTEGER"}]'])
    con.execute("""CREATE TEMP TABLE target_names AS
        SELECT s.name, s.partition_id, p.package_id::INTEGER AS package_id,
               (p.package_id IS NOT NULL) AS known_package,
               coalesce(w.lookup_count,0)::BIGINT AS expected_lookups,
               coalesce(w.declaration_count,0)::BIGINT AS expected_declarations,
               coalesce(w.candidate_count,0)::BIGINT AS candidate_count
        FROM selected s LEFT JOIN input_package p ON s.name=p.name
        LEFT JOIN package_workload w ON s.name=w.name""")
    if con.execute("SELECT count(*) FROM target_names").fetchone()[0] != len(names):
        raise ValueError("Target name mapping is not unique")
    con.execute("""CREATE TEMP TABLE target_population AS
        SELECT t.package_id,t.name,t.version,t.birth_index,s.partition_id
        FROM h1_targets t JOIN selected s ON t.name=s.name""")
    con.execute("""CREATE TEMP TABLE lookups AS
        SELECT l.lookup_id,l.declared_name,l.requirement,l.declaration_count,
               l.first_source_birth,s.partition_id
        FROM lookup_workload l JOIN selected s ON l.declared_name=s.name""")
    con.execute("""CREATE TEMP TABLE declarations AS
        WITH expanded AS (
            SELECT r.Name AS source_name,r.Version AS source_version,
                   unnest(r.Dependencies) AS item,
                   (generate_subscripts(r.Dependencies,1)-1)::BIGINT AS original_declaration_index
            FROM input_requirements r
        ), requested AS (
            SELECT e.source_name,e.source_version,e.original_declaration_index,
                   e.item.Name AS declared_name,e.item.Requirement AS requirement,t.partition_id
            FROM expanded e JOIN selected t ON e.item.Name=t.name
        )
        SELECT s.source_package_id,s.source_version,s.source_name,s.birth_index,s.dependency_error,
               r.original_declaration_index,r.declared_name,r.requirement,l.lookup_id,r.partition_id
        FROM requested r JOIN source_population s
          ON r.source_name=s.source_name AND r.source_version=s.source_version
        LEFT JOIN lookups l ON r.declared_name=l.declared_name
                     AND r.requirement IS NOT DISTINCT FROM l.requirement""")
    if con.execute("SELECT count(*) FROM declarations WHERE lookup_id IS NULL").fetchone()[0]:
        raise ValueError("Raw declaration is absent from the pinned H5-A lookups")
    if con.execute("""SELECT EXISTS(SELECT 1 FROM declarations
        GROUP BY source_package_id,source_version,original_declaration_index HAVING count(*)<>1)""").fetchone()[0]:
        raise ValueError("Duplicate original declaration identity")
    if con.execute("""WITH actual AS (SELECT lookup_id,count(*) AS n FROM declarations GROUP BY 1)
        SELECT EXISTS(SELECT 1 FROM lookups l FULL JOIN actual a USING(lookup_id)
        WHERE l.lookup_id IS NULL OR coalesce(a.n,0)<>l.declaration_count)""").fetchone()[0]:
        raise ValueError("Source declarations do not conserve the pinned H5-A lookup counts")
    if con.execute("""WITH actual AS (SELECT name,count(*) AS n FROM target_population GROUP BY 1)
        SELECT EXISTS(SELECT 1 FROM target_names t LEFT JOIN actual a USING(name)
        WHERE coalesce(a.n,0)<>t.candidate_count)""").fetchone()[0]:
        raise ValueError("Candidate population differs from the pinned H5-A profile")
    if con.execute("""WITH actual AS (SELECT declared_name AS name,count(*) AS n,
                                      sum(declaration_count) AS d FROM lookups GROUP BY 1)
        SELECT EXISTS(SELECT 1 FROM target_names t LEFT JOIN actual a USING(name)
        WHERE coalesce(a.n,0)<>t.expected_lookups OR coalesce(a.d,0)<>t.expected_declarations)""").fetchone()[0]:
        raise ValueError("Lookup and package workload totals differ")
    return {table: con.execute("SELECT count(*) FROM " + table).fetchone()[0] for table in TABLES}


def prepare(*, h1_dir, h1_manifest_sha256, profile_manifest, profile_manifest_sha256,
            selection_csv, selection_sha256, output, sample_names=None, full_selected=False,
            partition_count=128, threads=4, memory_limit="4GB", max_temp_size="40GB",
            min_free_bytes=20_000_000_000):
    started = time.monotonic()
    partition_for("validation", partition_count)
    names, selected = selection(selection_csv, selection_sha256,
                                sample_names=sample_names, full_selected=full_selected)
    h1_dir, output = _path(h1_dir), _path(output)
    h1, raw = _inputs(h1_dir, h1_manifest_sha256)
    profile_path = _path(profile_manifest)
    _verify_profile(profile_path, profile_manifest_sha256, h1_manifest_sha256)
    protected = [h1_dir, profile_path.parent, _path(selection_csv),
                 *[_path(p) for p in raw["sources"].values()]]
    if any(output.is_relative_to(p) or p.is_relative_to(output) for p in protected):
        raise ValueError("Preparation output overlaps a pinned input")
    if type(min_free_bytes) is not int or min_free_bytes < 0:
        raise ValueError("Invalid free disk guard")
    ancestor = output.parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    if shutil.disk_usage(ancestor).free < min_free_bytes:
        raise ValueError("Insufficient free disk before preparation")
    output.mkdir(parents=True, exist_ok=False)
    generation = contract()
    plan = {"format": FORMAT, "scope": "FULL_SELECTED" if full_selected else "SAMPLE",
            "h1_dir": str(h1_dir), "h1_manifest_sha256": h1_manifest_sha256,
            "profile_manifest": str(profile_path), "profile_manifest_sha256": profile_manifest_sha256,
            "selection": selected, "partition_count": partition_count, "policy": POLICY,
            "generation_contract": generation, "ready_for_load": False}
    _publish_json(output / "input_plan.json", plan)
    event(output, "VERIFY_PINNED_INPUTS")
    verify_historical_inputs(h1_dir, h1_manifest_sha256)
    raw_count = _verify_used_raw(raw)
    with connection(output / "preparation.duckdb", threads=threads, memory_limit=memory_limit,
                    max_temp_size=max_temp_size) as con:
        con.read_parquet(str(h1_dir / "source_population.parquet"), hive_partitioning=False).create_view("source_population")
        con.read_parquet(str(h1_dir / "target_population.parquet"), hive_partitioning=False).create_view("h1_targets")
        con.read_parquet(raw["files"]["requirements"], hive_partitioning=False).create_view("input_requirements")
        con.read_parquet(raw["files"]["package"], hive_partitioning=False).create_view("input_package")
        for table in ("lookup_workload", "package_workload"):
            con.read_parquet(str(profile_path.parent / (table + ".parquet")), hive_partitioning=False).create_view(table)
        calendar = [{"snapshot_at": day, "snapshot_timestamp": stamp} for day, stamp in con.execute(
            "SELECT snapshot_at::VARCHAR,strftime(snapshot_timestamp AT TIME ZONE 'UTC',"
            "'%Y-%m-%dT%H:%M:%S.%fZ') FROM read_parquet(?,hive_partitioning=false) ORDER BY snapshot_index",
            [str(h1_dir / "calendar.parquet")]).fetchall()]
        event(output, "EXTRACT_SELECTED_DECLARATIONS", target_names=len(names))
        counts = prepare_tables(con, names, partition_count=partition_count)
        event(output, "WRITE_PREPARED_INPUTS", rows=counts)
        orders = {"target_names": "partition_id,name", "target_population": "partition_id,name,birth_index,version",
                  "lookups": "partition_id,lookup_id",
                  "declarations": "partition_id,source_package_id,source_version,original_declaration_index"}
        for table in TABLES:
            con.execute(f"COPY (SELECT * FROM {table} ORDER BY {orders[table]}) TO ? (FORMAT PARQUET,COMPRESSION ZSTD)",
                        [str(output / (table + ".parquet"))])
    event(output, "REVERIFY_PINNED_INPUTS")
    _verify_used_raw(raw)
    verify_historical_inputs(h1_dir, h1_manifest_sha256)
    _verify_profile(profile_path, profile_manifest_sha256, h1_manifest_sha256)
    if file_sha256(_path(selection_csv)) != selection_sha256 or contract() != generation:
        raise ValueError("Selection or generation code changed during preparation")
    manifest = {**plan, "preparation_status": "COMPLETE", "count_status": "NOT_COMPUTED",
                "calendar": calendar, "observed_snapshot_timestamp": h1["observed_snapshot_timestamp"],
                "input_plan_sha256": file_sha256(output / "input_plan.json"),
                "files": [_record(output / (table + ".parquet")) for table in TABLES],
                "rows": counts, "verified_raw_files": raw_count,
                "elapsed_seconds": time.monotonic() - started}
    _publish_json(output / "input_manifest.json", manifest)
    event(output, "PREPARATION_COMPLETE", rows=counts)
    return {"prepared_dir": str(output), "manifest_sha256": file_sha256(output / "input_manifest.json"),
            "scope": plan["scope"], "rows": counts, "elapsed_seconds": manifest["elapsed_seconds"]}


def verify_inputs(prepared_dir, manifest_sha256):
    root = _path(prepared_dir)
    _validate_sha(manifest_sha256, "production input manifest SHA")
    path = root / "input_manifest.json"
    if file_sha256(path) != manifest_sha256:
        raise ValueError("Production input manifest SHA mismatch")
    manifest = _read_json(path)
    if (manifest.get("format") != FORMAT or manifest.get("preparation_status") != "COMPLETE"
            or manifest.get("count_status") != "NOT_COMPUTED"
            or manifest.get("scope") not in {"SAMPLE", "FULL_SELECTED"}
            or manifest.get("policy") != POLICY or manifest.get("generation_contract") != contract()
            or manifest.get("ready_for_load") is not False):
        raise ValueError("Production input contract mismatch")
    if file_sha256(root / "input_plan.json") != manifest["input_plan_sha256"]:
        raise ValueError("Production input plan SHA mismatch")
    plan = _read_json(root / "input_plan.json")
    if any(manifest.get(key) != value for key, value in plan.items()):
        raise ValueError("Production input manifest differs from its plan")
    _calendar(manifest["calendar"], manifest["observed_snapshot_timestamp"])
    names = {table + ".parquet" for table in TABLES}
    if len(manifest["files"]) != len(names) or {r["name"] for r in manifest["files"]} != names:
        raise ValueError("Production input file inventory mismatch")
    for record in manifest["files"]:
        if manifest["rows"].get(record["name"].removesuffix(".parquet")) != record["rows"]:
            raise ValueError("Production input row summary differs from file inventory")
        if _record(_path(root / record["name"])) != record:
            raise ValueError("Production input file changed: " + record["name"])
    with duckdb.connect(config={"threads": 2, "memory_limit": "1GB"}) as con:
        actual = con.execute("SELECT name,partition_id FROM read_parquet(?,hive_partitioning=false) ORDER BY name",
                             [str(root / "target_names.parquet")]).fetchall()
    names = [row[0] for row in actual]
    selected = manifest["selection"]
    if (len(names) != len(set(names)) or len(names) != selected["chosen_count"]
            or sha256(names) != selected["chosen_names_sha256"]
            or (manifest["scope"] == "SAMPLE" and sorted(selected["chosen_names"]) != names)
            or any(part != partition_for(name, manifest["partition_count"]) for name, part in actual)):
        raise ValueError("Prepared target-name coverage/partition differs from selection")
    return manifest


def open_inputs(con, prepared_dir, manifest):
    root = _path(prepared_dir)
    for table in TABLES:
        con.read_parquet(str(root / (table + ".parquet")), hive_partitioning=False).create_view(table)
