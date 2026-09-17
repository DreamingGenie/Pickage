"""Versioned, explicit producer references. No latest-object discovery."""
from pipeline.preprocessing.common.paths import REPO_ROOT
from datetime import date
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import subprocess
import sys

from pipeline.preprocessing.snapshot.policy import parse_timestamp

STAGES = ("snapshot", "package_version", "downloads", "repository", "package_snapshot", "dependents")
RUN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
SHA = re.compile(r"[0-9a-f]{64}")


def object_ref(value, label, *, curated_target=False):
    if not isinstance(value, dict):
        raise ValueError(label + " must be an object reference")
    for field in ("bucket", "key", "sha256"):
        if not isinstance(value.get(field), str) or not value[field]:
            raise ValueError(label + "." + field + " is required")
    key = value["key"]
    if ((value["bucket"] != "pickage-raw" and not (curated_target and value["bucket"] == "pickage-curated" and key.startswith("depsdev/v1/preprocessing-targets/"))) or "\\" in key or "\x00" in key
            or any(part in ("", ".", "..") for part in key.split("/"))
            or not SHA.fullmatch(value["sha256"])):
        raise ValueError(label + " has an invalid bucket/key/SHA")
    return value


def iso_day(value):
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError("Expected ISO snapshot date")
    return value


def validate_request(value):
    if not isinstance(value, dict):
        raise ValueError("Request must be a JSON object")
    allowed = {"format_version", "run_id", "snapshot", "snapshot_timestamp", "bronze_run_id",
               "raw_refs", "calendar_refs", "parent", "targets", "options"}
    if value.get("format_version") == 2:
        allowed.update({"parent_bundle", "download_history_refs"})
    missing = allowed - {"options", "download_history_refs"} - value.keys()
    if missing or value.keys() - allowed:
        raise ValueError("Request has missing or unknown fields: " + ", ".join(sorted(missing | (value.keys() - allowed))))
    if type(value["format_version"]) is not int or value["format_version"] not in (1, 2):
        raise ValueError("Unsupported request format_version")
    for field in ("run_id", "bronze_run_id"):
        if not isinstance(value[field], str) or not RUN.fullmatch(value[field]):
            raise ValueError("Invalid " + field)
    snapshot = iso_day(value["snapshot"])
    stamp = value["snapshot_timestamp"]
    if not isinstance(stamp, str) or not stamp.endswith("Z") or parse_timestamp(stamp).date().isoformat() != snapshot:
        raise ValueError("snapshot_timestamp must be UTC Z on the snapshot date")
    raw = value["raw_refs"]
    version_table = "versions_min" if value["format_version"] == 2 else "versions_full"
    if not isinstance(raw, dict) or set(raw) != {version_table, "requirements", "projects", "downloads"}:
        raise ValueError("raw_refs must match the versioned versions table, requirements, projects, downloads")
    for table, ref in raw.items():
        object_ref(ref, "raw_refs." + table)
        if table == "downloads":
            rid = ref.get("run_id")
            if not isinstance(rid, str) or not RUN.fullmatch(rid):
                raise ValueError("downloads.run_id is required")
            expected = f"npm-downloads/v1/run_id={rid}/run_manifest.json"
        else:
            expected = f"depsdev/v1/{table}/snapshot={snapshot}/run_id={value['bronze_run_id']}/run_manifest.json"
        if ref["key"] != expected:
            raise ValueError("Raw ref key does not match pinned identity: " + table)
    history = value.get("download_history_refs", [])
    if not isinstance(history, list):
        raise ValueError("download_history_refs must be a list")
    seen_downloads = {raw["downloads"]["run_id"]}
    for ref in history:
        object_ref(ref, "download_history_refs")
        rid = ref.get("run_id")
        if (not isinstance(rid, str) or not RUN.fullmatch(rid) or rid in seen_downloads
                or ref["key"] != f"npm-downloads/v1/run_id={rid}/run_manifest.json"):
            raise ValueError("Invalid or duplicate download history run")
        seen_downloads.add(rid)
    calendar = value["calendar_refs"]
    if not isinstance(calendar, list) or not calendar:
        raise ValueError("calendar_refs must contain Projects manifest references")
    days = []
    for ref in calendar:
        object_ref(ref, "calendar_refs")
        day = iso_day(ref.get("snapshot"))
        rid = ref.get("run_id")
        if not isinstance(rid, str) or not RUN.fullmatch(rid):
            raise ValueError("Calendar raw run ID missing")
        if day > snapshot or ref["key"] != f"depsdev/v1/projects/snapshot={day}/run_id={rid}/run_manifest.json":
            raise ValueError("Calendar reference date or key mismatch")
        days.append(day)
    if days != sorted(set(days)) or days[-1] != snapshot:
        raise ValueError("Calendar must be unique, ordered and end at snapshot")
    if any(calendar[-1][k] != raw["projects"][k] for k in ("bucket", "key", "sha256")):
        raise ValueError("Calendar and current Projects must use the same pinned source")
    targets = value["targets"]
    if not isinstance(targets, dict) or set(targets) != {"dependents"}:
        raise ValueError("targets.dependents is required; download targets belong to the download manifest")
    object_ref(targets["dependents"], "targets.dependents", curated_target=value["format_version"] == 2)
    parent = value["parent"]
    if parent is not None:
        if (not isinstance(parent, dict) or set(parent) != {"run_prefix", "manifest_sha256", "snapshot"}
                or not isinstance(parent["manifest_sha256"], str) or not SHA.fullmatch(parent["manifest_sha256"])):
            raise ValueError("parent must be the complete package-version pointer or null for bootstrap")
        iso_day(parent["snapshot"])
        if parent["snapshot"] > snapshot:
            raise ValueError("Parent mapping cannot be newer than the requested snapshot")
        prefix_pattern = r"depsdev/v1/package-version/snapshot=" + re.escape(parent["snapshot"]) + r"/run_id=[A-Za-z0-9_-]+"
        if not isinstance(parent["run_prefix"], str) or not re.fullmatch(prefix_pattern, parent["run_prefix"]):
            raise ValueError("Invalid parent run prefix")
        if parent["snapshot"] not in days:
            raise ValueError("Calendar must include the parent snapshot and all available intervening dates")
    if value["format_version"] == 2:
        bundle = value["parent_bundle"]
        if (not isinstance(bundle, dict) or set(bundle) != {"run_prefix", "manifest_sha256", "snapshot"}
                or not isinstance(bundle["manifest_sha256"], str) or not SHA.fullmatch(bundle["manifest_sha256"])
                or not re.fullmatch(r"depsdev/v1/curated-bundle/snapshot=\d{4}-\d{2}-\d{2}/run_id=[A-Za-z0-9_-]+", bundle["run_prefix"])):
            raise ValueError("Weekly input requires a pinned completed parent bundle")
        if parent is None or bundle["snapshot"] != parent["snapshot"] or bundle["snapshot"] >= snapshot:
            raise ValueError("Weekly parent must be an earlier completed snapshot")
        iso_day(bundle["snapshot"])
        if not bundle["run_prefix"].startswith("depsdev/v1/curated-bundle/snapshot=" + bundle["snapshot"] + "/"):
            raise ValueError("Parent bundle prefix date differs")
    options = value.get("options", {})
    if not isinstance(options, dict) or set(options) - {"workers", "threads", "memory_limit", "repository_engine"}:
        raise ValueError("Unknown execution option")
    for field, default, limit in (("workers", 2, 16), ("threads", 2, 32)):
        number = options.get(field, default)
        if type(number) is not int or not 1 <= number <= limit:
            raise ValueError("Invalid option: " + field)
    if not re.fullmatch(r"[1-9][0-9]*(?:MB|GB)", options.get("memory_limit", "2GB")):
        raise ValueError("memory_limit must be an explicit MB or GB value")
    if options.get("repository_engine", "native") not in ("native", "docker"):
        raise ValueError("repository_engine must be native or docker")
    # Return a detached, JSON-only request without inserting mutable defaults.
    return json.loads(json.dumps(value, allow_nan=False))


