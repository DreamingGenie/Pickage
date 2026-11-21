"""downloads 변환기의 두 쓰기 경로가 같은 결과를 내는가.

  .venv-bq/Scripts/python.exe -m unittest discover -s pipeline/collectors/downloads -v

--low-memory 는 46.9만 확장 때 기본 경로가 3.3억 행을 못 써서 생겼다. 그때는 워크로그의 별도
스크립트로 돌렸고 두 경로를 맞대 본 적이 없었다. 이 시험이 깨지면 알게 되는 것:

  - 두 경로가 다른 행·다른 값을 쓴다 (같은 수집분인데 어느 옵션으로 변환했는지에 따라 적재 값이 달라진다)
  - 저메모리 경로가 다시 변환할 때 지난 파일을 남겨 같은 날짜가 두 번 읽힌다
  - 저메모리 경로가 잘린 part 복구를 건너뛴다 (워크로그 판은 복구 로직이 없었다)
"""
import gzip
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO

import duckdb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import to_parquet  # noqa: E402


def record(name, days, fetched="2026-09-02T00:00:00", status="ok", tier="A"):
    return {"name": name, "rank": 1, "kind": "bulk", "start": "2026-08-01", "end": "2026-08-20", "tier": tier,
            "fetched_at": fetched, "task_id": f"t-{name}", "status": status,
            "downloads": [{"downloads": n, "day": d} for d, n in days]}


def days(values, start=1):
    return [(f"2026-08-{start + i:02d}", v) for i, v in enumerate(values)]


def write_part(raw, idx, records):
    path = os.path.join(raw, f"part-{idx:05d}.jsonl.gz")
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return path


def sample_parts(raw):
    """결손 규칙·중복 제거·NOT_FOUND 가 모두 걸리는 최소 입력."""
    busy = [5000] * 20
    busy[9] = 0                       # 전후 중앙값이 1000 이상인 0 → NULL + imputed_gap
    write_part(raw, 0, [
        record("busy", days(busy)),
        record("quiet", days([0, 3, 0, 2, 0, 1, 0, 0])),          # 중앙값이 작아 0 을 그대로 둔다
        record("refetched", days([10, 10, 10]), fetched="2026-09-01T00:00:00"),
    ])
    write_part(raw, 1, [
        record("refetched", days([20, 20, 20]), fetched="2026-09-03T00:00:00"),   # 나중에 받은 값이 이긴다
        record("gone", [], status="not_found"),
    ])


def read_back(out):
    con = duckdb.connect()
    glob = os.path.join(out, "downloads", "*", "*.parquet").replace(os.sep, "/")
    rows = con.execute(
        f"""SELECT CAST(date AS DATE), name, downloads, imputed_gap, tier, fetched_at
            FROM read_parquet('{glob}', hive_partitioning=true) ORDER BY 1, 2""").fetchall()
    st = os.path.join(out, "downloads_status.parquet").replace(os.sep, "/")
    status = con.execute(f"SELECT * FROM read_parquet('{st}') ORDER BY name").fetchall()
    con.close()
    return rows, status


def convert(raw, out, **kw):
    with redirect_stdout(StringIO()):
        to_parquet.convert(raw, out, mem="1GB", threads=2, **kw)


class Equivalence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.raw = os.path.join(self.tmp, "raw")
        os.makedirs(self.raw)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def out(self, name):
        return os.path.join(self.tmp, name)

    def test_both_paths_write_the_same_rows_and_status(self):
        sample_parts(self.raw)
        convert(self.raw, self.out("a"))
        convert(self.raw, self.out("b"), low_memory=True)
        rows_a, status_a = read_back(self.out("a"))
        rows_b, status_b = read_back(self.out("b"))
        self.assertEqual(rows_a, rows_b)
        self.assertEqual(status_a, status_b)
        # 입력이 규칙을 실제로 건드렸는지. 비어 있는 두 결과도 서로 같다.
        gaps = [r for r in rows_a if r[3]]
        self.assertEqual([(str(r[0]), r[1], r[2]) for r in gaps], [("2026-08-10", "busy", None)])
        self.assertEqual({r[2] for r in rows_a if r[1] == "refetched"}, {20})
        self.assertEqual([(s[0], s[2]) for s in status_a if s[0] == "gone"], [("gone", "NOT_FOUND")])

    def test_low_memory_rerun_replaces_matching_dates_and_keeps_others(self):
        sample_parts(self.raw)
        out = self.out("b")
        convert(self.raw, out, low_memory=True)
        rows_first, _ = read_back(out)
        # 지난 변환이 다른 이름으로 남긴 파일과, 이번 입력에 없는 날짜의 폴더를 심는다.
        day = os.path.join(out, "downloads", "date=2026-08-01")
        shutil.copy(os.path.join(day, os.listdir(day)[0]), os.path.join(day, "part-99.parquet"))
        other = os.path.join(out, "downloads", "date=2026-07-01")
        shutil.copytree(day, other)
        n_other = len(read_back(out)[0]) - len(rows_first) - len([r for r in rows_first if str(r[0]) == "2026-08-01"])
        convert(self.raw, out, low_memory=True)
        rows_again, _ = read_back(out)
        self.assertEqual([r for r in rows_again if str(r[0]) != "2026-07-01"], rows_first)
        self.assertEqual(len([r for r in rows_again if str(r[0]) == "2026-07-01"]), n_other)
        self.assertFalse(os.path.exists(os.path.join(out, "_work.duckdb")))
        self.assertFalse(os.path.exists(os.path.join(out, "_duckdb_tmp")))

    def test_low_memory_repairs_truncated_part_like_the_default_path(self):
        sample_parts(self.raw)
        # 가운데 part 를 자른다. 최신이 아니므로 "쓰는 중"이 아니라 복구 대상이다.
        broken = write_part(self.raw, 2, [record("late", days([7, 7, 7]))])
        write_part(self.raw, 3, [record("last", days([1]))])
        with open(broken, "rb") as f:
            data = f.read()
        with open(broken, "wb") as f:
            f.write(data[:-6])
        shutil.copytree(self.raw, self.raw + "2")
        convert(self.raw, self.out("a"))
        convert(self.raw + "2", self.out("b"), low_memory=True)
        self.assertEqual(read_back(self.out("a")), read_back(self.out("b")))
        self.assertTrue(os.path.exists(os.path.join(self.raw + "2", "part-00002.jsonl.gz.broken")))


if __name__ == "__main__":
    unittest.main()
