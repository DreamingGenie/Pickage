"""Assemble comparison-stage inputs from completed, immutable experiment artifacts.

This is an offline adapter: it never computes a stage or writes to object storage.
Its output is an experiment manifest, not a Curated publication or lineage claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any


STAGES = ("package_version", "downloads", "repository", "package_snapshot", "dependents")
SHA256_LENGTH = 64


def _json_paths(value: Any) -> Any:
    """Normalize path-bearing inputs without coercing unsupported values."""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_paths(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_paths(child) for child in value]
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _paths(value: Any, name: str) -> list[str]:
    if isinstance(value, (str, Path)):
        values = [str(value)]
    elif isinstance(value, (list, tuple)):
        values = [str(item) for item in value]
    else:
        raise ValueError(f"{name} must be a path or path list")
    if not values or any(not item for item in values):
        raise ValueError(f"{name} must not be empty")
    return values


def _file_inventory(value: Any, *, roots: tuple[Path, ...]) -> list[dict[str, Any]]:
    """Find every local file referenced by stage inputs and pin bytes and hash."""
    found: set[Path] = set()

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            for child in item.values():
                visit(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                visit(child)
        elif isinstance(item, (str, Path)):
            text = str(item)
            if text.startswith("s3a://"):
                raise ValueError("stage input paths must be locally materialized before assembly")
            candidate = Path(text)
            if candidate.is_file():
                resolved = candidate.resolve(strict=True)
                if not any(resolved.is_relative_to(root) for root in roots):
                    raise ValueError(f"input file is outside approved artifact roots: {resolved}")
                found.add(resolved)

    visit(value)
    if not found:
        raise ValueError("no local files found in stage inputs")
    return [{"path": str(path), "bytes": path.stat().st_size, "sha256": _sha256(path)}
            for path in sorted(found, key=lambda p: p.as_posix())]


def assemble(*, source_request: dict, source_manifests: dict[str, str],
             package_version: dict, downloads: dict, repository: dict,
             outputs: dict, population_rows: int, raw_inputs: dict,
             artifact_roots: list[str | Path], output_manifest: str | Path,
             code_identity: dict | str) -> Path:
    """Create all five job-compatible stage input dictionaries without computing.

    ``package_version``, ``downloads``, and ``repository`` are copied from their
    completed input manifests. ``outputs`` points at their completed result files
    and the successful repository retry. ``raw_inputs`` points at the frozen raw
    Parquet and target selection. All provenance is caller-supplied from source
    manifests; no successful stage manifest is synthesized here.
    """
    if not isinstance(source_request, dict) or not source_request:
        raise ValueError("source_request is required")
    if not isinstance(code_identity, (dict, str)) or not code_identity:
        raise ValueError("code_identity is required")
    if type(population_rows) is not int or population_rows <= 0:
        raise ValueError("population_rows must be a positive integer")
    required_sources = {"package_version", "downloads", "repository_retry", "raw"}
    if not required_sources.issubset(source_manifests):
        raise ValueError("source_manifests must pin completed stages, repository retry, and raw freeze")
    for label, value in source_manifests.items():
        if (not isinstance(value, str) or len(value) != SHA256_LENGTH
                or any(char not in "0123456789abcdef" for char in value)):
            raise ValueError(f"invalid source manifest SHA256: {label}")

    required_output_keys = {"package", "version", "downloads", "repository_metric", "repository_selection"}
    if not required_output_keys.issubset(outputs):
        raise ValueError("outputs are missing completed-stage artifacts")
    package_files = _paths(outputs["package"], "outputs.package")
    version_files = _paths(outputs["version"], "outputs.version")
    download_file = _paths(outputs["downloads"], "outputs.downloads")
    repository_metric_files = _paths(outputs["repository_metric"], "outputs.repository_metric")
    repository_selection_files = _paths(outputs["repository_selection"], "outputs.repository_selection")
    raw_versions = _paths(raw_inputs.get("versions_full"), "raw_inputs.versions_full")
    raw_requirements = _paths(raw_inputs.get("requirements"), "raw_inputs.requirements")
    targets = _paths(raw_inputs.get("targets"), "raw_inputs.targets")

    request = source_request.get("source_request", source_request)
    snapshot = request.get("snapshot")
    timestamp = request.get("snapshot_timestamp")
    if not isinstance(snapshot, str) or not isinstance(timestamp, str):
        raise ValueError("source request must include snapshot and snapshot_timestamp")
    if package_version.get("snapshot") != snapshot:
        raise ValueError("package_version input snapshot differs from the source request")
    if (not package_version.get("versions") or not package_version.get("requirements")
            or "previous_ids" not in package_version):
        raise ValueError("package_version inputs are incomplete")
    for name in ("package_files", "target_file", "status_file"):
        _paths(downloads.get(name), "downloads." + name)
    _paths(downloads.get("daily_files", []), "downloads.daily_files") if downloads.get("daily_files") else None
    if (not isinstance(downloads.get("interval"), dict)
            or downloads["interval"].get("snapshot_at") != snapshot
            or not isinstance(downloads.get("lineage"), dict)):
        raise ValueError("downloads input snapshot or lineage is incomplete")
    if (repository.get("snapshot") != snapshot
            or repository.get("snapshot_timestamp") != timestamp
            or not isinstance(repository.get("files"), dict)
            or not isinstance(repository.get("counts"), dict)):
        raise ValueError("repository input identity/counts are incomplete")

    # Preserve upstream manifests as supplied. The downstream dictionaries only
    # adapt output paths into the shape already consumed by job.py.
    stages = _json_paths({
        "package_version": dict(package_version),
        "downloads": dict(downloads),
        "repository": dict(repository),
        "package_snapshot": {
            "population_files": package_files,
            "download_files": download_file,
            "repository_files": repository_metric_files,
            "selection_files": repository_selection_files,
            "population_rows": population_rows,
        },
        "dependents": {
            "files": {"package": package_files, "version": version_files,
                      "versions_full": raw_versions, "requirements": raw_requirements,
                      "targets": targets[0] if len(targets) == 1 else targets},
            "snapshot": snapshot,
            "snapshot_timestamp": timestamp,
        },
    })
    roots = tuple(Path(root).resolve(strict=True) for root in artifact_roots)
    if not roots:
        raise ValueError("artifact_roots must not be empty")
    inventory = _file_inventory(stages, roots=roots)
    provenance = {
        "kind": "ASSEMBLED_FROM_COMPLETED_ARTIFACTS",
        "source_manifest_sha256": dict(sorted(source_manifests.items())),
        "source_lineage_preserved": True,
        "official_publication_manifest": False,
        "stage_execution_performed": False,
    }
    identity_doc = {"source_request": request, "source_manifest_sha256": provenance["source_manifest_sha256"],
                    "input_files": sorted((row["sha256"], row["bytes"]) for row in inventory),
                    "code_identity": code_identity}
    input_identity = hashlib.sha256(json.dumps(identity_doc, sort_keys=True, separators=(",", ":"),
                                                ensure_ascii=False).encode("utf-8")).hexdigest()
    manifest = {
        "format_version": 1,
        "scope": "FIXED_STAGE_INPUT_COMPARISON",
        "adapter": provenance,
        "source_request": request,
        "source_manifest_sha256": provenance["source_manifest_sha256"],
        "code_identity": code_identity,
        "input_identity": input_identity,
        "stages": stages,
        "input_files": inventory,
        "production_writes": False,
        "db_loaded": False,
    }
    payload = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    destination = Path(output_manifest)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)
    return destination


def verify(manifest_path: str | Path) -> dict:
    """Recheck frozen local bytes before a baseline or Spark invocation."""
    path = Path(manifest_path)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if (manifest.get("format_version") != 1
            or manifest.get("adapter", {}).get("kind") != "ASSEMBLED_FROM_COMPLETED_ARTIFACTS"
            or manifest.get("adapter", {}).get("official_publication_manifest") is not False
            or set(manifest.get("stages", {})) != set(STAGES)):
        raise ValueError("not a complete assembled comparison manifest")
    sources = manifest.get("source_manifest_sha256", {})
    if not {"package_version", "downloads", "repository_retry", "raw"}.issubset(sources):
        raise ValueError("comparison manifest has incomplete source provenance")
    identity_doc = {"source_request": manifest.get("source_request"),
                    "source_manifest_sha256": sources,
                    "input_files": sorted((row["sha256"], row["bytes"])
                                           for row in manifest.get("input_files", [])),
                    "code_identity": manifest.get("code_identity")}
    expected_identity = hashlib.sha256(json.dumps(
        identity_doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
    if manifest.get("input_identity") != expected_identity:
        raise ValueError("comparison manifest input identity is inconsistent")
    seen = set()
    for record in manifest.get("input_files", []):
        if (not isinstance(record.get("bytes"), int) or record["bytes"] < 0
                or not isinstance(record.get("sha256"), str) or len(record["sha256"]) != SHA256_LENGTH
                or record["path"] in seen):
            raise ValueError("comparison manifest input inventory is malformed")
        seen.add(record["path"])
        source = Path(record["path"])
        if (not source.is_file() or source.stat().st_size != record["bytes"]
                or _sha256(source) != record["sha256"]):
            raise ValueError(f"frozen experiment input changed: {source}")
    if not manifest.get("input_files"):
        raise ValueError("comparison manifest has no pinned input files")
    return manifest


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _overlay_object(reference_root: Path, bucket: str, key: str,
                    *, expected_bytes: int | None = None,
                    expected_sha256: str | None = None) -> Path:
    name = hashlib.sha256((bucket + "\0" + key).encode("utf-8")).hexdigest()
    path = reference_root / "objects" / name
    sidecar = path.with_suffix(".json")
    if not path.is_file() or not sidecar.is_file():
        raise ValueError(f"completed overlay object is missing: {key}")
    record = _read_json(sidecar)
    if record != {"Bucket": bucket, "Key": key}:
        raise ValueError(f"overlay key sidecar mismatch: {key}")
    if expected_bytes is not None and path.stat().st_size != expected_bytes:
        raise ValueError(f"overlay object size mismatch: {key}")
    if expected_sha256 is not None and _sha256(path) != expected_sha256:
        raise ValueError(f"overlay object hash mismatch: {key}")
    return path


def _overlay_by_digest(reference_root: Path, bucket: str, suffix: str,
                       expected_bytes: int, expected_sha256: str) -> Path:
    matches = []
    for sidecar in (reference_root / "objects").glob("*.json"):
        try:
            row = _read_json(sidecar)
        except (OSError, json.JSONDecodeError):
            continue
        if row.get("Bucket") == bucket and str(row.get("Key", "")).endswith("/" + suffix):
            payload = sidecar.with_suffix("")
            if payload.is_file() and payload.stat().st_size == expected_bytes and _sha256(payload) == expected_sha256:
                matches.append(payload)
    if len(matches) != 1:
        raise ValueError(f"expected one verified overlay object ending in {suffix}, found {len(matches)}")
    return matches[0]


def _frozen_object(root: Path, manifest: dict, key_suffix: str) -> Path:
    rows = [row for row in manifest.get("input_files", [])
            if row.get("bucket") == "pickage-raw" and row.get("key", "").endswith(key_suffix)]
    if len(rows) != 1:
        raise ValueError(f"expected one frozen raw object ending in {key_suffix}, found {len(rows)}")
    row = rows[0]
    path = (root / row["relative_path"]).resolve(strict=True)
    if not path.is_relative_to(root.resolve(strict=True)):
        raise ValueError("frozen raw path escapes its root")
    if path.stat().st_size != row["bytes"] or _sha256(path) != row["sha256"]:
        raise ValueError(f"frozen raw object changed: {row['key']}")
    return path


def assemble_from_artifacts(reference_root: str | Path, retry_root: str | Path,
                            output_dir: str | Path, frozen_root: str | Path, *,
                            metadata_root: str | Path | None = None,
                            code_identity: dict) -> Path:
    """Build all five stage inputs from the completed real-data attempt mounts.

    Expected metadata files are copied read-only from the server attempt:
    ``request.json``, ``status.json``, ``package_version-manifest.json``,
    ``downloads-manifest.json``, ``downloads-input.json``,
    ``repository-input.json``, and ``repository-result.json``. The retry mount
    supplies ``retry-input-manifest.json`` and ``repository-retry/report.json``.
    """
    reference = Path(reference_root).resolve(strict=True)
    retry = Path(retry_root).resolve(strict=True)
    frozen = Path(frozen_root).resolve(strict=True)
    if metadata_root is not None:
        metadata = Path(metadata_root).resolve(strict=True)
    else:
        candidates = (retry / "metadata", Path("/metadata"))
        metadata = next((candidate.resolve() for candidate in candidates if candidate.is_dir()), None)
        if metadata is None:
            raise ValueError("metadata root is missing; pass metadata_root or mount /metadata")
    destination_dir = Path(output_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    request_envelope = _read_json(metadata / "request.json")
    request = request_envelope.get("request")
    if not isinstance(request, dict):
        raise ValueError("reference request envelope is invalid")
    status = _read_json(metadata / "status.json")
    for completed in ("snapshot", "package_version", "downloads"):
        if status.get("stages", {}).get(completed, {}).get("status") != "COMPLETE":
            raise ValueError(f"reference stage is not complete: {completed}")

    package_manifest_path = metadata / "package_version-manifest.json"
    downloads_manifest_path = metadata / "downloads-manifest.json"
    downloads_input_path = metadata / "downloads-input.json"
    repository_input_path = metadata / "repository-input.json"
    repository_result_path = metadata / "repository-result.json"
    package_manifest = _read_json(package_manifest_path)
    downloads_manifest = _read_json(downloads_manifest_path)
    downloads_input_manifest = _read_json(downloads_input_path)
    repository_input = _read_json(repository_input_path)
    repository_result = _read_json(repository_result_path)
    raw_manifest_path = frozen / "raw-inputs.json"
    raw_manifest = _read_json(raw_manifest_path)
    retry_manifest_path = retry / "retry-input-manifest.json"
    retry_manifest = _read_json(retry_manifest_path)
    retry_report = _read_json(retry / "repository-retry" / "report.json")

    if package_manifest.get("status") != "PASSED" or downloads_manifest.get("status") != "PASSED":
        raise ValueError("reference package/download manifests are not passed")
    if (_sha256(package_manifest_path) != status["stages"]["package_version"]["manifest_sha256"]
            or _sha256(downloads_manifest_path) != status["stages"]["downloads"]["manifest_sha256"]):
        raise ValueError("copied package/download manifest differs from completed reference status")
    if downloads_manifest.get("input_manifest") != downloads_input_manifest:
        raise ValueError("downloads input manifest does not match the completed output manifest")
    if (raw_manifest.get("source_request", {}).get("snapshot") != request.get("snapshot")
            or raw_manifest.get("source_request", {}).get("snapshot_timestamp") != request.get("snapshot_timestamp")):
        raise ValueError("raw freeze and reference request identify different snapshots")
    if repository_result.get("status") != "COMPUTED" or repository_result.get("cleanup_errors"):
        raise ValueError("repository retry report is not a clean completed run")
    if repository_result != retry_report:
        raise ValueError("copied repository retry report differs from its output artifact")
    repository_stage_result = repository_result.get("stages", {}).get("repository", {}).get("result", {})
    if repository_stage_result.get("validation") != "PASSED":
        raise ValueError("repository retry stage validation did not pass")
    if retry_manifest.get("stages", {}).get("repository") != repository_input:
        raise ValueError("repository retry manifest does not preserve the pinned repository input")
    from pipeline.preprocessing.experiments.spark.runtime.repository_retry_entry import EXPECTED_REPOSITORY_CODE_SHA256, INPUT_MANIFEST_SHA256, repository_code_sha256
    from pipeline.preprocessing.common.paths import REPO_ROOT
    current_repository_code_sha256 = repository_code_sha256(REPO_ROOT)
    if current_repository_code_sha256 != EXPECTED_REPOSITORY_CODE_SHA256:
        raise ValueError("current repository code differs from the pinned repository retry implementation")
    retry_source = retry_manifest.get("source_request", {})
    if retry_source.get("input_manifest_sha256") != INPUT_MANIFEST_SHA256:
        raise ValueError("repository retry input does not match the original pinned attempt")
    if retry_source.get("repository_code_sha256") != EXPECTED_REPOSITORY_CODE_SHA256:
        raise ValueError("repository retry source-code contract differs from the original run")
    if _sha256(repository_input_path) != INPUT_MANIFEST_SHA256:
        raise ValueError("copied repository input manifest bytes differ from the pinned source")
    if request.get("snapshot") != package_manifest.get("request", {}).get("snapshot"):
        raise ValueError("request and package-version manifest snapshot differ")

    package_outputs = {}
    for record in package_manifest.get("files", []):
        key = record.get("key", "")
        for role in ("package", "version", "package_ids"):
            if f"/{role}/data/" in key:
                package_outputs.setdefault(role, []).append(_overlay_object(
                    reference, "pickage-curated", key,
                    expected_bytes=record["bytes"], expected_sha256=record["sha256"]))
    if not package_outputs.get("package") or not package_outputs.get("version"):
        raise ValueError("completed package/version population outputs are incomplete")

    raw_rows = {row["key"]: row for row in raw_manifest.get("input_files", [])
                if row.get("bucket") == "pickage-raw"}
    bronze_id = downloads_input_manifest["bronze_run_id"]
    raw_prefix = f"npm-downloads/v1/run_id={bronze_id}/data/"
    selected = downloads_input_manifest.get("selected", {})
    daily = []
    for record in selected.get("daily", []):
        key = raw_prefix + record["path"]
        frozen_record = raw_rows.get(key)
        if frozen_record is None:
            raise ValueError(f"selected downloads parquet is not in frozen raw inventory: {key}")
        daily.append(_frozen_object(frozen, raw_manifest, key))
    target_record = selected.get("target", {})
    target_key = raw_prefix + target_record.get("path", "")
    status_record = selected.get("status", {})
    status_key = raw_prefix + status_record.get("path", "")
    target_path = _frozen_object(frozen, raw_manifest, target_key)
    status_path = _frozen_object(frozen, raw_manifest, status_key)
    all_daily_dates = []
    for row in raw_rows.values():
        key = row["key"]
        match = re.search(r"/parquet/downloads/date=(\d{4}-\d{2}-\d{2})/", key)
        if key.startswith(raw_prefix + "parquet/downloads/") and match:
            all_daily_dates.append(match.group(1))
    if not all_daily_dates:
        raise ValueError("frozen raw inventory has no daily download Parquet dates")

    package_records = [row for row in package_manifest["files"] if "/package/data/" in row["key"]]
    package_file_paths = [str(_overlay_object(reference, "pickage-curated", row["key"],
                                               expected_bytes=row["bytes"], expected_sha256=row["sha256"]))
                          for row in package_records]
    download_output_files = {}
    for record in downloads_manifest.get("files", []):
        download_output_files[record["role"]] = str(_overlay_by_digest(
            reference, "pickage-curated", record["path"], record["bytes"], record["sha256"]))
    if "interval_downloads" not in download_output_files:
        raise ValueError("completed downloads output is missing interval_downloads")

    repository_output_root = retry / "repository-retry" / "repository"
    metric_files = sorted(str(path) for path in (repository_output_root / "metric" / "data").glob("*.parquet"))
    selection_files = sorted(str(path) for path in (repository_output_root / "quality" / "selection").glob("*.parquet"))
    if not metric_files or not selection_files:
        raise ValueError("repository retry metric or selection outputs are missing")

    versions_full = sorted(str(path) for path in (reference / "w" / "ref" / "inputs" / "versions_full").rglob("*.parquet"))
    requirements = sorted(str(path) for path in (reference / "w" / "ref" / "inputs" / "requirements").rglob("*.parquet"))
    if not versions_full or not requirements:
        raise ValueError("reference raw package/version stage inputs are missing")
    targets = _frozen_object(frozen, raw_manifest,
                             request["targets"]["dependents"]["key"])
    package_version_input = {"versions": versions_full, "requirements": requirements,
                             "previous_ids": None, "snapshot": request["snapshot"]}
    dl_interval = downloads_input_manifest["interval"]
    downloads_input = {
        "package_files": package_file_paths,
        "daily_files": daily,
        "target_file": str(target_path), "status_file": str(status_path),
        "interval": dl_interval,
        "available_start": min(all_daily_dates), "available_end": max(all_daily_dates),
        "expected_package_rows": package_manifest["report"]["output_counts"]["package/data"],
        "input_manifest": downloads_input_manifest,
        "input_manifest_sha256": downloads_manifest["input_manifest_sha256"],
        "lineage": {"input_manifest_sha256": downloads_manifest["input_manifest_sha256"],
                    "policy_sha256": downloads_manifest["input_manifest"]["policy_sha256"],
                    "aggregation_policy_sha256": downloads_manifest["aggregation_policy_sha256"]},
    }
    source_manifests = {
        "package_version": status["stages"]["package_version"]["manifest_sha256"],
        "downloads": status["stages"]["downloads"]["manifest_sha256"],
        "repository_retry": _sha256(retry_manifest_path),
        "raw": _sha256(raw_manifest_path),
    }
    return assemble(
        source_request=request,
        source_manifests=source_manifests,
        package_version=package_version_input,
        downloads=downloads_input,
        repository=repository_input,
        outputs={"package": package_file_paths,
                 "version": [str(path) for path in package_outputs["version"]],
                 "downloads": download_output_files["interval_downloads"],
                 "repository_metric": metric_files,
                 "repository_selection": selection_files},
        population_rows=package_manifest["report"]["output_counts"]["package/data"],
        raw_inputs={"versions_full": versions_full, "requirements": requirements,
                    "targets": [str(targets)]},
        artifact_roots=[reference, retry, frozen],
        output_manifest=destination_dir / "prepared-inputs.json",
        code_identity={"benchmark_code_identity": code_identity,
                       "metadata_sha256": {path.name: _sha256(path) for path in (
                           package_manifest_path, downloads_manifest_path, downloads_input_path,
                           repository_input_path, repository_result_path, raw_manifest_path,
                       retry_manifest_path)}},
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-root", type=Path, required=True)
    parser.add_argument("--retry-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--frozen-root", type=Path, required=True)
    parser.add_argument("--metadata-root", type=Path)
    parser.add_argument("--code-identity", type=Path, required=True,
                        help="JSON with the benchmark code/archive digest and runtime image digest")
    args = parser.parse_args(argv)
    manifest = assemble_from_artifacts(
        args.reference_root, args.retry_root, args.output_dir, args.frozen_root,
        metadata_root=args.metadata_root, code_identity=_read_json(args.code_identity))
    result = verify(manifest)
    print(json.dumps({"manifest": str(manifest), "stages": list(result["stages"]),
                      "input_file_count": len(result["input_files"]),
                      "input_identity": result["input_identity"],
                      "source_manifest_sha256": result["source_manifest_sha256"]},
                     sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
