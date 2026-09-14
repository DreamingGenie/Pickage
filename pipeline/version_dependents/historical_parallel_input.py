"""Physical, immutable input shards for the parallel historical calculator."""
from __future__ import annotations

import shutil
import tempfile
import hashlib
from pathlib import Path

import duckdb

from pipeline.requirements_resolution.input import file_sha256
from pipeline.requirements_resolution.policy import sha256, canonical_bytes
from .artifact import _reject_reparse_ancestors, _validate_sha
from .historical_artifact import _path, _publish_json, _read_json
from .historical_cache import _calendar
from .historical_production_input import TABLES, POLICY, contract as base_contract, partition_for
from .historical_production_input import (verify_inputs as verify_v1, selection,
    _inputs, _verify_profile, _verify_used_raw, prepare_tables, connection, verify_historical_inputs)

FORMAT = "historical-production-input-sharded-v2"


def _record(path, con=None):
    """Reuse the caller's bounded connection for file metadata and row counts."""
    if con is None:
        with duckdb.connect(config={'threads': 1, 'memory_limit': '256MB'}) as opened:
            return _record(path, opened)
    path = _path(path)
    try:
        schema = [[str(r[0]), str(r[1]).upper()] for r in con.execute(
            'DESCRIBE SELECT * FROM read_parquet(?, hive_partitioning=false)', [str(path)]).fetchall()]
        rows = con.execute('SELECT count(*) FROM read_parquet(?, hive_partitioning=false)', [str(path)]).fetchone()[0]
    except Exception as error:
        raise ValueError('Invalid partition Parquet: ' + path.name) from error
    return {'name': path.name, 'sha256': file_sha256(path), 'bytes': path.stat().st_size,
            'rows': rows, 'schema': schema,
            'schema_sha256': hashlib.sha256(canonical_bytes(schema).rstrip(b'\n')).hexdigest()}


def contract():
    return {"parallel_input_sha256": file_sha256(Path(__file__)),
            "validation_sha256": file_sha256(Path(__file__).with_name('historical_production_events.py')),
            "validation_sql_sha256": file_sha256(Path(__file__).with_name('historical_production_sql.py')),
            "base_input_contract": base_contract()}


def _safe_output(output: Path, protected: list[Path]) -> None:
    output = _path(output)
    if any(output.is_relative_to(p) or p.is_relative_to(output) for p in protected):
        raise ValueError("Sharded output overlaps a pinned input")
    _reject_reparse_ancestors(output)
    if output.exists():
        raise ValueError("Output already exists")


def _free_space(output, minimum):
    if type(minimum) is not int or minimum < 0:
        raise ValueError('Invalid free disk guard')
    ancestor = output.parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    if shutil.disk_usage(ancestor).free < minimum:
        raise ValueError('Insufficient free disk before sharding')


def _write_shards(con, output: Path, partition_count: int):
    partitions = {}
    totals = {table: 0 for table in TABLES}
    groups = {}
    for number, name in con.execute('SELECT partition_id,name FROM target_names ORDER BY partition_id,name').fetchall():
        groups.setdefault(number, []).append(name)
    for number in range(partition_count):
        names = groups.get(number, [])
        key = f'{number:03d}'
        partitions[key] = {'status': 'READY' if names else 'EMPTY', 'names': names,
                           'files': {}, 'rows': {table: 0 for table in TABLES}}
        if names:
            (output / ('partition=' + key)).mkdir()
    # One source scan per table. DuckDB may emit several chunks per partition;
    # consolidate only those chunks, never scan the full source again per owner.
    staging = output / 'partition-staging'
    staging.mkdir()
    con.execute('SET partitioned_write_max_open_files=256')
    for table in TABLES:
        source = staging / table
        con.execute(f'COPY {table} TO ? (FORMAT PARQUET, COMPRESSION ZSTD, '
                    "PARTITION_BY (partition_id), WRITE_PARTITION_COLUMNS true, FILENAME_PATTERN 'chunk_{i}')",
                    [str(source)])
        for number in sorted(groups):
            key = f'{number:03d}'
            path = output / ('partition=' + key) / (table + '.parquet')
            chunks = sorted((source / ('partition_id=' + str(number))).glob('*.parquet'))
            if len(chunks) == 1:
                chunks[0].rename(path)
            elif chunks:
                con.read_parquet([str(p) for p in chunks], hive_partitioning=False).create_view('_shard_chunks', replace=True)
                con.execute('COPY _shard_chunks TO ? (FORMAT PARQUET, COMPRESSION ZSTD)', [str(path)])
                for chunk in chunks:
                    if not chunk.resolve().is_relative_to(staging.resolve()):
                        raise ValueError('Staging chunk escapes the new preparation')
                    chunk.unlink()
            else:
                con.execute(f'COPY (SELECT * FROM {table} LIMIT 0) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)', [str(path)])
            record = {**_record(path, con), 'name': path.relative_to(output).as_posix()}
            partitions[key]['files'][table] = record
            partitions[key]['rows'][table] = record['rows']
            totals[table] += record['rows']
        if totals[table] != con.execute(f'SELECT count(*) FROM {table}').fetchone()[0]:
            raise ValueError('Partition writer lost source rows: ' + table)
    return partitions, totals


