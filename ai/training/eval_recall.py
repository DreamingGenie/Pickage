"""eval_recall.py — v7 학습 후 "기능적 대안" recall 벤치마크.

jupyter05 에서 실행 (sentence-transformers 필요). base bge-small vs 파인튜닝 결과를
같은 코퍼스·같은 지표로 나란히 찍어서 "v7이 나아졌나"에 숫자로 답한다.

방식:
  1. candidate_pool_v2.jsonl (name·description·keywords, ~4.75만) 를 코퍼스로 임베딩.
     → 실제 배치 파이프라인처럼 "몇만 개 후보 중에서" 찾는 상황을 재현. 쌍 183개끼리만
       비교하면(코퍼스=2개) recall이 의미없이 높게 나옴.
  2. test_alternatives_full.jsonl (도메인-분리 183쌍, 학습·검증 어디에도 안 쓰임) 의 a 를
     쿼리로, 코퍼스에서 top-k 중 b 가 있는지로 recall@3 / recall@10 계산.
  3. 텍스트 조립은 학습·추론과 동일: 'DESCRIPTION: {desc} / KEYWORDS: {정규화 keyword}'.
  4. 모델을 --model 로 여러 번 줘서 (base, v7 merged) 비교.

사용법:
  python eval_recall.py --model BAAI/bge-small-en-v1.5 --label base
  python eval_recall.py --model ./merged_bge_v7_hiconf --label v7_hiconf
  (같은 --pool·--test 로 두 번 돌리고 report 파일 비교)

  --apply-gates 를 붙이면 배치 파이프라인과 동일한 구조적 관문(plugin/adapter·same-family)을
  적용한 뒤 recall 을 계산한다. 순수 코사인 recall과 나란히 비교하면 "낮은 recall이 진짜
  모델 실패인지, 아니면 관문 없이는 near-duplicate(예: remark-* 플러그인 133개)가 top-k를
  채워서 생기는 착시인지" 구분할 수 있다 (2026-09-11, 마크다운 도메인 recall@3 0.038 원인 조사).
    python eval_recall.py --model ./merged_bge_v7_final --label v7_gated --apply-gates

출력: eval_recall_<label>.json (원시 랭크) + eval_recall_<label>_report.txt (요약)
"""
import argparse
import json
import re
import numpy as np

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def clean_desc(s):
    return _WS.sub(" ", _TAG.sub(" ", s or "")).strip()


def norm_keywords(kws, name):
    out, seen = [], set()
    for k in kws or []:
        k = _WS.sub(" ", str(k).lower().replace("-", " ").replace("_", " ")).strip()
        if not k or k == (name or "").lower() or k in seen:
            continue
        seen.add(k)
        out.append(k)
    return out


def text(name, desc, kws):
    return f"DESCRIPTION: {clean_desc(desc)} / KEYWORDS: {', '.join(norm_keywords(kws, name))}"


def load_jsonl(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip() and not l.startswith("#")]


def build_pool(pool, test):
    """코퍼스 이름/텍스트/keywords 리스트 + 평가쌍의 a/b 중 코퍼스에 없는 것 보충.
    (그래야 b 를 못 찾는 게 코퍼스 누락이 아니라 진짜 모델 실패로 해석됨)"""
    pool_names = [p["name"] for p in pool]
    pool_idx = {n: i for i, n in enumerate(pool_names)}
    pool_keywords = [p.get("keywords") for p in pool]
    pool_texts = [text(p["name"], p.get("description"), p.get("keywords")) for p in pool]
    for r in test:
        for side in ("a", "b"):
            n = r[side]
            if n not in pool_idx:
                pool_idx[n] = len(pool_names)
                pool_names.append(n)
                pool_keywords.append(r.get(f"{side}_keywords"))
                pool_texts.append(text(n, r[f"{side}_desc"], r.get(f"{side}_keywords")))
    return pool_names, pool_texts, pool_keywords, pool_idx


# ── 구조적 관문 — ai/similarity/similarity_batch_pipeline.py 의 is_plugin_adapter·
# is_same_family 를 그대로 복사(패키지 간 import 안 하려고). 로직이 갈라지면 이 eval이
# "실전(gate 적용) recall"을 대변하지 못하게 되니, 원본이 바뀌면 여기도 같이 바꿀 것.

_PLUGIN_MARKERS = {"plugin", "adapter", "preset", "loader"}


def is_plugin_adapter(name, keywords):
    base = name.rsplit("/", 1)[-1].lower()
    parts = base.replace("_", "-").split("-")
    if len(parts) >= 2:
        for i, p in enumerate(parts):
            if p in _PLUGIN_MARKERS:
                return True
            if p == "config" and i != len(parts) - 1:
                return True
    for k in keywords or []:
        toks = str(k).lower().replace("-", " ").split()
        if any(t in _PLUGIN_MARKERS for t in toks):
            return True
    return False


