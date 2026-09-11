"""Real-schema synthetic H1 to H5 profile integration and provenance tests."""
import json
from pathlib import Path
import tempfile
import unittest

import duckdb

from .historical_profile import build_profile
from .historical_job import supervise
from pipeline.requirements_resolution.input import file_sha256
from pipeline.requirements_resolution.policy import canonical_bytes


class HistoricalProfileTests(unittest.TestCase):
    def setUp(self):
        from .test_historical_artifact import HistoricalArtifactTests
        self.h1 = HistoricalArtifactTests()
        self.h1.setUp()
        self.addCleanup(self.h1.doCleanups)
        self.prepared = self.h1.build()
        self.temp = tempfile.TemporaryDirectory(prefix="h5-profile-")
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "profile"

    def build(self, **kwargs):
        args = dict(input_dir=self.prepared["output"], input_manifest_sha256=self.prepared["manifest_sha256"],
                    output=self.output, threads=1, memory_limit="256MB", max_temp_size="1GB")
        args.update(kwargs)
        return build_profile(**args)

    def test_h1_profile_roundtrip_and_preserved_count_status(self):
        result = self.build()
        self.assertEqual(result["profile_status"], "COMPLETE")
        manifest = json.loads((self.output / "profile_manifest.json").read_bytes())
        self.assertEqual(manifest["count_status"], "NOT_COMPUTED")
        self.assertFalse(manifest["ready_for_load"])
        self.assertEqual(manifest["statistics"]["source_declarations"], 1)
        phases = [json.loads(line)["phase"] for line in (self.output / "progress.jsonl").read_text().splitlines()]
        self.assertLess(phases.index("GROUP_UNIQUE_REQUIREMENTS"), phases.index("GROUP_PACKAGE_CANDIDATES"))
        self.assertLess(phases.index("GROUP_PACKAGE_CANDIDATES"), phases.index("WRITE_PROFILE_OUTPUTS"))
        self.assertEqual(phases[-1], "PROFILE_COMPLETE")
        with duckdb.connect() as con:
            self.assertEqual(con.execute("SELECT declared_name,requirement,declaration_count FROM read_parquet(?)",
                                         [str(self.output / "lookup_workload.parquet")]).fetchall(), [("dep", "^2", 1)])
        with self.assertRaises(FileExistsError):
            self.build()

    def test_bad_h1_pin_rejected_before_output(self):
        with self.assertRaisesRegex(ValueError, "H1 input manifest SHA"):
            self.build(input_manifest_sha256="0" * 64)
        self.assertFalse(self.output.exists())

    def test_changed_raw_input_cannot_publish_profile(self):
        source = self.h1.root / "requirements" / "fixture.parquet"
        with source.open("ab") as stream:
            stream.write(b"changed")
        with self.assertRaisesRegex(ValueError, "Input file changed"):
            self.build()
        self.assertFalse((self.output / "profile_manifest.json").exists())

    def test_real_supervisor_runs_profile_in_separate_interpreter(self):
        job=Path(self.temp.name)/"job";job.mkdir()
        config=job/"config.json"
        config.write_bytes(canonical_bytes({"format":"historical-profile-job-v1","job_dir":str(job),
            "profile_args":{"input_dir":self.prepared["output"],"input_manifest_sha256":self.prepared["manifest_sha256"],
                            "threads":1,"memory_limit":"256MB","max_temp_size":"1GB"},
            "budget":{"max_rss_bytes":1024**3,"max_scratch_bytes":1024**3,"max_output_bytes":1024**3,
                      "min_free_disk_bytes":1024**3,"max_seconds":None,"sample_seconds":1}}))
        result=supervise(config=config,config_sha256=file_sha256(config))
        self.assertEqual(result["status"],"COMPLETE",result)
        self.assertEqual(result["count_status"],"NOT_COMPUTED")
        self.assertIsNone(result["budget"]["max_seconds"])
        self.assertFalse(result["elapsed_limit_enforced"])
        self.assertTrue((job/"job_receipt.json").is_file())
        self.assertFalse((job/"supervisor_lost.json").exists())


if __name__ == "__main__":
    unittest.main()