def _split(source: Path, output: Path, *, manifest: dict, threads=4, memory_limit="16GB", max_temp_size="256GB", min_free_bytes: int = 0) -> dict:
    _safe_output(output, [source])
    _free_space(output, min_free_bytes)
    output.mkdir(parents=True, exist_ok=False)
    plan = {"format": FORMAT, "scope": manifest["scope"], "source_dir": str(source),
            "source_manifest_sha256": file_sha256(source / "input_manifest.json"),
            "selection": manifest["selection"], "calendar": manifest["calendar"],
            "observed_snapshot_timestamp": manifest["observed_snapshot_timestamp"],
            "policy": manifest["policy"], "partition_count": manifest["partition_count"],
            "generation_contract": contract(), "ready_for_load": False}
    _publish_json(output / "input_plan.json", plan)
    with connection(output / "sharding.duckdb", threads=threads, memory_limit=memory_limit, max_temp_size=max_temp_size) as con:
        for table in TABLES:
            con.read_parquet(str(source / (table + ".parquet")), hive_partitioning=False).create_view(table)
        partitions, totals = _write_shards(con, output, manifest["partition_count"])
    result = {**plan, "preparation_status": "COMPLETE", "count_status": "NOT_COMPUTED",
              "partitions": partitions, "files": {r["name"]: r for p in partitions.values() for r in p["files"].values()},
              "rows": totals,
              "partition_count": len(partitions), "input_plan_sha256": file_sha256(output / "input_plan.json")}
    _publish_json(output / "input_manifest.json", result)
    digest = file_sha256(output / "input_manifest.json")
    verify_inputs(output, digest)
    return {"prepared_dir": str(output), "manifest_sha256": digest}


def from_prepared(*, prepared_dir, manifest_sha256, output, threads=4, memory_limit="16GB",
                  max_temp_size="256GB", min_free_bytes=0):
    """Convert a verified v1 input into immutable physical partition files."""
    source = _path(prepared_dir); _validate_sha(manifest_sha256, "input manifest SHA")
    if file_sha256(source / "input_manifest.json") != manifest_sha256:
        raise ValueError("Input manifest SHA mismatch")
    old = verify_v1(source, manifest_sha256)
    generation = contract()
    result = _split(source, _path(output), manifest=old, threads=threads, memory_limit=memory_limit,
                    max_temp_size=max_temp_size, min_free_bytes=min_free_bytes)
    verify_v1(source, manifest_sha256)
    if contract() != generation:
        raise ValueError('Input generation changed during conversion')
    return result


