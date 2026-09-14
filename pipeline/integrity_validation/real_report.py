"""Assemble real integration evidence; never grants load/publication approval."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from .real_checks import assess_metadata
from .real_rollups import assess_rollups
from .real_sources import bind_sources
from .real_time import assess_time


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_metadata(folder):
    from .real_db import metadata_queries
    return {name: read(Path(folder) / (name + ".json")) for name in metadata_queries("unused_schema")}


def assess_sample_binding(sample, metadata):
    expected = {e["snapshot_at"]: e for e in metadata["executions"] if e["dataset"] == "package-snapshot" and e["status"] == "PUBLISHED"}
    failures = []
    dates = sorted(expected)
    chosen = list(dict.fromkeys([dates[0], dates[len(dates)//2], dates[-1]])) if dates else []
    if sample.get("status") != "PASS" or sample.get("mismatches") != [] or not sample.get("samples") or sample.get("dates") != chosen:
        failures.append("missing, failed or incomplete source samples")
    files = sample.get("files", [])
    if sorted(f.get("date") for f in files) != sorted(chosen):
        failures.append("sample file date coverage differs")
    for file in files:
        execution = expected.get(file["date"])
        pins = execution["input_metadata"].get("files", []) if execution else []
        pin = next((p for p in pins if p.get("role") == "package_snapshot"), {})
        if not pin or any(file.get(k) != pin.get(k) for k in ("bytes", "sha256")) or file.get("read_rows") != pin.get("row_count"):
            failures.append("sample file differs from DB manifest pin: " + file["date"])
    return {"id": "source_samples_bound_to_db_manifests", "status": "FAIL" if failures else "PASS",
            "evidence": {"dates": chosen, "samples": len(sample.get("samples", [])), "failures": failures,
                         "source_bytes": sample.get("total_bytes"), "all_source_rows_proven": False}}


def assess_prior_attempts(metadata, prior):
    from pipeline.snapshot.policy import parse_timestamp
    failed = [a for a in metadata["attempts"] if a["status"] == "FAILED"]
    missing, proven = [], []
    for active in failed:
        execution = next(e for e in metadata["executions"] if e["execution_id"] == active["execution_id"])
        valid = []
        for candidate in prior:
            if candidate.get("execution_id") != active["execution_id"] or candidate.get("status") not in {"PUBLISHED", "REVERIFIED"}:
                continue
            try:
                earlier = parse_timestamp(candidate["completed_at"]) <= parse_timestamp(active["created_at"])
            except (KeyError, ValueError, TypeError):
                earlier = False
            counts = execution.get("expected_counts", {})
            if earlier and counts and all(candidate.get("actual_counts", {}).get(k) == v for k, v in counts.items()):
                valid.append(candidate["attempt_id"])
        if valid:
            proven.append({"execution_id": active["execution_id"], "prior_successful_attempt_ids": valid, "failed_active_attempt_id": active["attempt_id"]})
        else:
            missing.append(active["execution_id"])
    return {"id": "failed_active_prior_publication_evidence", "status": "NOT_RUN" if missing else "PASS",
            "evidence": {"proven": proven, "missing": missing, "failed_reverification_is_not_success": True}}


def assemble(original_root, plan_path, evidence_dir, samples_path=None):
    folder = Path(evidence_dir)
    samples_path = Path(samples_path) if samples_path else folder / "source-samples.json"
    plan = read(plan_path)
    before, after = load_metadata(folder / "metadata"), load_metadata(folder / "metadata-after")
    source = bind_sources(Path(original_root), before, plan)
    scans = {name: read(folder / "full-scan" / (name + ".json")) for name in ("package", "version", "package_snapshot", "package_version_snapshot")}
    checks = assess_metadata(before, plan) + [assess_time(before)]
    checks += assess_rollups(scans, before, source["package_snapshot_results"])
    checks += [{"id": c["name"], "status": c["status"], "evidence": {k: v for k, v in c.items() if k not in {"name", "status"}}} for c in source["checks"]]
    changes = [key for key in before if before[key] != after[key]]
    checks.append({"id": "metadata_before_after_unchanged", "status": "FAIL" if changes else "PASS",
                   "evidence": {"changed_sections": changes, "transaction_scope": "separate read-only repeatable-read transaction per query",
                                "single_shared_mvcc_snapshot": False, "unchanged_metadata_proves_no_concurrent_payload_writes": False}})
    checks.append(assess_sample_binding(read(samples_path), before))
    prior_path = folder / "prior-attempts.json"
    checks.append(assess_prior_attempts(before, read(prior_path) if prior_path.exists() else []))
    state = read(folder / "full-scan/status.json")
    complete = state.get("status") == "COMPLETE" and all(state.get("results", {}).get(t, {}).get("status") == "COMPLETE" for t in scans)
    checks.append({"id": "full_scan_completed", "status": "PASS" if complete else "FAIL", "evidence": state})
    failures = [c for c in checks if c["status"] == "FAIL"]
    report = {"report_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
              "scope": "real local read-only integrity validation", "status": "PARTIAL",
              "ready_for_load": False, "ready_for_publication": False, "task_09_complete": False,
              "checks": checks, "summary": {status: sum(c["status"] == status for c in checks) for status in ("PASS", "FAIL", "NOT_RUN")},
              "failed_checks": [c["id"] for c in failures],
              "deferred": source["explicit_deferred"] + ["full_source_key_value_and_temporal_eligibility_revalidation",
                            "full_dataset_failure_recovery_reexecution", "representative_performance_benchmark"],
              "source_checked_files": source["checked_files"], "input_evidence": [], "validator_files": []}
    repo = Path(__file__).resolve().parents[2]
    code_files = [*sorted(Path(__file__).parent.glob("real_*.py")), repo / "pipeline/snapshot/policy.py",
                  repo / "pipeline/package_snapshot/policy.py", repo / "pipeline/requirements_resolution/policy.py",
                  repo / "pipeline/version_dependents/historical_db_reload.py"]
    for path in code_files:
        report["validator_files"].append({"path": path.relative_to(repo).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    paths = [Path(plan_path), *sorted((folder / "metadata").glob("*.json")), *sorted((folder / "metadata-after").glob("*.json")),
             *sorted((folder / "full-scan").glob("*.json")), samples_path]
    if prior_path.exists():
        paths.append(prior_path)
    for path in paths:
        raw = path.read_bytes()
        report["input_evidence"].append({"path": str(path.absolute()), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-root", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=Path, help="Explicit sample evidence JSON; defaults to evidence-dir/source-samples.json")
    args = parser.parse_args()
    report = assemble(args.original_root, args.plan, args.evidence_dir, args.samples)
    # Refuse to silently replace an older evidence report.
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"status": report["status"], "summary": report["summary"], "failed_checks": report["failed_checks"]}))
    return 2 if report["summary"]["FAIL"] or report["summary"]["NOT_RUN"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
