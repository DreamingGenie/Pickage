import json
import tempfile
import unittest
from pathlib import Path

from pipeline.spark_experiment.runtime.real_stage_inputs import assemble, verify


class RealStageInputsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.artifacts = self.root / "artifacts"
        self.artifacts.mkdir()
        self.files = {}
        for name in ("package", "version", "downloads", "metric", "selection",
                     "versions_full", "requirements", "targets", "candidate"):
            path = self.artifacts / (name + ".parquet")
            path.write_bytes(("source:" + name).encode())
            self.files[name] = str(path)
        self.output = self.root / "prepared" / "experiment.json"
        self.package_version = {"versions": [self.files["versions_full"]],
                                "requirements": [self.files["requirements"]],
                                "previous_ids": None, "snapshot": "2026-08-31"}
        self.downloads = {
            "package_files": [self.files["package"]], "daily_files": [],
            "target_file": self.files["targets"], "status_file": self.files["candidate"],
            "interval": {"snapshot_at": "2026-08-31"},
            "lineage": {"input_manifest_sha256": "1" * 64},
        }
        self.repository = {
            "snapshot": "2026-08-31", "snapshot_timestamp": "2026-08-31T21:01:10.517131Z",
            "files": {"package": [self.files["package"]], "version": [self.files["version"]],
                      "versions_full": [self.files["versions_full"]], "projects": [self.files["candidate"]]},
            "counts": {"package": 1, "version": 1, "versions_full": 1, "projects": 1},
        }

    def tearDown(self):
        self.temp.cleanup()

    def build(self):
        return assemble(
            source_request={"snapshot": "2026-08-31",
                            "snapshot_timestamp": "2026-08-31T21:01:10.517131Z"},
            source_manifests={"package_version": "a" * 64, "downloads": "b" * 64,
                              "repository_retry": "c" * 64, "raw": "d" * 64},
            package_version=self.package_version, downloads=self.downloads,
            repository=self.repository,
            outputs={"package": [self.files["package"]], "version": [self.files["version"]],
                     "downloads": self.files["downloads"],
                     "repository_metric": [self.files["metric"]],
                     "repository_selection": [self.files["selection"]]},
            population_rows=1,
            raw_inputs={"versions_full": [self.files["versions_full"]],
                        "requirements": [self.files["requirements"]], "targets": [self.files["targets"]]},
            artifact_roots=[self.artifacts], output_manifest=self.output,
            code_identity={"sha256": "e" * 64},
        )

    def test_assembles_five_stage_job_inputs_and_pins_every_file(self):
        result = self.build()
        manifest = verify(result)
        self.assertEqual(set(manifest["stages"]), {
            "package_version", "downloads", "repository", "package_snapshot", "dependents"})
        self.assertEqual(manifest["stages"]["package_snapshot"]["population_rows"], 1)
        self.assertEqual(manifest["stages"]["dependents"]["files"]["targets"], self.files["targets"])
        self.assertEqual(manifest["adapter"]["kind"], "ASSEMBLED_FROM_COMPLETED_ARTIFACTS")
        self.assertFalse(manifest["adapter"]["official_publication_manifest"])
        self.assertFalse(manifest["adapter"]["stage_execution_performed"])
        self.assertEqual(len(manifest["input_files"]), len(self.files))

    def test_refuses_changed_source_after_manifest_creation(self):
        result = self.build()
        Path(self.files["downloads"]).write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "frozen experiment input changed"):
            verify(result)

    def test_nested_path_inputs_round_trip_and_remap_to_shared_storage(self):
        from pipeline.spark_experiment.runtime.benchmark_data_phase import remap
        self.downloads['daily_files'] = [Path(self.files['downloads'])]
        self.package_version['versions'] = (Path(self.files['versions_full']),)
        self.repository['files']['projects'] = [Path(self.files['candidate'])]
        manifest = verify(self.build())
        mapping = {row['path']: 's3a://pickage-curated/experiments/test/' + row['sha256']
                   for row in manifest['input_files']}
        shared = remap(manifest, mapping)
        self.assertEqual(manifest['stages']['downloads']['daily_files'], [self.files['downloads']])
        self.assertEqual(shared['stages']['downloads']['daily_files'], [mapping[self.files['downloads']]])
        self.assertEqual(shared['stages']['repository']['files']['projects'], [mapping[self.files['candidate']]])
        self.assertIsInstance(self.downloads['daily_files'][0], Path)

    def test_unsupported_value_does_not_leave_partial_manifest(self):
        self.downloads['unsupported'] = object()
        with self.assertRaises(TypeError):
            self.build()
        self.assertFalse(self.output.exists())

    def test_refuses_file_outside_approved_artifact_roots(self):
        outside = self.root / "outside.parquet"
        outside.write_bytes(b"outside")
        self.package_version["versions"] = [str(outside)]
        with self.assertRaisesRegex(ValueError, "outside approved artifact roots"):
            self.build()

    def test_refuses_unpinned_or_incomplete_stage_source(self):
        self.repository["snapshot"] = "2026-08-24"
        with self.assertRaisesRegex(ValueError, "repository input identity"):
            self.build()

    def test_output_is_immutable(self):
        self.build()
        with self.assertRaises(FileExistsError):
            self.build()

    def test_refuses_manifest_identity_tampering(self):
        result = self.build()
        manifest = json.loads(result.read_text(encoding="utf-8"))
        manifest["source_request"]["snapshot"] = "2026-08-24"
        result.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "input identity is inconsistent"):
            verify(result)


if __name__ == "__main__":
    unittest.main()
