"""eval_gate_ranking.py — 관문 + cos 정렬 구조의 Recall@3 / Precision@3 측정 (S15P21A506-171).

171 은 원래 "여러 유사도 임계값에서 Recall@3/Precision@3 을 재 임계값을 확정" 하는 작업이었으나
DEC-RANK-20260910-01 로 "임계값 → 구조적 관문" 으로 바뀌었다. 이 스크립트는 그 결정을 숫자로 확인한다.

  · 배치 파이프라인과 같은 흐름 — top-K 검색(기본 30) → apply_gates → rerank(cos 순) → 상위 3개.
    관문·정렬은 ai/similarity/similarity_batch_pipeline.py 의 함수를 **그대로 import** 한다(복사 아님).
    그래서 관문 통과분이 3개 미만이면 3개 미만으로 노출되는 것까지 그대로 재현된다.
  · 설정 4가지를 나란히 잰다: cos(관문 없음) / gate(plugin·같은 계열) / gate(이름만 — keyword 로는
    플러그인 판정을 안 하는 변형) / gate+complement(보완재, dependents 필요).
  · 참고로 "cos 임계값으로 자르는" 예전 방식(τ 스윕)도 같은 표에 넣어 관문 방식과 비교한다.
  · 배치의 repo_archived 관문은 저장소 정보가 없어 넣지 못했고, 보완재 관문은 dependents 를 가진
    패키지에서만 동작한다(로컬 _dependents_of.json 은 코퍼스의 0.5%). 관문 4종 중 일부만 재현한다.

⚠ 반드시 **base 모델(BAAI/bge-small-en-v1.5)** 로 잰다. 골드셋 npm_functional_alternatives_v2.jsonl 의
  HTTP 클라이언트·스키마 검증·애플리케이션 로깅 등은 파인튜닝 학습 도메인이다(패키지 87~91%가
  train_v7_hiconf_v5 에 등장). 파인튜닝 모델로 이 도메인을 재면 학습 데이터 위의 점수가 된다.
  파인튜닝 모델은 --gold test_alternatives_full_v2.jsonl(평가 도메인)로만 잴 것.

⚠ Precision 은 하한이다. 골드셋에는 라벨링된 대안만 들어 있어서, 골드에 없는 좋은 후보가 top-3 에
  들어와도 오답으로 센다. 설정끼리(수정 전후 등) 비교하는 용도로만 읽을 것.

사용법 (sentence-transformers 필요):
  python eval_gate_ranking.py --label base_171 --out <dir> \\
      --domains "HTTP 클라이언트,스키마 검증,애플리케이션 로깅" --dependents _dependents_of.json
  python eval_gate_ranking.py --label base_heldout --out <dir> --gold test_alternatives_full_v2.jsonl

필요한 것:
  · 같은 디렉터리의 eval_recall.py (text / build_pool / load_jsonl 을 import 한다)
  · ai/similarity/similarity_batch_pipeline.py (관문·정렬 정본)
  · **레포에 없는 데이터 파일** — 이 디렉터리(로컬 ai/training 또는 jupyter05)에 있어야 한다:
      candidate_pool_full_922k.jsonl (코퍼스, --pool),
      npm_functional_alternatives_v2.jsonl (골드, 기본 --gold),
      test_alternatives_full_v2.jsonl (평가 도메인 골드),
      _dependents_of.json 또는 dependents parquet (선택, --dependents)
"""
import argparse
import json
import os
import sys
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "similarity"))

import similarity_batch_pipeline as sp  # noqa: E402  (관문·정렬의 정본)
from eval_recall import build_pool, load_jsonl, text  # noqa: E402

BASE_MODEL = "BAAI/bge-small-en-v1.5"
THRESHOLDS = [0.0, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85]


def load_dependents_any(path):
    """parquet(name·kind·dependents) 또는 {name: [dependents...]} JSON."""
    if not path:
        return {}
    if path.endswith(".json"):
        return {k: set(v) for k, v in json.load(open(path, encoding="utf-8")).items()}
    return sp.load_dependents(path)


