"""Connect native producers using their actual manifests and immutable outputs."""
import json
from pathlib import Path
import uuid

from pipeline.curated.storage import download_files, json_bytes, put_immutable, read_optional, verify_files
from .storage import BUCKET, atomic_json, required, sha

PREFIXES = {"snapshot": "depsdev/v1/snapshot-reference", "package_version": "depsdev/v1/package-version",
            "downloads": "npm-downloads-interval/v1", "repository": "depsdev/v1/repository-metrics",
            "package_snapshot": "depsdev/v1/package-snapshot"}


def prefix_for(name, request):
    return f"{PREFIXES[name]}/snapshot={request['snapshot']}/run_id={request['run_id']}"


def describe(name, request, s3, *, metadata=None):
    prefix = prefix_for(name, request)
    body = required(s3, BUCKET, prefix + "/run_manifest.json")
    manifest = json.loads(body)
    marker = required(s3, BUCKET, prefix + "/_SUCCESS")
    expected = sha(body)
    if name in ("downloads", "package_snapshot"):
        valid_marker = marker == (expected + "\n").encode()
    else:
        valid_marker = json.loads(marker) == {"manifest_sha256": expected}
    if not valid_marker or manifest.get("status") != "PASSED":
        raise ValueError("Native stage manifest/marker not approved: " + name)
    files = []
    for record in manifest["files"]:
        record = dict(record)
        if "key" not in record:
            base = prefix + ("/data/" if name in ("downloads", "package_snapshot") else "/")
            record["key"] = base + record["path"]
        files.append(record)
    return {"stage": name, "run_id": request["run_id"], "snapshot": request["snapshot"],
            "status": "PASSED", "bucket": BUCKET, "prefix": prefix,
            "manifest_key": prefix + "/run_manifest.json", "manifest_sha256": expected,
            "marker_key": prefix + "/_SUCCESS", "marker_sha256": sha(marker), "files": files,
            "quality": manifest.get("quality", manifest.get("report", {})), "metadata": metadata or {}}


def _restore_files(s3, records, root, relative, workers):
    root = Path(root)
    paths = download_files(s3, BUCKET, records, root.parent / "download-cache", workers=workers)
    for record, path in zip(records, paths):
        target = (root / relative(record)).resolve()
        if not target.is_relative_to(root.resolve()):
            raise ValueError("Hydrated output escapes directory")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            from pipeline.requirements_resolution.input import file_sha256
            if target.stat().st_size != record["bytes"] or file_sha256(target) != record["sha256"]:
                raise ValueError("Saved local stage output differs")
        else:
            import shutil
            shutil.copyfile(path, target)


def _snapshot(request, s3, work, workers):
    from .intake import hydrate_bronze
    from pipeline.snapshot.build import prepare
    from pipeline.snapshot.input import read_candidate
    projects = work / "inputs" / "projects"
    for ref in request["calendar_refs"]:
        hydrate_bronze(s3, ref, projects, table="projects", snapshot=ref["snapshot"], run_id=ref["run_id"])
    prefix = prefix_for("snapshot", request)
    output = work / "snapshot"
    candidate = output / "snapshot-candidate.json"
    remote = read_optional(s3, BUCKET, prefix + "/run_manifest.json")
    if remote is not None:
        manifest = json.loads(remote[0])
        if manifest.get("request") != request:
            raise ValueError("Snapshot reference belongs to another request")
        verify_files(s3, BUCKET, manifest["files"], workers=workers)
        _restore_files(s3, manifest["files"], output, lambda r: r["key"].split("/data/", 1)[1], workers)
    if not candidate.exists():
        attempt = work / ("snapshot-prepare-" + uuid.uuid4().hex)
        prepare(projects, attempt)
        # Same-volume rename publishes the three related files together locally.
        # Incomplete preparation directories are retained as failed-attempt evidence.
        attempt.rename(output)
    checked = read_candidate(candidate)
    interval = next(row for row in checked["calendar"] if row["snapshot_at"] == request["snapshot"])
    from pipeline.snapshot.policy import parse_timestamp
    if parse_timestamp(interval["snapshot_timestamp"]) != parse_timestamp(request["snapshot_timestamp"]):
        raise ValueError("Calendar exact timestamp differs from request")
    records = []
    for filename in ("projects-inventory.json", "snapshot-dates.sql", "snapshot-candidate.json"):
        body = (output / filename).read_bytes()
        key = prefix + "/data/" + filename
        put_immutable(s3, BUCKET, key, body)
        records.append({"key": key, "bytes": len(body), "sha256": sha(body)})
    manifest = {"format_version": 1, "dataset": "snapshot-reference", "status": "PASSED",
                "request": request, "snapshot": request["snapshot"], "run_id": request["run_id"],
                "files": records, "calendar": checked["calendar"], "candidate_sha256": checked["candidate_sha256"]}
    body = json_bytes(manifest)
    put_immutable(s3, BUCKET, prefix + "/run_manifest.json", body)
    verify_files(s3, BUCKET, records, workers=workers)
    put_immutable(s3, BUCKET, prefix + "/_SUCCESS", json_bytes({"manifest_sha256": sha(body)}))
    return describe("snapshot", request, s3, metadata={"candidate_path": str(candidate),
                    "candidate_sha256": checked["candidate_sha256"], "projects_dir": str(projects)})


