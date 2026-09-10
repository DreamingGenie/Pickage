"""Immutable publication of verified download files to an S3-compatible Bronze bucket."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from collections.abc import Callable

from botocore.exceptions import ClientError


_CHUNK = 1024 * 1024
_MAX_SINGLE_PUT = 5 * 1024 * 1024 * 1024
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _missing(error: Exception) -> bool:
    if not isinstance(error, ClientError):
        return False
    return str(error.response.get("Error", {}).get("Code", "")) in {
        "404", "NoSuchKey", "NotFound"
    }


def _read(s3, bucket: str, key: str) -> bytes | None:
    try:
        result = s3.get_object(Bucket=bucket, Key=key)
    except Exception as error:
        if _missing(error):
            return None
        raise
    body = result["Body"]
    try:
        return body.read()
    finally:
        close = getattr(body, "close", None)
        if close:
            close()


def _same_or_put(s3, bucket: str, key: str, body: bytes) -> bool:
    """Create an immutable object, accepting only an exact concurrent creator."""
    existing = _read(s3, bucket, key)
    if existing is not None:
        if existing != body:
            raise ValueError(f"Existing object differs: {key}")
        return False
    try:
        s3.put_object(Bucket=bucket, Key=key, Body=body, IfNoneMatch="*")
        return True
    except Exception as error:
        if not isinstance(error, ClientError) or str(error.response.get("Error", {}).get("Code", "")) not in {
                "412", "PreconditionFailed"}:
            raise
        existing = _read(s3, bucket, key)
        if existing is None or existing != body:
            raise
        return False


def _file_hash(path: Path) -> tuple[int, str]:
    size = 0
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(_CHUNK), b""):
            size += len(block)
            digest.update(block)
    return size, digest.hexdigest()


def _records(root: Path, manifest: dict) -> list[tuple[dict, Path, str]]:
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("manifest.files must be a non-empty list")
    root = root.resolve()
    result = []
    seen = set()
    for record in files:
        if not isinstance(record, dict):
            raise ValueError("manifest contains an invalid file record")
        relative = record.get("path")
        size, checksum = record.get("bytes"), record.get("sha256")
        if (not isinstance(relative, str) or not relative or "\\" in relative
                or not isinstance(size, int) or isinstance(size, bool) or size < 0
                or not isinstance(checksum, str) or not _SHA256.fullmatch(checksum)):
            raise ValueError("manifest contains an invalid file record")
        posix = PurePosixPath(relative)
        if posix.is_absolute() or any(part in ("", ".", "..") for part in posix.parts):
            raise ValueError(f"invalid relative file path: {relative}")
        normalized = posix.as_posix()
        if normalized != relative:
            raise ValueError(f"file path must be normalized POSIX: {relative}")
        if normalized in seen:
            raise ValueError(f"duplicate file path: {relative}")
        seen.add(normalized)
        untrusted_path = root / Path(*posix.parts)
        for parent in [root, *untrusted_path.parents]:
            if parent != root and parent.is_symlink():
                raise ValueError(f"source file path contains a symlink: {relative}")
        if untrusted_path.is_symlink():
            raise ValueError(f"source file is missing or symlinked: {relative}")
        path = untrusted_path.resolve()
        try:
            path.relative_to(root)
        except ValueError as error:
            raise ValueError(f"file escapes root: {relative}") from error
        if not path.is_file():
            raise ValueError(f"source file is missing or symlinked: {relative}")
        if size > _MAX_SINGLE_PUT:
            raise ValueError(f"files over 5 GiB require unsupported multipart upload: {relative}")
        result.append((record, path, normalized))
    return result


def _verify_local(entries: list[tuple[dict, Path, str]]) -> None:
    for record, path, relative in entries:
        size, checksum = _file_hash(path)
        if size != record["bytes"] or checksum != record["sha256"]:
            raise ValueError(f"source changed or does not match manifest: {relative}")


def _verify_remote(s3, bucket: str, key: str, expected_size: int, expected_hash: str) -> None:
    try:
        result = s3.get_object(Bucket=bucket, Key=key)
    except Exception as error:
        if _missing(error):
            raise ValueError(f"remote object is missing: {key}") from error
        raise
    body = result["Body"]
    size = 0
    digest = hashlib.sha256()
    try:
        for block in iter(lambda: body.read(_CHUNK), b""):
            size += len(block)
            digest.update(block)
    finally:
        close = getattr(body, "close", None)
        if close:
            close()
    if size != expected_size or digest.hexdigest() != expected_hash:
        raise ValueError(f"remote object verification failed: {key}")


def _verify_remote_if_present(s3, bucket: str, key: str, expected_size: int,
                              expected_hash: str) -> bool:
    try:
        result = s3.get_object(Bucket=bucket, Key=key)
    except Exception as error:
        if _missing(error):
            return False
        raise
    body = result["Body"]
    size = 0
    digest = hashlib.sha256()
    try:
        for block in iter(lambda: body.read(_CHUNK), b""):
            size += len(block)
            digest.update(block)
    finally:
        close = getattr(body, "close", None)
        if close:
            close()
    if size != expected_size or digest.hexdigest() != expected_hash:
        raise ValueError(f"remote object verification failed: {key}")
    return True


def publish(s3, *, bucket: str, prefix: str, root: Path, manifest: dict,
            failpoint: str | None = None,
            before_commit: Callable[[], None] | None = None) -> dict:
    """Publish one immutable, verified download run under ``prefix``.

    ``manifest`` is the complete input contract.  Its canonical bytes are
    locked in ``_INPUT.json`` before source files are uploaded.
    """
    if not isinstance(manifest, dict) or not isinstance(manifest.get("run_id"), str):
        raise ValueError("manifest.run_id is required")
    if not isinstance(prefix, str) or not prefix or prefix.endswith("/"):
        raise ValueError("prefix must be a non-empty S3 prefix without a trailing slash")
    entries = _records(Path(root), manifest)
    manifest_body = _json_bytes(manifest)
    manifest_hash = hashlib.sha256(manifest_body).hexdigest()
    input_body = _json_bytes({"manifest_sha256": manifest_hash})
    input_key = prefix + "/_INPUT.json"
    success_key = prefix + "/_SUCCESS"
    run_manifest_key = prefix + "/run_manifest.json"

    existing_success = _read(s3, bucket, success_key)
    if existing_success is not None:
        existing_input = _read(s3, bucket, input_key)
        if existing_input is None:
            raise ValueError("completed run is missing _INPUT.json")
        if existing_input != input_body:
            raise ValueError("run prefix is already bound to a different input manifest")
        if existing_success != (manifest_hash + "\n").encode("ascii"):
            raise ValueError("existing completion marker differs")
        remote_manifest = _read(s3, bucket, run_manifest_key)
        if remote_manifest != manifest_body:
            raise ValueError("completed run manifest is missing or differs")
        _verify_local(entries)
        for record, _, relative in entries:
            _verify_remote(s3, bucket, f"{prefix}/data/{relative}",
                           record["bytes"], record["sha256"])
        if before_commit:
            before_commit()
        return {"status": "REVERIFIED", "action": "REVERIFIED", "run_id": manifest["run_id"],
                "prefix": prefix, "manifest_sha256": manifest_hash,
                "file_count": len(entries), "bytes": sum(r["bytes"] for r, _, _ in entries)}

    existing_input = _read(s3, bucket, input_key)
    if existing_input is not None and existing_input != input_body:
        raise ValueError("run prefix is already bound to a different input manifest")
    _same_or_put(s3, bucket, input_key, input_body)

    _verify_local(entries)
    for record, path, relative in entries:
        key = f"{prefix}/data/{relative}"
        if _verify_remote_if_present(s3, bucket, key, record["bytes"], record["sha256"]):
            continue
        with path.open("rb") as stream:
            try:
                s3.put_object(Bucket=bucket, Key=key, Body=stream, IfNoneMatch="*")
            except Exception as error:
                # A simultaneous identical publisher may win the conditional PUT.
                if (not isinstance(error, ClientError)
                        or str(error.response.get("Error", {}).get("Code", "")) not in {
                            "412", "PreconditionFailed"}):
                    raise
                _verify_remote(s3, bucket, key, record["bytes"], record["sha256"])
        _verify_remote(s3, bucket, key, record["bytes"], record["sha256"])
    _verify_local(entries)
    if failpoint == "after_files":
        raise RuntimeError("failpoint: after_files")

    _same_or_put(s3, bucket, run_manifest_key, manifest_body)
    if before_commit:
        before_commit()
        _verify_local(entries)
    if failpoint == "before_success":
        raise RuntimeError("failpoint: before_success")
    _same_or_put(s3, bucket, success_key, (manifest_hash + "\n").encode("ascii"))
    return {"status": "PUBLISHED", "action": "LOADED", "run_id": manifest["run_id"],
            "prefix": prefix, "manifest_sha256": manifest_hash,
            "file_count": len(entries), "bytes": sum(r["bytes"] for r, _, _ in entries)}
