"""Tests for frozen snapshot candidate input validation."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from .build import json_bytes, snapshot_sql
from .input import read_candidate
from .policy import POLICY_VERSION, build_calendar, policy_document, policy_sha256


class CandidateInputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "projects"
        self.root.mkdir()
        self.inventory = {
            "source_kind": "local-projects",
            "validation": "PARQUET_FOOTER_TIMESTAMP_CHECKED",
            "timestamps": ["2026-08-24T21:00:00.000000Z", "2026-08-31T21:00:00.000000Z"],
            "snapshots": [], "file_count": 0, "total_rows": 0,
            "first_snapshot": "2026-08-24", "last_snapshot": "2026-08-31",
        }
        self.calendar = build_calendar(self.inventory["timestamps"])
        self.path = Path(self.tmp.name) / "snapshot-candidate.json"
        inventory_bytes = json_bytes(self.inventory)
        sql_bytes = snapshot_sql(self.calendar).encode("utf-8")
        (self.path.parent / "projects-inventory.json").write_bytes(inventory_bytes)
        (self.path.parent / "snapshot-dates.sql").write_bytes(sql_bytes)
        self.candidate = {
            "format_version": 1, "dataset": "snapshot-reference", "status": "LOCAL_VALIDATED",
            "db_published": False, "service_ready": False, "policy_version": POLICY_VERSION,
            "policy_sha256": policy_sha256(), "policy": policy_document(),
            "source": {"kind": "local-projects", "root": str(self.root.resolve()),
                       "inventory_file": "projects-inventory.json",
                       "inventory_sha256": hashlib.sha256(inventory_bytes).hexdigest()},
            "snapshot_count": 2, "first_snapshot_at": "2026-08-24", "last_snapshot_at": "2026-08-31",
            "calendar": self.calendar,
            "files": [{"path": "projects-inventory.json", "sha256": hashlib.sha256(inventory_bytes).hexdigest()},
                      {"path": "snapshot-dates.sql", "sha256": hashlib.sha256(sql_bytes).hexdigest()}],
        }
        self.path.write_bytes(json_bytes(self.candidate))
        self.addCleanup(self.tmp.cleanup)

    def test_reads_and_revalidates_complete_candidate(self):
        with patch("pipeline.snapshot.input.inspect_projects", return_value=self.inventory), \
                patch.object(Path, 'read_text', side_effect=AssertionError('parse the bytes already hashed')):
            result = read_candidate(self.path)
        self.assertEqual(result["candidate"], self.candidate)
        self.assertEqual(result["candidate_sha256"], hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(result["candidate_path"], str(self.path.resolve()))
        self.assertEqual(result["inventory"], self.inventory)
        self.assertEqual(result["inventory_sha256"], self.candidate["source"]["inventory_sha256"])

    def assert_invalid(self, mutate):
        value = json.loads(json_bytes(self.candidate))
        mutate(value)
        self.path.write_bytes(json_bytes(value))
        with patch("pipeline.snapshot.input.inspect_projects", return_value=self.inventory), self.assertRaisesRegex(ValueError, "invalid snapshot candidate"):
            read_candidate(self.path)

    def test_rejects_policy_hash_calendar_count_and_files_tampering(self):
        for mutate in (
            lambda c: c.__setitem__("policy_sha256", "0" * 64),
            lambda c: c["policy"].update({"tampered": True}),
            lambda c: c["calendar"].pop(),
            lambda c: c.__setitem__("snapshot_count", 99),
            lambda c: c.__setitem__("files", c["files"] + [c["files"][0]]),
            lambda c: c["files"][0].update(path=[]),
            lambda c: c["files"][0].update(sha256='0'*64),
            lambda c: c.__setitem__('format_version', True),
        ):
            with self.subTest(mutate=mutate):
                self.assert_invalid(mutate)

    def test_rejects_path_traversal_and_changed_source(self):
        def traversal(candidate):
            candidate["files"][0]["path"] = "../projects-inventory.json"
        self.assert_invalid(traversal)
        self.path.write_bytes(json_bytes(self.candidate))
        changed = dict(self.inventory)
        changed["total_rows"] = 1
        with patch("pipeline.snapshot.input.inspect_projects", return_value=changed), self.assertRaisesRegex(ValueError, "source inventory changed"):
            read_candidate(self.path)


if __name__ == "__main__":
    unittest.main()