def build_gold(rows, domains):
    """(domain, base) -> {정답 대안 이름}. 대안은 대칭으로 보고 양방향 모두 쿼리로 쓴다."""
    gold = defaultdict(set)
    for r in rows:
        if r.get("label", 1) != 1:
            continue
        if domains and r.get("domain") not in domains:
            continue
        gold[(r["domain"], r["a"])].add(r["b"])
        gold[(r["domain"], r["b"])].add(r["a"])
    return gold


def filter_gold_by_popularity(gold, downloads_by_name, floor):
    """정답(B)이 downloads_last_month>=floor 인 것만 남긴 골드 (S15P21A506-450).

    이 골드셋은 원래 "기능적으로 유사한가"만으로 라벨링됐다 — 인지도는 기준에 없었다.
    정답 기준 자체가 "기능이 유사하면서 인지도도 있어야 한다"로 바뀌면, downloads 하한을
    걸어서 생기는 recall 하락 중 일부는 진짜 실패가 아니라 "정답이지만 이제는 기준 미달인
    B를 더 이상 안 뽑는" **의도된 동작**이다. 원본 recall(구 정답지) 만으로는 이 둘을
    구분 못 한다 — 이 함수로 만든 골드로 다시 재면, "B 자체가 새 기준(인지도)도 만족하는데
    놓친" 진짜 손실만 남는다.

    floor<=0 이면 원본 그대로(구 정답지). B의 downloads 정보가 없으면(코퍼스 밖 보충 이름
    등) 새 기준을 만족하는지 모르므로 **제외**한다(관대하게 통과시키지 않음 — 위
    apply_downloads_floor 와 같은 보수적 태도).
    """
    if floor <= 0:
        return gold
    out = {}
    for k, alts in gold.items():
        kept = {a for a in alts if (downloads_by_name.get(a) or 0) >= floor}
        if kept:
            out[k] = kept
    return out


def embed(model, texts, cache, batch_size):
    if cache and os.path.exists(cache):
        arr = np.load(cache)
        if arr.shape[0] == len(texts):
            print(f"임베딩 캐시 사용: {cache}")
            return arr
    arr = model.encode(texts, batch_size=batch_size, normalize_embeddings=True,
                       show_progress_bar=True, convert_to_numpy=True)
    if cache:
        np.save(cache, arr)
    return arr


def retrieve(q_names, pool_idx, sims, retrieve_k):
    """배치의 top_k 와 같다: 자기 자신 제외, 코사인 내림차순 retrieve_k 개. (base_idx, cand_idx, cos)."""
    hits = []
    for qi, name in enumerate(q_names):
        base_idx = pool_idx[name]
        row = sims[qi].copy()
        row[base_idx] = -np.inf
        top = np.argpartition(-row, retrieve_k)[:retrieve_k]
        top = top[np.argsort(-row[top])]
        hits += [(base_idx, int(c), float(row[c])) for c in top]
    return hits


def shown_by_base(hits, names, k_user=3):
    """rerank(cos 정렬) 결과 중 노출분(rank<=3) 을 base 이름 -> [(후보, cos)] 로."""
    out = defaultdict(list)
    for row in sp.rerank(hits, names, k_user):
        out[row["base_package"]].append((row["candidate_package"], row["cos_score"]))
    return out


def score(gold, shown, tau=None):
    """설정 하나의 지표. tau 를 주면 노출분 중 cos < tau 는 잘라낸다(예전 임계값 방식)."""
    n_gold = n_hit = n_shown = n_bases_hit = n_cap = 0
    lt3 = zero = 0
    for (dom, base), g in gold.items():
        s = [c for c, cos in shown.get(base, []) if tau is None or cos >= tau]
        h = len(set(s) & g)
        n_gold += len(g)
        n_cap += min(3, len(g))
        n_hit += h
        n_shown += len(s)
        n_bases_hit += h > 0
        lt3 += len(s) < 3
        zero += len(s) == 0
    nb = len(gold)
    return {
        "recall@3": n_hit / max(n_gold, 1),
        # 정답이 3개보다 많은 base 는 3개를 다 맞혀도 recall@3 이 1 이 못 된다 — 그 상한(min(3,|정답|))으로 나눈 값
        "recall@3_cap": n_hit / max(n_cap, 1),
        "hit@3": n_bases_hit / max(nb, 1),
        "precision@3": n_hit / max(n_shown, 1),
        "avg_shown": n_shown / max(nb, 1),
        "lt3_ratio": lt3 / max(nb, 1),
        "zero_ratio": zero / max(nb, 1),
        "bases": nb,
        "gold_pairs": n_gold,
    }


