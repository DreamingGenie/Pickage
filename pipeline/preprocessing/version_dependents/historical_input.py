"""Prepare pinned historical populations without resolving or publishing counts."""
from __future__ import annotations
from pipeline.preprocessing.common.paths import REPO_ROOT

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys
import time

import duckdb

from pipeline.preprocessing.requirements_resolution.bridge import NodeSession, discover_runtime
from pipeline.preprocessing.requirements_resolution.input import RAW_SCHEMAS, TABLES, _plain_path, file_sha256, reverify_inputs
from pipeline.preprocessing.requirements_resolution.policy import canonical_bytes, sha256
from pipeline.preprocessing.common.curated_input import SCHEMAS, schema as _schema
from pipeline.preprocessing.snapshot.policy import parse_timestamp


MODE = "HISTORICAL_RECONSTRUCTION_FROM_FIXED_INPUT"
OUTPUT_TABLES = ("calendar", "source_population", "target_population",
                 "snapshot_population", "semver_classification")
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _micros(stamp):
    delta = stamp - EPOCH
    return (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds


def load_calendar(path: Path, expected_sha256: str, observed_timestamp: str) -> list[dict]:
    path = Path(path)
    if file_sha256(path) != expected_sha256:
        raise ValueError("Calendar SHA mismatch")
    observed = parse_timestamp(observed_timestamp)
    document = json.loads(path.read_bytes())
    rows = document.get("calendar") if isinstance(document, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError("Calendar must be nonempty")
    result, seen_dates = [], set()
    previous = None
    for index, row in enumerate(rows):
        stamp = parse_timestamp(row["snapshot_timestamp"])
        day = stamp.date().isoformat()
        if (row.get("snapshot_at") != day or day in seen_dates
                or stamp > observed or (previous is not None and stamp <= previous)):
            raise ValueError("Calendar date/order/observation boundary mismatch")
        result.append({"snapshot_index": index, "snapshot_at": day,
                       "snapshot_timestamp": stamp.isoformat(timespec="microseconds").replace("+00:00", "Z"),
                       "timestamp_us": _micros(stamp)})
        seen_dates.add(day)
        previous = stamp
    return result


def _reject(con, sql, message, args=None):
    if con.execute("SELECT EXISTS (" + sql + ")", args or []).fetchone()[0]:
        raise ValueError(message)


def _unique(con, table, keys):
    columns = ",".join(keys)
    _reject(con, f"SELECT {columns} FROM {table} GROUP BY {columns} HAVING count(*)>1",
            "Duplicate input key: " + table)


def _validate_relations(con, observed_timestamp):
    expected = _micros(parse_timestamp(observed_timestamp))
    for table in ("input_version", "input_versions_full"):
        types = dict(row[:2] for row in con.execute("DESCRIBE " + table).fetchall())
        if types.get("published_at") != "TIMESTAMP":
            raise ValueError("Publication timestamp requires the pinned BigQuery naive-UTC adapter")
        _reject(con, f"SELECT 1 FROM {table} WHERE published_at IS NOT NULL AND NOT isfinite(published_at)",
                "Invalid non-finite publication timestamp")
    for table in ("input_requirements", "input_versions_full"):
        types = dict(row[:2] for row in con.execute("DESCRIBE " + table).fetchall())
        if types.get("SnapshotAt") != "TIMESTAMP":
            raise ValueError("Observation timestamp requires the pinned BigQuery naive-UTC adapter")
        _reject(con, f"SELECT 1 FROM {table} WHERE SnapshotAt IS NULL OR epoch_us(SnapshotAt)<>?",
                "Mixed, NULL, or wrong observed SnapshotAt", [expected])
        _reject(con, f"SELECT 1 FROM {table} WHERE Name IS NULL OR Version IS NULL",
                "Invalid raw identity")
        _unique(con, table, ["Name", "Version"])
    _reject(con, "SELECT 1 FROM input_package WHERE package_id IS NULL OR package_id<=0 "
            "OR name IS NULL OR length(trim(name))=0", "Invalid package identity")
    _reject(con, "SELECT 1 FROM input_version WHERE package_id IS NULL OR version IS NULL "
            "OR length(trim(version))=0", "Invalid version identity")
    _unique(con, "input_package", ["package_id"])
    _unique(con, "input_package", ["name"])
    _unique(con, "input_version", ["package_id", "version"])
    _reject(con, "SELECT 1 FROM input_version v ANTI JOIN input_package p USING(package_id)",
            "Orphan Curated version")


def _classify_versions(con, runtime, output):
    """Classify each original version string once with the unchanged npm worker."""
    con.execute("CREATE TABLE unique_versions AS SELECT DISTINCT version FROM version_basis")
    rows = con.cursor().execute("SELECT version FROM unique_versions")
    path = output / "semver-classification.jsonl"
    with NodeSession(runtime, output / "node.log") as node, path.open("x", encoding="utf-8") as stream:
        metadata = node.request({"op": "metadata"})
        while batch := rows.fetchmany(4096):
            versions = [row[0] for row in batch]
            node.request({"op": "start", "name": "population-classification"})
            result = node.request({"op": "candidates", "versions": versions})
            rejected = {row["version"]: row["reason"] for row in result["rejected"]}
            if result["accepted_total"] + len(rejected) != len(versions):
                raise ValueError("Semver classifier lost original versions")
            for version in versions:
                stream.write(json.dumps({"version": version,
                                         "target_status": rejected.get(version, "ELIGIBLE")},
                                        ensure_ascii=True) + "\n")
    rows.close()
    con.execute("CREATE TABLE semver_classification AS SELECT * FROM read_json(?, "
                "format='newline_delimited', columns={version:'VARCHAR',target_status:'VARCHAR'})", [str(path)])
    con.execute("DROP TABLE unique_versions")
    return metadata


def build_populations(con, calendar: list[dict], observed_timestamp: str, runtime: dict,
                      output: Path) -> dict:
    """Build relations from verified input_* tables; caller owns the connection."""
    _validate_relations(con, observed_timestamp)
    con.execute("CREATE TABLE calendar(snapshot_index INTEGER,snapshot_at DATE,"
                "snapshot_timestamp TIMESTAMPTZ,timestamp_us BIGINT)")
    con.executemany("INSERT INTO calendar VALUES (?,?,?,?)",
                    [(r["snapshot_index"], r["snapshot_at"], r["snapshot_timestamp"], r["timestamp_us"])
                     for r in calendar])
    con.execute("""CREATE TABLE version_basis AS
        SELECT v.package_id,p.name,v.version,v.published_at AS published_at_raw,
               v.published_at AT TIME ZONE 'UTC' AS published_at,
               epoch_us(v.published_at) AS published_at_us,r.dependency_error,
               r.Name AS raw_name,r.is_release,r.published_at AS raw_published_at
        FROM input_version v JOIN input_package p USING(package_id)
        LEFT JOIN input_versions_full r ON p.name=r.Name AND v.version=r.Version""")
    _reject(con, "SELECT 1 FROM version_basis WHERE raw_name IS NULL OR is_release IS DISTINCT FROM true "
            "OR published_at_raw IS DISTINCT FROM raw_published_at",
            "Curated version lacks matching raw release/date provenance")
    if not con.execute("SELECT count(*) FROM version_basis").fetchone()[0]:
        raise ValueError("Empty Curated population")
    runtime_metadata = _classify_versions(con, runtime, Path(output))
    con.execute("""CREATE TABLE version_birth AS
        SELECT v.package_id,v.name,v.version,v.published_at_raw,v.published_at,
               v.published_at_us,v.dependency_error,c.snapshot_index AS birth_index,
               s.target_status
        FROM version_basis v JOIN semver_classification s USING(version)
        ASOF LEFT JOIN calendar c ON v.published_at_us<=c.timestamp_us""")
    con.execute("""CREATE TABLE source_population AS
        SELECT v.package_id AS source_package_id,v.name AS source_name,v.version AS source_version,
               v.published_at_raw,v.published_at,v.published_at_us,v.birth_index,v.dependency_error,
               r.Name IS NOT NULL AS requirements_present,
               r.Name IS NOT NULL AND r.Dependencies IS NULL AS selected_list_null,
               coalesce(array_length(r.Dependencies),0)::BIGINT AS declaration_count,
               array_length(r.PeerDependencies)::BIGINT AS excluded_peer_count,
               array_length(r.OptionalDependencies)::BIGINT AS excluded_optional_count
        FROM version_birth v LEFT JOIN input_requirements r ON v.name=r.Name AND v.version=r.Version
        WHERE v.birth_index IS NOT NULL""")
    con.execute("""CREATE TABLE target_population AS
        SELECT package_id,name,version,published_at_raw,published_at,published_at_us,birth_index
        FROM version_birth WHERE birth_index IS NOT NULL AND target_status='ELIGIBLE'""")
    # Only one row per birth index is joined to the calendar. Never form version x calendar.
    con.execute("""CREATE TABLE source_birth_counts AS
        SELECT birth_index,count(*) AS source_versions,sum(declaration_count)::BIGINT AS declarations,
               count(*) FILTER(WHERE NOT requirements_present) AS missing_requirements_sources,
               count(*) FILTER(WHERE selected_list_null) AS null_dependency_list_sources,
               count(*) FILTER(WHERE dependency_error=true) AS error_sources,
               count(*) FILTER(WHERE dependency_error IS NULL) AS unknown_error_sources
        FROM source_population GROUP BY birth_index""")
    con.execute("CREATE TABLE target_birth_counts AS SELECT birth_index,count(*) AS target_versions "
                "FROM target_population GROUP BY birth_index")
    metrics = ["source_versions", "declarations", "missing_requirements_sources",
               "null_dependency_list_sources", "error_sources", "unknown_error_sources"]
    columns = ["sum(coalesce(s." + name + ",0)) OVER (ORDER BY c.snapshot_index)::BIGINT AS " + name
               for name in metrics]
    columns.append("sum(coalesce(t.target_versions,0)) OVER (ORDER BY c.snapshot_index)::BIGINT AS target_versions")
    con.execute("CREATE TABLE snapshot_population AS SELECT c.*, " + ",".join(columns) +
                " FROM calendar c LEFT JOIN source_birth_counts s ON c.snapshot_index=s.birth_index "
                "LEFT JOIN target_birth_counts t ON c.snapshot_index=t.birth_index ORDER BY c.snapshot_index")
    summary = dict(zip(("curated_versions", "null_publication_versions", "after_last_snapshot_versions",
                        "eligible_sources", "eligible_targets", "prerelease_targets_excluded",
                        "invalid_semver_targets_excluded"), con.execute("""SELECT count(*),
        count(*) FILTER(WHERE published_at_us IS NULL),
        count(*) FILTER(WHERE published_at_us IS NOT NULL AND birth_index IS NULL),
        count(*) FILTER(WHERE birth_index IS NOT NULL),
        count(*) FILTER(WHERE birth_index IS NOT NULL AND target_status='ELIGIBLE'),
        count(*) FILTER(WHERE birth_index IS NOT NULL AND target_status='PRERELEASE_TARGET'),
        count(*) FILTER(WHERE birth_index IS NOT NULL AND target_status='INVALID_TARGET_SEMVER')
        FROM version_birth""").fetchone()))
    summary["dense_target_snapshot_keys"] = con.execute(
        "SELECT sum(target_versions)::BIGINT FROM snapshot_population").fetchone()[0]
    summary["source_snapshot_keys"] = con.execute(
        "SELECT sum(source_versions)::BIGINT FROM snapshot_population").fetchone()[0]
    summary["selected_declarations_latest"] = con.execute(
        "SELECT coalesce(sum(declaration_count),0)::BIGINT FROM source_population").fetchone()[0]
    summary["unique_original_version_strings"] = con.execute(
        "SELECT count(*) FROM semver_classification").fetchone()[0]
    if summary["curated_versions"] != sum(summary[k] for k in (
            "null_publication_versions", "after_last_snapshot_versions", "eligible_sources")):
        raise ValueError("Source population conservation failure")
    if summary["eligible_sources"] != sum(summary[k] for k in (
            "eligible_targets", "prerelease_targets_excluded", "invalid_semver_targets_excluded")):
        raise ValueError("Target population conservation failure")
    independent_dense = con.execute("SELECT coalesce(sum(?-birth_index),0)::BIGINT FROM target_population",
                                    [len(calendar)]).fetchone()[0]
    if independent_dense != summary["dense_target_snapshot_keys"]:
        raise ValueError("Birth intervals and dense key totals disagree")
    return {"statistics": summary, "runtime": runtime_metadata}


def _inspect_inputs(con, prepared):
    for table in TABLES:
        files = prepared["files"][table]
        for path in files:
            if table in ("package", "version"):
                _schema(con, Path(path), table, SCHEMAS)
            else:
                actual = [(r[0], r[1].upper().replace('"', '')) for r in con.execute(
                    "DESCRIBE SELECT * FROM read_parquet(?,hive_partitioning=false)", [path]).fetchall()]
                expected = [(n, t.upper().replace('"', '')) for n, t in RAW_SCHEMAS[table]]
                if actual != expected:
                    raise ValueError("Raw schema mismatch: " + table)
        con.read_parquet(files, hive_partitioning=False).create_view("input_" + table)
        actual_rows = con.execute("SELECT count(*) FROM input_" + table).fetchone()[0]
        if actual_rows != prepared["counts"][table]:
            raise ValueError("Parquet rows differ from pinned input manifest")


def _event(path, phase, **details):
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(),
                                 "phase": phase, **details}, ensure_ascii=True) + "\n")