def is_same_family(a, b):
    """S15P21A506-334·334 후속과 완전히 같은 로직 — 우산↔하위모듈 판정은 스코프를
    벗겨내지 않고 전체 이름으로 하고(오탐 방지), 스코프 없는 이름이 상대방의
    스코프(조직명) 자체와 정확히 같으면 그 조직의 서브패키지로 본다."""
    a, b = a.lower(), b.lower()
    if a == b:
        return True
    a_scoped, b_scoped = a.startswith("@"), b.startswith("@")
    if a_scoped and b_scoped:
        return a.split("/", 1)[0] == b.split("/", 1)[0]
    if a_scoped or b_scoped:
        scoped, unscoped = (a, b) if a_scoped else (b, a)
        scope, _, subpath = scoped[1:].partition("/")
        if scope == "types":
            return subpath == unscoped
        return scope == unscoped
    for x, y in ((a, b), (b, a)):
        if len(y) > len(x) and y.startswith(x) and y[len(x)] in "-._":
            return True
    return False


def is_complement(base_dependents, cand_dependents, threshold=0.3, min_sample=20):
    """S15P21A506-334·173 후속과 완전히 같은 로직 — 자세한 근거는 그쪽 docstring 참고.
    비율은 교집합 ÷ 둘 중 더 작은 쪽 크기, 표본이 min_sample 미만이면 판단 보류(False)."""
    if not base_dependents or not cand_dependents:
        return False
    if min(len(base_dependents), len(cand_dependents)) < min_sample:
        return False
    inter = len(base_dependents & cand_dependents)
    return inter / min(len(base_dependents), len(cand_dependents)) > threshold


def load_dependents(path, kind="regular"):
    """similarity_batch_pipeline.load_dependents 와 완전히 같은 로직."""
    if not path:
        return {}
    import pyarrow.parquet as pq

    tbl = pq.read_table(path, columns=["name", "kind", "dependents"]).to_pylist()
    return {r["name"]: set(r["dependents"] or []) for r in tbl if r["kind"] == kind}


def rank_results(model, pool_names, pool_texts, pool_keywords, pool_idx, test, topks,
                  batch_size=256, apply_gates=False, dependents=None):
    """model.encode 로 코퍼스·쿼리를 임베딩하고, 평가쌍마다 정답(b)의 순위를 매긴다.
    sweep_checkpoints.py 처럼 메모리 상의 모델 객체를 바로 넣어 여러 체크포인트를
    돌릴 때도 쓸 수 있게 CLI(main)와 분리해둠.

    apply_gates=True 면 배치 파이프라인과 동일한 구조적 관문(plugin/adapter, same-family,
    dependents 를 준 경우 보완재까지)을 후보 목록에 적용한 뒤 순위를 매긴다 — "순수 코사인
    recall"이 아니라 "실전에 노출됐을 때의 recall"에 가까워짐. b 자신이 관문에 걸리면
    (정답 자체가 same-family 등) rank=None 이 되고 gate_blocked_b=True 로 표시 — 이건
    모델 문제가 아니라 라벨링(정답) 자체가 관문과 모순됨을 뜻함.

    `dependents`: name -> dependents 집합 (load_dependents() 결과). 주면 보완재 관문도
    적용된다 — S15P21A506-173 도입 효과(recall 변화)를 재려면 반드시 넘겨야 한다.
    """
    corpus_emb = model.encode(pool_texts, batch_size=batch_size, normalize_embeddings=True,
                               show_progress_bar=True, convert_to_numpy=True)
    query_texts = [text(r["a"], r["a_desc"], r.get("a_keywords")) for r in test]
    query_emb = model.encode(query_texts, batch_size=batch_size, normalize_embeddings=True,
                              convert_to_numpy=True)
    sims = query_emb @ corpus_emb.T  # (n_query, n_corpus) cosine (정규화됐으니 내적 = cos)

    max_k = max(topks)
    results = []
    for i, r in enumerate(test):
        a_i = pool_idx[r["a"]]
        b_i = pool_idx[r["b"]]
        row = sims[i].copy()
        row[a_i] = -1e9  # 자기 자신 제외
        full_order = np.argsort(-row)

        gate_blocked_b = False
        if apply_gates:
            a_name = r["a"]
            a_deps = dependents.get(a_name) if dependents else None
            order_full = []
            for idx in full_order:
                cand = pool_names[idx]
                blocked = is_plugin_adapter(cand, pool_keywords[idx]) or is_same_family(a_name, cand)
                if not blocked and dependents:
                    blocked = is_complement(a_deps, dependents.get(cand))
                if blocked:
                    if idx == b_i:
                        gate_blocked_b = True
                    continue
                order_full.append(int(idx))
        else:
            order_full = full_order.tolist()

        order = order_full[:max_k]
        rank = order.index(b_i) + 1 if b_i in order else None
        if rank is None and not gate_blocked_b and b_i in order_full:
            rank = order_full.index(b_i) + 1
        results.append({
            "a": r["a"], "b": r["b"], "domain": r.get("domain"),
            "confidence": r.get("confidence"), "rank": rank,
            "gate_blocked_b": gate_blocked_b,
        })
    return results


