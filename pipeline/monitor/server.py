"""HTTP 서버 — 요청이 오면 **그때** 보고서를 만든다.

    GET /                      화면 (web/index.html)
    GET /api/nodes             이 노드와 중계하는 노드들
    GET /api/report            이 노드의 보고서 (JSON). ?fresh=1 이면 캐시를 무시한다
    GET /api/report?node=<x>   peers 에 있는 노드면 거기서 받아 그대로 넘긴다

주기적으로 파일을 쓰지 않는 이유: 사람이 보는 것은 "지금" 이다. 5분 전 보고서는 회차가
도는 동안 아무 답도 못 한다. 그래서 요청마다 계산하고, 무거운 절(버킷 LIST)만 짧게 캐시한다.

인증은 없다 — netdata 와 같은 자세다. 듣는 주소가 127.0.0.1(터널) 과 사설 IP(다른 노드의
중계) 뿐이고, 바깥 문은 호스트 방화벽이 닫고 있다. 로그 꼬리가 들어 있으므로 이 주소 목록을
넓히지 않는다 (deploy/prod/monitoring/README.md 11절).
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

WEB_DIR = Path(__file__).parent / "web"


class ReportCache:
    """짧은 캐시 + 같은 순간의 요청은 한 번만 계산한다 (탭 둘·연타)."""

    def __init__(self, build, ttl_seconds: float):
        self.build = build
        self.ttl = ttl_seconds
        self.lock = threading.Lock()
        self.value = None
        self.at = 0.0

    def get(self, *, fresh: bool = False) -> dict:
        with self.lock:
            if not fresh and self.value is not None and time.monotonic() - self.at < self.ttl:
                cached = dict(self.value)
                cached["cached"] = True
                return cached
            self.value = self.build(fresh=fresh)
            self.at = time.monotonic()
            return dict(self.value)


def fetch_peer(url: str, *, fresh: bool, timeout: float, path: str = "/api/report") -> tuple[int, dict]:
    """(상태 코드, JSON). 피어가 4xx/5xx 로 **답한** 것은 그대로 돌려준다 — 닿지 못한 것과 다르다.

    둘을 섞어 502 "닿지 못했다" 로 내면 사람이 방화벽을 뒤지는데 실제 원인은 그 노드의 보고서
    실패(500)나 꺼 둔 기능(404)이다. 닿지 못한 경우만 URLError 로 올라간다.
    """
    target = url.rstrip("/") + path + ("?fresh=1" if fresh else "")
    try:
        with urllib.request.urlopen(target, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body)
        except ValueError:
            payload = None
        if not isinstance(payload, dict):
            payload = {"error": f"{url} 이 {error.code} 로 답했다: {body[:300]}"}
        return error.code, payload


def peer_error(node: str, message: str) -> dict:
    """그 노드에 **닿지 못했다.** 화면은 그 노드 자리에 이유를 띄운다."""
    return {"schema": 1, "node": node, "generated_at": None, "unreachable": True,
            "errors": [{"section": "fetch", "message": message}]}


def report_error(node: str, message: str) -> dict:
    """닿았는데 보고서 자체를 못 만들었다. unreachable 이 아니다 — 방화벽이 아니라 그 노드의 로그를 볼 일이다."""
    return {"schema": 1, "node": node, "generated_at": None,
            "errors": [{"section": "report", "message": message}]}


def make_handler(*, node: str, cache: ReportCache, peers: dict[str, str], peer_timeout: float,
                 inventory=None, inventory_timeout: float = 600.0, web_dir: Path = WEB_DIR, log=print):
    """inventory: full_inventory(force=bool) 를 주면 이 노드가 전체 목록 조회를 받는다. 없으면 중계만."""
    class Handler(BaseHTTPRequestHandler):
        server_version = "pickage-pipeline-monitor/1"

        def log_message(self, fmt, *args):   # 기본은 stderr 에 한 줄씩. 우리 로그 형식으로
            log(f"{self.address_string()} {fmt % args}")

        def _send(self, status: int, body: bytes, content_type: str):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, status: int, payload: dict):
            self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            parts = urlsplit(self.path)
            query = parse_qs(parts.query)
            fresh = query.get("fresh", ["0"])[0] in ("1", "true", "yes")
            path = parts.path
            if path in ("/", "/index.html", "/pipeline.html"):
                page = web_dir / "index.html"
                if not page.is_file():
                    return self._send(404, "web/index.html 이 없다".encode("utf-8"), "text/plain; charset=utf-8")
                return self._send(200, page.read_bytes(), "text/html; charset=utf-8")
            if path == "/api/nodes":
                return self._json(200, {"self": node, "nodes": [node, *sorted(peers)],
                                        "peers": peers})
            if path == "/api/report":
                target = query.get("node", [node])[0]
                if target == node:
                    try:
                        return self._json(200, cache.get(fresh=fresh))
                    except Exception as error:   # 보고서 자체를 못 만든 경우도 JSON 으로 — 화면이 이유를 보여 준다
                        return self._json(500, report_error(node, f"{type(error).__name__}: {error}"[:500]))
                if target in peers:
                    try:
                        status, payload = fetch_peer(peers[target], fresh=fresh, timeout=peer_timeout)
                    except (urllib.error.URLError, OSError, ValueError) as error:
                        return self._json(502, peer_error(
                            target, f"{peers[target]} 에 닿지 못했다: {error} — 그 노드의 컨테이너와 방화벽(ufw)을 볼 것"))
                    payload["fetched_via"] = node
                    payload["fetched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                    return self._json(status, payload)   # 피어의 500·404 는 그 코드 그대로 — 닿긴 했다
                return self._json(404, {"error": f"모르는 노드: {target}", "nodes": [node, *peers]})
            if path == "/api/inventory":
                # 전체 목록 — 사람이 버튼을 눌렀을 때만 fresh 다. 자동 갱신은 fresh 없이 와서 마지막 결과만 받는다.
                target = query.get("node", [node])[0]
                if target == node:
                    if inventory is None:
                        return self._json(404, {"available": False, "error": f"{node} 노드는 전체 목록 조회를 하지 않는다 (minio.inventory)"})
                    try:
                        return self._json(200, inventory(force=fresh))
                    except Exception as error:
                        return self._json(500, {"available": False, "error": f"{type(error).__name__}: {error}"[:500]})
                if target in peers:
                    try:
                        status, payload = fetch_peer(peers[target], fresh=fresh, path="/api/inventory",
                                                     timeout=inventory_timeout if fresh else peer_timeout)
                    except (urllib.error.URLError, OSError, ValueError) as error:
                        return self._json(502, {"available": False, "unreachable": True,
                                                "error": f"{peers[target]} 에 닿지 못했다: {error}"})
                    payload["fetched_via"] = node
                    if status >= 400:
                        payload.setdefault("available", False)
                    return self._json(status, payload)
                return self._json(404, {"available": False, "error": f"모르는 노드: {target}"})
            if path == "/healthz":
                return self._send(200, b"ok", "text/plain")
            return self._send(404, b"not found", "text/plain")

    return Handler


def serve(addresses: list[tuple[str, int]], handler, *, log=print) -> list[ThreadingHTTPServer]:
    """주소마다 서버 하나. 마지막 것만 이 스레드에서 돌리고 나머지는 데몬 스레드."""
    servers = []
    for host, port in addresses:
        server = ThreadingHTTPServer((host, port), handler)
        server.daemon_threads = True
        servers.append(server)
        log(f"listening http://{host}:{port}/")
    for server in servers[:-1]:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    return servers