def verify_historical_inputs(output: Path, manifest_sha256: str) -> dict:
    """Independently read pinned Parquet and compare birth histograms with every date."""
    output = Path(output).resolve()
    manifest_path = output / "input_manifest.json"
    if file_sha256(manifest_path) != manifest_sha256:
        raise ValueError("Historical input manifest SHA mismatch")
    manifest = json.loads(manifest_path.read_bytes())
    if (manifest.get("dataset") != "version-dependents-historical-input"
            or manifest.get("preparation_status") != "COMPLETE"
            or manifest.get("count_status") != "NOT_COMPUTED"
            or manifest.get("ready_for_load") is not False
            or manifest.get("policy_sha256") != sha256(manifest.get("policy"))):
        raise ValueError("Historical population status/policy contract mismatch")
    names = {table + ".parquet" for table in OUTPUT_TABLES}
    if ({p.name for p in output.glob("*.parquet")} != names
            or {r["path"] for r in manifest["files"]} != names
            or len(manifest["files"]) != len(names)):
        raise ValueError("Historical population file set mismatch")
    with duckdb.connect(config={"threads": 4, "memory_limit": "4GB"}) as con:
        con.execute("SET TimeZone='UTC'")
        con.execute("SET enable_progress_bar=false")
        for record in manifest["files"]:
            path = _plain_path(output / record["path"], output)
            if path.stat().st_size != record["bytes"] or file_sha256(path) != record["sha256"]:
                raise ValueError("Historical population file changed")
            table = path.stem
            con.read_parquet(str(path), hive_partitioning=False).create_view(table)
            actual = [list(r[:2]) for r in con.execute("DESCRIBE " + table).fetchall()]
            if (actual != record["schema"] or
                    con.execute("SELECT count(*) FROM " + table).fetchone()[0] != record["rows"]):
                raise ValueError("Historical population schema/row mismatch")
        calendar = con.execute("SELECT snapshot_index,epoch_us(snapshot_timestamp),timestamp_us "
                               "FROM calendar ORDER BY snapshot_index").fetchall()
        n = manifest["snapshot_count"]
        if (len(calendar) != n or [r[0] for r in calendar] != list(range(n))
                or any(r[1] != r[2] for r in calendar)):
            raise ValueError("Invalid stored calendar")
        totals = {}
        for table in ("source_population", "target_population"):
            _reject(con, f"""SELECT 1 FROM {table} p LEFT JOIN calendar c ON p.birth_index=c.snapshot_index
                LEFT JOIN calendar prev ON prev.snapshot_index=p.birth_index-1
                WHERE c.snapshot_index IS NULL OR p.published_at_us IS NULL
                OR epoch_us(p.published_at) IS DISTINCT FROM p.published_at_us
                OR epoch_us(p.published_at_raw) IS DISTINCT FROM p.published_at_us
                OR p.published_at_us>c.timestamp_us
                OR (prev.timestamp_us IS NOT NULL AND p.published_at_us<=prev.timestamp_us)""",
                    "Publication/birth boundary mismatch")
            histogram = dict(con.execute("SELECT birth_index,count(*) FROM " + table + " GROUP BY birth_index").fetchall())
            totals[table] = [sum(count for born, count in histogram.items() if born <= i) for i in range(n)]
        rows = con.execute("SELECT snapshot_index,source_versions,target_versions FROM snapshot_population "
                           "ORDER BY snapshot_index").fetchall()
        expected = [(i, totals["source_population"][i], totals["target_population"][i]) for i in range(n)]
        if rows != expected:
            raise ValueError("Snapshot population differs from independent birth histogram")
        stats = manifest["statistics"]
        if (sum(totals["target_population"]) != stats["dense_target_snapshot_keys"]
                or totals["target_population"][-1] != stats["eligible_targets"]
                or totals["source_population"][-1] != stats["eligible_sources"]):
            raise ValueError("Population manifest statistics mismatch")
    return {"snapshots_verified": n, "dense_target_snapshot_keys": stats["dense_target_snapshot_keys"],
            "ready_for_load": False, "verification_scope": "LOCAL_POPULATION_ARTIFACT"}