def fmt(m):
    return (f"R@3 {m['recall@3']:.3f}  R@3상한대비 {m['recall@3_cap']:.3f}  hit@3 {m['hit@3']:.3f}  P@3 {m['precision@3']:.3f}  "
            f"평균노출 {m['avg_shown']:.2f}  3개미만 {m['lt3_ratio']:.0%}  0개 {m['zero_ratio']:.0%}")


# ── downloads 하한 스윕 (S15P21A506-450) ──────────────────────────────
#
# "TOP3에 영세 패키지가 너무 많이 잡힌다"는 반복 피드백 대응. cos 축은 기존
# 구조적 관문(위)이 이미 상대적으로 처리하므로, 여기서는 downloads_last_month에만
# 절대 하한을 걸어본다 — 하드 컷오프를 두 축에 동시에 걸면 후보가 비는 위험이
# 커지므로(브레인스토밍 결정) 한 축으로 제한한다.

def apply_downloads_floor(hits, names, downloads_by_idx, floor):
    """downloads_last_month < floor 인 후보(candidate)를 hits 에서 제거한다.

    floor<=0 이면 무변경(하한 없음). downloads 정보가 없는 후보(None)는 **통과시키지
    않는다** — 데이터 없다고 관대하게 봐주면 "실제로는 영세한데 그냥 몰라서 통과"하는
    사례를 만들 수 있어서다(구조적 관문의 보완재 판정과는 반대 방향 — 거긴 데이터
    없으면 통과가 기본값인데, 거기는 "감점 근거 없음=감점 안 함"이고 여기는 "자격
    근거 없음=자격 불충분"이라 취지가 다르다).
    """
    if floor <= 0:
        return hits, 0
    kept, dropped = [], 0
    for base_idx, cand_idx, cos in hits:
        dl = downloads_by_idx.get(cand_idx)
        if dl is None or dl < floor:
            dropped += 1
            continue
        kept.append((base_idx, cand_idx, cos))
    return kept, dropped


def downloads_stats(shown, downloads_by_name, floors=(10_000, 50_000, 100_000, 500_000)):
    """설정 하나에서 실제로 노출된(top-3) 후보들의 downloads_last_month 분포.

    "관문을 어떻게 바꾸면 recall/precision이 얼마나 깎이는가"만으로는 원래 문제
    ("영세 패키지가 뽑힌다")가 실제로 나아졌는지 알 수 없어서, 선정된 후보 자체의
    인기도 분포를 recall/precision과 나란히 본다.
    """
    vals = [downloads_by_name.get(c) for cands in shown.values() for c, _ in cands]
    vals = [v for v in vals if v is not None]
    missing = sum(1 for cands in shown.values() for c, _ in cands) - len(vals)
    if not vals:
        return None
    arr = np.array(vals, dtype=np.float64)
    out = {"n": len(arr), "missing_downloads": missing,
           "mean": float(np.mean(arr)), "median": float(np.median(arr))}
    for f in floors:
        out[f"below_{f}"] = float((arr < f).mean())
    return out


