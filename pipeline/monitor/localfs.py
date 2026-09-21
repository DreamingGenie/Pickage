"""로컬 디스크 — 지정한 경로에 무엇이 얼마나 쌓였고, 최근에 무엇이 생겼는가.

MinIO 에 `_SUCCESS` 가 붙기 전의 산출물은 로컬(`/srv/pickage/ingest-work`)에만 있다.
회차가 도는 23시간 동안 "지금 어디까지 받았나" 는 여기 파일이 늘어나는 것으로만 보인다.
단계별 로그(`logs/<step>.log`)도 여기다 — `run.json` 의 error_message 는 꼬리 4 KB 뿐이다.
"""
from __future__ import annotations

import glob
import heapq
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


def _keep(heap: list, item: tuple, cap: int) -> None:
    """크기 cap 의 최소 힙. 넘치면 가장 작은 것을 버린다 — 순회 중 목록이 파일 수만큼 자라지 않게."""
    if cap <= 0:
        return
    if len(heap) < cap:
        heapq.heappush(heap, item)
    else:
        heapq.heappushpop(heap, item)


def scan_path(path: str, label: str, *, now_epoch: float, window_hours: int,
              max_new_files: int, max_entries: int) -> dict:
    """경로 하나를 끝까지 훑는다 — 파일 수·크기, 바로 아래 항목별 집계, 최근/가장 오래된 파일.

    메모리는 파일 수에 비례하지 않는다. 바로 아래 항목(entries)은 항목 수만큼, 최근·오래된
    목록은 각각 max_new_files 개까지만 든다 — 20만 파일짜리 캐시를 훑어도 수십 KB 다.
    """
    root = Path(path)
    if not root.is_dir():
        return {"label": label, "missing": True}
    since = now_epoch - window_hours * 3600
    entries: dict[str, dict] = {}
    total_bytes = total_files = 0
    latest = None
    newest: list[tuple[float, str, int]] = []    # (mtime, …) 최소 힙 → 가장 최근 N개가 남는다
    oldest: list[tuple[float, str, int]] = []    # (-mtime, …) 최소 힙 → 가장 오래된 N개가 남는다
    new_bytes = new_count = 0
    for rel, size, mtime in _walk(root):
        total_bytes += size
        total_files += 1
        if latest is None or mtime > latest:
            latest = mtime
        rel = rel.replace(os.sep, "/")
        head = rel.split("/", 1)[0]
        bucket = entries.setdefault(head, {"name": head, "bytes": 0, "files": 0, "latest": None, "oldest": None})
        bucket["bytes"] += size
        bucket["files"] += 1
        if bucket["latest"] is None or mtime > bucket["latest"]:
            bucket["latest"] = mtime
        if bucket["oldest"] is None or mtime < bucket["oldest"]:
            bucket["oldest"] = mtime
        _keep(oldest, (-mtime, rel, size), max_new_files)
        if mtime >= since:
            new_count += 1
            new_bytes += size
            _keep(newest, (mtime, rel, size), max_new_files)
    rows = sorted(entries.values(), key=lambda e: (e["latest"] or 0), reverse=True)
    for row in rows:
        row["latest"] = _iso(row["latest"]) if row["latest"] else None
        row["oldest"] = _iso(row["oldest"]) if row["oldest"] else None
    return {
        "label": label,
        "bytes": total_bytes,
        "files": total_files,
        "latest": _iso(latest) if latest else None,
        "entries": rows[:max_entries],
        "entries_total": len(rows),
        "new": {"window_hours": window_hours, "files": new_count, "bytes": new_bytes,
                "list": [{"path": rel, "bytes": size, "modified": _iso(mtime)}
                         for mtime, rel, size in sorted(newest, key=lambda t: (-t[0], t[1]))]},   # 최근 것부터, 같으면 경로순
        # 가장 오래된 파일 — 캐시라면 비울 후보, 산출물이라면 안 지워진 옛 회차다.
        "oldest": [{"path": rel, "bytes": size, "modified": _iso(-neg)}
                   for neg, rel, size in sorted(oldest, key=lambda t: (-t[0], t[1]))],            # 오래된 것부터, 같으면 경로순
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
