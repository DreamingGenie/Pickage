"""Build a pinned orchestration request from a completed weekly raw receipt."""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from pipeline.orchestration.contracts import RUN, iso_day, validate_request
from pipeline.orchestration.storage import PREFIX, required, sha

RAW_BUCKET = "pickage-raw"
CURATED_BUCKET = "pickage-curated"


def _ref(s3, bucket, key, *, extras=None):
    body = required(s3, bucket, key)
    value = {"bucket": bucket, "key": key, "sha256": sha(body)}
    if extras:
        value.update(extras)
    return value


def _project_timestamp(s3, manifest):
    import tempfile
    import duckdb
    from pipeline.curated.storage import download_files
    from pipeline.snapshot.policy import parse_timestamp
    values = set()
    with tempfile.TemporaryDirectory(prefix="weekly-projects-") as directory:
        files = download_files(s3, RAW_BUCKET, manifest["files"], Path(directory), workers=1)
        with duckdb.connect(config={"threads": 1, "memory_limit": "256MB"}) as con:
            for path in files:
                rows = con.execute("SELECT DISTINCT SnapshotAt FROM read_parquet(?, hive_partitioning=false)", [str(path)]).fetchall()
                if any(row[0] is None for row in rows):
                    raise ValueError("Projects SnapshotAt cannot be NULL")
                values.update(row[0] for row in rows)
    if len(values) != 1:
        raise ValueError("Projects input must contain one exact SnapshotAt")
    return parse_timestamp(next(iter(values)).isoformat(), allow_naive_utc=True).isoformat().replace("+00:00", "Z")


def _target_ref(s3, manifest, snapshot, run_id, work_dir):
    from pipeline.curated.storage import put_immutable
    import duckdb
    targets = [item for item in manifest["files"] if item["role"] == "target_csv"]
    if len(targets) != 1:
        raise ValueError("Downloads manifest must contain one target_csv")
    target = targets[0]
    key = f"npm-downloads/v1/run_id={manifest['run_id']}/data/{target['path']}"
    body = required(s3, RAW_BUCKET, key)
    if len(body) != target["bytes"] or sha(body) != target["sha256"]:
        raise ValueError("Downloads target CSV checksum mismatch")
    reader = csv.DictReader(io.StringIO(body.decode("utf-8-sig")))
    if not reader.fieldnames or "name" not in reader.fieldnames:
        raise ValueError("Downloads target CSV requires name column")
    names = [row["name"] for row in reader]
    if (not names or len(names) != target["row_count"]
            or any(not name or name != name.strip() or "\x00" in name for name in names)):
        raise ValueError("Downloads target CSV names must be nonempty and match approved row count")
    out = Path(work_dir).resolve() / "targets" / run_id / "targets.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(config={"threads": 1, "memory_limit": "256MB"}) as con:
        con.execute("CREATE TABLE targets(name VARCHAR)")
        con.executemany("INSERT INTO targets VALUES (?)", [(name,) for name in sorted(set(names))])
        con.execute("COPY targets TO ? (FORMAT PARQUET)", [str(out)])
    payload = out.read_bytes()
    key = f"depsdev/v1/preprocessing-targets/snapshot={snapshot}/run_id={run_id}/targets.parquet"
    put_immutable(s3, CURATED_BUCKET, key, payload)
    return {"bucket": CURATED_BUCKET, "key": key, "sha256": sha(payload)}


def _parent_from_bundle(bundle):
    if not bundle:
        return None
    if not isinstance(bundle, dict) or not {"run_prefix", "manifest_sha256", "snapshot"} <= set(bundle):
        raise ValueError("parent_bundle must identify a completed bundle")
    return {"run_prefix": bundle["run_prefix"], "manifest_sha256": bundle["manifest_sha256"], "snapshot": bundle["snapshot"]}


