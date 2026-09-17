import json
import io
import hashlib
import tempfile
import unittest
from pathlib import Path

import duckdb

from pipeline.orchestration.weekly_request import _parent_from_bundle, _project_timestamp


class _S3:
    def __init__(self, objects):
        self.objects = objects

    def get_object(self, *, Bucket, Key):
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    def head_object(self, **kwargs):
        value = self.objects[(kwargs["Bucket"], kwargs["Key"])]
        return {"ContentLength": len(value)}


class WeeklyRequestHelpersTests(unittest.TestCase):
    def test_parent_bundle_requires_complete_pointer_shape(self):
        value = {"run_prefix": "depsdev/v1/curated-bundle/snapshot=2026-08-31/run_id=r1",
                 "manifest_sha256": "a" * 64, "snapshot": "2026-08-31"}
        self.assertEqual(_parent_from_bundle(value), value)
        with self.assertRaises(ValueError):
            _parent_from_bundle({"snapshot": "2026-08-31"})

    def test_project_timestamp_is_read_from_parquet(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "projects.parquet"
            with duckdb.connect() as con:
                con.execute("CREATE TABLE p(SnapshotAt TIMESTAMP, Type VARCHAR)")
                con.execute("INSERT INTO p VALUES ('2026-08-31 21:01:10', 'GITHUB')")
                con.execute("COPY p TO ? (FORMAT PARQUET)", [str(path)])
            body = path.read_bytes()
            s3 = _S3({("pickage-raw", "projects.parquet"): body})
            self.assertEqual(_project_timestamp(s3, {"files": [{"key": "projects.parquet", "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}]}),
                             "2026-08-31T21:01:10Z")

    def test_project_timestamp_rejects_multiple_values(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "projects.parquet"
            with duckdb.connect() as con:
                con.execute("CREATE TABLE p(SnapshotAt TIMESTAMP)")
                con.execute("INSERT INTO p VALUES ('2026-08-31 21:01:10'), ('2026-08-31 21:02:10')")
                con.execute("COPY p TO ? (FORMAT PARQUET)", [str(path)])
            body = path.read_bytes()
            with self.assertRaisesRegex(ValueError, "one exact SnapshotAt"):
                _project_timestamp(_S3({("pickage-raw", "projects.parquet"): path.read_bytes()}),
                                   {"files": [{"key": "projects.parquet", "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}]})


if __name__ == "__main__":
    unittest.main()