def execute_stage(name, request, completed, s3, work_dir):
    if name not in PREFIXES:
        raise ValueError("Unknown stage: " + name)
    work = Path(work_dir).resolve()
    options = request.get("options", {})
    workers, threads = options.get("workers", 2), options.get("threads", 2)
    memory = options.get("memory_limit", "2GB")
    snapshot, run_id = request["snapshot"], request["run_id"]
    if name == "snapshot":
        return _snapshot(request, s3, work, workers)
    if name == "package_version":
        from pipeline.curated.build import run
        run(s3, snapshot, request["bronze_run_id"], run_id, work / "package-version",
            workers=workers, threads=threads, memory=memory, expected_parent=request["parent"])
        return describe(name, request, s3)
    candidate_info = completed["snapshot"]["metadata"]
    candidate = Path(candidate_info["candidate_path"])
    population = completed["package_version"]
    common = {"snapshot": snapshot, "run_id": run_id, "s3": s3, "workers": workers,
              "threads": threads, "memory_limit": memory, "candidate_path": candidate,
              "candidate_sha256": candidate_info["candidate_sha256"]}
    if name == "downloads":
        from pipeline.downloads_interval.load import run
        raw = request["raw_refs"]["downloads"]
        run(**common, bronze_run_id=raw["run_id"], bronze_manifest_sha256=raw["sha256"],
            curated_run_id=run_id, curated_manifest_sha256=population["manifest_sha256"], work_dir=work / "downloads")
    elif name == "repository":
        from .intake import hydrate_bronze
        from pipeline.repository_metrics.build import run
        local_curated = work / "inputs" / "curated"
        _restore_files(s3, population["files"], local_curated,
                       lambda r: r["key"].split("/attempts/", 1)[1].split("/", 1)[1], workers)
        versions = work / "inputs" / "versions_full"
        hydrate_bronze(s3, request["raw_refs"]["versions_full"], versions,
                       table="versions_full", snapshot=snapshot, run_id=request["bronze_run_id"])
        local_lock = work / "repository" / run_id / ".writer.lock"
        if local_lock.exists():
            raise ValueError("Repository local writer lock is held")
        atomic_json(work / "repository-local-lock-owner.json", {"run_id": run_id})
        run(s3, snapshot=snapshot, curated_run_id=run_id, curated_outputs=local_curated,
            versions_dir=versions, projects_dir=Path(candidate_info["projects_dir"]),
            candidate_path=candidate, run_id=run_id, work_dir=work / "repository",
            threads=threads, driver_memory=memory.lower().replace("gb", "g").replace("mb", "m"),
            publish=True, engine=options.get("repository_engine", "native"))
    else:
        from pipeline.package_snapshot.build import run
        run(**common, population_run_id=run_id, population_manifest_sha256=population["manifest_sha256"],
            download_run_id=run_id, download_manifest_sha256=completed["downloads"]["manifest_sha256"],
            repository_run_id=run_id, repository_manifest_sha256=completed["repository"]["manifest_sha256"],
            work_dir=work / "package-snapshot")
    return describe(name, request, s3)
