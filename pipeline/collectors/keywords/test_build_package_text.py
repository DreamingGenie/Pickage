"""build_package_text.py 단위 시험 — download_rank 조인만 본다 (S15P21A506-402).

  .venv-bq/Scripts/python.exe -m unittest discover -s pipeline/collectors/keywords -v

이 폴더에는 __init__.py 가 없어 패키지 경로로는 import 되지 않는다. discover 가 이 폴더를
sys.path 에 올려 주므로 `import build_package_text` 로 쓴다(registry/test_collect.py와 같은 관례).

`main()` 하나가 전체 파이프라인이라 함수를 쪼개 부르지 않고, 실제 CLI처럼 --run·--raw·
--rank-list 를 임시 디렉터리로 채워 통째로 돌린 뒤 출력 parquet만 검사한다. 이 스크립트의
다른 단계(스팸 판정·description 우선순위 등)는 이번 변경과 무관해 건드리지 않는다.
"""
import gzip
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import duckdb  # noqa: E402

import build_package_text as bpt  # noqa: E402


def _record(name, rank, **overrides):
    """collect_keywords.py의 slim()이 내는 것과 같은 모양의 최소 레코드.

    `raw` 테이블이 SELECT하는 모든 열을 채워 둔다 — DuckDB read_json은 어떤 파일에도
    나타나지 않는 열은 union_by_name으로도 만들어 주지 않는다(전부 없으면 그냥 없는 열).
    """
    r = {
        "rank": rank, "name": name, "namespace": None, "description": "d",
        "keywords": [], "downloads_last_month": 1, "downloads_period": "last-month",
        "dependent_packages_count": 0, "dependent_repos_count": 0, "versions_count": 1,
        "latest_release_number": "1.0.0", "latest_release_published_at": "2026-01-01T00:00:00Z",
        "first_release_published_at": "2026-01-01T00:00:00Z", "licenses": None, "status": None,
        "repository_url": None, "homepage": None, "maintainers_count": 1,
        "last_synced_at": "2026-01-01T00:00:00Z", "repo_metadata_updated_at": None,
        # topics를 빈 리스트로 둔다 — 전 행이 repo=NULL이면 repo.topics 열 자체가 타입을
        # 못 잡아 list_transform이 바인딩 에러를 낸다(DuckDB read_json 타입 추론 한계).
        "repo": {"full_name": None, "description": None, "topics": [], "language": None,
                 "stargazers_count": 0, "forks_count": 0, "archived": False, "fork": False,
                 "pushed_at": None, "default_branch": None, "license": None},
        "page": 1, "fetched_at": "2026-01-01T00:00:00Z",
    }
    r.update(overrides)
    return r


def _write_raw(path, rows):
    """raw jsonl.gz 한 파트를 만든다."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _write_rank_list(path, rows):
    """name,rank CSV. build_package_dependents.py의 대상 목록과 같은 최소 스키마."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("rank,name\n")
        for rank, name in rows:
            f.write(f"{rank},{name}\n")


class DownloadRankJoin(unittest.TestCase):
    def _run(self, raw_rows, rank_rows):
        with tempfile.TemporaryDirectory() as d:
            _write_raw(os.path.join(d, "raw", "run=t", "part-00001.jsonl.gz"), raw_rows)
            rank_list = os.path.join(d, "rank_list.csv")
            _write_rank_list(rank_list, rank_rows)
            out = os.path.join(d, "out")
            argv = ["build_package_text.py", "--run", "t",
                    "--raw", os.path.join(d, "raw"),
                    "--out", out, "--no-depsdev",
                    "--rank-list", rank_list]
            old_argv = sys.argv
            sys.argv = argv
            try:
                bpt.main()
            finally:
                sys.argv = old_argv
            con = duckdb.connect()
            got = con.sql(
                f"SELECT name, rank, download_rank FROM read_parquet('{out}/package_text_t.parquet') ORDER BY name"
            ).fetchall()
            return {name: (rank, download_rank) for name, rank, download_rank in got}

    def test_name_in_rank_list_gets_download_rank(self):
        rows = self._run(
            raw_rows=[_record("in-scope-a", 1)],
            rank_rows=[(1, "in-scope-a")],
        )
        self.assertEqual(rows["in-scope-a"][1], 1)

    def test_name_outside_rank_list_is_null(self):
        rows = self._run(
            raw_rows=[_record("out-of-scope-b", 2)],
            rank_rows=[(1, "in-scope-a")],
        )
        self.assertIsNone(rows["out-of-scope-b"][1])

    def test_duplicate_name_in_rank_list_keeps_lower_rank(self):
        """대상 목록에 같은 이름이 여러 행이면 순위가 낮은(=상위) 쪽만 남는다."""
        rows = self._run(
            raw_rows=[_record("dup-name", 3)],
            rank_rows=[(50, "dup-name"), (5, "dup-name")],
        )
        self.assertEqual(rows["dup-name"][1], 5)

    def test_live_rank_column_untouched(self):
        """기존 rank(그날 재계산된 순위)는 download_rank와 별개로 그대로 보존된다."""
        rows = self._run(
            raw_rows=[_record("in-scope-a", 7)],
            rank_rows=[(1, "in-scope-a")],
        )
        self.assertEqual(rows["in-scope-a"][0], 7)
        self.assertEqual(rows["in-scope-a"][1], 1)


if __name__ == "__main__":
    unittest.main()
