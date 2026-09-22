"""파이프라인 모니터 실행기 — HTTP 로 물으면 그때 보고서를 만든다.

    python -m pipeline.monitor.run                 # 서버. 설정은 $MONITOR_CONFIG (기본 /etc/pipeline-monitor.yaml)
    python -m pipeline.monitor.run --once          # 서버 없이 한 번 만들어 stdout 에 찍는다 (진단)
    python -m pipeline.monitor.run --listen 0.0.0.0:19998 --peer data=http://x:19998   # 설정 덮어쓰기 (리허설)

한 절(MinIO·주간·로컬·docker)이 실패해도 나머지는 만든다. 실패는 보고서의 `errors` 에
남고 화면이 그 절 자리에 그 메시지를 띄운다 — **조용히 비우지 않는다.**

MinIO 는 두 층이다. **이벤트 구독**(events.py)은 서버가 켜져 있는 동안 계속 쌓이고 매
보고서에 실린다. **전체 목록**(s3inv.collect)은 사람이 화면의 버튼을 눌러 `/api/inventory?fresh=1`
을 부를 때만 긁고, 그 결과는 다음에 누를 때까지 메모리에 남는다. 자동 갱신은 절대 목록을
긁지 않는다 — 객체가 수십만 개가 되어도 평소 비용이 늘지 않게.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
import time
import traceback
from datetime import datetime, timezone

from . import config as cfg
from . import curated, dockerapi, events, localfs, s3inv, server, verdict, weekly

SCHEMA = 3
DEFAULT_CONFIG = "/etc/pipeline-monitor.yaml"


def log(message: str) -> None:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"{stamp} {message}", flush=True)


def make_s3(creds: cfg.S3Credentials):
    import boto3
    from botocore.config import Config
    return boto3.client("s3", endpoint_url=creds.endpoint,
                        aws_access_key_id=creds.access_key,
                        aws_secret_access_key=creds.secret_key,
                        region_name="us-east-1",
                        config=Config(signature_version="s3v4",
                                      retries={"max_attempts": 2},
                                      connect_timeout=10, read_timeout=60))


def _section(report: dict, name: str, fn):
    """한 절을 만든다. 실패하면 그 절은 None 이고 errors 에 이유가 남는다."""
    started = time.monotonic()
    try:
        report[name] = fn()
    except Exception as error:
        report[name] = None
        report["errors"].append({"section": name, "message": f"{type(error).__name__}: {error}"[:500]})
        log(f"[{name}] 실패: {type(error).__name__}: {error}")
        traceback.print_exc()
    finally:
        report["timings"][name] = round(time.monotonic() - started, 2)


class Builder:
    """보고서를 만든다. 이벤트 저장소와 마지막 전체 목록을 든다."""

    def __init__(self, settings: cfg.Settings, *, s3, docker_client, creds: cfg.S3Credentials | None = None,
                 open_stream=None):
        self.settings = settings
        self.s3 = s3
        self.docker_client = docker_client
        self.store: events.EventStore | None = None
        self.inventory_result: dict | None = None
        self.inventory_lock = threading.Lock()
        # refresh_seconds 를 둔 경로의 마지막 스캔 — path → (monotonic, 결과). 20만 파일을 15초마다 훑지 않게.
        self.local_scans: dict[str, tuple[float, dict]] = {}
        m = settings.minio
        if m.events and s3 is not None:
            self.store = events.EventStore(retention_hours=m.events_retention_hours, max_events=m.events_max,
                                           depth=m.depth, depth_overrides=m.depth_overrides)
            if open_stream is None and creds is not None:
                open_stream = events.minio_stream_opener(creds.endpoint, creds.access_key, creds.secret_key)
            if open_stream is not None:
                def resolve_buckets():
                    if m.buckets:
                        return list(m.buckets)
                    return sorted(b["Name"] for b in (s3.list_buckets().get("Buckets") or []))
                # MinIO 가 이 서버보다 늦게 떠도 구독이 걸리게 — 목록을 받을 때까지 재시도한다.
                events.start_listeners_when_ready(self.store, resolve_buckets, open_stream=open_stream, log=log)

    # ── 전체 목록 — 버튼으로만 ──────────────────────────────────
    def full_inventory(self, *, force: bool) -> dict:
        """force 면 지금 긁는다(동시 요청은 한 번만 긁고 같은 결과를 본다). 아니면 마지막 결과."""
        if not force:
            return self.inventory_result or {"available": False}
        with self.inventory_lock:
            m = self.settings.minio
            now = datetime.now(timezone.utc)
            started = time.monotonic()
            result = s3inv.collect(self.s3, buckets=m.buckets, depth=m.depth, depth_overrides=m.depth_overrides,
                                   max_objects=m.max_objects, now=now, window_hours=m.new_window_hours,
                                   recent_per_prefix=m.recent_per_prefix, pointers=[])
            result.update({"available": True, "took_seconds": round(time.monotonic() - started, 2),
                           "requested_at": now.isoformat(timespec="seconds")})
            self.inventory_result = result
            log(f"전체 목록 조회 took={result['took_seconds']}s objects="
                f"{sum(b.get('objects', 0) for b in result['buckets'])}")
            return result

    def build(self, *, fresh: bool = False) -> dict:
        settings = self.settings
        now = datetime.now(timezone.utc)
        started = time.monotonic()
        report = {
            "schema": SCHEMA,
            "node": settings.node,
            "hostname": os.environ.get("MONITOR_HOSTNAME") or socket.gethostname(),
            "generated_at": now.isoformat(timespec="seconds"),
            "errors": [],
            "timings": {},
        }
        m = settings.minio
        if self.s3 is not None and (m.events or m.pointers or m.inventory):
            def minio_section():
                out = {"pointers": s3inv.read_pointers(self.s3, m.pointers) if m.pointers else []}
                if self.store is not None:
                    out["events"] = self.store.snapshot(recent_per_prefix=m.recent_per_prefix)
                inv = self.inventory_result
                out["inventory"] = ({"available": True, "listed_at": inv["listed_at"],
                                     "took_seconds": inv["took_seconds"]}
                                    if inv else {"available": False})
                out["inventory_enabled"] = bool(m.inventory)
                return out
            _section(report, "minio", minio_section)
        if m.weekly and self.s3 is not None:
            _section(report, "weekly", lambda: weekly.collect(
                self.s3, bucket=m.weekly_bucket, max_runs=m.weekly_max_runs, now=now))
        if m.curated and self.s3 is not None:
            _section(report, "curated", lambda: curated.collect(
                self.s3, bucket=m.curated_bucket, max_runs=m.curated_max_runs, now=now))
        l = settings.local
        if l.paths or l.log_globs:
            def scan(p: cfg.PathSpec) -> dict:
                hit = self.local_scans.get(p.path)
                if hit and not fresh and time.monotonic() - hit[0] < p.refresh_seconds:
                    return {**hit[1], "cached": True}
                begun = time.monotonic()
                out = localfs.scan_path(p.path, p.label, now_epoch=now.timestamp(),
                                        window_hours=l.new_window_hours,
                                        max_new_files=l.max_new_files, max_entries=l.max_entries)
                out.update({"scanned_at": now.isoformat(timespec="seconds"),
                            "scan_seconds": round(time.monotonic() - begun, 2),
                            "refresh_seconds": p.refresh_seconds, "note": p.note})
                if p.refresh_seconds > 0:
                    self.local_scans[p.path] = (time.monotonic(), out)
                return out

            def local():
                return {
                    "paths": [scan(p) for p in l.paths],
                    "logs": localfs.scan_logs(l.log_globs, tail=l.tail_lines,
                                              error_pattern=l.error_pattern, error_ignore_pattern=l.error_ignore_pattern,
                                              max_logs=l.max_logs, strip_prefix="/host"),
                    # 화면이 같은 기준으로 색을 칠하고 임계 이상일 때만 판정에 올린다
                    "error_pattern": l.error_pattern, "error_ignore_pattern": l.error_ignore_pattern,
                    "error_min_lines": l.error_min_lines,
                }
            _section(report, "local", local)
        d = settings.docker
        if d.enabled and self.docker_client is not None:
            _section(report, "docker", lambda: dockerapi.collect(
                self.docker_client, name_pattern=d.name_pattern, log_tail=d.log_tail,
                log_since_hours=d.log_since_hours, error_pattern=d.error_pattern,
                error_ignore_pattern=d.error_ignore_pattern, error_min_lines=d.error_min_lines,
                now_epoch=int(now.timestamp())))
        # 판정 — 절들을 다 만든 뒤 순수 함수로. 화면은 이 목록을 그대로 보여 준다 (규칙·시계가 한 곳에 있다).
        _section(report, "findings", lambda: verdict.evaluate(report, now=now))
        report["took_seconds"] = round(time.monotonic() - started, 2)
        log(f"보고서 node={settings.node} took={report['took_seconds']}s errors={len(report['errors'])}"
            + (" fresh" if fresh else ""))
        return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Pickage 파이프라인 모니터")
    parser.add_argument("--config", default=os.environ.get("MONITOR_CONFIG", DEFAULT_CONFIG))
    parser.add_argument("--once", action="store_true", help="서버 없이 한 번 만들어 stdout 에 찍고 끝낸다")
    parser.add_argument("--no-s3", action="store_true", help="MinIO 를 아예 안 붙는다 (로컬·docker 절만)")
    parser.add_argument("--listen", action="append", help="설정의 listen 을 덮어쓴다 (여러 번 가능)")
    parser.add_argument("--peer", action="append", help="NAME=URL. 설정의 peers 에 더한다")
    args = parser.parse_args(argv)

    try:
        settings = cfg.load(args.config)
        if args.listen:
            settings.listen = args.listen
        for item in args.peer or []:
            name, sep, url = item.partition("=")
            if not sep:
                raise cfg.ConfigError(f"--peer 는 NAME=URL 이어야 한다: {item!r}")
            settings.peers[name] = url
        addresses = [cfg.parse_listen(x) for x in settings.listen]
    except cfg.ConfigError as error:
        print(f"설정 오류: {error}", file=sys.stderr)
        return 2

    s3 = creds = None
    if not args.no_s3:
        try:
            creds = cfg.s3_credentials()
            s3 = make_s3(creds)
        except cfg.ConfigError as error:
            print(f"설정 오류: {error}", file=sys.stderr)
            return 2
    docker_client = dockerapi.DockerClient(settings.docker.socket) if settings.docker.enabled else None

    if args.once:
        settings.minio.events = False        # 한 번 찍고 끝나는데 구독 스레드를 걸 이유가 없다
        builder = Builder(settings, s3=s3, docker_client=docker_client)
        print(json.dumps(builder.build(fresh=True), ensure_ascii=False, indent=1))
        return 0

    builder = Builder(settings, s3=s3, docker_client=docker_client, creds=creds)
    cache = server.ReportCache(builder.build, settings.cache_seconds)
    handler = server.make_handler(node=settings.node, cache=cache, peers=settings.peers,
                                  peer_timeout=settings.peer_timeout_seconds,
                                  inventory=builder.full_inventory if (s3 is not None and settings.minio.inventory) else None,
                                  inventory_timeout=settings.inventory_timeout_seconds, log=log)
    log(f"시작 node={settings.node} config={args.config} peers={settings.peers or '없음'}")
    servers = server.serve(addresses, handler, log=log)
    try:
        servers[-1].serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
