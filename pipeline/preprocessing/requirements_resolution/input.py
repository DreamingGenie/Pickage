"""Verify exact approved remote manifests against read-only local Parquet."""
from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath

import duckdb

from pipeline.preprocessing.curated.build import load_bronze
from pipeline.postgresql.input import select_run
from pipeline.preprocessing.common.curated_input import SCHEMAS, schema as _schema
from pipeline.preprocessing.snapshot.policy import parse_timestamp, policy_document, policy_sha256
from pipeline.preprocessing.requirements_resolution.policy import canonical_bytes, sha256

TABLES = ("package", "version", "versions_full", "requirements")
RAW_SCHEMAS = {
    "requirements": [("SnapshotAt", "TIMESTAMP"), ("Name", "VARCHAR"), ("Version", "VARCHAR")]
    + [(key, 'STRUCT("Name" VARCHAR, Requirement VARCHAR)[]')
       for key in ("Dependencies", "PeerDependencies", "OptionalDependencies")],
    "versions_full": [("SnapshotAt", "TIMESTAMP"), ("Name", "VARCHAR"), ("Version", "VARCHAR"),
                      ("is_release", "BOOLEAN"), ("ordinal", "BIGINT"), ("published_at", "TIMESTAMP"),
                      ("Deprecated", "VARCHAR"), ("dependency_error", "BOOLEAN"),
                      ("Description", "VARCHAR"), ("Licenses", "VARCHAR[]"), ("source_repo", "VARCHAR")],
}


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _plain_path(path, root):
    path, root = Path(path).absolute(), Path(root).absolute()
    if not path.is_relative_to(root):
        raise ValueError("Input path escapes its selected root")
    for item in [path, *path.parents]:
        if item.is_symlink() or getattr(item, "is_junction", lambda: False)():
            raise ValueError("Input symlinks/junctions are not accepted")
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError("Resolved input path escapes its selected root")
    return resolved


def _roots(curated_outputs, versions_dir, requirements_dir):
    roots = {"curated_outputs": Path(curated_outputs).absolute(),
             "versions_full": Path(versions_dir).absolute(),
             "requirements": Path(requirements_dir).absolute()}
    for key, root in roots.items():
        roots[key] = _plain_path(root, root)
        if not roots[key].is_dir():
            raise ValueError("Selected input root is missing: " + key)
    if len(set(roots.values())) != len(roots):
        raise ValueError("Input roots must be distinct")
    return roots


def _folder(roots, table):
    return roots["curated_outputs"] / table / "data" if table in ("package", "version") else roots[table]


def _local_selection(folder, records):
    expected = {}
    for record in records:
        name = PurePosixPath(record["key"]).name
        if ":" in name or name in expected:
            raise ValueError("Ambiguous or invalid manifest filename mapping")
        expected[name] = record
    actual = {p.name: p for p in folder.glob("*.parquet")}
    if set(actual) != set(expected):
        raise ValueError("Input file set differs from approved manifest: " + str(folder))
    return [(actual[name], expected[name]) for name in sorted(expected)]


def _inspect(con, path, root, table, expected, timestamp):
    path = _plain_path(path, root)
    before = path.stat()
    if before.st_size != expected["bytes"] or file_sha256(path) != expected["sha256"]:
        raise ValueError("Input file bytes/SHA differ from approved manifest: " + str(path))
    rows = con.execute("SELECT sum(num_rows) FROM parquet_file_metadata(?)", [[str(path)]]).fetchone()[0]
    if type(rows) is not int or rows < 0:
        raise ValueError("Invalid Parquet row metadata")
    if table in ("package", "version"):
        _schema(con, path, table, SCHEMAS)
    else:
        actual = [(row[0], row[1].upper().replace('"', '')) for row in con.execute(
            "DESCRIBE SELECT * FROM read_parquet(?,hive_partitioning=false)", [str(path)]).fetchall()]
        required = [(name, kind.upper().replace('"', '')) for name, kind in RAW_SCHEMAS[table]]
        if actual != required:
            raise ValueError("Raw Parquet schema mismatch: " + table)
        low, high, total, known = con.execute(
            "SELECT min(SnapshotAt),max(SnapshotAt),count(*),count(SnapshotAt) "
            "FROM read_parquet(?,hive_partitioning=false)", [str(path)]).fetchone()
        target = parse_timestamp(timestamp).replace(tzinfo=None)
        if total != rows or known != rows or (rows and (low != target or high != target)):
            raise ValueError("Raw input has mixed, NULL, or different SnapshotAt")
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("Input file changed during verification")
    return {"table": table, "path": str(path), "bytes": before.st_size,
            "sha256": expected["sha256"], "rows": rows}


