"""S15P21A506-476 — P3(available_package 교체) 전 영향 점검.

보고서 가능 범위 = 재정렬 10만 ∩ 다운로드 대상 46.9만 (운영 확정 전 잠정). 이를 기존 10만과 비교한다.
- 유지·들어옴·빠짐과 그 구성
- 좁은 분야(keywords 20~49개)·중간 분야(50~199개)에서 3개 이상이 범위에 있는 비율
  (datasets/targets/README.md §7-4 방식. README 값은 재정렬 10만 기준이라 다운로드 없는 8,283개를 포함한다)
- 분야별 예시와 한국 관련 패키지의 들어옴·빠짐

저장소 루트에서 실행한다. 입력: datasets/targets/*.csv, data/keywords/package_text/package_text_2026-09-08.parquet
  python docs/worklogs/S15P21A506-475/phase6_p3_impact.py > docs/worklogs/S15P21A506-475/evidence/phase6/P3-impact.txt
"""
import collections
import csv
import re

import pyarrow.parquet as pq

T = "datasets/targets/"


def names(f):
    return {r["name"] for r in csv.DictReader(open(T + f, encoding="utf-8"))}


old_rows = list(csv.DictReader(open(T + "rank_top100k_20260902.csv", encoding="utf-8")))
old = {r["name"] for r in old_rows}
# 기존 목록 통계는 목록을 만든 기준값(09-02 월 다운로드)으로 잰다. package_text(09-08) 값과 다르다.
old_dl = {r["name"]: int(float(r["downloads_last_month"] or 0)) for r in old_rows}
rerank = {r["name"]: r for r in csv.DictReader(open(T + "rerank_100k_20260922.csv", encoding="utf-8"))}
expanded = names("expanded_468k_20260922.csv")
pool = names("candidate_pool_260916.csv")
rep = {n for n in rerank if n in expanded}

t = pq.read_table(
    "data/keywords/package_text/package_text_2026-09-08.parquet",
    columns=["name", "keywords", "description", "status", "is_spam", "downloads_last_month"],
).to_pydict()
kw = collections.defaultdict(set)
dl, desc, kwtext, alive = {}, {}, {}, set()
for n, k, d, s, sp, m in zip(t["name"], t["keywords"], t["description"], t["status"], t["is_spam"], t["downloads_last_month"]):
    if s in ("removed", "unpublished") or sp:
        continue
    alive.add(n)
    dl[n] = m or 0
    desc[n] = d or ""
    kwtext[n] = " ".join(k or [])
    for x in {x.lower() for x in (k or [])}:
        kw[x].add(n)

kept, added, dropped = old & rep, rep - old, old - rep
print("## 1. 범위 변화 (잠정)")
print(f"기존 10만 {len(old):,} · 재정렬 10만 {len(rerank):,} · 보고서 가능(재정렬∩46.9만) {len(rep):,}")
print(f"재정렬 10만 중 다운로드 대상 밖 {len(set(rerank) - expanded):,}")
print(f"유지 {len(kept):,} · 들어옴 {len(added):,} · 빠짐 {len(dropped):,}")
print("들어옴 규칙별", dict(collections.Counter(rerank[n]["reason"] for n in added)))
dd = [old_dl[n] for n in dropped]
print(f"빠짐 중 (09-02 목록 기준) 월 100만 이상 {sum(d >= 1_000_000 for d in dd)} · 10만 이상 {sum(d >= 100_000 for d in dd)} · 스코프 {sum(n.startswith('@') for n in dropped):,}")
print("빠짐 상위 스코프", collections.Counter(n.split("/")[0] for n in dropped if n.startswith("@")).most_common(5))
print(f"AI 후보 풀 포함 {len(pool & old):,} → {len(pool & rep):,} / {len(pool):,}")
print(f"기존 10만 월 다운로드 최저 (09-02 목록 기준) {min(old_dl.values()):,}")

print("\n## 2. 분야 커버리지 (keywords 기준, 3개 이상 범위에 있는 분야 비율)")
for lo, hi, lab in [(20, 49, "좁은 분야"), (50, 199, "중간 분야")]:
    ks = [k for k, v in kw.items() if lo <= len(v) <= hi]
    row = [f"{nm} {100 * sum(len(kw[k] & S) >= 3 for k in ks) / len(ks):.1f}%" for nm, S in [("기존", old), ("재정렬", set(rerank)), ("보고서 가능", rep)]]
    print(f"{lab}({lo}~{hi}개, {len(ks):,}개 분야): " + " · ".join(row))

print("\n## 3. 분야 예시 (전 → 후, +들어옴 −빠짐)")
for w in ["ai-agent", "smarthome", "computer-vision", "home-automation", "zigbee", "opencv", "dify", "raspberry", "gpio", "arduino", "korea", "korean"]:
    v = kw.get(w, set())
    o, r = v & old, v & rep
    print(f"{w}: {len(o)} → {len(r)} (+{len(r - o)} −{len(o - r)})")

print("\n## 4. 사례 패키지")
for n in ["dify-client", "opencv4nodejs", "zigbee2mqtt", "onoff"]:
    r = rerank.get(n)
    print(n, "기존10만", n in old, "| 보고서 가능", n in rep, "| 규칙", r and r["reason"], "| 원래 순위", r and r["source_rank"], "| 월 다운로드", dl.get(n))

print("\n## 5. 한국 관련 패키지 (이름·설명·keywords 에 한글 또는 korea·kakao·naver·toss·iamport 등)")
pat = re.compile(r"[가-힣]|\bkorea|kakao|naver|\btoss\b|iamport|portone|daum|hangul|hangeul|nicepay|inicis|popbill|kakaopay", re.I)
kr = {n for n in alive if pat.search(" ".join([n, desc[n], kwtext[n]]))}
lost = sorted((kr & old) - rep, key=lambda n: -dl.get(n, 0))
gain = sorted((kr & rep) - old, key=lambda n: -dl.get(n, 0))
print(f"기존 {len(kr & old)} → 후 {len(kr & rep)} (들어옴 {len(gain)} · 빠짐 {len(lost)})")
print("빠짐 상위:", ", ".join(f"{n}({dl.get(n, 0):,})" for n in lost[:15]))
print("들어옴 상위:", ", ".join(f"{n}({dl.get(n, 0):,})" for n in gain[:15]))
