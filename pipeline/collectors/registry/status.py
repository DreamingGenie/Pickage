"""registry 수집 진행 상태 한 화면. 수집기에 손대지 않고 체크포인트만 읽는다.

  python status.py --run 2026-09-09                              # 1회 출력
  python status.py --run 2026-09-16 --shards 4                   # 분할 수집: 샤드 합산 + 샤드별
  python status.py --run 2026-09-16 --shards 4 --watch           # 60초마다 갱신 (Ctrl+C로 종료)
  python status.py --run 2026-09-16 --shards 4 --refresh-parquet # 출력 후 to_parquet.py도 실행해 DuckDB UI 뷰를 최신화
  python status.py --run a b c                                   # 샤드 이름이 규칙과 다르면 직접 나열해도 된다

샤드를 여럿 주면 전체 진행률과 끝나는 시각을 같이 낸다. 남은 시간은 샤드들의 합이 아니라
가장 늦는 샤드의 시간이다 — 넷이 동시에 돌기 때문이다.
"""
import argparse
import os
import re
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


def cmdlines():
    """registry/collect.py 를 실행 중인 python 프로세스의 명령줄 목록. 알 수 없으면 None.
    (Windows: tasklist 가 명령줄을 안 보여줘 PowerShell 을 쓴다. 샤드마다 부르면 그만큼 느려져 한 번에 받아 나눠 쓴다.)"""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
             "Where-Object { $_.CommandLine -like '*registry*collect.py*' } | "
             "Select-Object -ExpandProperty CommandLine"],
            capture_output=True, text=True, timeout=20,
        )
        return [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
    except Exception:
        return None


def alive():
    """실행 중인 수집기 수. 알 수 없으면 -1. (to_parquet.py 가 마지막 part 를 건드릴지 판단하는 데 쓴다)
    인자로 목록을 받지 않는다 — None 이 '모름'인지 '안 넘겼음'인지 구분되지 않아 0 과 -1 을 섞기 쉽다."""
    lines = cmdlines()
    return -1 if lines is None else len(lines)


def alive_for(run, lines):
    """이 run 을 돌리고 있는 프로세스 수. `--run 2026-09-16-s1` 이 `-s10` 에 걸리지 않게 경계를 본다."""
    if lines is None:
        return -1
    pat = re.compile(r"--run\s+" + re.escape(run) + r"(\s|$)")
    return sum(1 for ln in lines if pat.search(ln))


def read_run(run, out, lines):
    """체크포인트 한 개를 읽어 숫자로 돌려준다. 아직 없으면 total=0 인 딕셔너리."""
    rundir = os.path.join(out, f"run={run}")
    st = {"run": run, "rundir": rundir, "total": 0, "procs": alive_for(run, lines)}
    try:
        db = sqlite3.connect(f"file:{os.path.join(rundir, 'checkpoint.sqlite')}?mode=ro", uri=True)
        st["total"] = db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    except sqlite3.OperationalError:   # 파일 없음 / 테이블 아직 없음 — 첫 실행 초기화 중이거나 아직 안 떴다
        return st
    if st["total"] == 0:               # 첫 실행에서 대상 INSERT 가 commit 되기 전(약 0.3초)에도 여기로 온다
        db.close()
        return st
    by = dict(db.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status").fetchall())
    st["by"] = by
    st["done"] = by.get("done", 0)
    st["pend"] = by.get("pending", 0)
    st["finished"] = st["total"] - st["pend"]
    st["agg"] = db.execute(
        "SELECT COALESCE(SUM(bytes),0), COALESCE(AVG(bytes),0), COALESCE(MAX(bytes),0), COALESCE(SUM(n_versions),0) "
        "FROM tasks WHERE status='done'"
    ).fetchone()
    big = db.execute("SELECT name FROM tasks WHERE status='done' ORDER BY bytes DESC LIMIT 1").fetchone()
    st["big"] = big[0] if big else "-"
    st["last_ts"] = db.execute("SELECT MAX(ts) FROM events").fetchone()[0]
    st["r10"] = db.execute("SELECT COUNT(*), COALESCE(SUM(http=429),0) FROM events "
                           "WHERE ts >= strftime('%Y-%m-%dT%H:%M:%S','now','-10 minutes')").fetchone()
    st["r60"] = db.execute("SELECT COUNT(*), COALESCE(SUM(http=429),0), COUNT(DISTINCT name) FROM events "
                           "WHERE ts >= strftime('%Y-%m-%dT%H:%M:%S','now','-60 minutes')").fetchone()
    first_in_window = db.execute(
        "SELECT MIN(ts) FROM events WHERE ts >= strftime('%Y-%m-%dT%H:%M:%S','now','-60 minutes')").fetchone()[0]
    st["rank"] = db.execute("SELECT MAX(rank) FROM tasks WHERE status != 'pending'").fetchone()[0] or 0
    db.close()

    st["age"] = None
    if st["last_ts"]:
        t = datetime.fromisoformat(st["last_ts"])
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        st["age"] = (datetime.now(timezone.utc) - t).total_seconds()
    # 시간당 처리량: 최근 1시간 창. 가동(또는 재시작) 1시간 미만이면 창 안의 첫 호출부터 지금까지로 나눠 과대 ETA 를 막는다
    window_h = 1.0
    if first_in_window:
        t0 = datetime.fromisoformat(first_in_window)
        if t0.tzinfo is None:
            t0 = t0.replace(tzinfo=timezone.utc)
        window_h = max(1 / 60, min(1.0, (datetime.now(timezone.utc) - t0).total_seconds() / 3600))
    st["pkgs_per_h"] = round(st["r60"][2] / window_h)
    if not st["pend"]:
        st["eta_h"] = 0.0
    else:
        st["eta_h"] = st["pend"] / st["pkgs_per_h"] if st["pkgs_per_h"] else None
    st["size_mb"] = sum(os.path.getsize(os.path.join(rundir, f))
                        for f in os.listdir(rundir) if f.startswith("part-")) / 1e6
    return st


def state_of(st):
    procs, age = st["procs"], st.get("age")
    if procs > 0 and age is not None and age < 120:
        return "RUNNING"
    if procs > 0 and age is None:
        return "STARTING (프로세스는 있음, 아직 첫 호출 전 — 대상을 체크포인트에 넣는 중)"
    if procs > 0:
        return f"STALLED? (마지막 호출 {age / 60:.0f}분 전, 프로세스는 있음)"
    if not st.get("pend", 1):
        return "DONE"
    return "NOT RUNNING (프로세스 없음 — 같은 명령으로 재시작하면 이어감)"


def render(st, prefix=""):
    """샤드 하나를 사람이 읽는 형태로."""
    if st["total"] == 0:
        state = "STARTING (체크포인트 초기화 중)" if st["procs"] > 0 else "NOT RUNNING (체크포인트 없음)"
        print(f"{prefix}run={st['run']}  상태: {state}")
        return
    by, agg = st["by"], st["agg"]
    print(f"{prefix}run={st['run']}  상태: {state_of(st)}")
    print(f"{prefix}  진행   {st['finished']:,}/{st['total']:,} ({st['finished'] / st['total']:.1%})  남은 {st['pend']:,}  "
          f"성공 {st['done']:,} · 미존재 {by.get('not_found', 0):,} · 전체삭제 {by.get('unpublished', 0):,} · "
          f"실패 {by.get('failed', 0):,}  순위 ~{st['rank']:,}")
    print(f"{prefix}  문서   평균 {agg[1] / 1024:,.0f} KB · 최대 {agg[2] / 1024 / 1024:,.1f} MB({st['big']}) · "
          f"누적 {agg[0] / 1e9:,.2f} GB  버전 행 {agg[3]:,}")
    print(f"{prefix}  속도   최근 10분 {st['r10'][0]}건(429 {st['r10'][1]})  최근 1시간 {st['r60'][0]}건(429 {st['r60'][1]}) "
          f"= {st['pkgs_per_h']:,} 패키지/h")
    if st["eta_h"]:
        print(f"{prefix}  예상   남은 {st['eta_h']:.1f}h → "
              f"{datetime.fromtimestamp(time.time() + st['eta_h'] * 3600).strftime('%m-%d %H:%M')}")
    elif not st["pend"]:
        print(f"{prefix}  예상   완료")
    else:
        print(f"{prefix}  예상   알 수 없음 (최근 1시간 처리 0건)")
    print(f"{prefix}  원본   {st['size_mb']:,.0f} MB  마지막 호출 {st['last_ts'] or '-'} UTC")


def hours_to_hm(hours):
    """소수 시간 → (시, 분). 시와 분을 따로 반올림하면 '2시간 60분' 이 나온다(0.9955h → 60분).
    전체 분으로 먼저 반올림한 뒤 나눈다."""
    return divmod(int(round(hours * 60)), 60)


def bar(frac, width=32):
    """진행 막대. 콘솔이 cp949 로 잡히는 경로가 있어 ASCII 만 쓴다."""
    n = int(round(frac * width))
    return "#" * n + "." * (width - n)


def render_total(sts):
    """샤드 합산. 남은 시간은 합이 아니라 가장 늦는 샤드의 시간이다(넷이 동시에 돈다)."""
    live = [s for s in sts if s["total"]]
    if not live:
        print("  합계   아직 체크포인트가 없다 — 수집기가 뜨는 중이거나 --run 이름이 틀렸다")
        return
    total = sum(s["total"] for s in live)
    finished = sum(s["finished"] for s in live)
    pend = sum(s["pend"] for s in live)
    done = sum(s["done"] for s in live)
    failed = sum(s["by"].get("failed", 0) for s in live)
    r429 = sum(s["r60"][1] for s in live)
    rate = sum(s["pkgs_per_h"] for s in live)
    gb = sum(s["agg"][0] for s in live) / 1e9
    vers = sum(s["agg"][3] for s in live)
    mb = sum(s["size_mb"] for s in live)
    etas = [(s["eta_h"], s["run"]) for s in live if s["pend"]]
    frac = finished / total if total else 0

    print(f"  합계   [{bar(frac)}] {frac:6.1%}   {finished:,}/{total:,} 패키지  남은 {pend:,}")
    print(f"         성공 {done:,} · 실패 {failed:,}   버전 행 {vers:,}   원본 {gb:,.2f} GB 전송 / {mb:,.0f} MB 저장")
    print(f"         속도 {rate:,} 패키지/h (샤드 {len(live)}개 합산)   최근 1시간 429 {r429}건")
    if not etas:
        print("         남은 시간 없음 — 전부 완료")
    elif any(e is None for e, _ in etas):
        stuck = [r for e, r in etas if e is None]
        print(f"         남은 시간 알 수 없음 — 최근 1시간 처리 0건인 샤드: {', '.join(stuck)}")
    else:
        worst_h, worst_run = max(etas)
        end = datetime.fromtimestamp(time.time() + worst_h * 3600)
        h, m = hours_to_hm(worst_h)
        print(f"         남은 {h}시간 {m}분 → 완료 예상 {end.strftime('%m-%d %H:%M')}  "
              f"(가장 늦는 샤드 {worst_run}, 현재 속도 유지·PC 절전 없을 때)")


def report(runs, out):
    lines = cmdlines()
    sts = [read_run(r, out, lines) for r in runs]
    now = datetime.now().strftime("%m-%d %H:%M:%S")
    if len(sts) == 1:
        print(f"[{now}] registry ", end="")
        render(sts[0])
    else:
        running = sum(1 for s in sts if s["procs"] > 0)
        print(f"[{now}] registry 분할 수집 — 샤드 {len(sts)}개 중 {running}개 실행 중")
        render_total(sts)
        print()
        for s in sts:
            render(s, prefix="  ")
    # 하나라도 체크포인트가 아직 없으면 '끝났다'고 보지 않는다(수집기가 뜨는 중일 수 있다)
    return all(s["total"] and not s["pend"] for s in sts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, nargs="+", help="run 이름. 분할 수집이면 --shards 와 같이 기준 이름 하나만 준다")
    ap.add_argument("--shards", type=int,
                    help="샤드 수. 주면 --run 하나를 <run>-s1 … <run>-sN 으로 펼친다(start_registry_sharded.cmd 와 같은 규칙)")
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "registry", "raw"))
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--interval", type=int, default=60)
    ap.add_argument("--refresh-parquet", action="store_true", help="to_parquet.py를 실행해 Parquet 갱신")
    ap.add_argument("--parquet-out", default=os.path.join(ROOT, "data", "registry", "parquet"),
                    help="변환 결과를 쓸 폴더. --run 을 바꿔 돌릴 때 여기도 바꾸지 않으면 to_parquet 가 거부한다")
    ap.add_argument("--parquet-force", action="store_true",
                    help="to_parquet 에 --force 를 넘긴다. 이전 run 으로 만든 출력 폴더를 이번 run 결과로 덮어쓸 때만 쓴다 "
                         "(분할 수집은 run 이름이 바뀌므로 --refresh-parquet 만으로는 출처 검사에 막힌다)")
    ap.add_argument("--refresh-min-interval", type=int, default=3600,
                    help="--refresh-parquet 재실행 최소 간격(초). 변환은 2,000만 행 규모에서 수십 분이라 자주 돌리면 수집기와 자원을 다툰다")
    a = ap.parse_args()
    runs = a.run
    if a.shards:
        assert a.shards >= 1, "--shards 는 1 이상"
        assert len(a.run) == 1, "--shards 를 줄 때는 --run 에 기준 이름 하나만 준다"
        runs = [f"{a.run[0]}-s{i + 1}" for i in range(a.shards)]
    last_refresh = 0.0
    while True:
        finished = report(runs, a.out)
        # part 수가 늘었는지로 판단하면 15초에 하나씩 늘어나는 동안 60초 주기마다 매번 참이라 변환이 등을 맞대고 돈다.
        # 시간 하한을 두고, 수집이 끝났으면 하한과 무관하게 마지막 한 번은 돌려 마지막 part 를 결과에 넣는다.
        if a.refresh_parquet and (finished or time.time() - last_refresh >= a.refresh_min_interval):
            rundirs = [os.path.join(a.out, f"run={r}") for r in runs]
            cmd = [sys.executable, os.path.join(HERE, "to_parquet.py"), "--raw", *rundirs, "--out", a.parquet_out]
            if a.parquet_force:
                cmd.append("--force")
            p = subprocess.run(cmd)
            if p.returncode == 0:
                last_refresh = time.time()
            else:   # 실패했으면 시각을 갱신하지 않아 다음 주기에 다시 시도한다
                print(f"  변환   실패(exit {p.returncode}). 다음 주기에 다시 시도한다")
        if not a.watch or finished:
            break
        time.sleep(a.interval)
        print()


if __name__ == "__main__":
    main()
