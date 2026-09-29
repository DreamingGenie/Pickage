import unittest

from pipeline.preprocessing.snapshot.policy import assess_download_coverage, build_calendar, parse_timestamp, policy_document, policy_sha256, select_project_observation, version_eligibility


class SnapshotPolicyTests(unittest.TestCase):
    def test_parse_timestamp_normalizes_offsets_and_preserves_microseconds(self):
        value = parse_timestamp("2026-01-01T09:00:00.123456+09:00")
        self.assertEqual(value.isoformat(), "2026-01-01T00:00:00.123456+00:00")
        self.assertEqual(parse_timestamp("2026-01-01T00:00:00 UTC"), value.replace(microsecond=0))
        self.assertEqual(parse_timestamp("2026-01-01 00:00:00.123456", allow_naive_utc=True).microsecond, 123456)

    def test_parse_timestamp_rejects_weak_or_overprecise_values(self):
        for value in ("2026-01-01", "2026-01-01T00:00:00", "2026-01-01T00:00:00.1234567Z"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_timestamp(value)
        for value in ("2026-01-01T00:00:00+24:00", "2026-01-01T00:00:00+01:99"):
            with self.assertRaises(ValueError):
                parse_timestamp(value)

    def test_calendar_deduplicates_equal_instants_but_rejects_utc_date_conflicts(self):
        rows = build_calendar(["2026-01-02T00:00:00Z", "2026-01-01T19:00:00-05:00", "2026-01-03T00:00:00Z"])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["source_timestamps"], ["2026-01-02T00:00:00Z", "2026-01-01T19:00:00-05:00"])
        self.assertEqual(rows[1]["interval_days"], 1)
        with self.assertRaises(ValueError):
            build_calendar(["2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z"])

    def test_calendar_irregular_gap_is_actual_gap(self):
        rows = build_calendar(["2026-01-24T00:00:00Z", "2026-01-31T00:00:00Z"])
        self.assertEqual(rows[1]["download_start_inclusive"], "2026-01-24")
        self.assertEqual(rows[1]["download_end_exclusive"], "2026-01-31")
        self.assertEqual(rows[1]["interval_days"], 7)
        rows = build_calendar(["2026-01-15T00:00:00Z", "2026-01-01T00:00:00Z"])
        self.assertEqual(rows[1]["previous_snapshot_at"], "2026-01-01")
        self.assertEqual(rows[1]["interval_days"], 14)

    def test_coverage_distinguishes_missing_from_observed_zero(self):
        row = build_calendar(["2026-01-01T00:00:00Z", "2026-01-04T00:00:00Z"])[1]
        self.assertEqual(assess_download_coverage(row, available_start="2026-01-01", available_end="2026-01-03"), {"eligible": True, "null_reason": None, "expected_days": 3, "missing_days": []})
        result = assess_download_coverage(row, available_start="2026-01-01", available_end="2026-01-03", missing_dates=["2026-01-02"])
        self.assertEqual(result["null_reason"], "MISSING_DAILY_VALUES")
        self.assertEqual(result["missing_days"], ["2026-01-02"])
        adjacent = assess_download_coverage(row, available_start="2026-01-01", available_end="2026-01-03", missing_dates=["2026-01-04", "2025-12-31"])
        self.assertTrue(adjacent["eligible"])
        forged = dict(row, previous_snapshot_at="2025-12-31")
        with self.assertRaises(ValueError):
            assess_download_coverage(forged, available_start="2026-01-01", available_end="2026-01-03")

    def test_first_snapshot_and_outside_range(self):
        row = build_calendar(["2026-01-04T00:00:00Z"])[0]
        self.assertEqual(assess_download_coverage(row, available_start="2026-01-01", available_end="2026-01-04")["null_reason"], "NO_PREVIOUS_SNAPSHOT")
        row = build_calendar(["2026-01-01T00:00:00Z", "2026-01-04T00:00:00Z"])[1]
        self.assertEqual(assess_download_coverage(row, available_start="2026-01-02", available_end="2026-01-04")["null_reason"], "OUTSIDE_AVAILABLE_RANGE")

    def test_projects_require_exact_instant_and_population_is_same_snapshot(self):
        target = "2026-01-01T00:00:00Z"
        self.assertEqual(select_project_observation(target, ["2025-12-31T00:00:00Z"])["reason"], "NO_EXACT_OBSERVATION")
        self.assertEqual(select_project_observation(target, ["2026-01-01T09:00:00+09:00"])["reason"], None)
        self.assertEqual(select_project_observation(target, ["2026-01-01T00:00:01Z"])["reason"], "NO_EXACT_OBSERVATION")
        self.assertEqual(version_eligibility(snapshot_timestamp=target, observed_snapshot_timestamp=target, published_at=None, is_release=True), {"eligible": True, "reason": "PUBLISHED_AT_UNKNOWN"})

    def test_version_reasons_and_policy_hash_are_stable(self):
        target = "2026-01-01T00:00:00Z"
        self.assertEqual(version_eligibility(snapshot_timestamp=target, observed_snapshot_timestamp="2026-01-02T00:00:00Z", published_at=None, is_release=True)["reason"], "OBSERVED_SNAPSHOT_MISMATCH")
        self.assertEqual(version_eligibility(snapshot_timestamp=target, observed_snapshot_timestamp=target, published_at=target, is_release=False)["reason"], "NOT_RELEASE")
        self.assertEqual(version_eligibility(snapshot_timestamp=target, observed_snapshot_timestamp=target, published_at="2026-01-02T00:00:00Z", is_release=True)["reason"], "PUBLISHED_AFTER_SNAPSHOT")
        with self.assertRaises(TypeError):
            version_eligibility(snapshot_timestamp=target, observed_snapshot_timestamp=target, published_at=None, is_release=0)
        self.assertEqual(policy_document()["policy_version"], "snapshot-time-v1")
        self.assertEqual(len(policy_sha256()), 64)


if __name__ == "__main__":
    unittest.main()
