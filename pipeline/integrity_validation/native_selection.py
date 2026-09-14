"""Select a bounded, explicitly pinned native run by metadata only."""
from __future__ import annotations

from datetime import date, datetime
from pathlib import PurePosixPath
import re

from pipeline.package_snapshot.load import select_run as select_snapshot_run
from pipeline.postgresql.input import select_run as select_package_version_run
from pipeline.snapshot.policy import parse_timestamp


BUCKET = "pickage-curated"
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
RUN_ID = re.compile(r"[A-Za-z0-9_-]+\Z")
REQUIRED = {"format_version", "kind", "dataset", "snapshot", "run_id",
            "snapshot_timestamp", "manifest_sha256", "expected_counts",
            "objects", "samples"}
PRODUCER_FIELDS = {
    "build_contract_sha256", "contract_sha256", "policy_sha256",
    "input_manifest_sha256", "aggregation_policy_sha256",
    "selection_policy_sha256", "validator_contract_sha256",
}


def _error(label: str, error: Exception) -> ValueError:
    return ValueError(f"malformed native {label}: {error}")


def _timestamp(value, label: str, *, allow_naive_utc=False) -> datetime:
    try:
        return parse_timestamp(value, allow_naive_utc=allow_naive_utc)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} violates the snapshot timestamp policy: {error}") from error


def _relative(path, label: str) -> str:
    if not isinstance(path, str) or not path or "\\" in path or "\x00" in path:
        raise ValueError(f"{label} must be a relative POSIX path")
    parsed = PurePosixPath(path)
    if parsed.is_absolute() or parsed.as_posix() != path or ".." in parsed.parts:
        raise ValueError(f"{label} must be a relative POSIX path")
    return path


def _counts(value, dataset: str) -> dict[str, int]:
    expected_key = "package_snapshot" if dataset == "package-snapshot-observed" else None
    if not isinstance(value, dict):
        raise ValueError("expected_counts must be an object")
    allowed = {"package_snapshot"} if expected_key else {"package", "version"}
    if set(value) != allowed:
        raise ValueError("expected_counts has unexpected or missing keys")
    result = {}
    for key, count in value.items():
        if type(count) is not int or count < (1 if key == "package_snapshot" else 0):
            raise ValueError(f"invalid expected count: {key}")
        result[key] = count
    return result