def prepare(*, h1_dir, h1_manifest_sha256, profile_manifest, profile_manifest_sha256,
            selection_csv, selection_sha256, output, sample_names=None, full_selected=False,
            partition_count=128, threads=4, memory_limit="16GB", max_temp_size="256GB",
            min_free_bytes=20_000_000_000):
    """Validate pinned inputs and write physical shards directly from source views."""
    partition_for('validation', partition_count)
    names, selected = selection(selection_csv, selection_sha256, sample_names=sample_names,
                                full_selected=full_selected)
    h1_dir, output = _path(h1_dir), _path(output); profile_path = _path(profile_manifest)
    h1, raw = _inputs(h1_dir, h1_manifest_sha256)
    _verify_profile(profile_path, profile_manifest_sha256, h1_manifest_sha256)
    _safe_output(output, [h1_dir, profile_path.parent, _path(selection_csv), *[_path(p) for p in raw["sources"].values()]])
    _free_space(output, min_free_bytes)
    output.mkdir(parents=True, exist_ok=False)
    generation = contract()
    calendar = []
    plan = {"format": FORMAT, "scope": "FULL_SELECTED" if full_selected else "SAMPLE",
            "h1_dir": str(h1_dir), "h1_manifest_sha256": h1_manifest_sha256,
            "profile_manifest": str(profile_path), "profile_manifest_sha256": profile_manifest_sha256,
            "selection": selected, "partition_count": partition_count, "policy": POLICY,
            "generation_contract": generation, "ready_for_load": False}
    _publish_json(output / "input_plan.json", plan)
    verify_historical_inputs(h1_dir, h1_manifest_sha256)
    _verify_used_raw(raw)
    with connection(output / "preparation.duckdb", threads=threads, memory_limit=memory_limit, max_temp_size=max_temp_size) as con:
        con.read_parquet(str(h1_dir / "source_population.parquet"), hive_partitioning=False).create_view("source_population")
        con.read_parquet(str(h1_dir / "target_population.parquet"), hive_partitioning=False).create_view("h1_targets")
        con.read_parquet(raw["files"]["requirements"], hive_partitioning=False).create_view("input_requirements")
        con.read_parquet(raw["files"]["package"], hive_partitioning=False).create_view("input_package")
        for table in ("lookup_workload", "package_workload"):
            con.read_parquet(str(profile_path.parent / (table + ".parquet")), hive_partitioning=False).create_view(table)
        calendar = [{"snapshot_at": day, "snapshot_timestamp": stamp} for day, stamp in con.execute(
            "SELECT snapshot_at::VARCHAR,strftime(snapshot_timestamp AT TIME ZONE 'UTC','%Y-%m-%dT%H:%M:%S.%fZ') FROM read_parquet(?) ORDER BY snapshot_index", [str(h1_dir / "calendar.parquet")]).fetchall()]
        counts = prepare_tables(con, names, partition_count=partition_count)
        partitions, totals = _write_shards(con, output, partition_count)
    if counts != totals:
        raise ValueError('Shards do not conserve prepared source counts')
    _verify_used_raw(raw)
    verify_historical_inputs(h1_dir, h1_manifest_sha256)
    _verify_profile(profile_path, profile_manifest_sha256, h1_manifest_sha256)
    if file_sha256(_path(selection_csv)) != selection_sha256 or contract() != generation: raise ValueError("Input or generation code changed during preparation")
    result = {**plan, "preparation_status": "COMPLETE", "count_status": "NOT_COMPUTED", "calendar": calendar,
              "observed_snapshot_timestamp": h1["observed_snapshot_timestamp"], "input_plan_sha256": file_sha256(output / "input_plan.json"),
              "partitions": partitions, "files": {r["name"]: r for p in partitions.values() for r in p["files"].values()}, "rows": totals}
    _publish_json(output / "input_manifest.json", result)
    digest = file_sha256(output / "input_manifest.json"); verify_inputs(output, digest)
    return {"prepared_dir": str(output), "manifest_sha256": digest}


def _manifest(root, digest):
    _validate_sha(digest, "sharded input manifest SHA")
    path = root / "input_manifest.json"
    if file_sha256(path) != digest: raise ValueError("Sharded manifest SHA mismatch")
    m = _read_json(path)
    if m.get("format") != FORMAT or m.get("preparation_status") != "COMPLETE" or m.get("policy") != POLICY:
        raise ValueError("Sharded input contract mismatch")
    if m.get("generation_contract") != contract() or file_sha256(root / "input_plan.json") != m.get("input_plan_sha256"):
        raise ValueError("Sharded generation or plan mismatch")
    plan = _read_json(root / 'input_plan.json')
    if any(m.get(k) != v for k, v in plan.items()):
        raise ValueError('Sharded manifest differs from its input plan')
    if m.get('scope') not in ('SAMPLE', 'FULL_SELECTED') or m.get('ready_for_load') is not False:
        raise ValueError('Invalid input scope or readiness')
    partition_for('validation', m['partition_count'])
    _calendar(m['calendar'], m['observed_snapshot_timestamp'])
    return m


