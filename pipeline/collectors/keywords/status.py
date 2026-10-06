"""keywords 수집 진행 상태 한 화면. 수집기에 손대지 않고 part 파일·manifest·로그만 읽는다.

  python status.py --run 2026-09-08            # 1회 출력
  python status.py --run 2026-09-08 --watch    # 60초마다 갱신 (Ctrl+C로 종료)
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔(cp949) 리다이렉트 시 한글 깨짐 방지
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))


def alive():
    """collect_keywords.py를 실행 중인 python 프로세스 수 (Windows: PowerShell로 명령줄 조회)."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
             "Where-Object { $_.CommandLine -like '*collect_keywords.py*' } | Measure-Object).Count"],
            capture_output=True, text=True, timeout=20,
        )
        return int(out.stdout.strip() or 0)
    except Exception:
        return -1


def report(run, out, pages_planned):
    rundir = os.path.join(out, f"run={run}")
    parts = []
    for f in os.listdir(rundir):
        if f.startswith("part-") and f.endswith(".jsonl.gz"):
            st = os.stat(os.path.join(rundir, f))
            parts.append((int(f[5:10]), st.st_mtime, st.st_size))
    parts.sort()
    manifest = {}
    mp = os.path.join(rundir, "manifest.json")
    if os.path.exists(mp):
        with open(mp, encoding="utf-8") as f:
            manifest = json.load(f)
    total = manifest.get("pages_planned") or pages_planned
    per_page = manifest.get("per_page", 1000)
    done = len(parts)
    pend = max(total - done, 0)
    now = time.time()
    last_mtime = parts[-1][1] if parts else None
    age = now - last_mtime if last_mtime else None
    r10 = sum(1 for _, m, _ in parts if m >= now - 600)
    r60 = sum(1 for _, m, _ in parts if m >= now - 3600)
    # 처리율: 최근 1시간에 60개 미만이면 첫 part부터 지금까지의 평균으로 보정(초반 구간)
    if r60 >= 10:
        pages_per_h = r60 if (now - parts[0][1]) >= 3600 else r60 / ((now - parts[0][1]) / 3600)
    elif len(parts) >= 2:
        pages_per_h = (len(parts) - 1) / max((parts[-1][1] - parts[0][1]) / 3600, 1e-6)
    else:
        pages_per_h = 0
    eta_h = pend / pages_per_h if pages_per_h else None
    size = sum(s for _, _, s in parts) / 1e6
    st = manifest.get("session_stats", {})
    rows = st.get("rows", 0)
    kw = st.get("with_keywords", 0)
    tp = st.get("with_topics", 0)
    max_page = parts[-1][0] if parts else 0

    procs = alive()
    if pend == 0:
        state = "DONE"
    elif procs > 0 and age is not None and age < 180:
        state = "RUNNING"
    elif procs > 0:
        state = f"STALLED? (마지막 페이지 저장 {age/60:.0f}분 전, 프로세스는 있음)"
    else:
        state = "NOT RUNNING (프로세스 없음 — start_keywords.cmd 또는 같은 명령으로 재시작하면 이어감)"

    bar_n = 40
    filled = int(bar_n * done / total) if total else 0
    bar = "#" * filled + "-" * (bar_n - filled)
    ts = datetime.now().strftime("%m-%d %H:%M:%S")
    print(f"[{ts}] keywords run={run}  상태: {state}")
    print(f"  진행   [{bar}] {done:,}/{total:,} 페이지 ({done/total:.1%})  순위 ~{max_page*per_page:,}까지  남은 {pend:,}페이지 ≈ {pend*per_page:,}개")
    print(f"  속도   최근 10분 {r10}페이지  최근 1시간 {r60}페이지  = {pages_per_h:,.0f} 페이지/h ({3600/pages_per_h if pages_per_h else 0:.0f} s/페이지)")
    if eta_h is not None and pend:
        eta = datetime.fromtimestamp(now + eta_h * 3600).strftime("%m-%d %H:%M")
        print(f"  예상   남은 {eta_h:.1f}h → {eta} 완료 (현재 속도 유지·PC 절전 없을 때)")
    elif not pend:
        print("  예상   완료")
    if rows:
        print(f"  내용   {rows:,}개 중 keywords {kw:,} ({kw/rows:.1%})  github topics {tp:,} ({tp/rows:.1%})  "
              f"429 {st.get('http429',0)}  연결오류 {st.get('conn_err',0)}  (manifest 기준, 10페이지마다 갱신)")
    print(f"  파일   {size:,.0f} MB / {done} part  마지막 저장 {datetime.fromtimestamp(last_mtime).strftime('%H:%M:%S') if last_mtime else '-'}")
    return pend == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "keywords", "raw"))
    ap.add_argument("--pages", type=int, default=1000, help="manifest가 없을 때의 전체 페이지 수")
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--interval", type=int, default=60)
    a = ap.parse_args()
    while True:
        if a.watch:
            os.system("cls" if os.name == "nt" else "clear")
        finished = report(a.run, a.out, a.pages)
        if not a.watch or finished:
            break
        time.sleep(a.interval)


if __name__ == "__main__":
    main()
