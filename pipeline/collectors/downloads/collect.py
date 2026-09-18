"""npm downloads collector — 수집계획_downloads_npmAPI_260902.md §3 구현.

단일 프로세스 · 초당 1건 토큰버킷 · 429 지수 백오프 · SQLite 체크포인트(재시작 시 이어감)
· 응답 start/end 검증 · 원본 응답을 jsonl.gz로 보존 · manifest.json 기록.

사용:
  python collect.py --targets rank_top100k.csv --run 2026-09-02 --mode backfill --out data/downloads/raw
  python collect.py --targets rank_top100k.csv --run 2026-09-09 --mode weekly   --out data/downloads/raw
옵션: --end YYYY-MM-DD(기본 UTC 오늘-2) --rate 1.0 --limit N(작업 수 상한, 테스트용) --exclude-status removed,unpublished
"""
import argparse
import csv
import gzip
import json
import os
import socket
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

import requests

try:
    # start_backfill.cmd 는 stdout 을 로그 파일로 넘긴다. 콘솔이 아니면 인코딩이 로캘(cp949)로 정해져
    # cp949 에 없는 글자 하나에 UnicodeEncodeError 로 수집기가 죽는다. chcp 65001 은 콘솔 코드페이지만 바꾼다.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

API = "https://api.npmjs.org/downloads/range"
# npm은 대량 호출 시 UA에 연락 가능한 주소를 요구한다. 개인 주소는 저장소에 올리지 않으므로 비워 두고,
# 실행자가 환경변수 OSS_SHIFT_UA_CONTACT 로 넘기거나 여기 직접 채운다. 비어 있으면 실행을 거부한다.
UA_CONTACT = os.environ.get("OSS_SHIFT_UA_CONTACT", "")
UA = f"oss-shift-a506 collector (SSAFY student project; {UA_CONTACT})"
BULK_MAX = 128
URL_MAX = 7000


def iso(d):
    return d.strftime("%Y-%m-%d")


def enc(name):
    return quote(name, safe="@").replace("/", "%2F")


def build_tasks(rows, mode, end, exclude_status):
    """rows: [(rank, name, status)] 순위 오름차순. 벌크 먼저, 스코프는 순위 순."""
    rows = [r for r in rows if not (r[2] and r[2] in exclude_status)]
    if mode == "backfill":
        bulk_windows = [(end - timedelta(days=364), end), (end - timedelta(days=729), end - timedelta(days=365))]
        single_windows = [(end - timedelta(days=548), end)]  # 549일 ≤ 18개월 (실측 OK)
    else:
        w = [(end - timedelta(days=13), end)]  # 직전 14일
        bulk_windows = single_windows = w
    unscoped = [r for r in rows if not r[1].startswith("@")]
    scoped = [r for r in rows if r[1].startswith("@")]
    tasks = []
    for ws, we in bulk_windows:
        chunk = []
        for r in unscoped:
            if len(chunk) == BULK_MAX or (chunk and len(",".join(enc(x[1]) for x in chunk + [r])) > URL_MAX):
                tasks.append(("bulk", chunk, ws, we))
                chunk = []
            chunk.append(r)
        if chunk:
            tasks.append(("bulk", chunk, ws, we))
    for ws, we in single_windows:
        for r in scoped:
            tasks.append(("single", [r], ws, we))
    out = []
    for kind, chunk, ws, we in tasks:
        tid = f"{kind}-{chunk[0][0]:06d}-{iso(ws)}"
        out.append((tid, kind, chunk[0][0], json.dumps([[r[0], r[1]] for r in chunk]), iso(ws), iso(we)))
    return out


