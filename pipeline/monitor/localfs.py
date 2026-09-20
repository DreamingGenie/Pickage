"""로컬 디스크 — 지정한 경로에 무엇이 얼마나 쌓였고, 최근에 무엇이 생겼는가.

MinIO 에 `_SUCCESS` 가 붙기 전의 산출물은 로컬(`/srv/pickage/ingest-work`)에만 있다.
회차가 도는 23시간 동안 "지금 어디까지 받았나" 는 여기 파일이 늘어나는 것으로만 보인다.
단계별 로그(`logs/<step>.log`)도 여기다 — `run.json` 의 error_message 는 꼬리 4 KB 뿐이다.
"""
from __future__ import annotations

import glob
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat(timespec="seconds")


def disk_usage(path: str) -> dict | None:
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return None
    return {"total": usage.total, "used": usage.used, "free": usage.free}


def _walk(root: Path):
    """(상대경로, 크기, mtime) 를 낸다. 못 읽는 항목은 건너뛴다 — 권한 하나로 전체를 잃지 않는다."""
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_symlink():
                    continue                       # 입고기도 심링크를 거부한다. 따라가지 않는다
                if entry.is_dir(follow_symlinks=False):
                    stack.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    stat = entry.stat(follow_symlinks=False)
                    yield os.path.relpath(entry.path, root), stat.st_size, stat.st_mtime
            except OSError:
                continue


def scan_path(path: str, label: str, *, now_epoch: float, window_hours: int,
              max_new_files: int, max_entries: int) -> dict:
    root = Path(path)
    if not root.is_dir():
        return {"label": label, "missing": True}
    since = now_epoch - window_hours * 3600
    entries: dict[str, dict] = {}
    total_bytes = total_files = 0
    latest = None
    new_files: list[tuple[float, str, int]] = []
    new_bytes = new_count = 0
    for rel, size, mtime in _walk(root):
        total_bytes += size
        total_files += 1
        if latest is None or mtime > latest:
            latest = mtime
        head = rel.replace(os.sep, "/").split("/", 1)[0]
        bucket = entries.setdefault(head, {"name": head, "bytes": 0, "files": 0, "latest": None})
        bucket["bytes"] += size
        bucket["files"] += 1
        if bucket["latest"] is None or mtime > bucket["latest"]:
            bucket["latest"] = mtime
        if mtime >= since:
            new_count += 1
            new_bytes += size
            new_files.append((mtime, rel.replace(os.sep, "/"), size))
    new_files.sort(reverse=True)
    rows = sorted(entries.values(), key=lambda e: (e["latest"] or 0), reverse=True)
    for row in rows:
        row["latest"] = _iso(row["latest"]) if row["latest"] else None
    return {
        "label": label,
        "bytes": total_bytes,
        "files": total_files,
        "latest": _iso(latest) if latest else None,
        "entries": rows[:max_entries],
        "entries_total": len(rows),
        "new": {"window_hours": window_hours, "files": new_count, "bytes": new_bytes,
                "list": [{"path": rel, "bytes": size, "modified": _iso(mtime)}
                         for mtime, rel, size in new_files[:max_new_files]]},
        "disk": disk_usage(path),
    }


def tail_lines(path: Path, count: int, *, chunk: int = 65536) -> list[str]:
    """파일 끝에서 count 줄. 큰 로그를 통째로 읽지 않는다."""
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            data = b""
            while size > 0 and data.count(b"\n") <= count:
                step = min(chunk, size)
                size -= step
                handle.seek(size)
                data = handle.read(step) + data
                if len(data) > chunk * 8:
                    break
    except OSError:
        return []
    lines = data.decode("utf-8", errors="replace").splitlines()
    return [line for line in lines if line.strip()][-count:]


def scan_logs(globs: list[str], *, tail: int, error_pattern: str, max_logs: int,
              strip_prefix: str = "") -> list[dict]:
    """패턴에 걸리는 로그 파일 중 최근 것부터 max_logs 개. 각각 꼬리와 에러 줄 수."""
    regex = re.compile(error_pattern)
    found = []
    for pattern in globs:
        for match in glob.glob(pattern):
            path = Path(match)
            try:
                stat = path.stat()
            except OSError:
                continue
            found.append((stat.st_mtime, path, stat.st_size))
    found.sort(reverse=True)
    rows = []
    for mtime, path, size in found[:max_logs]:
        lines = tail_lines(path, tail)
        shown = str(path).replace(os.sep, "/")
        if strip_prefix and shown.startswith(strip_prefix):
            shown = shown[len(strip_prefix):]
        rows.append({"path": shown, "size": size, "modified": _iso(mtime),
                     "tail": lines, "error_lines": sum(1 for l in lines if regex.search(l))})
    return rows
