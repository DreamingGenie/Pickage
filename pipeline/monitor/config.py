"""설정 — 노드별 YAML 하나 + 자격증명 환경변수 셋.

경로·패턴·깊이처럼 **노드마다 다른 값**은 YAML(`deploy/prod/monitoring/<노드>/pipeline-monitor.yaml`)
에 있고 커밋된다. 자격증명만 환경변수로 받는다 — 운영 compose 가 `${}` 치환으로 넘긴다.

값이 빠지면 여기서 죽는다. 보고서 한복판에서 KeyError 로 죽으면 어느 줄이 빠졌는지
로그를 한참 읽어야 한다.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

NODE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")


class ConfigError(Exception):
    pass


@dataclass
class PathSpec:
    path: str          # 컨테이너 안에서 보이는 경로 (보통 /host/... 로 마운트)
    label: str         # 사람이 아는 호스트 경로. 화면에는 이것이 찍힌다


@dataclass
class MinioSettings:
    inventory: bool = True
    buckets: list[str] = field(default_factory=list)   # 비우면 계정이 볼 수 있는 전부
    depth: int = 3
    depth_overrides: dict[str, int] = field(default_factory=dict)
    max_objects: int = 300_000
    new_window_hours: int = 24
    recent_per_prefix: int = 20
    # 버킷 이벤트 구독 (events.py). 켜진 뒤의 것을 retention 시간만큼 메모리에 든다.
    # 전체 목록(inventory)은 사람이 버튼을 누를 때만 긁는다 — 자동으로는 절대 안 긁는다.
    events: bool = True
    events_retention_hours: int = 24
    events_max: int = 20_000
    weekly: bool = True
    weekly_bucket: str = "pickage-raw"
    weekly_max_runs: int = 8
    pointers: list[str] = field(default_factory=list)  # "bucket/key" 형태


@dataclass
class LocalSettings:
    paths: list[PathSpec] = field(default_factory=list)
    log_globs: list[str] = field(default_factory=list)
    tail_lines: int = 30
    max_logs: int = 20
    new_window_hours: int = 24
    max_new_files: int = 50
    max_entries: int = 40


@dataclass
class DockerSettings:
    enabled: bool = True
    socket: str = "/var/run/docker.sock"
    name_pattern: str = r"pickage|minio|spark|mlflow"
    log_tail: int = 40
    log_since_hours: int = 6
    error_pattern: str = r"(?i)\b(error|exception|traceback|fatal|oom|killed|denied|refused)\b"


@dataclass
class Settings:
    node: str
    # 어디서 듣나. 주소마다 서버를 하나씩 띄운다 — 0.0.0.0 을 안 쓰기 위해서다
    # (netdata.conf 의 `bind to` 와 같은 태도).
    listen: list[str] = field(default_factory=lambda: ["127.0.0.1:19998"])
    # 다른 노드의 같은 서버. {node: url}. 화면은 한 곳(app)에만 붙고 여기서 중계한다.
    peers: dict[str, str] = field(default_factory=dict)
    peer_timeout_seconds: int = 25
    # 전체 목록 조회를 중계할 때는 훨씬 길다 — 객체 1,000개당 요청 하나라 수십만 개면 분 단위다.
    inventory_timeout_seconds: int = 600
    # 보고서 전체의 짧은 캐시. 연타·탭 여러 개를 하나로 합친다. "지금 확인" 은 무시한다.
    cache_seconds: int = 3
    minio: MinioSettings = field(default_factory=MinioSettings)
    local: LocalSettings = field(default_factory=LocalSettings)
    docker: DockerSettings = field(default_factory=DockerSettings)


@dataclass
class S3Credentials:
    endpoint: str
    access_key: str
    secret_key: str


def _section(raw: dict, name: str, cls, **extra):
    data = dict(raw.get(name) or {})
    data.update(extra)
    unknown = set(data) - set(cls.__dataclass_fields__)
    if unknown:
        raise ConfigError(f"{name}: 모르는 키 {sorted(unknown)} — 오타면 조용히 무시되는 대신 여기서 멈춘다")
    return cls(**data)


def parse_listen(value: str) -> tuple[str, int]:
    host, sep, port = value.rpartition(":")
    if not sep or not host or not port.isdigit():
        raise ConfigError(f"listen 항목은 '주소:포트' 여야 한다: {value!r}")
    return host, int(port)


def parse(raw: dict) -> Settings:
    if not isinstance(raw, dict):
        raise ConfigError("설정 파일의 최상위는 매핑이어야 한다")
    node = raw.get("node")
    if not node or not NODE_RE.match(str(node)):
        raise ConfigError("node 는 영문 소문자·숫자·하이픈이어야 한다 (URL 과 화면에 쓰인다)")
    local_raw = dict(raw.get("local") or {})
    paths = []
    for item in local_raw.pop("paths", []) or []:
        if not isinstance(item, dict) or "path" not in item:
            raise ConfigError("local.paths 항목은 {path, label} 매핑이어야 한다")
        paths.append(PathSpec(path=str(item["path"]), label=str(item.get("label") or item["path"])))
    top_unknown = set(raw) - set(Settings.__dataclass_fields__)
    if top_unknown:
        raise ConfigError(f"모르는 최상위 키 {sorted(top_unknown)}")
    settings = Settings(
        node=str(node),
        listen=[str(x) for x in (raw.get("listen") or ["127.0.0.1:19998"])],
        peers={str(k): str(v) for k, v in (raw.get("peers") or {}).items()},
        peer_timeout_seconds=int(raw.get("peer_timeout_seconds", 25)),
        inventory_timeout_seconds=int(raw.get("inventory_timeout_seconds", 600)),
        cache_seconds=int(raw.get("cache_seconds", 3)),
        minio=_section(raw, "minio", MinioSettings),
        local=_section({"local": local_raw}, "local", LocalSettings, paths=paths),
        docker=_section(raw, "docker", DockerSettings),
    )
    for item in settings.listen:
        parse_listen(item)
    for name, url in settings.peers.items():
        if not NODE_RE.match(name):
            raise ConfigError(f"peers 의 이름은 node 와 같은 규칙이다: {name!r}")
        if name == settings.node:
            raise ConfigError("peers 에 자기 자신을 넣지 않는다")
        if not url.startswith(("http://", "https://")):
            raise ConfigError(f"peers.{name} 은 http(s):// 로 시작해야 한다: {url!r}")
    for key in settings.minio.pointers:
        if "/" not in key:
            raise ConfigError(f"minio.pointers 항목은 'bucket/key' 형태여야 한다: {key}")
    re.compile(settings.docker.name_pattern)
    re.compile(settings.docker.error_pattern)
    return settings


def load(path: str | Path) -> Settings:
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"설정 파일이 없다: {path}")
    return parse(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


def s3_credentials(env=None) -> S3Credentials:
    """`PICKAGE_S3_*` — pipeline/minio 의 자격증명 파일과 같은 키 이름을 환경변수로 받는다."""
    env = os.environ if env is None else env
    endpoint = env.get("PICKAGE_S3_ENDPOINT")
    access = env.get("PICKAGE_S3_ACCESS_KEY")
    secret = env.get("PICKAGE_S3_SECRET_KEY")
    missing = [k for k, v in (("PICKAGE_S3_ENDPOINT", endpoint),
                              ("PICKAGE_S3_ACCESS_KEY", access),
                              ("PICKAGE_S3_SECRET_KEY", secret)) if not v]
    if missing:
        raise ConfigError("환경변수가 비어 있다: " + ", ".join(missing)
                          + " — deploy/prod/monitoring/<노드>/.env 를 볼 것")
    return S3Credentials(endpoint=endpoint, access_key=access, secret_key=secret)
