"""Sequential snapshot execution with immutable checkpoints and bundle commit."""
import json
import sys
from pathlib import Path

from pipeline.preprocessing.curated.storage import json_bytes, put_immutable, read_optional
from pipeline.preprocessing.orchestration.contracts import STAGES, code_contract, validate_request
from pipeline.preprocessing.orchestration.weekly_parent import publish_current
from pipeline.preprocessing.orchestration.storage import BUCKET, PREFIX, WaitingInput, StageClient, atomic_json, host_lock, required, save_event, save_state, sha, utc_now, verify_descriptor


def run_prefix(request):
    return f"{PREFIX}/snapshot={request['snapshot']}/run_id={request['run_id']}"


def plan(request):
    request = validate_request(request)
    return {"request": request, "stages": list(STAGES), "scope": "RAW_TO_CURATED_ONLY",
            "output_bucket": BUCKET, "output_prefix": run_prefix(request),
            "execution": "SINGLE_HOST_SEQUENTIAL", "performs_collection": False,
            "performs_db_load": False, "remote_inputs_checked": False}


def status(request, s3):
    request = validate_request(request)
    prefix = run_prefix(request)
    registered = read_optional(s3, BUCKET, prefix + "/request.json")
    if registered is not None and json.loads(registered[0]).get("request") != request:
        raise ValueError("Run belongs to a different request")
    marker = read_optional(s3, BUCKET, prefix + "/_SUCCESS")
    saved = read_optional(s3, BUCKET, prefix + "/status.json")
    result = json.loads(saved[0]) if saved else {"run_id": request["run_id"], "status": "NOT_STARTED"}
    if marker is not None:
        body = required(s3, BUCKET, prefix + "/run_manifest.json")
        if json.loads(marker[0]) != {"manifest_sha256": sha(body)}:
            raise ValueError("Bundle completion marker mismatch")
        bundle = json.loads(body)
        if bundle.get("request") != request:
            raise ValueError("Bundle belongs to a different request")
        result.update(status="COMPLETE", bundle_manifest_key=prefix + "/run_manifest.json",
                      bundle_manifest_sha256=sha(body), output_bytes_reverified=False)
    return result


def _default_executor(name, request, completed, s3, work_dir):
    if name == "dependents":
        from pipeline.preprocessing.orchestration.dependents import execute_stage
        return execute_stage(request, completed, s3, work_dir)
    from pipeline.preprocessing.orchestration.stages import execute_stage
    return execute_stage(name, request, completed, s3, work_dir)


def _default_preflight(s3, request, work_dir):
    from pipeline.preprocessing.orchestration.intake import preflight
    return preflight(s3, request, work_dir)


def _validate_work_path(local, run_id):
    # Docker can create files which the Windows host cannot subsequently open.
    # Check the native Spark output layout before publishing any run state.
    if sys.platform == "win32":
        sample = (local / "repository" / run_id / "attempts" / ("0" * 32)
                  / "outputs" / "quality" / "project_observations"
                  / "part-00000-00000000-0000-0000-0000-000000000000-c000.snappy.parquet")
        if len(str(sample).encode("utf-16-le")) // 2 >= 260:
            raise ValueError("Windows output path would exceed 259 characters; "
                             "use a shorter --work-dir and run_id (for example C:/pickage-work and s20260831)")


