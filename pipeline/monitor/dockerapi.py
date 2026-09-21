"""Docker Engine API 를 소켓으로 직접 부른다 — 컨테이너 목록·상태·로그 꼬리.

`docker` 파이썬 SDK 를 넣지 않는 이유: 쓰는 엔드포인트가 셋(`/containers/json`,
`/containers/<id>/json`, `/containers/<id>/logs`)뿐이고, SDK 는 의존성이 requests·
urllib3 로 이어진다. 여기 코드가 60줄이다.

⚠ 소켓을 주는 것은 호스트 root 를 주는 것과 같다 — `deploy/prod/monitoring/README.md` 4절.
  이 모듈은 GET 만 부른다. 컨테이너를 만들거나 지우는 경로는 아예 없다.
"""
from __future__ import annotations

import http.client
import json
import re
import socket
from urllib.parse import urlencode

# API 버전 접두사(/v1.xx)를 붙이지 않는다. 붙이면 새 데몬이 "client version is too old" 로 거절한다 —
# 두 노드의 데몬이 최소 1.44 를 요구해 박아 둔 v1.41 이 400 을 받았다(2026-09-21). 접두사가 없으면
# 데몬이 자기 현재 버전으로 답하고, 여기서 쓰는 세 엔드포인트와 읽는 필드(Names·State·
# Config.Labels·logs)는 모든 버전에 있다.


class _UnixConnection(http.client.HTTPConnection):
    def __init__(self, path: str, timeout: float):
        super().__init__("localhost", timeout=timeout)
        self.unix_path = path

    def connect(self):
        family = getattr(socket, "AF_UNIX", None)
        if family is None:
            raise OSError("이 플랫폼에는 유닉스 소켓이 없다 (컨테이너 안에서만 돈다)")
        sock = socket.socket(family, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self.unix_path)
        self.sock = sock


class DockerClient:
    def __init__(self, socket_path: str = "/var/run/docker.sock", timeout: float = 30.0):
        self.socket_path = socket_path
        self.timeout = timeout

    def _get(self, path: str, query: dict | None = None) -> bytes:
        conn = _UnixConnection(self.socket_path, self.timeout)
        try:
            url = path
            if query:
                url += "?" + urlencode(query)
            conn.request("GET", url)
            response = conn.getresponse()
            body = response.read()
            if response.status >= 400:
                raise RuntimeError(f"Docker API {response.status} {path}: {body[:200]!r}")
            return body
        finally:
            conn.close()

    def containers(self) -> list[dict]:
        return json.loads(self._get("/containers/json", {"all": "1"}))

    def inspect(self, container_id: str) -> dict:
        return json.loads(self._get(f"/containers/{container_id}/json"))

    def logs(self, container_id: str, *, tail: int, since: int, tty: bool) -> list[str]:
        raw = self._get(f"/containers/{container_id}/logs",
                        {"stdout": "1", "stderr": "1", "tail": str(tail), "since": str(since)})
        return split_lines(raw if tty else demux(raw))


def demux(raw: bytes) -> bytes:
    """TTY 없는 컨테이너의 로그는 8바이트 헤더(스트림 1바이트 + 0×3 + 길이 4바이트 BE)
    프레임이다. 헤더를 벗기고 본문만 잇는다. 깨진 꼬리는 그대로 붙인다 — 잘라 버리면
    마지막 줄이 통째로 사라진다.
    """
    out = bytearray()
    pos = 0
    total = len(raw)
    while pos + 8 <= total:
        stream = raw[pos]
        if stream not in (0, 1, 2) or raw[pos + 1:pos + 4] != b"\x00\x00\x00":
            out.extend(raw[pos:])        # 헤더 모양이 아니다 — TTY 로그가 섞인 것
            return bytes(out)
        size = int.from_bytes(raw[pos + 4:pos + 8], "big")
        out.extend(raw[pos + 8:pos + 8 + size])
        pos += 8 + size
    out.extend(raw[pos:])
    return bytes(out)


def split_lines(data: bytes) -> list[str]:
    text = data.decode("utf-8", errors="replace")
    return [line.rstrip("\r") for line in text.split("\n") if line.strip()]


def summarize(listing: dict, detail: dict) -> dict:
    """`/containers/json` 한 항목 + `inspect` 결과 → 화면에 필요한 것만."""
    state = detail.get("State") or {}
    health = (state.get("Health") or {}).get("Status")
    names = listing.get("Names") or []
    name = names[0].lstrip("/") if names else listing.get("Id", "")[:12]
    labels = (detail.get("Config") or {}).get("Labels") or {}
    return {
        "name": name,
        "image": listing.get("Image"),
        "state": state.get("Status") or listing.get("State"),   # running · exited · restarting …
        "status": listing.get("Status"),                         # 사람이 읽는 "Up 3 hours" 류
        "exit_code": state.get("ExitCode"),
        "oom_killed": bool(state.get("OOMKilled")),
        "started_at": _iso_or_none(state.get("StartedAt")),
        "finished_at": _iso_or_none(state.get("FinishedAt")),
        "restart_count": detail.get("RestartCount", 0),
        "health": health,
        "tty": bool((detail.get("Config") or {}).get("Tty")),
        "compose_project": labels.get("com.docker.compose.project"),
        "compose_service": labels.get("com.docker.compose.service"),
    }


def _iso_or_none(value):
    # Docker 는 "안 일어난 일" 을 0001-01-01T00:00:00Z 로 준다. 화면에 그 해가 찍히면 안 된다.
    if not value or value.startswith("0001-01-01"):
        return None
    return value


def count_matches(lines: list[str], pattern: str) -> int:
    regex = re.compile(pattern)
    return sum(1 for line in lines if regex.search(line))


def collect(client: DockerClient, *, name_pattern: str, log_tail: int,
            log_since_hours: int, error_pattern: str, now_epoch: int) -> dict:
    """이름이 패턴에 걸리는 컨테이너 전부(멈춘 것 포함)와 각자의 로그 꼬리."""
    regex = re.compile(name_pattern)
    since = now_epoch - log_since_hours * 3600
    rows = []
    for item in client.containers():
        names = [n.lstrip("/") for n in item.get("Names") or []]
        if not any(regex.search(n) for n in names):
            continue
        detail = client.inspect(item["Id"])
        row = summarize(item, detail)
        try:
            lines = client.logs(item["Id"], tail=log_tail, since=since, tty=row["tty"])
            row["log"] = {"lines": lines, "error_lines": count_matches(lines, error_pattern),
                          "since_hours": log_since_hours, "tail": log_tail}
        except Exception as error:   # 로그 하나가 안 읽혀도 목록은 남긴다
            row["log"] = {"lines": [], "error_lines": 0, "error": str(error)}
        rows.append(row)
    rows.sort(key=lambda r: r["name"])
    return {"containers": rows, "matched": len(rows)}
