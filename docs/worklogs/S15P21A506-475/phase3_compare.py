"""S15P21A506-475 3단계 — 리허설 산출물 비교.

두 candidates.parquet 의 top-3(화면 노출)·top-20 을 기준 패키지 단위로 비교하고, 대표 패키지의
top-3 를 나란히 찍는다. 선택적으로 available(보고서 가능) 목록 밖 후보 수를 센다.

사용 (저장소 루트):
  python docs/worklogs/S15P21A506-475/phase3_compare.py <A.parquet> <B.parquet> [--available <csv>]
"""
import argparse
import collections
import csv
import json

import pyarrow.parquet as pq

PROBES = ["ws", "js-yaml", "yaml", "axios", "express", "react", "lodash", "moment", "webpack",
          "jest", "cheerio", "jsdom", "marked", "commander", "chalk", "uuid", "dotenv", "zod"]


def load(path):
    t = pq.read_table(path, columns=["base_package", "candidate_package", "rank", "cos_score"]).to_pylist()
    by = collections.defaultdict(list)
    for r in t:
        by[r["base_package"]].append((r["rank"], r["candidate_package"], r["cos_score"]))
    for k in by:
        by[k].sort()
    return by, len(t)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--available", default=None)
    args = ap.parse_args()
    A, na = load(args.a)
    B, nb = load(args.b)
    common = set(A) & set(B)
    top3_same = sum(1 for k in common if [c for _, c, _ in A[k][:3]] == [c for _, c, _ in B[k][:3]])
    top3_set_same = sum(1 for k in common if {c for _, c, _ in A[k][:3]} == {c for _, c, _ in B[k][:3]})
    ov20 = [len({c for _, c, _ in A[k][:20]} & {c for _, c, _ in B[k][:20]}) / max(1, min(20, len(A[k]), len(B[k])))
            for k in common]
    out = {
        "A": {"path": args.a, "rows": na, "bases": len(A)},
        "B": {"path": args.b, "rows": nb, "bases": len(B)},
        "bases_common": len(common), "bases_only_A": len(set(A) - set(B)), "bases_only_B": len(set(B) - set(A)),
        "top3_identical_order": top3_same, "top3_identical_set": top3_set_same,
        "top3_identical_order_pct": round(100 * top3_same / max(1, len(common)), 2),
        "top20_overlap_mean": round(sum(ov20) / max(1, len(ov20)), 4),
        "bases_with_lt3_A": sum(1 for v in A.values() if len(v) < 3),
        "bases_with_lt3_B": sum(1 for v in B.values() if len(v) < 3),
    }
    if args.available:
        with open(args.available, encoding="utf-8") as f:
            av = {r["name"] for r in csv.DictReader(f)}
        for tag, D in (("A", A), ("B", B)):
            out[f"outside_available_{tag}"] = {
                "bases": sum(1 for k in D if k not in av),
                "top3_candidates": sum(1 for v in D.values() for _, c, _ in v[:3] if c not in av),
            }
    out["probes"] = {p: {"A": [c for _, c, _ in A.get(p, [])[:3]], "B": [c for _, c, _ in B.get(p, [])[:3]]}
                     for p in PROBES}
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
