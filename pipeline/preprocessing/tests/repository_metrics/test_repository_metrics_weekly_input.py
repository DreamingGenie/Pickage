import hashlib
import tempfile
import unittest
from pathlib import Path

import duckdb

from pipeline.preprocessing.repository_metrics.input import _validate_derived_versions


class WeeklyRepositoryInputTests(unittest.TestCase):
    def test_derived_versions_are_bound_to_curated_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "weekly_versions" / "data"
            output.mkdir(parents=True)
            path = output / "part-0.parquet"
            with duckdb.connect() as con:
                con.execute("COPY (SELECT TIMESTAMP '2026-08-31 21:01:10.517131' AS SnapshotAt, 'demo' AS \"Name\", '1.0.0' AS \"Version\", true AS is_release, 1::BIGINT AS ordinal, NULL::TIMESTAMP AS published_at, NULL::VARCHAR AS source_repo) TO ? (FORMAT PARQUET)", [str(path)])
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            metadata = {"run_prefix": "depsdev/v1/package-version/snapshot=2026-08-31/run_id=r",
                        "manifest": {"files": [{"key": "depsdev/v1/package-version/snapshot=2026-08-31/run_id=r/attempts/a/weekly_versions/data/part-0.parquet",
                                                   "bytes": path.stat().st_size, "sha256": digest, "rows": 1}]}}
            bronze = {"source_manifest_sha256": "a" * 64}
            bronze_ref = {"key": "depsdev/v1/versions_min/run_manifest.json"}
            with duckdb.connect() as con:
                paths, records, lineage = _validate_derived_versions(
                    root, metadata, output, "2026-08-31", "2026-08-31T21:01:10.517131", bronze, bronze_ref, con)
            self.assertEqual(len(paths), 1)
            self.assertEqual(records[0]["source_table"], "versions_min")
            self.assertEqual(lineage, "a" * 64)

    def test_derived_versions_reject_unapproved_extra_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); output = root / "data"; output.mkdir()
            for name in ("part-0.parquet", "extra.parquet"):
                with duckdb.connect() as con:
                    con.execute("COPY (SELECT 1::INTEGER AS SnapshotAt) TO ? (FORMAT PARQUET)", [str(output / name)])
            metadata = {"run_prefix": "r", "manifest": {"files": [{"key": "r/attempts/a/weekly_versions/data/part-0.parquet", "bytes": (output / "part-0.parquet").stat().st_size, "sha256": hashlib.sha256((output / "part-0.parquet").read_bytes()).hexdigest()}]}}
            with duckdb.connect() as con, self.assertRaisesRegex(ValueError, "differ"):
                _validate_derived_versions(root, metadata, output, "2026-08-31", "2026-08-31T00:00:00", {"source_manifest_sha256": "a" * 64}, {"key": "x"}, con)


if __name__ == "__main__":
    unittest.main()
