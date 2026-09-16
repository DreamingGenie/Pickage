"""유지·유입·이탈 — "X 를 쓰던 사람들이 이 구간에 어떻게 움직였나" (S15P21A506-195)

MVP 의 Snapshot 총수 `delta` 와 **다른 지표다.** `delta` 는 첫·마지막 관측의 수 차이일 뿐
누가 남고 누가 떠났는지 모른다. 여기서는 dependent 를 **이름으로 식별해** 구간 양 끝의
선언 집합을 비교한다. 기획 구상안 §12.6 · 요구사항 §12.5 기능-08.

`DEC-DEPENDENCY-DELTA-20260910-01` 에 따라 `delta = 유입 - 이탈` 을 전제하지 않는다.
두 지표는 모집단도 계산도 달라 그 관계가 성립하지 않는다.

입력  data/raw/versions_full  (대표 릴리스 판정 — ordinal·published_at)
      data/raw/requirements   (선언 — Dependencies·Peer·Optional)
      datasets/targets/rank_top100k_20260902.csv (대상 목록)

출력  data/dependent_transitions<_label>/dependent_transitions.parquet
        (period, target, kind) 1행 — 네 범주의 수
      datasets/dependent_transitions_<label 또는 260916>/
        transitions_summary.csv   같은 표 (UTF-8 BOM)
        stats.json

실행  .venv-bq/Scripts/python.exe pipeline/duckdb/build_dependent_transitions.py

## 계산 — 시점 두 개를 비교한다

**시점 T 의 대표 릴리스** = `published_at <= T` 중 `ordinal` 최고.
`build_package_dependents.py`·`build_peer_similarity.py` 와 같은 기준이다. 라인(major)별로
나누지 않는다 — 대표 하나만 보므로 5.0.0 뒤에 나온 유지보수 릴리스 4.17.3 이 최신으로
잡히는 문제가 애초에 생기지 않는다.

`T2` 는 스냅샷 날짜로 **고정한다.** "오늘" 로 두면 매일 값이 바뀌어 어제 본 숫자와
달라지고 캐시가 매일 깨진다. `T1 = T2 - 구간`.

구간을 프리셋으로 묶는 것은 화면이 고르게 하기 위해서다. 임의 날짜를 받으면 요청마다
수천만 행을 집계해야 한다 — `react` 하나가 regular dependent 192,736 개다.

## 범주가 셋이 아니라 넷인 이유 — 여기가 이 파일의 핵심이다

`A` = as_of(T1) 선언 여부 · `B` = as_of(T2) 선언 여부 ·
`M` = (T1, T2] 안에 **대표 릴리스가 바뀌었는가**.

    | A | B | M | 범주                                        |
    |---|---|---|---------------------------------------------|
    | T | T | T | 유지     — 릴리스를 내면서도 계속 선언했다  |
    | T | T | F | 관측불가 — 변할 기회 자체가 없었다          |
    | F | T | T | 유입                                        |
    | T | F | T | 이탈                                        |
    | F | F | - | 대상 아님                                   |

`A <> B` 이면 `M` 은 **반드시 참이다.** 대표 릴리스가 안 바뀌었는데 선언이 달라질 수
없기 때문이다. 그래서 관측 불가는 `A=T, B=T, M=F` 한 칸뿐이고, 나머지 두 칸은 존재할
수 없다 — `verify()` 의 `impossible_change_without_move` 가 그것을 센다.

**관측 불가를 유지로 세면 숫자가 거짓이 된다.** 2026-09-16 실측 — 마지막 릴리스가 1년
이내인 패키지는 npm 전수 4,065,913 중 974,770(24.0%) 뿐이다. 3년 49.2% · 5년 66.2%.
1년 구간에서 76% 가 움직일 기회가 없었는데 그것을 전부 유지로 세면 유지율이 76% 에서
시작한다. 기능-08-R03 이 "자료 없음을 이탈로 분류하지 않는다" 고 못 박은 것과 같은
이유로 **유지로 분류하는 것도 잘못이다.**

받는 쪽은 네 수를 모두 화면에 내야 한다. 관측 불가를 숨기면 나머지 셋의 비율이 거짓이 된다.

## 읽는 사람이 반드시 알아야 할 것

**devDependencies 는 이 회차에 없다.** deps.dev `NPMRequirements` 는 Dependencies·Peer·
Optional 셋뿐이다. 개발 도구(eslint·jest·prettier 류)의 유지·유입·이탈을 이 결과로 읽으면
안 된다. dev 는 npm registry 수집분(S15P21A506-280·-366)에서 별도 회차로 낸다 —
**dependent 모집단이 상위 10만이라 여기(npm 전수 406만)와 절대수를 비교할 수 없다.**

**생존 편향.** unpublish 된 버전은 과거에 있었어도 보이지 않는다. T1 시점의 선언이 실제보다
적게 잡힐 수 있고, 그만큼 유입이 부풀고 이탈이 줄어든다 (수집계획 v2 §2-3).

**번들 경로 노드를 거른다.** deps.dev 에는 `@winglang/sdk>0.76.19>cdktf>safe-buffer` 처럼
중첩 의존성의 경로가 패키지처럼 들어 있다(고유 이름의 61.9%). `published_at IS NOT NULL`
이 정본이고 `NOT LIKE '%>%'` 는 문서용이다 — 근거는 `build_package_dependents.py`.

**대상 밖은 알 수 없다.** 대상 10만 밖 패키지는 조회 결과가 0 이 아니라 범위 밖이다.
받는 쪽에서 `OUT_OF_SCOPE` 로 구분한다.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sys
import time

import duckdb

try:
    # 콘솔이 아니면 stdout 인코딩이 cp949 로 정해져 한글 한 글자에 죽는다
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[2].as_posix()
RANK = f"{ROOT}/datasets/targets/rank_top100k_20260902.csv"
DEFAULT_LABEL = "260916"

# 스냅샷 경계. T2 를 "오늘" 로 두지 않는 이유는 위 docstring 을 볼 것.
# 23:59:59 까지 포함해야 스냅샷 당일 발행분이 빠지지 않는다.
T2 = "2026-08-31 23:59:59"
PERIODS = {"1y": "2025-08-31 23:59:59",
           "3y": "2023-08-31 23:59:59",
           "5y": "2021-08-31 23:59:59"}
KINDS = ("regular", "peer", "optional")

# 판정 — 위 docstring 의 표 그대로다.
#
# 시험이 같은 문장을 합성 입력에 적용할 수 있게 상수로 뺐다. 여기를 고치면 시험이 따라
# 깨지는 것이 맞다 — 표가 계약이고 이 SQL 은 그 표의 구현이기 때문이다.
#
# 입력 계약  decl(dependent, point, target, kind)  point 는 't2' 또는 구간 이름
#            moved(dependent, period)              있으면 그 구간에 대표가 바뀐 것
#            periods(period, t1) · tgt(name)
# 출력       cls_m(period, target, kind, dependent, a, b, moved) · agg(period, target, kind, 네 수)
CLASSIFY_SQL = """
CREATE OR REPLACE TABLE cls AS
SELECT w.period, d.target, d.kind, d.dependent,
       bool_or(d.point = w.period) AS a,
       bool_or(d.point = 't2')     AS b
