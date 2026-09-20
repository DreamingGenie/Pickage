import unittest
from datetime import datetime, timedelta, timezone

from . import s3inv
from .test_support import FakeS3

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
H = timedelta(hours=1)
D = timedelta(days=1)


def seeded():
    s3 = FakeS3()
    raw = "pickage-raw"
    run = "depsdev/v1/projects/snapshot=2026-09-21/run_id=bronze-weekly-20260921"
    s3.add(raw, f"{run}/data/part-0.parquet", b"a" * 100, NOW - 3 * H)
    s3.add(raw, f"{run}/data/part-1.parquet", b"b" * 100, NOW - 2 * H)
    s3.add(raw, f"{run}/run_manifest.json", b"{}", NOW - 1 * H)
    s3.add(raw, f"{run}/_SUCCESS", b"", NOW - 1 * H)
    old = "depsdev/v1/projects/snapshot=2026-09-14/run_id=bronze-weekly-20260914"
    s3.add(raw, f"{old}/data/part-0.parquet", b"c" * 500, NOW - 8 * D)
    s3.add(raw, f"{old}/_SUCCESS", b"", NOW - 8 * D)
    s3.add(raw, "_ops/weekly/2026-09-21/run.json", b"{}", NOW - 1 * H)
    s3.add("pickage-curated", "ecosystems-keywords/v1/package-text/_current.json",
           {"run_id": "package-text-20260908-v1"}, NOW - 5 * D)
    s3.add("pickage-curated", "ecosystems-keywords/v1/package-text/collected_date=2026-09-08/run_id=x/_SUCCESS",
           b"", NOW - 5 * D)
    return s3


class ListTest(unittest.TestCase):
    def test_pages_until_done(self):
        s3 = seeded()
        s3.page_size = 3
        objects, truncated = s3inv.list_bucket(s3, "pickage-raw", max_objects=1000)
        self.assertEqual(len(objects), 7)
        self.assertFalse(truncated)
        self.assertEqual(s3.list_calls, 3)

    def test_cap_marks_truncated(self):
        objects, truncated = s3inv.list_bucket(seeded(), "pickage-raw", max_objects=4)
        self.assertEqual(len(objects), 4)
        self.assertTrue(truncated)


class PrefixTest(unittest.TestCase):
    def test_depth_cuts_directory_part_only(self):
        key = "depsdev/v1/projects/snapshot=2026-09-21/run_id=r/data/p.parquet"
        self.assertEqual(s3inv.prefix_of(key, 3), "depsdev/v1/projects")
        self.assertEqual(s3inv.prefix_of(key, 4), "depsdev/v1/projects/snapshot=2026-09-21")
        self.assertEqual(s3inv.prefix_of("top.json", 3), "(root)")
        self.assertEqual(s3inv.prefix_of("a/b.json", 3), "a")


class AggregateTest(unittest.TestCase):
    def test_new_window_and_recent(self):
        s3 = seeded()
        objects, _ = s3inv.list_bucket(s3, "pickage-raw", max_objects=1000)
        out = s3inv.aggregate("pickage-raw", objects, depth=4, now=NOW, window_hours=24,
                              recent_per_prefix=2, truncated=False)
        self.assertEqual(out["objects"], 7)
        self.assertEqual(out["new"]["objects"], 5)            # 8일 전 둘만 빠진다
        self.assertEqual(out["new_7d"]["objects"], 5)
        by_prefix = {p["prefix"]: p for p in out["prefixes"]}
        this_week = by_prefix["depsdev/v1/projects/snapshot=2026-09-21"]
        self.assertEqual(this_week["objects"], 4)
        self.assertEqual(this_week["bytes"], 202)
        self.assertEqual(len(this_week["recent"]), 2)         # cap
        self.assertEqual(this_week["recent"][0]["key"].rsplit("/", 1)[1], "_SUCCESS")
        last_week = by_prefix["depsdev/v1/projects/snapshot=2026-09-14"]
        self.assertEqual(last_week["new"]["objects"], 0)
        self.assertEqual(last_week["recent"], [])


class CompletedRunsTest(unittest.TestCase):
    def test_success_markers_become_runs_newest_first(self):
        s3 = seeded()
        objects, _ = s3inv.list_bucket(s3, "pickage-raw", max_objects=1000)
        runs = s3inv.completed_runs("pickage-raw", objects)
        self.assertEqual([r["prefix"].rsplit("=", 1)[1] for r in runs],
                         ["bronze-weekly-20260921", "bronze-weekly-20260914"])
        self.assertEqual(runs[0]["objects"], 4)               # _SUCCESS 와 manifest 도 센다
        self.assertEqual(runs[0]["bytes"], 202)
        self.assertEqual(runs[1]["bytes"], 500)


class PointersTest(unittest.TestCase):
    def test_reads_present_and_marks_missing(self):
        rows = s3inv.read_pointers(seeded(), [
            "pickage-curated/ecosystems-keywords/v1/package-text/_current.json",
            "pickage-vectors/_current.json"])
        self.assertEqual(rows[0]["value"]["run_id"], "package-text-20260908-v1")
        self.assertTrue(rows[1]["missing"])
        self.assertEqual(rows[1]["error"], "NoSuchKey")


class CollectTest(unittest.TestCase):
    def test_all_buckets_when_none_given(self):
        out = s3inv.collect(seeded(), buckets=[], depth=3, depth_overrides={"pickage-raw": 4},
                            max_objects=1000, now=NOW, window_hours=24, recent_per_prefix=5,
                            pointers=[])
        self.assertEqual([b["name"] for b in out["buckets"]], ["pickage-curated", "pickage-raw"])
        self.assertEqual(out["buckets"][1]["depth"], 4)
        self.assertEqual(len(out["completed_runs"]), 3)
        self.assertEqual(out["completed_runs"][0]["bucket"], "pickage-raw")
        self.assertEqual(out["errors"], [])

    def test_bucket_failure_is_reported_in_place(self):
        s3 = seeded()
        real = s3.list_objects_v2

        def flaky(Bucket, **kw):
            if Bucket == "pickage-raw":
                raise RuntimeError("AccessDenied")
            return real(Bucket=Bucket, **kw)
        s3.list_objects_v2 = flaky
        out = s3inv.collect(s3, buckets=["pickage-raw", "pickage-curated"], depth=3, depth_overrides={},
                            max_objects=1000, now=NOW, window_hours=24, recent_per_prefix=5, pointers=[])
        self.assertIn("error", out["buckets"][0])
        self.assertEqual(out["buckets"][1]["objects"], 2)
        self.assertEqual(len(out["errors"]), 1)


if __name__ == "__main__":
    unittest.main()
