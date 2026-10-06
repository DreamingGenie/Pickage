"""Contract tests for the DuckDB repository-metrics implementation.

The fixtures are deliberately written with DuckDB itself so these tests do not
require a Spark installation.  They exercise the same six evidence groups as
the Spark implementation and keep the repository identity rules explicit.
"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

try:
    import duckdb
except ImportError:  # Local lightweight Python installs may omit the benchmark runtime.
    duckdb = None

if duckdb is not None:
    from pipeline.preprocessing.experiments.spark.repository_duckdb import ValidationError, transform
else:
    ValidationError = transform = None


SNAPSHOT = "2026-08-31"
SNAPSHOT_TS = "2026-08-31T21:01:10Z"
TS = datetime(2026, 8, 31, 21, 1, 10)
GROUPS = {
    "metric/data",
    "quality/selection",
    "quality/candidates",
    "quality/project_observations",
    "quality/project_conflicts",
    "quality/unmapped_projects",
}


@unittest.skipUnless(duckdb is not None, "duckdb benchmark dependency is not installed")
class RepositoryDuckDBTransformTests(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="repository-duckdb-test-"))

    def tearDown(self):
        shutil.rmtree(self.temp, ignore_errors=True)

    def _parquet(self, name, columns, rows):
        table = "fixture_" + name.replace("-", "_")
        defs = ", ".join(f"{key} {kind}" for key, kind in columns)
        path = self.temp / f"{name}.parquet"
        with duckdb.connect() as con:
            con.execute(f"CREATE TABLE {table} ({defs})")
            if rows:
                placeholders = ", ".join("?" for _ in columns)
                con.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)
            con.execute(f"COPY {table} TO '{path.as_posix()}' (FORMAT PARQUET)")
        return str(path)

    def _inputs(self, packages, versions, raws, projects):
        files = {
            "package": [self._parquet("package", [("package_id", "INTEGER"), ("name", "VARCHAR")], packages)],
            "version": [self._parquet("version", [("package_id", "INTEGER"), ("version", "VARCHAR"),
                                                       ("published_at", "TIMESTAMP"), ("ordinal", "BIGINT")], versions)],
            "versions_full": [self._parquet("versions_full", [("SnapshotAt", "TIMESTAMP"), ("Name", "VARCHAR"),
                                                                 ("Version", "VARCHAR"), ("is_release", "BOOLEAN"),
                                                                 ("published_at", "TIMESTAMP"), ("ordinal", "BIGINT"),
                                                                 ("source_repo", "VARCHAR")], raws)],
            "projects": [self._parquet("projects", [("SnapshotAt", "TIMESTAMP"), ("Type", "VARCHAR"),
                                                       ("project_name", "VARCHAR"), ("StarsCount", "BIGINT"),
                                                       ("OpenIssuesCount", "BIGINT")], projects)],
        }
        return {"snapshot": SNAPSHOT, "snapshot_timestamp": SNAPSHOT_TS, "files": files,
                "counts": {"package": len(packages), "version": len(versions),
                            "versions_full": len(raws), "projects": len(projects)}}

    def _run(self, packages, versions, raws, projects):
        with duckdb.connect(config={"threads": 2}) as con:
            report = transform(con, self._inputs(packages, versions, raws, projects), self.temp / "out")
        return report

    def _rows(self, group, columns="*"):
        with duckdb.connect() as con:
            return con.execute(f"SELECT {columns} FROM read_parquet('{(self.temp / 'out' / group).as_posix()}/*.parquet', hive_partitioning=false) ORDER BY ALL").fetchall()

    def test_valid_fallback_and_six_output_groups(self):
        packages = [(1, "alpha"), (2, "missing")]
        versions = [(1, "1.0.0", TS, 1), (1, "2.0.0", TS, 2), (2, "1.0.0", TS, 1)]
        raws = [(TS, "alpha", "1.0.0", True, TS, 1, "https://github.com/acme/old"),
                (TS, "alpha", "2.0.0", True, TS, 2, "https://github.com/acme/new"),
                (TS, "missing", "1.0.0", True, TS, 1, "https://github.com/acme/no-observation")]
        projects = [(TS, "GITHUB", "acme/new", 4, 2)]
        report = self._run(packages, versions, raws, projects)
        self.assertEqual(set(report["output_counts"]), GROUPS)
        self.assertEqual(self._rows("metric/data", "package_id, stars, open_issues"), [(1, 4, 2), (2, None, None)])
        self.assertEqual(report["mapping"]["null"], 1)
        self.assertEqual(self._rows("quality/selection", "package_id, reason"), [(1, "SELECTED"), (2, "NO_EXACT_OBSERVATION")])

    def test_github_case_variants_deduplicate_but_conflicting_values_null(self):
        packages = [(1, "alpha")]
        versions = [(1, "1.0.0", TS, 1)]
        raws = [(TS, "alpha", "1.0.0", True, TS, 1, "https://github.com/Acme/Repo")]
        projects = [(TS, "GITHUB", "Acme/Repo", 4, 2), (TS, "github", "acme/repo", 5, 2)]
        report = self._run(packages, versions, raws, projects)
        self.assertEqual(self._rows("metric/data", "stars, open_issues"), [(None, None)])
        self.assertEqual(report["conflicts"], 1)

        shutil.rmtree(self.temp / "out")
        projects[-1] = (TS, "github", "acme/repo", 4, 2)
        report = self._run(packages, versions, raws, projects)
        self.assertEqual(self._rows("metric/data", "stars, open_issues"), [(4, 2)])
        self.assertEqual(report["conflicts"], 0)

    def test_gitlab_case_is_exact_and_absent_observation_stays_null(self):
        packages = [(1, "alpha")]
        versions = [(1, "1.0.0", TS, 1)]
        raws = [(TS, "alpha", "1.0.0", True, TS, 1, "https://gitlab.com/Group/Repo")]
        projects = [(TS, "GITLAB", "group/repo", 4, 2)]
        self._run(packages, versions, raws, projects)
        self.assertEqual(self._rows("metric/data", "stars, open_issues"), [(None, None)])
        self.assertEqual(self._rows("quality/selection", "reason, mapping_status"),
                         [("NO_EXACT_OBSERVATION", "NO_EXACT_PROVIDER_PATH_MATCH")])

    def test_invalid_metric_and_null_publication_are_preserved_as_quality(self):
        packages = [(1, "bad"), (2, "null-published")]
        versions = [(1, "1.0.0", TS, 1), (2, "1.0.0", None, 1)]
        raws = [(TS, "bad", "1.0.0", True, TS, 1, "https://github.com/acme/bad"),
                (TS, "null-published", "1.0.0", True, None, 1, "https://github.com/acme/null")]
        projects = [(TS, "GITHUB", "acme/bad", -1, 2), (TS, "GITHUB", "acme/null", 0, 0)]
        self._run(packages, versions, raws, projects)
        self.assertEqual(self._rows("metric/data", "package_id, stars, open_issues"), [(1, None, None), (2, 0, 0)])
        self.assertEqual(self._rows("quality/selection", "package_id, reason"), [(1, "INVALID_METRIC_VALUE"), (2, "SELECTED")])

    def test_candidate_tie_uses_published_at_then_version_and_skips_invalid_url(self):
        packages = [(1, "alpha")]
        earlier = datetime(2026, 8, 1)
        versions = [(1, "1.0.0", earlier, 5), (1, "2.0.0", TS, 5)]
        raws = [(TS, "alpha", "1.0.0", True, earlier, 5, "https://github.com/acme/old/tree/main"),
                (TS, "alpha", "2.0.0", True, TS, 5, "https://example.invalid/nope")]
        projects = [(TS, "GITHUB", "acme/old", 7, 3)]
        self._run(packages, versions, raws, projects)
        self.assertEqual(self._rows("quality/selection", "version, repo_url"),
                         [("1.0.0", "https://github.com/acme/old")])

    def test_wrong_snapshot_timestamp_duplicate_keys_and_missing_fk_fail(self):
        packages = [(1, "alpha")]
        versions = [(1, "1.0.0", TS, 1)]
        raws = [(datetime(2026, 8, 31, 21, 1, 11), "alpha", "1.0.0", True, TS, 1, "https://github.com/acme/repo")]
        projects = [(TS, "GITHUB", "acme/repo", 1, 1)]
        with self.assertRaises(ValidationError):
            self._run(packages, versions, raws, projects)

        shutil.rmtree(self.temp / "out", ignore_errors=True)
        duplicate_raw = raws[:]
        duplicate_raw[0] = (TS, "alpha", "1.0.0", True, TS, 1, "https://github.com/acme/repo")
        with self.assertRaises(ValidationError):
            self._run(packages, versions, duplicate_raw + duplicate_raw, projects)

        shutil.rmtree(self.temp / "out", ignore_errors=True)
        with self.assertRaises(ValidationError):
            self._run([(1, "alpha")], [(99, "1.0.0", TS, 1)], [duplicate_raw[0]], projects)

    def test_empty_populations_still_publish_typed_groups(self):
        report = self._run([], [], [], [])
        self.assertEqual(set(report["output_counts"]), GROUPS)
        self.assertTrue(all(count == 0 for count in report["output_counts"].values()))




    def test_utc_annotated_parquet_and_offset_instant(self):
        inputs = self._inputs([(1, 'alpha')], [(1, '1.0.0', TS, 1)],
                             [(TS, 'alpha', '1.0.0', True, TS, 1, 'https://github.com/acme/repo')],
                             [(TS, 'GITHUB', 'acme/repo', 4, 2)])
        with duckdb.connect() as con:
            con.execute("SET TimeZone='UTC'")
            for name, columns in [('version', ['published_at']), ('versions_full', ['published_at', 'SnapshotAt']), ('projects', ['SnapshotAt'])]:
                target = self.temp / (name + '-tz.parquet')
                replacements = ', '.join(f"{c} AT TIME ZONE 'UTC' AS {c}" for c in columns)
                con.execute(f'CREATE OR REPLACE TEMP TABLE tz_fixture AS SELECT * REPLACE ({replacements}) FROM read_parquet(?)', [inputs['files'][name]])
                con.execute('COPY tz_fixture TO ? (FORMAT PARQUET)', [str(target)])
                inputs['files'][name] = [str(target)]
            inputs['snapshot_timestamp'] = '2026-09-01T06:01:10+09:00'
            result = transform(con, inputs, self.temp / 'out')
        self.assertEqual(result['selection_reasons'], {'SELECTED': 1})
        self.assertEqual(self._rows('metric/data', 'stars, open_issues'), [(4, 2)])