def prepare_historical_inputs(*, input_manifest, input_manifest_sha256, calendar_path,
                              calendar_sha256, output, runtime=None, threads=8,
                              memory_limit="8GB", max_temp_size="100GB", expected_snapshot_count=229):
    started = time.monotonic()
    manifest_path, calendar_path, output = map(Path, (input_manifest, calendar_path, output))
    if file_sha256(manifest_path) != input_manifest_sha256:
        raise ValueError("Input manifest SHA mismatch")
    prepared = json.loads(manifest_path.read_bytes())
    observed = prepared["snapshot_timestamp"]
    calendar = load_calendar(calendar_path, calendar_sha256, observed)
    if (type(expected_snapshot_count) is not int or expected_snapshot_count < 1
            or len(calendar) != expected_snapshot_count
            or calendar[-1]["timestamp_us"] != _micros(parse_timestamp(observed))):
        raise ValueError("Expected calendar count or latest observation boundary mismatch")
    output = _plain_path(output, output)
    sources = [Path(value).resolve() for value in prepared["sources"].values()]
    if any(output.is_relative_to(root) or root.is_relative_to(output) for root in sources):
        raise ValueError("Output overlaps original input")
    if output == manifest_path.parent.resolve() or manifest_path.resolve().is_relative_to(output):
        raise ValueError("Output overlaps input manifest")
    if type(threads) is not int or not 1 <= threads <= 8:
        raise ValueError("Use 1..8 threads")
    runtime = runtime or discover_runtime()
    output.mkdir(parents=True, exist_ok=False)
    free_bytes = shutil.disk_usage(output).free
    progress = output / "progress.jsonl"
    _event(progress, "VERIFY_PINNED_INPUT", input_bytes=sum(r["bytes"] for r in prepared["file_records"]))
    reverify_inputs(prepared)
    before = {r["path"]: (Path(r["path"]).stat().st_size, Path(r["path"]).stat().st_mtime_ns)
              for r in prepared["file_records"]}
    pipeline = (REPO_ROOT / 'pipeline')
    code_files = [Path(__file__), *(pipeline / path for path in (
        "preprocessing/requirements_resolution/semver_worker.cjs", "preprocessing/requirements_resolution/bridge.py",
        "preprocessing/requirements_resolution/input.py", "preprocessing/requirements_resolution/policy.py",
        "preprocessing/snapshot/policy.py", "preprocessing/common/curated_input.py"))]
    code_hashes = {str(p.resolve()): file_sha256(p) for p in code_files}
    with duckdb.connect(str(output / "working.duckdb"), config={"threads": threads,
                        "memory_limit": memory_limit}) as con:
        con.execute("SET TimeZone='UTC'")
        con.execute("SET enable_progress_bar=false")
        con.execute("SET preserve_insertion_order=false")
        con.execute("SET temp_directory=?", [str(output / "scratch")])
        con.execute("SET max_temp_directory_size=?", [max_temp_size])
        _inspect_inputs(con, prepared)
        _event(progress, "BUILD_POPULATIONS")
        result = build_populations(con, calendar, observed, runtime, output)
        _event(progress, "WRITE_POPULATIONS", statistics=result["statistics"])
        records = []
        for table in OUTPUT_TABLES:
            path = output / (table + ".parquet")
            con.execute("COPY " + table + " TO ? (FORMAT PARQUET,COMPRESSION ZSTD)", [str(path)])
            records.append({"path": path.name, "bytes": path.stat().st_size,
                            "sha256": file_sha256(path),
                            "rows": con.execute("SELECT count(*) FROM " + table).fetchone()[0],
                            "schema": [list(r[:2]) for r in con.execute("DESCRIBE " + table).fetchall()]})
    _event(progress, "REVERIFY_PINNED_INPUT")
    reverify_inputs(prepared)
    if any((Path(p).stat().st_size, Path(p).stat().st_mtime_ns) != stat for p, stat in before.items()):
        raise ValueError("Input changed during historical preparation")
    if file_sha256(manifest_path) != input_manifest_sha256 or file_sha256(calendar_path) != calendar_sha256:
        raise ValueError("Pinned metadata changed during preparation")
    if any(file_sha256(p) != value for p, value in code_hashes.items()):
        raise ValueError("Preparation code changed during execution")
    manifest = {"format_version": 1, "dataset": "version-dependents-historical-input",
                "calculation_mode": MODE, "preparation_status": "COMPLETE", "count_status": "NOT_COMPUTED",
                "ready_for_load": False, "observed_snapshot_timestamp": observed,
                "snapshot_count": len(calendar), "first_snapshot_at": calendar[0]["snapshot_at"],
                "expected_snapshot_count": expected_snapshot_count,
                "last_snapshot_at": calendar[-1]["snapshot_at"],
                "input_manifest": {"path": str(manifest_path.resolve()), "sha256": input_manifest_sha256,
                                   "input_sha256": prepared["input_sha256"],
                                   "curated_manifest_sha256": prepared["curated_manifest_sha256"]},
                "calendar_manifest": {"path": str(calendar_path.resolve()), "sha256": calendar_sha256},
                "timestamp_adapter": "PINNED_BIGQUERY_NAIVE_UTC_TO_EPOCH_MICROSECONDS",
                "policy": {"source": "ALL_CURATED_RELEASE_VERSIONS_WITH_KNOWN_PUBLICATION_AT_T",
                           "target": "SAME_POPULATION_VALID_STABLE_NPM_SEMVER", "kind": "dependencies",
                           "null_publication": "EXCLUDE", "missing_output_count": "NOT_COMPUTED",
                           "historical_observation_completeness": "UNVERIFIED"},
                "upstream_publication_reverified": False, "local_files_verified": True,
                "raw_input_manifest_preserved": prepared, "code_sha256": code_hashes,
                "files": records, **result,
                "python_version": sys.version, "duckdb_version": duckdb.__version__,
                "resources": {"threads": threads, "memory_limit": memory_limit,
                              "max_temp_directory_size": max_temp_size,
                              "disk_free_bytes_at_start": free_bytes},
                "elapsed_seconds": time.monotonic() - started}
    manifest["policy_sha256"] = sha256(manifest["policy"])
    # Completion metadata is written only after both input checks and all outputs finish.
    manifest_file = output / "input_manifest.json"
    manifest_file.write_bytes(canonical_bytes(manifest))
    _event(progress, "COMPLETE", elapsed_seconds=manifest["elapsed_seconds"])
    return {"output": str(output), "manifest_sha256": file_sha256(manifest_file),
            "statistics": result["statistics"], "elapsed_seconds": manifest["elapsed_seconds"],
            "ready_for_load": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-manifest", type=Path, required=True)
    parser.add_argument("--input-manifest-sha256", required=True)
    parser.add_argument("--calendar", type=Path, required=True)
    parser.add_argument("--calendar-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--memory-limit", default="8GB")
    parser.add_argument("--max-temp-size", default="100GB")
    parser.add_argument("--expected-snapshot-count", type=int, default=229)
    args = parser.parse_args()
    result = prepare_historical_inputs(input_manifest=args.input_manifest,
        input_manifest_sha256=args.input_manifest_sha256, calendar_path=args.calendar,
        calendar_sha256=args.calendar_sha256, output=args.output, threads=args.threads,
        memory_limit=args.memory_limit, max_temp_size=args.max_temp_size,
        expected_snapshot_count=args.expected_snapshot_count)
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
