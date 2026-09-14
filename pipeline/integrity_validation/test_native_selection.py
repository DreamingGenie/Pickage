import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from pipeline.curated.storage import json_bytes
from pipeline.integrity_validation.native_fixture import create_demo
from pipeline.integrity_validation.native_selection import select_metadata


class _Store:
    def __init__(self, root, request):
        self.objects = {}
        for key, relative in request["objects"].items():
            self.objects[key] = (root / relative).read_bytes()

    def get_object(self, *, Bucket, Key):
        if Key not in self.objects:
            raise KeyError(Key)
        return {"Body": io.BytesIO(self.objects[Key])}


class NativeSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "bundle"
        create_demo(self.root)
        self.request = json.loads((self.root / "request.json").read_bytes())
        self.store = _Store(self.root, self.request)

    def tearDown(self):
        self.temp.cleanup()

    def select(self, request=None):
        return select_metadata(request or self.request, self.store)

    def repin_manifest(self, manifest, *, dataset="package-version"):
        """Replace the in-memory management objects and caller pin together."""
        body = json_bytes(manifest)
        digest = hashlib.sha256(body).hexdigest()
        prefix_dataset = "package-version" if dataset == "package-version" else "package-snapshot"
        prefix = f"depsdev/v1/{prefix_dataset}/snapshot=2026-08-31/run_id=tiny-native-demo"
        self.store.objects[prefix + "/run_manifest.json"] = body
        if dataset == "package-version":
            self.store.objects[prefix + "/_SUCCESS"] = json_bytes({"manifest_sha256": digest})
        else:
            self.store.objects[prefix + "/_SUCCESS"] = (digest + "\n").encode()
            self.store.objects[prefix + "/_INPUT.json"] = json_bytes({"manifest_sha256": digest})
        request = copy.deepcopy(self.request)
        request["manifest_sha256"] = digest
        return request

    def test_selects_pinned_package_version_metadata_without_reading_samples(self):
        result = self.select()
        self.assertEqual(result["native_selector"], "pipeline.postgresql.input.select_run")
        self.assertEqual(result["metadata"]["counts"], {"package": 2, "version": 2})
        self.assertEqual({row["role"] for row in result["records"]}, {"package", "version"})

    def test_creates_observed_snapshot_bundle_with_service_identity_samples(self):
        root = Path(self.temp.name) / "observed"
        create_demo(root, "package-snapshot-observed")
        request = json.loads((root / "request.json").read_bytes())
        result = select_metadata(request, _Store(root, request))
        self.assertEqual(result["native_selector"], "pipeline.package_snapshot.load.select_run")
        self.assertEqual([row["role"] for row in result["records"]], ["package_snapshot", "package_identity", "quality"])
        self.assertEqual({sample["key"].split("/")[-1] for sample in request["samples"]}, {"package_snapshot.parquet", "package_identity.parquet"})

    def test_rejects_wrong_run_pin(self):
        request = copy.deepcopy(self.request)
        request["run_id"] = "other-run"
        with self.assertRaisesRegex(ValueError, "native manifest|missing|mismatch|objects"):
            self.select(request)

    def test_rejects_wrong_snapshot_timestamp_microseconds(self):
        request = copy.deepcopy(self.request)
        request["snapshot_timestamp"] = "2026-08-31T12:34:56.123457Z"
        with self.assertRaisesRegex(ValueError, "timestamp"):
            self.select(request)

    def test_rejects_manifest_pin_after_manifest_mutation(self):
        request = copy.deepcopy(self.request)
        manifest = json.loads((self.root / "run_manifest.json").read_bytes())
        manifest["synthetic_demo"] = "mutated"
        body = json_bytes(manifest)
        manifest_key = "depsdev/v1/package-version/snapshot=2026-08-31/run_id=tiny-native-demo/run_manifest.json"
        success_key = "depsdev/v1/package-version/snapshot=2026-08-31/run_id=tiny-native-demo/_SUCCESS"
        self.store.objects[manifest_key] = body
        self.store.objects[success_key] = json_bytes({"manifest_sha256": hashlib.sha256(body).hexdigest()})
        with self.assertRaisesRegex(ValueError, "pin"):
            self.select(request)

    def test_rejects_expected_count_type_mismatch(self):
        request = copy.deepcopy(self.request)
        request["expected_counts"]["package"] = "2"
        with self.assertRaisesRegex(ValueError, "expected count"):
            self.select(request)

    def test_rejects_missing_completion_marker(self):
        request = copy.deepcopy(self.request)
        self.store.objects.pop("depsdev/v1/package-version/snapshot=2026-08-31/run_id=tiny-native-demo/_SUCCESS")
        with self.assertRaisesRegex(ValueError, "missing|Required object|malformed"):
            self.select(request)

    def test_rejects_unknown_request_field(self):
        request = copy.deepcopy(self.request)
        request["unexpected"] = True
        with self.assertRaisesRegex(ValueError, "keys invalid"):
            self.select(request)

    def test_rejects_native_manifest_that_is_not_passed_even_when_re_pinned(self):
        manifest = json.loads((self.root / "run_manifest.json").read_bytes())
        manifest["status"] = "FAILED"
        request = self.repin_manifest(manifest)
        with self.assertRaisesRegex(ValueError, "Unapproved Curated manifest"):
            self.select(request)

    def test_rejects_historical_fields_in_observed_bundle_after_repinning(self):
        root = Path(self.temp.name) / "historical"
        create_demo(root, "package-snapshot-observed")
        request = json.loads((root / "request.json").read_bytes())
        store = _Store(root, request)
        manifest = json.loads((root / "run_manifest.json").read_bytes())
        manifest["history_policy"] = "historical-v1"
        body = json_bytes(manifest)
        digest = hashlib.sha256(body).hexdigest()
        prefix = "depsdev/v1/package-snapshot/snapshot=2026-08-31/run_id=tiny-native-demo"
        store.objects[prefix + "/run_manifest.json"] = body
        store.objects[prefix + "/_SUCCESS"] = (digest + "\n").encode()
        store.objects[prefix + "/_INPUT.json"] = json_bytes({"manifest_sha256": digest})
        request["manifest_sha256"] = digest
        with self.assertRaisesRegex(ValueError, "historical"):
            select_metadata(request, store)

    def test_rejects_observed_shards_when_role_row_counts_sum_past_total(self):
        root = Path(self.temp.name) / "shards"
        create_demo(root, "package-snapshot-observed")
        request = json.loads((root / "request.json").read_bytes())
        store = _Store(root, request)
        manifest = json.loads((root / "run_manifest.json").read_bytes())
        duplicate = copy.deepcopy(next(row for row in manifest["files"] if row["role"] == "package_snapshot"))
        duplicate["path"] = "package_snapshot-1.parquet"
        manifest["files"].append(duplicate)
        body = json_bytes(manifest)
        digest = hashlib.sha256(body).hexdigest()
        prefix = "depsdev/v1/package-snapshot/snapshot=2026-08-31/run_id=tiny-native-demo"
        store.objects[prefix + "/run_manifest.json"] = body
        store.objects[prefix + "/_SUCCESS"] = (digest + "\n").encode()
        store.objects[prefix + "/_INPUT.json"] = json_bytes({"manifest_sha256": digest})
        request["manifest_sha256"] = digest
        with self.assertRaisesRegex(ValueError, "row_count sum"):
            select_metadata(request, store)

    def test_rejects_unsupported_explicit_dataset(self):
        request = copy.deepcopy(self.request)
        request["dataset"] = "package-snapshot-history"
        with self.assertRaisesRegex(ValueError, "unsupported native dataset"):
            self.select(request)

    def test_rejects_boolean_expected_count(self):
        request = copy.deepcopy(self.request)
        request["expected_counts"]["package"] = True
        with self.assertRaisesRegex(ValueError, "invalid expected count"):
            self.select(request)

    def test_fixture_refuses_overwrite_and_cli_metadata_are_local(self):
        with self.assertRaises(FileExistsError):
            create_demo(self.root)
        self.assertEqual(hashlib.sha256((self.root / "run_manifest.json").read_bytes()).hexdigest(), self.request["manifest_sha256"])


if __name__ == "__main__":
    unittest.main()
