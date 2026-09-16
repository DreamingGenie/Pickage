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
from build_dependent_transitions import CLASSIFY_SQL, KINDS  # noqa: E402

PERIOD = "1y"
T1 = "2025-08-31 23:59:59"


def setup(decl, moved, targets=("x",)):
    """decl: (dependent, point, target, kind) · moved: (dependent, period)"""
    con = duckdb.connect()
    con.execute("CREATE TABLE periods(period VARCHAR, t1 TIMESTAMP)")
    con.execute("INSERT INTO periods VALUES (?, ?)", [PERIOD, T1])
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
