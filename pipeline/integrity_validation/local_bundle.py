"""Explicit local metadata reads with fixed budgets; no remote client or discovery."""
from __future__ import annotations

import hashlib
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import stat

from .runner import _reject_constant, _unique_object

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 8 * 1024 * 1024
MAX_SAMPLES = 16
MAX_SAMPLE_ROWS = 5000


def strict_json(body: bytes):
    return json.loads(body, object_pairs_hook=_unique_object, parse_constant=_reject_constant)


def plain_file(path: Path, limit: int) -> Path:
    """Check before opening, including Windows junctions and other reparse points."""
    path = Path(path).absolute()
    for item in (path, *path.parents):
        info = item.lstat()
        if (stat.S_ISLNK(info.st_mode) or
                getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise ValueError("Input symlinks/reparse points are not accepted")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("Input must be a regular file")
    if info.st_size > limit:
        raise ValueError("Input exceeds the bounded file size limit")
    return path


def relative_file(root: Path, relative: str, limit: int = MAX_FILE_BYTES) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ValueError("A relative local file path is required")
    parts = relative.split("/")
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                *(f"LPT{i}" for i in range(1, 10))}
    if (PurePosixPath(relative).is_absolute() or
            any(c in relative for c in '\\:*?[]\x00<>|"') or
            any(part in ("", ".", "..") or part.endswith((".", " ")) or
                part.split(".", 1)[0].upper() in reserved for part in parts)):
        raise ValueError("Unsafe local file path")
    root = Path(root).absolute()
    path = plain_file(root.joinpath(*parts), limit)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Input path escapes the selected bundle")
    return path


def read_bounded(path: Path, limit: int = MAX_FILE_BYTES) -> bytes:
    path = plain_file(path, limit)
    with path.open("rb") as stream:
        body = stream.read(limit + 1)
    if len(body) > limit:
        raise ValueError("Input grew beyond the bounded file size limit")
    return body


class LocalMetadataStore:
    """Only the get_object surface required by native metadata selectors is exposed."""

    def __init__(self, root: Path, objects: dict):
        if (not isinstance(objects, dict) or not 1 <= len(objects) <= 3 or
                any(not isinstance(k, str) or not isinstance(v, str) for k, v in objects.items())):
            raise ValueError("Explicit metadata object mapping is required (at most 3 objects)")
        self.root = Path(root)
        self.objects = dict(objects)
        self.reads = []
        self.total_bytes = 0

    def get_object(self, *, Bucket, Key):
        if Bucket != "pickage-curated" or Key not in self.objects:
            raise ValueError("Metadata object was not explicitly mapped: " + str(Key))
        if not Key.endswith(("/run_manifest.json", "/_SUCCESS", "/_INPUT.json")):
            raise ValueError("Only native manifest and completion metadata may be opened")
        remaining = MAX_TOTAL_BYTES - self.total_bytes
        path = relative_file(self.root, self.objects[Key], min(MAX_FILE_BYTES, remaining))
        body = read_bounded(path, min(MAX_FILE_BYTES, remaining))
        # Native selectors use json.loads without duplicate-key detection. Validate
        # JSON here while returning the exact original bytes for producer SHA checks.
        if Key.endswith(".json") or body.lstrip().startswith(b"{"):
            strict_json(body)
        self.total_bytes += len(body)
        self.reads.append({"key": Key, "path": self.objects[Key], "bytes": len(body),
                           "sha256": hashlib.sha256(body).hexdigest()})
        return {"Body": BytesIO(body)}
