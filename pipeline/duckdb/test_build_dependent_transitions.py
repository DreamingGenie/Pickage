"""판정표 5칸이 계약이다 (S15P21A506-195).

**깨지면 알게 되는 것** — 관측 불가가 유지로 새거나, 유입·이탈이 활성 판정을 잘못 타는 것.
그 둘은 화면 숫자를 직접 거짓으로 만든다. 1년 구간에서 npm 전수의 76% 가 관측 불가라
이 경계 하나가 유지율을 수십 %p 움직인다.

빌더 전체를 돌리지 않는다. 원천 11 GB 를 읽지 않고 `CLASSIFY_SQL` 만 합성 입력에 적용한다.
빌더가 그 상수를 쓰므로 계약이 바뀌면 여기가 따라 깨지는 것이 맞다.

    .venv-bq/Scripts/python.exe pipeline/duckdb/test_build_dependent_transitions.py
"""
from pathlib import Path
import sys
import unittest

import duckdb

# pipeline/duckdb 는 패키지가 아니라 스크립트 폴더다 (__init__.py 없음).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_dependent_transitions import (  # noqa: E402
    CLASSIFY_SQL, KINDS, REP_AT_SQL, REP_SQL)

PERIOD = "1y"
T1 = "2025-08-31 23:59:59"


def setup(decl, moved, targets=("x",), first_rel=None):
    """decl: (dependent, point, target, kind) · moved: (dependent, period)

    first_rel 을 생략하면 모든 dependent 가 **T1 보다 훨씬 전에 생긴 것**으로 본다.
    유입 세부를 시험하지 않는 케이스에서 is_new 가 끼어들지 않게 하려는 기본값이다.
    """
    con = duckdb.connect()
    con.execute("CREATE TABLE periods(period VARCHAR, t1 TIMESTAMP)")
    con.execute("INSERT INTO periods VALUES (?, ?)", [PERIOD, T1])
    con.execute("CREATE TABLE first_rel(dependent VARCHAR, first_release TIMESTAMP)")
    if first_rel is None:
        # dependent 당 한 줄이어야 한다. 중복이 있으면 cls_m 의 조인이 행을 복제해
        # 모든 범주가 배로 불어난다 (빌더 쪽은 GROUP BY 라 중복이 생기지 않는다).
        first_rel = [(d, "2000-01-01 00:00:00")
                     for d in dict.fromkeys(x[0] for x in (decl or []))]
    if first_rel:
        con.executemany("INSERT INTO first_rel VALUES (?, ?)", first_rel)
    con.execute("CREATE TABLE tgt(name VARCHAR, download_rank INTEGER)")
    con.executemany("INSERT INTO tgt VALUES (?, NULL)", [(t,) for t in targets])
    con.execute("CREATE TABLE decl(dependent VARCHAR, point VARCHAR, target VARCHAR, kind VARCHAR)")
    if decl:
        con.executemany("INSERT INTO decl VALUES (?, ?, ?, ?)", decl)
    con.execute("CREATE TABLE moved(dependent VARCHAR, period VARCHAR)")
    if moved:
        con.executemany("INSERT INTO moved VALUES (?, ?)", moved)
    con.execute(CLASSIFY_SQL, {"kinds": list(KINDS)})
    return con


def counts(con, target="x", kind="regular"):
    return con.execute(
        "SELECT retained, inflow, outflow, unobserved FROM agg"
        " WHERE period = ? AND target = ? AND kind = ?", [PERIOD, target, kind]).fetchone()


