"""Small, independently hand-calculated reference cases for dependency counts."""
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import unittest

from pipeline.preprocessing.requirements_resolution.bridge import discover_runtime
from pipeline.preprocessing.version_dependents.historical_reference import compute_reference


S0 = "2026-08-30T21:00:00.000000Z"
T = "2026-08-31T21:01:10.517131Z"
FUTURE = "2026-08-31T21:01:10.517132Z"
_MISSING = object()


def _req(name, requirement):
    return {"name": name, "requirement": requirement}


def reference_fixture():
    packages = [
        (1, "app"), (2, "dep"), (3, "chain"), (4, "future"),
        (5, "pre"), (6, "prestable"), (7, "tie"), (8, "err"),
        (9, "unknownerr"), (10, "missing"), (11, "nullsrc"),
    ]
    versions = []
    requirements = []

    def add(package_id, version, published_at, *, dependency_error=False, dependencies=_MISSING, has_requirements=True):
        versions.append({"package_id": package_id, "version": version,
                         "published_at": published_at, "dependency_error": dependency_error})
        if has_requirements:
            requirements.append({"package_id": package_id, "version": version,
                                 "dependencies": [] if dependencies is _MISSING else dependencies,
                                 "peer_dependencies": [], "optional_dependencies": []})

    add(1, "1.0.0", S0, dependencies=[
        _req("dep", "1.0.0"), _req("dep", "^1.0.0"), _req("dep", "~1.0.0"),
        _req("dep", ">=1.0.0 <2.0.0"), _req("dep", "^2.0.0 || ^1.0.0"),
        _req("dep", "1.x"), _req("dep", "1.0.0 - 1.5.0"), _req("dep", "*"),
        _req("future", "*"), _req("pre", "*"),
        _req("prestable", "2.0.0-beta.1"), _req("dep", "npm:dep@^1.0.0"),
        _req("dep", "workspace:*") , _req("unknown", "*"),
        _req("chain", "*"), _req("app", "*"), _req("tie", "1.0.0"),
    ])
    add(1, "1.1.0", T)
    add(1, "1.2.0", FUTURE)
    add(1, "1.3.0", None)
    for version in ("1.0.0", "1.5.0", "2.0.0", "2.0.0-beta.1"):
        add(2, version, S0)
    add(3, "1.0.0", S0)
    add(4, "1.0.0", FUTURE)
    add(5, "1.0.0-beta.1", S0)
    add(6, "1.0.0", S0)
    add(6, "2.0.0-beta.1", S0)
    add(7, "1.0.0+z", S0)
    add(7, "1.0.0+aa", S0)
    add(8, "1.0.0", S0, dependency_error=True)
    add(9, "1.0.0", S0, dependency_error=None)
    add(10, "1.0.0", S0, has_requirements=False)
    add(11, "1.0.0", S0, dependencies=None)
    return {
        "observed_snapshot_timestamp": T,
        "calendar": [
            {"snapshot_at": "2026-08-30", "snapshot_timestamp": S0},
            {"snapshot_at": "2026-08-31", "snapshot_timestamp": T},
        ],
        "packages": [{"package_id": package_id, "name": name} for package_id, name in packages],
        "versions": versions,
        "requirements": requirements,
    }


def tiny_fixture(packages, versions, requirements, timestamps):
    return {"observed_snapshot_timestamp": timestamps[-1],
            "calendar": [{"snapshot_at": stamp[:10], "snapshot_timestamp": stamp}
                          for stamp in timestamps],
            "packages": [{"package_id": pid, "name": name} for pid, name in packages],
            "versions": versions, "requirements": requirements}


def v(package_id, version, published_at, dependency_error=False):
    return {"package_id": package_id, "version": version,
            "published_at": published_at, "dependency_error": dependency_error}


def r(package_id, version, dependencies):
    return {"package_id": package_id, "version": version, "dependencies": dependencies,
            "peer_dependencies": [], "optional_dependencies": []}


class HistoricalReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime = discover_runtime()

    def compute(self, fixture=None):
        fixture = fixture or reference_fixture()
        temp = tempfile.TemporaryDirectory(prefix="historical-reference-")
        self.addCleanup(temp.cleanup)
        return compute_reference(fixture, runtime=self.runtime, log_path=Path(temp.name) / "node.log")

    @staticmethod
    def outcome(result, requirement, declared_name=None):
        return next(row for row in result["snapshots"][-1]["declaration_outcomes"]
                    if row["requirement"] == requirement
                    and (declared_name is None or row["declared_name"] == declared_name))

    def test_all_supported_range_forms_and_resolution_statuses(self):
        result = self.compute()
        expected = [
            ("dep", "1.0.0", "RESOLVED", "1.0.0"), ("dep", "^1.0.0", "RESOLVED", "1.5.0"),
            ("dep", "~1.0.0", "RESOLVED", "1.0.0"), ("dep", ">=1.0.0 <2.0.0", "RESOLVED", "1.5.0"),
            ("dep", "^2.0.0 || ^1.0.0", "RESOLVED", "2.0.0"), ("dep", "1.x", "RESOLVED", "1.5.0"),
            ("dep", "1.0.0 - 1.5.0", "RESOLVED", "1.5.0"), ("dep", "*", "RESOLVED", "2.0.0"),
            ("future", "*", "NO_ELIGIBLE_TARGET", None), ("pre", "*", "NO_ELIGIBLE_TARGET", None),
            ("prestable", "2.0.0-beta.1", "NO_SATISFYING_VERSION", None),
            ("dep", "npm:dep@^1.0.0", "UNSUPPORTED_ALIAS", None),
            ("dep", "workspace:*", "INVALID_SPEC", None), ("unknown", "*", "UNMAPPED_TARGET_PACKAGE", None),
            ("chain", "*", "RESOLVED", "1.0.0"), ("app", "*", "RESOLVED", "1.1.0"),
        ]
        for name, requirement, status, target in expected:
            row = self.outcome(result, requirement, name)
            self.assertEqual(row["status"], status, requirement)
            self.assertEqual(row["target_version"], target, requirement)
        tie = self.outcome(result, "1.0.0", "tie")
        self.assertEqual(tie["target_package_id"], 7)

    def test_snapshot_population_and_direct_edge_counts(self):
        result = self.compute()
        self.assertFalse(result["ready_for_load"])
        self.assertEqual(len(result["snapshots"]), 2)
        first, latest = result["snapshots"]
        self.assertEqual(first["snapshot_at"], "2026-08-30")
        self.assertEqual(latest["snapshot_at"], "2026-08-31")
        self.assertEqual(latest["quality"]["selected_declarations"], 17)
        self.assertEqual(latest["quality"]["resolved_declarations"], 11)
        self.assertEqual(latest["quality"]["unresolved_declarations"], 6)
        self.assertEqual(latest["quality"]["distinct_edges"], 6)
        self.assertEqual(latest["quality"]["duplicate_resolved_declarations"], 5)
        self.assertEqual(sum(row["dependents_count"] for row in latest["counts"]), 6)
        self.assertIn({"package_id": 1, "version": "1.1.0", "dependents_count": 1}, latest["counts"])
        chain_count = next(row["dependents_count"] for row in latest["counts"]
                           if row["package_id"] == 3 and row["version"] == "1.0.0")
        self.assertEqual(chain_count, 1)

    def test_source_outcome_precedence_and_error_edges_are_preserved(self):
        result = self.compute()
        latest = result["snapshots"][-1]
        statuses = {(row["source_package_id"], row["source_version"]): row["status"]
                    for row in latest["source_outcomes"]}
        self.assertEqual(statuses[(8, "1.0.0")], "DEPENDENCY_EXTRACTION_ERROR")
        self.assertEqual(statuses[(9, "1.0.0")], "DEPENDENCY_EXTRACTION_UNKNOWN")
        self.assertEqual(statuses[(10, "1.0.0")], "MISSING_REQUIREMENTS")
        self.assertEqual(statuses[(11, "1.0.0")], "NULL_DEPENDENCY_LIST")
        self.assertEqual(latest["quality"]["source_status_counts"]["PARTIAL"], 1)
        self.assertEqual(latest["quality"]["declaration_status_counts"]["RESOLVED"], 11)

    def test_late_higher_lower_and_equal_precedence_winners_are_snapshot_local(self):
        s1, s2, s3 = "2026-08-29T20:00:00.000000Z", "2026-08-30T20:00:00.000000Z", T
        fixture = tiny_fixture([(1, "app"), (2, "dep"), (3, "tie")], [
            v(1, "1.0.0", s1), v(1, "1.1.0", s2), v(1, "1.2.0", s3),
            v(2, "1.0.0", s1), v(2, "1.2.0", s2), v(2, "1.1.0", s3),
            v(3, "1.0.0+z", s2), v(3, "1.0.0+aa", s3)], [
            r(1, "1.0.0", [_req("dep", "^1.0.0"), _req("tie", "1.0.0")]),
            r(1, "1.1.0", [_req("dep", "^1.0.0")]),
            r(1, "1.2.0", [_req("dep", "=1.0.0")]),
        ], [s1, s2, s3])
        result = self.compute(fixture)
        winners = []
        for snapshot in result["snapshots"]:
            row = next(item for item in snapshot["declaration_outcomes"]
                       if item["declared_name"] == "dep")
            winners.append((row["status"], row["target_version"]))
        self.assertEqual(winners, [("RESOLVED", "1.0.0"), ("RESOLVED", "1.2.0"), ("RESOLVED", "1.2.0")])
        tie_rows = [next(item for item in snapshot["declaration_outcomes"]
                         if item["declared_name"] == "tie")
                    for snapshot in result["snapshots"]]
        self.assertEqual([(row["status"], row["target_version"]) for row in tie_rows],
                         [("NO_ELIGIBLE_TARGET", None), ("RESOLVED", "1.0.0+z"),
                          ("RESOLVED", "1.0.0+aa")])

    def test_two_source_versions_and_same_source_duplicate_share_one_target(self):
        s1, s2 = "2026-08-30T20:00:00.000000Z", T
        fixture = tiny_fixture([(1, "a"), (2, "dep")], [
            v(1, "1.0.0", s1), v(1, "2.0.0", s2), v(2, "1.0.0", s1)], [
            r(1, "1.0.0", [_req("dep", "1.0.0"), _req("dep", "1.0.0")]),
            r(1, "2.0.0", [_req("dep", "1.0.0")]), r(2, "1.0.0", []),
        ], [s1, s2])
        latest = self.compute(fixture)["snapshots"][-1]
        count = next(row for row in latest["counts"] if row["package_id"] == 2)
        self.assertEqual(count["dependents_count"], 2)
        self.assertEqual(latest["quality"]["resolved_declarations"], 3)
        self.assertEqual(latest["quality"]["distinct_edges"], 2)
        self.assertEqual(latest["quality"]["duplicate_resolved_declarations"], 1)

    def test_direct_chain_and_self_edge_do_not_count_transitive_dependents(self):
        stamp = T
        fixture = tiny_fixture([(1, "a"), (2, "b"), (3, "c")], [
            v(1, "1.0.0", stamp), v(2, "1.0.0", stamp), v(3, "1.0.0", stamp)], [
            r(1, "1.0.0", [_req("b", "*") , _req("a", "*")]),
            r(2, "1.0.0", [_req("c", "*")]), r(3, "1.0.0", []),
        ], [stamp])
        latest = self.compute(fixture)["snapshots"][0]
        counts = {(row["package_id"], row["version"]): row["dependents_count"] for row in latest["counts"]}
        self.assertEqual(counts, {(1, "1.0.0"): 1, (2, "1.0.0"): 1, (3, "1.0.0"): 1})

    def test_known_future_target_moves_no_eligible_to_no_satisfying_to_resolved(self):
        s1, s2, s3 = "2026-08-29T20:00:00.000000Z", "2026-08-30T20:00:00.000000Z", T
        fixture = tiny_fixture([(1, "a"), (2, "future")], [
            v(1, "1.0.0", s1), v(2, "1.0.0", s2), v(2, "2.0.0", s3)],
            [r(1, "1.0.0", [_req("future", "^2.0.0")])], [s1, s2, s3])
        statuses = [snapshot["declaration_outcomes"][0]["status"]
                    for snapshot in self.compute(fixture)["snapshots"]]
        self.assertEqual(statuses, ["NO_ELIGIBLE_TARGET", "NO_SATISFYING_VERSION", "RESOLVED"])

    def test_error_unknown_missing_and_null_sources_keep_successful_edges(self):
        stamp = T
        fixture = tiny_fixture([(1, "error"), (2, "unknown"), (3, "missing"), (4, "null"), (5, "dep")], [
            v(1, "1.0.0", stamp, True), v(2, "1.0.0", stamp, None),
            v(3, "1.0.0", stamp), v(4, "1.0.0", stamp), v(5, "1.0.0", stamp)], [
            r(1, "1.0.0", [_req("dep", "*")]), r(2, "1.0.0", [_req("dep", "*")]),
            r(4, "1.0.0", None), r(5, "1.0.0", []),
        ], [stamp])
        latest = self.compute(fixture)["snapshots"][0]
        statuses = {(row["source_package_id"], row["source_version"]): row["status"]
                    for row in latest["source_outcomes"]}
        self.assertEqual(statuses[(1, "1.0.0")], "DEPENDENCY_EXTRACTION_ERROR")
        self.assertEqual(statuses[(2, "1.0.0")], "DEPENDENCY_EXTRACTION_UNKNOWN")
        self.assertEqual(statuses[(3, "1.0.0")], "MISSING_REQUIREMENTS")
        self.assertEqual(statuses[(4, "1.0.0")], "NULL_DEPENDENCY_LIST")
        self.assertEqual(latest["quality"]["resolved_declarations"], 2)
        self.assertEqual(next(row for row in latest["counts"] if row["package_id"] == 5)["dependents_count"], 2)


if __name__ == "__main__":
    unittest.main()