def build_request(s3, snapshot, run_id, work_dir, *, bronze_run_id=None,
                  download_run_id=None, parent_bundle=None, options=None,
                  download_history_run_ids=None):
    """Create a fully pinned v2 request; missing receipts raise WaitingInput."""
    iso_day(snapshot)
    if not isinstance(run_id, str) or not RUN.fullmatch(run_id):
        raise ValueError("Invalid weekly run_id")
    bronze_run_id = bronze_run_id or f"bronze-weekly-{snapshot.replace('-', '')}"
    download_run_id = download_run_id or f"downloads-weekly-{snapshot.replace('-', '')}"
    for value in (bronze_run_id, download_run_id, *(download_history_run_ids or [])):
        if not isinstance(value, str) or not RUN.fullmatch(value):
            raise ValueError("Invalid weekly raw run ID")
    base = "depsdev/v1"
    version_key = f"{base}/versions_min/snapshot={snapshot}/run_id={bronze_run_id}/run_manifest.json"
    req_key = f"{base}/requirements/snapshot={snapshot}/run_id={bronze_run_id}/run_manifest.json"
    project_key = f"{base}/projects/snapshot={snapshot}/run_id={bronze_run_id}/run_manifest.json"
    download_key = f"npm-downloads/v1/run_id={download_run_id}/run_manifest.json"
    versions = _ref(s3, RAW_BUCKET, version_key)
    requirements = _ref(s3, RAW_BUCKET, req_key)
    projects = _ref(s3, RAW_BUCKET, project_key, extras={"snapshot": snapshot, "run_id": bronze_run_id})
    downloads = _ref(s3, RAW_BUCKET, download_key, extras={"run_id": download_run_id})
    from pipeline.curated.build import load_bronze
    from pipeline.downloads_interval.input import _bronze
    from .intake import _check_marker
    for ref in (versions, requirements, projects, downloads):
        _check_marker(s3, ref)
    for table, ref in (("versions_min", versions), ("requirements", requirements), ("projects", projects)):
        manifest, fingerprint = load_bronze(s3, table, snapshot, bronze_run_id)
        if fingerprint["sha256"] != ref["sha256"]:
            raise ValueError("Producer manifest changed during request preparation")
        if table == "projects":
            project_manifest = manifest
    download_manifest, _ = _bronze(s3, download_run_id, downloads["sha256"])
    stamp = _project_timestamp(s3, project_manifest)
    target = _target_ref(s3, download_manifest, snapshot, run_id, work_dir)
    current = {"snapshot": snapshot, "run_id": bronze_run_id, **projects}
    if parent_bundle is None:
        pointer_body = required(s3, CURATED_BUCKET, PREFIX + "/_current.json")
        parent_bundle = json.loads(pointer_body.decode("utf-8"))
        if not isinstance(parent_bundle, dict):
            raise ValueError("Curated current pointer is malformed")
    parent = _parent_from_bundle(parent_bundle)
    from .weekly_parent import read_bundle
    bundle = read_bundle(s3, parent)
    prior_request = bundle.get("request", {})
    calendar = list(prior_request.get("calendar_refs", []))
    calendar.append(current)
    package_stage = bundle.get("stages", {}).get("package_version", {})
    package_parent = {"run_prefix": package_stage.get("prefix", ""),
                      "manifest_sha256": package_stage.get("manifest_sha256", ""),
                      "snapshot": parent["snapshot"]}
    request = {"format_version": 2, "run_id": run_id, "snapshot": snapshot,
               "snapshot_timestamp": stamp, "bronze_run_id": bronze_run_id,
               "parent": package_parent,
               "parent_bundle": parent,
               "raw_refs": {"versions_min": versions, "requirements": requirements,
                            "projects": projects, "downloads": downloads},
               "calendar_refs": calendar, "targets": {"dependents": target},
               "options": options or {"workers": 1, "threads": 1, "memory_limit": "1GB",
                                       "repository_engine": "native"}}
    if download_history_run_ids:
        history = []
        for history_id in download_history_run_ids:
            ref = _ref(s3, RAW_BUCKET, f"npm-downloads/v1/run_id={history_id}/run_manifest.json",
                       extras={"run_id": history_id})
            _check_marker(s3, ref)
            _bronze(s3, history_id, ref["sha256"])
            history.append(ref)
        request["download_history_refs"] = history
    # Validate the full immutable input contract before execution.
    return validate_request(request)


__all__ = ["build_request"]
