"""npm registry 버전 이력 수집기 — 수집계획_devDependencies_npmRegistry_260909.md §3 구현.

패키지 1개 = 요청 1회(`registry.npmjs.org/<name>`, 전체 문서). 문서에서 버전마다 dependencies · devDependencies ·
peerDependencies · optionalDependencies · 발행 시각 · deprecated 만 남겨 jsonl.gz 로 쓴다(원본 문서는 보존하지 않음).
단일 프로세스 · 요청 간격 토큰버킷 · 429 지수 백오프 · SQLite 체크포인트(재시작 시 이어감) · manifest.json 기록.

사용:
  python collect.py --targets datasets/targets/rank_top100k_20260902.csv --run 2026-09-09 --out data/registry/raw --interval 0.5
옵션: --limit N(작업 수 상한, 스모크용) --retry-failed(failed 도 다시 시도) --max-doc-mb 200(이보다 큰 문서는 failed)
      --exclude-status removed,unpublished(대상 CSV 의 status 열 값으로 제외)

축약 문서(Accept: application/vnd.npm.install-v1+json)는 devDependencies 가 빠지므로 쓰지 않는다. 기본(전체) 문서를 받는다.
"""
import argparse
import csv
import gzip
import json
import os
import socket
import sqlite3
import time
from datetime import datetime, timezone
from urllib.parse import quote

import requests

API = "https://registry.npmjs.org"
# npm은 대량 호출 시 UA에 연락 가능한 주소를 요구한다. 개인 주소는 저장소에 올리지 않으므로 비워 두고,
# 실행자가 환경변수 OSS_SHIFT_UA_CONTACT 로 넘긴다. 비어 있으면 실행을 거부한다(downloads 수집기와 동일).
UA_CONTACT = os.environ.get("OSS_SHIFT_UA_CONTACT", "")
UA = f"oss-shift-a506 collector (SSAFY student project; {UA_CONTACT})"
NON_VERSION_TIME_KEYS = {"created", "modified", "unpublished"}  # time 객체에서 버전이 아닌 키


class TooLarge(Exception):
    pass


def enc(name):
    return quote(name, safe="@").replace("/", "%2F")


def dep_list(d):
    """{"ansi-styles": "^4.1.0"} → deps.dev NPMRequirements 와 같은 [{"Name","Requirement"}] 구조. 삽입 순서 유지."""
    if not isinstance(d, dict):
        return []
    return [{"Name": k, "Requirement": v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)} for k, v in d.items()]


def parse(doc, name, rank, fetched_at):
    """전체 문서 → (버전 행 목록, time.modified). 패키지 전체가 unpublish 된 문서(versions 없음 + time.unpublished)는 None.
    versions 에 없고 time 에만 있는 버전 = unpublish 된 버전: 행은 남기고 의존은 빈 값, unpublished=True."""
    times = doc.get("time") or {}
    versions = doc.get("versions")
    if not isinstance(versions, dict):
        if "unpublished" in times:
            return None
        raise ValueError("no versions")
    modified = times.get("modified")
    vers = list(versions.keys())
    seen = set(vers)
    for k in times:
        if k not in NON_VERSION_TIME_KEYS and k not in seen:
            vers.append(k)
            seen.add(k)
    rows = []
    for v in vers:
        meta = versions.get(v)
        unpublished = meta is None
        if not isinstance(meta, dict):
            meta = {}
        dep = meta.get("deprecated")
        if dep is not None and not isinstance(dep, str):
            dep = json.dumps(dep, ensure_ascii=False)
        rows.append({
            "Name": name, "Version": v, "published_at": times.get(v), "rank": rank,
            "Dependencies": dep_list(meta.get("dependencies")),
            "DevDependencies": dep_list(meta.get("devDependencies")),
            "PeerDependencies": dep_list(meta.get("peerDependencies")),
            "OptionalDependencies": dep_list(meta.get("optionalDependencies")),
            "deprecated": dep, "unpublished": unpublished,
            "fetched_at": fetched_at, "modified": modified,
        })
    rows.sort(key=lambda r: (r["published_at"] or "", r["Version"]))
    return rows, modified