def recall_at(k, rows):
    hit = sum(1 for r in rows if r["rank"] is not None and r["rank"] <= k)
    return hit / max(len(rows), 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="HF 이름 또는 로컬 SentenceTransformer 경로")
    ap.add_argument("--label", required=True, help="리포트 파일명에 쓸 태그 (예: base, v7_hiconf)")
    ap.add_argument("--pool", default="candidate_pool_v2.jsonl")
    ap.add_argument("--test", default="test_alternatives_full.jsonl")
    ap.add_argument("--topk", default="3,10")
    ap.add_argument("--batch-size", type=int, default=256)
    ap.add_argument("--apply-gates", action="store_true",
                     help="배치 파이프라인의 plugin/adapter·same-family(·dependents 주면 보완재)"
                          " 관문을 적용해 '실전 노출 recall'을 측정 (기본은 순수 코사인 recall)")
    ap.add_argument("--dependents", default=None,
                     help="candidate_pool_package_dependents.parquet 경로 (S15P21A506-173 "
                          "보완재 관문 효과를 재려면 --apply-gates 와 같이 지정)")
    args = ap.parse_args()
    topks = [int(k) for k in args.topk.split(",")]

    from sentence_transformers import SentenceTransformer

    pool = load_jsonl(args.pool)
    test = load_jsonl(args.test)
    dependents = load_dependents(args.dependents)
    print(f"코퍼스 {len(pool)}개 / 평가쌍 {len(test)}개 / 모델 {args.model} / "
          f"gate={'ON' if args.apply_gates else 'OFF'} / dependents={len(dependents)}개")

    pool_names, pool_texts, pool_keywords, pool_idx = build_pool(pool, test)
    model = SentenceTransformer(args.model)
    results = rank_results(model, pool_names, pool_texts, pool_keywords, pool_idx, test, topks,
                            args.batch_size, apply_gates=args.apply_gates, dependents=dependents)

    by_domain = {}
    for r in results:
        by_domain.setdefault(r["domain"], []).append(r)

    blocked = [r for r in results if r["gate_blocked_b"]]

    lines = [
        f"eval_recall — {args.label}  ({args.model})  gate={'ON' if args.apply_gates else 'OFF'}",
        "=" * 50,
        f"코퍼스 {len(pool_names)}개 (원본 {len(pool)} + 평가쌍에서 누락분 보충 {len(pool_names)-len(pool)})",
        f"평가쌍 {len(results)}개, 도메인 {len(by_domain)}개",
        "",
        "전체:",
    ]
    for k in topks:
        lines.append(f"  recall@{k:<3} {recall_at(k, results):.3f}")
    if args.apply_gates:
        lines.append(f"  (정답(b) 자체가 관문에 걸려 원천 차단된 쌍: {len(blocked)}/{len(results)} — "
                      "이건 모델 실패가 아니라 라벨과 관문 정의가 모순되는 경우)")
    lines += ["", "도메인별 recall@3:"]
    for d, rows in sorted(by_domain.items(), key=lambda x: -len(x[1])):
        blocked_in_d = sum(1 for r in rows if r["gate_blocked_b"])
        suffix = f"  (blocked={blocked_in_d})" if args.apply_gates and blocked_in_d else ""
        lines.append(f"  {len(rows):3}  {recall_at(3, rows):.3f}  {d}{suffix}")

    misses = [r for r in results if r["rank"] is None or r["rank"] > topks[-1]]
    lines += ["", f"top-{topks[-1]} 밖 (실패) {len(misses)}개, 예시:"]
    for r in misses[:10]:
        lines.append(f"  {r['a']:30} -> {r['b']:30} rank={r['rank']}")

    report = "\n".join(lines)
    with open(f"eval_recall_{args.label}_report.txt", "w", encoding="utf-8") as f:
        f.write(report)
    with open(f"eval_recall_{args.label}.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    try:
        print(report)
    except UnicodeEncodeError:
        print(report.encode("ascii", "replace").decode())


if __name__ == "__main__":
    main()