def prepare_inputs(s3, *, snapshot, curated_run_id, curated_outputs, versions_dir,
                   requirements_dir, output=None):
    roots = _roots(curated_outputs, versions_dir, requirements_dir)
    if output is not None:
        output = Path(output).resolve()
        if any(output.is_relative_to(root) for root in roots.values()) or output.exists():
            raise ValueError("Input manifest output must be new and outside source roots")
    curated = select_run(s3, snapshot, curated_run_id)
    stamp = parse_timestamp(curated["snapshot_timestamp"], allow_naive_utc=True)
    if stamp.date().isoformat() != snapshot:
        raise ValueError("Curated timestamp does not match requested snapshot date")
    timestamp = stamp.isoformat(timespec="microseconds").replace("+00:00", "Z")
    request = curated["manifest"]["request"]
    bronze_id = request.get("bronze_run_id")
    if not isinstance(bronze_id, str) or not isinstance(request.get("sources"), dict):
        raise ValueError("Curated request has no Bronze lineage")
    remote_records = dict(curated["_service_records"])
    refs, metadata, expected_counts = {}, [], dict(curated["counts"])
    for table in ("versions_full", "requirements"):
        manifest, ref = load_bronze(s3, table, snapshot, bronze_id)
        if request["sources"].get(table) != ref:
            raise ValueError("Curated/Bronze manifest lineage mismatch: " + table)
        local = _plain_path(roots[table] / "_MANIFEST.json", roots[table])
        body = local.read_bytes()
        if hashlib.sha256(body).hexdigest() != manifest["source_manifest_sha256"]:
            raise ValueError("Local extraction summary differs from approved Bronze source manifest")
        refs[table] = {**ref, "source_manifest_sha256": manifest["source_manifest_sha256"]}
        metadata.append({"path": str(local), "sha256": hashlib.sha256(body).hexdigest()})
        remote_records[table] = manifest["files"]
        expected_counts[table] = manifest["row_count"]
    files, records = {}, []
    with duckdb.connect(config={"threads": 1, "memory_limit": "512MB"}) as con:
        for table in TABLES:
            folder = _folder(roots, table)
            root = roots["curated_outputs"] if table in ("package", "version") else folder
            files[table] = []
            table_records = []
            for path, remote in _local_selection(folder, remote_records[table]):
                record = _inspect(con, path, root, table, remote, timestamp)
                table_records.append(record)
                files[table].append(record["path"])
            if sum(record["rows"] for record in table_records) != expected_counts[table]:
                raise ValueError("Input Parquet row total differs from approved run: " + table)
            records.extend(table_records)
    prepared = {"format_version": 1, "dataset": "requirements-resolution-input", "snapshot": snapshot,
                "snapshot_timestamp": timestamp, "curated_run_id": curated_run_id,
                "bronze_run_id": bronze_id, "curated_manifest_sha256": curated["manifest_sha256"],
                "bronze_references": refs,
                "snapshot_policy": {"document": policy_document(), "sha256": policy_sha256()},
                "files": files, "counts": expected_counts, "file_records": records,
                "metadata_records": metadata,
                "sources": {"curated_outputs": str(roots["curated_outputs"]),
                            "versions_dir": str(roots["versions_full"]),
                            "requirements_dir": str(roots["requirements"])}}
    prepared["input_sha256"] = sha256(prepared)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("xb") as stream:
            stream.write(canonical_bytes(prepared))
    return prepared


def reverify_inputs(prepared, s3=None):
    if not isinstance(prepared, dict) or prepared.get("dataset") != "requirements-resolution-input":
        raise ValueError("Invalid prepared input contract")
    payload = {key: value for key, value in prepared.items() if key != "input_sha256"}
    if sha256(payload) != prepared.get("input_sha256"):
        raise ValueError("Prepared input manifest checksum mismatch")
    if prepared.get("snapshot_policy") != {"document": policy_document(), "sha256": policy_sha256()}:
        raise ValueError("Snapshot policy changed")
    roots = _roots(**prepared["sources"])
    for table in TABLES:
        folder = _folder(roots, table)
        records = [row for row in prepared["file_records"] if row["table"] == table]
        expected = {Path(row["path"]) for row in records}
        if len(expected) != len(records) or expected != set(map(Path, prepared["files"][table])):
            raise ValueError("Prepared file lists disagree")
        if set(folder.glob("*.parquet")) != expected:
            raise ValueError("Input file set changed")
        if sum(row["rows"] for row in records) != prepared["counts"][table]:
            raise ValueError("Prepared row totals disagree")
        root = roots["curated_outputs"] if table in ("package", "version") else folder
        for row in records:
            path = _plain_path(row["path"], root)
            if path.stat().st_size != row["bytes"] or file_sha256(path) != row["sha256"]:
                raise ValueError("Input file changed: " + str(path))
    for row in prepared["metadata_records"]:
        path = Path(row["path"])
        matches = [root for root in roots.values() if path.is_relative_to(root)]
        if len(matches) != 1:
            raise ValueError("Input metadata escaped selected roots")
        _plain_path(path, matches[0])
        if file_sha256(path) != row["sha256"]:
            raise ValueError("Input metadata changed")
    if s3 is not None:
        curated = select_run(s3, prepared["snapshot"], prepared["curated_run_id"])
        if curated["manifest_sha256"] != prepared["curated_manifest_sha256"]:
            raise ValueError("Curated run changed")
        for table, expected in prepared["bronze_references"].items():
            manifest, ref = load_bronze(s3, table, prepared["snapshot"], prepared["bronze_run_id"])
            if {**ref, "source_manifest_sha256": manifest["source_manifest_sha256"]} != expected:
                raise ValueError("Bronze run changed")
    return True
