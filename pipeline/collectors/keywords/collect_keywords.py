"""ecosyste.ms npm 패키지 keywords 수집기 — 검증_keywords_수집가능성_260908.md §3 실행안 1단계.

목록 API를 다운로드 순위 내림차순으로 페이지 단위(1,000개) 호출해 AI 학습에 필요한 열만 jsonl.gz로 남긴다.
페이지가 원자 단위다: part-NNNNN.jsonl.gz 가 있으면 완료(임시파일에 쓰고 rename) → 재시작 시 없는 페이지만 받는다.
한도: polite 시간당 15,000건(UA에 연락처). 페이지당 3~8 s, 100 MB급 응답이므로 병목은 회선이지 한도가 아니다.

사용:
  python collect_keywords.py --run 2026-09-08 --pages 1000 --out data/keywords/raw
  python collect_keywords.py --run 2026-09-08 --pages 1000 --worker 0 --of 3   # 팀 분산: page % of == worker 만
옵션: --start N(첫 페이지) --per-page 1000 --interval 0.5(요청 간 최소 간격 s) --smoke(per-page 100·2페이지·별도 run)
"""
import argparse
import gzip
import json
import os
import socket
import time
from datetime import datetime, timezone

import requests

API = "https://packages.ecosyste.ms/api/v1/registries/npmjs.org/packages"
# ecosyste.ms polite pool 은 UA 에 연락처를 요구한다. 개인 주소는 저장소에 올리지 않으므로 비워 두고
# 실행자가 환경변수 OSS_SHIFT_UA_CONTACT 로 넘긴다(downloads/collect.py 와 같은 변수). 비어 있으면 실행을 거부한다.
UA_CONTACT = os.environ.get("OSS_SHIFT_UA_CONTACT", "")
UA = f"oss-shift-a506 keywords-collector (SSAFY student project; {UA_CONTACT})"

REPO_KEYS = ("full_name", "description", "topics", "language", "stargazers_count", "forks_count",
             "archived", "fork", "pushed_at", "default_branch", "license")


