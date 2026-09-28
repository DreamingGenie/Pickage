"""S15P21A506-475 2단계 — 보고서 가능 목록으로 download_rank 재부착 + 원본 대비 검증 (로컬 전용).

운영에 아무것도 쓰지 않는다. 입력은 운영 v2 와 바이트가 같은 로컬 사본(SHA 로 확인)이고,
산출물은 git 밖 `data/rehearsal475/` 에만 쓴다.

보고서 가능 목록(잠정) = 재정렬 10만(rerank_100k_20260922.csv) ∩ 확장 46.9만(다운로드 시계열).
운영 확정값은 455 적재 뒤 운영 실측으로 다시 만든다 — 이 목록은 리허설용이다.

실행 (저장소 루트):
    python docs/worklogs/S15P21A506-475/phase2_build_and_verify.py
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys

import pyarrow.compute as pc
import pyarrow.parquet as pq

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "ai", "similarity"))
import similarity_batch_pipeline as sp  # noqa: E402  (load_package_text·qualify 정본)

SRC = os.path.join(ROOT, "data/keywords/package_text/package_text_2026-09-08.parquet")
SRC_SHA = "8b9b1f58e666e8dce47b65e0e866895a121037ec28eac5eb31d477535904d860"  # 운영 v2 manifest
RERANK = os.path.join(ROOT, "datasets/targets/rerank_100k_20260922.csv")
RERANK_SHA = "001d63149f6ca5dfe9af5bc0b92d97a02dd97d31d43da9487debf87a59c549fb"  # targets/README §7-5
EXPANDED = os.path.join(ROOT, "datasets/targets/expanded_468k_20260922.csv")
OLD100K = os.path.join(ROOT, "datasets/targets/rank_top100k_20260902.csv")
OUT_DIR = os.path.join(ROOT, "data/rehearsal475")
RANK_LIST = os.path.join(OUT_DIR, "reportable_rerank_20260925.csv")
OUT = os.path.join(OUT_DIR, "package_text_reportable.parquet")
EVIDENCE = os.path.join(ROOT, "docs/worklogs/S15P21A506-475/evidence/phase2")


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_lf(path: str) -> str:
    """CSV 는 Windows 체크아웃(core.autocrlf=true)에서 CRLF 로 풀린다. git 원본(LF)과 대조하려고
    CR 만 지우고 해시한다 — 내용 비교 기준은 그대로다."""
    with open(path, "rb") as f:
        return hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()


def read_names(path: str) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def fail(msg: str) -> None:
    raise SystemExit(f"중단: {msg}")


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(EVIDENCE, exist_ok=True)
    report: dict = {"run_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}

    # 1. 입력 고정
    for path, want, fn in ((SRC, SRC_SHA, sha256), (RERANK, RERANK_SHA, sha256_lf)):
        got = fn(path)
        if got != want:
            fail(f"{path} SHA 불일치 {got} != {want}")
    report["inputs"] = {
        "package_text": {"path": os.path.relpath(SRC, ROOT), "sha256": SRC_SHA},
        "rerank_100k": {"path": os.path.relpath(RERANK, ROOT), "sha256_lf": RERANK_SHA},
        "expanded_468k": {"path": os.path.relpath(EXPANDED, ROOT), "sha256_lf": sha256_lf(EXPANDED)},
    }

    # 2. 보고서 가능 목록(잠정) — 재정렬 순위를 그대로 쓴다(1..100000 안, 빈 번호 있음)
    rerank = read_names(RERANK)
    expanded = {r["name"] for r in read_names(EXPANDED)}
    reportable = [r for r in rerank if r["name"] in expanded]
    if len(rerank) != 100000:
        fail(f"재정렬 행 수 {len(rerank)}")
    with open(RANK_LIST, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["rank", "name", "reason"])
        for r in reportable:
            w.writerow([r["rank"], r["name"], r["reason"]])
    report["reportable_list"] = {
        "path": os.path.relpath(RANK_LIST, ROOT), "rows": len(reportable),
        "excluded_no_downloads": len(rerank) - len(reportable), "sha256": sha256(RANK_LIST),
    }

    # 3. 재부착 — 레포의 도구를 그대로 부른다(원본은 건드리지 않는다)
    if os.path.exists(OUT):
        os.remove(OUT)
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "pipeline/collectors/keywords/backfill_download_rank.py"),
         "--in", SRC, "--out", OUT, "--rank-list", RANK_LIST, "--overwrite-existing-column"],
        capture_output=True, text=True, encoding="utf-8", cwd=os.path.join(ROOT, "pipeline/collectors/keywords"))
    report["backfill"] = {"returncode": proc.returncode, "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip()[-2000:]}
    if proc.returncode != 0:
        fail("backfill_download_rank.py 실패")
    if sha256(SRC) != SRC_SHA:
        fail("원본이 바뀌었다")
    report["output"] = {"path": os.path.relpath(OUT, ROOT), "sha256": sha256(OUT), "bytes": os.path.getsize(OUT)}

    # 4. 원본 대비 검증 — download_rank 외 열은 같아야 한다
    a = pq.read_table(SRC)
    b = pq.read_table(OUT)
    checks = {}
    checks["rows_equal"] = a.num_rows == b.num_rows
    checks["schema_names_equal"] = a.schema.names == b.schema.names
    checks["schema_types_equal"] = [str(t) for t in a.schema.types] == [str(t) for t in b.schema.types]
    a_s = a.sort_by("name")
    b_s = b.sort_by("name")
    other = [c for c in a.schema.names if c != "download_rank"]
    mismatched = [c for c in other if not a_s.column(c).equals(b_s.column(c))]
    checks["other_columns_identical"] = not mismatched
    checks["mismatched_columns"] = mismatched
    nn = b.num_rows - b.column("download_rank").null_count
    names_in_text = set(a.column("name").to_pylist())
    expect_nn = sum(1 for r in reportable if r["name"] in names_in_text)
    checks["download_rank_not_null"] = nn
    checks["download_rank_expected"] = expect_nn
    checks["download_rank_count_ok"] = nn == expect_nn
    rank_by_name = {r["name"]: int(r["rank"]) for r in reportable}
    got = dict(zip(b.column("name").to_pylist(), b.column("download_rank").to_pylist()))
    wrong = [n for n, rk in rank_by_name.items() if n in got and got[n] != rk]
    checks["download_rank_values_ok"] = not wrong
    checks["download_rank_wrong_sample"] = wrong[:10]
    checks["max_download_rank"] = int(pc.max(b.column("download_rank")).as_py())
    report["checks"] = checks
    if not all(checks[k] for k in ("rows_equal", "schema_names_equal", "schema_types_equal",
                                   "other_columns_identical", "download_rank_count_ok",
                                   "download_rank_values_ok")):
        json.dump(report, open(os.path.join(EVIDENCE, "phase2-report.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        fail("검증 실패 — phase2-report.json 참고")

    # 5. 배치의 정본 함수로 코퍼스 규모 확인 (운영 기본값 min_dependents=5, max_rank=100000, 12개월)
    today = dt.date.today()
    cur_rows = sp.load_package_text(SRC, 5, 100000)
    new_rows = sp.load_package_text(OUT, 5, 100000)
    cur_q = sp.qualify(cur_rows, 5, 12)
    new_q = sp.qualify(new_rows, 5, 12)
    cur_names = {r["name"] for r in cur_q}
    new_names = {r["name"] for r in new_q}
    old100k = {r["name"] for r in read_names(OLD100K)}
    report["corpus"] = {
        "qualify_date": today.isoformat(),
        "current_v2": {"loaded": len(cur_rows), "qualified": len(cur_q)},
        "reportable": {"loaded": len(new_rows), "qualified": len(new_q)},
        "qualified_added": len(new_names - cur_names),
        "qualified_removed": len(cur_names - new_names),
        "qualified_removed_sample": sorted(cur_names - new_names)[:30],
        "all_new_inside_reportable": all(n in rank_by_name for n in new_names),
        "current_inside_old100k": all(n in old100k for n in cur_names),
    }
    for probe in ("ws", "websocket", "eiows", "websocket13", "pusher", "socket.io", "js-yaml", "yaml"):
        report["corpus"].setdefault("probes", {})[probe] = {
            "in_current": probe in cur_names, "in_reportable": probe in new_names,
            "reportable_rank": rank_by_name.get(probe)}

    with open(os.path.join(EVIDENCE, "phase2-report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