def select_metadata(document: dict, store) -> dict:
    """Select one native run using only bounded manifest metadata and samples."""
    if not isinstance(document, dict):
        raise ValueError("metadata request must be an object")
    unknown = set(document) - REQUIRED
    missing = REQUIRED - set(document)
    if unknown or missing:
        raise ValueError(f"metadata request keys invalid (missing={sorted(missing)}, unknown={sorted(unknown)})")
    if type(document["format_version"]) is not int or document["format_version"] != 1:
        raise ValueError("format_version must be integer 1")
    if document["kind"] != "native_metadata_bundle":
        raise ValueError("unsupported metadata kind")
    dataset = document["dataset"]
    if dataset not in ("package-version", "package-snapshot-observed"):
        raise ValueError(f"unsupported native dataset format: {dataset}")
    snapshot = document["snapshot"]
    try:
        if not isinstance(snapshot, str) or date.fromisoformat(snapshot).isoformat() != snapshot:
            raise ValueError
    except ValueError as error:
        raise ValueError("snapshot must be an ISO date") from error
    run_id = document["run_id"]
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        raise ValueError("run_id is invalid")
    requested_time = _timestamp(document["snapshot_timestamp"], "snapshot_timestamp")
    manifest_sha = document["manifest_sha256"]
    if not isinstance(manifest_sha, str) or not SHA256.fullmatch(manifest_sha):
        raise ValueError("manifest_sha256 must be lowercase hexadecimal SHA-256")
    counts = _counts(document["expected_counts"], dataset)

    prefix_dataset = "package-version" if dataset == "package-version" else "package-snapshot"
    prefix = f"depsdev/v1/{prefix_dataset}/snapshot={snapshot}/run_id={run_id}"
    expected_objects = {prefix + "/run_manifest.json", prefix + "/_SUCCESS"}
    if dataset == "package-snapshot-observed":
        expected_objects.add(prefix + "/_INPUT.json")
    objects = document["objects"]
    if not isinstance(objects, dict) or set(objects) != expected_objects:
        raise ValueError("objects must bind exactly the native management objects")
    for key, path in objects.items():
        if not isinstance(key, str) or not key.startswith(prefix + "/"):
            raise ValueError("objects contains a non-native key")
        _relative(path, f"objects[{key!r}]")

    samples = document["samples"]
    if not isinstance(samples, list):
        raise ValueError("samples must be a list")
    sample_keys = set()
    for sample in samples:
        if not isinstance(sample, dict) or set(sample) != {"key", "path"}:
            raise ValueError("malformed sample binding")
        key = sample["key"]
        if not isinstance(key, str) or key in sample_keys or key.startswith(prefix + "/") is False:
            raise ValueError("sample key is invalid or duplicated")
        sample_keys.add(key)
        _relative(sample["path"], f"sample[{key!r}]")

    try:
        if dataset == "package-version":
            native = select_package_version_run(store, snapshot, run_id)
            selector_name = "pipeline.postgresql.input.select_run"
        else:
            native = select_snapshot_run(store, snapshot, run_id, manifest_sha)
            selector_name = "pipeline.package_snapshot.load.select_run"
    except (KeyError, TypeError, AttributeError) as error:
        raise _error("manifest", error) from error
    if native["manifest_sha256"] != manifest_sha:
        raise ValueError("native manifest SHA does not match caller pin")
    manifest = native.get("manifest")
    if not isinstance(manifest, dict):
        raise ValueError("native manifest is malformed")
    # Inspect the unmodified manifest time too: the existing selector's parser
    # could already have truncated unsupported precision before returning metadata.
    source_time = (manifest["report"]["snapshot_timestamp"] if dataset == "package-version"
                   else manifest["snapshot_timestamp"])
    source_time = _timestamp(source_time, "source snapshot_timestamp",
                             allow_naive_utc=dataset == "package-version")
    native_time = _timestamp(native["snapshot_timestamp"], "native snapshot_timestamp", allow_naive_utc=True)
    if source_time != native_time:
        raise ValueError("native selector changed the source snapshot timestamp")
    if native_time != requested_time or native_time.date().isoformat() != snapshot:
        raise ValueError("snapshot timestamp does not match requested UTC instant/date")
    if native["counts"] != counts:
        raise ValueError("native counts do not match expected_counts")
    if dataset == "package-snapshot-observed":
        historical = {"history_policy", "build_contract_sha256", "history_input"}
        if historical & set(manifest):
            raise ValueError("historical manifest cannot be labeled observed")
    for key in PRODUCER_FIELDS & set(manifest):
        if not isinstance(manifest[key], str) or not SHA256.fullmatch(manifest[key]):
            raise ValueError(f"native producer hash is invalid: {key}")
    records = []
    groups = native.get("_service_records") if dataset == "package-version" else native.get("_records")
    if not isinstance(groups, dict):
        raise ValueError("native file records are missing")
    for role, entries in groups.items():
        if not isinstance(entries, list):
            raise ValueError("native file records are malformed")
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("key"), str):
                raise ValueError("native file record is malformed")
            if "row_count" in entry and (type(entry["row_count"]) is not int or entry["row_count"] < 0):
                raise ValueError("native row_count is invalid")
            record = {"role": role, "key": entry["key"], "bytes": entry.get("bytes"), "sha256": entry.get("sha256")}
            if "row_count" in entry:
                record["row_count"] = entry["row_count"]
            records.append(record)
        if dataset == "package-snapshot-observed":
            role_rows = [record["row_count"] for record in records if record["role"] == role and "row_count" in record]
            if role_rows and sum(role_rows) != counts["package_snapshot"]:
                raise ValueError(f"native {role} row_count sum disagrees with package_snapshot count")
    known = {r["key"] for r in records}
    if any(key not in known for key in sample_keys):
        raise ValueError("sample key is not bound to a native file record")
    producer_contracts = {key: manifest[key] for key in PRODUCER_FIELDS if key in manifest}
    return {"metadata": native, "records": records, "native_selector": selector_name,
            "producer_contracts": producer_contracts}


__all__ = ["select_metadata"]
