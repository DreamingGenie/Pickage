import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from .real_db import query
from .real_report import assess_sample_binding, assess_prior_attempts


class RealReportTests(unittest.TestCase):
    def test_prior_success_requires_matching_counts_and_earlier_time(self):
        metadata = {"attempts": [{"status": "FAILED", "execution_id": "e", "attempt_id": "failed", "created_at": "2026-01-02T00:00:00Z"}],
                    "executions": [{"execution_id": "e", "expected_counts": {"package_snapshot": 2}}]}
        prior = [{"execution_id": "e", "attempt_id": "good", "status": "PUBLISHED", "completed_at": "2026-01-01T00:00:00Z", "actual_counts": {"package_snapshot": 2}}]
        self.assertEqual(assess_prior_attempts(metadata, prior)["status"], "PASS")
        self.assertEqual(assess_prior_attempts(metadata, [])["status"], "NOT_RUN")
        prior[0]["actual_counts"]["package_snapshot"] = 1
        self.assertEqual(assess_prior_attempts(metadata, prior)["status"], "NOT_RUN")
        prior[0]["actual_counts"]["package_snapshot"] = 2
        prior[0]["completed_at"] = "2026-01-03T00:00:00Z"
        self.assertEqual(assess_prior_attempts(metadata, prior)["status"], "NOT_RUN")

    def test_sample_file_pin_mismatch_fails(self):
        sample = {"status": "PASS", "mismatches": [], "dates": ["2026-01-01"], "samples": [{"package_id": 1}],
                  "files": [{"date": "2026-01-01", "bytes": 10, "sha256": "original", "read_rows": 2}]}
        metadata = {"executions": [{"dataset": "package-snapshot", "status": "PUBLISHED", "snapshot_at": "2026-01-01",
                                     "input_metadata": {"files": [{"role": "package_snapshot", "bytes": 10, "sha256": "original", "row_count": 2}]}}]}
        self.assertEqual(assess_sample_binding(sample, metadata)["status"], "PASS")
        sample["files"][0]["sha256"] = "tampered"
        self.assertEqual(assess_sample_binding(sample, metadata)["status"], "FAIL")

    @patch("pipeline.integrity_validation.real_db.subprocess.run")
    def test_reader_sets_session_and_transaction_readonly(self, run):
        run.return_value = SimpleNamespace(returncode=0, stdout='{"ok":true}', stderr="")
        self.assertEqual(query("fixture", "fixture", "SELECT true", timeout=3)[0], {"ok": True})
        command = run.call_args.args[0]
        self.assertIn("PGOPTIONS=-c default_transaction_read_only=on -c application_name=integrity09-readonly", command)
        sql = run.call_args.kwargs["input"]
        self.assertIn("REPEATABLE READ READ ONLY", sql)
        self.assertIn("statement_timeout='3s'", sql)
        self.assertTrue(sql.endswith("ROLLBACK;\n"))
        self.assertEqual(run.call_args.kwargs["timeout"], 18)

    @patch("pipeline.integrity_validation.real_db.subprocess.run")
    def test_error_or_untrusted_identifier_never_becomes_success(self, run):
        with self.assertRaises(ValueError):
            query("unsafe; command", "db", "SELECT 1")
        run.assert_not_called()
        run.return_value = SimpleNamespace(returncode=1, stderr="readonly violation", stdout="")
        with self.assertRaisesRegex(RuntimeError, "readonly violation"):
            query("fixture", "db", "SELECT 1")


if __name__ == "__main__":
    unittest.main()
