import unittest
from unittest.mock import patch
import hashlib
import os
from pathlib import Path
import json

from .historical_db_publish import HistoricalCountLoader
from .test_historical_db_keys import HistoricalDbKeyValidationIntegrationTests
from pipeline.requirements_resolution.policy import sha256


def metadata():
    manifest = {
        "lineage": {"population": {"run_id": "curated-run", "manifest_sha256": "a" * 64,
                                     "snapshot": "2026-08-31", "snapshot_timestamp": "2026-08-31T21:00:00Z"},
                    "calendar": {"manifest_sha256": "b" * 64}},
        "calendar": [{"snapshot_at": "2026-08-31", "snapshot_timestamp": "2026-08-31T21:00:00Z"}],
        "quality": {"calculation_status": "COMPLETE", "resolution_status": "PARTIAL"},
    }
    return {"dataset": "version-dependents", "snapshot": "2026-08-31",
            "snapshot_timestamp": "2026-08-31T21:00:00Z", "curated_run_id": "curated-run",
            "run_prefix": "run", "manifest": manifest, "manifest_sha256": sha256(manifest),
            "counts": {"package_version_snapshot": 1, "identities": 1}}


class HistoricalCountLoaderUnitTests(unittest.TestCase):
    def test_start_rejects_manifest_hash_tampering_before_connect(self):
        loader = HistoricalCountLoader(["psql"], ".")
        with self.assertRaisesRegex(ValueError, "manifest hash"):
            loader.start(dict(metadata(), manifest_sha256="0" * 64), "run-1", "c" * 64, "attempt-1")

    def test_start_rejects_wrong_dataset(self):
        loader = HistoricalCountLoader(["psql"], ".")
        with self.assertRaisesRegex(ValueError, "unsupported dataset"):
            loader.start(dict(metadata(), dataset="package-version"), "run-1", "c" * 64, "attempt-1")

    def test_publish_requires_start(self):
        loader = HistoricalCountLoader(["psql"], ".")
        with self.assertRaisesRegex(RuntimeError, "start"):
            loader.publish({}, None)


@unittest.skipUnless(os.environ.get("PICKAGE_TEST_CONTAINER"),
                     "PICKAGE_TEST_CONTAINER is required for PostgreSQL publisher tests")
