"""Bounded contract tests for the stored CPU/GPU suite input loader."""
from pipeline.preprocessing.common.paths import REPO_ROOT
from pathlib import Path
import json
import unittest

from pipeline.preprocessing.requirements_resolution.input import file_sha256
from pipeline.preprocessing.experiments.dependents.historical_gpu_suite_input import load_suite, reverify_protected_files
from pipeline.preprocessing.version_dependents.historical_production import contract, WEIGHTED_ALGORITHM


ROOT = REPO_ROOT
PREPARED = ROOT / "data" / "vd-pilot-a" / "32" / "input"
RUN = ROOT / "data" / "vd-pilot-a" / "32" / "run"


@unittest.skipUnless((PREPARED / "input_manifest.json").is_file()
                     and (RUN / "run_manifest.json").is_file(),
                     "stored 32-package production fixture is unavailable")
class HistoricalGpuSuiteInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stored = json.loads((RUN / "run_plan.json").read_bytes())
        if stored["generation_contract"] != contract(WEIGHTED_ALGORITHM):
            raise unittest.SkipTest("stored sample requires its original generation code; synthetic tests remain active")
        cls.suite = load_suite(
            prepared_dir=PREPARED,
            oracle_run_dir=RUN,
            oracle_manifest_sha256=file_sha256(RUN / "run_manifest.json"),
        )

    def test_loads_all_selected_packages_and_preserves_counts(self):
        self.assertEqual(len(self.suite["packages"]), 32)
        self.assertEqual(len(self.suite["calendar"]), 229)
        self.assertEqual(self.suite["provenance"]["contract"], "weighted-events-v2")
        self.assertEqual(self.suite["provenance"]["source"], "stored production lookup intervals")
        self.assertEqual(self.suite["input_rows"]["lookups"],
                         sum(len(item["lookups"]) for item in self.suite["packages"]))
        self.assertGreater(self.suite["input_rows"]["oracle_intervals"], 0)

    def test_protected_files_can_be_reverified(self):
        reverify_protected_files(self.suite)

    def test_wrong_manifest_digest_is_rejected(self):
        with self.assertRaises(ValueError):
            load_suite(prepared_dir=PREPARED, oracle_run_dir=RUN,
                       oracle_manifest_sha256="0" * 64)


if __name__ == "__main__":
    unittest.main()
