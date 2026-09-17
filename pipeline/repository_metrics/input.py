"""Freeze and validate the inputs consumed by repository-metrics transforms.

The adapter is deliberately read-only.  It joins immutable Curated metadata,
the approved Bronze ``versions_full`` manifest, and the local snapshot
candidate/inventories into one deterministic input manifest.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any

import duckdb

from pipeline.curated.build import CURATED_BUCKET, load_bronze
from pipeline.curated.storage import read_optional
from pipeline.postgresql.input import select_run
from pipeline.snapshot.input import read_candidate


RAW_BUCKET = "pickage-raw"
_SHA = re.compile(r"^[0-9a-f]{64}$")
_RUN = re.compile(r"^[A-Za-z0-9_-]+$")
_TABLES = ("package", "version", "versions_full", "projects")
_CURATED_SCHEMA = {
    "package": [("package_id", "INTEGER"), ("name", "VARCHAR"), ("repo_url", "VARCHAR")],
    "version": [("version", "VARCHAR"), ("package_id", "INTEGER"),
                 ("published_at", "TIMESTAMP"), ("ordinal", "BIGINT"),
                 ("description", "VARCHAR"), ("licenses", "JSON"),
                 ("deprecated", "VARCHAR"), ("dependency", "JSON")],
}


def _sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _safe_rel(value: str) -> str:
    path = PurePosixPath(value)
    raw_parts = value.replace("\\", "/").split("/")
    if (not value or path.is_absolute() or ":" in raw_parts[0]
            or "\\" in value or any(p in ("", ".", "..") for p in raw_parts)):
        raise ValueError(f"unsafe relative path: {value!r}")
    return path.as_posix()


def _naive_utc(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed.isoformat(timespec="microseconds")


def _parquet_rows(con: Any, path: Path) -> int:
    try:
        value = con.execute("SELECT sum(num_rows) FROM parquet_file_metadata(?)", [[str(path)]]).fetchone()[0]
    except Exception as exc:
        raise ValueError(f"invalid Parquet input: {path}") from exc
    return int(value or 0)


def _file_record(path: Path, root: Path, con: Any, *, snapshot_timestamp: str | None = None) -> dict:
    path = path.resolve()
    root = root.resolve()
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(f"file escapes input root: {path}") from exc
    before = path.stat()
    rows = _parquet_rows(con, path)
    record = {"path": str(path), "relative_path": relative, "bytes": before.st_size,
              "sha256": _sha_file(path), "rows": rows}
    if snapshot_timestamp is not None:
        try:
            desc = con.execute("DESCRIBE SELECT SnapshotAt FROM read_parquet(?, hive_partitioning=false)", [str(path)]).fetchall()
        except Exception as exc:
            raise ValueError(f"SnapshotAt schema missing: {path}") from exc
        if not desc:
            raise ValueError(f"SnapshotAt schema missing: {path}")
        type_name = str(desc[0][1]).upper()
        if type_name not in {"TIMESTAMP", "TIMESTAMP WITH TIME ZONE", "TIMESTAMP_MS", "TIMESTAMP_S"}:
            raise ValueError(f"SnapshotAt must be timestamp: {path}")
        values = con.execute("SELECT min(SnapshotAt), max(SnapshotAt), count(*), count(SnapshotAt) FROM read_parquet(?, hive_partitioning=false)", [str(path)]).fetchone()
        if values[0] is None or values[0] != values[1] or int(values[2]) != rows or int(values[3]) != rows:
            raise ValueError(f"mixed or empty SnapshotAt values: {path}")
        observed = _naive_utc(str(values[0]))
        if observed != snapshot_timestamp:
            raise ValueError(f"snapshot timestamp mismatch: {path}")
        record["snapshot_timestamp"] = observed
    after = path.stat()
    if after.st_size != before.st_size or after.st_mtime_ns != before.st_mtime_ns:
        raise ValueError(f"file changed during inspection: {path}")
    return record


def _local_manifest(root: Path, snapshot: str) -> tuple[Path, bytes, dict]:
    candidates = [root / "_MANIFEST.json", root / f"snapshot={snapshot}" / "_MANIFEST.json"]
    marker = next((p for p in candidates if p.is_file()), None)
    if marker is None:
        raise ValueError(f"missing versions_full _MANIFEST.json under {root}")
    raw = marker.read_bytes()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid manifest: {marker}") from exc
    if not isinstance(value, dict):
        raise ValueError("versions_full manifest must be an object")
    return marker, raw, value


def _manifest_files(value: dict) -> list[dict]:
    files = value.get("files", value.get("gcs_files"))
    if not isinstance(files, list):
        raise ValueError("versions_full manifest has no files")
    result = []
    for item in files:
        if not isinstance(item, dict):
            raise ValueError("malformed versions_full manifest file")
        key = item.get("key", item.get("path", item.get("name")))
        if not isinstance(key, str) or not key:
            raise ValueError("versions_full manifest file has no key")
        result.append({"basename": PurePosixPath(key).name,
                       "bytes": item.get("bytes", item.get("size")),
                       "sha256": item.get("sha256", item.get("checksum")),
                       "rows": item.get("rows", item.get("row_count"))})
    return result


def _validate_curated_files(curated_outputs: Path, metadata: dict, con: Any) -> tuple[dict[str, list[str]], list[dict]]:
    expected: dict[str, list[tuple[str, dict]]] = {"package": [], "version": []}
    prefix = metadata["run_prefix"] + "/attempts/"
    for table, records in metadata.get("_service_records", {}).items():
        for record in records:
            key = record["key"]
            if not key.startswith(prefix):
                raise ValueError("Curated service key is outside the run")
            suffix = key[len(prefix):]
            parts = suffix.split("/", 1)
            if len(parts) != 2 or not _RUN.fullmatch(parts[0]):
                raise ValueError("invalid Curated attempt path")
            relative = _safe_rel(parts[1])
            if not relative.startswith(table + "/"):
                raise ValueError("Curated service table path mismatch")
            expected[table].append((relative, record))
    all_expected: set[str] = set()
    attempt_ids: set[str] = set()
    for record in metadata["manifest"].get("files", []):
        key = record["key"]
        if not key.startswith(prefix):
            raise ValueError("Curated manifest file is outside the run")
        suffix = key[len(prefix):]
        attempt, relative = suffix.split("/", 1) if "/" in suffix else ("", "")
        if not _RUN.fullmatch(attempt):
            raise ValueError("invalid Curated attempt path")
        attempt_ids.add(attempt)
        all_expected.add(_safe_rel(relative))
    if len(attempt_ids) != 1:
        raise ValueError("Curated outputs use multiple attempts")
    actual_files = sorted(p for p in curated_outputs.rglob("*") if p.is_file())
    actual_rel = {_safe_rel(p.relative_to(curated_outputs).as_posix()): p for p in actual_files}
    if set(actual_rel) != all_expected:
        raise ValueError("Curated output files differ from approved manifest")
    expected_rel = {relative for rows in expected.values() for relative, _ in rows}
    if not expected_rel.issubset(actual_rel):
        raise ValueError("Curated service files are missing")
    paths, file_records = {"package": [], "version": []}, []
    for table in ("package", "version"):
        for relative, remote in expected[table]:
            path = actual_rel[relative]
            record = _file_record(path, curated_outputs, con)
            if record["bytes"] != remote["bytes"] or record["sha256"] != remote["sha256"]:
                raise ValueError(f"Curated file checksum/size mismatch: {relative}")
            record.update({"table": table, "key": remote["key"], "expected_bytes": remote["bytes"], "expected_sha256": remote["sha256"]})
            paths[table].append(str(path.resolve()))
            file_records.append(record)
    for table in paths:
        for path in paths[table]:
            actual_schema = [(r[0], str(r[1]).upper()) for r in con.execute("DESCRIBE SELECT * FROM read_parquet(?, hive_partitioning=false)", [path]).fetchall()]
            if actual_schema != _CURATED_SCHEMA[table]:
                raise ValueError(f"Curated {table} schema mismatch")
        if sum(r["rows"] for r in file_records if r["table"] == table) != metadata["counts"][table]:
            raise ValueError(f"Curated {table} row count mismatch")
    # Preserve every approved Curated object in the frozen manifest.  Auxiliary
    # outputs (ID registry, quality evidence) are not consumed by this input
    # adapter, but their presence and bytes are part of the immutable run.
    service_rel = {relative for rows in expected.values() for relative, _ in rows}
    by_relative = {r["key"][len(prefix):].split("/", 1)[1]: r for r in metadata["manifest"].get("files", [])}
    for relative in sorted(all_expected - service_rel):
        path = actual_rel[relative]
        remote = by_relative[relative]
        stat = path.stat()
        digest = _sha_file(path)
        if stat.st_size != remote.get("bytes") or digest != remote.get("sha256"):
            raise ValueError(f"Curated auxiliary file checksum/size mismatch: {relative}")
        file_records.append({"path": str(path.resolve()), "relative_path": relative,
                             "bytes": stat.st_size, "sha256": digest, "rows": 0,
                             "table": "curated_aux", "key": remote["key"]})
    return paths, file_records


def _validate_versions(versions_dir: Path, snapshot: str, snapshot_timestamp: str, bronze_manifest: dict, con: Any, *, table="versions_full") -> tuple[list[str], list[dict], str]:
    marker, marker_raw, local = _local_manifest(versions_dir, snapshot)
    expected_source_sha = bronze_manifest.get("source_manifest_sha256")
    if not isinstance(expected_source_sha, str) or _sha_bytes(marker_raw) != expected_source_sha:
        raise ValueError("local versions_full manifest SHA does not match approved Bronze source manifest")
    if local.get("table") not in (None, "versions_full") or local.get("snapshot") not in (None, snapshot):
        raise ValueError("versions_full manifest identity mismatch")
    bronze_records = _manifest_files(bronze_manifest)
    expected_names = {r["basename"] for r in bronze_records}
    # The preserved source _MANIFEST is a BigQuery extraction receipt and may
    # only contain gcs_files/gcs_bytes.  When it has per-file records, enforce
    # those too; the authoritative per-file list is the approved Bronze run.
    local_files = local.get("files")
    if local_files is not None:
        local_records = _manifest_files(local)
        by_name = {r["basename"]: r for r in local_records}
        if len(by_name) != len(local_records) or set(by_name) != expected_names:
            raise ValueError("versions_full file list differs from Bronze manifest")
    root = marker.parent
    files = {p.name: p for p in root.glob("*.parquet")}
    if set(files) != expected_names:
        raise ValueError("local versions_full Parquet files differ from Bronze manifest")
    if local.get("rows", local.get("row_count")) is not None and local.get("rows", local.get("row_count")) != bronze_manifest.get("row_count"):
        raise ValueError("local versions_full row count differs from Bronze manifest")
    if local.get("gcs_files") is not None and local.get("gcs_files") != len(bronze_records):
        raise ValueError("local versions_full file count differs from Bronze manifest")
    if local.get("gcs_bytes") is not None and local.get("gcs_bytes") != sum(r["bytes"] for r in bronze_records):
        raise ValueError("local versions_full byte count differs from Bronze manifest")
    records, paths = [], []
    for item in bronze_records:
        name = item["basename"]
        path = files[name]
        actual = _file_record(path, root, con, snapshot_timestamp=snapshot_timestamp)
        for field in ("bytes", "sha256"):
            expected = item[field]
            if expected is None or actual[field] != expected:
                raise ValueError(f"versions_full {field} mismatch: {name}")
        if item.get("rows") is not None and actual["rows"] != item["rows"]:
            raise ValueError(f"versions_full rows mismatch: {name}")
        actual.update({"table": "versions_full", "bronze_key": item.get("key", name)})
        records.append(actual)
        paths.append(str(path.resolve()))
    if sum(r["rows"] for r in records) != bronze_manifest.get("row_count"):
        raise ValueError("local versions_full file rows do not sum to Bronze manifest row_count")
    return paths, records, _sha_bytes(marker_raw)


def _validate_derived_versions(curated_outputs: Path, metadata: dict, versions_dir: Path,
                               snapshot: str, snapshot_timestamp: str, bronze_manifest: dict,
                               bronze_ref: dict, con: Any) -> tuple[list[str], list[dict], str]:
    """Validate the full-shaped weekly version file published by Curated.

    ``versions_min`` has no full metadata of its own.  The weekly Curated
    stage publishes an enriched Parquet file and records it in the approved
    Curated manifest; that record, rather than a fabricated raw marker, is the
    authority for this repository input.
    """
    prefix = metadata["run_prefix"] + "/attempts/"
    records = []
    for item in metadata["manifest"].get("files", []):
        key = item.get("key", "")
        if not key.startswith(prefix):
            continue
        relative = key[len(prefix):].split("/", 1)[-1]
        if relative.startswith("weekly_versions/data/") and relative.endswith(".parquet"):
            records.append((relative[len("weekly_versions/data/"):], item))
    if not records:
        raise ValueError("Curated manifest has no weekly_versions/data files")
    root = Path(versions_dir).resolve()
    actual = {p.name: p for p in root.glob("*.parquet")}
    expected = {name for name, _ in records}
    if set(actual) != expected:
        raise ValueError("weekly_versions Parquet files differ from Curated manifest")
    # The derived file must retain the raw min lineage, even though its shape
    # is expanded for the repository transform.
    raw_sha = bronze_manifest.get("source_manifest_sha256")
    if not isinstance(raw_sha, str) or not _SHA.fullmatch(raw_sha):
        raise ValueError("versions_min Bronze source fingerprint is missing")
    paths, output = [], []
    for name, remote in records:
        path = actual[name]
        observed = _file_record(path, root, con, snapshot_timestamp=snapshot_timestamp)
        if observed["bytes"] != remote.get("bytes") or observed["sha256"] != remote.get("sha256"):
            raise ValueError(f"weekly_versions checksum mismatch: {name}")
        if remote.get("rows") is not None and observed["rows"] != remote["rows"]:
            raise ValueError(f"weekly_versions rows mismatch: {name}")
        observed.update({"table": "versions_full", "bronze_key": bronze_ref.get("key", name),
                         "source_table": "versions_min", "source_manifest_sha256": raw_sha})
        paths.append(str(path.resolve()))
        output.append(observed)
    return paths, output, raw_sha


def _validate_projects(projects_dir: Path, prepared_candidate: dict, snapshot: str, snapshot_timestamp: str, con: Any) -> tuple[list[str], list[dict]]:
    inventory = prepared_candidate["inventory"]
    selected = next((row for row in inventory["snapshots"] if row["snapshot"] == snapshot), None)
    if selected is None or selected["snapshot_timestamp"] != snapshot_timestamp + "Z":
        raise ValueError("Projects inventory has no exact target snapshot timestamp")
    root = projects_dir.resolve()
    paths, records = [], []
    expected = {item["path"]: item for item in selected["files"]}
    actual = {p.relative_to(root).as_posix(): p for p in (root / f"snapshot={snapshot}").glob("*.parquet")}
    if set(actual) != set(expected):
        raise ValueError("Projects partition files differ from candidate inventory")
    for relative, item in expected.items():
        record = _file_record(actual[relative], root, con, snapshot_timestamp=snapshot_timestamp)
        if record["bytes"] != item["bytes"] or record["rows"] != item["rows"]:
            raise ValueError(f"Projects file metadata mismatch: {relative}")
        from pipeline.snapshot.projects import _footer_sha256
        footer_sha = _footer_sha256(actual[relative])
        if footer_sha != item.get("parquet_footer_sha256"):
            raise ValueError(f"Projects footer checksum mismatch: {relative}")
        # Keep the footer identity separate from the full-file SHA.  The former
        # is the candidate's Parquet-structure check; the latter detects bytes
        # changed outside the footer as well.
        record.update({"table": "projects", "parquet_footer_sha256": footer_sha, "inventory_path": relative})
        paths.append(str(actual[relative].resolve()))
        records.append(record)
    return paths, records


def prepare_inputs(s3, *, snapshot: str, curated_run_id: str, curated_outputs: Path,
                   versions_dir: Path, projects_dir: Path, candidate_path: Path, output: Path) -> dict:
    """Validate and freeze all read-only inputs for one repository-metrics run."""
    curated = select_run(s3, snapshot, curated_run_id)
    request = curated["manifest"].get("request", {})
    if request.get("bronze_run_id") is None or not isinstance(request.get("sources"), dict):
        raise ValueError("Curated request lacks Bronze lineage")
    bronze_run_id = request["bronze_run_id"]
    version_source = "versions_min" if request["sources"].get("versions_min") is not None else "versions_full"
    bronze_manifest, bronze_ref = load_bronze(s3, version_source, snapshot, bronze_run_id)
    if request["sources"].get(version_source) != bronze_ref:
        raise ValueError(f"Curated {version_source} fingerprint does not match Bronze manifest")
    snapshot_timestamp = _naive_utc(curated["snapshot_timestamp"])
    candidate = read_candidate(candidate_path)
    source_root = Path(candidate["candidate"]["source"]["root"]).resolve()
    if source_root != Path(projects_dir).resolve():
        raise ValueError("candidate source root does not match projects_dir")
    calendar_row = next((r for r in candidate["calendar"] if r["snapshot_at"] == snapshot), None)
    if calendar_row is None or _naive_utc(calendar_row["snapshot_timestamp"]) != snapshot_timestamp:
        raise ValueError("Curated and candidate snapshot timestamps differ")
    output = Path(output).resolve()
    source_roots = [Path(curated_outputs).resolve(), Path(versions_dir).resolve(), Path(projects_dir).resolve(), Path(candidate_path).resolve().parent]
    if any(output == root or root in output.parents for root in source_roots):
        raise ValueError("output must be outside input roots")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise ValueError(f"input manifest already exists: {output}")
    with duckdb.connect(config={"threads": 1, "memory_limit": "512MB"}) as con:
        curated_paths, curated_records = _validate_curated_files(Path(curated_outputs), curated, con)
        if version_source == "versions_min":
            version_paths, version_records, local_versions_manifest_sha = _validate_derived_versions(
                Path(curated_outputs), curated, Path(versions_dir), snapshot, snapshot_timestamp,
                bronze_manifest, bronze_ref, con)
        else:
            version_paths, version_records, local_versions_manifest_sha = _validate_versions(
                Path(versions_dir), snapshot, snapshot_timestamp, bronze_manifest, con)
        project_paths, project_records = _validate_projects(Path(projects_dir), candidate, snapshot, snapshot_timestamp, con)
    files = {"package": curated_paths["package"], "version": curated_paths["version"], "versions_full": version_paths, "projects": project_paths}
    records = curated_records + version_records + project_records
    prepared = {
        "format_version": 1, "dataset": "repository-metrics-input", "snapshot": snapshot,
        "snapshot_timestamp": snapshot_timestamp + "Z", "curated_run_id": curated_run_id,
        "bronze_run_id": bronze_run_id, "curated_manifest_sha256": curated["manifest_sha256"],
        "bronze_run_manifest_sha256": bronze_ref["sha256"], "bronze_source_manifest_sha256": bronze_manifest["source_manifest_sha256"],
        "local_versions_manifest_sha256": local_versions_manifest_sha,
        "candidate_sha256": candidate["candidate_sha256"], "candidate_inventory_sha256": candidate["inventory_sha256"],
        "policy_version": candidate["candidate"]["policy_version"], "policy_sha256": candidate["candidate"]["policy_sha256"],
        "calendar": candidate["calendar"], "files": files,
        "counts": {k: sum(r["rows"] for r in records if r.get("table") == k) for k in _TABLES},
        "file_records": records,
        "sources": {"curated_request": request, "bronze_manifest": bronze_manifest,
                    "candidate_path": str(Path(candidate_path).resolve()),
                    "versions_manifest_path": str(_local_manifest(Path(versions_dir), snapshot)[0].resolve()) if version_source == "versions_full" else None,
                    "projects_dir": str(Path(projects_dir).resolve()),
                    "curated_outputs": str(Path(curated_outputs).resolve()),
                    "versions_dir": str(Path(versions_dir).resolve()),
                    "versions_source": version_source},
    }
    output.write_bytes(_json_bytes(prepared))
    prepared["input_sha256"] = _sha_bytes(output.read_bytes())
    return prepared


def reverify_inputs(prepared: dict, s3=None) -> None:
    """Recheck every frozen local file and, when supplied, remote lineage."""
    if not isinstance(prepared, dict) or prepared.get("format_version") != 1:
        raise ValueError("invalid prepared input manifest")
    for item in prepared.get("file_records", []):
        path = Path(item["path"])
        if not path.is_file() or path.stat().st_size != item["bytes"] or _sha_file(path) != item["sha256"]:
            raise ValueError(f"input file changed: {path}")
    for path_text in (prepared.get("sources", {}).get("candidate_path"),):
        if not path_text or not Path(path_text).is_file():
            raise ValueError("input metadata file missing")
    candidate_path = Path(prepared["sources"]["candidate_path"])
    if _sha_file(candidate_path) != prepared.get("candidate_sha256"):
        raise ValueError("snapshot candidate changed")
    versions_manifest_text = prepared.get("sources", {}).get("versions_manifest_path")
    if versions_manifest_text:
        versions_manifest = Path(versions_manifest_text)
        if not versions_manifest.is_file() or _sha_file(versions_manifest) != prepared.get("local_versions_manifest_sha256"):
            raise ValueError("versions_full manifest changed")
    current_candidate = read_candidate(candidate_path)
    if current_candidate["inventory_sha256"] != prepared.get("candidate_inventory_sha256"):
        raise ValueError("Projects inventory changed")
    for root_key, tables in (("curated_outputs", ("package", "version", "curated_aux")),
                             ("versions_dir", ("versions_full",)), ("projects_dir", ("projects",))):
        root = Path(prepared["sources"][root_key])
        expected = {Path(item["path"]).resolve() for item in prepared["file_records"] if item.get("table") in tables}
        if root_key == "curated_outputs":
            actual = {p.resolve() for p in root.rglob("*") if p.is_file()}
        elif root_key == "versions_dir":
            actual = {p.resolve() for p in root.glob("*.parquet")}
        else:
            actual = {p.resolve() for p in (root / f"snapshot={prepared['snapshot']}").glob("*.parquet")}
        if actual != expected:
            raise ValueError(f"input file set changed under {root_key}")
    if s3 is not None:
        curated = select_run(s3, prepared["snapshot"], prepared["curated_run_id"])
        if curated["manifest_sha256"] != prepared["curated_manifest_sha256"]:
            raise ValueError("Curated manifest changed")
        version_source = prepared.get("sources", {}).get("versions_source", "versions_full")
        bronze, ref = load_bronze(s3, version_source, prepared["snapshot"], prepared["bronze_run_id"])
        if ref["sha256"] != prepared["bronze_run_manifest_sha256"] or bronze["source_manifest_sha256"] != prepared["bronze_source_manifest_sha256"]:
            raise ValueError("Bronze metadata changed")


__all__ = ["prepare_inputs", "reverify_inputs"]
