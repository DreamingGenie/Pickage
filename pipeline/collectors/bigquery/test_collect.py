"""BigQuery 수집기의 과금 관문 시험.

  .venv-bq/Scripts/python.exe -m unittest discover -s pipeline/collectors/bigquery -v

BigQuery·GCS 는 부르지 않는다. 클라이언트 자리에 "무엇을 요청받았는가"를 적는 가짜를 끼우고,
**과금되는 쿼리가 나갔는가**만 본다. 이 수집기에서 틀리면 돈이 나가는 자리는 `bq.query` 를
dry-run 이 아닌 설정으로 부르는 한 줄뿐이라, 관문마다 그 줄에 닿았는지를 센다.

여기 있는 시험이 깨지면 알게 되는 것:
  - 관문 2~4 중 하나가 과금 쿼리를 막지 못한다 (하드캡·기대치 편차·세션 예산)
  - 실행 상한(`maximum_bytes_billed`) 식이 README·계획서와 달라졌다
  - 매니페스트가 있는데 다시 받는다 = 같은 데이터를 두 번 과금한다
  - 스테이징 재사용 경로가 끝까지 가지 못한다 (2026-11-21 시험을 쓰다 찾은 결함 — 아래 ReuseStaging)

실제 과금은 `ledger/ledger.jsonl` 236줄로 확인해 왔다. 그것은 "그때 넘지 않았다"는 기록이고,
이 시험은 "코드를 고쳐도 관문이 남아 있다"를 본다.
"""
import argparse
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from google.api_core import exceptions as gexc  # noqa: E402

import collect  # noqa: E402

GiB = collect.GiB
MiB = collect.MiB
SNAP = "2026-08-31"


class FakeJob:
    def __init__(self, job_id="job-1", billed=0, processed=0):
        self.job_id = job_id
        self.total_bytes_billed = billed
        self.total_bytes_processed = processed

    def result(self):
        return []


class FakeTable:
    def __init__(self, rows, size=1):
        self.num_rows, self.num_bytes = rows, size


class FakeBQ:
    """dry-run 과 실행을 갈라 적는다. 실행 뒤에만 스테이징 테이블이 생긴다."""

    def __init__(self, dry_bytes, rows=0, staged=False):
        self.dry_bytes, self.rows, self.staged = dry_bytes, rows, staged
        self.dry_runs, self.executed, self.extracted, self.deleted = [], [], [], []

    def query(self, sql, job_config=None):
        if job_config is not None and job_config.dry_run:
            self.dry_runs.append(sql)
            return FakeJob(processed=self.dry_bytes)
        self.executed.append(job_config)
        self.staged = True
        return FakeJob(billed=self.dry_bytes)

    def get_table(self, dest):
        if not self.staged:
            raise gexc.NotFound(dest)
        return FakeTable(self.rows)

    def extract_table(self, dest, uri, job_config=None):
        self.extracted.append(uri)
        return FakeJob(job_id="extract-1")

    def delete_table(self, dest, not_found_ok=False):
        self.deleted.append(dest)


class FakeBlob:
    def __init__(self, exists=False):
        self._exists, self.uploaded = exists, None

    def exists(self):
        return self._exists

    def delete(self):
        self._exists = False

    def upload_from_string(self, body, content_type=None):
        self.uploaded, self._exists = body, True


class FakeGCS:
    def list_blobs(self, bucket, prefix=None):
        return []


def make(dry_gib, *, tier="t0", rows=0, staged=False, manifest=False, part_rows=None, **flags):
    """클라이언트를 만들지 않고 Collector 를 세운다. `__init__` 은 자격증명을 찾는다."""
    args = argparse.Namespace(
        tier=tier, snap=SNAP, plan=False, budget_gib=None, force=False, allow_deviation=False,
        continue_on_mismatch=False, since=None, until=None, include_latest=False, keep_staging=False)
    for k, v in flags.items():
        setattr(args, k, v)
    c = collect.Collector.__new__(collect.Collector)
    c.args = args
    c.bq = FakeBQ(int(dry_gib * GiB), rows=rows, staged=staged)
    c.gcs = FakeGCS()
    c.tables, c.budget_gib, c.root = collect.TIERS[tier]
    if args.budget_gib is not None:
        c.budget_gib = args.budget_gib
    c.cum_dry = c.cum_billed = 0
    c.rows_meta = dict(part_rows or {})
    c.results = []
    c.blobs = {}
    c.manifest_blob = lambda table, snap: c.blobs.setdefault((table, snap), FakeBlob(exists=manifest))
    return c


def quiet(fn, *a, **kw):
    with mock.patch.object(collect, "log"):
        return fn(*a, **kw)


class HardCap(unittest.TestCase):
    """관문 2 — 테이블별 하드캡. 파티션 필터가 빠진 쿼리가 전체 스캔으로 나가는 것을 막는다."""

    def test_over_cap_aborts_before_any_billed_query(self):
        cap = collect.TABLES["projects"][1]
        c = make(cap + 0.1)
        with self.assertRaises(SystemExit):
            quiet(c.run_one, "projects", SNAP, False)
        self.assertEqual(c.bq.executed, [])

    def test_every_table_has_cap_above_its_expectation(self):
        """하드캡이 기대치보다 작으면 정상 수집이 언제나 중단된다. 표를 고칠 때 깨진다."""
        for name, (_, cap, expected, _) in collect.TABLES.items():
            self.assertGreater(cap, expected, name)