def run(request, s3, work_dir, *, resume=False, failpoint=None, _executor=None, _preflight=None):
    """Run or resume one immutable request. Private hooks are for failure tests.

    Stages may publish their datasets independently. Only this final bundle's
    _SUCCESS announces completion of the entire preprocessing request.
    """
    request = validate_request(request)
    prefix = run_prefix(request)
    local = Path(work_dir).resolve() / request["run_id"]
    _validate_work_path(local, request["run_id"])
    if request.get("options", {}).get("work_cleanup", "none") == "stage":
        from pipeline.preprocessing.orchestration.workspace import claim
        claim(local, request["run_id"])
    else:
        local.mkdir(parents=True, exist_ok=True)
    execute = _executor or _default_executor
    preflight = _preflight or _default_preflight
    workers = request.get("options", {}).get("workers", 2)
    contract = code_contract()
    envelope = {"request": request, "code_contract": contract, "work_dir": str(local)}
    checkpoint_prefix = prefix + "/stages/"
    with host_lock(s3):
        prior = read_optional(s3, BUCKET, prefix + "/request.json")
        if prior is not None and json.loads(prior[0]) != envelope:
            raise ValueError("Run ID belongs to different inputs/code/work directory; use a new run ID")
        if resume and prior is None:
            raise ValueError("Cannot resume an unknown run")
        put_immutable(s3, BUCKET, prefix + "/request.json", json_bytes(envelope))
        atomic_json(local / "request.json", envelope)
        stage_client = StageClient(s3, local, request)
        recovered = stage_client.recover()
        if recovered:
            save_event(s3, prefix, local, {"status": "RECOVERED_OWN_LOCKS", "keys": recovered})
        old_state = read_optional(s3, BUCKET, prefix + "/status.json")
        state = json.loads(old_state[0]) if old_state else {
            "run_id": request["run_id"], "snapshot": request["snapshot"],
            "started_at": utc_now(), "stages": {}}
        state.update(status="RUNNING", phase="INPUT", error=None)
        save_state(s3, prefix, local, state)
        completed = {}
        try:
            marker = read_optional(s3, BUCKET, prefix + "/_SUCCESS")
            if marker is not None:
                body = required(s3, BUCKET, prefix + "/run_manifest.json")
                bundle = json.loads(body)
                if (json.loads(marker[0]) != {"manifest_sha256": sha(body)}
                        or bundle.get("request") != request
                        or bundle.get("code_contract_sha256") != sha(json_bytes(contract))
                        or set(bundle.get("stages", {})) != set(STAGES)):
                    raise ValueError("Completed bundle identity or stage set differs")
                for name, descriptor in bundle["stages"].items():
                    if (descriptor.get("stage") != name or descriptor.get("run_id") != request["run_id"]
                            or descriptor.get("snapshot") != request["snapshot"]):
                        raise ValueError("Completed bundle stage identity differs")
                    verify_descriptor(s3, descriptor, workers=workers)
                # A newer ID registry does not prevent read-only verification of
                # an older completed bundle; never move its current pointer back.
                publish_current(s3, request, body, replay=True)
                state.update(status="COMPLETE", phase="COMPLETE", finished_at=utc_now(),
                             bundle_manifest_key=prefix + "/run_manifest.json", bundle_manifest_sha256=sha(body))
                save_state(s3, prefix, local, state)
                return bundle
            preflight(s3, request, local)
            save_event(s3, prefix, local, {"phase": "INPUT", "status": "INPUT_READY"})
            for name in STAGES:
                state["phase"] = name
                key = checkpoint_prefix + name + ".json"
                checkpoint = read_optional(s3, BUCKET, key)
                if checkpoint is not None:
                    descriptor = json.loads(checkpoint[0])
                    if (descriptor.get("stage") != name or descriptor.get("snapshot") != request["snapshot"]
                            or descriptor.get("run_id") != request["run_id"]):
                        raise ValueError("Stage checkpoint identity mismatch")
                    verify_descriptor(s3, descriptor, workers=workers)
                    if name == "snapshot" and _executor is None:
                        metadata = descriptor.get("metadata", {})
                        candidate = Path(metadata.get("candidate_path", ""))
                        projects = Path(metadata.get("projects_dir", ""))
                        if not candidate.is_file() or not projects.is_dir():
                            replayed = execute(name, request, completed, stage_client, local)
                            verify_descriptor(s3, replayed, workers=workers)
                            descriptor = replayed
                    completed[name] = descriptor
                    state["stages"].setdefault(name, {}).update(status="COMPLETE", action="REVERIFIED")
                    save_state(s3, prefix, local, state)
                    continue
                record = state["stages"].setdefault(name, {"attempt": 0})
                record.update(status="RUNNING", attempt=record.get("attempt", 0) + 1,
                              started_at=utc_now(), finished_at=None, error=None)
                save_state(s3, prefix, local, state)
                save_event(s3, prefix, local, {"stage": name, "status": "RUNNING", "attempt": record["attempt"]})
                if failpoint:
                    failpoint("before_stage:" + name)
                descriptor = execute(name, request, completed, stage_client, local)
                if (descriptor.get("stage") != name or descriptor.get("run_id") != request["run_id"]
                        or descriptor.get("snapshot") != request["snapshot"]):
                    raise ValueError("Stage result identity mismatch")
                verify_descriptor(s3, descriptor, workers=workers)
                if failpoint:
                    failpoint("after_stage:" + name)
                put_immutable(s3, BUCKET, key, json_bytes(descriptor))
                completed[name] = descriptor
                record.update(status="COMPLETE", finished_at=utc_now(),
                              manifest_key=descriptor["manifest_key"], manifest_sha256=descriptor["manifest_sha256"])
                save_state(s3, prefix, local, state)
                save_event(s3, prefix, local, {"stage": name, "status": "COMPLETE", "attempt": record["attempt"],
                                             "manifest_sha256": descriptor["manifest_sha256"]})
                if request.get("options", {}).get("work_cleanup", "none") == "stage":
                    from pipeline.preprocessing.orchestration.workspace import cleanup_stage
                    removed = cleanup_stage(local, name)
                    if removed:
                        save_event(s3, prefix, local, {"stage": name, "status": "WORKSPACE_CLEANED",
                                                       "removed": removed})
            if code_contract() != contract:
                raise ValueError("Generator code changed during execution")
            # Recheck references at commit: later stages cannot silently replace earlier results.
            for descriptor in completed.values():
                verify_descriptor(s3, descriptor, workers=workers)
            bundle = {"format_version": 1, "dataset": "curated-bundle", "status": "COMPLETE",
                      "scope": "RAW_TO_CURATED_ONLY", "request": request,
                      "code_contract_sha256": sha(json_bytes(contract)), "stages": completed,
                      "calculation_complete": True, "db_loaded": False,
                      "consumer_contract": "pipeline/preprocessing/orchestration/CONTRACT.md"}
            body = json_bytes(bundle)
            if failpoint:
                failpoint("before_bundle_manifest")
            put_immutable(s3, BUCKET, prefix + "/run_manifest.json", body)
            if failpoint:
                failpoint("before_bundle_marker")
            put_immutable(s3, BUCKET, prefix + "/_SUCCESS", json_bytes({"manifest_sha256": sha(body)}))
            if failpoint:
                failpoint("after_bundle_marker")
            publish_current(s3, request, body)
            state.update(status="COMPLETE", phase="COMPLETE", finished_at=utc_now(),
                         bundle_manifest_key=prefix + "/run_manifest.json", bundle_manifest_sha256=sha(body))
            save_state(s3, prefix, local, state)
            atomic_json(local / "bundle.json", bundle)
            return bundle
        except BaseException as error:
            state.update(status="WAITING_INPUT" if isinstance(error, WaitingInput) else "FAILED",
                         error={"type": type(error).__name__, "message": str(error)}, finished_at=utc_now())
            active = state["stages"].get(state["phase"])
            if active is not None and active.get("status") == "RUNNING":
                active.update(status="FAILED", error=state["error"], finished_at=utc_now())
            # Keep the original failure even if remote evidence storage is unavailable.
            atomic_json(local / "status.json", state)
            try:
                save_state(s3, prefix, local, state)
                save_event(s3, prefix, local, {"status": state["status"], "phase": state["phase"], "error": state["error"]})
            except Exception:
                pass
            if request.get("options", {}).get("work_cleanup", "none") == "stage":
                try:
                    from pipeline.preprocessing.orchestration.workspace import cleanup_failed
                    removed = cleanup_failed(local)
                    save_event(s3, prefix, local, {"status": "WORKSPACE_CLEANED_AFTER_FAILURE", "removed": removed})
                except Exception:
                    pass
            raise
