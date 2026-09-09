"""registry 수집 진행 상태 한 화면. 수집기에 손대지 않고 체크포인트만 읽는다.

  python status.py --run 2026-09-09            # 1회 출력
  python status.py --run 2026-09-09 --watch    # 60초마다 갱신 (Ctrl+C로 종료)
  python status.py --run 2026-09-09 --refresh-parquet   # 출력 후 to_parquet.py도 실행해 DuckDB UI 뷰를 최신화
"""
import argparse
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔(cp949) 리다이렉트 시 한글 깨짐 방지
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))


def alive():
    """registry/collect.py를 실행 중인 python 프로세스가 있는가 (Windows: tasklist가 명령줄을 안 보여줘 PowerShell 사용)."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
             "Where-Object { $_.CommandLine -like '*registry*collect.py*' } | Measure-Object).Count"],
            capture_output=True, text=True, timeout=20,
        )
        return int(out.stdout.strip() or 0)
    except Exception:
        return -1


def report(run, out):
    rundir = os.path.join(out, f"run={run}")
    db = sqlite3.connect(f"file:{os.path.join(rundir, 'checkpoint.sqlite')}?mode=ro", uri=True)
    total = db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    by = dict(db.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status").fetchall())
    done = by.get("done", 0)
    finished = done + by.get("not_found", 0) + by.get("unpublished", 0) + by.get("failed", 0)
    pend = by.get("pending", 0)
    agg = db.execute(
        "SELECT COALESCE(SUM(bytes),0), COALESCE(AVG(bytes),0), COALESCE(MAX(bytes),0), COALESCE(SUM(n_versions),0) "
        "FROM tasks WHERE status='done'"
    ).fetchone()
    big = db.execute("SELECT name FROM tasks WHERE status='done' ORDER BY bytes DESC LIMIT 1").fetchone()
    last_ts = db.execute("SELECT MAX(ts) FROM events").fetchone()[0]
    r10 = db.execute("SELECT COUNT(*), COALESCE(SUM(http=429),0) FROM events "
                     "WHERE ts >= strftime('%Y-%m-%dT%H:%M:%S','now','-10 minutes')").fetchone()
    r60 = db.execute("SELECT COUNT(*), COALESCE(SUM(http=429),0), COUNT(DISTINCT name) FROM events "
                     "WHERE ts >= strftime('%Y-%m-%dT%H:%M:%S','now','-60 minutes')").fetchone()
    rank = db.execute("SELECT MAX(rank) FROM tasks WHERE status != 'pending'").fetchone()[0]
    db.close()

    age = None
    if last_ts:
        t = datetime.fromisoformat(last_ts)
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - t).total_seconds()
    procs = alive()
    pkgs_per_h = r60[2]
    eta_h = pend / pkgs_per_h if pkgs_per_h else None
    size = sum(os.path.getsize(os.path.join(rundir, f)) for f in os.listdir(rundir) if f.startswith("part-")) / 1e6

    if procs > 0 and age is not None and age < 120:
        state = "RUNNING"
    elif procs > 0 and age is None:
        state = "STARTING (프로세스는 있음, 아직 첫 호출 전 — 대상 10만 건을 체크포인트에 넣는 중)"
    elif procs > 0:
        state = f"STALLED? (마지막 호출 {age/60:.0f}분 전, 프로세스는 있음)"
    else:
        state = "NOT RUNNING (프로세스 없음 — 같은 명령으로 재시작하면 이어감)"

    now = datetime.now().strftime("%m-%d %H:%M:%S")
    print(f"[{now}] registry run={run}  상태: {state}")
    print(f"  진행   {finished:,}/{total:,} 패키지 ({finished/total:.1%})  남은 {pend:,}  "
          f"성공 {done:,} · 미존재 {by.get('not_found', 0):,} · 전체삭제 {by.get('unpublished', 0):,} · 실패 {by.get('failed', 0):,}  "
          f"순위 ~{rank or 0:,}까지")
    print(f"  문서   평균 {agg[1]/1024:,.0f} KB · 최대 {agg[2]/1024/1024:,.1f} MB({big[0] if big else '-'}) · 누적 {agg[0]/1e9:,.2f} GB  "
          f"버전 행 {agg[3]:,}")
    print(f"  속도   최근 10분 {r10[0]}건(429 {r10[1]})  최근 1시간 {r60[0]}건(429 {r60[1]}) = {pkgs_per_h:,} 패키지/h")
    if eta_h is not None and pend:
        eta = datetime.now().timestamp() + eta_h * 3600
        print(f"  예상   남은 {eta_h:.1f}h → {datetime.fromtimestamp(eta).strftime('%m-%d %H:%M')} (현재 속도 유지·PC 절전 없을 때)")
    elif not pend:
        print("  예상   완료")
    print(f"  원본   {size:,.0f} MB  마지막 호출 {last_ts or '-'} UTC")
    return pend == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "registry", "raw"))
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--interval", type=int, default=60)
    ap.add_argument("--refresh-parquet", action="store_true", help="to_parquet.py를 실행해 data/registry/parquet 갱신")
    a = ap.parse_args()
    while True:
        finished = report(a.run, a.out)
        if a.refresh_parquet:
            subprocess.run([sys.executable, os.path.join(HERE, "to_parquet.py"), "--raw", os.path.join(a.out, f"run={a.run}"),
                            "--out", os.path.join(ROOT, "data", "registry", "parquet")], check=False)
        if not a.watch or finished:
            break
        time.sleep(a.interval)
        print()


if __name__ == "__main__":
    main()
