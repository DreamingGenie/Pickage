"""Immutable MinIO/S3 storage helpers for the Curated pipeline."""

from __future__ import annotations

from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import uuid

from botocore.exceptions import ClientError


_CHUNK = 1024 * 1024
_MAX_SINGLE_PUT = 5 * 1024 * 1024 * 1024
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def json_bytes(value) -> bytes:
    """Serialize JSON deterministically for manifests, locks, and CAS."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _not_found(error: Exception) -> bool:
    if not isinstance(error, ClientError):
        return False
    code = str(error.response.get("Error", {}).get("Code", ""))
    return code in {"404", "NoSuchKey", "NotFound"}


def _etag(value) -> str | None:
    if value is None:
        return None
    value = value.decode() if isinstance(value, bytes) else str(value)
    return value.strip('"')


def read_optional(s3, bucket, key):
    """Read an object, returning ``None`` only for a missing object."""
    try:
        result = s3.get_object(Bucket=bucket, Key=key)
    except Exception as error:
        if _not_found(error):
            return None
        raise
    body = result["Body"]
    try:
        return body.read(), _etag(result.get("ETag"))
    finally:
        close = getattr(body, "close", None)
        if close:
            close()


def put_immutable(s3, bucket, key, body: bytes) -> None:
    """Put once; an existing object is accepted only when bytes are identical."""
    if not isinstance(body, bytes):
        raise TypeError("body must be bytes")
    if len(body) > _MAX_SINGLE_PUT:
        raise ValueError("immutable single PUT is limited to 5 GiB")
    existing = read_optional(s3, bucket, key)
    if existing is not None:
        if existing[0] != body:
            raise ValueError("Existing object differs")
        return
    try:
        s3.put_object(Bucket=bucket, Key=key, Body=body, IfNoneMatch="*")
    except Exception:
        # A concurrent creator may have won the race. Accept only an exact
        # byte-for-byte match; all other failures remain failures.
        existing = read_optional(s3, bucket, key)
        if existing is None or existing[0] != body:
            raise


def _record(record):
    try:
        key, size, checksum = record["key"], int(record["bytes"]), record["sha256"]
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Invalid object record") from error
    if not isinstance(key, str) or not key or "\x00" in key:
        raise ValueError("Invalid object key")
    if size < 0 or not isinstance(checksum, str) or not _SHA256.fullmatch(checksum):
        raise ValueError("Invalid object record")
    return key, size, checksum


def _hash_file(path: Path):
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(_CHUNK), b""):
            digest.update(block)
            size += len(block)
    return size, digest.hexdigest()


def _download_one(s3, bucket, record, cache_dir: Path) -> Path:
    key, expected_size, expected_hash = _record(record)
    target = cache_dir / (expected_hash + ".parquet")
    if target.exists():
        local_size, local_hash = _hash_file(target)
        try:
            remote = s3.head_object(Bucket=bucket, Key=key)
        except Exception:
            raise
        remote_size = int(remote.get("ContentLength", -1))
        if local_size == expected_size == remote_size and local_hash == expected_hash:
            return target
        try:
            target.unlink()
        except FileNotFoundError:
            pass

    cache_dir.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".download-", suffix=".tmp", dir=cache_dir)
    os.close(fd)
    temporary_path = Path(temporary)
    digest = hashlib.sha256()
    size = 0
    try:
        result = s3.get_object(Bucket=bucket, Key=key)
        body = result["Body"]
        with temporary_path.open("wb") as stream:
            for block in iter(lambda: body.read(_CHUNK), b""):
                digest.update(block)
                size += len(block)
                stream.write(block)
        close = getattr(body, "close", None)
        if close:
            close()
        if size != expected_size or digest.hexdigest() != expected_hash:
            raise ValueError("Downloaded object verification failed")
        os.replace(temporary_path, target)
        return target
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


def download_files(s3, bucket, records, cache_dir, workers=4) -> list[Path]:
    records = list(records)
    if not 1 <= workers <= 64:
        raise ValueError("workers must be between 1 and 64")
    cache_dir = Path(cache_dir).resolve()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_download_one, s3, bucket, record, cache_dir)
                   for record in records]
        return [future.result() for future in futures]


def _verify_remote(s3, bucket, key, expected_size, expected_hash):
    result = s3.get_object(Bucket=bucket, Key=key)
    body = result["Body"]
    digest = hashlib.sha256()
    size = 0
    try:
        for block in iter(lambda: body.read(_CHUNK), b""):
            digest.update(block)
            size += len(block)
    finally:
        close = getattr(body, "close", None)
        if close:
            close()
    if size != expected_size or digest.hexdigest() != expected_hash:
        raise ValueError("Remote object verification failed")


def verify_files(s3, bucket, records, workers=4):
    records = list(records)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(lambda r: (_verify_remote(s3, bucket, *_record(r)), r)[1], record)
                   for record in records]
        return [future.result() for future in futures]


def _upload_one(s3, bucket, prefix: str, directory: Path, path: Path):
    relative = path.resolve().relative_to(directory)
    key = "/".join(part for part in (prefix.strip("/"), *relative.parts) if part)
    body = path.read_bytes()
    size = len(body)
    checksum = hashlib.sha256(body).hexdigest()
    if size > _MAX_SINGLE_PUT:
        raise ValueError("Curated output exceeds single PUT limit")
    put_immutable(s3, bucket, key, body)
    _verify_remote(s3, bucket, key, size, checksum)
    return {"key": key, "bytes": size, "sha256": checksum}


def upload_outputs(s3, bucket, prefix, directory, workers=4):
    directory = Path(directory).resolve()
    if not directory.is_dir():
        raise ValueError("Output directory does not exist")
    files = sorted(path for path in directory.rglob("*") if path.is_file())
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_upload_one, s3, bucket, prefix, directory, path)
                   for path in files]
        return [future.result() for future in futures]


@contextmanager
def writer_lock(s3, bucket, key, owner):
    """Acquire an immutable lock and release it only while still owning it."""
    token = uuid.uuid4().hex
    body = json_bytes({"owner": owner, "token": token})
    try:
        s3.put_object(Bucket=bucket, Key=key, Body=body, IfNoneMatch="*")
    except Exception as error:
        raise ValueError("Writer lock is already held or unavailable") from error
    try:
        yield
    finally:
        current = read_optional(s3, bucket, key)
        if current is None or current[0] != body:
            raise RuntimeError("Writer lock ownership was lost")
        try:
            s3.delete_object(Bucket=bucket, Key=key, IfMatch=current[1])
        except Exception as error:
            raise RuntimeError("Writer lock release failed") from error


def compare_and_swap_json(s3, bucket, key, value, previous_etag: str | None = None):
    body = json_bytes(value)
    kwargs = {"Bucket": bucket, "Key": key, "Body": body}
    if previous_etag is None:
        kwargs["IfNoneMatch"] = "*"
    else:
        kwargs["IfMatch"] = previous_etag.strip('"')
    result = s3.put_object(**kwargs)
    return _etag(result.get("ETag"))


__all__ = ["json_bytes", "read_optional", "put_immutable", "download_files",
           "verify_files", "upload_outputs", "writer_lock", "compare_and_swap_json"]
