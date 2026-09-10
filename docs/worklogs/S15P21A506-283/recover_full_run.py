"""Verify preserved task-07 results without manufacturing a standard success marker."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import traceback

from pipeline.requirements_resolution import build, runtime
from pipeline.requirements_resolution.input import reverify_inputs
from pipeline.requirements_resolution.policy import canonical_bytes, validate_policy
from verify_full_run import verify

ROOT = Path(__file__).resolve().parents[3]
RUN = ROOT / "data/requirements-resolution/runs/requirements-20260831-v1"
ATTEMPT = RUN / "attempts/20260909T052957543914Z"
PRIOR = ROOT / "data/requirements-resolution/verification/integration-dbf68cf2/run_manifest.json"
GAPS = ["initial_code_sha256_not_persisted", "initial_runtime_identity_not_persisted",
        "original_post_finalize_host_checks_not_observed"]


def read(path):
    return json.loads(build._io_path(path).read_bytes())


def write(path, value):
    with build._io_path(path).open("xb") as stream:
        stream.write(canonical_bytes(value))


def evidence(path):
    size, digest = build._hash_file(path)
    return {"path": str(path), "bytes": size, "sha256": digest,
            "mtime_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()}


def validate_invocations(inputs, policy):
    adapted = copy.deepcopy(inputs)
    adapted["files"] = {}
    roots = [(Path(value).resolve(), "/input/" + key) for key, value in inputs["sources"].items()]
    for table, paths in inputs["files"].items():
        adapted["files"][table] = []
        for value in paths:
            path = Path(value).resolve()
            matches = [(root, target) for root, target in roots if path.is_relative_to(root)]
            if len(matches) != 1:
                raise ValueError("Ambiguous input mount")
            root, target = matches[0]
            adapted["files"][table].append(target + "/" + path.relative_to(root).as_posix())
    for stage in ("prepare", "finalize"):
        expected = {"stage": stage, "inputs": adapted, "policy": policy,
                    "run_id": RUN.name, "shuffle_partitions": 32}
        if stage == "finalize":
            expected.update(prepared_dir="/input/prepared", bridge_dir="/input/bridge")
        if read(ATTEMPT / stage / "invocation.json") != expected:
            raise ValueError("Persisted stage invocation mismatch: " + stage)


def validate_stage_reports(inputs, policy, prepare, final):
    for report in (prepare, final):
        for key, expected in (("snapshot", inputs["snapshot"]), ("input_sha256", inputs["input_sha256"]),
                              ("policy_sha256", policy["sha256"])):
            if report.get(key) != expected:
                raise ValueError("Stage report lineage mismatch: " + key)
    for key, expected in (("run_id", RUN.name), ("curated_run_id", inputs["curated_run_id"]),
                          ("bronze_run_id", inputs["bronze_run_id"])):
        if final.get(key) != expected:
            raise ValueError("Finalize report lineage mismatch: " + key)
    counts = prepare["counts"]
    if (counts["sources"] != counts["candidates"]
            or counts["sources"] != final["output_counts"]["source_outcomes"]
            or counts["declarations"] != final["output_counts"]["declaration_outcomes"]
            or counts["declarations"] != final["selected_declarations"]):
        raise ValueError("Stage report counts disagree")


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = RUN / "verification" / ("recovery-" + stamp)
    destination.mkdir(parents=True, exist_ok=False)
    phase = "capture_evidence"
    def progress(value):
        nonlocal phase
        phase = value
        print(json.dumps({"phase": value, "utc": datetime.now(timezone.utc).isoformat()}), flush=True)
    try:
        if (RUN / "_SUCCESS").exists() or (RUN / "run_manifest.json").exists():
            raise ValueError("Standard completion record exists; inspect it before recovery")
        inputs = read(ATTEMPT / "input-manifest.json")
        policy = read(ROOT / "data/requirements-resolution/policy.json")
        doc = validate_policy(policy)
        if (doc["kinds"], doc["unknown_published_at"], doc["unresolved"]) != (["dependencies"], "exclude", "partial"):
            raise ValueError("Approved policy mismatch")
        validate_invocations(inputs, policy)
        prepare = read(ATTEMPT / "prepare/result.json")
        final = read(ATTEMPT / "finalize/result.json")
        validate_stage_reports(inputs, policy, prepare, final)
        if final["resolution_status"] != "PARTIAL" or final["ready_for_dependents"] is not False:
            raise ValueError("Unexpected resolution status")
        current = {"code_sha256": build._code_fingerprint(),
                   "runtime_identity": build._runtime_identity(None)}
        current["runtime_metadata"] = build._runtime_metadata(current["runtime_identity"])
        prior = read(PRIOR)
        corroboration = {"prior_integration_manifest": evidence(PRIOR),
                         "same_code_sha256": prior["code_sha256"] == current["code_sha256"],
                         "same_runtime_metadata": prior["runtime_metadata"] == current["runtime_metadata"],
                         "interpretation": "Supporting evidence only; not an attestation of this attempt's initial code/runtime"}
        tracked = [ATTEMPT / "input-manifest.json", ROOT / "data/requirements-resolution/policy.json", PRIOR]
        tracked += [ATTEMPT / stage / filename for stage in ("prepare", "finalize")
                    for filename in ("invocation.json", "result.json")]
        original_evidence = [evidence(path) for path in tracked]
        write(destination / "start_evidence.json", {"current_observation": current,
              "corroboration": corroboration, "persisted_records": original_evidence, "gaps": GAPS})
        progress("reverify_local_inputs_and_remote_approved_manifests")
        s3 = build._client_from_env(ROOT.parent / "S15P21A506/pipeline/minio/.env")
        reverify_inputs(inputs, s3)
        write(destination / "input_verification.json", {"passed": True, "input_sha256": inputs["input_sha256"],
              "files": len(inputs["file_records"]), "local_content_sha256_checked": True,
              "approved_remote_manifests_checked": True, "utc": datetime.now(timezone.utc).isoformat()})
        progress("capture_output_content_inventory")
        output = ATTEMPT / "finalize/outputs"
        files = build._output_inventory(output)
        candidate = {"status": "RECOVERY_CANDIDATE", "resolution_status": "PARTIAL", "ready_for_dependents": False,
                     "request": {"run_id": RUN.name}, "input": inputs, "policy": policy,
                     "runtime_metadata": current["runtime_metadata"],
                     "final_output": output.relative_to(RUN).as_posix(), "finalize_report": final,
                     "prepare_report": prepare, "files": files,
                     "recovery": {"gaps": GAPS, "current_observation": current, "corroboration": corroboration,
                                  "output_hash_semantics": "Post-reboot validation baseline; no pre-interruption output hash was persisted"}}
        candidate_path = RUN / ("recovery_candidate-" + stamp + ".json")
        write(candidate_path, candidate)
        candidate_evidence = evidence(candidate_path)
        progress("verify_output_content_rows_policy_and_relationships")
        report_path = destination / "data_verification.json"
        report = verify(candidate_path, report_path, candidate_manifest=True)
        report_evidence = evidence(report_path)
        if report["manifest_sha256"] != candidate_evidence["sha256"]:
            raise ValueError("Verifier read different candidate bytes")
        progress("verify_stable_evidence_at_completion")
        reverify_inputs(inputs, s3)
        build._verify_inventory(output, files)
        if build._code_fingerprint() != current["code_sha256"] or build._runtime_metadata(current["runtime_identity"]) != current["runtime_metadata"]:
            raise ValueError("Code/runtime changed during recovery verification")
        if [evidence(path) for path in tracked] != original_evidence:
            raise ValueError("Persisted evidence changed during recovery verification")
        if evidence(candidate_path) != candidate_evidence or evidence(report_path) != report_evidence:
            raise ValueError("Candidate or verification report changed")
        if (RUN / "_SUCCESS").exists() or (RUN / "run_manifest.json").exists():
            raise ValueError("Standard completion record unexpectedly appeared")
        record = {"status": "RECOVERED_VERIFIED_WITH_PROVENANCE_GAP",
                  "resolution_status": "PARTIAL", "ready_for_dependents": False,
                  "standard_success_marker_written": False, "published": False,
                  "provenance_gaps": GAPS, "data_checks_passed": report["data_checks_passed"],
                  "candidate": candidate_evidence, "data_verification": report_evidence,
                  "current_observation": current, "corroboration": corroboration,
                  "completed_utc": datetime.now(timezone.utc).isoformat(),
                  "scope": "Preserved direct dependency resolution data; no recalculation, MinIO writes, dependents_count or DB load"}
        write(destination / "recovery_record.json", record)
        progress("complete")
        print(json.dumps({"record": str(destination / "recovery_record.json")}), flush=True)
    except Exception as error:
        write(destination / "failure.json", {"phase": phase, "type": type(error).__name__, "error": str(error)})
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
