"""Versioned, explicit producer references. No latest-object discovery."""
from datetime import date
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import subprocess
import sys

from pipeline.snapshot.policy import parse_timestamp

STAGES = ("snapshot", "package_version", "downloads", "repository", "package_snapshot", "dependents")
RUN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
SHA = re.compile(r"[0-9a-f]{64}")


def object_ref(value, label):
    if not isinstance(value, dict):
        raise ValueError(label + " must be an object reference")
    for field in ("bucket", "key", "sha256"):
        if not isinstance(value.get(field), str) or not value[field]:
            raise ValueError(label + "." + field + " is required")
    key = value["key"]
    if (value["bucket"] != "pickage-raw" or "\\" in key or "\x00" in key
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
    missing = allowed - {"options"} - value.keys()
    if missing or value.keys() - allowed:
        raise ValueError("Request has missing or unknown fields: " + ", ".join(sorted(missing | (value.keys() - allowed))))
    if type(value["format_version"]) is not int or value["format_version"] != 1:
        raise ValueError("Unsupported request format_version")
    for field in ("run_id", "bronze_run_id"):
        if not isinstance(value[field], str) or not RUN.fullmatch(value[field]):
            raise ValueError("Invalid " + field)
    snapshot = iso_day(value["snapshot"])
    stamp = value["snapshot_timestamp"]
    if not isinstance(stamp, str) or not stamp.endswith("Z") or parse_timestamp(stamp).date().isoformat() != snapshot:
        raise ValueError("snapshot_timestamp must be UTC Z on the snapshot date")
    raw = value["raw_refs"]
    if not isinstance(raw, dict) or set(raw) != {"versions_full", "requirements", "projects", "downloads"}:
        raise ValueError("raw_refs requires versions_full, requirements, projects, downloads")
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
    object_ref(targets["dependents"], "targets.dependents")
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
    root = Path(__file__).resolve().parents[2]
    files = {}
    folders = ("orchestration", "curated", "snapshot", "downloads", "downloads_interval",
               "repository_metrics", "package_snapshot", "version_dependents", "requirements_resolution",
               "minio", "postgresql")
    for folder in folders:
        for path in sorted((root / "pipeline" / folder).rglob("*")):
            if (path.is_file() and path.suffix in (".py", ".cjs", ".json")
                    and "node_modules" not in path.parts and not path.name.startswith("test_")):
                # Ignore OS line-ending differences, preserve all other code bytes.
                files[path.relative_to(root).as_posix()] = hashlib.sha256(
                    path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    runtime = {}
    for package in ("duckdb", "boto3", "botocore", "numpy"):
        try:
            runtime[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            runtime[package] = None
    runtime["python"] = list(sys.version_info[:3])
    from pipeline.requirements_resolution.bridge import discover_runtime
    resolver = discover_runtime()
    runtime["node"] = subprocess.run([resolver["node"], "--version"], check=True,
                                     capture_output=True, text=True, timeout=10).stdout.strip()
    for name in ("semver_module", "package_arg_module"):
        directory = Path(resolver[name])
        runtime[name] = {path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                         for path in sorted(directory.rglob("*")) if path.is_file() and path.suffix in (".js", ".json")}
    return {"files": files, "runtime": runtime}