class HistoricalCountLoaderIntegrationTests(HistoricalDbKeyValidationIntegrationTests):
    """Real atomic publish checks on the disposable key-validation database."""

    def setUp(self):
        super().setUp()
        self.counts = self.root / "counts.tsv"
        self.counts.write_bytes(b"1\t1.0.0\t2026-08-31\t0\n1\t2.0.0\t2026-08-31\t4\n2\t1.0.0\t2026-08-31\t2\n")
        self.publisher_metadata = self._publisher_metadata()

    def _publisher_metadata(self, snapshot="2026-08-31"):
        def record(role, path):
            data = path.read_bytes()
            return {"role": role, "path": path.name, "bytes": len(data),
                    "rows": 2 if role == "identities" else 3,
                    "sha256": hashlib.sha256(data).hexdigest()}
        manifest = {"lineage": {"population": {"run_id": "curated-run", "manifest_sha256": "a" * 64,
                                                  "snapshot": "2026-08-31", "snapshot_timestamp": "2026-08-31T21:00:00Z"},
                                 "calendar": {"manifest_sha256": "b" * 64}},
                    "calendar": self.calendar,
                    "scope": {"selection_sha256": "e" * 64, "selection_count": 2},
                    "quality": {"calculation_status": "COMPLETE", "resolution_status": "PARTIAL",
                                "target_versions": 3, "positive_target_versions": 2,
                                "zero_target_versions": 1, "distinct_edges": 6},
                    "files": [record("identities", self.identity), record("counts", self.counts)]}
        return {"dataset": "version-dependents", "snapshot": snapshot,
                "snapshot_timestamp": snapshot + "T21:00:00Z", "curated_run_id": "curated-run",
                "run_prefix": "run", "manifest": manifest, "manifest_sha256": sha256(manifest),
                "counts": {"package_version_snapshot": 3, "identities": 2}}

    def _publish(self, execution="dep-1", attempt="dep-attempt", failpoint=None):
        with HistoricalCountLoader(self.command, self.root) as loader:
            loader.start(self.publisher_metadata, execution, "c" * 64, attempt)
            try:
                return loader.publish({"identities": self.identity, "counts": self.counts}, failpoint=failpoint)
            except BaseException as error:
                loader.fail(error)
                raise

    def test_atomic_publish_zero_and_idempotent_rerun(self):
        result = self._publish()
        self.assertEqual(result["action"], "LOADED")
        self.assertEqual(self._sql("SELECT count(*) FROM package_version_snapshot;"), "3")
        self.assertEqual(self._sql("SELECT execution_id FROM etl_dataset_current WHERE dataset='version-dependents';"), "dep-1")
        result = self._publish(attempt="dep-reverify")
        self.assertEqual(result["action"], "REVERIFIED")
        self.assertEqual(self._sql("SELECT dependents_count FROM package_version_snapshot WHERE package_id=1 AND version='1.0.0';"), "0")

    def test_failpoint_rolls_back_and_retry_publishes(self):
        with self.assertRaisesRegex(RuntimeError, "after_insert"):
            self._publish(failpoint="after_insert")
        self.assertEqual(self._sql("SELECT count(*) FROM package_version_snapshot;"), "0")
        self.assertEqual(self._sql("SELECT status FROM etl_load_execution WHERE execution_id='dep-1';"), "FAILED")
        result = self._publish(attempt="dep-retry")
        self.assertEqual(result["action"], "LOADED")

    def test_after_copy_and_before_commit_rollback_then_retry(self):
        with self.assertRaisesRegex(RuntimeError, "after_copy"):
            self._publish(execution="dep-copy", attempt="dep-copy-a", failpoint="after_copy")
        self.assertEqual(self._sql("SELECT count(*) FROM package_version_snapshot;"), "0")
        with self.assertRaisesRegex(RuntimeError, "before_commit"):
            self._publish(execution="dep-commit", attempt="dep-commit-a", failpoint="before_commit")
        self.assertEqual(self._sql("SELECT count(*) FROM package_version_snapshot;"), "0")
        self.assertEqual(self._publish(execution="dep-copy", attempt="dep-copy-b")["action"], "LOADED")
        self.assertEqual(self._publish(execution="dep-commit", attempt="dep-commit-b")["action"], "REVERIFIED")

    def test_tampered_or_deleted_service_value_is_rejected_on_reverify(self):
        self._publish()
        self._sql("UPDATE package_version_snapshot SET dependents_count=99 WHERE package_id=1 AND version='1.0.0';")
        with self.assertRaisesRegex(RuntimeError, "stored count validation|values"):
            self._publish(attempt="dep-tamper")
        self._sql("UPDATE package_version_snapshot SET dependents_count=0 WHERE package_id=1 AND version='1.0.0'; DELETE FROM package_version_snapshot WHERE package_id=1 AND version='1.0.0';")
        with self.assertRaisesRegex(RuntimeError, "stored count"):
            self._publish(attempt="dep-missing")

    def test_conflicting_execution_input_is_rejected(self):
        self._publish()
        self.publisher_metadata["run_prefix"] = "different-input"
        with self.assertRaisesRegex(ValueError, "different input"):
            self._publish(attempt="dep-conflict")

    def test_partial_quality_is_recorded_and_other_data_is_preserved(self):
        self._sql("INSERT INTO package VALUES (3,'outside',NULL); INSERT INTO version(version,package_id) VALUES ('9.0.0',3); INSERT INTO package_version_snapshot VALUES (3,'9.0.0','2026-08-31',123);")
        self._sql("INSERT INTO package_snapshot(package_id,snapshot_at,downloads,stars,open_issues) VALUES (1,'2026-08-31',77,7,7);")
        self._publish()
        self.assertEqual(self._sql("SELECT downloads || '|' || stars || '|' || open_issues FROM package_snapshot WHERE package_id=1 AND snapshot_at='2026-08-31';"), "77|7|7")
        self.assertEqual(self._sql("SELECT quality_report->>'resolution_status' FROM etl_load_attempt WHERE attempt_id='dep-attempt';"), "PARTIAL")
        self.assertEqual(self._sql("SELECT dependents_count FROM package_version_snapshot WHERE package_id=3;"), "123")

    def test_old_date_does_not_regress_current_pointer(self):
        self._publish()
        self.counts.write_bytes(b"1\t1.0.0\t2026-08-30\t0\n1\t2.0.0\t2026-08-30\t4\n2\t1.0.0\t2026-08-30\t2\n")
        self.publisher_metadata = self._publisher_metadata("2026-08-30")
        self.assertEqual(self._publish(execution="dep-old", attempt="dep-old-a")["action"], "LOADED")
        self.assertEqual(self._sql("SELECT snapshot_at FROM etl_dataset_current WHERE dataset='version-dependents';"), "2026-08-31")

    def test_file_tamper_and_missing_zero_are_rejected(self):
        self.counts.write_bytes(b"1\t1.0.0\t2026-08-31\t4\n1\t2.0.0\t2026-08-31\t4\n2\t1.0.0\t2026-08-31\t2\n")
        with self.assertRaisesRegex(ValueError, "does not match manifest"):
            self._publish()


if __name__ == "__main__":
    unittest.main()
