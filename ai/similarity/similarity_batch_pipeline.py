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
  4 구조적 관문      구현 — plugin/adapter·same-family·repo_archived·보완재(dependents 교집합
                      >0.3, package_dependents.parquet 이 입력 옆에 있을 때) drop (--gate, 기본 on, S15P21A506-333·173)
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


DEPENDENTS_FILENAME = "package_dependents.parquet"


def resolve_dependents_path(explicit: str | None, package_text_path: str) -> str | None:
    """보완재 관문이 읽을 dependents parquet 경로 (S15P21A506-173).

    --dependents 로 직접 지정하면 그 경로(없어도 그대로 — 경고는 호출부가 한다). 안 줬으면
    --package-text 와 **같은 폴더**의 `package_dependents.parquet` 을 찾는다. 배치가
    /work/in/ 에서 입력을 읽으므로 ai-stage 가 그 파일을 옆에 복사해 두기만 하면
    인자를 안 넘겨도 관문이 돈다. 둘 다 없으면 None.
    """
    if explicit:
        return explicit
    sibling = os.path.join(os.path.dirname(os.path.abspath(package_text_path)), DEPENDENTS_FILENAME)
    return sibling if os.path.exists(sibling) else None


def load_dependents(path: str | None, kind: str = "regular") -> dict[str, set[str]]:
    """package_dependents 류 parquet(name·kind·dependents)를 name → dependents 집합으로.

    데이터 팀이 후보 풀(29,310개) 기준으로 재계산해준 파일(2026-09-16, 100% 커버) 형태를
    전제한다. kind 는 기본 'regular' — 실측(웹팩↔웹팩-cli 0.903 vs 웹팩↔롤업 0.075)으로
    이 한 종류만으로도 보완재/대안 판별 신호가 뚜렷했다(S15P21A506-173). 파일이 없으면
    빈 dict — 그러면 apply_gates() 의 보완재 관문이 자동으로 꺼진다(기존 호출부 그대로 둠).
    """
    if not path or not os.path.exists(path):
        return {}
    import pyarrow.parquet as pq

    tbl = pq.read_table(path, columns=["name", "kind", "dependents"]).to_pylist()
    deps = {r["name"]: set(r["dependents"] or []) for r in tbl if r["kind"] == kind}
    log(f"dependents({kind}): {len(deps)} 개 패키지")
    return deps


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

    우산↔하위모듈 판정(접두어 비교)은 **스코프를 벗겨내지 않고 전체 이름**으로 한다
    (S15P21A506-334). 한쪽만 스코프가 있으면 그 판정에서 제외한다 — 스코프를 벗겨낸
    뒤 남는 이름이 우연히 같은 단어를 포함할 뿐인 무관한 패키지(예: 'markdown-it' 와
    '@ts-stack/markdown')를 같은 계열로 오탐하기 때문이다.

    다만 스코프 없는 이름이 상대방의 **스코프(조직명) 자체와 정확히 같으면** 그
    조직이 낸 서브패키지로 본다 (S15P21A506-334 후속) — 'parcel'과 그 프로젝트가
    낸 '@parcel/graph'처럼. 이건 이름 조각이 우연히 겹치는 것과 달리, "이 스코프를
    만든 조직이 곧 이 이름의 프로젝트"라는 훨씬 강한 신호라 위의 오탐 사례와
    다르다. 조직명이 아니라 하위 경로까지 우연히 같은 경우(예: 'passport'와
    '@passport-next/passport')는 잡지 않는다 — 스코프 자체가 다르면 별개 조직이다.

    '@types/x'는 예외로 스코프가 아니라 슬래시 뒤 이름으로 비교한다 — DefinitelyTyped
    관례상 '@types/x'는 항상 'x'의 타입 선언 파일이지 'x'의 대안이 될 수 없다.
    """
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


def is_repo_archived(value) -> bool:
    """GitHub 저장소가 archived(보관 처리)됐는가 (S15P21A506-333).

    `repo_full_name` 이 없어 build_package_text.py 의 repo_stat 과 LEFT JOIN 이 안 되면
    이 값은 NULL(None) — 그 경우는 보관 아님으로 취급한다.
    """
    return bool(value)


def is_complement(
    base_dependents: set[str] | None,
    cand_dependents: set[str] | None,
    threshold: float = 0.3,
    min_sample: int = 20,
) -> bool:
    """base 와 cand 가 자주 같이 쓰이는 보완재인가 (S15P21A506-173).

    dependents(그 패키지를 쓰는 다른 패키지들) 집합의 겹침 비율 = 교집합 ÷ 둘 중
    더 작은 쪽 크기(containment). 실측(2026-09-16, 후보 풀 29,310개 기준 dependents,
    kind=regular)으로 이 계산이 보완재(webpack↔webpack-cli 0.903, express↔body-parser
    0.873)와 진짜 대안(webpack↔rollup 0.075)을 뚜렷하게 갈라놓는 걸 확인했다. 큰 쪽
    기준으로 나누면(예: webpack↔webpack-cli 0.237) 신호가 뭉개져 이 방식을 안 쓴다.

    둘 중 하나라도 dependents 데이터가 없으면(빈 집합 포함) 판단하지 않고 False —
    데이터 없다고 감점하면 안 되므로 통과가 기본값이다.

    `min_sample`: 둘 중 더 작은 쪽의 dependents 수가 이보다 작으면 비율이 통계적으로
    못 미더우니 판단을 보류한다(False). 실측(테스트 알테너티브 315쌍 교차검증) 중
    `jest`↔`@japa/runner`가 dependents 7개짜리 우연한 겹침만으로 비율 0.571까지
    나와 진짜 대안인데 오탐 위험이 있었던 걸 보고 추가한 안전장치 — 그 315쌍 중
    이런 표본 부족 오탐은 이 사례 하나뿐이었고, 실제 보완재들은 전부 표본이 수백~
    수만 규모라 20으로 잡아도 재현율에 영향이 없었다.
    """
    if not base_dependents or not cand_dependents:
        return False
    if min(len(base_dependents), len(cand_dependents)) < min_sample:
        return False
    inter = len(base_dependents & cand_dependents)
    ratio = inter / min(len(base_dependents), len(cand_dependents))
    return ratio > threshold


def apply_gates(
    hits: list[tuple[int, int, float]],
    names: list[str],
    keywords_by_idx: dict[int, list],
    enabled: bool,
    archived_by_idx: dict[int, bool] | None = None,
    dependents_by_idx: dict[int, set[str]] | None = None,
) -> tuple[list[tuple[int, int, float]], dict]:
    """--gate 시 hits 에서 구조적으로 대안이 아닌 (base, cand) 쌍을 제거한다.

    plugin/adapter·same-family(우산·하위모듈·스코프)에 더해, `archived_by_idx` 를 주면
    GitHub 저장소가 archived 된 후보도, `dependents_by_idx` 를 주면 보완재(dependents
    교집합 > 0.3, S15P21A506-173)도 drop 한다. enabled=False 면 무변경.

    `drops["complement"]` 는 항상 들어간다 — dependents 를 안 줘서 관문이 안 돌았으면 None,
    돌았으면 걸러낸 쌍 수. manifest 에서 "0건 걸렀다" 와 "안 돌았다" 를 구분하려는 것이다.
    """
    if not enabled:
        return hits, {}
    drops = {"plugin_adapter": 0, "same_family": 0}
    if archived_by_idx is not None:
        drops["repo_archived"] = 0
    drops["complement"] = 0 if dependents_by_idx is not None else None
    kept = []
    for base_idx, cand_idx, cos in hits:
        cand = names[cand_idx]
        if is_plugin_adapter(cand, keywords_by_idx.get(cand_idx)):
            drops["plugin_adapter"] += 1
            continue
        if is_same_family(names[base_idx], cand):
            drops["same_family"] += 1
            continue
        if archived_by_idx is not None and is_repo_archived(archived_by_idx.get(cand_idx)):
            drops["repo_archived"] += 1
            continue
        if dependents_by_idx is not None and is_complement(
            dependents_by_idx.get(base_idx), dependents_by_idx.get(cand_idx)
        ):
            drops["complement"] += 1
            continue
        kept.append((base_idx, cand_idx, cos))
    return kept, drops


def dependents_coverage(names: list[str], dependents_map: dict[str, set[str]]) -> dict | None:
    """이번 배치 패키지 중 dependents 행이 있는 비율 (S15P21A506-173).

    보완재 관문은 dependents 가 없는 패키지가 낀 쌍을 판단하지 못하고 통과시킨다. dependents
    파일이 만들어진 뒤 후보 풀이 바뀌면 그런 패키지가 늘어나도 결과는 겉으로 똑같아서, 이 비율을
    manifest 에 남겨 파일이 낡았는지 볼 수 있게 한다.

    "있음" 은 파일에 그 이름의 행이 있다는 뜻이다. 의존자가 0개인 패키지도 행은 있으므로
    센다 — 그건 결측이 아니라 "의존자 없음" 이라는 범주다. dependents 를 안 줘서
    (dependents_map 이 비어) 관문이 안 돌면 None.
    """
    if not dependents_map:
        return None
    covered = sum(1 for n in names if n in dependents_map)
    return {
        "pool": len(names),
        "with_dependents": covered,
        "ratio": round(covered / len(names), 4) if names else 0.0,
    }


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
    p.add_argument("--model-dir", required=True, help="onnx_bge_vN 디렉터리 (model.onnx + tokenizer) — 버전은 ai/MODEL_CONTRACT.md 기준")
    p.add_argument("--out", required=True, help="산출물 디렉터리")
    p.add_argument("--raw-text-column", default=None,
                   help="이 컬럼을 모델 입력으로 그대로 사용 (샘플: description). 생략 시 description+keywords 조립")
    p.add_argument("--state", default=None, help="이전 실행의 text_hash_state.parquet (증분 재임베딩용)")
    p.add_argument("--dependents", default=None,
                   help="후보 풀 기준 package_dependents parquet (S15P21A506-173, 보완재 감점용). "
                        f"생략하면 --package-text 와 같은 폴더의 {DEPENDENTS_FILENAME} 를 찾고, "
                        "그것도 없으면 경고 후 보완재 관문만 건너뛴다")
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
    archived_by_idx = {i: rows[i].get("repo_archived") for i in range(len(rows))}
    dependents_path = resolve_dependents_path(args.dependents, args.package_text)
    dependents_map = load_dependents(dependents_path)
    if not dependents_map and args.gate:
        log(
            "경고: 보완재 관문 건너뜀 — dependents 데이터 없음 "
            f"({dependents_path or '--package-text 옆 ' + DEPENDENTS_FILENAME + ' 없음'})"
        )
    dependents_by_idx = {i: dependents_map.get(names[i]) for i in range(len(names))} if dependents_map else None
    coverage = dependents_coverage(names, dependents_map)
    if coverage:
        log(f"dependents 커버리지: {coverage['with_dependents']}/{coverage['pool']} ({coverage['ratio']:.1%})")
    hits, gate_drops = apply_gates(
        hits, names, keywords_by_idx, args.gate, archived_by_idx, dependents_by_idx
    )
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
            "dependents": dependents_path,
            "dependents_coverage": coverage,
            "raw_text_column": args.raw_text_column,
        },
        "elapsed_sec": round(time.time() - t0, 1),
    }
    write_output(args.out, candidates, rows, gate, meta, args.allow_gate_skip)
    log(f"완료 — {meta['elapsed_sec']}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