def slim(x, rank):
    """응답 1건 → 저장 열. 원본은 110 MB/페이지라 보존하지 않고 필요한 것만 남긴다."""
    rm = x.get("repo_metadata") or {}
    return {
        "rank": rank,
        "name": x.get("name"),
        "namespace": x.get("namespace"),
        "description": x.get("description"),
        "keywords": x.get("keywords_array") or [],
        "downloads_last_month": x.get("downloads"),
        "downloads_period": x.get("downloads_period"),
        "dependent_packages_count": x.get("dependent_packages_count"),
        "dependent_repos_count": x.get("dependent_repos_count"),
        "versions_count": x.get("versions_count"),
        "latest_release_number": x.get("latest_release_number"),
        "latest_release_published_at": x.get("latest_release_published_at"),
        "first_release_published_at": x.get("first_release_published_at"),
        "licenses": x.get("licenses"),
        "status": x.get("status"),
        "repository_url": x.get("repository_url"),
        "homepage": x.get("homepage"),
        "maintainers_count": len(x.get("maintainers") or []),
        "last_synced_at": x.get("last_synced_at"),
        "repo_metadata_updated_at": x.get("repo_metadata_updated_at"),
        "repo": {k: rm.get(k) for k in REPO_KEYS} if rm else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--out", default="data/keywords/raw")
    ap.add_argument("--pages", type=int, default=1000)
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--per-page", type=int, default=1000)
    ap.add_argument("--interval", type=float, default=0.5)
    ap.add_argument("--worker", type=int, default=0)
    ap.add_argument("--of", type=int, default=1)
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    if not UA_CONTACT:
        raise SystemExit("[keywords] User-Agent 연락처가 비어 있다. 환경변수 OSS_SHIFT_UA_CONTACT=<이메일 또는 URL> 을 설정할 것")
    if a.smoke:
        a.run, a.pages, a.per_page = f"smoke-{a.run}", 2, 100

    rundir = os.path.join(a.out, f"run={a.run}")
    os.makedirs(rundir, exist_ok=True)
    pages = [p for p in range(a.start, a.start + a.pages) if p % a.of == a.worker]
    done = {p for p in pages if os.path.exists(os.path.join(rundir, f"part-{p:05d}.jsonl.gz"))}
    todo = [p for p in pages if p not in done]
    print(f"[keywords] run={a.run} pages={len(pages)} done={len(done)} todo={len(todo)} per_page={a.per_page} "
          f"worker={a.worker}/{a.of}", flush=True)

    S = requests.Session()
    S.headers["User-Agent"] = UA
    stats = {"ok": 0, "rows": 0, "with_keywords": 0, "with_topics": 0, "http429": 0, "http5xx": 0,
             "conn_err": 0, "empty_pages": 0, "bytes": 0}
    started = time.time()
    manifest_path = os.path.join(rundir, "manifest.json")
    page_log = {}                                   # page -> (first_downloads, last_downloads, n, secs)
    last_call = 0.0

    def manifest(final=False):
        m = {"run": a.run, "source": API, "per_page": a.per_page, "pages_planned": len(pages),
             "pages_done": len(done), "worker": a.worker, "of": a.of, "host": socket.gethostname(),
             "started_at": datetime.fromtimestamp(started, timezone.utc).isoformat(),
             "updated_at": datetime.now(timezone.utc).isoformat(), "final": final,
             "elapsed_s": round(time.time() - started), "session_stats": stats,
             "page_log": {str(k): v for k, v in sorted(page_log.items())}}
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False, indent=1)

    try:
        for i, p in enumerate(todo):
            attempts = 0
            while True:
                wait = last_call + a.interval - time.time()
                if wait > 0:
                    time.sleep(wait)
                last_call = time.time()
                t0 = time.time()
                try:
                    r = S.get(API, params={"sort": "downloads", "order": "desc", "per_page": a.per_page, "page": p},
                              timeout=(30, 600))
                except requests.RequestException as e:
                    stats["conn_err"] += 1
                    attempts += 1
                    print(f"[keywords] page {p} conn_err {e.__class__.__name__} attempt {attempts}", flush=True)
                    time.sleep(min(60, 5 * 2 ** attempts))
                    if attempts >= 6:
                        raise
                    continue
                if r.status_code == 429:
                    stats["http429"] += 1
                    reset = int(r.headers.get("x-ratelimit-reset", "0") or 0)
                    sleep = max(30, min(3600, reset - int(time.time()) + 5)) if reset else 60
                    print(f"[keywords] page {p} 429 remaining={r.headers.get('x-ratelimit-remaining')} sleep {sleep}s", flush=True)
                    time.sleep(sleep)
                    continue
                if r.status_code >= 500:
                    stats["http5xx"] += 1
                    attempts += 1
                    time.sleep(min(120, 10 * 2 ** attempts))
                    if attempts >= 6:
                        raise SystemExit(f"[keywords] page {p} 5xx {attempts}회, 중단")
                    continue
                r.raise_for_status()
                break

            rows = r.json()
            secs = round(time.time() - t0, 1)
            stats["bytes"] += len(r.content)
            if not rows:
                stats["empty_pages"] += 1
                print(f"[keywords] page {p} empty → 레지스트리 끝. 남은 페이지 건너뜀", flush=True)
                # 빈 페이지도 완료로 표시해 재시작 시 다시 부르지 않는다
                with gzip.open(os.path.join(rundir, f"part-{p:05d}.jsonl.gz"), "wt", encoding="utf-8"):
                    pass
                done.add(p)
                break
            tmp = os.path.join(rundir, f"part-{p:05d}.jsonl.gz.tmp")
            base = (p - 1) * a.per_page
            fetched_at = datetime.now(timezone.utc).isoformat()
            nk = nt = 0
            with gzip.open(tmp, "wt", encoding="utf-8") as f:
                for j, x in enumerate(rows):
                    o = slim(x, base + j + 1)
                    o["page"], o["fetched_at"] = p, fetched_at
                    nk += bool(o["keywords"])
                    nt += bool(o["repo"] and o["repo"].get("topics"))
                    f.write(json.dumps(o, ensure_ascii=False) + "\n")
            os.replace(tmp, tmp[:-4])
            done.add(p)
            stats["ok"] += 1
            stats["rows"] += len(rows)
            stats["with_keywords"] += nk
            stats["with_topics"] += nt
            page_log[p] = (rows[0].get("downloads"), rows[-1].get("downloads"), len(rows), secs)
            if i % 10 == 0 or p == todo[-1]:
                el = time.time() - started
                rate = (i + 1) / el
                eta = (len(todo) - i - 1) / rate if rate else 0
                print(f"[keywords] page {p:5d} n={len(rows)} kw={nk} topics={nt} {secs}s {len(r.content)/1e6:.0f}MB "
                      f"dl={rows[0].get('downloads')}->{rows[-1].get('downloads')} remaining={r.headers.get('x-ratelimit-remaining')} "
                      f"| done {len(done)}/{len(pages)} ETA {eta/60:.0f}min", flush=True)
            if i % 10 == 0:
                manifest()
    finally:
        manifest(final=len(done) >= len(pages) or stats["empty_pages"] > 0)
        print(f"[keywords] end done={len(done)}/{len(pages)} rows={stats['rows']} kw={stats['with_keywords']} "
              f"topics={stats['with_topics']} 429={stats['http429']} {stats['bytes']/1e9:.1f}GB "
              f"{(time.time()-started)/60:.0f}min", flush=True)


if __name__ == "__main__":
    main()