def fmt_downloads(d):
    if d is None:
        return "(downloads 정보 없음)"
    below = "  ".join(f"<{f:,} {d[f'below_{f}']:.0%}" for f in (10_000, 50_000, 100_000, 500_000) if f"below_{f}" in d)
    return f"평균 {d['mean']:,.0f}  중앙값 {d['median']:,.0f}  {below}  (n={d['n']}, downloads결측 {d['missing_downloads']})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", default=".", help="리포트·원시 결과를 쓸 디렉터리")
    ap.add_argument("--model", default=BASE_MODEL)
    ap.add_argument("--pool", default=os.path.join(HERE, "candidate_pool_full_922k.jsonl"))
    ap.add_argument("--gold", default=os.path.join(HERE, "npm_functional_alternatives_v2.jsonl"))
    ap.add_argument("--domains", default=None, help="쉼표 구분. 생략하면 골드 파일의 전 도메인")
    ap.add_argument("--dependents", default=None, help="parquet 또는 name->list JSON (보완재 관문)")
    ap.add_argument("--retrieve-k", type=int, default=30)
    ap.add_argument("--batch-size", type=int, default=128)
    ap.add_argument("--cache", default=None, help="코퍼스 임베딩 .npy 캐시 경로")
    ap.add_argument("--downloads-floors", default="10000,50000,100000,500000",
                     help="쉼표 구분 downloads_last_month 하한 스윕 값(S15P21A506-450). "
                          "각 값마다 gate(+보완재) 결과에 하한을 추가로 걸어 recall/precision/"
                          "lt3_ratio와 선정된 downloads 분포를 나란히 잰다")
    args = ap.parse_args()

    if args.model != BASE_MODEL:
        print(f"경고: base 모델이 아니다({args.model}). --gold 가 학습 도메인이면 결과는 오염된다.")

    from sentence_transformers import SentenceTransformer

    domains = set(args.domains.split(",")) if args.domains else None
    gold_rows = load_jsonl(args.gold)
    gold = build_gold(gold_rows, domains)
    pool = load_jsonl(args.pool)
    used_rows = [r for r in gold_rows if r.get("label", 1) == 1 and (not domains or r["domain"] in domains)]
    names, texts, keywords, pool_idx = build_pool(pool, used_rows)
    print(f"코퍼스 {len(names)}개(원본 {len(pool)} + 보충 {len(names) - len(pool)}) / "
          f"쿼리 {len(gold)}건 / 골드쌍 {sum(len(g) for g in gold.values())}(양방향)")

    model = SentenceTransformer(args.model)
    corpus = embed(model, texts, args.cache, args.batch_size)
    q_names = sorted({b for _, b in gold})
    q_emb = model.encode([texts[pool_idx[n]] for n in q_names], batch_size=args.batch_size,
                         normalize_embeddings=True, convert_to_numpy=True)
    sims = q_emb @ corpus.T

    hits = retrieve(q_names, pool_idx, sims, args.retrieve_k)
    kw_by_idx = {i: k for i, k in enumerate(keywords)}
    deps = load_dependents_any(args.dependents)
    deps_by_idx = {pool_idx[n]: d for n, d in deps.items() if n in pool_idx} if deps else None

    configs = {"cos(관문 없음)": hits}
    gated, drops = sp.apply_gates(hits, names, kw_by_idx, True)
    configs["gate(plugin·같은계열)"] = gated
    # keyword 로는 플러그인 판정을 안 하는 변형 — keywords 를 비워 이름 규칙만 남긴다 (markdown-it 오탐 검토용)
    name_only, drops_name = sp.apply_gates(hits, names, {}, True)
    configs["gate(이름만)"] = name_only
    if deps_by_idx is not None:
        gc, drops_c = sp.apply_gates(hits, names, kw_by_idx, True, dependents_by_idx=deps_by_idx)
        configs["gate+보완재"] = gc
        cov = sum(1 for n in names if n in deps) / len(names)

    # downloads 하한 스윕 (S15P21A506-450) — 프로덕션과 가장 가까운 관문(보완재 있으면 그것,
    # 없으면 plugin·같은계열) 결과 위에 downloads_last_month 하한만 추가로 건다.
    base_key = "gate+보완재" if deps_by_idx is not None else "gate(plugin·같은계열)"
    downloads_by_idx = {pool_idx[p["name"]]: p.get("downloads_last_month")
                         for p in pool if p["name"] in pool_idx}
    downloads_by_name = {p["name"]: p.get("downloads_last_month") for p in pool}
    floors = [int(f) for f in args.downloads_floors.split(",") if f.strip()]
    dl_drops = {}
    config_floor = {k: 0 for k in configs}  # 각 설정이 어느 downloads 하한에 대응하는지 (매칭 골드용)
    for floor in floors:
        dl_hits, dropped = apply_downloads_floor(configs[base_key], names, downloads_by_idx, floor)
        key = f"{base_key}+dl>={floor:,}"
        configs[key] = dl_hits
        config_floor[key] = floor
        dl_drops[floor] = dropped

    # 정답 기준 자체가 바뀌었으므로(기능 유사 → 기능 유사 + 인지도), downloads 하한을 건
    # 설정은 같은 하한으로 거른 골드("B도 그 인지도는 넘어야 진짜 정답")와 맞춰 잰다.
    # floor=0(구 정답지)은 그대로 남겨서 "얼마나 많이가 재라벨 때문인지" 대조할 수 있게 한다.
    gold_matched = {0: gold}
    gold_drop = {}
    for floor in floors:
        gm = filter_gold_by_popularity(gold, downloads_by_name, floor)
        gold_matched[floor] = gm
        old_pairs = sum(len(v) for v in gold.values())
        new_pairs = sum(len(v) for v in gm.values())
        gold_drop[floor] = {"골드쌍": f"{old_pairs}→{new_pairs}", "쿼리(base)": f"{len(gold)}→{len(gm)}"}

    shown = {k: shown_by_base(h, names) for k, h in configs.items()}

    lines = [
        f"eval_gate_ranking — {args.label}  model={args.model}",
        "=" * 60,
        f"골드: {os.path.basename(args.gold)}  도메인 {sorted(domains) if domains else '전체'}",
        f"쿼리(base) {len(gold)}건, 골드쌍 {sum(len(g) for g in gold.values())}건(양방향), "
        f"코퍼스 {len(names)}, retrieve-k {args.retrieve_k}",
    ]
    if deps_by_idx is not None:
        lines.append(f"dependents 커버리지: 코퍼스의 {cov:.1%} ({len(deps)}개 패키지) — "
                     "행이 없는 패키지가 낀 쌍은 보완재 관문이 판단을 보류하고 통과시킨다")
    lines += ["", f"관문 drop 수(top-{args.retrieve_k} 후보 기준): {drops}",
              f"이름만 판정 시 drop 수: {drops_name}"]
    if deps_by_idx is not None:
        lines.append(f"보완재 포함 drop 수: {drops_c}")
    lines.append(f"downloads 하한 drop 수 (기준: {base_key}): {dl_drops}")
    lines += ["", "[정답 기준 자체의 변화] downloads 하한별로 '정답(B)도 그 인지도를 넘는' 것만 남기면"
                  " 골드셋이 이렇게 줄어든다 (B 자체가 원래도 인지도 미달이면, 그 정답 자체가 새 기준"
                  " 아래선 더 이상 '틀렸다고 감점할 대상'이 아니다):"]
    for floor, d in gold_drop.items():
        lines.append(f"  dl>={floor:<8,} 골드쌍 {d['골드쌍']}  쿼리(base) {d['쿼리(base)']}")

    lines += ["", "[설정별 지표] (recall/precision/lt3_ratio + 선정된 TOP3의 downloads 분포)",
              "  downloads 하한이 걸린 설정은 '구 정답지'(원래 정답, 인지도 무관)와 '신 정답지'"
              "(같은 하한으로 거른 정답, B도 인지도 있어야 함) 둘 다 잰다 — 그 차이가"
              " '재라벨 때문에 사라진 손실'이다."]
    for k in configs:
        floor = config_floor[k]
        m = score(gold, shown[k])
        lines.append(f"  {k:28} {fmt(m)}  [구정답지]")
        if floor > 0:
            m_new = score(gold_matched[floor], shown[k])
            lines.append(f"  {'':28} {fmt(m_new)}  [신정답지: B도 dl>={floor:,}]")
            # 같은 신정답지 기준으로, 하한을 안 건 기존 시스템은 얼마나 하는지 — 하한이
            # 실제로 "누락됐던 인기 정답"을 더 건져오는지, 아니면 후보만 줄여 손해인지 확인용
            m_nofloor = score(gold_matched[floor], shown[base_key])
            lines.append(f"  {'':28} {fmt(m_nofloor)}  [신정답지, 하한無 비교용({base_key})]")
        lines.append(f"  {'':28} └ downloads: {fmt_downloads(downloads_stats(shown[k], downloads_by_name))}")

    lines += ["", "[참고] 예전 방식 — cos 임계값 τ 로 top-3 를 자름 (관문 없음 / 관문 있음)"]
    for tau in THRESHOLDS:
        a = score(gold, shown["cos(관문 없음)"], tau)
        b = score(gold, shown["gate(plugin·같은계열)"], tau)
        lines.append(f"  τ={tau:<4}  cos만: R@3 {a['recall@3']:.3f} P@3 {a['precision@3']:.3f} 노출 {a['avg_shown']:.2f}"
                     f"  |  gate+τ: R@3 {b['recall@3']:.3f} P@3 {b['precision@3']:.3f} 노출 {b['avg_shown']:.2f}")

    # 골드가 관문과 모순되는 경우 / 검색 상한
    cand_sets = defaultdict(set)
    for b, c, _ in hits:
        cand_sets[names[b]].add(names[c])
    gated_sets = defaultdict(set)
    for b, c, _ in gated:
        gated_sets[names[b]].add(names[c])
    in_top = blocked = 0
    blocked_ex = []
    for (dom, base), g in gold.items():
        for alt in g:
            if alt in cand_sets[base]:
                in_top += 1
                if alt not in gated_sets[base]:
                    blocked += 1
                    blocked_ex.append((dom, base, alt))
    total = sum(len(g) for g in gold.values())
    lines += ["", f"[검색 상한] 골드쌍 중 top-{args.retrieve_k} 안에 든 비율 {in_top / max(total, 1):.3f} "
                  f"(recall@{args.retrieve_k}) — 이보다 위로는 어떤 관문·정렬로도 못 올린다",
              f"[관문 모순] top-{args.retrieve_k} 안의 골드쌍 중 관문이 잘라낸 것 {blocked}/{in_top}"
              " — 라벨과 관문 정의가 충돌(오탐 관문이거나 오라벨). 예시:"]
    for dom, base, alt in blocked_ex[:15]:
        lines.append(f"    [{dom}] {base} -> {alt}")

    lines += ["", "[도메인별] (cos → gate)"]
    for dom in sorted({d for d, _ in gold}):
        sub = {k: v for k, v in gold.items() if k[0] == dom}
        c, g = score(sub, shown["cos(관문 없음)"]), score(sub, shown["gate(plugin·같은계열)"])
        lines.append(f"  {dom:14} 쿼리{c['bases']:4}  R@3 {c['recall@3']:.3f}→{g['recall@3']:.3f}  "
                     f"P@3 {c['precision@3']:.3f}→{g['precision@3']:.3f}  평균노출 {c['avg_shown']:.2f}→{g['avg_shown']:.2f}")

    os.makedirs(args.out, exist_ok=True)
    report = "\n".join(lines)
    with open(os.path.join(args.out, f"eval_gate_{args.label}_report.txt"), "w", encoding="utf-8") as f:
        f.write(report)
    raw = {k: {b: v for b, v in s.items()} for k, s in shown.items()}
    with open(os.path.join(args.out, f"eval_gate_{args.label}.json"), "w", encoding="utf-8") as f:
        json.dump({"shown": raw, "gold": {f"{d}|{b}": sorted(g) for (d, b), g in gold.items()},
                   "downloads_by_name": downloads_by_name},
                  f, ensure_ascii=False)
    try:
        print(report)
    except UnicodeEncodeError:
        print(report.encode("ascii", "replace").decode())


if __name__ == "__main__":
    main()
