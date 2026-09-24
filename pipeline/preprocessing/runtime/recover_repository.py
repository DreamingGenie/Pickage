"""Bounded recovery for a run whose repository stage failed.

This controller is intentionally separate from :mod:`orchestration.runner`.
It accepts one very specific state: snapshot, package_version and downloads
are already complete for the exact request, while the remaining stages may be
replayed under a pinned recovery receipt.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

from pipeline.preprocessing.curated.storage import json_bytes, put_immutable, read_optional
from pipeline.preprocessing.orchestration import runner
from pipeline.preprocessing.orchestration.contracts import STAGES, code_contract, validate_request
from pipeline.preprocessing.orchestration.storage import (
    BUCKET,
    StageClient,
    host_lock,
    required,
    save_event,
    save_state,
    sha,
    utc_now,
    verify_descriptor,
)
from pipeline.preprocessing.orchestration.weekly_parent import publish_current
from pipeline.preprocessing.orchestration.workspace import claim, cleanup_failed, cleanup_stage
from pipeline.preprocessing.requirements_resolution.input import file_sha256
from pipeline.preprocessing.snapshot.projects import _footer_sha256


RECOVERY_ID = "repository-bounded-v1"
ALLOWED_GENERATOR = "pipeline/preprocessing/repository_metrics/duckdb_transform.py"
ALLOWED_LIFECYCLE = "pipeline/preprocessing/orchestration/workspace.py"
ALLOWED_CHANGES = {ALLOWED_GENERATOR, ALLOWED_LIFECYCLE}
RETAINED_STAGES = ("snapshot", "package_version", "downloads")
RECOVERED_STAGES = ("repository", "package_snapshot", "dependents")


def _contract_changes(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    if old.get("runtime") != new.get("runtime"):
        raise ValueError("Recovery runtime differs from original execution")
    changed = sorted(k for k in set(old.get("files", {})) | set(new.get("files", {}))
                     if old.get("files", {}).get(k) != new.get("files", {}).get(k))
    if set(changed) - ALLOWED_CHANGES:
        raise ValueError("Recovery only permits the reviewed repository generator/lifecycle changes: " + str(changed))
    return changed


def contract_changes(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    """Return the reviewed generator diff, rejecting all other drift."""
    return _contract_changes(old, new)


def _checkpoint(s3, prefix: str, name: str, request: dict[str, Any], workers: int) -> tuple[bytes, dict[str, Any]]:
    body = required(s3, BUCKET, f"{prefix}/stages/{name}.json")
    descriptor = json.loads(body)
    if (descriptor.get("stage"), descriptor.get("run_id"), descriptor.get("snapshot")) != (
            name, request["run_id"], request["snapshot"]):
        raise ValueError("Completed checkpoint identity differs: " + name)
    verify_descriptor(s3, descriptor, workers=workers)
    return body, descriptor


def _receipt(request: dict[str, Any], envelope: bytes, old: dict[str, Any], new: dict[str, Any],
             checkpoints: dict[str, str]) -> tuple[str, bytes]:
    body = json_bytes({
        "format": RECOVERY_ID,
        "recovery_id": RECOVERY_ID,
        "request": request,
        "original_envelope_sha256": sha(envelope),
        "original_code_contract": old["code_contract"],
        "new_code_contract": new,
        "changed_generator_files": contract_changes(old["code_contract"], new),
        "checkpoints": checkpoints,
        "helper_sha256": file_sha256(Path(__file__)),
        "scope": "REUSE_SNAPSHOT_PACKAGE_VERSION_DOWNLOADS_ONLY",
    })
    return f"{runner.run_prefix(request)}/recoveries/{RECOVERY_ID}.json", body


def _verify_retained_checkpoints(s3: Any, prefix: str,
                                 completed: dict[str, dict[str, Any]],
                                 checkpoint_shas: dict[str, str]) -> None:
    for name in RETAINED_STAGES:
        retained_body = required(s3, BUCKET, f"{prefix}/stages/{name}.json")
        if sha(retained_body) != checkpoint_shas[name]:
            raise ValueError("Retained checkpoint changed during recovery: " + name)
        retained_descriptor = json.loads(retained_body)
        if retained_descriptor != completed[name]:
            raise ValueError("Retained checkpoint descriptor changed during recovery: " + name)


def _workspace_path(value: Any, workspace: Path, label: str) -> Path:
    if not isinstance(value, (str, Path)) or not value:
        raise ValueError(f"Snapshot metadata missing {label}")
    raw = Path(value)
    if not raw.is_absolute():
        raise ValueError(f"Snapshot metadata {label} must be absolute")
    for part in (raw, *raw.parents):
        if part.is_symlink():
            raise ValueError(f"Snapshot metadata {label} contains a symlink")
    resolved = raw.resolve(strict=False)
    root = workspace.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"Snapshot metadata {label} escapes recovery workspace")
    return resolved


def _validate_snapshot_metadata(snapshot: dict[str, Any], workspace: Path) -> None:
    metadata = snapshot.get("metadata", {})
    if not metadata:
        return
    candidate = _workspace_path(metadata.get("candidate_path"), workspace, "candidate_path")
    # Keep validation independent of current hydration state. The executor may
    # create these paths later, but their declared locations are already fixed.
    _workspace_path(metadata.get("projects_dir"), workspace, "projects_dir")
    _workspace_path(candidate.parent / "projects-inventory.json", workspace, "inventory")


def _restore_project_mtimes(snapshot: dict[str, Any], workspace: Path) -> None:
    """Restore the candidate's pinned footer inventory timestamps after hydration."""
    metadata = snapshot.get("metadata", {})
    if not metadata:
        return
    _validate_snapshot_metadata(snapshot, workspace)
    candidate = _workspace_path(metadata.get("candidate_path"), workspace, "candidate_path")
    projects = _workspace_path(metadata.get("projects_dir"), workspace, "projects_dir")
    inventory_path = _workspace_path(candidate.parent / "projects-inventory.json", workspace, "inventory")
    if not candidate.is_file() or not projects.is_dir() or not inventory_path.is_file():
        return
    inventory = json.loads(inventory_path.read_bytes())
    for partition in inventory.get("snapshots", []):
        for record in partition.get("files", []):
            path = _workspace_path(projects / record["path"], workspace, "inventory record")
            if not path.is_relative_to(projects.resolve()):
                raise ValueError("Snapshot inventory record escapes projects directory")
            if path.is_file():
                mtime_ns = record.get("mtime_ns")
                if (type(mtime_ns) is int and mtime_ns > 0
                        and record.get("bytes") == path.stat().st_size
                        and record.get("parquet_footer_sha256") == _footer_sha256(path)):
                    os.utime(path, ns=(mtime_ns, mtime_ns))


