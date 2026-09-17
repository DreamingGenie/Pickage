import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import duckdb
from botocore.exceptions import ClientError

from pipeline.curated import build


class _Body:
    def __init__(self, body):
        self.body, self.offset = body, 0

    def read(self, size=-1):
        if size < 0:
            size = len(self.body) - self.offset
        value = self.body[self.offset:self.offset + size]
        self.offset += len(value)
        return value

    def close(self):
        pass


class FakeS3:
    def __init__(self):
        self.objects = {}

    def get_object(self, Bucket, Key):
        body = self.objects.get((Bucket, Key))
        if body is None:
            raise ClientError({"Error": {"Code": "404"}}, "GetObject")
        return {"Body": _Body(body), "ETag": '"' + hashlib.md5(body).hexdigest() + '"'}

    def head_object(self, Bucket, Key):
        body = self.objects.get((Bucket, Key))
        if body is None:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {"ContentLength": len(body), "ETag": '"' + hashlib.md5(body).hexdigest() + '"'}

    def list_objects_v2(self, Bucket, Prefix, **_):
        return {"Contents": [{"Key": key} for (bucket, key) in sorted(self.objects)
                              if bucket == Bucket and key.startswith(Prefix)],
                "IsTruncated": False}

    def put_object(self, Bucket, Key, Body, IfNoneMatch=None, IfMatch=None, **_):
        old = self.objects.get((Bucket, Key))
        digest = hashlib.md5(Body).hexdigest()
        if IfNoneMatch == "*" and old is not None:
            raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")
        if IfMatch is not None and (old is None or hashlib.md5(old).hexdigest() != IfMatch.strip('"')):
            raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")
        self.objects[(Bucket, Key)] = Body
        return {"ETag": '"' + digest + '"'}

    def delete_object(self, Bucket, Key, IfMatch=None):
        if (Bucket, Key) not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "DeleteObject")
        del self.objects[(Bucket, Key)]


def _parquet(schema, rows, path):
    with duckdb.connect() as con:
        con.execute("CREATE TABLE data (" + schema + ")")
        if rows:
            con.executemany("INSERT INTO data VALUES (" + ",".join("?" for _ in rows[0]) + ")", rows)
        con.execute("COPY data TO ? (FORMAT PARQUET)", [str(path)])
    return path.read_bytes()