def code_contract():
    """Fingerprint generator sources and installed execution dependencies."""
    root = REPO_ROOT
    files = {}
    folders = ("preprocessing/orchestration", "preprocessing/common", "preprocessing/curated",
               "preprocessing/snapshot", "downloads", "preprocessing/downloads_interval",
               "preprocessing/repository_metrics", "preprocessing/package_snapshot",
               "preprocessing/version_dependents", "preprocessing/requirements_resolution",
               "minio", "postgresql")
    for folder in folders:
        for path in sorted((root / "pipeline" / folder).rglob("*")):
            if (path.is_file() and path.suffix in (".py", ".cjs", ".json")
                    and not {"node_modules", "tests"}.intersection(path.parts)
                    and not path.name.startswith("test_")):
                files[path.relative_to(root).as_posix()] = hashlib.sha256(
                    path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    runtime = {}
    for package in ("duckdb", "boto3", "botocore", "numpy"):
        try:
            runtime[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            runtime[package] = None
    runtime["python"] = list(sys.version_info[:3])
    from pipeline.preprocessing.requirements_resolution.bridge import discover_runtime
    resolver = discover_runtime()
    runtime["node"] = subprocess.run([resolver["node"], "--version"], check=True,
                                     capture_output=True, text=True, timeout=10).stdout.strip()
    for name in ("semver_module", "package_arg_module"):
        directory = Path(resolver[name])
        runtime[name] = {path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                         for path in sorted(directory.rglob("*")) if path.is_file() and path.suffix in (".js", ".json")}
    return {"files": files, "runtime": runtime}


def version_table(request):
    return "versions_min" if request["format_version"] == 2 else "versions_full"