def recover(request: dict[str, Any], s3: Any, work_dir: str | Path, *,
            _executor: Callable[..., dict[str, Any]] | None = None,
            _preflight: Callable[..., Any] | None = None) -> dict[str, Any]:
    """Recover the repository tail of one exact failed request.

    Private executor and preflight hooks exist solely for deterministic tests;
    no normal ``runner.run`` fallback is used by this API.
    """
    request = validate_request(request)
    local = Path(work_dir).resolve() / request["run_id"]
    prefix = runner.run_prefix(request)
    workers = request.get("options", {}).get("workers", 2)
    execute = _executor or runner._default_executor
    preflight = _preflight or runner._default_preflight
    local = claim(local, request["run_id"])

    with host_lock(s3):
        original_envelope = required(s3, BUCKET, prefix + "/request.json")
        envelope = json.loads(original_envelope)
        if envelope.get("request") != request or envelope.get("work_dir") != str(local):
            raise ValueError("Original request or work directory identity differs")
        current = code_contract()
        completed: dict[str, dict[str, Any]] = {}
        checkpoint_shas: dict[str, str] = {}
        for name in RETAINED_STAGES:
            body, descriptor = _checkpoint(s3, prefix, name, request, workers)
            checkpoint_shas[name] = sha(body)
            completed[name] = descriptor
        _validate_snapshot_metadata(completed["snapshot"], local)

        receipt_key, receipt_body = _receipt(request, original_envelope, envelope, current, checkpoint_shas)
        existing_receipt = read_optional(s3, BUCKET, receipt_key)
        if existing_receipt is not None and existing_receipt[0] != receipt_body:
            raise ValueError("Repository recovery receipt changed")
        put_immutable(s3, BUCKET, receipt_key, receipt_body)
        receipt_ref = {"key": receipt_key, "sha256": sha(receipt_body)}

        marker = read_optional(s3, BUCKET, prefix + "/_SUCCESS")
        if marker is not None:
            body = required(s3, BUCKET, prefix + "/run_manifest.json")
            bundle = json.loads(body)
            if (json.loads(marker[0]) != {"manifest_sha256": sha(body)}
                    or bundle.get("request") != request
                    or bundle.get("code_contract_sha256") != sha(json_bytes(current))
                    or bundle.get("recovery") != receipt_ref
                    or set(bundle.get("stages", {})) != set(STAGES)):
                raise ValueError("Completed recovery bundle differs from pinned recovery")
            for name in STAGES:
                descriptor = bundle["stages"][name]
                if (descriptor.get("stage"), descriptor.get("run_id"), descriptor.get("snapshot")) != (
                        name, request["run_id"], request["snapshot"]):
                    raise ValueError("Completed bundle stage identity differs: " + name)
                if name in RETAINED_STAGES:
                    retained = json.loads(required(s3, BUCKET, f"{prefix}/stages/{name}.json"))
                    if retained != descriptor or retained != completed[name]:
                        raise ValueError("Completed retained checkpoint differs: " + name)
                if name in RECOVERED_STAGES and descriptor.get("recovery") != receipt_ref:
                    raise ValueError("Completed recovery stage is outside this receipt: " + name)
                verify_descriptor(s3, descriptor, workers=workers)
            publish_current(s3, request, body, replay=True)
            return bundle

        state_body = read_optional(s3, BUCKET, prefix + "/status.json")
        state = json.loads(state_body[0]) if state_body else {
            "run_id": request["run_id"], "snapshot": request["snapshot"], "stages": {}}
        state.setdefault("stages", {})
        state.update(status="RUNNING", phase="INPUT", error=None, recovery=receipt_ref)
        save_state(s3, prefix, local, state)
        stage_client = StageClient(s3, local, request)
        recovered_locks = stage_client.recover()
        if recovered_locks:
            save_event(s3, prefix, local, {"status": "RECOVERED_OWN_LOCKS", "keys": recovered_locks})
        try:
            preflight(s3, request, local)
            save_event(s3, prefix, local, {"phase": "INPUT", "status": "INPUT_READY", "recovery": receipt_ref})
            removed = cleanup_stage(local, "package_version")
            if removed:
                save_event(s3, prefix, local, {"stage": "package_version", "status": "WORKSPACE_CLEANED", "removed": removed})

            # Rehydrate the snapshot's local metadata through the real stage
            # executor and require byte-for-byte descriptor identity.
            state["phase"] = "snapshot"
            state["stages"].setdefault("snapshot", {}).update(
                status="RUNNING", action="REHYDRATE", started_at=utc_now(), finished_at=None, error=None,
                attempt=state["stages"].get("snapshot", {}).get("attempt", 0) + 1)
            save_state(s3, prefix, local, state)
            try:
                snapshot = execute("snapshot", request, completed, stage_client, local)
            except ValueError as error:
                if "Projects source inventory changed" not in str(error):
                    raise
                _restore_project_mtimes(completed["snapshot"], local)
                snapshot = execute("snapshot", request, completed, stage_client, local)
            if snapshot != completed["snapshot"]:
                raise ValueError("Snapshot rehydration descriptor differs from completed checkpoint")
            state["stages"]["snapshot"].update(status="COMPLETE", finished_at=utc_now())
            save_state(s3, prefix, local, state)

            for name in RECOVERED_STAGES:
                state["phase"] = name
                key = f"{prefix}/stages/{name}.json"
                saved = read_optional(s3, BUCKET, key)
                if saved is not None:
                    descriptor = json.loads(saved[0])
                    if descriptor.get("recovery") != receipt_ref:
                        raise ValueError("Later checkpoint is outside this recovery")
                    if (descriptor.get("stage"), descriptor.get("run_id"), descriptor.get("snapshot")) != (
                            name, request["run_id"], request["snapshot"]):
                        raise ValueError("Recovery checkpoint identity differs: " + name)
                    verify_descriptor(s3, descriptor, workers=workers)
                else:
                    record = state["stages"].setdefault(name, {"attempt": 0})
                    record.update(status="RUNNING", attempt=record.get("attempt", 0) + 1,
                                  started_at=utc_now(), finished_at=None, error=None)
                    save_state(s3, prefix, local, state)
                    save_event(s3, prefix, local, {"stage": name, "status": "RUNNING",
                                                   "attempt": record["attempt"], "recovery": receipt_ref})
                    descriptor = execute(name, request, completed, stage_client, local)
                    if (descriptor.get("stage"), descriptor.get("run_id"), descriptor.get("snapshot")) != (
                            name, request["run_id"], request["snapshot"]):
                        raise ValueError("Recovery stage result identity differs: " + name)
                    descriptor = dict(descriptor)
                    descriptor["recovery"] = receipt_ref
                    verify_descriptor(s3, descriptor, workers=workers)
                    put_immutable(s3, BUCKET, key, json_bytes(descriptor))
                completed[name] = descriptor
                save_event(s3, prefix, local, {"stage": name, "status": "COMPLETE", "recovery": receipt_ref})
                state["stages"].setdefault(name, {}).update(status="COMPLETE", action="RECOVERED",
                                                             finished_at=utc_now(), error=None)
                save_state(s3, prefix, local, state)
                removed = cleanup_stage(local, name)
                if removed:
                    save_event(s3, prefix, local, {"stage": name, "status": "WORKSPACE_CLEANED", "removed": removed})

            if code_contract() != current or file_sha256(Path(__file__)) != json.loads(receipt_body)["helper_sha256"]:
                raise ValueError("Recovery generator changed during execution")
            # Re-read the retained checkpoint bodies immediately before
            # publication. A checkpoint changing mid-recovery must prevent a
            # bundle from being published against the original receipt.
            _verify_retained_checkpoints(s3, prefix, completed,
                                         json.loads(receipt_body)["checkpoints"])
            for descriptor in completed.values():
                verify_descriptor(s3, descriptor, workers=workers)
            bundle = {"format_version": 1, "dataset": "curated-bundle", "status": "COMPLETE",
                      "scope": "RAW_TO_CURATED_ONLY", "request": request,
                      "code_contract_sha256": sha(json_bytes(current)), "stages": completed,
                      "calculation_complete": True, "db_loaded": False,
                      "consumer_contract": "pipeline/preprocessing/orchestration/CONTRACT.md",
                      "recovery": receipt_ref}
            body = json_bytes(bundle)
            put_immutable(s3, BUCKET, prefix + "/run_manifest.json", body)
            put_immutable(s3, BUCKET, prefix + "/_SUCCESS", json_bytes({"manifest_sha256": sha(body)}))
            publish_current(s3, request, body)
            state.update(status="COMPLETE", phase="COMPLETE", finished_at=utc_now(), error=None)
            save_state(s3, prefix, local, state)
            return bundle
        except BaseException as error:
            state.update(status="FAILED", phase=state.get("phase", "repository"),
                         error={"type": type(error).__name__, "message": str(error)}, finished_at=utc_now())
            active = state.get("stages", {}).get(state.get("phase"))
            if active is not None:
                active.update(status="FAILED", error=state["error"])
            try:
                save_state(s3, prefix, local, state)
            except Exception:
                pass
            try:
                removed = cleanup_failed(local)
                save_event(s3, prefix, local, {"status": "WORKSPACE_CLEANED_AFTER_FAILURE", "removed": removed})
            except Exception:
                pass
            try:
                save_state(s3, prefix, local, state)
                save_event(s3, prefix, local, {"status": "FAILED", "phase": state["phase"], "error": state["error"]})
            except Exception:
                pass
            raise


__all__ = ["ALLOWED_CHANGES", "ALLOWED_GENERATOR", "RECOVERY_ID", "contract_changes", "recover"]
