"""backfill_download_rank.py 단위 시험 (S15P21A506-402).

  .venv-bq/Scripts/python.exe -m unittest discover -s pipeline/collectors/keywords -v

이 폴더에는 __init__.py 가 없어 discover 가 이 폴더를 sys.path 에 올려 준다
(test_build_package_text.py·registry/test_collect.py 와 같은 관례).
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import duckdb  # noqa: E402
import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

import backfill_download_rank as bdr  # noqa: E402


def _write_rank_list(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        f.write("rank,name\n")
        for rank, name in rows:
            f.write(f"{rank},{name}\n")


def _write_package_text(path, names, extra_columns=None):
    data = {"name": names, "description": [f"d-{n}" for n in names]}
    if extra_columns:
        data.update(extra_columns)
    pq.write_table(pa.table(data), path)


class BackfillDownloadRank(unittest.TestCase):
    def _run(self, argv):
        old_argv = sys.argv
        sys.argv = ["backfill_download_rank.py"] + argv
        try:
            bdr.main()
        finally:
            sys.argv = old_argv

    def test_adds_download_rank_from_rank_list(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "in.parquet")
            out = os.path.join(d, "out.parquet")
            rank_list = os.path.join(d, "rank.csv")
            _write_package_text(src, ["in-scope-a", "out-of-scope-b"])
            _write_rank_list(rank_list, [(1, "in-scope-a")])

            self._run(["--in", src, "--out", out, "--rank-list", rank_list])

            con = duckdb.connect()
            got = dict(con.sql(f"SELECT name, download_rank FROM read_parquet('{out}')").fetchall())
        self.assertEqual(got["in-scope-a"], 1)
        self.assertIsNone(got["out-of-scope-b"])

    def test_other_columns_and_row_count_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "in.parquet")
            out = os.path.join(d, "out.parquet")
            rank_list = os.path.join(d, "rank.csv")
            _write_package_text(src, ["a", "b"], {"rank": [5, 9], "is_spam": [False, True]})
            _write_rank_list(rank_list, [(1, "a")])

            self._run(["--in", src, "--out", out, "--rank-list", rank_list])

            con = duckdb.connect()
            got = con.sql(
                f"SELECT name, rank, is_spam, download_rank FROM read_parquet('{out}') ORDER BY name"
            ).fetchall()
        self.assertEqual(got, [("a", 5, False, 1), ("b", 9, True, None)])

    def test_refuses_same_input_and_output_path(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "same.parquet")
            rank_list = os.path.join(d, "rank.csv")
            _write_package_text(src, ["a"])
            _write_rank_list(rank_list, [(1, "a")])

            with self.assertRaises(SystemExit):
                self._run(["--in", src, "--out", src, "--rank-list", rank_list])

    def test_refuses_when_download_rank_already_exists_without_flag(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "in.parquet")
            out = os.path.join(d, "out.parquet")
            rank_list = os.path.join(d, "rank.csv")
            _write_package_text(src, ["a"], {"download_rank": [999]})
            _write_rank_list(rank_list, [(1, "a")])

            with self.assertRaises(SystemExit):
                self._run(["--in", src, "--out", out, "--rank-list", rank_list])

    def test_overwrite_flag_replaces_existing_download_rank(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "in.parquet")
            out = os.path.join(d, "out.parquet")
            rank_list = os.path.join(d, "rank.csv")
            _write_package_text(src, ["a"], {"download_rank": [999]})
            _write_rank_list(rank_list, [(1, "a")])

            self._run(["--in", src, "--out", out, "--rank-list", rank_list,
                       "--overwrite-existing-column"])

            con = duckdb.connect()
            got = con.sql(f"SELECT download_rank FROM read_parquet('{out}')").fetchone()[0]
        self.assertEqual(got, 1)


if __name__ == "__main__":
    unittest.main()
