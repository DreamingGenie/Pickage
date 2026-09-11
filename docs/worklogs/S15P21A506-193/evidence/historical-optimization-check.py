"""Run from repository root; only a bounded synthetic H2/H3 comparison."""
import hashlib
import json
import statistics
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pipeline.requirements_resolution.bridge import discover_runtime
from pipeline.version_dependents.historical import compute_optimized
from pipeline.version_dependents.historical_reference import compute_reference


def checksum(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def expanded(optimized):
    # Only the small comparison artifact expands zero keys and interval outcomes.
    snapshots = []
    for index, row in enumerate(optimized["snapshots"]):
        counts = {(t["package_id"], t["version"]): 0 for t in optimized["target_population"] if t["birth_index"] <= index}
        counts.update({(t["package_id"], t["version"]): t["dependents_count"] for t in row["counts"]})
        result = {**row, "counts": [{"package_id": p, "version": v, "dependents_count": c} for (p, v), c in sorted(counts.items())]}
        for intervals, outcomes, keys in [("declaration_intervals", "declaration_outcomes", ("source_package_id", "source_version", "declaration_index")),
                                            ("source_intervals", "source_outcomes", ("source_package_id", "source_version"))]:
            rows = [{k: v for k, v in t.items() if k not in {"start_index", "end_index"}}
                    for t in optimized[intervals] if t["start_index"] <= index < t["end_index"]]
            result[outcomes] = sorted(rows, key=lambda t: tuple(t[k] for k in keys))
        snapshots.append(result)
    return snapshots


def repeated_fixture():
    stamps = [(datetime(2026, 8, 1, 12, tzinfo=timezone.utc) + timedelta(days=i)).isoformat() for i in range(16)]
    versions = [{"package_id": 1, "version": f"1.0.{i}", "published_at": stamps[0], "dependency_error": False} for i in range(120)]
    versions += [{"package_id": 2, "version": f"1.{i}.0", "published_at": stamps[i * 4], "dependency_error": False} for i in range(4)]
    requirements = [{"package_id": v["package_id"], "version": v["version"], "dependencies": [
        {"name": "dep", "requirement": "^1.0.0"}, {"name": "dep", "requirement": ">=1.0.0 <2.0.0"}]
        if v["package_id"] == 1 else []} for v in versions]
    return {"observed_snapshot_timestamp": stamps[-1],
            "calendar": [{"snapshot_at": s[:10], "snapshot_timestamp": s} for s in stamps],
            "packages": [{"package_id": 1, "name": "app"}, {"package_id": 2, "name": "dep"}],
            "versions": versions, "requirements": requirements}


def main():
    evidence = Path("docs/worklogs/S15P21A506-193/evidence")
    output = Path("data/version-dependents/optimization-examples") / datetime.now(timezone.utc).strftime("run_id=h3-%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True, exist_ok=False)
    baseline = json.loads((evidence / "historical-reference-validation.json").read_bytes())["code_sha256"]
    baseline.update(json.loads((evidence / "historical-count-plan-check.json").read_bytes())["code_before_final_plan_sha256"])
    for path, value in baseline.items():
        assert checksum(path) == value, path
    code_paths = ["pipeline/version_dependents/historical.py", "pipeline/version_dependents/historical_semver_worker.cjs",
                  "docs/worklogs/S15P21A506-193/evidence/historical-optimization-check.py"]
    code = {p: checksum(p) for p in code_paths}
    runtime = discover_runtime()
    records = []
    fixtures = {"golden": json.loads(Path("pipeline/version_dependents/fixtures/historical_reference.json").read_bytes()),
                "repeated": repeated_fixture()}
    for name, fixture in fixtures.items():
        fixture_path = output / f"{name}-fixture.json"
        fixture_path.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")
        timings = {"reference": [], "optimized": []}
        results = {}
        for trial in range(3 if name == "repeated" else 1):
            methods = [("reference", compute_reference), ("optimized", compute_optimized)]
            if trial % 2:
                methods.reverse()
            for method, fn in methods:
                started = time.monotonic()
                results[method] = fn(fixture, runtime=runtime, log_path=output / f"{name}-{method}-{trial}.log")
                timings[method].append(time.monotonic() - started)
            assert expanded(results["optimized"]) == results["reference"]["snapshots"]
            for field in ("semver_sha256", "package_arg_sha256", "dependency_closure_sha256"):
                assert results["reference"]["runtime"][field] == results["optimized"]["runtime"][field]
        saved = {}
        for method, result in results.items():
            path = output / f"{name}-{method}.json"
            path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            saved[method] = {"path": str(path.resolve()), "sha256": checksum(path)}
        medians = {method: statistics.median(values) for method, values in timings.items()}
        records.append({"fixture": name, "fixture_sha256": checksum(fixture_path), "snapshots": len(fixture["calendar"]),
                        "versions": len(fixture["versions"]), "timings_seconds": timings, "median_seconds": medians,
                        "observed_speedup": medians["reference"] / medians["optimized"],
                        "all_counts_states_quality_match": True, "runtime_fingerprints_match": True,
                        "metrics": results["optimized"]["metrics"], "saved": saved})
    for path, value in {**baseline, **code}.items():
        assert checksum(path) == value, path
    receipt = {"at": datetime.now(timezone.utc).isoformat(), "status": "PASS", "output": str(output.resolve()),
               "scope": "Synthetic golden and repeated lookup fixture only; not real historical performance",
               "legacy_files_verified_unchanged": len(baseline), "code_sha256": code, "cases": records,
               "actual_229_snapshot_count_executed": False, "database_access": False, "ready_for_load": False}
    (evidence / "historical-optimization-comparison.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
