"""Freeze identical stage inputs without publishing or moving production IDs."""
import copy
import hashlib
import json
from pathlib import Path
import time

from pipeline.curated.storage import download_files, json_bytes
from pipeline.orchestration.runner import run
from pipeline.orchestration.contracts import validate_request
from .overlay import OverlayS3

STAGES = ("package_version", "downloads", "repository", "package_snapshot", "dependents")


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def file_references(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from file_references(item)
    elif isinstance(value, list):
        for item in value:
            yield from file_references(item)
    elif isinstance(value, str):
        try:
            path = Path(value)
            if path.is_file():
                yield path.resolve()
        except OSError:
            pass


def prepare(s3, request, directory):
    request = validate_request(request)
    root = Path(directory).resolve()
    root.mkdir(parents=True, exist_ok=False)
    began = time.perf_counter()
    private = copy.deepcopy(request)
    private["run_id"] = "ref"
    overlay = OverlayS3(s3, root / "objects", private["parent"])
    bundle = run(private, overlay, root / "w")
    stages = bundle["stages"]
    work = root / "w" / "ref"
    candidate = stages["snapshot"]["metadata"]
    cache = root / "cached"

    def fetch(records, bucket="pickage-curated"):
        return [str(p) for p in download_files(overlay, bucket, records, cache, workers=1)]

    populations = {}
    for role in ("package", "version"):
        populations[role] = fetch([r for r in stages["package_version"]["files"] if f"/{role}/data/" in r["key"]])
    raw = {}
    for role in ("versions_full", "requirements"):
        raw[role] = [str(p) for p in sorted((work / "inputs" / role).rglob("*.parquet"))]
    previous = None
    if private["parent"]:
        prefix = private["parent"]["run_prefix"]
        manifest = json.loads(overlay.get_object(Bucket="pickage-curated", Key=prefix + "/run_manifest.json")["Body"].read())
        previous = fetch([r for r in manifest["files"] if "/package_ids/data/" in r["key"]])

    from pipeline.downloads_interval.input import prepare as downloads_prepare
    dl = request["raw_refs"]["downloads"]
    downloads = downloads_prepare(overlay, snapshot=request["snapshot"], bronze_run_id=dl["run_id"],
        bronze_manifest_sha256=dl["sha256"], curated_run_id="ref",
        curated_manifest_sha256=stages["package_version"]["manifest_sha256"],
        candidate_path=Path(candidate["candidate_path"]), candidate_sha256=candidate["candidate_sha256"],
        cache_dir=root / "d", workers=1)
    from pipeline.downloads_interval.policy import policy_sha256
    downloads["lineage"]["aggregation_policy_sha256"] = policy_sha256()
    from pipeline.package_snapshot.input import prepare as snapshot_prepare
    snapshot = snapshot_prepare(overlay, snapshot=request["snapshot"], population_run_id="ref",
        population_manifest_sha256=stages["package_version"]["manifest_sha256"],
        candidate_path=Path(candidate["candidate_path"]), candidate_sha256=candidate["candidate_sha256"],
        download_run_id="ref", download_manifest_sha256=stages["downloads"]["manifest_sha256"],
        repository_run_id="ref", repository_manifest_sha256=stages["repository"]["manifest_sha256"],
        cache_dir=root / "p", workers=1)
    repo = json.loads(overlay.get_object(Bucket="pickage-curated", Key=stages["repository"]["manifest_key"])["Body"].read())["input"]
    payload = {
        "package_version": {"versions": raw["versions_full"], "requirements": raw["requirements"],
                            "previous_ids": previous, "snapshot": request["snapshot"]},
        "downloads": downloads, "repository": repo, "package_snapshot": snapshot,
        "dependents": {"files": {**populations, **raw, "targets": str(work / "inputs" / "dependents-targets.parquet")},
                       "snapshot": request["snapshot"], "snapshot_timestamp": request["snapshot_timestamp"]},
    }
    inventory = [{"path": str(p), "bytes": p.stat().st_size, "sha256": digest(p)}
                 for p in sorted(set(file_references(payload)))]
    manifest = {"format_version": 1, "scope": "FIXED_STAGE_INPUT_COMPARISON", "source_request": request,
                "baseline_commit": "df775b8", "stages": payload, "input_files": inventory,
                "preparation_seconds": time.perf_counter() - began,
                "production_writes": False, "db_loaded": False}
    (root / "experiment.json").write_bytes(json_bytes(manifest))
    return root / "experiment.json"


def verify_inputs(manifest):
    for record in manifest["input_files"]:
        path = Path(record["path"])
        if not path.is_file() or path.stat().st_size != record["bytes"] or digest(path) != record["sha256"]:
            raise ValueError("Frozen experiment input changed: " + record["path"])
