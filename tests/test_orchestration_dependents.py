"""Independent tiny oracles through actual task08 npm/SQL kernels."""
from datetime import date
from pathlib import Path
import tempfile
import unittest

import duckdb

from pipeline.orchestration.dependents import calculate
from tests.orchestration_fixture import _parquet


class DependentsTests(unittest.TestCase):
    def case(self, root, snapshot, *, new_version=False, null_list=False, invalid_range=False):
        root = Path(root)
        stamp = snapshot + "T21:00:00Z"
        packages = [(10, "app"), (20, "lib"), (30, "zero")]
        versions = [(10, "0.9.0", "2020-01-01"), (10, "1.0.0", "2021-01-01"),
                    (20, "1.0.0", "2020-01-01"), (30, "1.0.0", "2020-01-01")]
        if new_version:
            versions.append((20, "1.1.0", snapshot + "T20:00:00"))
        paths = {}
        for table, schema, rows in (
            ("package", "package_id INTEGER,name VARCHAR", packages),
            ("version", "package_id INTEGER,version VARCHAR,published_at TIMESTAMP", versions),
            ("versions_full", "Name VARCHAR,Version VARCHAR,published_at TIMESTAMP,is_release BOOLEAN,"
                              "dependency_error BOOLEAN,SnapshotAt TIMESTAMP",
             [(dict(packages)[pid], v, p, True, False, stamp) for pid, v, p in versions])):
            path = root / (table + ".parquet")
            _parquet(path, schema, rows)
            paths[table] = [path]
        requirements = []
        for pid, version, _ in versions:
            deps = []
            if pid == 10:
                deps = [{"Name": "lib", "Requirement": "^1"}]
                if version == "1.0.0":
                    deps *= 2  # Same source must count once despite duplicate declarations.
                    if invalid_range:
                        deps += [{"Name": "lib", "Requirement": "workspace:*"}]
                elif null_list:
                    deps = None
            requirements.append((dict(packages)[pid], version, deps, [], [], stamp))
        path = root / "requirements.parquet"
        _parquet(path, "Name VARCHAR,Version VARCHAR,Dependencies STRUCT(Name VARCHAR,Requirement VARCHAR)[],"
                 "PeerDependencies STRUCT(Name VARCHAR,Requirement VARCHAR)[],"
                 "OptionalDependencies STRUCT(Name VARCHAR,Requirement VARCHAR)[],SnapshotAt TIMESTAMP", requirements)
        paths["requirements"] = [path]
        paths["targets"] = root / "targets.parquet"
        _parquet(paths["targets"], "name VARCHAR", [("lib",), ("zero",)])
        with duckdb.connect(str(root / "working.duckdb"), config={"threads": 1, "memory_limit": "512MB"}) as con:
            con.execute("SET TimeZone='UTC'")
            output, schemas, quality = calculate(con, files=paths, snapshot=snapshot,
                snapshot_timestamp=stamp, output=root / "attempt")
            rows = con.execute("SELECT * FROM read_parquet(?) ORDER BY package_id,version",
                               [str(output / "version_dependents.parquet")]).fetchall()
        return rows, schemas, quality

    def test_two_dates_old_sources_move_to_new_target_release(self):
        with tempfile.TemporaryDirectory() as root:
            first, _, q1 = self.case(Path(root) / "first", "2026-08-31")
            second, schemas, q2 = self.case(Path(root) / "second", "2026-09-07", new_version=True)
        self.assertEqual(first, [(10, "0.9.0", date(2026, 8, 31), None),
                                 (10, "1.0.0", date(2026, 8, 31), None),
                                 (20, "1.0.0", date(2026, 8, 31), 2), (30, "1.0.0", date(2026, 8, 31), 0)])
        self.assertEqual([(r[0], r[1], r[3]) for r in second],
                         [(10, "0.9.0", None), (10, "1.0.0", None), (20, "1.0.0", 0), (20, "1.1.0", 2), (30, "1.0.0", 0)])
        self.assertEqual(q1["resolution_status"], "COMPLETE")
        self.assertEqual(q2["snapshot_count"], 1)
        self.assertEqual(schemas[0]["schema"][2], ["snapshot_at", "DATE"])

    def test_null_list_and_unsupported_range_preserve_partial(self):
        with tempfile.TemporaryDirectory() as root:
            rows, _, quality = self.case(Path(root), "2026-08-31", null_list=True, invalid_range=True)
        self.assertEqual(quality["calculation_status"], "COMPLETE")
        self.assertEqual(quality["resolution_status"], "PARTIAL")
        self.assertEqual(quality["source_gaps"]["null_dependency_list"], 1)
        self.assertEqual(quality["unresolved_declarations"], 1)
        self.assertEqual(rows[2][3], 1)
        self.assertIsNone(rows[0][3])


if __name__ == "__main__":
    unittest.main()
