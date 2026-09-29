"""Reference input boundaries and the independently specified example artifact."""
from pipeline.preprocessing.common.paths import REPO_ROOT
import copy
from datetime import date, timedelta
import json
from pathlib import Path
import tempfile
import unittest

from pipeline.preprocessing.requirements_resolution.input import file_sha256
from pipeline.preprocessing.version_dependents.historical_reference import compute_reference, save_reference, MAX_VERSIONS


FIXTURE_PATH = (REPO_ROOT / 'pipeline/preprocessing/version_dependents/fixtures/historical_reference.json')


class ReferenceContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="reference-'한글-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = json.loads(FIXTURE_PATH.read_bytes())
        self.log_index = 0

    def compute(self, fixture=None):
        self.log_index += 1
        return compute_reference(self.fixture if fixture is None else fixture,
                                 log_path=self.root / f"node-{self.log_index}.log")

    def test_demo_exact_counts_and_quality_then_file_receipt(self):
        output = self.root / "example"
        receipt = save_reference(FIXTURE_PATH, output)
        self.assertEqual(receipt["result_sha256"], file_sha256(output / "reference_result.json"))
        result = json.loads((output / "reference_result.json").read_bytes())
        expected = [
            {(1, "1.0.0"): 0, (2, "1.0.0"): 1, (3, "1.0.0"): 2},
            {(1, "1.0.0"): 0, (1, "2.0.0"): 0, (2, "1.0.0"): 0, (2, "1.2.0"): 2, (3, "1.0.0"): 2},
            {(1, "1.0.0"): 0, (1, "2.0.0"): 0, (2, "1.0.0"): 0, (2, "1.1.0"): 0,
             (2, "1.2.0"): 2, (3, "1.0.0"): 2},
        ]
        for snapshot, counts, edge_count in zip(result["snapshots"], expected, (3, 4, 4)):
            self.assertEqual({(row["package_id"], row["version"]): row["dependents_count"]
                              for row in snapshot["counts"]}, counts)
            self.assertEqual(snapshot["quality"]["duplicate_resolved_declarations"], 1)
            self.assertEqual(snapshot["quality"]["distinct_edges"], edge_count)
            self.assertEqual(snapshot["quality"]["resolution_status"], "COMPLETE")
        self.assertFalse(result["ready_for_load"])
        with self.assertRaises(FileExistsError):
            save_reference(FIXTURE_PATH, output)

    def test_input_permutation_does_not_change_snapshots(self):
        baseline = self.compute()
        for key in ("packages", "versions", "requirements"):
            self.fixture[key].reverse()
        self.assertEqual(self.compute()["snapshots"], baseline["snapshots"])

    def test_past_calendar_subset_is_allowed_for_small_comparisons(self):
        baseline = self.compute()
        self.fixture["calendar"] = self.fixture["calendar"][:1]
        result = self.compute()
        self.assertEqual(result["snapshots"], baseline["snapshots"][:1])
        self.assertEqual(result["observed_snapshot_timestamp"], baseline["observed_snapshot_timestamp"])
        self.assertFalse(result["ready_for_load"])

    def test_peer_and_optional_are_counted_as_excluded_only(self):
        self.fixture["requirements"][0]["dependencies"] = []
        self.fixture["requirements"][0]["peer_dependencies"] = [{"name": "dep", "requirement": "*"}]
        self.fixture["requirements"][0]["optional_dependencies"] = [{"name": "dep", "requirement": "*"}]
        first = self.compute()["snapshots"][0]
        self.assertEqual(first["quality"]["excluded_kind_declarations"],
                         {"peer_dependencies": 1, "optional_dependencies": 1})
        self.assertEqual(first["quality"]["distinct_edges"], 1)
        self.assertEqual(first["quality"]["selected_declarations"], 1)

    def test_bad_identity_duplicate_and_unmapped_requirements_rejected(self):
        mutations = [lambda f: f["packages"].append(f["packages"][0]),
                     lambda f: f["versions"].append(f["versions"][0]),
                     lambda f: f["requirements"].append(f["requirements"][0]),
                     lambda f: f["versions"][0].update(package_id=999),
                     lambda f: f["requirements"][0].update(version="not-present"),
                     lambda f: f["versions"][0].update(dependency_error=1),
                     lambda f: f["versions"][0].update(is_release=False)]
        for change in mutations:
            with self.subTest(change=change):
                fixture = copy.deepcopy(self.fixture)
                change(fixture)
                with self.assertRaises(ValueError):
                    self.compute(fixture)

    def test_invalid_calendar_and_naive_publication_rejected(self):
        mutations = [lambda f: f["calendar"].reverse(),
                     lambda f: f["calendar"].append(f["calendar"][-1]),
                     lambda f: f["calendar"][0].update(snapshot_at="2026-08-11"),
                     lambda f: f.update(observed_snapshot_timestamp="2026-08-01T00:00:00Z"),
                     lambda f: f["versions"][0].update(published_at="2026-08-01T00:00:00"),
                     lambda f: f["versions"][0].update(published_at="2026-08-01T00:00:00.0000001Z")]
        for change in mutations:
            with self.subTest(change=change):
                fixture = copy.deepcopy(self.fixture)
                change(fixture)
                with self.assertRaises(ValueError):
                    self.compute(fixture)

    def test_large_fixture_rejected_before_node_or_output(self):
        self.fixture["versions"] = [self.fixture["versions"][0]] * (MAX_VERSIONS + 1)
        path = self.root / "large.json"
        path.write_text(json.dumps(self.fixture), encoding="utf-8")
        output = self.root / "large-result"
        with self.assertRaisesRegex(ValueError, "bounds"):
            save_reference(path, output)
        self.assertFalse(output.exists())

    def test_comparison_work_is_bounded_even_with_allowed_list_sizes(self):
        self.fixture["versions"] = [{"package_id": 1, "version": f"1.0.{i}",
                                      "published_at": "2026-01-01T00:00:00Z", "dependency_error": False}
                                     for i in range(MAX_VERSIONS)]
        self.fixture["requirements"] = [{"package_id": 1, "version": "1.0.0",
                                         "dependencies": [{"name": "app", "requirement": "*"}] * 123}]
        self.fixture["calendar"] = [{"snapshot_at": (date(2026, 1, 1) + timedelta(days=i)).isoformat(),
                                     "snapshot_timestamp": (date(2026, 1, 1) + timedelta(days=i)).isoformat() + "T12:00:00Z"}
                                    for i in range(32)]
        with self.assertRaisesRegex(ValueError, "bounded comparison"):
            self.compute()


if __name__ == "__main__":
    unittest.main()
