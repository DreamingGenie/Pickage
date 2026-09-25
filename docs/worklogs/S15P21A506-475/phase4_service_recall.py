"""S15P21A506-475 4단계 — 서비스 조건 추천 품질 (배치 산출물 그대로 채점).

기존 eval_recall.py 는 평가 패키지가 코퍼스에 없으면 끼워 넣어서 채점한다(보충 66개).
여기서는 **끼워 넣지 않는다** — 배치가 실제로 낸 candidates.parquet 의 순위를 그대로 본다.
그래서 "서비스에서 이 기준 패키지를 검색했을 때 정답 대안이 top-3(화면)·top-20 에 뜨는가" 다.

정답쌍 (a → b): a 가 기준으로 산출됐고 b 가 a 의 후보 목록 몇 위인가.
분모를 셋으로 나눠 보고한다.
  all      : 평가쌍 전부 (a·b 가 코퍼스에 없어도 실패로 센다) — 서비스 체감
  in_scope : a·b 둘 다 이번 코퍼스(text_hash_state)에 있는 쌍 — 모델·관문 성능

사용 (저장소 루트):
  python docs/worklogs/S15P21A506-475/phase4_service_recall.py <run_dir>... [--test <jsonl>]
"""
import argparse
import collections
import json
import os

import pyarrow.parquet as pq


def load_run(run_dir):
    res = os.path.join(run_dir, "out", "result")
    ranks = collections.defaultdict(dict)
    for r in pq.read_table(os.path.join(res, "candidates.parquet"),
                           columns=["base_package", "candidate_package", "rank"]).to_pylist():
        ranks[r["base_package"]][r["candidate_package"]] = r["rank"]
    corpus = {r["name"] for r in pq.read_table(os.path.join(res, "text_hash_state.parquet"), columns=["name"]).to_pylist()}
    return ranks, corpus


def score(ranks, corpus, pairs):
    out = {}
    for scope in ("all", "in_scope"):
        sel = [p for p in pairs if scope == "all" or (p["a"] in corpus and p["b"] in corpus)]
        hits3 = sum(1 for p in sel if ranks.get(p["a"], {}).get(p["b"], 99) <= 3)
        hits20 = sum(1 for p in sel if ranks.get(p["a"], {}).get(p["b"], 99) <= 20)
        qs = collections.defaultdict(list)
        for p in sel:
            qs[p["a"]].append(ranks.get(p["a"], {}).get(p["b"], 99))
        out[scope] = {"pairs": len(sel), "recall@3": round(hits3 / max(1, len(sel)), 4),
                      "recall@20": round(hits20 / max(1, len(sel)), 4),
                      "queries": len(qs), "query_hit@3": sum(1 for v in qs.values() if min(v) <= 3)}
    out["a_in_corpus"] = sum(1 for a in {p["a"] for p in pairs} if a in corpus)
    out["b_in_corpus"] = sum(1 for b in {p["b"] for p in pairs} if b in corpus)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--test", default="data/rehearsal475/inputs/test_alternatives_full_v2.jsonl")
    args = ap.parse_args()
    pairs = [json.loads(l) for l in open(args.test, encoding="utf-8") if l.strip()]
    report = {"test": args.test, "pairs": len(pairs), "runs": {}}
    for run in args.runs:
        ranks, corpus = load_run(run)
        report["runs"][os.path.basename(run.rstrip("/"))] = score(ranks, corpus, pairs)
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
