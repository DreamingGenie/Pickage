import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pipeline.postgresql import load


class LoadTests(unittest.TestCase):
    def test_missing_input_leaves_failure_report_without_database(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(load, "select_run", side_effect=ValueError("missing completion")):
                with self.assertRaisesRegex(ValueError, "missing completion"):
                    load.run(None, "2026-08-31", "source", "test-load", Path(temporary), None, verify_only=True)
            reports = list(Path(temporary).glob("test-load/*/execution_report.json"))
            self.assertEqual(len(reports), 1)
            report = json.loads(reports[0].read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "FAILED")
            self.assertEqual(report["phase"], "SELECT_INPUT")
            self.assertEqual(report["error_type"], "ValueError")

    def test_verify_only_does_not_connect_or_export(self):
        metadata = {"counts": {"package": 1, "version": 2}}
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(load, "select_run", return_value=metadata), \
                    patch.object(load, "prepare", return_value={"counts": metadata["counts"], "validation": {"checks": "PASSED"}}) as prepare, \
                    patch.object(load, "PgLoader") as database:
                result = load.run(None, "2026-08-31", "source", "test-verify", Path(temporary), None, verify_only=True)
            database.assert_not_called()
            self.assertFalse(prepare.call_args.kwargs["export_csv"])
            self.assertEqual(result["status"], "VERIFIED")

    def test_execution_id_cannot_escape_work_directory(self):
        with self.assertRaisesRegex(ValueError, "execution ID"):
            load.run(None, "2026-08-31", "source", "../elsewhere", Path("."), None, verify_only=True)


if __name__ == "__main__":
    unittest.main()