FROM decl d, periods w
WHERE d.point IN (w.period, 't2')
GROUP BY 1, 2, 3, 4;

-- moved 는 있음/없음만 담는다. LEFT JOIN 결과가 NULL 이면 그 구간에 대표가 안 바뀐 것이다.
CREATE OR REPLACE TABLE cls_m AS
SELECT c.period, c.target, c.kind, c.dependent, c.a, c.b,
       (m.dependent IS NOT NULL) AS moved
FROM cls c
LEFT JOIN moved m ON m.dependent = c.dependent AND m.period = c.period;

-- 대상 × kind × 구간을 모두 만들고 없으면 0 을 넣는다. 행을 빼면 받는 쪽에서
-- "조회 실패" 와 "dependent 가 없음" 을 구분할 수 없다 (build_package_dependents.py 와 같은 규칙).
CREATE OR REPLACE TABLE agg AS
SELECT g.period, g.name AS target, g.kind,
       count(c.dependent) FILTER (WHERE c.a AND c.b AND c.moved)      AS retained,
       count(c.dependent) FILTER (WHERE NOT c.a AND c.b)              AS inflow,
       count(c.dependent) FILTER (WHERE c.a AND NOT c.b)              AS outflow,
       count(c.dependent) FILTER (WHERE c.a AND c.b AND NOT c.moved)  AS unobserved
FROM (SELECT t.name, k.kind, w.period
      FROM tgt t
      CROSS JOIN (SELECT unnest($kinds) AS kind) k
      CROSS JOIN periods w) g
