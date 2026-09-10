"""Regression fixtures for publication-date-based historical snapshots."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import tempfile
import unittest
from pathlib import Path

import duckdb

from .history_build import build_snapshot, prepare_state
from .history_load import prepare_copy
from .quality import COMMON_SCHEMA, HISTORY_FIELDS, QUALITY_SCHEMA_ID


TARGET = "2025-12-31"
PREVIOUS = "2025-12-29"


class HistoryBuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.pkg = self.root / "package.parquet"
        self.cand = self.root / "candidates.parquet"
        self.daily = {}
        self.target = self.root / "target.csv"
        self.status = self.root / "status.parquet"

        with duckdb.connect() as con:
            con.execute("CREATE TABLE packages(package_id INTEGER,name VARCHAR)")
            con.executemany("INSERT INTO packages VALUES (?,?)", [
                (1, "alpha"), (2, "beta"), (3, "gamma"), (4, "delta"),
                (5, "epsilon"), (6, "zeta"), (7, "eta"), (8, "theta"),
            ])
            con.execute("COPY packages TO ? (FORMAT PARQUET)", [str(self.pkg)])
            con.execute("""CREATE TABLE candidates(
                package_id INTEGER, version VARCHAR, published_at TIMESTAMPTZ,
                ordinal BIGINT, repo_url VARCHAR, eligible BOOLEAN)""")
            con.executemany("INSERT INTO candidates VALUES (?,?,?,?,?,?)", [
                (1, "1.0", datetime(2024, 1, 1, tzinfo=timezone.utc), 2, "https://github.com/Org/Repo", True),
                (1, "2.0", datetime(2025, 1, 1, tzinfo=timezone.utc), 1, "https://github.com/Org/New", True),
                (2, "1.0", datetime(2024, 1, 1, tzinfo=timezone.utc), 1, "https://gitlab.com/Group/Repo", True),
                (3, "1.0", datetime(2024, 1, 1, tzinfo=timezone.utc), 1, None, True),
                (4, "1.0", None, 1, "https://github.com/Org/Unknown", True),
                (5, "1.0", datetime(2026, 1, 1, tzinfo=timezone.utc), 1, "https://github.com/Org/Future", True),
                (6, "1.0", datetime(2024, 1, 1, tzinfo=timezone.utc), 1, "https://github.com/Org/Conflict", True),
                (7, "1.0", datetime(2024, 1, 1, tzinfo=timezone.utc), 1, "https://github.com/Org/Nullable", True),
                (8, "1.0", datetime(2024, 1, 1, tzinfo=timezone.utc), 1, "https://github.com/Org/Theta", True),
            ])
            con.execute("COPY candidates TO ? (FORMAT PARQUET)", [str(self.cand)])

        self.projects = self.project_file(TARGET)
        self.daily["2025-12-29"] = [str(self.daily_file("2025-12-29", [
            ("alpha", 10, False), ("beta", 0, False), ("gamma", 0, False),
            ("zeta", 3, False), ("eta", 4, False),
        ]))]
        self.daily["2025-12-30"] = [str(self.daily_file("2025-12-30", [
            ("alpha", None, True), ("beta", 0, False),
            ("zeta", 3, False), ("eta", 4, False),
        ]))]
        # This input is present but must be excluded because [P,S) ends before S.
        self.daily["2025-12-31"] = [str(self.daily_file("2025-12-31", [("alpha", 999, False)]))]

        # Target and status sets agree; theta is deliberately outside the target list.
        self.target.write_text("name\nalpha\nbeta\ngamma\nzeta\neta\n", encoding="utf-8")
        self.write_status({name: "READY" for name in ("alpha", "beta", "gamma", "zeta", "eta")})
        self.prepared = {
            "package_files": [str(self.pkg)], "candidate_files": [str(self.cand)],
            "input_sha256": "a" * 64, "project_files": {TARGET: [str(self.projects)]},
            "daily_files": self.daily, "target_file": str(self.target),
            "status_file": str(self.status), "available_start": "2025-12-29",
            "available_end": "2025-12-31",
        }
        self.state = prepare_state(self.prepared, self.root / "state", memory="256MB", threads=1)

    def tearDown(self):
        self.tmp.cleanup()

    def project_file(self, snapshot, rows=None, name="projects", metric_type="INTEGER",
                     timestamp_override=None):
        timestamp = datetime.fromisoformat(timestamp_override or (snapshot + "T21:00:00+00:00"))
        rows = rows or [
            ("GITHUB", "org/repo", 3, 1), ("GITHUB", "org/new", 99, 99),
            ("GITLAB", "Group/Repo", 20, 2), ("GITLAB", "group/repo", 99, 99),
            ("GITHUB", "org/conflict", 3, 4), ("GITHUB", "org/conflict", 3, 4),
            ("GITHUB", "org/conflict", None, 4), ("GITHUB", "org/nullable", None, 7),
        ]
        path = self.root / f"{name}-{snapshot}.parquet"
        with duckdb.connect() as con:
            con.execute(f"""CREATE TABLE projects(
                Type VARCHAR, project_name VARCHAR, StarsCount {metric_type},
                OpenIssuesCount {metric_type}, SnapshotAt TIMESTAMPTZ)""")
            con.executemany("INSERT INTO projects VALUES (?,?,?,?,?)",
                            [(provider, project, stars, issues, timestamp)
                             for provider, project, stars, issues in rows])
            con.execute("COPY projects TO ? (FORMAT PARQUET)", [str(path)])
        return path

    def daily_file(self, day, rows, name="daily"):
        path = self.root / f"{name}-{day}.parquet"
        with duckdb.connect() as con:
            con.execute("CREATE TABLE daily(name VARCHAR,downloads BIGINT,imputed_gap BOOLEAN,date DATE)")
            con.executemany("INSERT INTO daily VALUES (?,?,?,?)",
                            [(name_value, downloads, gap, day) for name_value, downloads, gap in rows])
            con.execute("COPY daily TO ? (FORMAT PARQUET)", [str(path)])
        return path

    def write_status(self, values):
        with duckdb.connect() as con:
            con.execute("CREATE TABLE statuses(name VARCHAR,status VARCHAR)")
            con.executemany("INSERT INTO statuses VALUES (?,?)", list(values.items()))
            con.execute("COPY statuses TO ? (FORMAT PARQUET)", [str(self.status)])

    def build(self, *, snapshot=TARGET, previous=PREVIOUS, prepared=None,
              output_name="output", projects=None):
        data = deepcopy(prepared or self.prepared)
        if projects is not None:
            data["project_files"] = {snapshot: [str(projects)]}
        snapshot_date = datetime.fromisoformat(snapshot).date()
        previous_date = None if previous is None else datetime.fromisoformat(previous).date()
        return build_snapshot(
            data, self.state,
            {"snapshot_at": snapshot, "snapshot_timestamp": snapshot + "T21:00:00Z",
             "previous_snapshot_at": previous,
             "interval_days": None if previous is None else (snapshot_date - previous_date).days},
            self.root / output_name, memory="256MB", threads=1,
        )

    def quality_rows(self, result):
        with duckdb.connect() as con:
            return con.execute("SELECT package_id FROM read_parquet(?) ORDER BY package_id",
                               [result["files"]["quality"]]).fetchall()

    def quality_for(self, result, package_id):
        with duckdb.connect() as con:
            return con.execute("""SELECT package_id,CAST(snapshot_at AS VARCHAR),
                CAST(first_published_at AS VARCHAR),CAST(selected_published_at AS VARCHAR),
                download_sum,stars,open_issues,data_status,expected_days,observed_days,
                valid_days,null_reason,quality_reasons,repository_reason,repository_repo_url,
                repository_version,CAST(repository_observed_timestamp AS VARCHAR)
                FROM read_parquet(?) WHERE package_id=?""",
                               [result["files"]["quality"], package_id]).fetchone()

    def test_state_keeps_unknown_and_future_publication_excluded(self):
        self.assertEqual(self.state["counts"]["unknown_publication_packages"], 1)
        result = self.build()
        ids = {row[0] for row in self.quality_rows(result)}
        self.assertNotIn(4, ids)
        self.assertNotIn(5, ids)

    def test_high_ordinal_wins_over_later_low_ordinal_version(self):
        result = self.build()
        self.assertEqual(self.quality_for(result, 1)[15], "1.0")

    def test_daily_sum_uses_half_open_interval_and_excludes_snapshot_day(self):
        result = self.build()
        row = self.quality_for(result, 1)
        self.assertEqual(row[4], 10)
        self.assertEqual(row[8:11], (2, 2, 1))
        self.assertEqual(row[7], "PARTIAL")

    def test_duplicate_metric_pair_collapses_but_conflict_with_null_is_all_null(self):
        result = self.build()
        beta = self.quality_for(result, 2)
        zeta = self.quality_for(result, 6)
        self.assertEqual(beta[5:7], (20, 2))
        self.assertEqual(zeta[5:7], (None, None))
        self.assertEqual(zeta[13], "PROJECT_METRIC_CONFLICT")

    def test_individual_null_metric_preserves_other_metric(self):
        result = self.build()
        row = self.quality_for(result, 7)
        self.assertEqual(row[5:7], (None, 7))
        self.assertEqual(row[13], "SELECTED")

    def test_invalid_negative_or_overflow_metrics_are_both_null(self):
        invalid = self.project_file(TARGET, rows=[
            ("GITHUB", "org/conflict", -1, 4),
            ("GITHUB", "org/nullable", 2147483648, 7),
        ], name="invalid-metrics", metric_type="BIGINT")
        result = self.build(projects=invalid, output_name="invalid-metrics")
        self.assertEqual(self.quality_for(result, 6)[5:7], (None, None))
        self.assertEqual(self.quality_for(result, 6)[13], "INVALID_METRIC_VALUE")
        self.assertEqual(self.quality_for(result, 7)[5:7], (None, None))
        self.assertEqual(self.quality_for(result, 7)[13], "INVALID_METRIC_VALUE")

    def test_github_is_case_insensitive_and_gitlab_is_exact(self):
        result = self.build()
        self.assertEqual(self.quality_for(result, 1)[14], "https://github.com/Org/Repo")
        self.assertEqual(self.quality_for(result, 2)[5:7], (20, 2))

    def test_no_repository_package_remains_in_population(self):
        row = self.quality_for(self.build(), 3)
        self.assertIsNone(row[14])
        self.assertEqual(row[13], "NO_VALID_REPOSITORY")

    def test_outside_target_and_not_found_reasons_are_preserved(self):
        outside = self.quality_for(self.build(), 8)
        self.assertEqual(outside[11], "OUTSIDE_TARGET_LIST")
        self.assertIn("OUTSIDE_TARGET_LIST", outside[12])
        self.write_status({"alpha": "READY", "beta": "NOT_FOUND", "gamma": "READY", "zeta": "READY", "eta": "READY"})
        prepared = deepcopy(self.prepared)
        prepared["daily_files"] = {
            **self.daily,
            "2025-12-29": [str(self.daily_file("2025-12-29", [
                ("alpha", 10, False), ("gamma", 0, False), ("zeta", 3, False), ("eta", 4, False),
            ], name="not-found"))],
            "2025-12-30": [str(self.daily_file("2025-12-30", [
                ("alpha", None, True), ("zeta", 3, False), ("eta", 4, False),
            ], name="not-found"))],
        }
        not_found = self.build(prepared=prepared, output_name="not-found")
        self.assertEqual(self.quality_for(not_found, 2)[11], "NOT_FOUND")

    def test_first_snapshot_has_no_previous_interval(self):
        row = self.quality_for(self.build(previous=None, output_name="first"), 1)
        self.assertIsNone(row[8])
        self.assertEqual(row[7], "UNAVAILABLE")
        self.assertEqual(row[11], "NO_PREVIOUS_SNAPSHOT")
        self.assertIn("NO_PREVIOUS_SNAPSHOT", row[12])

    def test_invalid_project_snapshot_timestamp_is_rejected(self):
        bad = self.project_file(TARGET, name="wrong-timestamp",
                                timestamp_override="2025-12-30T21:00:00+00:00")
        with self.assertRaisesRegex(ValueError, "wrong SnapshotAt"):
            self.build(projects=bad, output_name="bad-project-time")

    def test_available_end_is_inclusive_for_interval_end_exclusive(self):
        prepared = deepcopy(self.prepared)
        prepared["available_end"] = "2025-12-30"
        beta = self.quality_for(self.build(prepared=prepared, output_name="inclusive-end"), 2)
        self.assertEqual(beta[7], "COMPLETE")
        self.assertIsNone(beta[11])

    def test_fully_outside_available_range_is_marked(self):
        snapshot = "2025-12-22"
        projects = self.project_file(snapshot, name="outside")
        prepared = deepcopy(self.prepared)
        prepared["project_files"] = {snapshot: [str(projects)]}
        prepared["available_start"] = "2025-12-29"
        prepared["available_end"] = "2025-12-30"
        row = self.quality_for(self.build(snapshot=snapshot, previous="2025-12-20",
                                           prepared=prepared, output_name="outside-range"), 2)
        self.assertEqual(row[11], "OUTSIDE_AVAILABLE_RANGE")

    def test_partial_overlap_has_partial_status_and_range_reason(self):
        prepared = deepcopy(self.prepared)
        prepared["available_start"] = "2025-12-29"
        prepared["available_end"] = "2025-12-30"
        beta = self.quality_for(self.build(previous="2025-12-28", prepared=prepared,
                                           output_name="partial-range"), 2)
        self.assertEqual(beta[7], "PARTIAL")
        self.assertEqual(beta[4], 0)
        self.assertIn("OUTSIDE_AVAILABLE_RANGE", beta[12])

    def test_partial_zero_is_retained_as_zero(self):
        gamma = self.quality_for(self.build(), 3)
        self.assertEqual(gamma[4], 0)
        self.assertEqual(gamma[7], "PARTIAL")
        self.assertEqual(gamma[9], 1)

    def test_build_outputs_pass_history_copy_quality_validation(self):
        result = self.build(output_name="copy-input")
        manifest = {
            "quality_schema": QUALITY_SCHEMA_ID,
            "snapshot": TARGET,
            "interval": {"snapshot_timestamp": TARGET + "T21:00:00Z", "interval_days": 2,
                         "previous_snapshot_at": PREVIOUS},
            "counts": {"package_snapshot": result["rows"]},
        }
        copied = prepare_copy(result["files"], manifest, self.root / "copy", memory="256MB", threads=1)
        self.assertEqual(copied["validation"]["rows"], result["rows"])
        self.assertEqual(copied["validation"]["verification"],
                         "ALL_KEYS_VALUES_ELIGIBILITY_COVERAGE_AND_QUALITY")
        self.assertEqual(set(copied["csv_files"]), {"package_snapshot", "package_identity"})
        self.assertIn(b"1\t2025-12-31\t10\t3\t1\n",
                      (self.root / "copy" / "package_snapshot.copy.tsv").read_bytes())

    def test_history_common_schema_mapping_and_name(self):
        result = self.build(output_name="common-schema")
        self.assertEqual(result["quality_schema"], QUALITY_SCHEMA_ID)
        with duckdb.connect() as con:
            schema = [(r[0], r[1]) for r in con.execute("DESCRIBE SELECT * FROM read_parquet(?)",
                      [result["files"]["quality"]]).fetchall()]
            self.assertEqual(schema, COMMON_SCHEMA + HISTORY_FIELDS)
            rows = con.execute("SELECT package_id,name,repository_mapping_status FROM read_parquet(?) "
                               "WHERE package_id IN (1,3,6) ORDER BY 1", [result["files"]["quality"]]).fetchall()
        self.assertEqual(rows, [(1, "alpha", "MATCHED"), (3, "gamma", "NO_SELECTED_REPOSITORY"),
                                (6, "zeta", "MATCHED")])

    def test_duplicate_daily_name_and_date_is_rejected(self):
        duplicate = self.daily_file("2025-12-29", [("alpha", 10, False)], name="duplicate")
        prepared = deepcopy(self.prepared)
        prepared["daily_files"] = dict(self.daily)
        prepared["daily_files"]["2025-12-29"] = [self.daily["2025-12-29"][0], str(duplicate)]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.build(prepared=prepared, output_name="duplicate-daily")

    def test_rejects_state_for_other_input(self):
        prepared = deepcopy(self.prepared)
        prepared["input_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "different input"):
            self.build(prepared=prepared, output_name="wrong-state")


if __name__ == "__main__":
    unittest.main()