def online(session):
    """registry 가 닿는가. 연결 오류가 '이 패키지 문제'인지 '인터넷 끊김'인지 가르는 데 쓴다."""
    try:
        return session.get(f"{API}/-/ping", timeout=10).status_code < 500
    except requests.RequestException:
        return False


def wait_online(session, poll=30):
    """인터넷이 끊겼으면 복구될 때까지 기다린다. 끊긴 동안 패키지를 failed 로 넘기지 않기 위함(밤새 실행 대비)."""
    print("[collect] offline? registry 에 닿지 않는다 — 30초마다 재확인, 복구되면 이어간다", flush=True)
    t0 = time.time()
    while not online(session):
        time.sleep(poll)
    print(f"[collect] network back after {time.time() - t0:.0f}s", flush=True)


def fetch(session, url, max_bytes):
    """전체 문서를 조각으로 읽어 모은다. 압축 해제 후 크기가 max_bytes 를 넘으면 TooLarge (수십 MB 문서가 있어 상한 필요)."""
    r = session.get(url, timeout=(15, 180), stream=True)
    if r.status_code != 200:
        body = r.content  # 오류 본문은 작다
        return r, body
    buf = bytearray()
    for chunk in r.iter_content(1 << 20):
        buf += chunk
        if len(buf) > max_bytes:
            r.close()
            raise TooLarge(len(buf))
    return r, bytes(buf)


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

    def close(self):
        if self.fh:
            self.fh.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", required=True)
    ap.add_argument("--run", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--interval", type=float, default=0.5,
                    help="요청 간 최소 간격(초). 429 가 나오면 15%%씩 늘어난다(최대 3초)")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--retry-failed", action="store_true")
    ap.add_argument("--max-doc-mb", type=float, default=200.0)
    ap.add_argument("--exclude-status", default="")
    a = ap.parse_args()
    if not UA_CONTACT:
        raise SystemExit("[collect] User-Agent 연락처가 비어 있다. 환경변수 OSS_SHIFT_UA_CONTACT=<이메일 또는 URL> 을 설정할 것")

    rundir = os.path.join(a.out, f"run={a.run}")
    os.makedirs(rundir, exist_ok=True)
    run_meta = os.path.join(rundir, "run.json")
    if not os.path.exists(run_meta):
        with open(run_meta, "w", encoding="utf-8") as f:
            json.dump({"run": a.run, "targets": os.path.basename(a.targets),
                       "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}, f)
    exclude = set(filter(None, a.exclude_status.split(",")))
    rows = []
    with open(a.targets, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("status") and r["status"] in exclude:
                continue
            rows.append((r["name"], int(r["rank"])))
    rows.sort(key=lambda x: x[1])

    db = sqlite3.connect(os.path.join(rundir, "checkpoint.sqlite"))
    db.execute(
        """CREATE TABLE IF NOT EXISTS tasks(name TEXT PRIMARY KEY, rank INT, status TEXT DEFAULT 'pending', http INT,
           attempts INT DEFAULT 0, fetched_at TEXT, bytes INT, n_versions INT, n_unpublished INT, modified TEXT, error TEXT)"""
    )
    db.execute("CREATE TABLE IF NOT EXISTS events(ts TEXT, http INT, name TEXT)")
    db.executemany("INSERT OR IGNORE INTO tasks(name, rank) VALUES(?,?)", rows)
    # 연결 오류(conn:)로 실패한 작업은 인터넷 끊김이 원인일 가능성이 커서 재시작 때마다 자동으로 다시 시도한다.
    # 그 외 failed(too_large·parse·5xx)는 --retry-failed 를 줬을 때만.
    n_conn = db.execute("UPDATE tasks SET status='pending', attempts=0, error=NULL WHERE status='failed' AND error LIKE 'conn:%'").rowcount
    if n_conn:
        print(f"[collect] reset {n_conn} conn-failed tasks to pending", flush=True)
    if a.retry_failed:
        db.execute("UPDATE tasks SET status='pending', attempts=0, error=NULL WHERE status='failed'")
    db.commit()

    pending = db.execute("SELECT name, rank, attempts FROM tasks WHERE status='pending' ORDER BY rank").fetchall()
    if a.limit:
        pending = pending[: a.limit]
    total = db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    print(f"[collect] run={a.run} tasks total={total} pending={len(pending)} interval={a.interval}s", flush=True)

    S = requests.Session()
    S.headers["User-Agent"] = UA
    S.headers["Accept"] = "application/json"  # 전체 문서. 축약형(vnd.npm.install-v1+json)은 devDependencies 가 없다
    W = Writer(rundir)
    stats = {"ok": 0, "not_found": 0, "unpublished": 0, "failed": 0, "http429": 0, "http5xx": 0, "conn_err": 0,
             "too_large": 0, "bytes": 0, "max_bytes": 0, "max_bytes_name": None, "versions": 0}
    started = time.time()
    last_start = 0.0
    consec429 = 0
    interval = a.interval          # 적응형: 429가 나오면 15% 늘리고(최대 3 s), 200이 이어지면 천천히 되돌린다
    interval_min, interval_max = a.interval, 3.0
    recent = []                    # 최근 100 작업의 완료 시각 → 실제 처리율로 ETA 계산
    max_bytes = int(a.max_doc_mb * 1024 * 1024)
    manifest_path = os.path.join(rundir, "manifest.json")

    def manifest(final=False):
        c = dict(db.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status").fetchall())
        agg = db.execute(
            "SELECT COALESCE(SUM(bytes),0), COALESCE(AVG(bytes),0), COALESCE(MAX(bytes),0), COALESCE(SUM(n_versions),0) "
            "FROM tasks WHERE status='done'"
        ).fetchone()
        m = {
            "run": a.run, "targets": a.targets, "host": socket.gethostname(),
            "started_at": datetime.fromtimestamp(started, timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(), "final": final,
            "elapsed_s": round(time.time() - started), "tasks_total": total, "tasks_by_status": c,
            "doc_bytes_total": agg[0], "doc_bytes_avg": round(agg[1]), "doc_bytes_max": agg[2], "versions_total": agg[3],
            "session_stats": stats, "interval_start_s": a.interval, "interval_now_s": round(interval, 3),
            "failed_tasks": [r[0] for r in db.execute("SELECT name FROM tasks WHERE status='failed'").fetchall()][:500],
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False, indent=1)

    try:
        for i, (name, rank, attempts) in enumerate(pending):
            url = f"{API}/{enc(name)}"
            while True:
                wait = last_start + interval - time.time()
                if wait > 0:
                    time.sleep(wait)
                last_start = time.time()
                try:
                    r, body = fetch(S, url, max_bytes)
                except TooLarge as e:
                    stats["too_large"] += 1
                    stats["failed"] += 1
                    db.execute("UPDATE tasks SET status='failed',http=200,error=? WHERE name=?",
                               (f"too_large:>{e.args[0]}B", name))
                    break
                except requests.RequestException as e:
                    stats["conn_err"] += 1
                    if not online(S):          # 인터넷 끊김: 시도 횟수를 소모하지 않고 복구까지 대기 후 같은 패키지 재시도
                        db.commit()
                        wait_online(S)
                        continue
                    attempts += 1
                    if attempts >= 4:
                        db.execute("UPDATE tasks SET status='failed',attempts=?,error=? WHERE name=?",
                                   (attempts, f"conn:{e}"[:200], name))
                        stats["failed"] += 1
                        break
                    time.sleep(10)
                    continue
                now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                db.execute("INSERT INTO events VALUES(?,?,?)", (now, r.status_code, name))
                if r.status_code == 429:
                    stats["http429"] += 1
                    consec429 += 1
                    interval = min(interval * 1.15, interval_max)
                    time.sleep(300 if consec429 >= 5 else min(2 ** consec429, 60))
                    continue
                consec429 = 0
                interval = max(interval_min, interval * 0.998)
                if r.status_code == 404:
                    db.execute("UPDATE tasks SET status='not_found',http=404,fetched_at=? WHERE name=?", (now, name))
                    stats["not_found"] += 1
                    break
                if r.status_code >= 500:
                    stats["http5xx"] += 1
                    attempts += 1
                    if attempts >= 4:
                        db.execute("UPDATE tasks SET status='failed',http=?,attempts=?,error=? WHERE name=?",
                                   (r.status_code, attempts, body[:200].decode("utf-8", "replace"), name))
                        stats["failed"] += 1
                        break
                    time.sleep(10)
                    continue
                if r.status_code != 200:
                    db.execute("UPDATE tasks SET status='failed',http=?,error=? WHERE name=?",
                               (r.status_code, body[:200].decode("utf-8", "replace"), name))
                    stats["failed"] += 1
                    break
                nbytes = len(body)
                try:
                    doc = json.loads(body)
                    parsed = parse(doc, name, rank, now)
                except (ValueError, MemoryError, TypeError) as e:
                    db.execute("UPDATE tasks SET status='failed',http=200,bytes=?,error=? WHERE name=?",
                               (nbytes, f"parse:{e}"[:200], name))
                    stats["failed"] += 1
                    break
                finally:
                    body = None  # 큰 문서는 파싱 직후 버린다
                if parsed is None:
                    db.execute("UPDATE tasks SET status='unpublished',http=200,fetched_at=?,bytes=?,n_versions=0 WHERE name=?",
                               (now, nbytes, name))
                    stats["unpublished"] += 1
                    break
                vrows, modified = parsed
                for row in vrows:
                    W.write(row)
                n_unpub = sum(1 for row in vrows if row["unpublished"])
                db.execute(
                    "UPDATE tasks SET status='done',http=200,fetched_at=?,bytes=?,n_versions=?,n_unpublished=?,modified=? "
                    "WHERE name=?",
                    (now, nbytes, len(vrows), n_unpub, modified, name),
                )
                stats["ok"] += 1
                stats["bytes"] += nbytes
                stats["versions"] += len(vrows)
                if nbytes > stats["max_bytes"]:
                    stats["max_bytes"], stats["max_bytes_name"] = nbytes, name
                doc = vrows = None
                break
            recent.append(time.time())
            if len(recent) > 100:
                recent.pop(0)
            if (i + 1) % 20 == 0:
                db.commit()
            if (i + 1) % 100 == 0 or i + 1 == len(pending):
                db.commit()
                el = time.time() - started
                per_task = (recent[-1] - recent[0]) / max(1, len(recent) - 1) if len(recent) > 1 else 0
                eta = per_task * (len(pending) - i - 1)
                avg_kb = stats["bytes"] / max(1, stats["ok"]) / 1024
                print(
                    f"[collect] {i + 1}/{len(pending)} pkgs  ok={stats['ok']} nf={stats['not_found']} "
                    f"unpub={stats['unpublished']} fail={stats['failed']} 429={stats['http429']}  "
                    f"versions={stats['versions']} avg_doc={avg_kb:.0f}KB "
                    f"max_doc={stats['max_bytes'] / 1024 / 1024:.1f}MB({stats['max_bytes_name']})  interval={interval:.2f}s "
                    f"{el / 3600:.2f}h elapsed, eta {eta / 3600:.2f}h (recent {per_task:.2f}s/pkg)",
                    flush=True,
                )
            if (i + 1) % 500 == 0:
                manifest()
    except KeyboardInterrupt:
        print("[collect] interrupted — checkpoint saved", flush=True)
    finally:
        db.commit()
        W.close()
        manifest(final=True)
        db.close()
        print(f"[collect] wrote manifest {manifest_path}", flush=True)


if __name__ == "__main__":
    main()
