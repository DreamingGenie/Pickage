"""npm registry 버전 이력 수집기 — 수집계획_devDependencies_npmRegistry_260909.md §3 구현.

패키지 1개 = 요청 1회(`registry.npmjs.org/<name>`, 전체 문서). 문서에서 버전마다 dependencies · devDependencies ·
peerDependencies · optionalDependencies · 발행 시각 · deprecated 와 패키지 형태 6열(unpacked_size · file_count ·
module_type · main · types · exports)만 남겨 jsonl.gz 로 쓴다(원본 문서는 보존하지 않음).
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
import re
import socket
import sqlite3
import sys
import time
from datetime import datetime, timezone
from urllib.parse import quote

import requests

try:
    # start_registry.cmd 는 stdout 을 로그 파일로 넘긴다. 콘솔이 아니면 인코딩이 로캘(cp949)로 정해져
    # cp949 에 없는 글자 하나에 UnicodeEncodeError 로 수집기가 죽는다. chcp 65001 은 콘솔 코드페이지만 바꾼다.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

API = "https://registry.npmjs.org"
# npm은 대량 호출 시 UA에 연락 가능한 주소를 요구한다. 개인 주소는 저장소에 올리지 않으므로 비워 두고,
# 실행자가 환경변수 OSS_SHIFT_UA_CONTACT 로 넘긴다. 비어 있으면 실행을 거부한다(downloads 수집기와 동일).
UA_CONTACT = os.environ.get("OSS_SHIFT_UA_CONTACT", "")
UA = f"oss-shift-a506 collector (SSAFY student project; {UA_CONTACT})"
NON_VERSION_TIME_KEYS = {"created", "modified", "unpublished"}  # time 객체의 알려진 비버전 키
# time 의 키를 버전으로 받아들일 조건. 위 셋 말고도 모르는 키가 들어오고(실측: appdirsjs 의 "undefined"),
# 블랙리스트로 두면 그런 키가 전부 가짜 unpublish 버전 행이 되어 first_published_at 을 망친다.
# 이동쌍 빌더(pipeline/duckdb/build_migration_pairs.py)가 버전을 거르는 기준과 같은 모양을 쓴다.
VERSION_KEY = re.compile(r"^\d+\.\d+")


class TooLarge(Exception):
    pass


def enc(name):
    return quote(name, safe="@").replace("/", "%2F")


def dep_list(d):
    """{"ansi-styles": "^4.1.0"} → deps.dev NPMRequirements 와 같은 [{"Name","Requirement"}] 구조. 삽입 순서 유지."""
    if not isinstance(d, dict):
        return []
    return [{"Name": k, "Requirement": v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)} for k, v in d.items()]


def _int(v):
    """dist.unpackedSize · fileCount 는 정수여야 한다. 문자열·실수로 오는 문서가 있어도 Parquet 의 BIGINT 열이
    깨지지 않게 여기서 거른다. 정수로 읽을 수 없으면 NULL(모름)."""
    if v is None or isinstance(v, bool):
        return None
    try:
        n = v if isinstance(v, int) else int(float(v))
    except (TypeError, ValueError, OverflowError):
        return None
    # 파일 크기라 음수일 수 없고, BIGINT 를 넘으면 Parquet 변환이 통째로 죽는다.
    # 4.5시간 수집 뒤 30분짜리 변환이 이상치 한 줄에 실패하는 것보다 그 행만 모름으로 두는 게 낫다.
    return n if 0 <= n <= 2 ** 63 - 1 else None


def _text(v):
    """type · main · types 처럼 문자열이어야 하는 필드. 문자열이 아니면 JSON 으로 적어 둔다 —
    조용히 버리면 나중에 '왜 비었나' 를 물을 수 없다. deprecated 를 다루는 방식과 같다."""
    if v is None or isinstance(v, str):
        return v
    return json.dumps(v, ensure_ascii=False)


def parse(doc, name, rank, fetched_at, stats=None):
    """전체 문서 → (버전 행 목록, time.modified). 패키지 전체가 unpublish 된 문서(versions 없음 + time.unpublished)는 (None, modified).
    versions 에 없고 time 에만 있는 버전 = unpublish 된 버전: 행은 남기고 의존 네 열은 NULL(모름), unpublished=True.
    NULL 로 두는 이유: []('의존 없음') 로 쓰면 lag() 비교에서 '의존 전부 제거' 로 잘못 잡힌다(§5-3 검증에서 실제 발생).
    stats 를 주면 버전으로 보지 않고 버린 time 키 수를 odd_time_keys 에 센다(조용히 버리지 않기 위함)."""
    if not isinstance(doc, dict):
        raise ValueError(f"document is {type(doc).__name__}, not object")
    times = doc.get("time")
    if not isinstance(times, dict):
        times = {}
    modified = times.get("modified")
    versions = doc.get("versions")
    if not isinstance(versions, dict):
        if "unpublished" in times:
            return None, modified
        raise ValueError("no versions")
    vers = list(versions.keys())
    seen = set(vers)
    for k in times:
        if k in seen or k in NON_VERSION_TIME_KEYS:
            continue
        if VERSION_KEY.match(k):
            vers.append(k)
            seen.add(k)
        elif stats is not None:
            stats["odd_time_keys"] = stats.get("odd_time_keys", 0) + 1
    rows = []
    for v in vers:
        meta = versions.get(v)
        unpublished = meta is None
        if not isinstance(meta, dict):
            meta = {}
        dep = meta.get("deprecated")
        # 문구 대신 불리언이 오기도 한다. False 와 ""(npm deprecate 로 문구를 비운 경우)는 '폐기 아님'이라 NULL 로
        # 정규화하고, True 는 '문구 없는 폐기'라 'true' 로 남긴다. 실측: false 9,561행 · true 1,145행 · "" 4행.
        if dep is False or dep == "":
            dep = None
        elif dep is not None and not isinstance(dep, str):
            dep = json.dumps(dep, ensure_ascii=False)
        # 패키지 형태 6열(S15P21A506-366). unpublish 된 버전은 meta 가 비어 있어 전부 NULL(모름)이 된다 —
        # 의존 네 열과 같은 뜻이다. unpacked_size · file_count 는 top level 이 아니라 dist 안에 있고,
        # npm 이 2018년부터 계산해서 그 이전 발행 버전에는 아예 없다(결측이 '작다' 가 아니라 '모른다').
        dist = meta.get("dist")
        if not isinstance(dist, dict):
            dist = {}
        # exports 는 중첩 객체(실측 dict 799 · str 15)라 열에 그대로 못 넣는다. JSON 문자열로 적고 읽는 쪽에서 판다.
        exports = meta.get("exports")
        if exports is not None:
            exports = json.dumps(exports, ensure_ascii=False, separators=(",", ":"))
            if stats is not None and len(exports) > stats.get("max_exports_bytes", 0):
                stats["max_exports_bytes"] = len(exports)
        rows.append({
            "Name": name, "Version": v, "published_at": times.get(v), "rank": rank,
            "Dependencies": None if unpublished else dep_list(meta.get("dependencies")),
            "DevDependencies": None if unpublished else dep_list(meta.get("devDependencies")),
            "PeerDependencies": None if unpublished else dep_list(meta.get("peerDependencies")),
            "OptionalDependencies": None if unpublished else dep_list(meta.get("optionalDependencies")),
            "deprecated": dep, "unpublished": unpublished,
            "unpacked_size": _int(dist.get("unpackedSize")), "file_count": _int(dist.get("fileCount")),
            "module_type": _text(meta.get("type")), "main": _text(meta.get("main")),
            # types 가 정본이고 없으면 typings 로 떨어진다. 실측: ajv 는 typings 만 있는 버전이 127개라
            # types 만 보면 타입 제공 버전을 과소 계상한다.
            "types": _text(meta.get("types") or meta.get("typings")), "exports": exports,
            "fetched_at": fetched_at, "modified": modified,
        })
    rows.sort(key=lambda r: (r["published_at"] or "", r["Version"]))
    return rows, modified


def serialize(rows):
    """행 목록 → 쓸 준비가 끝난 줄 목록. utf-8 인코딩까지 여기서 확인한다.
    쓰는 도중에 실패하면 '체크포인트는 failed 인데 앞부분 행은 raw 에 남은' 패키지가 되고,
    그 고아 행은 (Name, Version) 중복 제거로도 걸러지지 않는다. 그래서 쓰기 전에 전부 만들어 본다.
    실제 경로: 의존 요구사항 문자열에 lone surrogate 가 있으면 json.loads 는 통과시키고 인코딩에서 터진다."""
    lines = [json.dumps(r, ensure_ascii=False) for r in rows]
    for ln in lines:
        ln.encode("utf-8")
    return lines


def online(session):
    """registry 가 닿는가. 연결 오류가 '이 패키지 문제'인지 '인터넷 끊김'인지 가르는 데 쓴다."""
    try:
        return session.get(f"{API}/-/ping", timeout=10).status_code < 500
    except requests.RequestException:
        return False


def wait_online(session, poll=30):
    """인터넷이 끊겼으면 복구될 때까지 기다린다. 끊긴 동안 패키지를 failed 로 넘기지 않기 위함(밤새 실행 대비)."""
    print("[collect] offline? registry 에 닿지 않는다. 30초마다 재확인, 복구되면 이어간다", flush=True)
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
    return r, buf  # json.loads 는 bytearray 를 그대로 받는다 — bytes() 복사(최대 115 MB)를 피한다


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

    def write_line(self, line):
        """이미 직렬화하고 utf-8 인코딩 가능까지 확인한 한 줄을 쓴다."""
        self.fh.write(line + "\n")
        self.n += 1
        if self.n >= self.rotate:
            self._open()

    def write(self, obj):
        self.write_line(json.dumps(obj, ensure_ascii=False))

    def flush(self):
        """체크포인트 commit 직전에 호출. gzip 버퍼를 디스크에 내려 강제 종료 시 '체크포인트는 done 인데 행은 없는' 패키지가 생기지 않게 한다."""
        if self.fh:
            self.fh.flush()

    def close(self):
        if self.fh:
            self.fh.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", required=True)
    ap.add_argument("--run", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--interval", type=float, default=0.5,
                    help="요청 간 최소 간격(초). 429 가 나오면 15%%씩 늘어난다(상한은 3초, --interval 이 그보다 크면 --interval)")
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
    # failed(too_large·parse·conn·5xx)는 --retry-failed 를 줬을 때만 다시 시도한다. 인터넷 끊김은 수집기가 실행 중에
    # 복구를 기다리므로(wait_online) conn: 실패는 온라인 상태의 전송 오류 4회 = 조사할 가치가 있는 사유다. 자동으로 지우지 않는다.
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
             "too_large": 0, "bytes": 0, "max_bytes": 0, "max_bytes_name": None, "versions": 0, "odd_time_keys": 0,
             "max_exports_bytes": 0}
    started = time.time()
    last_start = 0.0
    consec429 = 0
    interval = a.interval          # 적응형: 429가 나오면 15% 늘리고, 200이 이어지면 천천히 되돌린다
    # 상한을 3초로 고정하면 --interval 을 3보다 크게 준 실행에서 429 가 간격을 오히려 줄인다(느리게 돌리라고 준 값인데).
    interval_min, interval_max = a.interval, max(3.0, a.interval)
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
            pkg429 = 0
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
                        W.flush()              # 대기 중 강제 종료돼도 done 으로 commit 된 행이 디스크에 있게 (flush → commit 순서 유지)
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
                    pkg429 += 1
                    interval = min(interval * 1.15, interval_max)
                    # 상한이 없으면 영구 스로틀(IP 차단)에 걸린 패키지가 pending 으로 영원히 남는다. pending 은
                    # --retry-failed 로도 건질 수 없고, events 에 429 가 계속 찍혀 현황판은 RUNNING 으로 보인다.
                    if pkg429 >= 8:
                        db.execute("UPDATE tasks SET status='failed',http=429,error=? WHERE name=?",
                                   (f"http429: rate limited {pkg429}x", name))
                        stats["failed"] += 1
                        break
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
                # 파싱·직렬화에서 나는 어떤 예외도 이 패키지의 failed 로 기록하고 다음으로 넘어간다.
                # 예외를 밖으로 흘리면 작업이 pending 으로 남아 재시작마다 같은 패키지에서 다시 죽는다(--retry-failed 로도 못 벗어남).
                # 예: 본문이 JSON 객체가 아님(AttributeError), lone surrogate 문자열의 utf-8 인코딩(UnicodeEncodeError).
                # 줄을 전부 만들고 인코딩까지 확인한 뒤에 쓴다. 쓰는 도중에 실패하면 '체크포인트는 failed 인데
                # 앞부분 행은 raw 에 남은' 패키지가 되고, 그 고아 행은 (Name, Version) 중복 제거로도 걸러지지 않는다.
                lines = None
                try:
                    doc = json.loads(body)
                    vrows, modified = parse(doc, name, rank, now, stats)
                    doc = None                  # 큰 문서는 파싱 직후 버린다(줄 목록을 만들 메모리를 비워 준다)
                    if vrows is not None:
                        lines = serialize(vrows)
                except Exception as e:
                    db.execute("UPDATE tasks SET status='failed',http=200,bytes=?,error=? WHERE name=?",
                               (nbytes, f"parse:{type(e).__name__}:{e}"[:200], name))
                    stats["failed"] += 1
                    break
                finally:
                    body = None
                if vrows is None:
                    db.execute("UPDATE tasks SET status='unpublished',http=200,fetched_at=?,bytes=?,n_versions=0,modified=? WHERE name=?",
                               (now, nbytes, modified, name))
                    stats["unpublished"] += 1
                    break
                for ln in lines:   # 여기부터는 예외가 날 수 없다
                    W.write_line(ln)
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
                vrows = lines = None
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
        print("[collect] interrupted, checkpoint saved", flush=True)
    finally:
        W.close()      # 행을 먼저 디스크에 내리고(gzip 트레일러 포함) 그 다음 체크포인트를 확정한다
        db.commit()
        manifest(final=True)
        db.close()
        print(f"[collect] wrote manifest {manifest_path}", flush=True)


if __name__ == "__main__":
    main()
