"""Disposable PostgreSQL tests for reconstructed historical package snapshots."""

from __future__ import annotations

import os
from importlib import import_module
from pathlib import Path
import unittest
import uuid

from pipeline.postgresql.package_snapshot.history_load import HistorySnapshotLoader
from pipeline.preprocessing.package_snapshot.history_policy import policy_document, policy_sha256


CONTAINER = os.environ.get("PICKAGE_PACKAGE_SNAPSHOT_TEST_CONTAINER")


@unittest.skipUnless(CONTAINER, "PICKAGE_PACKAGE_SNAPSHOT_TEST_CONTAINER is required")
class HistorySnapshotPostgresTests(unittest.TestCase):
    """Reuse the disposable fixture setup without inheriting its test methods."""

    target_snapshot = "2026-08-24"
    target_timestamp = "2026-08-24T21:01:08.477988Z"
    base_snapshot = "2026-08-31"
    base_timestamp = "2026-08-31T21:01:10.517131Z"

    def setUp(self):
        fixture_type = import_module(".test_postgres", package=__package__).PackageSnapshotPostgresTests
        self.fixture = fixture_type("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.database = self.fixture.database
        self.command = self.fixture.command
        self.work = Path(self.fixture.work.name)
        self.seed_latest_package_snapshot()

    def sql(self, statement):
        return self.fixture.sql(statement)

    def seed_latest_package_snapshot(self):
        self.sql("""BEGIN;
            INSERT INTO package_snapshot(package_id,snapshot_at,downloads,stars,open_issues)
              VALUES (1,DATE '2026-08-31',99,9,9),(2,DATE '2026-08-31',88,8,8),(3,DATE '2026-08-31',77,7,7);
            INSERT INTO etl_load_execution(execution_id,dataset,status,snapshot_at,snapshot_timestamp,
              curated_run_id,run_prefix,manifest_sha256,contract_sha256,input_metadata,expected_counts,active_attempt_id)
              VALUES ('latest-package-snapshot','package-snapshot','PUBLISHED',DATE '2026-08-31',
                '2026-08-31 21:01:10.517131','latest-run','depsdev/v1/package-snapshot/latest',repeat('e',64),repeat('f',64),
                '{"dataset":"package-snapshot"}','{"package_snapshot":3}','latest-package-snapshot-attempt');
            INSERT INTO etl_load_attempt(attempt_id,execution_id,status,phase,actual_counts,completed_at)
              VALUES ('latest-package-snapshot-attempt','latest-package-snapshot','PUBLISHED','COMMIT','{"package_snapshot":3}',clock_timestamp());
            INSERT INTO etl_dataset_current(dataset,execution_id,snapshot_at,manifest_sha256,manifest)
              VALUES ('package-snapshot','latest-package-snapshot',DATE '2026-08-31',repeat('e',64),'{"dataset":"package-snapshot"}');
            COMMIT;""")

    def metadata(self, *, snapshot=target_snapshot, snapshot_timestamp=target_timestamp,
                 population_manifest="a" * 64, candidate_sha="c" * 64,
                 history_policy=None, history_policy_hash=None):
        manifest = {
            "dataset": "package-snapshot",
            "history_policy": policy_document() if history_policy is None else history_policy,
            "history_policy_sha256": policy_sha256() if history_policy_hash is None else history_policy_hash,
            "input_manifest": {
                "population": {
                    "snapshot": self.base_snapshot,
                    "snapshot_timestamp": self.base_timestamp,
                    "run_id": "population-run",
                    "manifest_sha256": population_manifest,
                },
                "candidate": {"sha256": candidate_sha},
            },
            "interval": {
                "previous_snapshot_at": None,
                "previous_snapshot_timestamp": None,
                "snapshot_timestamp": snapshot_timestamp,
            },
            "quality": {"history_kind": policy_document()["history_kind"]},
        }
        return {
            "dataset": "package-snapshot",
            "snapshot": snapshot,
            "snapshot_timestamp": snapshot_timestamp.removesuffix("Z"),
            "curated_run_id": "history-run",
            "run_prefix": "depsdev/v1/package-snapshot/history-run",
            "manifest_sha256": "d" * 64,
            "manifest": manifest,
            "counts": {"package_snapshot": 3},
        }

    def files(self, snapshot=target_snapshot):
        suffix = uuid.uuid4().hex
        snapshot_path = self.work / f"package_snapshot-{suffix}.copy.tsv"
        identity_path = self.work / f"package_identity-{suffix}.copy.tsv"
        snapshot_path.write_text(
            "1\t%s\t10\t4\t2\n2\t%s\t0\t0\t0\n3\t%s\t1\t1\t1\n"
            % (snapshot, snapshot, snapshot), encoding="utf-8", newline=""
        )
        identity_path.write_text("1\talpha\n2\tbeta\n3\tgamma\n", encoding="utf-8", newline="")
        return {"package_snapshot": [snapshot_path], "package_identity": [identity_path]}

    def load(self, execution_id="history-load", *, metadata=None, attempt=None,
             files=None, failpoint=None, proof_failure=False):
        metadata = metadata or self.metadata()
        attempt = attempt or execution_id + "-attempt"
        with HistorySnapshotLoader(self.command + ["-d", self.database], self.work) as loader:
            loader.start(metadata, execution_id, "f" * 64, attempt)
            if proof_failure:
                original_one_shot = loader._one_shot

                def fail_after_commit(sql):
                    if "json_build_object" in sql:
                        raise RuntimeError("simulated post-commit proof failure")
                    return original_one_shot(sql)

                loader._one_shot = fail_after_commit
            try:
                return loader.publish(files or self.files(), failpoint=failpoint)
            except BaseException as exc:
                # A proof failure occurs after COMMIT; preserve PUBLISHED DB state.
                if loader.phase not in ("COMMIT_SENT", "VERIFY_COMMIT", "COMPLETE"):
                    loader.fail(exc)
                raise

    def test_historical_load_succeeds_and_preserves_latest_pointers(self):
        result = self.load()
        self.assertEqual(result["action"], "LOADED")
        self.assertEqual(self.sql("SELECT count(*) FROM package_snapshot WHERE snapshot_at=DATE '2026-08-24'"), "3")
        self.assertEqual(
            self.sql("SELECT snapshot_at FROM etl_dataset_current WHERE dataset='package-snapshot'"),
            self.base_snapshot,
        )
        self.assertEqual(
            self.sql("SELECT snapshot_at FROM etl_dataset_current WHERE dataset='package-version'"),
            self.base_snapshot,
        )

    def test_same_input_retry_is_reverified_without_duplicate_rows(self):
        self.assertEqual(self.load()["action"], "LOADED")
        result = self.load(attempt="history-load-retry")
        self.assertEqual(result["action"], "REVERIFIED")
        self.assertEqual(self.sql("SELECT count(*) FROM package_snapshot WHERE snapshot_at=DATE '2026-08-24'"), "3")
        self.assertEqual(self.sql("SELECT actual_counts::text FROM etl_load_execution WHERE execution_id='history-load'"),
                         '{"inserted": 3, "verified_rows": 3, "package_snapshot": 3}')

    def test_policy_and_population_mutations_are_rejected(self):
        cases = (
            ("policy", self.metadata(history_policy={"changed": True}), "history reconstruction policy"),
            ("population", self.metadata(population_manifest="b" * 64), "history base population"),
        )
        for name, metadata, message in cases:
            with self.subTest(name=name), self.assertRaisesRegex(Exception, message):
                self.load("history-mutated-" + name, metadata=metadata)
            self.assertEqual(self.sql("SELECT count(*) FROM package_snapshot WHERE snapshot_at=DATE '2026-08-24'"), "0")

    def test_exact_snapshot_reference_timestamp_is_required(self):
        metadata = self.metadata(
            snapshot_timestamp="2026-08-24T21:01:09.000000Z",
        )
        with self.assertRaisesRegex(Exception, "history calendar or exact source observation time"):
            self.load("history-wrong-reference", metadata=metadata)
        self.assertEqual(self.sql("SELECT count(*) FROM package_snapshot WHERE snapshot_at=DATE '2026-08-24'"), "0")

    def test_base_snapshot_or_later_is_rejected(self):
        metadata = self.metadata(snapshot=self.base_snapshot, snapshot_timestamp=self.base_timestamp)
        with self.assertRaisesRegex(Exception, "accepts dates before"):
            self.load("history-at-base", metadata=metadata, files=self.files(snapshot=self.base_snapshot))
        self.assertEqual(self.sql("SELECT count(*) FROM package_snapshot WHERE snapshot_at=DATE '2026-08-31'"), "3")

    def test_failure_rolls_back_historical_rows_and_records_failed_attempt(self):
        with self.assertRaisesRegex(Exception, "injected failure after_insert"):
            self.load("history-failed", failpoint="after_insert")
        self.assertEqual(self.sql("SELECT count(*) FROM package_snapshot WHERE snapshot_at=DATE '2026-08-24'"), "0")
        self.assertEqual(self.sql("SELECT status FROM etl_load_execution WHERE execution_id='history-failed'"), "FAILED")
        self.assertEqual(self.sql("SELECT status FROM etl_load_attempt WHERE attempt_id='history-failed-attempt'"), "FAILED")

    def test_post_commit_proof_failure_preserves_published_rows_and_retry_reverifies(self):
        with self.assertRaisesRegex(Exception, "simulated post-commit proof failure"):
            self.load("history-post-commit", proof_failure=True)
        self.assertEqual(self.sql("SELECT count(*) FROM package_snapshot WHERE snapshot_at=DATE '2026-08-24'"), "3")
        self.assertEqual(self.sql("SELECT status FROM etl_load_execution WHERE execution_id='history-post-commit'"), "PUBLISHED")
        self.assertEqual(self.sql("SELECT status FROM etl_load_attempt WHERE attempt_id='history-post-commit-attempt'"), "PUBLISHED")
        result = self.load("history-post-commit", attempt="history-post-commit-retry")
        self.assertEqual(result["action"], "REVERIFIED")
        self.assertEqual(self.sql("SELECT count(*) FROM package_snapshot WHERE snapshot_at=DATE '2026-08-24'"), "3")


if __name__ == "__main__":
    unittest.main()
