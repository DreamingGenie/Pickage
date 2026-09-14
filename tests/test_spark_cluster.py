import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.spark_experiment.cluster import build_cluster_bundle


class ClusterBundleTests(unittest.TestCase):
    def test_bundle_copies_inputs_hashes_sources_and_generates_safe_launcher(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source_root = root / "source"
            source_root.mkdir()
            raw = source_root / "downloads" / "2026-08-31" / "part.parquet"
            raw.parent.mkdir(parents=True)
            raw.write_bytes(b"frozen")
            pipeline_root = source_root / "pipeline"
            pipeline_root.mkdir()
            (pipeline_root / "main.py").write_text("print('ok')\n", encoding="utf-8")
            (pipeline_root / "worker.cjs").write_text("console.log('ok')\n", encoding="utf-8")
            (pipeline_root / "node_modules").mkdir()
            (pipeline_root / "node_modules" / "ignored.cjs").write_text("bad", encoding="utf-8")
            (source_root / "unrelated.py").write_text("bad\n", encoding="utf-8")
            digest = hashlib.sha256(raw.read_bytes()).hexdigest()
            manifest_path = root / "experiment.json"
            manifest_path.write_text(json.dumps({
                "input_files": [{"path": str(raw), "bytes": raw.stat().st_size, "sha256": digest}],
                "source_request": {},
                "stages": {"package_version": {"versions": [str(raw)]}},
            }), encoding="utf-8")
            with patch("pipeline.spark_experiment.cluster.ROOT", source_root), patch("pipeline.spark_experiment.cluster.verify_inputs"):
                bundle = build_cluster_bundle(manifest_path, root / "bundles")
            cluster_manifest = json.loads((bundle / "cluster_manifest.json").read_text(encoding="utf-8"))
            record = cluster_manifest["input_files"][0]
            self.assertTrue(record["path"].startswith("s3a://pickage-curated/experiments/cluster-"))
            self.assertEqual(record["relative_path"], "source/downloads/2026-08-31/part.parquet")
            self.assertTrue((bundle / "inputs" / "source" / "downloads" / "2026-08-31" / "part.parquet").is_file())
            self.assertTrue((bundle / "code" / "pipeline" / "main.py").is_file())
            self.assertTrue((bundle / "code" / "pipeline" / "worker.cjs").is_file())
            self.assertFalse((bundle / "code" / "pipeline" / "node_modules" / "ignored.cjs").exists())
            self.assertFalse((bundle / "code" / "unrelated.py").exists())
            launcher = (bundle / "launch_cluster.sh").read_text(encoding="utf-8")
            self.assertIn("--deploy-mode client", launcher)
            self.assertIn("SPARK_MASTER", launcher)
            self.assertIn("NODE_RUNTIME_ROOT", launcher)
            self.assertIn("mc cp --recursive", launcher)
            self.assertIn("spark.executorEnv.PYTHONPATH", launcher)
            self.assertIn("--driver-memory", launcher)
            self.assertIn("--total-executor-cores", launcher)
            self.assertNotIn("_SUCCESS", cluster_manifest)

    def test_input_outside_manifest_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest_root = root / "manifest-root"
            manifest_root.mkdir()
            outside = root / "outside.parquet"
            outside.write_bytes(b"x")
            manifest = manifest_root / "manifest.json"
            manifest.write_text(json.dumps({
                "input_files": [{"path": str(outside), "bytes": 1,
                                  "sha256": hashlib.sha256(b"x").hexdigest()}],
            }), encoding="utf-8")
            with patch("pipeline.spark_experiment.cluster.verify_inputs"):
                with self.assertRaises(ValueError):
                    build_cluster_bundle(manifest, root / "bundles")


if __name__ == "__main__":
    unittest.main()
