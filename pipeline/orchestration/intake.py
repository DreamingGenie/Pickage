"""Pinned MinIO input validation and local hydration."""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
import shutil
from typing import Any, Mapping

from .contracts import validate_request, version_table

def _body(s3, bucket, key):
    stream = s3.get_object(Bucket=bucket, Key=key)["Body"]
    try: return stream.read()
    finally:
        if getattr(stream, "close", None): stream.close()

def _missing(error):
    return str(getattr(error, "response", {}).get("Error", {}).get("Code", "")) in {"404", "NoSuchKey", "NotFound"}

def _safe(value):
    path = PurePosixPath(value)
    if not value or path.is_absolute() or "\\" in value or any(p in ("", ".", "..") for p in path.parts):
        raise ValueError(f"unsafe input path: {value!r}")
    return path.as_posix()

def _file_sha(path):
    digest = hashlib.sha256(); size = 0
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk); size += len(chunk)
    return size, digest.hexdigest()

def _check_ref(s3, ref, waiting=False):
    try: body = _body(s3, ref["bucket"], ref["key"])
    except Exception as error:
        if waiting and _missing(error):
            from .storage import WaitingInput
            raise WaitingInput(f"Required object has not arrived: {ref['bucket']}/{ref['key']}") from error
        raise
    if hashlib.sha256(body).hexdigest() != ref["sha256"]:
        raise ValueError("Pinned object SHA mismatch: " + ref["key"])
    return body

def _check_marker(s3, ref):
    from .storage import WaitingInput
    key = ref["key"].rsplit("/", 1)[0] + "/_SUCCESS"
    try: body = _body(s3, ref["bucket"], key)
    except Exception as error:
        if _missing(error): raise WaitingInput("Producer completion marker has not arrived: " + key) from error
        raise
    if body not in (b"", ref["sha256"].encode() + b"\n"):
        try: marker = json.loads(body)
        except json.JSONDecodeError as error: raise ValueError("Invalid producer completion marker") from error
        if marker.get("manifest_sha256") != ref["sha256"]: raise ValueError("Producer marker SHA mismatch")

def hydrate_ref(s3, ref: Mapping[str, Any], target: Path) -> Path:
    from pipeline.curated.storage import download_files
    from .storage import WaitingInput
    target = Path(target).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        size = s3.head_object(Bucket=ref["bucket"], Key=ref["key"])["ContentLength"]
        cached = download_files(s3, ref["bucket"], [{**ref, "bytes": size}], target.parent / ".ref-cache", workers=1)[0]
    except Exception as error:
        if _missing(error):
            raise WaitingInput("Required object has not arrived: " + ref["key"]) from error
        raise
    if target.exists():
        if _file_sha(target) != (size, ref["sha256"]):
            raise ValueError("Hydrated object differs: " + str(target))
    else:
        shutil.copyfile(cached, target)
    return target

def hydrate_bronze(s3, ref, root: Path, *, table: str, snapshot: str, run_id: str, source_manifest=True) -> dict:
    """Verify one native raw run and materialize its files; preserve source receipt as _MANIFEST.json."""
    from pipeline.curated.build import load_bronze
    prefix = ref["key"].rsplit("/", 1)[0]; manifest_body = _check_ref(s3, ref, waiting=True)
    _check_marker(s3, ref)
    if table in {"versions_full", "versions_min", "requirements", "projects"}:
        manifest, _ = load_bronze(s3, table, snapshot, run_id)
    else: raise ValueError("Unsupported raw table: " + table)
    rows = manifest.get("files")
    if not isinstance(rows, list) or not rows: raise ValueError("Bronze manifest has no files")
    root = Path(root).resolve(); destination = root / (f"snapshot={snapshot}" if table == "projects" else "")
    destination.mkdir(parents=True, exist_ok=True)
    try: source_body = _body(s3, ref["bucket"], prefix + "/source_manifest.json")
    except Exception as error:
        if _missing(error):
            from .storage import WaitingInput
            raise WaitingInput("Bronze source manifest has not arrived: " + prefix) from error
        raise
    source = json.loads(source_body)
    if table != "projects" and (source.get("status"), source.get("verify")) != ("done", "ok"):
        raise ValueError("Bronze source receipt is not verified")
    (destination / "_MANIFEST.json").write_bytes(source_body)
    cache = root.parent / ".raw-cache"
    from pipeline.curated.storage import download_files
    for row in rows:
        key = row.get("key"); path = row.get("path") or (Path(key).name if isinstance(key, str) else None)
        if not isinstance(key, str) or not isinstance(path, str): raise ValueError("Bronze file requires key/path")
        path = _safe(path)
        record = {"key": key, "bytes": row.get("bytes"), "sha256": row.get("sha256")}
        cached = download_files(s3, ref["bucket"], [record], cache, workers=1)[0]
        target = (destination / path).resolve()
        if not target.is_relative_to(destination): raise ValueError("Bronze file escapes destination")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if _file_sha(target) != (record["bytes"], record["sha256"]):
                raise ValueError("Hydrated Bronze file differs")
        else: shutil.copyfile(cached, target)
    return manifest

