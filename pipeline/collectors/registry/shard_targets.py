"""대상 CSV 를 N개 샤드로 나눈다 (4분할 수집, S15P21A506-366).

  python shard_targets.py --targets datasets/targets/rank_top100k_20260902.csv --shards 4 --out data/registry/targets

순위로 **돌아가며**(1→s1, 2→s2, 3→s3, 4→s4, 5→s1 …) 나눈다. 앞에서부터 25,000개씩 끊으면
샤드마다 성격이 달라져 같이 끝나지 않는다 — 상위권은 문서가 크고(react 6.8 MB, @types/node 10.9 MB),
하위권은 CDN 캐시가 차가워 지연이 3배다(실측 순위 1~2만 0.18초 · 8~10만 0.60초).
돌아가며 나누면 네 샤드가 같은 순위 분포를 갖는다.

이름이 겹치는 행은 순위가 낮은(=상위) 쪽만 남긴다. 실측: 상위 10만 CSV 에 이름 중복이 4건 있다
(@capgo/capacitor-mqtt 61000·61001 등, ecosyste.ms 순위에서 온 것). 직렬 수집은 체크포인트의
INSERT OR IGNORE 가 알아서 하나로 합쳐 왔지만(작업 99,996건), 나눠서 돌리면 두 샤드가 같은 패키지를
따로 받게 된다 — 요청이 낭비되고 to_parquet 의 상태 표에 같은 이름이 두 행으로 남는다.

샤드 파일은 대상의 모든 열을 그대로 물려받는다(collect.py 가 status 열로 제외를 거른다).
출력은 data/ 아래(gitignore)로 쓴다 — 원본 CSV 에서 언제든 다시 만들 수 있는 파생물이라 추적하지 않는다.
"""
import argparse
import csv
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def shard(targets, shards, out):
    with open(targets, encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        fields = r.fieldnames
        assert fields and "name" in fields and "rank" in fields, f"name·rank 열이 필요하다: {fields}"
        rows = sorted(r, key=lambda x: int(x["rank"]))
    assert rows, "대상이 비어 있다: " + targets
    seen, uniq = set(), []
    for row in rows:                 # rank 오름차순이라 먼저 만난 쪽이 상위 순위다(체크포인트의 선택과 같다)
        if row["name"] in seen:
            continue
        seen.add(row["name"])
        uniq.append(row)
    dropped, rows = len(rows) - len(uniq), uniq
    os.makedirs(out, exist_ok=True)
    base = os.path.splitext(os.path.basename(targets))[0]
    paths = []
    for i in range(shards):
        p = os.path.join(out, f"{base}-s{i + 1}of{shards}.csv")
        part = rows[i::shards]           # 돌아가며 나누기
        with open(p, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(part)
        paths.append((p, part))
    return paths, dropped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", required=True)
    ap.add_argument("--shards", type=int, default=4)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    assert a.shards >= 1, "--shards 는 1 이상"
    paths, dropped = shard(a.targets, a.shards, a.out)
    total = sum(len(p) for _, p in paths)
    print(f"[shard_targets] {a.targets} → {a.shards}개 샤드, 합계 {total:,}건"
          + (f" (이름 중복 {dropped}건은 상위 순위만 남김)" if dropped else ""))
    for p, part in paths:
        ranks = [int(x["rank"]) for x in part]
        print(f"  {os.path.basename(p):<50} {len(part):>7,}건  순위 {min(ranks):,}~{max(ranks):,}")


if __name__ == "__main__":
    main()