class Writer:
    def __init__(self, outdir, rotate=5000):
        self.outdir, self.rotate, self.n, self.fh = outdir, rotate, 0, None
        existing = [f for f in os.listdir(outdir) if f.startswith("part-") and f.endswith(".jsonl.gz")]
        self.part = max([int(f[5:10]) for f in existing], default=-1)
        self._open()

    def _open(self):
        if self.fh:
            self.fh.close()
        self.part += 1
        self.n = 0
        self.fh = gzip.open(os.path.join(self.outdir, f"part-{self.part:05d}.jsonl.gz"), "at", encoding="utf-8")

    def write(self, obj):
        self.fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self.n += 1
        if self.n >= self.rotate:
            self._open()

    def flush(self):
        """체크포인트 commit 직전에 호출. gzip 버퍼를 디스크에 내려 강제 종료 시 '체크포인트는 done 인데 행은 없는' 작업이 생기지 않게 한다."""
        if self.fh:
            self.fh.flush()

    def close(self):
        if self.fh:
            self.fh.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", required=True)
    ap.add_argument("--run", required=True)
    ap.add_argument("--mode", choices=["backfill", "weekly"], required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--end")
    ap.add_argument("--rate", type=float, default=1.0)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--exclude-status", default="")
    ap.add_argument("--tier", default="A")
    a = ap.parse_args()
    if not UA_CONTACT:
        raise SystemExit("[collect] User-Agent 연락처가 비어 있다. 환경변수 OSS_SHIFT_UA_CONTACT=<이메일 또는 URL> 을 설정할 것")

    rundir = os.path.join(a.out, f"run={a.run}")
    os.makedirs(rundir, exist_ok=True)
    # 구간 끝(end)은 run마다 고정한다. 재시작 시 날짜가 바뀌면 작업 id가 전부 달라져 처음부터 다시 받게 되므로
    # 첫 실행 때 run.json에 기록하고 이후엔 그 값을 쓴다. --end를 다르게 주면 거부한다.
    run_meta = os.path.join(rundir, "run.json")
    if os.path.exists(run_meta):
        with open(run_meta, encoding="utf-8") as f:
            saved = json.load(f)
        if a.end and a.end != saved["end"]:
            raise SystemExit(f"[collect] run={a.run} 은 end={saved['end']} 로 시작됐다. --end {a.end} 는 새 run 이름으로 실행할 것")
        end = date.fromisoformat(saved["end"])
    else:
        end = date.fromisoformat(a.end) if a.end else datetime.now(timezone.utc).date() - timedelta(days=2)
        with open(run_meta, "w", encoding="utf-8") as f:
            json.dump({"run": a.run, "mode": a.mode, "end": iso(end), "targets": os.path.basename(a.targets)}, f)
    rows = []
    with open(a.targets, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append((int(r["rank"]), r["name"], r.get("status") or ""))
    rows.sort()
    tasks = build_tasks(rows, a.mode, end, set(filter(None, a.exclude_status.split(","))))

    db = sqlite3.connect(os.path.join(rundir, "checkpoint.sqlite"))
    db.execute(
        """CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, kind TEXT, rank_min INT, names TEXT,
           ws TEXT, we TEXT, status TEXT DEFAULT 'pending', http INT, attempts INT DEFAULT 0,
           fetched_at TEXT, error TEXT, n_pkg INT, n_not_found INT)"""
    )
    db.execute("CREATE TABLE IF NOT EXISTS events(ts TEXT, http INT, task_id TEXT)")
    db.executemany("INSERT OR IGNORE INTO tasks(id,kind,rank_min,names,ws,we) VALUES(?,?,?,?,?,?)", tasks)
    db.commit()

    pending = db.execute(
        "SELECT id,kind,names,ws,we,attempts FROM tasks WHERE status IN ('pending','retry') ORDER BY rowid"
    ).fetchall()
    if a.limit:
        pending = pending[: a.limit]
    total = db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    n_bulk = sum(1 for t in tasks if t[1] == "bulk")
    print(
        f"[collect] run={a.run} mode={a.mode} end={end} tasks total={total} pending={len(pending)} "
        f"bulk={n_bulk} single={len(tasks) - n_bulk}",
        flush=True,
    )

    S = requests.Session()
    S.headers["User-Agent"] = UA
    W = Writer(rundir)
    stats = {"ok": 0, "not_found": 0, "failed": 0, "http429": 0, "http5xx": 0, "conn_err": 0}
    started = time.time()
    last_start = 0.0
    consec429 = 0
    interval = 1.0 / a.rate          # 적응형: 429가 나오면 15% 늘리고(최대 3 s), 200이 이어지면 천천히 되돌린다
    interval_min, interval_max = 1.0 / a.rate, 3.0
    recent = []                      # 최근 100 작업의 완료 시각 → 실제 처리율로 ETA 계산
    manifest_path = os.path.join(rundir, "manifest.json")

    def manifest(final=False):
        c = dict(db.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status").fetchall())
        nf = db.execute(
            "SELECT COALESCE(SUM(n_not_found),0), COALESCE(SUM(n_pkg),0) FROM tasks WHERE status='done'"
        ).fetchone()
        m = {
            "run": a.run, "mode": a.mode, "tier": a.tier, "end_date": iso(end), "targets": a.targets,
            "host": socket.gethostname(),
            "started_at": datetime.fromtimestamp(started, timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(), "final": final,
            "elapsed_s": round(time.time() - started), "tasks_total": total, "tasks_by_status": c,
            "packages_done": nf[1], "packages_not_found": nf[0], "session_stats": stats,
            "rate_target_per_s": a.rate,
            "failed_tasks": [r[0] for r in db.execute("SELECT id FROM tasks WHERE status='failed'").fetchall()][:500],
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False, indent=1)

    def rec(n, rank, kind, ws, we, now, tid, status, downloads):
        W.write({"name": n, "rank": rank, "kind": kind, "start": ws, "end": we, "tier": a.tier,
                 "fetched_at": now, "task_id": tid, "status": status, "downloads": downloads})

    try:
        for i, (tid, kind, names_j, ws, we, attempts) in enumerate(pending):
            names = json.loads(names_j)
            url = f"{API}/{ws}:{we}/{','.join(enc(n) for _, n in names)}"
            while True:
                wait = last_start + interval - time.time()
                if wait > 0:
                    time.sleep(wait)
                last_start = time.time()
                try:
                    r = S.get(url, timeout=60)
                except requests.RequestException as e:
                    stats["conn_err"] += 1
                    attempts += 1
                    if attempts >= 4:
                        db.execute("UPDATE tasks SET status='failed',attempts=?,error=? WHERE id=?",
                                   (attempts, f"conn:{e}"[:200], tid))
                        break
                    time.sleep(10)
                    continue
                now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                db.execute("INSERT INTO events VALUES(?,?,?)", (now, r.status_code, tid))
                if r.status_code == 429:
                    stats["http429"] += 1
                    consec429 += 1
                    interval = min(interval * 1.15, interval_max)
                    time.sleep(300 if consec429 >= 5 else min(2 ** consec429, 60))
                    continue
                consec429 = 0
                interval = max(interval_min, interval * 0.998)
                if r.status_code == 404 and kind == "single":
                    rec(names[0][1], names[0][0], kind, ws, we, now, tid, "not_found", None)
                    db.execute("UPDATE tasks SET status='not_found',http=404,fetched_at=?,n_pkg=1,n_not_found=1 WHERE id=?",
                               (now, tid))
                    stats["not_found"] += 1
                    break
                if r.status_code >= 500:
                    stats["http5xx"] += 1
                    attempts += 1
                    if attempts >= 4:
                        db.execute("UPDATE tasks SET status='failed',http=?,attempts=?,error=? WHERE id=?",
                                   (r.status_code, attempts, r.text[:200], tid))
                        break
                    time.sleep(10)
                    continue
                if r.status_code != 200:
                    db.execute("UPDATE tasks SET status='failed',http=?,error=? WHERE id=?",
                               (r.status_code, r.text[:200], tid))
                    stats["failed"] += 1
                    break
                j = r.json()
                # 요청이 1개면(단일 또는 벌크 1개) 단일 형태 {package,start,end,downloads}로 옴.
                # 2개 이상이면 항상 이름→객체 dict. 이름이 "package"인 패키지가 실제로 있어 키 존재로 판별하면 안 됨.
                objs = {names[0][1]: j} if len(names) == 1 else j
                n_nf = 0
                bad = None
                for rank, n in names:
                    o = objs.get(n)
                    if o is None:
                        n_nf += 1
                        rec(n, rank, kind, ws, we, now, tid, "not_found", None)
                        continue
                    if o.get("start") != ws or o.get("end") != we or not isinstance(o.get("downloads"), list):
                        bad = f"window_mismatch {n}: {o.get('start')}..{o.get('end')}"
                        break
                    rec(n, rank, kind, ws, we, now, tid, "ok", o["downloads"])
                if bad:
                    db.execute("UPDATE tasks SET status='failed',http=200,error=? WHERE id=?", (bad, tid))
                    stats["failed"] += 1
                else:
                    db.execute("UPDATE tasks SET status='done',http=200,fetched_at=?,n_pkg=?,n_not_found=? WHERE id=?",
                               (now, len(names), n_nf, tid))
                    stats["ok"] += 1
                    stats["not_found"] += n_nf
                break
            recent.append(time.time())
            if len(recent) > 100:
                recent.pop(0)
            if (i + 1) % 20 == 0:
                W.flush()
                db.commit()
            if (i + 1) % 100 == 0 or i + 1 == len(pending):
                W.flush()
                db.commit()
                el = time.time() - started
                per_task = (recent[-1] - recent[0]) / max(1, len(recent) - 1) if len(recent) > 1 else 0
                eta = per_task * (len(pending) - i - 1)
                print(
                    f"[collect] {i + 1}/{len(pending)} tasks  ok={stats['ok']} nf={stats['not_found']} "
                    f"fail={stats['failed']} 429={stats['http429']}  interval={interval:.2f}s "
                    f"{el / 3600:.2f}h elapsed, eta {eta / 3600:.2f}h (recent {per_task:.2f}s/task)",
                    flush=True,
                )
            if (i + 1) % 500 == 0:
                manifest()
    except KeyboardInterrupt:
        print("[collect] interrupted — checkpoint saved", flush=True)
    finally:
        W.close()      # 행을 먼저 디스크에 내리고(gzip 트레일러 포함) 그 다음 체크포인트를 확정한다
        db.commit()
        manifest(final=True)
        db.close()
        print(f"[collect] wrote manifest {manifest_path}", flush=True)


if __name__ == "__main__":
    main()
