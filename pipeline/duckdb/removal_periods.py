"""구간별 이탈 사유 집계 (S15P21A506-378).

`build_migration_pairs.py` 가 쓰는 판정 문장과 검산을 여기 둔다. 그 파일은 **스크립트**라
import 하는 순간 11 GB DuckDB 를 열고 전체 계산이 돌아, 시험이 문장만 가져올 수 없다.

## 구간은 겹친다

`1y ⊂ 3y ⊂ 5y` 이고 셋 다 `T2` 에서 끝난다. 연도별 집계처럼 서로 배타적이지 않으므로
**같은 제거 한 건이 세 구간에 모두 들어간다.** 유지·유입·이탈이 구간마다 독립된 창을
보는 것과 같은 규칙이고, 그래서 구간끼리 더하면 안 된다.

## 연도별 집계로 대신할 수 없는 이유

구간은 `2026-08-31` 에 끝나는데 달력 연도는 `12-31` 에 끝난다. 한 해를 잘라 쓸 수 없다.
`dependents` 는 `COUNT(DISTINCT)` 라 연도끼리 더해지지도 않는다.

## 경계는 유지·유입·이탈에서 가져온다

여기에 날짜를 다시 적으면 다음 스냅샷에서 한쪽만 고쳐지고, 두 산출물이 서로 다른 구간을
같은 이름(`3y`)으로 부르게 된다. **그 어긋남은 검산에 걸리지 않는다** — 각자 내부적으로는
앞뒤가 맞기 때문이다.
"""
from pathlib import Path
import sys

# 같은 폴더의 형제 모듈. 부르는 쪽이 `-m` 이든 경로 실행이든 되도록 명시해 둔다.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_dependent_transitions import PERIODS, T2  # noqa: E402

__all__ = ["PERIODS", "T2", "REMOVAL_BY_PERIOD_SQL", "build_periods", "require_monotonic"]

# 입력 계약  trans(Name, to_ts, removed, added) · periods(period, t1, t2)
# 출력       removal_by_period(period, removed_pkg, removals, removals_no_replacement,
#                              removals_with_replacement, dependents)
REMOVAL_BY_PERIOD_SQL = """
CREATE OR REPLACE TABLE removal_by_period AS
SELECT p.period, x AS removed_pkg,
       count(*)                                            AS removals,
       count(*) FILTER (WHERE coalesce(len(added), 0) = 0) AS removals_no_replacement,
       count(*) FILTER (WHERE len(added) > 0)              AS removals_with_replacement,
       count(DISTINCT Name)                                AS dependents
FROM trans, unnest(removed) AS u(x), periods p
WHERE to_ts > p.t1 AND to_ts <= p.t2
GROUP BY 1, 2
"""


def build_periods(con):
    """구간 표. T1 을 SQL 문자열로 붙이지 않으려고 테이블로 만든다
    (`build_dependent_transitions.py` 와 같은 방식)."""
    con.execute("CREATE OR REPLACE TABLE periods(period VARCHAR, t1 TIMESTAMP, t2 TIMESTAMP)")
    for period, t1 in PERIODS.items():
        con.execute("INSERT INTO periods VALUES (?, ?, ?)", [period, t1, T2])


def require_monotonic(con):
    """구간이 겹치므로 **1y ≤ 3y ≤ 5y ≤ 전체** 가 반드시 성립한다. 어긋나면 구간 경계나
    조인이 틀린 것이므로 산출물을 쓰기 전에 멈춘다.

    `removals = 대체동반 + 대체없음` 은 두 FILTER 가 같은 조건을 갈라 쓰므로 언제나 참이라
    검산이 되지 못한다. 이쪽은 실제로 틀릴 수 있는 관계다 — 경계를 잘못 잡거나 조인이
    어긋나면 바로 깨진다.

    `removal_stats`(전 기간)가 있어야 마지막 비교를 할 수 있다.
    """
    bad = con.execute("""
        WITH w AS (
          SELECT removed_pkg,
                 coalesce(max(removals) FILTER (WHERE period = '1y'), 0) AS y1,
                 coalesce(max(removals) FILTER (WHERE period = '3y'), 0) AS y3,
                 coalesce(max(removals) FILTER (WHERE period = '5y'), 0) AS y5
          FROM removal_by_period GROUP BY 1)
        SELECT count(*) FROM w JOIN removal_stats s USING (removed_pkg)
        WHERE w.y1 > w.y3 OR w.y3 > w.y5 OR w.y5 > s.removals_total""").fetchone()[0]
    if bad:
        raise SystemExit(f"검산 실패 — 구간 포함관계가 깨진 대상이 {bad:,}개다. 산출물을 쓰지 않는다")