LEFT JOIN cls_m c ON c.target = g.name AND c.kind = g.kind AND c.period = g.period
GROUP BY 1, 2, 3;
"""


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--targets", default=RANK,
                    help="대상 목록 CSV. name 열만 있으면 된다 (기본: 다운로드 상위 10만)")
    ap.add_argument("--label", default=None,
                    help="회차 이름. 주면 출력 폴더가 갈린다. 기본 회차는 생략한다")
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--memory", default="40GB")
    args = ap.parse_args(argv)

    # label 은 폴더 이름이자 MinIO 객체 키가 된다 (build_package_dependents.py 와 같은 규칙).
    if args.label is not None and not re.fullmatch(r"[a-z0-9_]+", args.label):
        ap.error("--label 은 영문 소문자·숫자·밑줄만 쓴다 (폴더 이름이자 MinIO 객체 키가 된다)")
    if args.label == DEFAULT_LABEL:
        ap.error(f"--label {DEFAULT_LABEL} 은 기본 회차가 쓰는 이름이다. label 없이 실행한다")

    targets = args.targets if os.path.isabs(args.targets) else f"{ROOT}/{args.targets}"
    if not os.path.isfile(targets):
        ap.error(f"대상 목록을 찾을 수 없다: {targets}")
    # 대상을 바꿨는데 label 이 없으면 기본 회차 산출물을 조용히 덮어쓴다 (2026-09-16 -359 사고).
    if targets != RANK and args.label is None:
        ap.error("--targets 를 바꿀 때는 --label 도 줘야 한다. 없으면 기본 회차를 덮어쓴다")
    args.targets = targets
    return args


def build_periods(con):
    """구간 표. T1 을 SQL 문자열로 붙이지 않으려고 테이블로 만든다."""
    con.execute("CREATE OR REPLACE TABLE periods(period VARCHAR, t1 TIMESTAMP)")
    for w, t1 in PERIODS.items():
        con.execute("INSERT INTO periods VALUES (?, ?)", [w, t1])


def verify(con):
    """완료 조건의 검산. 값을 stats 에 남겨 README 가 인용한다."""
    v = {}
    # 1) 존재할 수 없는 조합 — 대표가 안 바뀌었는데 선언이 달라졌다. 0 이어야 한다.
    #    0 이 아니면 대표 릴리스 판정이나 시점 필터가 틀린 것이다.
    v["impossible_change_without_move"] = con.execute(
        "SELECT count(*) FROM cls_m WHERE a <> b AND NOT moved").fetchone()[0]

    # 2) 보존 관계 (S15P21A506-196 에서 넘어온 항목)
    #    유지 + 유입 = T2 에 선언한 활성 dependent, 유지 + 이탈 = T1 에 선언한 활성 dependent.
    #    inflow·outflow 는 정의상 moved 가 참이므로 활성 조건을 따로 걸지 않아도 같다.
    v["conservation_t2_mismatch"] = con.execute("""
        SELECT count(*) FROM agg a
        JOIN (SELECT period, target, kind, count(*) AS n FROM cls_m
              WHERE b AND moved GROUP BY 1, 2, 3) x
          ON x.period = a.period AND x.target = a.target AND x.kind = a.kind
        WHERE a.retained + a.inflow <> x.n""").fetchone()[0]
    v["conservation_t1_mismatch"] = con.execute("""
        SELECT count(*) FROM agg a
        JOIN (SELECT period, target, kind, count(*) AS n FROM cls_m
              WHERE a AND moved GROUP BY 1, 2, 3) x
          ON x.period = a.period AND x.target = a.target AND x.kind = a.kind
        WHERE a.retained + a.outflow <> x.n""").fetchone()[0]

    # 3) 관측 불가 비중 — docstring 이 인용하는 수치의 실측값
    v["unobserved_share_by_period"] = con.execute("""
        SELECT period,
               round(sum(unobserved)::DOUBLE
                     / nullif(sum(retained + inflow + outflow + unobserved), 0), 4)
        FROM agg GROUP BY 1 ORDER BY 1""").fetchall()
    return v


def main(argv=None):
    args = parse_args(argv)
    t0 = time.time()

    def log(*a):
        print(f"[{time.time() - t0:6.0f}s]", *a, flush=True)

    suffix = f"_{args.label}" if args.label else ""
    pq_dir = f"{ROOT}/data/dependent_transitions{suffix}"
    out = f"{ROOT}/datasets/dependent_transitions_{args.label or DEFAULT_LABEL}"
    tmp = f"{ROOT}/data/duckdb_tmp"
    for d in (pq_dir, out, tmp):
        os.makedirs(d, exist_ok=True)

    v_path = f"{ROOT}/data/raw/versions_full/snapshot=2026-08-31/*.parquet"
    r_path = f"{ROOT}/data/raw/requirements/**/*.parquet"

    con = duckdb.connect()
    con.execute(f"SET threads={args.threads}; SET memory_limit='{args.memory}'; "
                f"SET temp_directory='{tmp}'; SET preserve_insertion_order=false")

    stats = {"snapshot": "2026-08-31", "t2": T2, "periods": PERIODS,
             "kinds": list(KINDS), "source": "depsdev",
             "built_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    build_periods(con)

    # 1) 대표 릴리스 전환점 ---------------------------------------------------
    #    모든 릴리스가 아니라 **대표가 바뀐 지점만** 남긴다. 과거 라인의 유지보수 릴리스는
    #    대표를 바꾸지 않으므로 여기서 빠지고, 그래야 M(관측 가능) 판정이 정확해진다 —
    #    "릴리스는 냈지만 우리가 보는 선언은 바뀔 수 없었다" 를 유지로 세지 않기 위해서다.
    #    동순위 정렬에 ordinal 을 함께 넣어 같은 published_at 에서도 결정적으로 고른다.
    log("1/5 대표 릴리스 전환점")
    con.execute(f"""CREATE OR REPLACE TABLE rep AS
