"""유사도 배치 파이프라인 (§4.1) — EC2 #1에서 cron이 배치 시각마다 1회성으로 실행.

코퍼스 자격 필터 → (변경분) ONNX 재임베딩 → 의미 검색(넓게) → 구조적 관문 → cos 정렬
→ 채점 게이트 → MinIO 산출물(_SUCCESS + manifest). PostgreSQL은 건드리지 않는다(방식 C).

모델 I/O·전처리 규격: ai/MODEL_CONTRACT.md
설계: docs/Pickage_기능별_개발_구상안_0909.md §3.3, §4.1, §4.2
2단계 랭커(넓게 검색 → 관문 → 정렬): 제안_유사후보_v1랭커_2단계분리_260910.md (2026-09-10 팀 승인)

현재 구현 상태 (S15P21A506-168):
  1 자격 필터        구현 — deprecated 완전 제외 (DEC-RANK-20260909-01)
  2 변경분 재임베딩    구현 (--state 로 이전 text_hash 비교, 없으면 전수)
  3 의미 검색        구현 — --retrieve-k(기본 30) 개. 최종 노출(3)보다 넉넉히
  4 구조적 관문      구현 — plugin/adapter·same-family drop (--gate, 기본 on).
                      보완재 감점(dependents 교집합 >0.3)은 의존 그래프 필요 → TODO
  4b 정렬           구현 — 관문 통과분을 cos 유사도 순. 다른 가·감점 없음.
                      move_lift·deprecated 지목 가산 없음
  5 채점 게이트       TODO — deprecated 51K 홀드아웃 정의 미확정 (S15P21A506-169)
  6 산출물           구현 (로컬 디렉터리. s3:// 출력은 후속)
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import time
from typing import Iterable

import numpy as np

# onnxruntime · transformers · pyarrow 는 무겁고 배치 실행 노드에만 설치된다.
# 순수 로직(자격 필터·top-K·재랭킹·게이트)을 numpy 만으로 테스트할 수 있도록
# 각 호출부에서 지연 import 한다.

MAX_LENGTH = 512  # ai/MODEL_CONTRACT.md — SentenceTransformer.max_seq_length
DEPRECATED_STATUSES = {"deprecated", "removed", "unpublished"}


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ── 입력 ────────────────────────────────────────────────────────────────

def load_package_text(path: str) -> list[dict]:
    """package_text parquet 를 행 dict 목록으로 읽는다.

    기대 컬럼: name, description, keywords, dependent_packages_count,
    latest_release_published_at, status (일부는 없을 수 있음).
    """
    import pyarrow.parquet as pq

    table = pq.read_table(path)
    rows = table.to_pylist()
    log(f"package_text: {len(rows)} 행  ({path})")
    return rows


def build_text(row: dict, raw_column: str | None) -> str:
    """모델 입력 텍스트. raw_column 이 주어지면 그 값을 그대로,
    아니면 'DESCRIPTION: {description} / KEYWORDS: {k1, k2, ...}' 로 조립한다."""
    if raw_column:
        return (row.get(raw_column) or "").strip()
    desc = (row.get("description") or "").strip()
    kws = row.get("keywords") or []
    if isinstance(kws, str):
        kws = [kws]
    return f"DESCRIPTION: {desc} / KEYWORDS: {', '.join(kws)}"


# ── 1. 코퍼스 자격 필터 (§4.1) ──────────────────────────────────────────

def _parse_date(value) -> dt.date | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    s = str(value)[:10]
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        return None


def qualify(rows: list[dict], min_dependents: int, max_age_months: int) -> list[dict]:
    """dependents 하한 · 최근 N개월 릴리스 · deprecated 제외 로 코퍼스를 좁힌다.

    deprecated 는 여기서 코퍼스째 제외한다 (DEC-RANK-20260909-01 — 지목 가산 아님).
    """
    cutoff = dt.date.today() - dt.timedelta(days=int(max_age_months * 30.44))
    kept, drop_dep, drop_age, drop_status = [], 0, 0, 0
    for r in rows:
        dep = r.get("dependent_packages_count")
        if dep is None or dep < min_dependents:
            drop_dep += 1
            continue
        released = _parse_date(r.get("latest_release_published_at"))
        if released is not None and released < cutoff:
            drop_age += 1
            continue
        status = (r.get("status") or "").lower()
        if status in DEPRECATED_STATUSES or r.get("is_spam"):
            drop_status += 1
            continue
        kept.append(r)
    log(
        f"자격 필터: {len(rows)} → {len(kept)}  "
        f"(dependents<{min_dependents} {drop_dep}, {max_age_months}개월 초과 {drop_age}, "
        f"deprecated/spam {drop_status})"
    )
    return kept


# ── 2. 변경분 재임베딩 (§4.1) ──────────────────────────────────────────

def text_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def load_state(path: str | None) -> dict[str, dict]:
    """이전 실행의 name → {hash, vector} 상태. 없으면 빈 dict (전수 임베딩)."""
    if not path or not os.path.exists(path):
        return {}
    import pyarrow.parquet as pq

    tbl = pq.read_table(path).to_pylist()
    state = {r["name"]: {"hash": r["text_hash"], "vector": np.array(r["vector"], dtype=np.float32)} for r in tbl}
    log(f"이전 상태: {len(state)} 개 (재임베딩 생략 후보)")
    return state


class OnnxEmbedder:
    """ai/MODEL_CONTRACT.md 규격: 입력 int64, 출력 last_hidden_state,
    후처리는 여기서 (CLS pooling + L2 정규화). ONNX 밖."""

    def __init__(self, model_dir: str):
        import onnxruntime as ort
        from transformers import AutoTokenizer

        self.tok = AutoTokenizer.from_pretrained(model_dir)
        self.sess = ort.InferenceSession(
            os.path.join(model_dir, "model.onnx"), providers=["CPUExecutionProvider"]
        )
        self.model_ver = self._read_model_ver(model_dir)
        log(f"ONNX 로드: {model_dir}  (model_ver={self.model_ver})")

    @staticmethod
    def _read_model_ver(model_dir: str) -> str:
        mf = os.path.join(model_dir, "run_manifest.json")
        if os.path.exists(mf):
            try:
                return json.load(open(mf, encoding="utf-8")).get("model_ver", "unknown")
            except Exception:
                pass
        return "unknown"

    def encode(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        out: list[np.ndarray] = []
        for i in range(0, len(texts), batch_size):
            enc = self.tok(
                texts[i : i + batch_size],
                padding=True,
                truncation=True,
                max_length=MAX_LENGTH,
                return_tensors="np",
            )
            h = self.sess.run(
                None,
                {
                    "input_ids": enc["input_ids"].astype("int64"),
                    "attention_mask": enc["attention_mask"].astype("int64"),
                },
            )[0]
            v = h[:, 0, :]  # CLS pooling
            v = v / np.linalg.norm(v, axis=1, keepdims=True)  # L2 정규화
            out.append(v.astype(np.float32))
            if (i // batch_size) % 50 == 0 and i:
                log(f"  임베딩 {i}/{len(texts)}")
        return np.vstack(out) if out else np.zeros((0, 384), dtype=np.float32)


def embed_corpus(
    rows: list[dict], texts: list[str], embedder: OnnxEmbedder, state: dict, batch_size: int
) -> np.ndarray:
    """text_hash 가 바뀐 항목만 재임베딩하고, 나머지는 이전 벡터를 재사용한다."""
    hashes = [text_hash(t) for t in texts]
    to_embed = [i for i, (r, h) in enumerate(zip(rows, hashes)) if state.get(r["name"], {}).get("hash") != h]
    log(f"재임베딩 대상: {len(to_embed)} / {len(rows)} (변경·신규분)")

    vectors = np.zeros((len(rows), 384), dtype=np.float32)
    for i, r in enumerate(rows):
        if i not in set(to_embed):
            vectors[i] = state[r["name"]]["vector"]
    if to_embed:
        fresh = embedder.encode([texts[i] for i in to_embed], batch_size=batch_size)
        for k, i in enumerate(to_embed):
            vectors[i] = fresh[k]
    for i, h in enumerate(hashes):
        rows[i]["_text_hash"] = h
    return vectors


# ── 3. 의미 검색 top-K (§4.1) ─────────────────────────────────────────

def top_k(vectors: np.ndarray, names: list[str], k: int, query_block: int) -> list[tuple[int, int, float]]:
    """정규화 벡터 블록 행렬곱으로 패키지별 top-k(자기 자신 제외). (base_idx, cand_idx, cos)."""
    n = len(names)
    results: list[tuple[int, int, float]] = []
    for start in range(0, n, query_block):
        end = min(start + query_block, n)
        sims = vectors[start:end] @ vectors.T  # (block, n)
        for local, base_idx in enumerate(range(start, end)):
            row = sims[local]
            row[base_idx] = -np.inf  # 자기 자신 제외
            top = np.argpartition(-row, min(k, n - 1))[:k]
            top = top[np.argsort(-row[top])]
            for cand_idx in top:
                results.append((base_idx, int(cand_idx), float(row[cand_idx])))
        log(f"  top-{k} {end}/{n}")
    return results


# ── 4. 정렬 (§4.2) — 후보를 cos 유사도 순으로 (main 에서 관문 뒤에 실행) ──

def rerank(
    hits: list[tuple[int, int, float]],
    names: list[str],
    k_user: int,
) -> list[dict]:
    """v1 재랭킹 (§4.2, DEC-RANK-20260909-01).

    구현: cos 유사도를 그대로 score 로 쓴다.
      - move_lift(대체 이동 쌍 관측 가산) 배제 확정 (DEC-RANK-20260907-01)
      - deprecated 지목 가산 없음 (0909) — deprecated 는 1단계 qualify() 에서 코퍼스째
        제외되므로 여기까지 후보로 올라오지 않는다. 별도 drop 불필요.
    TODO(S15P21A506-168): 보완재 감점 — dependents 교집합 >0.3. 의존 그래프 필요.
    """
    by_base: dict[int, list[dict]] = {}
    for base_idx, cand_idx, cos in hits:
        by_base.setdefault(base_idx, []).append(
            {
                "candidate": names[cand_idx],
                "cos": round(cos, 6),
                "score": round(cos, 6),
                "reason": ["SEMANTIC_RELEVANCE"],
            }
        )

    out: list[dict] = []
    for base_idx, cands in by_base.items():
        cands.sort(key=lambda c: -c["score"])
        for rank, c in enumerate(cands[:k_user], start=1):
            out.append(
                {
                    "base_package": names[base_idx],
                    "candidate_package": c["candidate"],
                    "cos_score": c["cos"],
                    "final_score": c["score"],
                    "rank": rank,
                    "ranking_reason": c["reason"],
                    "user_visible": rank <= 3,      # §4.2 사용자 노출 최대 3
                    "default_selected": rank <= 2,  # §4.2 상위 2 기본 선택
                }
            )
    return out


# ── 4 (관문). 구조적 관문 (§4.2, 2단계 랭커 — --gate 기본 on) ───────────
#
# 검색 결과 중 "설명은 비슷하지만 대안이 아닌" 후보를 점수 조정이 아니라
# 통과/탈락으로 걸러낸다. main 에서 정렬(위 §4) 앞에 실행. 각 판정은 순수 함수.

_PLUGIN_MARKERS = {"plugin", "adapter", "preset", "loader"}


def is_plugin_adapter(name: str, keywords: list[str] | None) -> bool:
    """이름·keywords 로 플러그인/어댑터/프리셋/로더/설정을 판별 (S15P21A506-173).

    'eslint-plugin-react', 'css-loader', 'babel-preset-env', '@sveltejs/adapter-node',
    'eslint-config-airbnb' 처럼 다른 패키지에 얹혀 동작하는 것 = 대안이 아니다.
    """
    base = name.rsplit("/", 1)[-1].lower()
    parts = base.replace("_", "-").split("-")
    if len(parts) >= 2:
        for i, p in enumerate(parts):
            if p in _PLUGIN_MARKERS:
                return True
            if p == "config" and i != len(parts) - 1:  # 'node-config'(단독) 오탐 방지
                return True
    for k in keywords or []:
        toks = str(k).lower().replace("-", " ").split()
        if any(t in _PLUGIN_MARKERS for t in toks):
            return True
    return False


def is_same_family(a: str, b: str) -> bool:
    """두 패키지가 같은 계열인가 — 우산↔하위모듈·같은 포장·같은 스코프.

    'd3'↔'d3-axis', 'lodash'↔'lodash.pickby', 'lodash'↔'lodash-es',
    '@babel/core'↔'@babel/preset-env'. 대안이 아니다. 'react'↔'preact' 는 계열 아님.
    """
    a, b = a.lower(), b.lower()
    if a == b:
        return True
    if a.startswith("@") and b.startswith("@") and a.split("/", 1)[0] == b.split("/", 1)[0]:
        return True
    ba, bb = a.rsplit("/", 1)[-1], b.rsplit("/", 1)[-1]
    for x, y in ((ba, bb), (bb, ba)):
        if len(y) > len(x) and y.startswith(x) and y[len(x)] in "-._":
            return True
    return False


def apply_gates(
    hits: list[tuple[int, int, float]],
    names: list[str],
    keywords_by_idx: dict[int, list],
    enabled: bool,
) -> tuple[list[tuple[int, int, float]], dict]:
    """--gate 시 hits 에서 구조적으로 대안이 아닌 (base, cand) 쌍을 제거한다.

    보완재 감점(의존 그래프)은 아직 미구현 — 여기서는 이름·keywords 만으로 판정 가능한
    plugin/adapter 와 same-family(우산·하위모듈·스코프)만 drop 한다. enabled=False 면 무변경.
    """
    if not enabled:
        return hits, {}
    kept, drops = [], {"plugin_adapter": 0, "same_family": 0}
    for base_idx, cand_idx, cos in hits:
        cand = names[cand_idx]
        if is_plugin_adapter(cand, keywords_by_idx.get(cand_idx)):
            drops["plugin_adapter"] += 1
            continue
        if is_same_family(names[base_idx], cand):
            drops["same_family"] += 1
            continue
        kept.append((base_idx, cand_idx, cos))
    return kept, drops


# ── 5. 채점 게이트 (§4.1) — TODO ──────────────────────────────────────

def scoring_gate(candidates: list[dict]) -> dict:
    """deprecated 51K 홀드아웃으로 Recall@20/@10 측정, 직전 운영값 대비 하락 시 중단.

    TODO(S15P21A506-169): 51K 홀드아웃 구성 방식 미확정. 현재는 SKIPPED.
    """
    return {
        "status": "SKIPPED",
        "reason": "51K holdout undefined (S15P21A506-169)",
        "measured_candidate_rows": len(candidates),
    }


# ── 6. 산출물 (§4.1) ──────────────────────────────────────────────────

def gate_allows_success(gate: dict, allow_gate_skip: bool) -> bool:
    """`_SUCCESS` 마커를 기록해도 되는가 (= 로더가 이 실행을 적재해도 되는가).

    PASSED 는 항상 허용. SKIPPED 는 --allow-gate-skip 일 때만. 그 외(FAILED 등)는 불허.
    """
    status = gate["status"]
    return status == "PASSED" or (status == "SKIPPED" and allow_gate_skip)


def write_output(
    out_dir: str,
    candidates: list[dict],
    rows: list[dict],
    gate: dict,
    meta: dict,
    allow_gate_skip: bool,
) -> None:
    os.makedirs(out_dir, exist_ok=True)

    import pyarrow as pa
    import pyarrow.parquet as pq

    pq.write_table(pa.Table.from_pylist(candidates), os.path.join(out_dir, "candidates.parquet"))
    pq.write_table(
        pa.Table.from_pylist([{"name": r["name"], "text_hash": r["_text_hash"]} for r in rows]),
        os.path.join(out_dir, "text_hash_state.parquet"),
    )

    manifest = {
        **meta,
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
        "candidate_rows": len(candidates),
        "base_packages": len({c["base_package"] for c in candidates}),
        "scoring_gate": gate,
    }
    json.dump(manifest, open(os.path.join(out_dir, "run_manifest.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    if gate_allows_success(gate, allow_gate_skip):
        open(os.path.join(out_dir, "_SUCCESS"), "w").close()
        log(f"_SUCCESS 기록 ({out_dir})")
    else:
        log(f"게이트 미통과({gate['status']}) — _SUCCESS 미기록. 로더가 이 실행을 무시함")


# ── main ─────────────────────────────────────────────────────────────

def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="유사 패키지 후보 배치 (§4.1)")
    p.add_argument("--package-text", required=True, help="package_text parquet 경로")
    p.add_argument("--model-dir", required=True, help="onnx_bge_v6 디렉터리 (model.onnx + tokenizer)")
    p.add_argument("--out", required=True, help="산출물 디렉터리")
    p.add_argument("--raw-text-column", default=None,
                   help="이 컬럼을 모델 입력으로 그대로 사용 (샘플: description). 생략 시 description+keywords 조립")
    p.add_argument("--state", default=None, help="이전 실행의 text_hash_state.parquet (증분 재임베딩용)")
    p.add_argument("--min-dependents", type=int, default=5)
    p.add_argument("--max-age-months", type=int, default=12)
    p.add_argument("--retrieve-k", type=int, default=30,
                   help="검색 단계 후보 수 (DEC-RANK: 최종보다 넉넉히 뽑아 관문으로 좁힌다)")
    p.add_argument("--user-k", type=int, default=20, help="재랭킹 후 산출할 상위 개수 (화면 노출은 rank<=3)")
    p.add_argument("--gate", action=argparse.BooleanOptionalAction, default=True,
                   help="구조적 관문(plugin/adapter·same-family drop). 기본 on, --no-gate 로 끔")
    p.add_argument("--batch-size", type=int, default=32)
    p.add_argument("--query-block", type=int, default=2000)
    p.add_argument("--allow-gate-skip", action="store_true",
                   help="채점 게이트 미구현 상태에서도 _SUCCESS 기록 (개발용)")
    return p.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    t0 = time.time()

    rows = load_package_text(args.package_text)
    rows = qualify(rows, args.min_dependents, args.max_age_months)
    if not rows:
        log("자격 통과 패키지 0개 — 중단")
        return 1

    texts = [build_text(r, args.raw_text_column) for r in rows]
    names = [r["name"] for r in rows]

    embedder = OnnxEmbedder(args.model_dir)
    state = load_state(args.state)
    vectors = embed_corpus(rows, texts, embedder, state, args.batch_size)

    hits = top_k(vectors, names, args.retrieve_k, args.query_block)
    log(f"검색 top-{args.retrieve_k}: {len(hits)} 쌍 ({len(names)} base)")

    keywords_by_idx = {i: (rows[i].get("keywords") or []) for i in range(len(rows))}
    hits, gate_drops = apply_gates(hits, names, keywords_by_idx, args.gate)
    if args.gate:
        log(f"구조적 관문: {gate_drops} → {len(hits)} 쌍 잔여")

    candidates = rerank(hits, names, args.user_k)

    gate = scoring_gate(candidates)
    log(f"채점 게이트: {gate['status']} ({gate.get('reason', '')})")

    meta = {
        "model_ver": embedder.model_ver,
        "input_package_text": os.path.abspath(args.package_text),
        "input_rows_qualified": len(rows),
        "params": {
            "min_dependents": args.min_dependents,
            "max_age_months": args.max_age_months,
            "retrieve_k": args.retrieve_k,
            "user_k": args.user_k,
            "gate": args.gate,
            "gate_drops": gate_drops,
            "raw_text_column": args.raw_text_column,
        },
        "elapsed_sec": round(time.time() - t0, 1),
    }
    write_output(args.out, candidates, rows, gate, meta, args.allow_gate_skip)
    log(f"완료 — {meta['elapsed_sec']}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
