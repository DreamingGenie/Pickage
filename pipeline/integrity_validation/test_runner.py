"""Boundary and report tests; only bounded in-memory data is used."""
from copy import deepcopy
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from .__main__ import main
from .queries import CHECKS
from .runner import MAX_BYTES, load_fixture, validate_fixture


FIXTURE = Path(__file__).parent / "fixtures" / "normal.json"


class RunnerTests(unittest.TestCase):
    def fixture(self):
        return load_fixture(FIXTURE)[0]

    def test_missing_and_explicit_null_are_distinct(self):
        missing = self.fixture()
        del missing["tables"]["public.package_snapshot"][0]["downloads"]
        with self.assertRaisesRegex(ValueError, "every column"):
            validate_fixture(missing)
        explicit_null = self.fixture()
        explicit_null["tables"]["public.package_snapshot"][0]["downloads"] = None
        report = validate_fixture(explicit_null)
        self.assertEqual(report["validation_status"], "FAIL")

    def test_boolean_integer_and_overflow_rejected_before_sql(self):
        for value in (True, 2147483648, 1.5, "1"):
            with self.subTest(value=value):
                document = self.fixture()
                document["tables"]["public.package"][0]["package_id"] = value
                with self.assertRaises(ValueError):
                    validate_fixture(document)

    def test_timestamp_precision_and_utc_normalization(self):
        original = self.fixture()
        document = deepcopy(original)
        row = document["tables"]["validation.snapshot_context"][0]
        row["snapshot_timestamp"] = row["snapshot_at"] + "T09:00:00.000001+09:00"
        self.assertEqual(validate_fixture(document)["validation_status"],
                         validate_fixture(original)["validation_status"])
        row["snapshot_timestamp"] = row["snapshot_at"] + "T00:00:00.0000001Z"
        with self.assertRaises(ValueError):
            validate_fixture(document)

    def test_real_run_cannot_be_presented_as_fixture_approval(self):
        document = self.fixture()
        document["kind"] = "PUBLISHED"
        with self.assertRaisesRegex(ValueError, "native runs"):
            validate_fixture(document)
        document = self.fixture()
        document["tables"]["validation.snapshot_context"] = []
        with self.assertRaisesRegex(ValueError, "snapshot context"):
            validate_fixture(document)

    def test_partial_source_is_retained_even_with_zero_unresolved_declarations(self):
        document = self.fixture()
        row = document["tables"]["validation.source_quality"][0]
        row["resolution_status"], row["unresolved_count"] = "PARTIAL", 0
        report = validate_fixture(document)
        self.assertEqual(report["validation_status"], "PASS")
        self.assertEqual(report["quality"][0]["resolution_status"], "PARTIAL")
        self.assertFalse(report["ready_for_publication"])

    def test_incomplete_calculation_cannot_validate_even_genuine_zero(self):
        document = self.fixture()
        document["tables"]["validation.source_quality"][-1]["calculation_status"] = "PARTIAL"
        report = validate_fixture(document)
        self.assertEqual(report["validation_status"], "FAIL")
        self.assertTrue(any(x["id"] == "source_quality_zero_contract" and x["status"] == "FAIL"
                            for x in report["checks"]))

    def test_duplicate_json_keys_and_oversized_file_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "fixture.json"
            path.write_text('{"kind":"native","kind":"synthetic_fixture"}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
                load_fixture(path)
            path.write_bytes(b" " * (MAX_BYTES + 1))
            with self.assertRaisesRegex(ValueError, "2 MiB"):
                load_fixture(path)

    def test_catalog_error_is_reported_and_never_passes(self):
        invalid = {"id": "broken", "description": "의도한 SQL 실패", "sql": "SELECT absent FROM public.package"}
        with patch("pipeline.integrity_validation.queries.CHECKS", (*CHECKS, invalid)):
            report = validate_fixture(self.fixture())
        self.assertEqual(report["validation_status"], "ERROR")
        self.assertEqual(report["checks"][-1]["status"], "ERROR")
        self.assertFalse(report["ready_for_publication"])

    def test_cli_reports_hashes_and_preserves_completed_output_on_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "report"
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = main(["--fixture", str(FIXTURE), "--output", str(output)])
            self.assertEqual(code, 0)
            report = json.loads((output / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["fixture_file_sha256"], hashlib.sha256(FIXTURE.read_bytes()).hexdigest())
            self.assertEqual(len(report["validator_sha256"]), 64)
            self.assertFalse(report["task_09_complete"])
            self.assertTrue(all(x["status"] == "NOT_RUN" for x in report["deferred_checks"]))
            before = {p.name: p.read_bytes() for p in output.iterdir()}
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                retry = main(["--fixture", str(FIXTURE), "--output", str(output)])
            self.assertEqual(retry, 2)
            self.assertEqual(before, {p.name: p.read_bytes() for p in output.iterdir()})
            sql = (output / "integrity_checks.sql").read_text(encoding="utf-8")
            self.assertIn("READ ONLY", sql)
            self.assertIn("ON_ERROR_STOP on", sql)
            self.assertTrue(sql.endswith("ROLLBACK;\n"))

    def test_failed_fixture_has_nonzero_exit_and_a_reviewable_report(self):
        document = self.fixture()
        document["tables"]["public.package_version_snapshot"][0]["dependents_count"] = -1
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "bad.json"
            source.write_text(json.dumps(document), encoding="utf-8")
            output = Path(temp) / "result"
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = main(["--fixture", str(source), "--output", str(output)])
            self.assertEqual(code, 1)
            report = json.loads((output / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["validation_status"], "FAIL")
            self.assertFalse(report["ready_for_publication"])


if __name__ == "__main__":
    unittest.main()
