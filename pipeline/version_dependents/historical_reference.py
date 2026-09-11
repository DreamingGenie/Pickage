"""Bounded, per-snapshot reference calculation for historical count tests."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys
import time

from pipeline.requirements_resolution.bridge import NodeSession, discover_runtime
from pipeline.requirements_resolution.input import file_sha256
from pipeline.requirements_resolution.policy import canonical_bytes, sha256
from pipeline.snapshot.policy import parse_timestamp


MAX_VERSIONS = 512
MAX_DECLARATIONS = 2048
MAX_SNAPSHOTS = 32
MAX_COMPARISONS = 2_000_000
MAX_FIXTURE_BYTES = 4 * 1024 * 1024
SOURCE_GAPS = {"MISSING_REQUIREMENTS", "NULL_DEPENDENCY_LIST", "DEPENDENCY_EXTRACTION_ERROR",
               "DEPENDENCY_EXTRACTION_UNKNOWN"}


def _identity(row):
    pid, version = row.get("package_id"), row.get("version")
    if type(pid) is not int or pid <= 0 or not isinstance(version, str) or not version.strip():
        raise ValueError("Invalid fixture package-version identity")
    return pid, version


def _validate(fixture):
    """Only normalized, mapped release versions belong in this small oracle."""
    if not isinstance(fixture, dict):
        raise ValueError("Reference fixture must be an object")
    for field in ("calendar", "packages", "versions", "requirements"):
        if not isinstance(fixture.get(field), list):
            raise ValueError("Missing fixture list: " + field)
        if any(not isinstance(row, dict) for row in fixture[field]):
            raise ValueError("Fixture rows must be objects: " + field)
    if (not 0 < len(fixture["calendar"]) <= MAX_SNAPSHOTS
            or not 0 < len(fixture["versions"]) <= MAX_VERSIONS
            or len(fixture["packages"]) > MAX_VERSIONS
            or len(fixture["requirements"]) > MAX_VERSIONS):
        raise ValueError("Reference fixture exceeds small-data bounds or has an empty calendar/population")
    observed = parse_timestamp(fixture["observed_snapshot_timestamp"])
    calendar, days = [], set()
    for row in fixture["calendar"]:
        stamp = parse_timestamp(row["snapshot_timestamp"])
        day = stamp.date().isoformat()
        if (row.get("snapshot_at") != day or day in days or stamp > observed
                or (calendar and stamp <= calendar[-1][1])):
            raise ValueError("Reference calendar date/order/observation mismatch")
        calendar.append((day, stamp))
        days.add(day)
    packages, names = {}, set()
    for row in fixture["packages"]:
        pid, name = row.get("package_id"), row.get("name")
        if (type(pid) is not int or pid <= 0 or pid in packages or not isinstance(name, str)
                or not name.strip() or "\x00" in name or name in names):
            raise ValueError("Invalid or duplicate fixture package")
        packages[pid] = name
        names.add(name)
    versions = {}
    for row in fixture["versions"]:
        key = _identity(row)
        if key in versions or key[0] not in packages:
            raise ValueError("Duplicate or unmapped fixture version")
        if row.get("is_release", True) is not True:
            raise ValueError("Reference input requires mapped release versions")
        if "published_at" not in row or "dependency_error" not in row:
            raise ValueError("Publication and extraction error fields must be explicit")
        if row["dependency_error"] is not None and type(row["dependency_error"]) is not bool:
            raise ValueError("Extraction error must be boolean or NULL")
        published = None if row["published_at"] is None else parse_timestamp(row["published_at"])
        versions[key] = {"published": published, "dependency_error": row["dependency_error"]}
    requirements, declaration_count = {}, 0
    for row in fixture["requirements"]:
        key = _identity(row)
        if key in requirements or key not in versions:
            raise ValueError("Duplicate or unmapped fixture requirements")
        if "dependencies" not in row:
            raise ValueError("A present requirements row needs an explicit dependency list or NULL")
        for kind in ("dependencies", "peer_dependencies", "optional_dependencies"):
            items = row.get(kind)
            if items is not None and not isinstance(items, list):
                raise ValueError("Fixture dependency fields must be arrays or NULL")
            if items is not None and len(items) > MAX_DECLARATIONS:
                raise ValueError("Reference fixture exceeds declaration bounds")
        for item in row["dependencies"] or []:
            if item is not None and (not isinstance(item, dict) or any(
                    item.get(field) is not None and not isinstance(item.get(field), str)
                    for field in ("name", "requirement"))):
                raise ValueError("Fixture declaration must preserve nullable string name/range fields")
        declaration_count += len(row["dependencies"] or [])
        requirements[key] = row
    if (declaration_count > MAX_DECLARATIONS
            or len(calendar) * len(versions) * max(declaration_count, 1) > MAX_COMPARISONS):
        raise ValueError("Reference fixture exceeds bounded comparison work")
    return calendar, packages, versions, requirements


def _source_status(present, declarations, extraction_error, total, resolved):
    if not present:
        return "MISSING_REQUIREMENTS"
    if declarations is None:
        return "NULL_DEPENDENCY_LIST"
    if extraction_error is True:
        return "DEPENDENCY_EXTRACTION_ERROR"
    if extraction_error is None:
        return "DEPENDENCY_EXTRACTION_UNKNOWN"
    if total == 0:
        return "OBSERVED_NO_DEPENDENCIES"
    if resolved == total:
        return "RESOLVED"
    return "PARTIAL" if resolved else "UNRESOLVED"


def _resolve(node, name, requirement, candidates, known_names):
    if not isinstance(name, str) or not name or "\x00" in name:
        return {"status": "INVALID_PACKAGE_NAME", "normalized_range": None, "target_version": None}
    # Intentionally reset candidates for every declaration and every snapshot.
    # No winner intervals, cache across dates, or delta logic is shared with H3.
    node.request({"op": "start", "name": name})
    node.request({"op": "candidates", "versions": candidates.get(name, [])})
    reply = node.request({"op": "resolve", "requirements": [requirement]})[0]
    if reply["requirement"] != requirement:
        raise ValueError("Resolver changed original requirement")
    if reply["status"] == "NO_ELIGIBLE_TARGET" and name not in known_names:
        reply["status"] = "UNMAPPED_TARGET_PACKAGE"
    return reply


def compute_reference(fixture: dict, *, runtime=None, log_path: Path) -> dict:
    calendar, packages, versions, requirements = _validate(fixture)
    snapshots = []
    ids_by_name = {name: pid for pid, name in packages.items()}
    with NodeSession(runtime or discover_runtime(), Path(log_path)) as node:
        metadata = node.request({"op": "metadata"})
        for day, stamp in calendar:
            eligible = {key: row for key, row in versions.items()
                        if row["published"] is not None and row["published"] <= stamp}
            candidates = defaultdict(list)
            for pid, version in sorted(eligible):
                candidates[packages[pid]].append(version)
            targets, rejection_counts = set(), Counter()
            for name, values in sorted(candidates.items()):
                node.request({"op": "start", "name": name})
                response = node.request({"op": "candidates", "versions": values})
                rejected = {row["version"]: row["reason"] for row in response["rejected"]}
                rejection_counts.update(rejected.values())
                targets.update((ids_by_name[name], version) for version in values if version not in rejected)
            edges, outcomes, source_outcomes = set(), [], []
            excluded_kinds = Counter({"peer_dependencies": 0, "optional_dependencies": 0})
            for key, version_row in sorted(eligible.items()):
                source_id, source_version = key
                source_requirements = requirements.get(key)
                declared = None if source_requirements is None else source_requirements["dependencies"]
                resolved = 0
                for kind in excluded_kinds:
                    excluded_kinds[kind] += len((source_requirements or {}).get(kind) or [])
                for index, declaration in enumerate(declared or []):
                    item = declaration or {}
                    name, requirement = item.get("name"), item.get("requirement")
                    reply = _resolve(node, name, requirement, candidates, ids_by_name)
                    target_id = None
                    if reply["status"] == "RESOLVED":
                        target_id = ids_by_name.get(name)
                        if (target_id, reply["target_version"]) not in targets:
                            raise ValueError("Resolved target absent from eligible stable population")
                        edges.add((source_id, source_version, target_id, reply["target_version"]))
                        resolved += 1
                    outcomes.append({"source_package_id": source_id, "source_version": source_version,
                                     "kind": "dependencies", "declaration_index": index,
                                     "declared_name": name, "requirement": requirement,
                                     "normalized_range": reply["normalized_range"], "status": reply["status"],
                                     "target_package_id": target_id, "target_version": reply["target_version"]})
                total = len(declared or [])
                status = _source_status(source_requirements is not None, declared,
                                        version_row["dependency_error"], total, resolved)
                source_outcomes.append({"source_package_id": source_id, "source_version": source_version,
                                        "status": status, "declaration_count": total,
                                        "resolved_count": resolved, "unresolved_count": total - resolved})
            by_target = Counter((edge[2], edge[3]) for edge in edges)
            counts = [{"package_id": pid, "version": version, "dependents_count": by_target[(pid, version)]}
                      for pid, version in sorted(targets)]
            source_statuses = Counter(row["status"] for row in source_outcomes)
            declaration_statuses = Counter(row["status"] for row in outcomes)
            resolved = declaration_statuses["RESOLVED"]
            unresolved = len(outcomes) - resolved
            complete = unresolved == 0 and not any(source_statuses[status] for status in SOURCE_GAPS)
            quality = {"source_versions": len(eligible), "target_versions": len(targets),
                       "selected_declarations": len(outcomes), "resolved_declarations": resolved,
                       "unresolved_declarations": unresolved, "distinct_edges": len(edges),
                       "duplicate_resolved_declarations": resolved - len(edges),
                       "resolution_status": "COMPLETE" if complete else "PARTIAL",
                       "source_status_counts": dict(sorted(source_statuses.items())),
                       "declaration_status_counts": dict(sorted(declaration_statuses.items())),
                       "excluded_kind_declarations": dict(excluded_kinds),
                       "source_null_publication_excluded": sum(v["published"] is None for v in versions.values()),
                       "source_future_excluded": sum(v["published"] is not None and v["published"] > stamp
                                                     for v in versions.values()),
                       "target_rejections": dict(sorted(rejection_counts.items()))}
            if (sum(row["dependents_count"] for row in counts) != len(edges)
                    or sum(row["resolved_count"] for row in source_outcomes) != resolved
                    or sum(row["declaration_count"] for row in source_outcomes) != len(outcomes)
                    or sum(source_statuses.values()) != len(eligible)
                    or sum(declaration_statuses.values()) != resolved + unresolved
                    or len(edges) > resolved):
                raise ValueError("Reference counts or quality failed conservation")
            snapshots.append({"snapshot_at": day,
                              "snapshot_timestamp": stamp.isoformat(timespec="microseconds").replace("+00:00", "Z"),
                              "counts": counts, "declaration_outcomes": outcomes,
                              "source_outcomes": source_outcomes, "quality": quality})
    return {"scope": "SMALL_REFERENCE_ONLY", "method": "PER_SNAPSHOT_FULL_RECOMPUTATION",
            "calculation_mode": "HISTORICAL_RECONSTRUCTION_FROM_FIXED_INPUT",
            "ready_for_load": False, "input_sha256": sha256(fixture),
            "observed_snapshot_timestamp": fixture["observed_snapshot_timestamp"],
            "runtime": metadata, "snapshots": snapshots}


def save_reference(fixture_path: Path, output: Path) -> dict:
    fixture_path, output = Path(fixture_path).resolve(), Path(output).resolve()
    if fixture_path.stat().st_size > MAX_FIXTURE_BYTES:
        raise ValueError("Reference fixture file exceeds small-data limit")
    body = fixture_path.read_bytes()
    fixture = json.loads(body)
    _validate(fixture)
    output.mkdir(parents=True, exist_ok=False)
    code_paths = (Path(__file__), *(Path(__file__).parents[1] / name for name in (
        "requirements_resolution/semver_worker.cjs", "requirements_resolution/bridge.py",
        "requirements_resolution/input.py", "requirements_resolution/policy.py", "snapshot/policy.py")))
    code_hashes = {str(path.resolve()): file_sha256(path) for path in code_paths}
    started = time.monotonic()
    result = compute_reference(fixture, log_path=output / "node.log")
    if fixture_path.read_bytes() != body:
        raise ValueError("Reference fixture changed during calculation")
    if any(file_sha256(path) != checksum for path, checksum in code_hashes.items()):
        raise ValueError("Reference calculation code changed during execution")
    result_path = output / "reference_result.json"
    result_path.write_bytes(canonical_bytes(result))
    receipt = {"scope": "SMALL_REFERENCE_ONLY", "ready_for_load": False,
               "fixture_path": str(fixture_path), "fixture_sha256": file_sha256(fixture_path),
               "result_path": str(result_path), "result_sha256": file_sha256(result_path),
               "snapshot_count": len(result["snapshots"]), "elapsed_seconds": time.monotonic() - started,
               "code_sha256": code_hashes, "python_version": sys.version}
    (output / "reference_manifest.json").write_bytes(canonical_bytes(receipt))
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(save_reference(args.fixture, args.output), ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
