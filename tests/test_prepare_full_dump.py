import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).parents[1] / "scripts" / "service-data-migration"
sys.path.insert(0, str(SCRIPT_DIR))
SPEC = importlib.util.spec_from_file_location("prepare_full_dump", SCRIPT_DIR / "prepare_full_dump.py")
prepare = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(prepare)


ROOTS = ("package", "version", "snapshot", "package_snapshot", "package_version_snapshot")
CHILD_SCHEMA = "vd193_reload_20260912_ready01"


def catalog():
    relations = [
        {"schema": "public", "table": table, "kind": "p" if table == "package_version_snapshot" else "r"}
        for table in ROOTS
    ]
    relations.extend(
        {"schema": CHILD_SCHEMA, "table": f"d202608{day:02d}", "kind": "r"}
        for day in (30, 31)
    )
    return {"relations": relations}


def toc(*, omit=None, include_parent_data=False):
    omit = set(omit or ())
    lines = []
    number = 1
    for schema, table in [("public", table) for table in ROOTS] + [
        (CHILD_SCHEMA, "d20260830"), (CHILD_SCHEMA, "d20260831")
    ]:
        key = (schema, table, "definition")
        if key not in omit:
            lines.append(f"{number}; 1259 {number} TABLE {schema} {table} postgres")
            number += 1
    data_tables = [("public", table) for table in ROOTS[:-1]] + [
        (CHILD_SCHEMA, "d20260830"), (CHILD_SCHEMA, "d20260831")
    ]
    if include_parent_data:
        data_tables.append(("public", "package_version_snapshot"))
    for schema, table in data_tables:
        key = (schema, table, "data")
        if key not in omit:
            lines.append(f"{number}; 1259 {number} TABLE DATA {schema} {table} postgres")
            number += 1
    return "\n".join(lines)


class PrepareFullDumpTests(unittest.TestCase):
    def test_toc_matches_catalog_and_rejects_missing_data(self):
        prepare.verify_full_toc(toc(), catalog())
        with self.assertRaises(RuntimeError):
            prepare.verify_full_toc(toc(omit={(CHILD_SCHEMA, "d20260831", "data")}), catalog())
        with self.assertRaises(RuntimeError):
            prepare.verify_full_toc(toc(include_parent_data=True), catalog())
        with self.assertRaises(RuntimeError):
            prepare.verify_full_toc(toc(omit={("public", "version", "definition")}), catalog())

    def test_stale_receipts_cannot_be_reused_as_a_new_run(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw)
            (root/'code').mkdir()
            (root/'stdout.log').touch()
            prepare.check_new_run_directory(root)
            (root/'expected-signatures.json').write_text('{}')
            with self.assertRaises(RuntimeError):
                prepare.check_new_run_directory(root)

    def test_receipt_aggregation_preserves_rows_and_signed_hash_sums(self):
        groups = [
            {"rows": 3, "sum_hi": "-2", "sum_lo": "7"},
            {"rows": 4, "sum_hi": "5", "sum_lo": "-9"},
        ]
        self.assertEqual(prepare.add_signatures(groups), {"rows": 7, "sum_hi": "3", "sum_lo": "-2"})


if __name__ == "__main__":
    unittest.main()