def _put_raw(s3, root, table, snapshot, run_id, schema, rows):
    path = root / f"{table}.parquet"
    body = _parquet(schema, rows, path)
    prefix = f"depsdev/v1/{table}/snapshot={snapshot}/run_id={run_id}"
    key = prefix + "/data/part-000.parquet"
    s3.put_object(Bucket=build.RAW_BUCKET, Key=key, Body=body)
    source = {"status": "done", "verify": "ok", "snapshot": snapshot, "table": table,
              "rows": len(rows), "gcs_files": 1, "gcs_bytes": len(body)}
    source_body = json.dumps(source, separators=(",", ":")).encode()
    s3.put_object(Bucket=build.RAW_BUCKET, Key=prefix + "/source_manifest.json", Body=source_body)
    record = {"key": key, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
    manifest = {"contract_version": 1, "run_id": run_id, "status": "PASSED", "table": table,
                "snapshot": snapshot, "row_count": len(rows), "file_count": 1, "bytes": len(body),
                "verification": "GET_SHA256_ALL_FILES", "source_manifest_sha256": hashlib.sha256(source_body).hexdigest(),
                "files": [record]}
    s3.put_object(Bucket=build.RAW_BUCKET, Key=prefix + "/run_manifest.json",
                  Body=json.dumps(manifest, separators=(",", ":")).encode())
    s3.put_object(Bucket=build.RAW_BUCKET, Key=prefix + "/_SUCCESS", Body=b"")


class WeeklyBuildIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.s3 = FakeS3()
        self.full_schema = ("Name VARCHAR, Version VARCHAR, published_at TIMESTAMP, is_release BOOLEAN, "
                            "ordinal BIGINT, Description VARCHAR, Licenses VARCHAR[], Deprecated VARCHAR, "
                            "source_repo VARCHAR, SnapshotAt TIMESTAMP")
        self.min_schema = "Name VARCHAR, Version VARCHAR, published_at TIMESTAMP, is_release BOOLEAN, ordinal BIGINT, Deprecated VARCHAR, SnapshotAt TIMESTAMP"
        self.req_schema = ("Name VARCHAR, Version VARCHAR, Dependencies STRUCT(Name VARCHAR, Requirement VARCHAR)[], "
                           "PeerDependencies STRUCT(Name VARCHAR, Requirement VARCHAR)[], OptionalDependencies STRUCT(Name VARCHAR, Requirement VARCHAR)[], SnapshotAt TIMESTAMP")

    def tearDown(self):
        self.temp.cleanup()

    def seed(self, snapshot, run_id, table, rows, schema):
        _put_raw(self.s3, self.root, table, snapshot, run_id, schema, rows)

    def execute(self, snapshot, bronze, run_id, versions_table):
        return build.run(self.s3, snapshot, bronze, run_id, self.root / run_id,
                         workers=1, threads=1, memory="1GB", versions_table=versions_table)

    def rows(self, manifest, needle):
        record = next(r for r in manifest["files"] if needle in r["key"])
        body = self.s3.objects[(build.CURATED_BUCKET, record["key"])]
        path = self.root / ("read-" + hashlib.md5(body).hexdigest() + ".parquet")
        path.write_bytes(body)
        with duckdb.connect() as con:
            return con.execute("SELECT * FROM read_parquet(?)", [str(path)]).fetchall()

    def test_full_then_min_inherits_and_cumulates_missing_parent(self):
        ts0 = "2026-08-31T21:01:10"
        ts1 = "2026-09-07T21:01:10"
        full_versions = [("alpha", "1.0.0", ts0, True, 1, "stable alpha", ["MIT"], None,
                          "https://github.com/example/alpha.git", ts0)]
        req0 = [("alpha", "1.0.0", [], [], [], ts0)]
        self.seed("2026-08-31", "raw-full", "versions_full", full_versions, self.full_schema)
        self.seed("2026-08-31", "raw-full", "requirements", req0, self.req_schema)
        first = self.execute("2026-08-31", "raw-full", "curated-full", "versions_full")

        min_versions = [("alpha", "1.0.0", ts1, True, 1, "old", ts1),
                        ("alpha", "2.0.0", ts1, True, 2, "new", ts1),
                        ("beta", "1.0.0", ts1, True, 1, None, ts1)]
        req1 = [(name, version, [], [], [], ts1)
                for name, version, *_ in min_versions]
        self.seed("2026-09-07", "raw-min", "versions_min", min_versions, self.min_schema)
        self.seed("2026-09-07", "raw-min", "requirements", req1, self.req_schema)
        second = self.execute("2026-09-07", "raw-min", "curated-min", "versions_min")
        version_rows = self.rows(second, "/version/data/")
        by_version = {row[0]: row for row in version_rows if row[1] == 1}
        self.assertEqual(by_version["1.0.0"][4:7], ("stable alpha", '["MIT"]', "old"))
        self.assertEqual(by_version["2.0.0"][4:7], ("stable alpha", '["MIT"]', "new"))
        beta = next(row for row in version_rows if row[1] == 2)
        self.assertEqual(beta[4:7], (None, None, None))
        master_packages = self.rows(second, "/master_package/data/")
        self.assertEqual({row[1] for row in master_packages}, {"alpha", "beta"})
        change_rows = self.rows(second, "/changes/version_upserts.parquet")
        self.assertGreaterEqual(len(change_rows), 2)
        self.assertEqual(self.rows(first, "/master_package/data/"), [(1, "alpha", "https://github.com/example/alpha")])


if __name__ == "__main__":
    unittest.main()