class ClassificationTable(unittest.TestCase):
    """docstring 의 다섯 줄을 그대로 옮긴 것이다."""

    def test_네_범주가_각각_한_칸씩_잡힌다(self):
        con = setup(
            decl=[
                # A=T B=T — 양 끝에 선언이 있다
                ("keep", PERIOD, "x", "regular"), ("keep", "t2", "x", "regular"),
                ("dormant", PERIOD, "x", "regular"), ("dormant", "t2", "x", "regular"),
                # A=F B=T — 구간 안에 새로 넣었다
                ("new", "t2", "x", "regular"),
                # A=T B=F — 구간 안에 뺐다
                ("gone", PERIOD, "x", "regular"),
            ],
            # dormant 만 구간 안에 대표 릴리스가 바뀌지 않았다
            moved=[("keep", PERIOD), ("new", PERIOD), ("gone", PERIOD)])
        self.assertEqual(counts(con), (1, 1, 1, 1))

    def test_대표가_안_바뀌면_유지가_아니라_관측_불가다(self):
        """이 시험이 이 파일의 존재 이유다. moved 한 줄만 빼면 유지가 관측 불가가 된다."""
        decl = [("d", PERIOD, "x", "regular"), ("d", "t2", "x", "regular")]
        self.assertEqual(counts(setup(decl, moved=[("d", PERIOD)])), (1, 0, 0, 0))
        self.assertEqual(counts(setup(decl, moved=[])), (0, 0, 0, 1))

    def test_양쪽_다_선언이_없으면_어느_범주도_아니다(self):
        # 구간 중간에 넣었다 뺀 경우가 여기 해당한다. 네 범주 어디에도 들어가지 않는다.
        con = setup(decl=[("churned", "3y", "x", "regular")],
                    moved=[("churned", PERIOD)])
        self.assertEqual(counts(con), (0, 0, 0, 0))

    def test_kind_가_섞이지_않는다(self):
        con = setup(
            decl=[("a", PERIOD, "x", "regular"), ("a", "t2", "x", "regular"),
                  ("a", "t2", "x", "peer")],
            moved=[("a", PERIOD)])
        self.assertEqual(counts(con, kind="regular"), (1, 0, 0, 0))
        self.assertEqual(counts(con, kind="peer"), (0, 1, 0, 0))
        self.assertEqual(counts(con, kind="optional"), (0, 0, 0, 0))

    def test_dependent_가_없는_대상도_행이_남는다(self):
        """행을 빼면 받는 쪽에서 '조회 실패' 와 'dependent 가 없음' 을 구분할 수 없다."""
        con = setup(decl=[("a", "t2", "x", "regular")], moved=[("a", PERIOD)],
                    targets=("x", "y"))
        self.assertEqual(counts(con, target="y"), (0, 0, 0, 0))
        rows = con.execute("SELECT count(*) FROM agg").fetchone()[0]
        self.assertEqual(rows, 2 * len(KINDS))  # 대상 2 × kind 3 × 구간 1


class RepresentativeRelease(unittest.TestCase):
    """대표는 ordinal 이 정한다. published_at 은 **시점 필터에만** 쓴다.

    2026-09-17 실측 — 대표를 `arg_max(Version, published_at)` 로 고르던 판에서 150개
    패키지가 잘못된 대표를 잡았다. 같은 발행시각에 전환점이 둘 이상인 그룹이 1,001개
    (699 패키지) 있어 무엇이 뽑힐지 정해지지 않았기 때문이다. 교차 대조에서 46 엣지가
    설명되지 않아 드러났다.
    """

    def rep(self, rows):
        """rows: (Name, Version, published_at, ordinal, is_release)"""
        con = duckdb.connect()
        con.execute("CREATE TABLE v(Name VARCHAR, Version VARCHAR, published_at TIMESTAMP,"
                    " ordinal BIGINT, is_release BOOLEAN)")
        con.executemany("INSERT INTO v VALUES (?, ?, ?, ?, ?)", rows)
        con.execute(REP_SQL.format(source="v"))
        return con

    def at(self, con, t):
        con.execute("CREATE OR REPLACE TABLE rep_pt(Name VARCHAR, point VARCHAR, Version VARCHAR)")
        con.execute(REP_AT_SQL, {"point": "t", "t": t})
        return con.execute("SELECT Name, Version FROM rep_pt ORDER BY Name").fetchall()

    def test_같은_발행시각이면_ordinal_이_높은_쪽이_대표다(self):
        """이 시험이 잡는 버그다. 발행시각으로 고르면 둘 중 무엇이 나올지 정해지지 않는다."""
        con = self.rep([("p", "1.0.0", "2024-01-01 00:00:00", 1, True),
                        ("p", "2.0.0", "2024-01-01 00:00:00", 2, True)])
        self.assertEqual(self.at(con, "2026-08-31 23:59:59"), [("p", "2.0.0")])

    def test_유지보수_릴리스는_대표를_바꾸지_않는다(self):
        """5.0.0 뒤에 나온 4.17.3 이 최신으로 잡히면 안 된다. 전환점에서도 빠진다."""
        con = self.rep([("p", "4.17.2", "2024-01-01 00:00:00", 10, True),
                        ("p", "5.0.0", "2024-06-01 00:00:00", 20, True),
                        ("p", "4.17.3", "2024-09-01 00:00:00", 15, True)])
        self.assertEqual(self.at(con, "2026-08-31 23:59:59"), [("p", "5.0.0")])
        # 전환점은 둘뿐이다 — 4.17.3 은 대표를 바꾸지 않았으므로 M 판정에도 기여하지 않는다
        self.assertEqual(con.execute("SELECT count(*) FROM rep").fetchone()[0], 2)

    def test_시점_필터는_그_시각_이하만_본다(self):
        con = self.rep([("p", "1.0.0", "2020-01-01 00:00:00", 1, True),
                        ("p", "2.0.0", "2026-01-01 00:00:00", 2, True)])
        self.assertEqual(self.at(con, "2021-08-31 23:59:59"), [("p", "1.0.0")])
        self.assertEqual(self.at(con, "2026-08-31 23:59:59"), [("p", "2.0.0")])

    def test_릴리스가_아니거나_발행일이_없거나_번들_경로면_뺀다(self):
        con = self.rep([
            ("p", "1.0.0", "2024-01-01 00:00:00", 1, True),
            ("p", "2.0.0-beta", "2024-02-01 00:00:00", 2, False),   # 릴리스 아님
            ("p", "3.0.0", None, 3, True),                          # 발행일 없음
            ("a>1.0.0>b", "9.9.9", "2024-03-01 00:00:00", 9, True),  # 번들 경로 노드
        ])
        self.assertEqual(self.at(con, "2026-08-31 23:59:59"), [("p", "1.0.0")])


