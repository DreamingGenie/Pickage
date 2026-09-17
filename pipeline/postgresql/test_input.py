import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import duckdb
from botocore.exceptions import ClientError

from pipeline.preprocessing.curated.storage import json_bytes
from pipeline.postgresql import input as loader_input


SNAPSHOT = "2026-08-31"
RUN_ID = "curated-test"


class _Body:
    def __init__(self, value):
        self.value, self.offset = value, 0

    def read(self, size=-1):
        if size < 0:
            size = len(self.value)
        result = self.value[self.offset:self.offset + size]
        self.offset += len(result)
        return result

    def close(self):
        pass


class FakeS3:
    def __init__(self):
        self.objects = {}

    def get_object(self, Bucket, Key):
        try:
            body, etag = self.objects[(Bucket, Key)]
        except KeyError:
            raise ClientError({"Error": {"Code": "404"}}, "GetObject")
        return {"Body": _Body(body), "ETag": '"' + etag + '"'}

    def head_object(self, Bucket, Key):
        try:
            body, _ = self.objects[(Bucket, Key)]
        except KeyError:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {"ContentLength": len(body)}

    def put_object(self, Bucket, Key, Body, **kwargs):
        self.objects[(Bucket, Key)] = (Body, _sha(Body))
        return {"ETag": '"' + _sha(Body) + '"'}


def _sha(body):
    return hashlib.sha256(body).hexdigest()


