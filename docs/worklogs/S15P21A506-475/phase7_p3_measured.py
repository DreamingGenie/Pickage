"""S15P21A506-475 P3 실측 — 운영 available_package 교체 전·후 목록으로 phase6_p3_impact.py 와 같은 정의를 다시 잰다.

저장소 루트에서 실행한다. 입력(git 밖, 운영 읽기 전용 조회로 받음):
  data/rehearsal475/prod_available_before_P3.txt  (교체 전 97,743)
  data/rehearsal475/prod_available_names.txt      (교체 후 90,833)
  python docs/worklogs/S15P21A506-475/phase7_p3_measured.py > docs/worklogs/S15P21A506-475/evidence/phase6/P3-3-measured.txt
"""
import collections
import csv
import re

import pyarrow.parquet as pq

T = "datasets/targets/"
rd = lambda p: {l.strip() for l in open(p, encoding="utf-8") if l.strip()}
before = rd("data/rehearsal475/prod_available_before_P3.txt")
after = rd("data/rehearsal475/prod_available_names.txt")
pool = {r["name"] for r in csv.DictReader(open(T + "candidate_pool_260916.csv", encoding="utf-8"))}

t = pq.read_table("data/keywords/package_text/package_text_2026-09-08.parquet",
                  columns=["name", "keywords", "description", "status", "is_spam", "downloads_last_month"]).to_pydict()
kw = collections.defaultdict(set)
dl, desc, kwtext, alive = {}, {}, {}, set()
for n, k, d, s, sp, m in zip(t["name"], t["keywords"], t["description"], t["status"], t["is_spam"], t["downloads_last_month"]):
    if s in ("removed", "unpublished") or sp:
        continue
    alive.add(n); dl[n] = m or 0; desc[n] = d or ""; kwtext[n] = " ".join(k or [])
    for x in {x.lower() for x in (k or [])}:
        kw[x].add(n)

kept, added, dropped = before & after, after - before, before - after
print("## 1. 범위 변화 (운영 실측)")
print(f"교체 전 {len(before):,} → 후 {len(after):,} ({len(after) - len(before):+,}, {100 * (len(after) - len(before)) / len(before):+.1f}%)")
print(f"유지 {len(kept):,} · 추가 {len(added):,} · 제외 {len(dropped):,}")
print(f"제외 중 package_text(09-08) 월 100만 이상 {sum(dl.get(n, 0) >= 1_000_000 for n in dropped)} · 스코프 {sum(n.startswith('@') for n in dropped):,} · @types {sum(n.startswith('@types/') for n in dropped):,}")
print(f"AI 후보 풀 포함 {len(pool & before):,} ({100 * len(pool & before) / len(pool):.1f}%) → {len(pool & after):,} ({100 * len(pool & after) / len(pool):.1f}%) / {len(pool):,}")

print("\n## 2. 분야 커버리지 (keywords, 3개 이상 범위에 있는 분야 비율)")
for lo, hi, lab in [(20, 49, "좁은 분야"), (50, 199, "중간 분야")]:
    ks = [k for k, v in kw.items() if lo <= len(v) <= hi]
    row = [f"{nm} {100 * sum(len(kw[k] & S) >= 3 for k in ks) / len(ks):.1f}% ({sum(len(kw[k] & S) >= 3 for k in ks):,})" for nm, S in [("전", before), ("후", after)]]
    print(f"{lab}({lo}~{hi}개, {len(ks):,}개 분야): " + " · ".join(row))

print("\n## 3. 분야 예시 (전 → 후)")
for w in ["ai-agent", "smarthome", "computer-vision", "raspberry", "arduino"]:
    v = kw.get(w, set())
    print(f"{w}: {len(v & before)} → {len(v & after)}")

print("\n## 4. 사례 패키지")
for n in ["dify-client", "opencv4nodejs", "zigbee2mqtt"]:
    print(n, "전", n in before, "| 후", n in after)

print("\n## 5. 한국 관련 패키지")
pat = re.compile(r"[가-힣]|\bkorea|kakao|naver|\btoss\b|iamport|portone|daum|hangul|hangeul|nicepay|inicis|popbill|kakaopay", re.I)
kr = {n for n in alive if pat.search(" ".join([n, desc[n], kwtext[n]]))}
print(f"전 {len(kr & before)} → 후 {len(kr & after)} (들어옴 {len((kr & after) - before)} · 빠짐 {len((kr & before) - after)})")