class Deviation(unittest.TestCase):
    """관문 3 — 최신 스냅샷이 실측 기대치와 25% 넘게 어긋나면 멈춘다."""

    def setUp(self):
        self.expected = collect.TABLES["requirements"][2]

    def test_latest_snapshot_off_by_more_than_limit_aborts(self):
        c = make(self.expected * 0.7)
        with self.assertRaises(SystemExit):
            quiet(c.run_one, "requirements", SNAP, True)
        self.assertEqual(c.bq.executed, [])

    def test_allow_deviation_lets_it_through(self):
        c = make(self.expected * 0.7, plan=True, allow_deviation=True)
        self.assertEqual(quiet(c.run_one, "requirements", SNAP, True)["status"], "planned")

    def test_past_snapshot_is_not_compared(self):
        """과거 스냅샷은 크기가 다른 것이 정상이다. 여기 걸리면 T1 228 파티션을 못 받는다."""
        c = make(self.expected * 0.3, plan=True)
        self.assertEqual(quiet(c.run_one, "requirements", SNAP, False)["status"], "planned")


class SessionBudget(unittest.TestCase):
    """관문 4 — 한 실행의 누적 dry-run 이 예산을 넘기면 **그 잡 앞에서** 선다."""

    def test_job_that_would_cross_budget_is_not_run(self):
        c = make(0.3, budget_gib=0.5, rows=10, part_rows={("Projects", SNAP): 10})
        first = quiet(c.run_one, "projects", SNAP, False)
        second = quiet(c.run_one, "projects", "2026-08-24", False)
        self.assertEqual(first["status"], "done")
        self.assertEqual(second["status"], "stopped_budget")
        self.assertEqual(len(c.bq.executed), 1)
        # 못 돈 잡의 바이트는 누적에 넣지 않는다. 넣으면 요약의 dry-run 합계가 부푼다.
        self.assertEqual(c.cum_dry, int(0.3 * GiB))

    def test_plan_mode_never_bills(self):
        c = make(0.3, plan=True)
        self.assertEqual(quiet(c.run_one, "projects", SNAP, False)["status"], "planned")
        self.assertEqual(c.bq.executed, [])
        self.assertEqual(len(c.bq.dry_runs), 1)


class BilledCeiling(unittest.TestCase):
    """관문 5 — 실행 쿼리에 거는 상한. README 가 약속한 식이다."""

    def test_maximum_bytes_billed_is_dry_run_times_1_25_plus_512_mib(self):
        c = make(0.3, rows=10, part_rows={("Projects", SNAP): 10})
        quiet(c.run_one, "projects", SNAP, False)
        cfg = c.bq.executed[0]
        self.assertEqual(cfg.maximum_bytes_billed, int(int(0.3 * GiB) * 1.25) + 512 * MiB)
        self.assertFalse(cfg.use_query_cache)


class Idempotency(unittest.TestCase):
    """관문 1 — 받은 것을 다시 받지 않는다. 다시 받으면 같은 데이터에 두 번 과금된다."""

    def test_manifest_present_skips_without_touching_bigquery(self):
        c = make(0.3, manifest=True)
        rec = quiet(c.run_one, "projects", SNAP, False)
        self.assertEqual(rec["status"], "skipped_manifest_exists")
        self.assertEqual((c.bq.dry_runs, c.bq.executed), ([], []))


class ReuseStaging(unittest.TestCase):
    """쿼리는 끝났는데 extract 전에 끊긴 경우. 남은 스테이징 테이블을 재쿼리 없이 쓴다.

    2026-11-21 까지 이 경로는 매니페스트를 올린 뒤 마지막 로그 줄에서 죽었다 — 그 줄이
    재쿼리했을 때만 생기는 `job` 을 읽었다. 반출과 매니페스트는 끝난 뒤라 데이터는 온전했지만,
    예외가 올라가 그 뒤의 잡이 전부 돌지 않았다.
    """

    def test_reuses_staging_without_requery_and_finishes(self):
        c = make(0.3, rows=10, staged=True, part_rows={("Projects", SNAP): 10})
        rec = quiet(c.run_one, "projects", SNAP, False)
        self.assertEqual(c.bq.executed, [])
        self.assertEqual((rec["status"], rec["billed_bytes"], rec["job_id"]), ("done", 0, "reused_staging"))
        self.assertEqual(len(c.bq.extracted), 1)


class RowVerification(unittest.TestCase):
    """관문 6 — 반출한 행 수를 파티션 메타와 맞댄다."""

    def test_exact_mismatch_writes_manifest_then_aborts(self):
        c = make(0.3, rows=9, part_rows={("Projects", SNAP): 10})
        with self.assertRaises(SystemExit):
            quiet(c.run_one, "projects", SNAP, False)
        # 매니페스트는 남긴다. 무엇이 어긋났는지가 거기 있고, 다음 실행이 조용히 건너뛰지 않게
        # status 가 done 이 아니다.
        self.assertEqual(json.loads(c.blobs[("projects", SNAP)].uploaded)["status"], "done_verify_failed")

    def test_versions_are_checked_against_requirements_partition_within_1_percent(self):
        meta = {("NPMRequirements", SNAP): 1000, ("PackageVersions", SNAP): 5000}
        for table in ("versions_full", "versions_min"):
            dry = collect.TABLES[table][2]
            ok = make(dry, rows=1009, part_rows=meta)
            self.assertEqual(quiet(ok.run_one, table, SNAP, False)["verify"], "ok")
            bad = make(dry, rows=1011, part_rows=meta, continue_on_mismatch=True)
            self.assertEqual(quiet(bad.run_one, table, SNAP, False)["verify"], "MISMATCH")


if __name__ == "__main__":
    unittest.main()
