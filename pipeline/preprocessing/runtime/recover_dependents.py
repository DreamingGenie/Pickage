"""Recover only the dependents tail from five verified stage checkpoints."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from pipeline.preprocessing.curated.storage import json_bytes, put_immutable, read_optional
from pipeline.preprocessing.orchestration import runner
from pipeline.preprocessing.orchestration.contracts import code_contract, validate_request
from pipeline.preprocessing.orchestration.storage import (BUCKET, StageClient, host_lock, required,
    save_event, save_state, sha, utc_now, verify_descriptor, pinned)
from pipeline.preprocessing.orchestration.workspace import claim, cleanup_failed, cleanup_stage
from pipeline.preprocessing.orchestration.weekly_parent import publish_current
from pipeline.preprocessing.requirements_resolution.input import file_sha256


RECOVERY_ID = "dependents-bounded-v2"
PREDECESSOR_ID = "repository-bounded-v1"
RETAINED_STAGES = ("snapshot", "package_version", "downloads", "repository", "package_snapshot")
DEPENDENTS_FILES = {
    "pipeline/preprocessing/orchestration/dependents_parallel.py",
    "pipeline/preprocessing/version_dependents/historical_input.py",
    "pipeline/preprocessing/version_dependents/historical_production_events.py",
    "pipeline/preprocessing/version_dependents/historical_parallel_input.py",
    "pipeline/preprocessing/version_dependents/historical_production_quality.py",
}


def _changed_files(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    if old.get("runtime") != new.get("runtime"):
        raise ValueError("Dependents recovery runtime differs from predecessor")
    changed = sorted(set(old.get("files", {})) | set(new.get("files", {})))
    changed = [key for key in changed if old.get("files", {}).get(key) != new.get("files", {}).get(key)]
    if set(changed) - DEPENDENTS_FILES:
        raise ValueError("Dependents recovery has unapproved code changes: " + str(changed))
    return changed


def _checkpoint(s3, prefix, name, request, workers):
    body = required(s3, BUCKET, f"{prefix}/stages/{name}.json")
    descriptor = json.loads(body)
    if (descriptor.get("stage"), descriptor.get("run_id"), descriptor.get("snapshot")) != (
            name, request["run_id"], request["snapshot"]):
        raise ValueError("Retained checkpoint identity differs: " + name)
    verify_descriptor(s3, descriptor, workers=workers)
    return body, descriptor


def _verify_retained(s3, prefix, completed, hashes):
    for name in RETAINED_STAGES:
        body = required(s3, BUCKET, f"{prefix}/stages/{name}.json")
        if sha(body) != hashes[name] or json.loads(body) != completed[name]:
            raise ValueError("Retained checkpoint changed during dependents recovery: " + name)


def _verify_request_inputs(s3, request):
    for ref in request["raw_refs"].values():
        pinned(s3, ref)
    targets = request.get("targets", {}).get("dependents")
    if targets:
        pinned(s3, targets)


def _receipt(request, envelope, predecessor_body, predecessor_sha, old, new, hashes):
    body = json_bytes({
        "format": RECOVERY_ID, "recovery_id": RECOVERY_ID,
        "request": request, "original_envelope_sha256": sha(envelope),
        "predecessor_receipt_sha256": predecessor_sha,
        "predecessor_receipt": json.loads(predecessor_body),
        "original_code_contract": old, "new_code_contract": new,
        "changed_dependents_files": _changed_files(old, new),
        "retained_checkpoints": hashes,
        "helper_sha256": file_sha256(Path(__file__)),
        "scope": "REUSE_SNAPSHOT_PACKAGE_VERSION_DOWNLOADS_REPOSITORY_PACKAGE_SNAPSHOT",
    })
    return f"{runner.run_prefix(request)}/recoveries/{RECOVERY_ID}.json", body


def recover(request: dict[str, Any], s3: Any, work_dir: str | Path,
            *, _executor: Callable[..., dict[str, Any]] | None = None) -> dict[str, Any]:
    request = validate_request(request)
    prefix = runner.run_prefix(request)
    local = claim(Path(work_dir).resolve() / request["run_id"], request["run_id"])
    execute = _executor or runner._default_executor
    workers = request.get("options", {}).get("workers", 2)
    with host_lock(s3):
        envelope_body = required(s3, BUCKET, prefix + "/request.json")
        envelope = json.loads(envelope_body)
        if envelope.get("request") != request or envelope.get("work_dir") != str(local):
            raise ValueError("Original request or work directory identity differs")
        predecessor_key = prefix + "/recoveries/repository-bounded-v1.json"
        predecessor_body = required(s3, BUCKET, predecessor_key)
        predecessor = json.loads(predecessor_body)
        if predecessor.get("recovery_id") != PREDECESSOR_ID or predecessor.get("request") != request:
            raise ValueError("Repository predecessor receipt does not match request")
        predecessor_ref = {"key": predecessor_key, "sha256": sha(predecessor_body)}
        if (predecessor.get("original_envelope_sha256") != sha(envelope_body)
                or predecessor.get("original_code_contract") != envelope.get("code_contract")):
            raise ValueError("Repository predecessor is for a different original request")
        current = code_contract()
        old = predecessor["new_code_contract"]
        _changed_files(old, current)
        completed, hashes = {}, {}
        for name in RETAINED_STAGES:
            body, descriptor = _checkpoint(s3, prefix, name, request, workers)
            completed[name], hashes[name] = descriptor, sha(body)
            if name in ("repository", "package_snapshot") and descriptor.get("recovery") != {
                    "key": predecessor_key, "sha256": predecessor_ref["sha256"]}:
                raise ValueError("Retained descriptor is outside repository predecessor receipt: " + name)
        if any(predecessor.get("checkpoints", {}).get(name) != hashes[name]
               for name in ("snapshot", "package_version", "downloads")):
            raise ValueError("Repository predecessor retained checkpoint hashes differ")
        receipt_key, receipt_body = _receipt(request, envelope_body, predecessor_body,
                                             predecessor_ref["sha256"], predecessor["new_code_contract"], current, hashes)
        existing = read_optional(s3, BUCKET, receipt_key)
        if existing is not None and existing[0] != receipt_body:
            raise ValueError("Dependents recovery receipt changed")
        put_immutable(s3, BUCKET, receipt_key, receipt_body)
        receipt_ref = {"key": receipt_key, "sha256": sha(receipt_body)}
        marker = read_optional(s3, BUCKET, prefix + "/_SUCCESS")
        if marker is not None:
            body = required(s3, BUCKET, prefix + "/run_manifest.json")
            bundle = json.loads(body)
            if json.loads(marker[0]) != {"manifest_sha256": sha(body)} or bundle.get("recovery") != receipt_ref:
                raise ValueError("Completed dependents recovery bundle differs from receipt")
            if bundle.get("request") != request or bundle.get("code_contract_sha256") != sha(json_bytes(current)):
                raise ValueError("Completed dependents bundle contract differs")
            _verify_retained(s3, prefix, completed, hashes)
            if set(bundle.get("stages", {})) != set((*RETAINED_STAGES, "dependents")):
                raise ValueError("Completed dependents bundle stage set differs")
            for name in RETAINED_STAGES:
                if bundle["stages"].get(name) != completed[name]:
                    raise ValueError("Completed retained descriptor differs: " + name)
            if bundle["stages"]["dependents"].get("recovery") != receipt_ref:
                raise ValueError("Completed dependents descriptor is outside this receipt")
            saved_tail = json.loads(required(s3, BUCKET, prefix + "/stages/dependents.json"))
            if saved_tail != bundle["stages"]["dependents"]:
                raise ValueError("Completed dependents checkpoint differs from bundle")
            if (saved_tail.get("stage"), saved_tail.get("run_id"), saved_tail.get("snapshot")) != (
                    "dependents", request["run_id"], request["snapshot"]):
                raise ValueError("Completed dependents checkpoint identity differs")
            for descriptor in bundle["stages"].values():
                verify_descriptor(s3, descriptor, workers=workers)
            publish_current(s3, request, body, replay=True)
            cleanup_stage(local, "dependents")
            prior = read_optional(s3, BUCKET, prefix + "/status.json")
            state = json.loads(prior[0]) if prior else {}
            state.update(status="COMPLETE", phase="COMPLETE", error=None, finished_at=utc_now())
            state.setdefault("stages", {}).setdefault("dependents", {}).update(
                status="COMPLETE", error=None, finished_at=utc_now())
            save_state(s3, prefix, local, state)
            return bundle
        stage_client = StageClient(s3, local, request)
        stage_client.recover()
        saved_state = read_optional(s3, BUCKET, prefix + "/status.json")
        state = json.loads(saved_state[0]) if saved_state else {
            "run_id": request["run_id"], "snapshot": request["snapshot"], "stages": {}}
        state.setdefault("stages", {})
        state.update(status="RUNNING", phase="dependents", error=None, recovery=receipt_ref)
        state["stages"].setdefault("dependents", {}).update(
            status="RUNNING", attempt=state["stages"].get("dependents", {}).get("attempt", 0) + 1,
            started_at=utc_now(), finished_at=None, error=None)
        save_state(s3, prefix, local, state)
        save_event(s3, prefix, local, {"stage": "dependents", "status": "RUNNING", "recovery": receipt_ref})
        try:
            _verify_request_inputs(s3, request)
            saved_dependents = read_optional(s3, BUCKET, prefix + "/stages/dependents.json")
            if saved_dependents is not None:
                descriptor = json.loads(saved_dependents[0])
                if descriptor.get("recovery") != receipt_ref:
                    raise ValueError("Existing dependents checkpoint is outside this receipt")
                verify_descriptor(s3, descriptor, workers=workers)
            else:
                descriptor = execute("dependents", request, completed, stage_client, local)
            if (descriptor.get("stage"), descriptor.get("run_id"), descriptor.get("snapshot")) != (
                    "dependents", request["run_id"], request["snapshot"]):
                raise ValueError("Dependents result identity differs")
            descriptor = dict(descriptor)
            descriptor["recovery"] = receipt_ref
            verify_descriptor(s3, descriptor, workers=workers)
            put_immutable(s3, BUCKET, prefix + "/stages/dependents.json", json_bytes(descriptor))
            completed["dependents"] = descriptor
            _verify_retained(s3, prefix, completed, hashes)
            for name in RETAINED_STAGES:
                verify_descriptor(s3, completed[name], workers=workers)
            if required(s3, BUCKET, predecessor_key) != predecessor_body or required(s3, BUCKET, prefix + "/request.json") != envelope_body:
                raise ValueError("Recovery predecessor or original envelope changed during execution")
            if code_contract() != current or file_sha256(Path(__file__)) != json.loads(receipt_body)["helper_sha256"]:
                raise ValueError("Dependents recovery code changed during execution")
            bundle = {"format_version": 1, "dataset": "curated-bundle", "status": "COMPLETE",
                      "scope": "RAW_TO_CURATED_ONLY", "request": request,
                      "code_contract_sha256": sha(json_bytes(current)),
                      "stages": completed, "calculation_complete": True, "db_loaded": False,
                      "consumer_contract": "pipeline/preprocessing/orchestration/CONTRACT.md",
                      "recovery": receipt_ref}
            body = json_bytes(bundle)
            put_immutable(s3, BUCKET, prefix + "/run_manifest.json", body)
            put_immutable(s3, BUCKET, prefix + "/_SUCCESS", json_bytes({"manifest_sha256": sha(body)}))
            publish_current(s3, request, body)
            cleanup_stage(local, "dependents")
            state["stages"]["dependents"].update(status="COMPLETE", finished_at=utc_now(), error=None)
            state.update(status="COMPLETE", phase="COMPLETE", finished_at=utc_now())
            save_state(s3, prefix, local, state)
            save_event(s3, prefix, local, {"status": "COMPLETE", "recovery": receipt_ref})
            return bundle
        except BaseException as error:
            state.update(status="FAILED", error={"type": type(error).__name__, "message": str(error)}, finished_at=utc_now())
            state["stages"]["dependents"].update(status="FAILED", error=state["error"], finished_at=utc_now())
            try:
                save_state(s3, prefix, local, state)
                save_event(s3, prefix, local, {"stage": "dependents", "status": "FAILED", "error": state["error"]})
            except Exception:
                pass
            try:
                cleanup_failed(local)
            except Exception:
                pass
            raise


__all__ = ["DEPENDENTS_FILES", "RECOVERY_ID", "recover"]
