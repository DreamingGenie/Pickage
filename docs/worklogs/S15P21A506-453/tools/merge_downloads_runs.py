r"""U5: 두 downloads run 을 Bronze 입고 계약(pipeline.downloads.load)에 맞는 source-root 로 합친다.
  root = data/downloads/bronze_468k/
    expanded_468k_20260922.csv                   대상 CSV (name 열)  ← 정본
    raw/run=2026-09-22-merged-468k/part-NNNNN.jsonl.gz   두 run 의 part 를 하드링크(연번 재부여; 검증기 정규식 ^part-\d+\.jsonl\.gz$)
    raw/run=2026-09-22-merged-468k/run.json, manifest.json   합본임을 밝힌 메타(final=true, 상태 합산, merged_from)
    parquet/                                     to_parquet.py --out (이 스크립트가 만들지 않음)
root 아래에는 검증기가 아는 파일만 있어야 한다(알 수 없는 파일 거부). 다시 돌리면 raw 폴더를 비우고 새로 링크한다.
"""
import os, sys, glob, sqlite3, json, shutil
from datetime import datetime, timezone
RAW = r"C:\git\S15P21A506\data\downloads\raw"
A, B = os.path.join(RAW, "run=2026-09-02"), os.path.join(RAW, "run=2026-09-22-additions")
ROOT = r"C:\git\S15P21A506\data\downloads\bronze_468k"
RUN = "2026-09-22-merged-468k"
M = os.path.join(ROOT, "raw", f"run={RUN}")
TARGET_SRC = r"C:\git\S15P21A506-453\datasets\targets\expanded_468k_20260922.csv"

def status(run):
    return dict(sqlite3.connect(os.path.join(run, "checkpoint.sqlite")).execute(
        "select status,count(*) from tasks group by status").fetchall())
def manifest(run):
    return json.load(open(os.path.join(run, "manifest.json"), encoding="utf-8"))

sa, sb = status(A), status(B)
if sb.get("pending", 0) or sb.get("retry", 0):
    print("B still pending:", sb); sys.exit(2)
ma, mb = manifest(A), manifest(B)
if not (ma.get("final") and mb.get("final")):
    print("manifest not final: A", ma.get("final"), "B", mb.get("final")); sys.exit(3)

shutil.rmtree(M, ignore_errors=True); os.makedirs(M)
n = 0
for run in (A, B):
    for src in sorted(glob.glob(os.path.join(run, "part-*.jsonl.gz"))):
        os.link(src, os.path.join(M, f"part-{n:05d}.jsonl.gz")); n += 1
tgt = os.path.join(ROOT, "expanded_468k_20260922.csv")
if not os.path.exists(tgt): shutil.copyfile(TARGET_SRC, tgt)
json.dump({"run": RUN, "mode": "backfill", "end": "2026-08-31", "targets": "expanded_468k_20260922.csv",
           "merged_from": ["2026-09-02", "2026-09-22-additions"]},
          open(os.path.join(M, "run.json"), "w", encoding="utf-8"))
tb = {k: sa.get(k, 0) + sb.get(k, 0) for k in set(sa) | set(sb)}
json.dump({"run": RUN, "mode": "backfill", "end_date": "2026-08-31", "targets": "expanded_468k_20260922.csv",
           "final": True, "merged_from": [{"run": ma["run"], "tasks_by_status": sa, "parts": len(glob.glob(os.path.join(A, "part-*.jsonl.gz")))},
                                          {"run": mb["run"], "tasks_by_status": sb, "parts": len(glob.glob(os.path.join(B, "part-*.jsonl.gz")))}],
           "tasks_total": sum(tb.values()), "tasks_by_status": tb,
           "packages_done": ma["packages_done"] + mb["packages_done"],
           "packages_not_found": ma["packages_not_found"] + mb["packages_not_found"],
           "failed_tasks": ma["failed_tasks"] + mb["failed_tasks"],
           "merged_at": datetime.now(timezone.utc).isoformat(),
           "note": "하드링크로 합친 두 run. 원본 part 바이트 불변, 연번만 재부여. S15P21A506-453 입력(U5, 컨트롤 타워)."},
          open(os.path.join(M, "manifest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"linked {n} parts -> {M}"); print("tasks_by_status", tb)
print("next: to_parquet.py --raw", M, "--out", os.path.join(ROOT, "parquet"))
