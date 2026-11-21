"""이동쌍의 "도착지가 출발지의 의존인가" 판정의 계약.

깨지면 알게 되는 것 — 방향이 뒤집혔거나(Y 가 X 에 의존하는 것을 X 가 Y 에 의존한다고 센다),
"그때의 대표 릴리스"가 아니라 아무 릴리스나 보고 있거나, 대표를 발행 순서로 고르고 있는 것.
셋 다 README 의 비율을 그럴듯한 다른 숫자로 바꾼다.

전수 실행은 원천 11 GB 를 읽는다. 여기서는 판정 SQL 만 합성 입력에 적용한다.

    .venv-bq/Scripts/python.exe pipeline/duckdb/test_transitive_dependency_axis.py
"""
from pathlib import Path
import sys
import unittest

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from transitive_dependency_axis import SUMMARY_SQL, TOP1_SQL, judge  # noqa: E402


def make(pairs, req, ver):
    """pairs: (tier, from, to, votes, last_seen) · req: (pkg, version, dep) · ver: (pkg, version, ordinal, published)"""
    con = duckdb.connect()
    con.execute("CREATE TABLE pairs(tier VARCHAR, from_pkg VARCHAR, to_pkg VARCHAR, votes DOUBLE, last_seen DATE)")
    con.execute("CREATE TABLE req(Name VARCHAR, Version VARCHAR, dep VARCHAR)")
    con.execute("CREATE TABLE ver(Name VARCHAR, Version VARCHAR, ordinal BIGINT, published_at TIMESTAMP)")
    con.executemany("INSERT INTO pairs VALUES (?, ?, ?, ?, ?)", pairs)
    con.executemany("INSERT INTO req VALUES (?, ?, ?)", req)
    con.executemany("INSERT INTO ver VALUES (?, ?, ?, ?)", ver)
    judge(con)
    return con


def flags(con, frm, to):
    return con.execute(
        "SELECT dep_ever, dep_at_time, reverse_ever FROM judged WHERE from_pkg = ? AND to_pkg = ?",
        [frm, to]).fetchone()


class Direction(unittest.TestCase):
    def test_from_depends_on_to_is_not_confused_with_the_reverse(self):
        con = make(
            pairs=[("all", "rxjs", "tslib", 273.0, "2026-07-19"),      # rxjs 가 tslib 에 의존 → 딸려 온 부품
                   ("all", "lit-html", "lit", 229.0, "2026-04-30"),    # lit 이 lit-html 에 의존 → 감싼 후속
                   ("all", "moment", "dayjs", 347.4, "2026-08-26")],   # 서로 무관
            req=[("rxjs", "7.5.1", "tslib"), ("lit", "3.0.0", "lit-html")],
            ver=[("rxjs", "7.5.1", 10, "2022-01-01"), ("lit", "3.0.0", 5, "2023-10-10"),
                 ("lit-html", "3.0.0", 5, "2023-10-10"), ("moment", "2.30.1", 9, "2023-12-27")])
        self.assertEqual(flags(con, "rxjs", "tslib"), (True, True, False))
        self.assertEqual(flags(con, "lit-html", "lit"), (False, False, True))
        self.assertEqual(flags(con, "moment", "dayjs"), (False, False, False))


class AtTime(unittest.TestCase):
    """ever 는 넓고 at_time 은 좁다. 둘이 같아지면 두 번째 열이 정보를 잃는다."""

    def test_dependency_added_after_the_moves_ended_counts_as_ever_only(self):
        con = make(
            pairs=[("all", "x", "y", 5.0, "2020-06-30")],
            req=[("x", "2.0.0", "y")],                                  # 이동이 끝난 뒤에야 y 에 의존
            ver=[("x", "1.0.0", 1, "2019-01-01"), ("x", "2.0.0", 2, "2021-01-01")])
        self.assertEqual(flags(con, "x", "y"), (True, False, False))

    def test_representative_is_highest_ordinal_not_latest_published(self):
        """1.x 백포트가 나중에 나와도 그날의 대표는 2.0.0 이다. 발행 순으로 고르면 뒤집힌다."""
        con = make(
            pairs=[("all", "x", "y", 5.0, "2021-12-31")],
            req=[("x", "1.9.9", "y")],                                  # 옛 메이저만 y 에 의존
            ver=[("x", "2.0.0", 20, "2021-01-01"), ("x", "1.9.9", 19, "2021-06-01")])
        self.assertEqual(flags(con, "x", "y"), (True, False, False))

    def test_release_published_on_last_seen_day_is_included(self):
        con = make(
            pairs=[("all", "x", "y", 5.0, "2021-06-01")],
            req=[("x", "1.0.0", "y")],
            ver=[("x", "1.0.0", 1, "2021-06-01 18:00:00")])            # last_seen 은 날짜라 그날 끝까지 본다
        self.assertEqual(flags(con, "x", "y"), (True, True, False))


class Summary(unittest.TestCase):
    def test_tiers_are_counted_separately_and_top1_follows_votes(self):
        con = make(
            pairs=[("all", "x", "bundled", 9.0, "2021-12-31"), ("all", "x", "real", 3.0, "2021-12-31"),
                   ("strict", "x", "bundled", 9.0, "2021-12-31")],
            req=[("x", "1.0.0", "bundled")],
            ver=[("x", "1.0.0", 1, "2020-01-01")])
        self.assertEqual({r[0]: r[1:4] for r in con.execute(SUMMARY_SQL).fetchall()},
                         {"all": (2, 1, 1), "strict": (1, 1, 1)})
        # x 의 1위(votes 최대)가 딸려 온 부품이다.
        self.assertEqual({r[0]: r[1:] for r in con.execute(TOP1_SQL).fetchall()},
                         {"all": (1, 1, 1), "strict": (1, 1, 1)})


if __name__ == "__main__":
    unittest.main()