class InflowSplit(unittest.TestCase):
    """유입은 한 덩어리가 아니다. T1 때 없던 패키지의 유입은 채택이 아니라 생태계 성장이다."""

    def split(self, first_rel):
        con = setup(decl=[("adopter", "t2", "x", "regular"),
                          ("newborn", "t2", "x", "regular")],
                    moved=[("adopter", PERIOD), ("newborn", PERIOD)],
                    first_rel=first_rel)
        return con.execute(
            "SELECT inflow, inflow_new FROM agg WHERE period = ? AND target = 'x'"
            " AND kind = 'regular'", [PERIOD]).fetchone()

    def test_T1_이후에_생긴_패키지만_inflow_new_로_센다(self):
        # adopter 는 T1 전에 있었고, newborn 은 T1 뒤에 처음 나왔다
        self.assertEqual(self.split([("adopter", "2020-01-01 00:00:00"),
                                     ("newborn", "2026-01-01 00:00:00")]), (2, 1))

    def test_전부_기존_패키지면_inflow_new_는_0_이다(self):
        self.assertEqual(self.split([("adopter", "2020-01-01 00:00:00"),
                                     ("newborn", "2020-02-01 00:00:00")]), (2, 0))

    def test_유지_이탈은_inflow_new_에_들어가지_않는다(self):
        """T1 뒤에 생긴 패키지라도 유입이 아니면 세지 않는다 (실제로는 나올 수 없는 조합이지만
        필터가 inflow 조건과 함께 걸려 있는지 확인한다)."""
        con = setup(decl=[("d", PERIOD, "x", "regular"), ("d", "t2", "x", "regular")],
                    moved=[("d", PERIOD)],
                    first_rel=[("d", "2026-01-01 00:00:00")])
        self.assertEqual(con.execute(
            "SELECT retained, inflow, inflow_new FROM agg WHERE period = ?"
            " AND target = 'x' AND kind = 'regular'", [PERIOD]).fetchone(), (1, 0, 0))


class Verification(unittest.TestCase):

    def test_존재할_수_없는_조합을_검산이_잡는다(self):
        """A<>B 인데 대표가 안 바뀐 입력. 실제 데이터에서는 나올 수 없지만,
        나왔을 때 검산이 0 이 아닌 값을 내는지 확인한다."""
        from build_dependent_transitions import verify
        ok = setup(decl=[("a", PERIOD, "x", "regular")], moved=[("a", PERIOD)])
        self.assertEqual(verify(ok)["impossible_change_without_move"], 0)

        bad = setup(decl=[("a", PERIOD, "x", "regular")], moved=[])
        self.assertEqual(verify(bad)["impossible_change_without_move"], 1)

    def test_보존_관계가_성립한다(self):
        """유지+유입 = T2 활성 집합, 유지+이탈 = T1 활성 집합 (S15P21A506-196 에서 넘어온 항목)."""
        from build_dependent_transitions import verify
        con = setup(
            decl=[("keep", PERIOD, "x", "regular"), ("keep", "t2", "x", "regular"),
                  ("dormant", PERIOD, "x", "regular"), ("dormant", "t2", "x", "regular"),
                  ("new", "t2", "x", "regular"),
                  ("gone", PERIOD, "x", "regular")],
            moved=[("keep", PERIOD), ("new", PERIOD), ("gone", PERIOD)])
        v = verify(con)
        self.assertEqual(v["conservation_t2_mismatch"], 0)
        self.assertEqual(v["conservation_t1_mismatch"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
