"""S15P21A506-475 4단계 — 정성 검수표 (사람이 판정).

다운로드 상위 기준 패키지 N개 + 시연 패키지의 top-3 를 실행별로 나란히 둔 CSV 를 만든다.
판정 열(`verdict_<run>`)은 비워 둔다 — 적합/부적합/애매는 사람이 채운다.

사용 (저장소 루트):
  python docs/worklogs/S15P21A506-475/phase4_review_sheet.py --runs R0 R1 R2 R3 --n 200 \
      --out docs/worklogs/S15P21A506-475/evidence/phase4/review_top3.csv
"""
import argparse
import collections
import csv
import os

import pyarrow.parquet as pq

DEMO = ["ws", "js-yaml", "yaml", "axios", "express", "cheerio", "jsdom", "react", "lodash", "moment"]


def top3(run):
    by = collections.defaultdict(list)
    path = os.path.join("data/rehearsal475/runs", run, "out/result/candidates.parquet")
    for r in pq.read_table(path, columns=["base_package", "candidate_package", "rank"]).to_pylist():
        if r["rank"] <= 3:
            by[r["base_package"]].append((r["rank"], r["candidate_package"]))
    return {k: [c for _, c in sorted(v)] for k, v in by.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", required=True)
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    tops = {r: top3(r) for r in args.runs}
    pt = pq.read_table("data/rehearsal475/package_text_reportable.parquet",
                       columns=["name", "downloads_last_month", "description"]).to_pylist()
    meta = {x["name"]: x for x in pt}
    bases = set.union(*(set(t) for t in tops.values()))
    ranked = sorted(bases, key=lambda n: -(meta.get(n, {}).get("downloads_last_month") or 0))
    pick = list(dict.fromkeys(DEMO + ranked[: args.n]))
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        head = ["base", "downloads_last_month", "description"]
        for r in args.runs:
            head += [f"top3_{r}", f"verdict_{r}"]
        head.append("changed_vs_first")
        w.writerow(head)
        for b in pick:
            row = [b, meta.get(b, {}).get("downloads_last_month"), (meta.get(b, {}).get("description") or "")[:120]]
            for r in args.runs:
                row += [" | ".join(tops[r].get(b, [])), ""]
            first = tops[args.runs[0]].get(b, [])
            row.append(any(tops[r].get(b, []) != first for r in args.runs[1:]))
            w.writerow(row)
    print(f"{len(pick)} 행 → {args.out}")


if __name__ == "__main__":
    main()
