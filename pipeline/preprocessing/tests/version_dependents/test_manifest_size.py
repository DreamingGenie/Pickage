import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pipeline.preprocessing.version_dependents import historical_artifact


class ManifestSizeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="manifest-size-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "manifest.json"

    def test_sharded_name_metadata_above_legacy_limit_is_accepted(self):
        names = [f"package-{index:06d}-{'x' * 40}" for index in range(100_000)]
        self.path.write_text(json.dumps({"names": names}), encoding="utf-8")
        self.assertGreater(self.path.stat().st_size, 4 * 1024 * 1024)
        self.assertLessEqual(self.path.stat().st_size, historical_artifact._MAX_JSON_BYTES)

        manifest = historical_artifact._read_json(self.path)

        self.assertEqual(len(manifest["names"]), 100_000)

    def test_manifest_above_16_mib_is_rejected(self):
        self.path.write_bytes(b" " * (historical_artifact._MAX_JSON_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "Oversized manifest.*16 MiB"):
            historical_artifact._read_json(self.path)

    def test_missing_manifest_has_distinct_error(self):
        with self.assertRaisesRegex(ValueError, "Missing or unsafe manifest"):
            historical_artifact._read_json(self.path)

    def test_reparse_manifest_has_distinct_error(self):
        self.path.write_text("{}", encoding="utf-8")
        with patch.object(historical_artifact, "_reparse", return_value=True):
            with self.assertRaisesRegex(ValueError, "Missing or unsafe manifest"):
                historical_artifact._read_json(self.path)


if __name__ == "__main__":
    unittest.main()
