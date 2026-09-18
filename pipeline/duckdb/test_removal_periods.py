"""구간별 이탈 사유 집계의 계약 (S15P21A506-378).

깨지면 알게 되는 것 — 구간 경계가 밀렸거나, 겹치는 구간을 배타적으로 세고 있거나,
대체 동반/대체 없음의 판정이 뒤집힌 것. 셋 다 **화면에는 그럴듯한 숫자로** 나타난다.

전수 실행은 30분이라 틀린 채로 돌리면 그만큼 날린다. 여기서 먼저 거른다.

    .venv-bq/Scripts/python.exe pipeline/duckdb/test_removal_periods.py
"""
from pathlib import Path
import sys
import unittest

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from removal_periods import (  # noqa: E402
    PERIODS, REMOVAL_BY_PERIOD_SQL, T2, build_periods, require_monotonic)


def make(rows):
    """rows: (Name, to_ts, removed[], added[]) → removal_by_period 를 만든 연결을 돌려준다."""
    con = duckdb.connect()
    con.execute("CREATE TABLE trans(Name VARCHAR, to_ts TIMESTAMP, "
                "removed VARCHAR[], added VARCHAR[])")
    for name, ts, removed, added in rows:
        con.execute("INSERT INTO trans VALUES (?, ?, ?, ?)", [name, ts, removed, added])
    build_periods(con)
    con.execute(REMOVAL_BY_PERIOD_SQL)
    return con


def counts(con, period, pkg):
    row = con.execute("""SELECT removals, removals_no_replacement, removals_with_replacement,
                                dependents
                         FROM removal_by_period WHERE period = ? AND removed_pkg = ?""",
                      [period, pkg]).fetchone()
    return row or (0, 0, 0, 0)


class Windows(unittest.TestCase):
    """구간은 T2 에서 끝나고 서로 겹친다."""

    def test_구간이_겹쳐서_최근_건은_셋_다에_들어간다(self):
        con = make([("app", "2026-06-01 00:00:00", ["x"], [])])
        for period in ("1y", "3y", "5y"):
            self.assertEqual(counts(con, period, "x")[0], 1, period)

    def test_오래된_건은_긴_구간에만_들어간다(self):
        # 4년 전 = 1y·3y 밖, 5y 안
        con = make([("app", "2022-06-01 00:00:00", ["x"], [])])
        self.assertEqual(counts(con, "1y", "x")[0], 0)
        self.assertEqual(counts(con, "3y", "x")[0], 0)
        self.assertEqual(counts(con, "5y", "x")[0], 1)

    def test_T2_를_넘으면_어느_구간에도_안_들어간다(self):
        """원천에 스냅샷 경계 뒤 발행분이 섞여 있다. 그것까지 세면 유지·유입·이탈과 기준이 갈린다."""
        con = make([("app", "2026-09-01 00:00:00", ["x"], [])])
        for period in ("1y", "3y", "5y"):
            self.assertEqual(counts(con, period, "x")[0], 0, period)

    def test_경계는_t1_제외_t2_포함이다(self):
        con = make([("a", PERIODS["1y"], ["x"], []),   # t1 정각 = 제외
                    ("b", T2, ["x"], [])])             # t2 정각 = 포함
        self.assertEqual(counts(con, "1y", "x")[0], 1)


class Reason(unittest.TestCase):
    """대체 동반 / 대체 없음."""

    def test_아무것도_안_넣었으면_대체_없음이다(self):
        con = make([("app", "2026-06-01 00:00:00", ["x"], [])])
        _, no_repl, with_repl, _ = counts(con, "1y", "x")
        self.assertEqual((no_repl, with_repl), (1, 0))

    def test_같은_전이에서_뭔가_넣었으면_대체_동반이다(self):
        con = make([("app", "2026-06-01 00:00:00", ["x"], ["y"])])
        _, no_repl, with_repl, _ = counts(con, "1y", "x")
        self.assertEqual((no_repl, with_repl), (0, 1))

    def test_added_가_NULL_이어도_대체_없음으로_센다(self):
        """len(NULL) 은 NULL 이라 coalesce 가 없으면 어느 쪽에도 안 잡혀 합이 안 맞는다."""
        con = make([("app", "2026-06-01 00:00:00", ["x"], None)])
        total, no_repl, with_repl, _ = counts(con, "1y", "x")
        self.assertEqual((total, no_repl, with_repl), (1, 1, 0))

    def test_한_전이에서_둘을_빼면_각각_한_건이다(self):
        con = make([("app", "2026-06-01 00:00:00", ["x", "z"], ["y"])])
        self.assertEqual(counts(con, "1y", "x")[0], 1)
        self.assertEqual(counts(con, "1y", "z")[0], 1)

    def test_dependents_는_중복을_접는다(self):
        """같은 패키지가 여러 번 뺐다 넣었다 해도 의존자 수는 1 이다.
        removals(전이 건수)와 dependents(패키지 수)의 단위가 다르다는 것이 이 표의 핵심이다."""
        con = make([("app", "2026-05-01 00:00:00", ["x"], []),
                    ("app", "2026-06-01 00:00:00", ["x"], ["y"])])
        total, _, _, dependents = counts(con, "1y", "x")
        self.assertEqual((total, dependents), (2, 1))


class Monotonic(unittest.TestCase):
    """검산 — 구간이 겹치므로 1y ≤ 3y ≤ 5y ≤ 전체."""

    def _with_stats(self, con, pkg, total):
        con.execute("CREATE OR REPLACE TABLE removal_stats AS "
                    "SELECT ? AS removed_pkg, ? AS removals_total", [pkg, total])
        return con

    def test_정상이면_통과한다(self):
        con = make([("app", "2026-06-01 00:00:00", ["x"], []),
                    ("app", "2022-06-01 00:00:00", ["x"], [])])
        require_monotonic(self._with_stats(con, "x", 2))  # 1y=1 ≤ 3y=1 ≤ 5y=2 ≤ 2

    def test_전체보다_많으면_멈춘다(self):
        """구간 합이 전 기간 총수를 넘을 수 없다. 넘으면 경계나 조인이 틀린 것이다."""
        con = make([("app", "2026-06-01 00:00:00", ["x"], [])])
        with self.assertRaises(SystemExit):
            require_monotonic(self._with_stats(con, "x", 0))

    def test_포함관계가_뒤집히면_멈춘다(self):
        con = make([("app", "2026-06-01 00:00:00", ["x"], [])])
        # 1y 를 손으로 부풀려 3y 보다 크게 만든다
        con.execute("UPDATE removal_by_period SET removals = 99 WHERE period = '1y'")
        with self.assertRaises(SystemExit):
            require_monotonic(self._with_stats(con, "x", 99))


class Boundary(unittest.TestCase):
    """구간 경계가 유지·유입·이탈과 같은 값인가."""

    def test_T2_와_구간_시작이_그쪽에서_온다(self):
        con = duckdb.connect()
        build_periods(con)
        rows = dict((p, (str(a), str(b))) for p, a, b in
                    con.execute("SELECT period, t1, t2 FROM periods").fetchall())
        self.assertEqual(set(rows), {"1y", "3y", "5y"})
        for period, (t1, t2) in rows.items():
            self.assertEqual(t1, PERIODS[period])
            self.assertEqual(t2, T2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
