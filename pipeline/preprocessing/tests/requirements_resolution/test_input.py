import json
from pathlib import Path
from unittest.mock import patch
import unittest

from pipeline.preprocessing.requirements_resolution.input import prepare_inputs, reverify_inputs
from pipeline.preprocessing.tests.fixtures.requirements_resolution import Fixture, SNAPSHOT


class PrepareInputsEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.fixture = Fixture()

    def tearDown(self):
        self.fixture.close()

    def test_prepare_serialize_and_reverify_with_remote_lineage(self):
        output = self.fixture.root / "prepared.json"
        prepared = prepare_inputs(self.fixture.s3, **self.fixture.arguments(output))
        self.assertEqual(prepared["counts"], {"package": 1, "version": 1, "versions_full": 1, "requirements": 1})
        serialized = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(serialized["input_sha256"], prepared["input_sha256"])
        self.assertTrue(reverify_inputs(serialized, self.fixture.s3))

    def test_tamper_same_size_missing_and_extra_file_fail(self):
        prepared = prepare_inputs(self.fixture.s3, **self.fixture.arguments())
        path = Path(prepared["files"]["requirements"][0])
        body = path.read_bytes()
        path.write_bytes(bytes([body[0] ^ 1]) + body[1:])
        with self.assertRaises(ValueError):
            reverify_inputs(prepared)
        path.write_bytes(body)
        path.unlink()
        with self.assertRaises(ValueError):
            reverify_inputs(prepared)
        path.write_bytes(body)
        extra = path.with_name("part-extra.parquet")
        extra.write_bytes(body)
        with self.assertRaises(ValueError):
            reverify_inputs(prepared)

    def test_raw_wrong_snapshot_is_rejected_after_consistent_manifest_update(self):
        self.fixture.raw_rows["requirements"][0]["SnapshotAt"] = "2026-09-01 21:01:10.123456"
        self.fixture._refresh_raw("requirements")
        self.fixture._publish_curated(self.fixture.curated / "package/data/part-000.parquet", self.fixture.curated / "version/data/part-000.parquet")
        with self.assertRaisesRegex(ValueError, "Raw input"):
            prepare_inputs(self.fixture.s3, **self.fixture.arguments())

    def test_remote_fingerprint_change_fails_reverify(self):
        prepared = prepare_inputs(self.fixture.s3, **self.fixture.arguments())
        key = prepared["bronze_references"]["requirements"]["key"]
        body = self.fixture.s3.objects[("pickage-raw", key)][0]
        self.fixture.s3.put_object(Bucket="pickage-raw", Key=key, Body=body + b"x")
        with self.assertRaises(ValueError):
            reverify_inputs(prepared, self.fixture.s3)

    def test_curated_run_change_fails_reverify(self):
        prepared = prepare_inputs(self.fixture.s3, **self.fixture.arguments())
        key = f"depsdev/v1/package-version/snapshot={SNAPSHOT}/run_id=curated-test/run_manifest.json"
        body = self.fixture.s3.objects[("pickage-curated", key)][0]
        self.fixture.s3.put_object(Bucket="pickage-curated", Key=key, Body=body + b"x")
        with self.assertRaises(ValueError):
            reverify_inputs(prepared, self.fixture.s3)

    def test_path_escape_and_output_inside_input_fail(self):
        with self.assertRaises(ValueError):
            prepare_inputs(self.fixture.s3, **self.fixture.arguments(self.fixture.curated / "out.json"))
        args = self.fixture.arguments()
        args["requirements_dir"] = self.fixture.requirements / ".."
        with self.assertRaises((ValueError, FileNotFoundError)):
            prepare_inputs(self.fixture.s3, **args)

    def test_null_snapshot_fails_with_approved_file_fingerprint(self):
        self.fixture.raw_rows["requirements"][0]["SnapshotAt"] = None
        self.fixture._refresh_raw("requirements")
        self.fixture._publish_curated(self.fixture.curated / "package/data/part-000.parquet", self.fixture.curated / "version/data/part-000.parquet")
        with self.assertRaisesRegex(ValueError, "NULL"):
            prepare_inputs(self.fixture.s3, **self.fixture.arguments())

    def test_schema_contract_fails_even_when_file_hash_matches(self):
        # Force the expected schema to differ; hashes and remote approval still match.
        with patch("pipeline.preprocessing.requirements_resolution.input.RAW_SCHEMAS", {"versions_full": []}):
            with self.assertRaisesRegex(ValueError, "schema mismatch"):
                prepare_inputs(self.fixture.s3, **self.fixture.arguments())

    def test_changed_extraction_summary_fails(self):
        marker = self.fixture.requirements / "_MANIFEST.json"
        marker.write_bytes(marker.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "extraction summary"):
            prepare_inputs(self.fixture.s3, **self.fixture.arguments())


if __name__ == "__main__":
    unittest.main()
