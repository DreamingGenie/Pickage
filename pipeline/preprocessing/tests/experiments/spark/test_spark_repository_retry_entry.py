import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from pipeline.preprocessing.experiments.spark.runtime import repository_retry_entry as entry
from pipeline.preprocessing.experiments.spark.runtime.repository_retry_entry import build_stage_manifest, fresh_control, repository_code_sha256, verify_heap, verify_pinned_manifest, wait_for_start


class RepositoryRetryEntryTests(unittest.TestCase):
    def test_constructs_repository_only_fixed_stage_with_pinned_lineage(self):
        original = {
            "format_version": 1,
            "snapshot": "2026-08-31",
            "files": {"package": ["/experiment/reference/package.parquet"]},
            "file_records": [{"path": "/experiment/reference/package.parquet",
                              "bytes": 5, "sha256": "a" * 64, "rows": 7}],
        }
        fixed = build_stage_manifest(original, manifest_sha256="b" * 64,
                                     previous_code_sha256="c" * 64,
                                     current_code_sha256="c" * 64)
        self.assertEqual(set(fixed["stages"]), {"repository"})
        self.assertEqual(fixed["stages"]["repository"], original)
        self.assertEqual(fixed["input_files"], [{"path": "/experiment/reference/package.parquet",
                                                   "bytes": 5, "sha256": "a" * 64}])
        self.assertEqual(fixed["source_request"]["input_manifest_sha256"], "b" * 64)

    def test_rejects_source_contract_or_pinned_manifest_mismatch(self):
        with self.assertRaisesRegex(ValueError, "source contract"):
            build_stage_manifest({"format_version": 1, "file_records": [{}]},
                                 manifest_sha256="a" * 64,
                                 previous_code_sha256="b" * 64,
                                 current_code_sha256="c" * 64)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            path.write_text('{"format_version":1}')
            with self.assertRaisesRegex(ValueError, "SHA256"):
                verify_pinned_manifest(path, "0" * 64)

    def test_pinned_manifest_and_repository_contract_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            raw = b'{"format_version":1}\n'
            path.write_bytes(raw)
            manifest, digest = verify_pinned_manifest(path, hashlib.sha256(raw).hexdigest())
            self.assertEqual(manifest["format_version"], 1)
            self.assertEqual(digest, hashlib.sha256(raw).hexdigest())

            root = Path(directory) / "repo"
            (root / "pipeline/preprocessing/repository_metrics").mkdir(parents=True)
            (root / "pipeline/preprocessing/repository_metrics/build.py").write_bytes(b"build")
            for name in ("pipeline/preprocessing/curated/repository.py", "pipeline/preprocessing/curated/storage.py",
                         "pipeline/preprocessing/curated/build.py", "pipeline/minio/ingest_raw.py",
                         "pipeline/postgresql/input.py", "pipeline/preprocessing/common/curated_input.py", "pipeline/preprocessing/snapshot/policy.py",
                         "pipeline/preprocessing/snapshot/projects.py", "pipeline/preprocessing/snapshot/input.py",
                         "pipeline/preprocessing/snapshot/build.py"):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(name.encode())
            first = repository_code_sha256(root)
            (root / "pipeline/preprocessing/repository_metrics/build.py").write_bytes(b"changed")
            self.assertNotEqual(first, repository_code_sha256(root))

    def test_gate_requires_start_signal_and_fresh_supervisor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "supervisor-heartbeat.json").write_text(json.dumps({"time": 100.0}))
            self.assertTrue(fresh_control(root, now=110.0))
            self.assertFalse(fresh_control(root, now=130.0))
            with self.assertRaisesRegex(RuntimeError, "monitors"):
                wait_for_start(root, timeout=0, interval=0)
            (root / "start.signal").touch()
            with self.assertRaisesRegex(RuntimeError, "not fresh"):
                wait_for_start(root, timeout=0, interval=0)

    def test_heap_probe_fails_closed_when_below_four_gib(self):
        verify_heap(4 * 1024**3, 4 * 1024**3)
        with self.assertRaisesRegex(RuntimeError, "below requested heap"):
            verify_heap(3 * 1024**3, 4 * 1024**3)

    def test_main_reverifies_inputs_and_writes_fixed_manifest_once_before_job(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "input-manifest.json"
            original = {"format_version": 1, "snapshot": "2026-08-31",
                        "file_records": [{"path": "/experiment/reference/p.parquet",
                                          "bytes": 5, "sha256": "a" * 64, "rows": 7}]}
            manifest_path.write_text(json.dumps(original))
            output, telemetry, fixed = root / "out", root / "telemetry", root / "fixed.json"
            probe_stdout = "HEAP_PROBE_JSON:{\"max_memory\":4294967296}\n"
            fake_thread = unittest.mock.Mock()
            fake_job = unittest.mock.Mock(return_value=0)
            with (patch.object(entry, "wait_for_start"),
                  patch.object(entry.threading, "Thread", return_value=fake_thread),
                  patch.object(entry, "INPUT_MANIFEST", manifest_path),
                  patch.object(entry, "INPUT_MANIFEST_SHA256", hashlib.sha256(manifest_path.read_bytes()).hexdigest()),
                  patch.object(entry, "PREVIOUS_CODE", root / "previous"),
                  patch.object(entry, "CURRENT_CODE", root / "current"),
                  patch.object(entry, "OUTPUT", output),
                  patch.object(entry, "TELEMETRY", telemetry),
                  patch.object(entry, "FIXED_MANIFEST", fixed),
                  patch.object(entry, "repository_code_sha256", return_value=entry.EXPECTED_REPOSITORY_CODE_SHA256),
                  patch("pipeline.preprocessing.repository_metrics.input.reverify_inputs") as reverify,
                  patch.object(entry.subprocess, "run",
                               return_value=subprocess.CompletedProcess([], 0, probe_stdout, "")) as probe,
                  patch("pipeline.preprocessing.experiments.spark.job.main", fake_job)):
                self.assertEqual(entry.main(), 0)
            fake_thread.start.assert_called_once()
            reverify.assert_called_once_with(original)
            probe.assert_called_once()
            saved = json.loads(fixed.read_text())
            self.assertEqual(set(saved["stages"]), {"repository"})
            self.assertEqual(fake_job.call_args.args[0][-2], "--telemetry-dir")
            self.assertEqual(fake_job.call_args.args[0][-1], str(telemetry))


if __name__ == "__main__":
    unittest.main()