SELECT Name, Version, published_at AS at FROM (
  SELECT Name, Version, published_at, ordinal,
         max(ordinal) OVER (PARTITION BY Name ORDER BY published_at, ordinal
                            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS prev_max
  FROM read_parquet('{v_path}')
  WHERE is_release AND published_at IS NOT NULL AND Name NOT LIKE '%>%')
WHERE prev_max IS NULL OR ordinal > prev_max""")
    stats["representative_releases"] = con.execute("SELECT count(*) FROM rep").fetchone()[0]
    stats["packages"] = con.execute("SELECT count(DISTINCT Name) FROM rep").fetchone()[0]
    # T2 를 넘는 발행이 있으면 T2 활성 집합이 package_dependents.parquet 과 어긋난다.
    stats["published_after_t2"] = con.execute(
        f"SELECT count(*) FROM rep WHERE at > TIMESTAMP '{T2}'").fetchone()[0]
    log("   전환점", f"{stats['representative_releases']:,}",
        "패키지", f"{stats['packages']:,}", "T2 이후", stats["published_after_t2"])

    # 2) 대상 목록 -----------------------------------------------------------
    log("2/5 대상 목록")
    con.execute(f"""CREATE OR REPLACE TABLE tgt AS
SELECT t.name, k.download_rank
FROM (SELECT DISTINCT trim(name) AS name FROM read_csv_auto('{args.targets}', header=true)
      WHERE name IS NOT NULL AND trim(name) <> '') t
LEFT JOIN (SELECT trim(name) AS name, min(rank) AS download_rank
           FROM read_csv_auto('{RANK}') WHERE name IS NOT NULL GROUP BY 1) k
       ON k.name = t.name""")
    stats["targets_list"] = args.targets.replace(ROOT + "/", "")
    stats["targets"] = con.execute("SELECT count(*) FROM tgt").fetchone()[0]
    log("   대상", f"{stats['targets']:,}")

    # 3) 시점별 대표 릴리스 ---------------------------------------------------
    #    포인트마다 나눠 돈다. 한 번에 크로스 조인하면 rep 전체 × 4 를 한꺼번에 들고 있어야 한다.
    log("3/5 시점별 대표 릴리스")
    con.execute("CREATE OR REPLACE TABLE rep_pt(Name VARCHAR, point VARCHAR, Version VARCHAR)")
    for point, t in [("t2", T2)] + list(PERIODS.items()):
        con.execute(f"""INSERT INTO rep_pt
SELECT Name, '{point}', arg_max(Version, at)
FROM rep WHERE at <= TIMESTAMP '{t}' GROUP BY Name""")
        n = con.execute("SELECT count(*) FROM rep_pt WHERE point = ?", [point]).fetchone()[0]
        stats[f"packages_at_{point}"] = n
        log(f"   {point} ({t})", f"{n:,}")

    # 4) 선언 ----------------------------------------------------------------
    #    (Name, Version) 로 접어서 조인한다. 5년간 릴리스가 없던 패키지는 네 시점의 대표가
    #    같은 버전이라, 접지 않으면 requirements 의 같은 행을 네 번 읽는다.
    #    DISTINCT 는 같은 의존자가 같은 대상을 두 번 선언한 경우를 한 번으로 만든다.
    log("4/5 선언 전개 (오래 걸린다)")
    con.execute(f"""CREATE OR REPLACE TABLE nv AS
SELECT DISTINCT Name, Version FROM rep_pt""")
    con.execute(f"""CREATE OR REPLACE TABLE edges AS
SELECT DISTINCT nv.Name, nv.Version, u.target, u.kind
FROM nv
JOIN read_parquet('{r_path}') q ON q.Name = nv.Name AND q.Version = nv.Version,
LATERAL (
  SELECT unnest(list_transform(coalesce(q.Dependencies, []), x -> x.Name)) AS target,
         'regular' AS kind
  UNION ALL
  SELECT unnest(list_transform(coalesce(q.PeerDependencies, []), x -> x.Name)), 'peer'
  UNION ALL
  SELECT unnest(list_transform(coalesce(q.OptionalDependencies, []), x -> x.Name)), 'optional'
) u
WHERE u.target IN (SELECT name FROM tgt)""")
    con.execute("""CREATE OR REPLACE TABLE decl AS
SELECT p.Name AS dependent, p.point, e.target, e.kind
FROM rep_pt p JOIN edges e ON e.Name = p.Name AND e.Version = p.Version""")
    stats["representative_versions"] = con.execute("SELECT count(*) FROM nv").fetchone()[0]
    stats["declarations"] = con.execute("SELECT count(*) FROM decl").fetchone()[0]
    log("   선언", f"{stats['declarations']:,}")

    # M — 구간 안에 대표 릴리스가 바뀌었는가. 이것이 활성 판정이다.
    con.execute(f"""CREATE OR REPLACE TABLE moved AS
SELECT DISTINCT r.Name AS dependent, w.period
FROM rep r, periods w
WHERE r.at > w.t1 AND r.at <= TIMESTAMP '{T2}'""")

    # 5) 판정·저장 ------------------------------------------------------------
    log("5/5 판정·저장")
    con.execute(CLASSIFY_SQL, {"kinds": list(KINDS)})

    con.execute(f"""CREATE OR REPLACE TABLE out AS
SELECT a.period, a.target, a.kind, a.retained, a.inflow, a.outflow, a.unobserved,
       w.t1, TIMESTAMP '{T2}' AS t2, t.download_rank,
       (t.download_rank IS NOT NULL) AS in_top100k
FROM agg a JOIN periods w ON w.period = a.period JOIN tgt t ON t.name = a.target""")

    # 정렬 키에 target 을 넣는다. download_rank 만으로는 순위 밖이 전부 NULL 이라 동순위가
    # 생기고, 내용이 같은데 실행마다 파일 바이트가 달라진다 (2026-09-16 -359 실측).
    order = "ORDER BY period, download_rank NULLS LAST, target, kind"
    con.execute(f"""COPY (SELECT * FROM out {order})
                    TO '{pq_dir}/dependent_transitions.parquet'
                    (FORMAT PARQUET, COMPRESSION ZSTD)""")
    csv = f"{out}/transitions_summary.csv"
    con.execute(f"COPY (SELECT * FROM out {order}) TO '{csv}' (FORMAT CSV, HEADER)")
    # datasets/README.md 규칙 — CSV 는 UTF-8 BOM (엑셀·구글시트가 BOM 없이는 한글을 깬다)
    with open(csv, "rb") as fh:
        body = fh.read()
    if not body.startswith(b"\xef\xbb\xbf"):
        with open(csv, "wb") as fh:
            fh.write(b"\xef\xbb\xbf" + body)

    stats.update(verify(con))
    stats["rows"] = con.execute("SELECT count(*) FROM out").fetchone()[0]
    stats["file_bytes"] = os.path.getsize(f"{pq_dir}/dependent_transitions.parquet")
    stats["elapsed_sec"] = round(time.time() - t0)
    with open(f"{out}/stats.json", "w", encoding="utf-8") as fh:
        json.dump(stats, fh, ensure_ascii=False, indent=2, default=str)
    log("done", json.dumps(stats, ensure_ascii=False, default=str))
    return stats


if __name__ == "__main__":
    main()
