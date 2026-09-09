"""Pin producer-specific manifests and revalidate all consumed immutable files."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from pipeline.curated.storage import read_optional
from pipeline.downloads_interval.input import _fetch, _file_digest, _safe_relative, _verify_remote
from pipeline.downloads_interval.policy import policy_document as download_policy
from pipeline.postgresql.input import select_run
from pipeline.repository_metrics.policy import policy_document as repository_policy
from pipeline.snapshot.input import read_candidate
from pipeline.snapshot.policy import policy_sha256 as snapshot_policy_sha256
from .policy import canonical_bytes

BUCKET = "pickage-curated"
SHA = re.compile(r"[0-9a-f]{64}\Z")
RUN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}\Z")
GROUPS = ("population_files", "download_files", "repository_files", "selection_files", "detail_files")


def _read(s3, key):
    item = read_optional(s3, BUCKET, key)
    if item is None:
        raise ValueError("required object missing: " + key)
    return item[0]


def _json(body, label):
    try:
        value = json.loads(body)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid JSON: " + label) from error
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: " + label)
    return value


def _hash(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _run_meta(s3, prefix, run_id, checksum, dataset, success_json):
    body = _read(s3, prefix + "/run_manifest.json")
    if hashlib.sha256(body).hexdigest() != checksum:
        raise ValueError(dataset + " manifest SHA mismatch")
    marker = _read(s3, prefix + "/_SUCCESS")
    valid = (_json(marker, dataset + " marker") == {"manifest_sha256": checksum}
             if success_json else marker == (checksum + "\n").encode())
    if not valid:
        raise ValueError(dataset + " completion marker mismatch")
    if not success_json:
        if _json(_read(s3, prefix + "/_INPUT.json"), "download input lock") != {"manifest_sha256": checksum}:
            raise ValueError("download input lock mismatch")
    manifest = _json(body, dataset + " manifest")
    if any(manifest.get(k) != v for k, v in {
            "dataset": dataset, "run_id": run_id, "status": "PASSED", "format_version": 1}.items()):
        raise ValueError(dataset + " manifest contract mismatch")
    return manifest


def _records(manifest, dataset, prefix, *, download=False):
    """Resolve exact role namespaces rather than infer roles from substrings."""
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("manifest files missing")
    selected, seen = [], set()
    field = "role" if download else "dataset"
    for record in files:
        if not isinstance(record, dict):
            raise ValueError("invalid file record")
        path = _safe_relative(record.get("path"), "producer file path")
        if any(char in path for char in "*?[") or not path.endswith(".parquet") or path in seen:
            raise ValueError("unsafe or duplicate producer file path")
        seen.add(path)
        if record.get(field) != dataset:
            continue
        size, checksum = record.get("bytes"), record.get("sha256")
        rows = record.get("row_count" if download else "rows")
        if (type(size) is not int or size <= 0 or not isinstance(checksum, str)
                or not SHA.fullmatch(checksum) or type(rows) is not int or rows < 0):
            raise ValueError("invalid metric file record")
        if download:
            if path != dataset + ".parquet":
                raise ValueError("download role path mismatch")
            key = prefix + "/data/" + path
        else:
            pattern = r"attempts/[A-Za-z0-9_-]+/outputs/" + re.escape(dataset) + r"/[^/]+\.parquet"
            if not re.fullmatch(pattern, path):
                raise ValueError("repository role path mismatch")
            key = prefix + "/" + path
        selected.append({"key": key, "bytes": size, "sha256": checksum,
                         "row_count": rows, "role": dataset})
    if not selected:
        raise ValueError("no files for " + dataset)
    return sorted(selected, key=lambda record: record["key"])


def _select_inputs(s3, *, snapshot, population_run_id, population_manifest_sha256,
                   candidate_path, candidate_sha256, download_run_id, download_manifest_sha256,
                   repository_run_id, repository_manifest_sha256):
    if date.fromisoformat(snapshot).isoformat() != snapshot:
        raise ValueError("snapshot must be an ISO date")
    for value in (population_manifest_sha256, candidate_sha256,
                  download_manifest_sha256, repository_manifest_sha256):
        if not isinstance(value, str) or not SHA.fullmatch(value):
            raise ValueError("invalid input SHA")
    for value in (population_run_id, download_run_id, repository_run_id):
        if not isinstance(value, str) or not RUN.fullmatch(value):
            raise ValueError("invalid input run ID")
    candidate_path = Path(candidate_path)
    if candidate_path.is_symlink() or _file_digest(candidate_path)[1] != candidate_sha256:
        raise ValueError("candidate SHA mismatch")
    candidate = read_candidate(candidate_path)
    if candidate["candidate_sha256"] != candidate_sha256:
        raise ValueError("candidate changed while reading")
    if (candidate["candidate"]["policy_version"] != "snapshot-time-v1"
            or candidate["candidate"]["policy_sha256"] != snapshot_policy_sha256()):
        raise ValueError("snapshot policy mismatch")
    intervals = [row for row in candidate["calendar"] if row["snapshot_at"] == snapshot]
    if len(intervals) != 1:
        raise ValueError("snapshot missing or duplicated in candidate")
    interval = intervals[0]
    timestamp = datetime.fromisoformat(interval["snapshot_timestamp"].replace("Z", "+00:00"))
    if timestamp.tzinfo is None or timestamp.astimezone(timezone.utc).date().isoformat() != snapshot:
        raise ValueError("candidate requires exact UTC snapshot timestamp")
    population = select_run(s3, snapshot, population_run_id)
    if population["manifest_sha256"] != population_manifest_sha256:
        raise ValueError("population SHA mismatch")
    if population["counts"]["package"] <= 0:
        raise ValueError("empty population")
    # This producer explicitly stores naive UTC; only this adapter supplies UTC.
    if population["snapshot_timestamp"] != timestamp.astimezone(timezone.utc).replace(tzinfo=None).isoformat():
        raise ValueError("population exact timestamp mismatch")
    dp = f"npm-downloads-interval/v1/snapshot={snapshot}/run_id={download_run_id}"
    rp = f"depsdev/v1/repository-metrics/snapshot={snapshot}/run_id={repository_run_id}"
    downloads = _run_meta(s3, dp, download_run_id, download_manifest_sha256, "npm-downloads-interval", False)
    repository = _run_meta(s3, rp, repository_run_id, repository_manifest_sha256, "repository-metrics", True)
    if (downloads.get("required_remote_verification") != "GET_SHA256_ALL_FILES"
            or downloads.get("aggregation_policy") != download_policy()
            or downloads.get("aggregation_policy_sha256") != _hash(download_policy())
            or downloads.get("input_manifest_sha256") != _hash(downloads["input_manifest"])
            or not SHA.fullmatch(str(downloads.get("contract_sha256", "")))):
        raise ValueError("download policy or input hash mismatch")
    if (repository.get("verification") != "LOCAL_SHA256_PARQUET_RECONCILIATION"
            or repository.get("policy") != repository_policy()
            or repository["request"].get("policy_sha256") != _hash(repository_policy())
            or repository["request"].get("input_sha256") != _hash(repository["input"])
            or not SHA.fullmatch(str(repository["request"].get("code_sha256", "")))):
        raise ValueError("repository policy or input hash mismatch")
    lineage = {"curated_run_id": population_run_id,
               "curated_manifest_sha256": population_manifest_sha256,
               "candidate_sha256": candidate_sha256, "snapshot": snapshot,
               "policy_version": "snapshot-time-v1", "policy_sha256": snapshot_policy_sha256()}
    for label, producer in (("downloads", downloads["input_manifest"]), ("repository", repository["input"])):
        if any(producer.get(key) != value for key, value in lineage.items()):
            raise ValueError(label + " population/candidate/policy lineage mismatch")
    if downloads.get("interval") != interval or downloads["input_manifest"].get("interval") != interval:
        raise ValueError("download P/S interval mismatch")
    if (repository.get("snapshot") != snapshot
            or repository.get("snapshot_timestamp") != interval["snapshot_timestamp"]
            or repository["input"].get("snapshot_timestamp") != interval["snapshot_timestamp"]):
        raise ValueError("repository exact timestamp mismatch")
    groups = {
        "population_files": sorted(population["_service_records"]["package"], key=lambda rec: rec["key"]),
        "download_files": _records(downloads, "interval_downloads", dp, download=True),
        "repository_files": _records(repository, "metric/data", rp),
        "selection_files": _records(repository, "quality/selection", rp),
        "detail_files": _records(downloads, "daily_quality", dp, download=True)
                        + _records(downloads, "unmatched_packages", dp, download=True),
    }
    count = population["counts"]["package"]
    for group in ("download_files", "repository_files", "selection_files"):
        if sum(record["row_count"] for record in groups[group]) != count:
            raise ValueError(group + " manifest population count mismatch")
    payload = {
        "format_version": 1, "dataset": "package-snapshot-input", "snapshot": snapshot,
        "snapshot_timestamp": interval["snapshot_timestamp"], "interval": interval,
        "population": {"run_id": population_run_id, "manifest_sha256": population_manifest_sha256,
                       "run_prefix": population["run_prefix"]},
        "candidate": {"sha256": candidate_sha256, "policy_sha256": snapshot_policy_sha256()},
        "downloads": {"run_id": download_run_id, "manifest_sha256": download_manifest_sha256,
                      "run_prefix": dp, "policy_sha256": downloads["aggregation_policy_sha256"],
                      "input_manifest_sha256": downloads["input_manifest_sha256"]},
        "repository_metrics": {"run_id": repository_run_id, "manifest_sha256": repository_manifest_sha256,
                               "run_prefix": rp, "policy_sha256": repository["request"]["policy_sha256"]},
        **groups,
    }
    return payload, count


def prepare(s3, *, snapshot, population_run_id, population_manifest_sha256, candidate_path,
            candidate_sha256, download_run_id, download_manifest_sha256, repository_run_id,
            repository_manifest_sha256, cache_dir, workers=4):
    if type(workers) is not int or workers < 1:
        raise ValueError("workers must be positive")
    arguments = dict(snapshot=snapshot, population_run_id=population_run_id,
                     population_manifest_sha256=population_manifest_sha256,
                     candidate_path=str(Path(candidate_path).resolve()), candidate_sha256=candidate_sha256,
                     download_run_id=download_run_id, download_manifest_sha256=download_manifest_sha256,
                     repository_run_id=repository_run_id, repository_manifest_sha256=repository_manifest_sha256)
    payload, count = _select_inputs(s3, **arguments)
    root = Path(cache_dir).resolve()
    local = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for group in GROUPS:
            def fetch(record):
                return str(_fetch(s3, BUCKET, record["key"], record,
                                  root / group / (record["sha256"] + ".parquet")))
            local[group] = list(pool.map(fetch, payload[group]))
    return {**local, "input_manifest": payload, "input_manifest_sha256": _hash(payload),
            "interval": payload["interval"], "population_rows": count,
            "_arguments": arguments, "_workers": workers}


def revalidate(s3, prepared):
    payload, count = _select_inputs(s3, **prepared["_arguments"])
    if payload != prepared["input_manifest"] or count != prepared["population_rows"]:
        raise ValueError("approved inputs changed before commit")
    pairs = []
    for group in GROUPS:
        if len(prepared[group]) != len(payload[group]):
            raise ValueError("cached input inventory changed")
        pairs.extend(zip(payload[group], prepared[group]))
    def check(pair):
        record, local = pair
        path = Path(local)
        if path.is_symlink() or not path.is_file() or _file_digest(path) != (record["bytes"], record["sha256"]):
            raise ValueError("cached input changed: " + str(path))
        _verify_remote(s3, BUCKET, record["key"], record)
    with ThreadPoolExecutor(max_workers=prepared["_workers"]) as pool:
        list(pool.map(check, pairs))