def verify_inputs(prepared_dir, manifest_sha256):
    root = _path(prepared_dir); m = _manifest(root, manifest_sha256)
    if set(m.get("partitions", {})) != {f"{i:03d}" for i in range(m["partition_count"])}:
        raise ValueError("Partition inventory mismatch")
    inventory = {r['name']: r for part in m['partitions'].values() for r in part['files'].values()}
    ready = sum(p['status'] == 'READY' for p in m['partitions'].values())
    if inventory != m['files'] or len(inventory) != len(TABLES) * ready:
        raise ValueError('Global file inventory mismatch')
    with tempfile.TemporaryDirectory(prefix='parallel-input-check-') as scratch, connection(Path(scratch) / 'check.duckdb', memory_limit='16GB', max_temp_size='256GB') as con:
        seen = []
        for key, part in m['partitions'].items():
            if part['status'] == 'EMPTY':
                if part['names'] or part['files'] or part['rows'] != {t: 0 for t in TABLES}:
                    raise ValueError('Empty partition contains data')
                continue
            if part['status'] != 'READY':
                raise ValueError('Invalid partition status')
            verify_partition(root, m, key, con=con)
            if set(part['files']) != set(TABLES) or set(part['rows']) != set(TABLES):
                raise ValueError('Partition table inventory mismatch')
            for table in TABLES:
                path = root / part['files'][table]['name']
                count, misplaced = con.execute('SELECT count(*),count(*) FILTER '
                    '(WHERE partition_id IS DISTINCT FROM ?) FROM read_parquet(?, hive_partitioning=false)',
                    [int(key), str(path)]).fetchone()
                if misplaced or count != part['rows'][table]:
                    raise ValueError('Partition rows or ownership mismatch')
            names = [r[0] for r in con.execute('SELECT name FROM read_parquet(?, hive_partitioning=false) ORDER BY name',
                     [str(root / part['files']['target_names']['name'])]).fetchall()]
            if (names != part['names'] or part['status'] != ('READY' if names else 'EMPTY')
                    or any(partition_for(name, m['partition_count']) != int(key) for name in names)):
                raise ValueError('Partition name membership mismatch')
            seen.extend(names)
        selected = m['selection']
        if (len(seen) != len(set(seen)) or len(seen) != selected['chosen_count']
                or sha256(sorted(seen)) != selected['chosen_names_sha256']
                or (selected['chosen_names'] is not None and sorted(seen) != sorted(selected['chosen_names']))):
            raise ValueError('Partition target coverage mismatch')
        if m['rows'] != {t: sum(p['rows'][t] for p in m['partitions'].values()) for t in TABLES}:
            raise ValueError('Partition row totals mismatch')
        open_all(con, root, m)
        from .historical_production_events import validate_weighted_inputs
        validate_weighted_inputs(con, len(m["calendar"]))
        if con.execute("SELECT EXISTS(SELECT 1 FROM declarations GROUP BY source_package_id,source_version "
                       "HAVING count(DISTINCT birth_index)>1 OR "
                       "count(DISTINCT coalesce(dependency_error::VARCHAR,'NULL'))>1)").fetchone()[0]:
            raise ValueError('Source birth or error flag differs across shards')
    verify_bytes(root, manifest_sha256)
    return m


def verify_bytes(root, manifest_sha256):
    root = _path(root)
    manifest = _manifest(root, manifest_sha256)
    for key, part in manifest['partitions'].items():
        if part['status'] == 'EMPTY':
            if part['files'] or part['names'] or any(part['rows'].values()):
                raise ValueError('Empty partition contains data')
            continue
        for table in TABLES:
            record = part['files'][table]
            if record['name'] != f'partition={key}/{table}.parquet':
                raise ValueError('Partition file path is not canonical')
            path = _path(root / record['name'])
            if path.stat().st_size != record['bytes'] or file_sha256(path) != record['sha256']:
                raise ValueError('Partition file changed')
    return manifest


def verify_partition(root, manifest, partition_id, *, con=None, bytes_only=False):
    key = f"{partition_id:03d}" if isinstance(partition_id, int) else str(partition_id)
    if key not in manifest["partitions"]: raise ValueError("Unknown partition")
    part = manifest["partitions"][key]
    if part['status'] != 'READY':
        raise ValueError('Cannot execute an empty partition')
    if con is None and not bytes_only:
        with duckdb.connect(config={'threads': 1, 'memory_limit': '256MB'}) as opened:
            return verify_partition(root, manifest, partition_id, con=opened)
    for table in TABLES:
        path = _path(_path(root) / part["files"][table]["name"])
        expected = part["files"][table]
        if expected["name"] != f"partition={key}/{table}.parquet":
            raise ValueError("Partition file path is not canonical")
        if bytes_only:
            if path.stat().st_size != expected['bytes'] or file_sha256(path) != expected['sha256']:
                raise ValueError('Partition file changed')
        elif {**_record(path, con), "name": expected["name"]} != expected:
            raise ValueError("Partition file changed")
    return part


def open_partition(con, root, manifest, partition_id, materialize=True):
    root = _path(root); key = f"{partition_id:03d}" if isinstance(partition_id, int) else str(partition_id)
    if key not in manifest["partitions"]: raise ValueError("Unknown partition")
    part = manifest["partitions"][key]
    for table in TABLES:
        expected = part["files"][table]
        if expected["name"] != f"partition={key}/{table}.parquet": raise ValueError("Partition file path is not canonical")
        path = root / expected["name"]
        if materialize and table in {"target_names", "target_population", "lookups"}:
            quoted = str(path).replace("'", "''")
            con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM read_parquet('{quoted}', hive_partitioning=false)")
        else:
            con.read_parquet(str(path), hive_partitioning=False).create_view(table, replace=True)
    return [str(root / part["files"][t]["name"]) for t in TABLES]


def open_all(con, root, manifest):
    root = _path(root); paths = {t: [str(root / p["files"][t]["name"]) for p in manifest["partitions"].values() if p['status'] == 'READY'] for t in TABLES}
    for table, files in paths.items():
        literals = "[" + ",".join("'" + f.replace("'", "''") + "'" for f in files) + "]"
        con.execute(f"CREATE OR REPLACE VIEW {table} AS SELECT * FROM read_parquet({literals}, hive_partitioning=false)")
    return paths
