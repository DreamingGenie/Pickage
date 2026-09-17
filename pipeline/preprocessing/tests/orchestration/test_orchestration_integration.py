"""Small real-stage orchestration tests over an isolated S3 client."""
from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest

import duckdb

from pipeline.preprocessing.orchestration.runner import run, status
from pipeline.preprocessing.orchestration.storage import BUCKET, PREFIX

from pipeline.preprocessing.tests.fixtures.orchestration_fixture import make_fixture


class OrchestrationIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.fixture = make_fixture(Path(self.temp.name))
        self.work = Path(self.temp.name) / "w"

    def tearDown(self):
        self.temp.cleanup()

    def test_real_stages_publish_bundle_with_known_values_and_zero(self):
        first_request = self.fixture.first_request()
        first = run(first_request, self.fixture.s3, self.work)
        self._assert_complete(first, first_request, [(1, "alpha")], rows=1,
                              zero_rows=1, null_rows=0)

        second_request = self.fixture.current_request_after()
        second = run(second_request, self.fixture.s3, self.work)
        self._assert_complete(second, second_request,
                              [(1, "alpha"), (2, "beta"), (3, "gamma")],
                              rows=3, zero_rows=1, null_rows=1)

        # A completed run can be resumed by re-verifying checkpoints without
        # invoking any stage again.
        resumed = run(second_request, self.fixture.s3, self.work, resume=True)
        self.assertEqual(resumed["status"], "COMPLETE")
        changed = copy.deepcopy(second_request)
        changed["targets"] = {"dependents": dict(changed["targets"]["dependents"], sha256="0" * 64)}
        with self.assertRaises(ValueError):
            run(changed, self.fixture.s3, self.work)

    def _assert_complete(self, result, request, expected_mapping, *, rows, zero_rows, null_rows):
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(set(result["stages"]), {
            "snapshot", "package_version", "downloads", "repository",
            "package_snapshot", "dependents",
        })
        self.assertFalse(result["db_loaded"])
        dependents = result["stages"]["dependents"]
        self.assertEqual(dependents["quality"]["calculation_status"], "COMPLETE")
        self.assertEqual(dependents["quality"]["rows"], rows)
        self.assertEqual(dependents["quality"]["zero_rows"], zero_rows)
        self.assertEqual(dependents["quality"]["null_rows"], null_rows)
        self.assertTrue(any(record["bytes"] > 0 for record in dependents["files"]))
        mapping = next(record for record in result["stages"]["package_version"]["files"]
                       if "/package_ids/data/" in record["key"])
        mapping_path = Path(self.temp.name) / (request["run_id"] + "-mapping.parquet")
        mapping_path.write_bytes(self.fixture.s3.objects[(BUCKET, mapping["key"])])
        with duckdb.connect() as con:
            self.assertEqual(con.execute("SELECT * FROM read_parquet(?) ORDER BY package_id",
                                         [str(mapping_path)]).fetchall(), expected_mapping)
        bundle_prefix = f"{PREFIX}/snapshot={request['snapshot']}/run_id={request['run_id']}"
        self.assertIn((BUCKET, bundle_prefix + "/_SUCCESS"), self.fixture.s3.objects)
        self.assertEqual(status(request, self.fixture.s3)["status"], "COMPLETE")

    def test_failpoint_before_first_stage_leaves_no_bundle(self):
        seen = []

        def fail_once(point):
            seen.append(point)
            if point == "before_stage:snapshot":
                raise RuntimeError("fixture failpoint")

        with self.assertRaisesRegex(RuntimeError, "fixture failpoint"):
            run(self.fixture.request, self.fixture.s3, self.work, failpoint=fail_once)
        prefix = f"{PREFIX}/snapshot={self.fixture.snapshot}/run_id={self.fixture.request['run_id']}"
        self.assertNotIn((BUCKET, prefix + "/_SUCCESS"), self.fixture.s3.objects)
        self.assertIn("before_stage:snapshot", seen)


if __name__ == "__main__":
    unittest.main()
