"""Contract tests for the bounded date-aware H3 semver worker."""
from pipeline.preprocessing.common.paths import REPO_ROOT
import tempfile
import unittest
from pathlib import Path

from pipeline.preprocessing.requirements_resolution.bridge import NodeSession, discover_runtime


class HistoricalSemverWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime = discover_runtime()

    def request(self, payload):
        with tempfile.TemporaryDirectory(prefix="historical-semver-") as directory:
            with NodeSession(self.runtime, Path(directory) / "node.log",
                             worker=(REPO_ROOT / 'pipeline/preprocessing/version_dependents/historical_semver_worker.cjs')) as node:
                return node.request(payload)

    def test_intervals_cover_changes_and_tie_policy(self):
        result = self.request({"op": "package", "name": "dep", "known_package": True,
            "snapshot_count": 3, "candidates": [
                {"version": "1.0.0", "birth_index": 0}, {"version": "1.2.0", "birth_index": 1},
                {"version": "1.2.0+z", "birth_index": 1}, {"version": "1.2.0+aa", "birth_index": 1}],
            "requirements": ["^1", "~1.2"]})
        self.assertEqual(result["accepted"], [
            {"version": "1.0.0", "birth_index": 0}, {"version": "1.2.0", "birth_index": 1},
            {"version": "1.2.0+z", "birth_index": 1}, {"version": "1.2.0+aa", "birth_index": 1}])
        self.assertEqual(result["lookups"][0]["intervals"], [
            {"start_index": 0, "end_index": 1, "status": "RESOLVED", "normalized_range": ">=1.0.0 <2.0.0-0", "target_version": "1.0.0"},
            {"start_index": 1, "end_index": 3, "status": "RESOLVED", "normalized_range": ">=1.0.0 <2.0.0-0", "target_version": "1.2.0"}])
        self.assertEqual(result["lookups"][1]["intervals"][0]["status"], "NO_SATISFYING_VERSION")
        self.assertEqual(result["lookups"][1]["intervals"][1]["target_version"], "1.2.0")

    def test_statuses_and_candidate_rejections(self):
        result = self.request({"op": "package", "name": "dep", "known_package": True,
            "snapshot_count": 3, "candidates": [
                {"version": "1.0.0-beta.1", "birth_index": 0}, {"version": "garbage", "birth_index": 0},
                {"version": "2.0.0", "birth_index": 2}],
            "requirements": ["^1", "^3", "workspace:*", None]})
        self.assertEqual([item["status"] for item in result["lookups"][0]["intervals"]], ["NO_ELIGIBLE_TARGET", "NO_SATISFYING_VERSION"])
        self.assertEqual(result["lookups"][1]["intervals"][0]["status"], "NO_ELIGIBLE_TARGET")
        self.assertEqual(result["lookups"][1]["intervals"][1]["status"], "NO_SATISFYING_VERSION")
        self.assertEqual(result["lookups"][2]["intervals"][0]["status"], "INVALID_SPEC")
        self.assertEqual(result["lookups"][3]["intervals"][0]["status"], "INVALID_SPEC")
        self.assertEqual({row["reason"] for row in result["rejected"]}, {"PRERELEASE_TARGET", "INVALID_TARGET_SEMVER"})

    def test_alias_unknown_name_and_bounds(self):
        result = self.request({"op": "package", "name": "dep", "known_package": False,
            "snapshot_count": 1, "candidates": [],
            "requirements": ["^1", "npm:dep@^1", "*"]})
        self.assertEqual([item["intervals"][0]["status"] for item in result["lookups"]], ["UNMAPPED_TARGET_PACKAGE", "UNSUPPORTED_ALIAS", "UNMAPPED_TARGET_PACKAGE"])
        with self.assertRaisesRegex(RuntimeError, "Unmapped package"):
            self.request({"op": "package", "name": "ghost", "known_package": False,
                          "snapshot_count": 1, "candidates": [{"version": "1.0.0", "birth_index": 0}],
                          "requirements": ["^1"]})
        with self.assertRaisesRegex(RuntimeError, "snapshot_count"):
            self.request({"op": "package", "name": "dep", "known_package": True,
                "snapshot_count": 0, "candidates": [], "requirements": []})

    def test_new_candidates_are_tested_once_per_range_not_per_date(self):
        payload = {"op": "package", "name": "dep", "known_package": True,
                   "snapshot_count": 32, "candidates": [{"version": "1.0.0+z", "birth_index": 0},
                       {"version": "1.0.0+aa", "birth_index": 10},
                       {"version": "0.9.0", "birth_index": 20}],
                   "requirements": ["^1", "^2"]}
        result = self.request(payload)
        self.assertEqual(result["metrics"]["candidate_checks"], 6)
        self.assertEqual([r["target_version"] for r in result["lookups"][0]["intervals"]],
                         ["1.0.0+z", "1.0.0+aa"])
        duplicate = {**payload, "candidates": payload["candidates"] + [payload["candidates"][0]]}
        self.assertEqual(self.request(duplicate)["lookups"], result["lookups"])
        with self.assertRaisesRegex(RuntimeError, "conflicting birth_index"):
            self.request({**payload, "candidates": payload["candidates"] + [
                {"version": "1.0.0+z", "birth_index": 1}]})

    def test_input_permutation_does_not_change_semantic_results(self):
        base = {"op": "package", "name": "dep", "known_package": True, "snapshot_count": 2,
                "candidates": [{"version": "1.0.0", "birth_index": 0}, {"version": "1.1.0", "birth_index": 1}],
                "requirements": ["^1", "~1"]}
        permuted = {**base, "candidates": list(reversed(base["candidates"])), "requirements": list(reversed(base["requirements"]))}
        first, second = self.request(base), self.request(permuted)
        self.assertEqual(first["lookups"][0]["intervals"], second["lookups"][1]["intervals"])
        self.assertEqual(first["lookups"][1]["intervals"], second["lookups"][0]["intervals"])


if __name__ == "__main__":
    unittest.main()