def _check_schema(root: Path, expected: dict[str, str]) -> None:
    import duckdb
    files = sorted(Path(root).rglob("*.parquet"))
    if not files: raise ValueError("No Parquet files for schema validation")
    for path in files:
        with duckdb.connect(config={"threads": 1, "memory_limit": "256MB"}) as con:
            schema = dict((r[0], str(r[1]).upper()) for r in con.execute("DESCRIBE SELECT * FROM read_parquet(?, hive_partitioning=false)", [str(path)]).fetchall())
        if any(name not in schema or schema[name].replace('"', '') != kind.upper().replace('"', '')
               for name, kind in expected.items()):
            raise ValueError(f"Raw schema mismatch: {path}")

def _check_timestamp(root: Path, expected: str) -> None:
    import duckdb
    want = datetime.fromisoformat(expected.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
    files = sorted(Path(root).rglob("*.parquet"))
    if not files: raise ValueError("No Parquet files for timestamp validation")
    found_column = False
    with duckdb.connect(config={"threads": 1, "memory_limit": "256MB"}) as con:
        for path in files:
            columns = {row[0] for row in con.execute("DESCRIBE SELECT * FROM read_parquet(?, hive_partitioning=false)", [str(path)]).fetchall()}
            if "SnapshotAt" not in columns: raise ValueError(f"SnapshotAt column is missing: {path}")
            found_column = True
            minimum, maximum, rows, nonnull = con.execute(
                "SELECT min(SnapshotAt), max(SnapshotAt), count(*), count(SnapshotAt) FROM read_parquet(?, hive_partitioning=false)", [str(path)]).fetchone()
            if rows == 0:
                continue  # Empty requirements are a recorded source gap, not a different timestamp.
            if rows != nonnull or minimum is None or minimum.replace(tzinfo=None) != want or maximum.replace(tzinfo=None) != want:
                raise ValueError(f"SnapshotAt timestamp mismatch: {path}")
    if not found_column: raise ValueError("SnapshotAt column is missing")

def preflight(s3, request: dict, work_dir: Path) -> dict:
    from .storage import WaitingInput
    request = validate_request(request); work = Path(work_dir).resolve()
    from pipeline.curated.storage import read_optional
    current = read_optional(s3, "pickage-curated", "depsdev/v1/package-version/_current.json")
    if current is not None:
        pointer = json.loads(current[0])
        own = f"depsdev/v1/package-version/snapshot={request['snapshot']}/run_id={request['run_id']}"
        parent = request.get("parent")
        if pointer.get("run_prefix") != own and pointer != parent:
            raise ValueError("Current package-version pointer does not match request.parent")
    elif request.get("parent") is not None:
        raise ValueError("Request parent pointer does not exist")
    if request["format_version"] == 2:
        from .weekly_parent import validate_parent
        validate_parent(s3, request)
    versions = version_table(request)
    manifests = {}
    for table in (versions, "requirements"):
        manifests[table] = hydrate_bronze(s3, request["raw_refs"][table], work / "inputs" / table,
                                          table=table, snapshot=request["snapshot"], run_id=request["bronze_run_id"])
    projects = work / "inputs" / "projects"
    for ref in request["calendar_refs"]:
        hydrate_bronze(s3, ref, projects, table="projects", snapshot=ref["snapshot"], run_id=ref["run_id"])
    _check_timestamp(Path(work) / "inputs" / versions, request["snapshot_timestamp"])
    _check_timestamp(Path(work) / "inputs" / "requirements", request["snapshot_timestamp"])
    _check_timestamp(projects / ("snapshot=" + request["snapshot"]), request["snapshot_timestamp"])
    schema = {"Name": "VARCHAR", "Version": "VARCHAR", "published_at": "TIMESTAMP", "is_release": "BOOLEAN", "ordinal": "BIGINT", "Deprecated": "VARCHAR", "SnapshotAt": "TIMESTAMP"}
    if versions == "versions_full":
        schema.update(Description="VARCHAR", Licenses="VARCHAR[]", source_repo="VARCHAR")
    _check_schema(Path(work) / "inputs" / versions, schema)
    _check_schema(Path(work) / "inputs" / "requirements", {"Name": "VARCHAR", "Version": "VARCHAR", "Dependencies": "STRUCT(\"Name\" VARCHAR, \"Requirement\" VARCHAR)[]", "PeerDependencies": "STRUCT(\"Name\" VARCHAR, \"Requirement\" VARCHAR)[]", "OptionalDependencies": "STRUCT(\"Name\" VARCHAR, \"Requirement\" VARCHAR)[]", "SnapshotAt": "TIMESTAMP"})
    _check_schema(projects / ("snapshot=" + request["snapshot"]), {"Type": "VARCHAR", "project_name": "VARCHAR", "StarsCount": "BIGINT", "OpenIssuesCount": "BIGINT", "SnapshotAt": "TIMESTAMP"})
    from pipeline.downloads_interval.input import _bronze
    download_ref = request["raw_refs"]["downloads"]
    _check_ref(s3, download_ref, waiting=True)
    _check_marker(s3, download_ref)
    try: downloads, download_prefix = _bronze(s3, download_ref["run_id"], download_ref["sha256"])
    except Exception as error:
        if _missing(error): raise WaitingInput("Download Bronze manifest has not arrived") from error
        raise
    for row in downloads.get("files", []):
        key = download_prefix + "/data/" + row["path"]
        try: head = s3.head_object(Bucket=download_ref["bucket"], Key=key)
        except Exception as error:
            if _missing(error): raise WaitingInput("Download Bronze file has not arrived: " + key) from error
            raise
        if int(head.get("ContentLength", -1)) != row.get("bytes"):
            raise ValueError("Download Bronze file size mismatch: " + key)
    for ref in request.get("download_history_refs", []):
        _check_ref(s3, ref, waiting=True)
        _check_marker(s3, ref)
        _bronze(s3, ref["run_id"], ref["sha256"])
    target = request["targets"]["dependents"]
    if not target["key"].endswith(".parquet"):
        raise ValueError("Dependents target must be a direct Parquet reference")
    target_path = work / "inputs" / "dependents-targets.parquet"
    hydrate_ref(s3, target, target_path)
    import duckdb
    with duckdb.connect(config={"threads": 1, "memory_limit": "256MB"}) as con:
        schema = [(r[0], str(r[1]).upper()) for r in con.execute("DESCRIBE SELECT * FROM read_parquet(?, hive_partitioning=false)", [str(target_path)]).fetchall()]
    if schema != [("name", "VARCHAR")]: raise ValueError("Dependents target schema must be name VARCHAR")
    with duckdb.connect(config={"threads": 1, "memory_limit": "256MB"}) as con:
        total, invalid, duplicate = con.execute(
            "SELECT count(*),count(*) FILTER (WHERE name IS NULL OR trim(name)='' OR name<>trim(name) OR contains(name,chr(0))), "
            "count(*) - count(DISTINCT name) FROM read_parquet(?, hive_partitioning=false)", [str(target_path)]).fetchone()
    if not total or invalid or duplicate: raise ValueError("Dependents target names must be nonempty and unique")
    return {"status": "INPUT_READY", "projects_root": str(projects), "versions_root": str(work / "inputs" / versions),
            "requirements_root": str(work / "inputs" / "requirements"), "downloads": downloads,
            "target_path": str(target_path), "manifests": manifests}
