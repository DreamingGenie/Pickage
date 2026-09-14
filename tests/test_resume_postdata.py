import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


PATH = Path(__file__).parents[1] / "scripts/service-data-migration/resume_postdata.py"
SPEC = importlib.util.spec_from_file_location("resume_postdata", PATH)
resume = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(resume)


def catalog(*, index_valid=True, attached=True, definition="CREATE UNIQUE INDEX"):
    return {
        "constraints": [{
            "kind": "constraint", "schema": "public", "table": "package_version_snapshot",
            "name": "package_version_snapshot_pkey", "contype": "p",
            "definition": "PRIMARY KEY (package_id, version, snapshot_at)",
            "convalidated": True, "index_name": "package_version_snapshot_pkey",
        }],
        "indexes": [{
            "kind": "index", "schema": "public", "table": "package_version_snapshot",
            "name": "package_version_snapshot_pkey", "definition": definition,
            "indisvalid": index_valid, "indisready": True, "is_primary": True, "is_unique": True,
        }],
        "inherits": ([{"kind": "inherits", "schema": resume.CHILD_SCHEMA,
                        "child": "d20260831_pkey", "parent": "package_version_snapshot_pkey"}]
                      if attached else []),
    }


class CatalogReconcileTests(unittest.TestCase):
    def test_wrong_index_definition_is_rejected(self):
        diff = resume.catalog_diff(catalog(), catalog(definition="CREATE INDEX wrong"))
        self.assertEqual(len(diff["mismatched"]), 1)

    def test_invalid_parent_index_is_tolerated_only_as_intermediate_state(self):
        diff = resume.catalog_diff(catalog(), catalog(index_valid=False, attached=False))
        self.assertEqual(diff["mismatched"], [])
        self.assertEqual(len(diff["missing"]), 1)
        strict = resume.catalog_diff(catalog(), catalog(index_valid=False, attached=False),
                                     allow_invalid_parent_pk=False)
        self.assertEqual(len(strict["mismatched"]), 1)

    def test_attachment_is_idempotent(self):
        diff = resume.catalog_diff(catalog(), catalog())
        self.assertEqual(diff, {"missing": [], "mismatched": [], "extra": []})

    def test_missing_table_attachment_is_a_hard_stop(self):
        diff = {"missing": [{"kind": "inherits", "child": "d20260831", "parent": "package_version_snapshot"}]}
        self.assertEqual(len(resume.missing_table_attachments(diff)), 1)

    def test_benchmark_gate_requires_version_index_only_scan_without_heap_fetches_or_sort(self):
        good = [{"Plan": {"Node Type": "Merge Anti Join", "Plans": [
            {"Node Type": "Index Only Scan", "Relation Name": "version", "Heap Fetches": 0, "Actual Rows": 100},
            {"Node Type": "Index Only Scan", "Relation Name": "d20260831", "Heap Fetches": 0, "Actual Rows": 100}]}}]
        self.assertTrue(resume.plan_supports_improved_fk(good))
        self.assertFalse(resume.plan_supports_improved_fk([{"Plan": {"Node Type": "Sort", "Plans": good}}]))
        self.assertFalse(resume.plan_supports_improved_fk([{"Plan": {"Node Type": "Index Only Scan", "Relation Name": "version", "Heap Fetches": 1}}]))


class TocSelectionTests(unittest.TestCase):
    TOC = """; archive TOC\n1; 2606 1 CONSTRAINT public package_version_snapshot package_version_snapshot_pkey\n2; 1259 2 INDEX public package_version_snapshot_pkey\n3; 0 0 INDEX ATTACH vd193_reload_20260912_ready01 d20260831_pkey\n4; 2606 4 CONSTRAINT vd193_reload_20260912_ready01 d20260831 d20260831_version_fk\n"""

    def test_prepare_omits_fk_and_selects_missing_attachment(self):
        expected = catalog()
        expected["constraints"].append({
            "kind": "constraint", "schema": resume.CHILD_SCHEMA, "table": "d20260831",
            "name": "d20260831_version_fk", "contype": "f", "definition": "FOREIGN KEY (package_id, version)",
            "convalidated": True, "index_name": "-",
        })
        actual = catalog(attached=False, index_valid=False)
        lines = resume.select_toc_lines(self.TOC, expected, actual, include_foreign_keys=False)
        self.assertTrue(any("INDEX ATTACH" in line for line in lines))
        self.assertFalse(any("version_fk" in line for line in lines))


class CheckpointTests(unittest.TestCase):
    def test_checkpoint_identity_refuses_other_archive_or_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "resume-status.json"
            path.write_text(json.dumps({
                "candidate_db": "pickage_import_341_a",
                "archive_identity": {"archive_name": "archive", "manifest_sha256": "a"},
            }), encoding="utf-8")
            with self.assertRaises(resume.ResumeError):
                resume.load_checkpoint(path, {"archive_name": "archive", "manifest_sha256": "b"},
                                       "pickage_import_341_a")
            with self.assertRaises(resume.ResumeError):
                resume.load_checkpoint(path, {"archive_name": "archive", "manifest_sha256": "a"},
                                       "pickage_import_341_other")


if __name__ == "__main__":
    unittest.main()
