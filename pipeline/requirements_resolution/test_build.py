from pathlib import Path
import json
import hashlib
import tempfile
import unittest
from unittest.mock import patch

import duckdb

from pipeline.requirements_resolution import build
from pipeline.requirements_resolution.policy import make_policy
from pipeline.requirements_resolution.test_support import Fixture


POLICY = make_policy(kinds=["dependencies"], unknown_published_at="include", unresolved="partial", decision_reference="TEST-07")
RUNTIME_META = {"node_version": "test", "semver_version": "1", "package_arg_version": "1", "semver_sha256": "a"*64, "package_arg_sha256": "b"*64, "dependency_closure_sha256": "c"*64, "options": {"loose": False, "includePrerelease": False}, "equal_precedence_tie": "original_version_utf16_ascending"}


def _mock_stage(stage, inputs, policy, stage_dir, **kwargs):
    stage_dir = Path(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=False)
    outputs = stage_dir / "outputs"
    for group in ("declaration_outcomes", "source_outcomes", "edges", "target_quality"):
        outputs.joinpath(group).mkdir(parents=True)
    with duckdb.connect() as con:
        for group in ("declaration_outcomes", "source_outcomes", "edges", "target_quality"):
            con.execute("CREATE TABLE result(value VARCHAR)")
            if group in ("source_outcomes", "target_quality"):
                con.execute("INSERT INTO result VALUES ('fixture')")
            con.execute("COPY result TO ? (FORMAT PARQUET)", [str(outputs / group / "part-0.parquet")])
            con.execute("DROP TABLE result")
    return {"resolution_status": "PARTIAL", "ready_for_dependents": False,
            "selected_declarations": 0, "resolved_declarations": 0, "unresolved_declarations": 0,
            "source_status_counts": {"DEPENDENCY_EXTRACTION_ERROR": 1}, "declaration_status_counts": {},
            "output_counts": {"declaration_outcomes": 0, "source_outcomes": 1, "edges": 0, "target_quality": 1}}


def _ready_stage(stage, inputs, policy, stage_dir, **kwargs):
    result = _mock_stage(stage, inputs, policy, stage_dir, **kwargs)
    return {**result, "resolution_status": "COMPLETE", "ready_for_dependents": True,
            "source_status_counts": {"OBSERVED_NO_DEPENDENCIES": 1}}


class BuildLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.fixture = Fixture()
        self.work_temp = tempfile.TemporaryDirectory()
        self.work = Path(self.work_temp.name) / "runs"
        self.runtime = {"node": "missing-node", "semver_module": "missing-semver", "package_arg_module": "missing-arg"}

    def tearDown(self):
        self.work_temp.cleanup()
        self.fixture.close()

    def _run(self, **kwargs):
        args = self.fixture.arguments()
        args.pop("output", None)
        args.update({"run_id": "run-1", "work_dir": self.work, "policy": POLICY, "runtime": self.runtime})
        args.update(kwargs)
        return build.run(self.fixture.s3, **args)

    @patch.object(build, "_runtime_metadata", return_value=RUNTIME_META)
    @patch.object(build.bridge_module, "resolve_prepared", return_value={"lookups": 0, "runtime": RUNTIME_META})
    @patch.object(build.runtime_module, "run_stage", side_effect=_mock_stage)
    def test_success_marker_and_replay_are_immutable(self, stage, bridge, metadata):
        manifest = self._run()
        root = self.work / "run-1"
        self.assertTrue((root / "_SUCCESS").is_file())
        before = (root / "run_manifest.json").read_bytes()
        replay = self._run()
        self.assertTrue(replay["reverified"])
        self.assertEqual(before, (root / "run_manifest.json").read_bytes())
        self.assertEqual(stage.call_count, 2)

    @patch.object(build, "_runtime_metadata", return_value=RUNTIME_META)
    @patch.object(build.bridge_module, "resolve_prepared", return_value={"lookups": 0, "runtime": RUNTIME_META})
    @patch.object(build.runtime_module, "run_stage", side_effect=_mock_stage)
    def test_verify_only_requires_completed_run(self, stage, bridge, metadata):
        with self.assertRaises(ValueError):
            self._run(verify_only=True)

    @patch.object(build, "_runtime_metadata", return_value=RUNTIME_META)
    @patch.object(build.bridge_module, "resolve_prepared", return_value={"lookups": 0, "runtime": RUNTIME_META})
    @patch.object(build.runtime_module, "run_stage", side_effect=_mock_stage)
    def test_manifest_only_local_completion_marker_is_recovered(self, stage, bridge, metadata):
        self._run()
        marker = self.work / "run-1" / "_SUCCESS"
        marker.unlink()
        result = self._run()
        self.assertTrue(result["reverified"])
        self.assertTrue(marker.is_file())

    @patch.object(build, "_runtime_metadata", return_value=RUNTIME_META)
    @patch.object(build.bridge_module, "resolve_prepared", return_value={"lookups": 0, "runtime": RUNTIME_META})
    @patch.object(build.runtime_module, "run_stage", side_effect=_ready_stage)
    def test_manifest_only_remote_publish_marker_is_resumed(self, stage, bridge, metadata):
        self.fixture.s3.delete_object = lambda Bucket, Key, IfMatch=None: self.fixture.s3.objects.pop((Bucket, Key), None)
        self._run(publish=True)
        remote_marker = (build.BUCKET, "depsdev/v1/requirements-resolution/snapshot=2026-08-31/run_id=run-1/_SUCCESS")
        self.fixture.s3.objects.pop(remote_marker)
        result = self._run(publish=True)
        self.assertTrue(result["reverified"])
        self.assertIn(remote_marker, self.fixture.s3.objects)

    @patch.object(build, "_runtime_metadata", return_value=RUNTIME_META)
    @patch.object(build.bridge_module, "resolve_prepared", return_value={"lookups": 0, "runtime": RUNTIME_META})
    @patch.object(build.runtime_module, "run_stage", side_effect=_mock_stage)
    def test_completed_output_tamper_is_rejected(self, stage, bridge, metadata):
        self._run()
        output = next((self.work / "run-1").rglob("*.parquet"))
        output.write_bytes(output.read_bytes() + b"x")
        with self.assertRaises(ValueError):
            self._run()

    def test_invalid_run_id_and_input_overlap_fail(self):
        with self.assertRaises(ValueError):
            self._run(run_id="bad/id")
        args = self.fixture.arguments()
        args.pop("output", None)
        args.update(run_id="run-1", work_dir=self.fixture.curated, policy=POLICY, runtime=self.runtime)
        with self.assertRaises(ValueError):
            build.run(self.fixture.s3, **args)

    @patch.object(build, "_runtime_metadata", return_value=RUNTIME_META)
    @patch.object(build.bridge_module, "resolve_prepared", return_value={"lookups": 0, "runtime": RUNTIME_META})
    @patch.object(build.runtime_module, "run_stage", side_effect=_mock_stage)
    def test_partial_result_is_not_published(self, stage, bridge, metadata):
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self._run(publish=True)
        self.assertFalse(any(key[0] == build.BUCKET and "requirements-resolution" in key[1] for key in self.fixture.s3.objects))

    @patch.object(build, "_runtime_metadata", return_value=RUNTIME_META)
    @patch.object(build.bridge_module, "resolve_prepared", return_value={"lookups": 0, "runtime": RUNTIME_META})
    @patch.object(build.runtime_module, "run_stage", side_effect=_ready_stage)
    def test_ready_result_publishes_and_republishes_identically(self, stage, bridge, metadata):
        self.fixture.s3.delete_object = lambda Bucket, Key, IfMatch=None: self.fixture.s3.objects.pop((Bucket, Key), None)
        self._run(publish=True)
        before = dict(self.fixture.s3.objects)
        replay = self._run(publish=True)
        self.assertTrue(replay["reverified"])
        self.assertEqual(before, self.fixture.s3.objects)
        prefix = build.PREFIX + "/snapshot=2026-08-31/run_id=run-1"
        receipt_body = self.fixture.s3.objects[(build.BUCKET, prefix + "/run_manifest.json")][0]
        receipt = json.loads(receipt_body)
        self.assertEqual(receipt["final_output"], "data")
        self.assertEqual(len(receipt["files"]), 4)
        self.assertNotIn(str(self.fixture.root), receipt_body.decode())
        self.assertNotIn(str(self.work), receipt_body.decode())
        for record in receipt["files"]:
            body = self.fixture.s3.objects[(build.BUCKET, prefix + "/data/" + record["path"])][0]
            self.assertEqual(hashlib.sha256(body).hexdigest(), record["sha256"])

    @patch.object(build, "_runtime_metadata", return_value=RUNTIME_META)
    def test_lock_already_held_fails(self, metadata):
        self.work.mkdir(parents=True)
        lock = self.work / ".run-1.lock"
        lock.write_text("held", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            self._run()

    def test_linked_run_root_rejected_before_runtime(self):
        target = self.work / "run-1"
        with patch.object(Path, "is_junction", lambda item: item == target, create=True):
            with self.assertRaisesRegex(ValueError, "linked"):
                self._run()

    def test_final_output_traversal_and_inconsistent_report_fail(self):
        for relative in ("../outside", "a/../outside", "C:/outside", "a\\outside"):
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                build._safe_output(self.work, relative)
        stage = self.work / "stage"
        report = _ready_stage("finalize", {}, POLICY, stage)
        for change in ({"output_counts": {"edges": 0}}, {"resolution_status": "PARTIAL"},
                       {"selected_declarations": 1}, {"source_status_counts": {"DEPENDENCY_EXTRACTION_ERROR": 1}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                build._verify_stage_counts(stage / "outputs", {**report, **change})
        for path in (stage / "outputs/edges").glob("*.parquet"):
            path.unlink()
        with self.assertRaisesRegex(ValueError, "no Parquet"):
            build._verify_stage_counts(stage / "outputs", report)

    def test_long_windows_output_file_can_be_hashed_and_counted(self):
        directory = self.work / ("long-" + "x" * 95) / "declaration_outcomes"
        directory.mkdir(parents=True)
        path = directory / ("part-" + "y" * 80 + ".parquet")
        with duckdb.connect() as con:
            con.execute("COPY (SELECT 1 AS value) TO ? (FORMAT PARQUET)", [str(build._io_path(path))])
        try:
            records = build._output_inventory(directory.parent)
            self.assertEqual(records[0]["rows"], 1)
            build._verify_inventory(directory.parent, records)
        finally:
            build._io_path(path).unlink()


if __name__ == "__main__":
    unittest.main()