class InputTests(unittest.TestCase):
    def setUp(self):
        self.s3 = FakeS3()
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        with duckdb.connect() as con:
            con.execute("CREATE TABLE package(package_id INTEGER,name VARCHAR,repo_url VARCHAR)")
            con.execute("INSERT INTO package VALUES (1,'a\\nb','https://example.invalid/a')")
            con.execute(f"COPY package TO '{(root / 'package.parquet').as_posix()}' (FORMAT PARQUET)")
            con.execute("CREATE TABLE version(version VARCHAR,package_id INTEGER,published_at TIMESTAMP,ordinal BIGINT,description VARCHAR,licenses JSON,deprecated VARCHAR,dependency JSON)")
            con.execute("INSERT INTO version VALUES ('1.0.0',1,TIMESTAMP '2026-08-30 01:02:03.123456',0,E'line1\\n\\\\.\\tline2','[{\"type\":\"MIT\"}]',NULL,json '{\"dependencies\":{},\"peerDependencies\":{},\"optionalDependencies\":{}}')")
            con.execute(f"COPY version TO '{(root / 'version.parquet').as_posix()}' (FORMAT PARQUET)")
        self._seed(root)

    def tearDown(self):
        self.temp.cleanup()

    def _seed(self, root, corrupt=False):
        self._install(root / "package.parquet", root / "version.parquet", corrupt=corrupt)

    def _install(self, package_path, version_path, corrupt=False,
                 files_override=None, report_counts=None):
        files = []
        for table, path in (("package", package_path), ("version", version_path)):
            body = path.read_bytes()
            if corrupt and table == "version":
                body = body + b"x"
            key = f"{loader_input.PREFIX}/snapshot={SNAPSHOT}/run_id={RUN_ID}/attempts/a1/{table}/data/part-0.parquet"
            self.s3.put_object(Bucket=loader_input.CURATED_BUCKET, Key=key, Body=body)
            files.append({"key": key, "bytes": len(body), "sha256": _sha(body)})
        if files_override is not None:
            files = files_override
        manifest = {"contract_version": 1, "status": "PASSED",
                    "verification": "GET_SHA256_ALL_FILES",
                    "request": {"snapshot": SNAPSHOT, "run_id": RUN_ID},
                    "report": {"snapshot_timestamp": "2026-08-30T01:02:03.123456",
                               "output_counts": {"package/data": 1, "version/data": 1}},
                    "files": files}
        if report_counts is not None:
            manifest["report"]["output_counts"] = report_counts
        body = json_bytes(manifest)
        prefix = f"{loader_input.PREFIX}/snapshot={SNAPSHOT}/run_id={RUN_ID}"
        self.s3.put_object(Bucket=loader_input.CURATED_BUCKET, Key=prefix + "/run_manifest.json", Body=body)
        self.s3.put_object(Bucket=loader_input.CURATED_BUCKET, Key=prefix + "/_SUCCESS",
                           Body=json_bytes({"manifest_sha256": _sha(body)}))

    def test_select_and_prepare_text_copy(self):
        metadata = loader_input.select_run(self.s3, SNAPSHOT, RUN_ID)
        result = loader_input.prepare(self.s3, metadata, Path(self.temp.name) / "work")
        self.assertEqual(result["counts"], {"package": 1, "version": 1})
        raw = result["csv_files"]["version"][0].read_bytes()
        self.assertNotIn(b"\n\\.\n", raw)
        self.assertIn(b"\\n", raw)
        self.assertIn(b"\\\\.", raw)
        self.assertIn(b"01:02:03.123456", raw)

    def test_marker_corruption_is_rejected(self):
        prefix = f"{loader_input.PREFIX}/snapshot={SNAPSHOT}/run_id={RUN_ID}"
        self.s3.put_object(Bucket=loader_input.CURATED_BUCKET, Key=prefix + "/_SUCCESS", Body=b"{}")
        with self.assertRaisesRegex(ValueError, "marker hash"):
            loader_input.select_run(self.s3, SNAPSHOT, RUN_ID)

    def test_physical_file_corruption_is_rejected(self):
        metadata = loader_input.select_run(self.s3, SNAPSHOT, RUN_ID)
        record = metadata["_service_records"]["version"][0]
        body = self.s3.objects[(loader_input.CURATED_BUCKET, record["key"])][0]
        self.s3.put_object(Bucket=loader_input.CURATED_BUCKET, Key=record["key"], Body=body + b"bad")
        with self.assertRaises(ValueError):
            loader_input.prepare(self.s3, metadata, Path(self.temp.name) / "work")

    def test_missing_marker_and_unapproved_manifest_are_rejected(self):
        prefix = f"{loader_input.PREFIX}/snapshot={SNAPSHOT}/run_id={RUN_ID}"
        body, _ = self.s3.objects[(loader_input.CURATED_BUCKET, prefix + "/run_manifest.json")]
        self.s3.objects.pop((loader_input.CURATED_BUCKET, prefix + "/_SUCCESS"))
        with self.assertRaisesRegex(ValueError, "Required object missing"):
            loader_input.select_run(self.s3, SNAPSHOT, RUN_ID)
        self.s3.put_object(Bucket=loader_input.CURATED_BUCKET, Key=prefix + "/_SUCCESS",
                           Body=json_bytes({"manifest_sha256": _sha(body)}))
        manifest = json.loads(body)
        manifest["status"] = "PREPARED"
        body = json_bytes(manifest)
        self.s3.put_object(Bucket=loader_input.CURATED_BUCKET, Key=prefix + "/run_manifest.json", Body=body)
        self.s3.put_object(Bucket=loader_input.CURATED_BUCKET, Key=prefix + "/_SUCCESS",
                           Body=json_bytes({"manifest_sha256": _sha(body)}))
        with self.assertRaisesRegex(ValueError, "Unapproved"):
            loader_input.select_run(self.s3, SNAPSHOT, RUN_ID)

    def test_mixed_attempt_and_foreign_records_are_rejected(self):
        prefix = f"{loader_input.PREFIX}/snapshot={SNAPSHOT}/run_id={RUN_ID}"
        body = self.s3.objects[(loader_input.CURATED_BUCKET, prefix + "/run_manifest.json")][0]
        manifest = json.loads(body)
        records = manifest["files"]
        records[0] = dict(records[0], key=records[0]["key"].replace("attempts/a1", "attempts/a2"))
        body = json_bytes(manifest)
        self.s3.put_object(Bucket=loader_input.CURATED_BUCKET, Key=prefix + "/run_manifest.json", Body=body)
        self.s3.put_object(Bucket=loader_input.CURATED_BUCKET, Key=prefix + "/_SUCCESS",
                           Body=json_bytes({"manifest_sha256": _sha(body)}))
        with self.assertRaisesRegex(ValueError, "canonical attempt"):
            loader_input.select_run(self.s3, SNAPSHOT, RUN_ID)

    def test_report_count_mismatch_is_rejected(self):
        prefix = f"{loader_input.PREFIX}/snapshot={SNAPSHOT}/run_id={RUN_ID}"
        body = self.s3.objects[(loader_input.CURATED_BUCKET, prefix + "/run_manifest.json")][0]
        manifest = json.loads(body)
        manifest["report"]["output_counts"]["package/data"] = 2
        body = json_bytes(manifest)
        self.s3.put_object(Bucket=loader_input.CURATED_BUCKET, Key=prefix + "/run_manifest.json", Body=body)
        self.s3.put_object(Bucket=loader_input.CURATED_BUCKET, Key=prefix + "/_SUCCESS",
                           Body=json_bytes({"manifest_sha256": _sha(body)}))
        metadata = loader_input.select_run(self.s3, SNAPSHOT, RUN_ID)
        with self.assertRaisesRegex(ValueError, "manifest counts"):
            loader_input.prepare(self.s3, metadata, Path(self.temp.name) / "work")

    def test_schema_and_duplicate_constraints_are_rejected(self):
        root = Path(self.temp.name)
        bad = root / "bad-package.parquet"
        with duckdb.connect() as con:
            con.execute("CREATE TABLE bad(package_id BIGINT,name VARCHAR,repo_url VARCHAR)")
            con.execute("INSERT INTO bad VALUES (1,'a','x')")
            con.execute(f"COPY bad TO '{bad.as_posix()}' (FORMAT PARQUET)")
        self._install(bad, root / "version.parquet")
        metadata = loader_input.select_run(self.s3, SNAPSHOT, RUN_ID)
        with self.assertRaisesRegex(ValueError, "schema mismatch"):
            loader_input.prepare(self.s3, metadata, root / "schema-work")

    def test_key_fk_and_string_validation_are_rejected(self):
        root = Path(self.temp.name)
        package = root / "invalid-package.parquet"
        version = root / "invalid-version.parquet"
        with duckdb.connect() as con:
            con.execute("CREATE TABLE p(package_id INTEGER,name VARCHAR,repo_url VARCHAR)")
            con.execute("INSERT INTO p VALUES (1,'same','x'),(1,'same','x')")
            con.execute(f"COPY p TO '{package.as_posix()}' (FORMAT PARQUET)")
            con.execute("CREATE TABLE v(version VARCHAR,package_id INTEGER,published_at TIMESTAMP,ordinal BIGINT,description VARCHAR,licenses JSON,deprecated VARCHAR,dependency JSON)")
            con.execute("INSERT INTO v VALUES ('',99,NULL,-1,NULL,NULL,'bad' || chr(0),json '{\"x\":1}')")
            con.execute(f"COPY v TO '{version.as_posix()}' (FORMAT PARQUET)")
        self._install(package, version, report_counts={"package/data": 2, "version/data": 1})
        metadata = loader_input.select_run(self.s3, SNAPSHOT, RUN_ID)
        with self.assertRaisesRegex(ValueError, "validation failed"):
            loader_input.prepare(self.s3, metadata, root / "invalid-work")

    def test_sql_null_json_null_empty_json_and_array_are_preserved(self):
        root = Path(self.temp.name)
        version = root / "json-version.parquet"
        with duckdb.connect() as con:
            con.execute("CREATE TABLE v(version VARCHAR,package_id INTEGER,published_at TIMESTAMP,ordinal BIGINT,description VARCHAR,licenses JSON,deprecated VARCHAR,dependency JSON)")
            con.execute("INSERT INTO v VALUES ('null-value',1,NULL,0,NULL,NULL,NULL,json '{\"dependencies\":{},\"peerDependencies\":{},\"optionalDependencies\":{}}'),('json-null',1,NULL,1,NULL,json 'null',NULL,json 'null'),('empty-object',1,NULL,2,NULL,json '{}',NULL,json '{}'),('empty-array',1,NULL,3,NULL,json '[]',NULL,json '[]')")
            con.execute(f"COPY v TO '{version.as_posix()}' (FORMAT PARQUET)")
        self._install(root / "package.parquet", version, report_counts={"package/data": 1, "version/data": 4})
        metadata = loader_input.select_run(self.s3, SNAPSHOT, RUN_ID)
        result = loader_input.prepare(self.s3, metadata, root / "json-work")
        text = result["csv_files"]["version"][0].read_text(encoding="utf-8")
        self.assertIn("\\N", text)
        self.assertIn("null", text)
        self.assertIn("{}", text)
        self.assertIn("[]", text)

    def test_sql_null_dependency_is_defaulted_and_recorded(self):
        root = Path(self.temp.name)
        version = root / "null-dependency-version.parquet"
        with duckdb.connect() as con:
            con.execute("CREATE TABLE v(version VARCHAR,package_id INTEGER,published_at TIMESTAMP,ordinal BIGINT,description VARCHAR,licenses JSON,deprecated VARCHAR,dependency JSON)")
            con.execute("INSERT INTO v VALUES ('1.0.0',1,NULL,0,NULL,NULL,NULL,NULL)")
            con.execute(f"COPY v TO '{version.as_posix()}' (FORMAT PARQUET)")
        self._install(root / "package.parquet", version)
        metadata = loader_input.select_run(self.s3, SNAPSHOT, RUN_ID)
        result = loader_input.prepare(self.s3, metadata, root / "null-dependency-work")
        quality = result["quality"]["dependency_defaulted"]
        self.assertEqual(quality["count"], 1)
        self.assertEqual(quality["default_json"], loader_input.DEFAULT_DEPENDENCY)
        quality_path = Path(quality["path"])
        quality_body = quality_path.read_bytes()
        self.assertEqual(quality["sha256"], hashlib.sha256(quality_body).hexdigest())
        record = json.loads(quality_body.decode("utf-8"))
        self.assertEqual(record["package_id"], 1)
        self.assertEqual(record["name"], "a\\nb")
        self.assertEqual(record["version"], "1.0.0")
        self.assertEqual(record["reason"], "DEPENDENCY_SQL_NULL_DEFAULTED")
        self.assertTrue(record["source_dependency_is_sql_null"])
        self.assertEqual(record["replacement"], loader_input.DEFAULT_DEPENDENCY)
        self.assertEqual(record["source_run"], RUN_ID)
        self.assertEqual(record["manifest_sha256"], metadata["manifest_sha256"])
        copy_text = result["csv_files"]["version"][0].read_text(encoding="utf-8")
        self.assertIn(loader_input.DEFAULT_DEPENDENCY_JSON, copy_text)


if __name__ == "__main__":
    unittest.main()
