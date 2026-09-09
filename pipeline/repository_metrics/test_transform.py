"""Small Spark fixtures for the repository metrics transform.

This module intentionally imports PySpark directly.  A missing runtime is a
setup failure, rather than a silently skipped verification.
"""
from __future__ import annotations

import shutil
import tempfile
import unittest
import uuid
from datetime import datetime
from pathlib import Path

from pyspark.sql import SparkSession, types as T

from pipeline.repository_metrics.transform import ValidationError, transform


SNAPSHOT_TS = "2026-08-31T21:01:10Z"
TS = datetime(2026, 8, 31, 21, 1, 10)


class RepositoryMetricsTransformTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = (SparkSession.builder.master("local[2]").appName("repository-metrics-fixture")
                     .config("spark.ui.enabled", "false").config("spark.sql.shuffle.partitions", "2")
                     .config("spark.driver.memory", "2g").config("spark.sql.session.timeZone", "UTC").getOrCreate())
        cls.spark.sparkContext.setLogLevel("ERROR")

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="repository-metrics-test-"))

    def tearDown(self):
        shutil.rmtree(self.temp, ignore_errors=True)

    def _write(self, name, rows, schema):
        path = self.temp / f"{name}-{uuid.uuid4().hex}.parquet"
        self.spark.createDataFrame(rows, schema).write.mode("error").parquet(str(path))
        return str(path)

    def _inputs(self, packages, versions, raws, projects):
        files = {
            "package": [self._write("package", packages, "package_id INT, name STRING")],
            "version": [self._write("version", versions, "version STRING, package_id INT, published_at TIMESTAMP, ordinal BIGINT")],
            "versions_full": [self._write("versions_full", raws, "SnapshotAt TIMESTAMP, Name STRING, Version STRING, is_release BOOLEAN, published_at TIMESTAMP, ordinal BIGINT, source_repo STRING")],
            "projects": [self._write("projects", projects, "SnapshotAt TIMESTAMP, Type STRING, project_name STRING, StarsCount LONG, OpenIssuesCount LONG")],
        }
        return {"snapshot": "2026-08-31", "snapshot_timestamp": SNAPSHOT_TS, "files": files,
                "counts": {k: len(v) for k, v in {"package": packages, "version": versions,
                                                    "versions_full": raws, "projects": projects}.items()}}

    def test_selects_deterministic_candidate_and_keeps_null_when_observation_absent(self):
        packages = [(1, "alpha"), (2, "missing")]
        versions = [("1.0.0", 1, TS, 1), ("2.0.0", 1, TS, 2), ("1.0.0", 2, TS, 1)]
        raws = [(TS, "alpha", "1.0.0", True, TS, 1, "https://github.com/acme/old"),
                (TS, "alpha", "2.0.0", True, TS, 2, "https://github.com/acme/new"),
                (TS, "missing", "1.0.0", True, TS, 1, "https://github.com/acme/no-observation")]
        projects = [(TS, "GITHUB", "acme/new", 4, 2)]
        report = transform(self.spark, self._inputs(packages, versions, raws, projects), self.temp / "out")
        rows = self.spark.read.parquet(str(self.temp / "out/metric/data")).orderBy("package_id").collect()
        self.assertEqual([(r.package_id, r.stars, r.open_issues) for r in rows], [(1, 4, 2), (2, None, None)])
        self.assertEqual(report["mapping"]["null"], 1)
        self.assertIsInstance(self.spark.read.parquet(str(self.temp / "out/metric/data")).schema["snapshot_at"].dataType, T.DateType)
        evidence = self.spark.read.parquet(str(self.temp / "out/quality/selection")).orderBy("package_id").collect()
        self.assertEqual(evidence[0].observed_timestamp, TS)
        self.assertIsNone(evidence[1].observed_timestamp)
        self.assertEqual(evidence[1].repo_url, "https://github.com/acme/no-observation")

    def test_conflicting_project_values_are_null_and_reported(self):
        packages = [(1, "alpha")]
        versions = [("1.0.0", 1, TS, 1)]
        raws = [(TS, "alpha", "1.0.0", True, TS, 1, "https://gitlab.com/group/repo")]
        projects = [(TS, "GITLAB", "group/repo", 4, 2), (TS, "GITLAB", "group/repo", 5, 2)]
        report = transform(self.spark, self._inputs(packages, versions, raws, projects), self.temp / "out")
        row = self.spark.read.parquet(str(self.temp / "out/metric/data")).first()
        self.assertIsNone(row.stars)
        self.assertEqual(report["conflicts"], 1)

    def test_github_case_variant_metrics_conflict_after_lowercase_comparison(self):
        packages = [(1, "alpha")]
        versions = [("1.0.0", 1, TS, 1)]
        raws = [(TS, "alpha", "1.0.0", True, TS, 1, "https://github.com/Acme/Repo")]
        projects = [(TS, "GITHUB", "Acme/Repo", 4, 2),
                    (TS, "github", "acme/repo", 5, 2)]
        report = transform(self.spark, self._inputs(packages, versions, raws, projects), self.temp / "github-conflict")
        row = self.spark.read.parquet(str(self.temp / "github-conflict/metric/data")).first()
        self.assertIsNone(row.stars)
        self.assertEqual(report["conflicts"], 1)
        evidence = self.spark.read.parquet(str(self.temp / "github-conflict/quality/selection")).first()
        self.assertEqual(evidence.repo_url, "https://github.com/Acme/Repo")
        self.assertEqual(evidence.project_path, "Acme/Repo")
        self.assertEqual(evidence.comparison_project_path, "acme/repo")

    def test_github_equal_case_variant_duplicates_collapse_and_preserve_source_path(self):
        packages = [(1, "alpha")]
        versions = [("1.0.0", 1, TS, 1)]
        raws = [(TS, "alpha", "1.0.0", True, TS, 1, "https://github.com/Acme/Repo")]
        projects = [(TS, "GITHUB", "Acme/Repo", 4, 2),
                    (TS, "github", "acme/repo", 4, 2)]
        report = transform(self.spark, self._inputs(packages, versions, raws, projects), self.temp / "github-duplicate")
        row = self.spark.read.parquet(str(self.temp / "github-duplicate/metric/data")).first()
        self.assertEqual((row.stars, row.open_issues), (4, 2))
        self.assertEqual(report["conflicts"], 0)
        observation = self.spark.read.parquet(str(self.temp / "github-duplicate/quality/project_observations")).first()
        self.assertEqual((observation.source_rows, observation.distinct_metric_pairs), (2, 1))
        self.assertEqual(observation.source_project_path, "Acme/Repo")

    def test_gitlab_path_case_remains_case_sensitive(self):
        packages = [(1, "alpha")]
        versions = [("1.0.0", 1, TS, 1)]
        raws = [(TS, "alpha", "1.0.0", True, TS, 1, "https://gitlab.com/Group/Repo")]
        projects = [(TS, "GITLAB", "group/repo", 4, 2)]
        transform(self.spark, self._inputs(packages, versions, raws, projects), self.temp / "gitlab-case")
        row = self.spark.read.parquet(str(self.temp / "gitlab-case/metric/data")).first()
        self.assertIsNone(row.stars)
        evidence = self.spark.read.parquet(str(self.temp / "gitlab-case/quality/selection")).first()
        self.assertEqual(evidence.mapping_status, "NO_EXACT_PROVIDER_PATH_MATCH")

    def test_wrong_exact_timestamp_fails(self):
        packages = [(1, "alpha")]
        versions = [("1.0.0", 1, TS, 1)]
        raws = [(datetime(2026, 8, 31, 21, 1, 11), "alpha", "1.0.0", True, TS, 1, "https://github.com/acme/repo")]
        projects = [(TS, "GITHUB", "acme/repo", 1, 1)]
        with self.assertRaises(ValidationError):
            transform(self.spark, self._inputs(packages, versions, raws, projects), self.temp / "out")

    def test_missing_raw_key_and_fk_fail(self):
        packages = [(1, "alpha")]
        versions = [("1.0.0", 1, TS, 1)]
        projects = [(TS, "GITHUB", "acme/repo", 1, 1)]
        with self.assertRaises(ValidationError):
            transform(self.spark, self._inputs(packages, versions, [], projects), self.temp / "missing")
        bad_versions = [("1.0.0", 99, TS, 1)]
        raws = [(TS, "alpha", "1.0.0", True, TS, 1, "https://github.com/acme/repo")]
        with self.assertRaises(ValidationError):
            transform(self.spark, self._inputs(packages, bad_versions, raws, projects), self.temp / "fk")

    def test_ordinal_tie_and_invalid_url_fallback(self):
        packages = [(1, "alpha")]
        versions = [("1.0.0", 1, datetime(2026, 8, 1), 5), ("2.0.0", 1, datetime(2026, 8, 2), 5)]
        raws = [(TS, "alpha", "1.0.0", True, datetime(2026, 8, 1), 5, "https://github.com/acme/old/tree/main"),
                (TS, "alpha", "2.0.0", True, datetime(2026, 8, 2), 5, "https://example.invalid/not-supported")]
        projects = [(TS, "GITHUB", "acme/old", 7, 3)]
        transform(self.spark, self._inputs(packages, versions, raws, projects), self.temp / "tie")
        row = self.spark.read.parquet(str(self.temp / "tie/quality/selection")).first()
        self.assertEqual(row.version, "1.0.0")

    def test_github_and_gitlab_subgroups_are_separate_exact_keys(self):
        packages = [(1, "gh"), (2, "gl"), (3, "gl-same-path")]
        versions = [("1", 1, TS, 1), ("1", 2, TS, 1), ("1", 3, TS, 1)]
        raws = [(TS, "gh", "1", True, TS, 1, "https://github.com/acme/repo"),
                (TS, "gl", "1", True, TS, 1, "https://gitlab.com/group/sub/repo"),
                (TS, "gl-same-path", "1", True, TS, 1, "https://gitlab.com/acme/repo")]
        projects = [(TS, "GITHUB", "acme/repo", 1, 2), (TS, "GITLAB", "group/sub/repo", 9, 4),
                    (TS, "GITLAB", "acme/repo", 6, 8)]
        transform(self.spark, self._inputs(packages, versions, raws, projects), self.temp / "providers")
        rows = self.spark.read.parquet(str(self.temp / "providers/metric/data")).orderBy("package_id").collect()
        self.assertEqual([(r.stars, r.open_issues) for r in rows], [(1, 2), (9, 4), (6, 8)])

    def test_tie_orders_publish_time_then_version_with_null_last(self):
        packages = [(1, "tie"), (2, "null-last")]
        earlier = datetime(2026, 8, 1)
        versions = [("1", 1, earlier, 5), ("2", 1, TS, 5), ("3", 1, TS, 5),
                    ("1", 2, None, 5), ("2", 2, earlier, 5)]
        raws = [(TS, "tie" if i == 1 else "null-last", v, True, dt, ordinal,
                 "https://github.com/acme/v" + v) for v, i, dt, ordinal in versions]
        projects = [(TS, "GITHUB", "acme/v2", 5, 1)]
        transform(self.spark, self._inputs(packages, versions, raws, projects), self.temp / "ties")
        rows = self.spark.read.parquet(str(self.temp / "ties/quality/selection")).orderBy("package_id").collect()
        self.assertEqual([r.version for r in rows], ["2", "2"])

    def test_zero_metrics_are_observed_and_null_source_values_are_not_no_observation(self):
        packages = [(1, "zero"), (2, "nulls")]
        versions = [("1", 1, TS, 1), ("1", 2, TS, 1)]
        raws = [(TS, "zero", "1", True, TS, 1, "https://github.com/acme/zero"),
                (TS, "nulls", "1", True, TS, 1, "https://github.com/acme/nulls")]
        projects = [(TS, "GITHUB", "acme/zero", 0, 0), (TS, "GITHUB", "acme/nulls", None, None)]
        transform(self.spark, self._inputs(packages, versions, raws, projects), self.temp / "zero")
        rows = self.spark.read.parquet(str(self.temp / "zero/quality/selection")).orderBy("package_id").collect()
        self.assertEqual(rows[0].reason, "SELECTED")
        self.assertEqual(rows[1].reason, "SELECTED")

    def test_canonical_duplicates_shared_repository_and_unmapped_evidence(self):
        packages = [(1, "one"), (2, "two"), (3, "invalid"), (4, "no-url")]
        versions = [("1", i, TS, 1) for i, _ in packages]
        raws = [(TS, name, "1", True, TS, 1, None if i == 4 else
                 "https://github.com/acme/" + ("bad" if i == 3 else "shared")) for i, name in packages]
        projects = [(TS, "GITHUB", "acme/shared", 4, 2), (TS, "github", "acme/shared", 4, 2),
                    (TS, "GITHUB", "acme/shared", 4, 2), (TS, "GITHUB", "acme/bad", -1, 1),
                    (TS, "UNKNOWN", "acme/shared", 9, 8), (TS, "GITHUB", None, 1, 1)]
        report = transform(self.spark, self._inputs(packages, versions, raws, projects), self.temp / "out")
        rows = self.spark.read.parquet(str(self.temp / "out/metric/data")).orderBy("package_id").collect()
        self.assertEqual([(r.stars, r.open_issues) for r in rows], [(4, 2), (4, 2), (None, None), (None, None)])
        self.assertEqual(report["conflicts"], 0)
        self.assertEqual(report["unsupported_project_rows"], 2)
        obs = self.spark.read.parquet(str(self.temp / "out/quality/project_observations")).where("project_path = 'acme/shared'").first()
        self.assertEqual((obs.source_rows, obs.distinct_metric_pairs), (3, 1))
        unmapped = self.spark.read.parquet(str(self.temp / "out/quality/unmapped_projects")).collect()
        self.assertEqual({r.reason for r in unmapped}, {"PROVIDER_PATH_MAPPING_FAILED"})
        evidence = self.spark.read.parquet(str(self.temp / "out/quality/selection")).orderBy("package_id").collect()
        self.assertEqual([r.reason for r in evidence], ["SELECTED", "SELECTED", "INVALID_METRIC_VALUE", "NO_VALID_REPOSITORY"])

    def test_runtime_does_not_reuse_an_existing_context(self):
        from pipeline.repository_metrics.runtime import create_spark
        with self.assertRaisesRegex(ValueError, "existing Spark context"):
            create_spark(self.temp / "runtime")


if __name__ == "__main__":
    unittest.main()
