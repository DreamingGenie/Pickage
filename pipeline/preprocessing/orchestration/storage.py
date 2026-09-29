"""Run evidence and host locks, separate from immutable dataset publications."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import uuid

from pipeline.preprocessing.curated.storage import json_bytes, put_immutable, read_optional, verify_files

BUCKET = "pickage-curated"
PREFIX = "depsdev/v1/curated-bundle"


class WaitingInput(ValueError):
    """An explicit required object or producer completion marker has not arrived."""


class PipelineBusy(WaitingInput):
    """Retryable contention; no input or code contract has been violated."""


def sha(body):
    return hashlib.sha256(body).hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def required(s3, bucket, key):
    found = read_optional(s3, bucket, key)
    if found is None:
        raise WaitingInput(f"Required object has not arrived: {bucket}/{key}")
    return found[0]


def pinned(s3, ref):
    body = required(s3, ref["bucket"], ref["key"])
    if sha(body) != ref["sha256"]:
        raise ValueError("Pinned object SHA mismatch: " + ref["key"])
    return body


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex)
    try:
        with temporary.open("xb") as stream:
            stream.write(json_bytes(value))
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(4):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                # Windows virus/index scanners can briefly hold the old file.
                if os.name != "nt" or attempt == 3:
                    raise
                time.sleep(0.02 * (attempt + 1))
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def host_lock(s3, *, namespace="pipeline"):
    """OS-released lock for the documented one-host writer (including restarts).

    All work directories and run IDs share a lock. Do not delete the lock file:
    replacing its inode could allow two locks. Other hosts are unsupported.
    """
    endpoint = getattr(getattr(s3, "meta", None), "endpoint_url", "local-test")
    directory = Path(tempfile.gettempdir()) / "pickage-orchestration-locks"
    directory.mkdir(parents=True, exist_ok=True)
    identity = str(endpoint) if namespace == "pipeline" else str(endpoint) + "/" + namespace
    path = directory / (sha(identity.encode()) + ".lock")
    with path.open("a+b") as stream:
        if path.stat().st_size == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise PipelineBusy("Another Curated pipeline is active on this host") from error
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def verify_descriptor(s3, descriptor, *, workers=2):
    """Recheck the exact producer manifest, completion marker and every output."""
    bucket = descriptor["bucket"]
    body = required(s3, bucket, descriptor["manifest_key"])
    if sha(body) != descriptor["manifest_sha256"]:
        raise ValueError("Stage manifest changed: " + descriptor["manifest_key"])
    marker = required(s3, bucket, descriptor["marker_key"])
    if sha(marker) != descriptor["marker_sha256"]:
        raise ValueError("Stage completion marker changed")
    manifest = json.loads(body)
    if manifest.get("status") not in ("PASSED", "COMPLETE", "LOCAL_VALIDATED"):
        raise ValueError("Stage manifest is not approved")
    if not descriptor.get("files"):
        raise ValueError("Stage output inventory is empty")
    verify_files(s3, bucket, descriptor["files"], workers=workers)
    return manifest


def save_state(s3, prefix, local, state):
    """Local evidence first; mutable remote state is never a readiness marker."""
    state["updated_at"] = utc_now()
    atomic_json(Path(local) / "status.json", state)
    s3.put_object(Bucket=BUCKET, Key=prefix + "/status.json", Body=json_bytes(state))


def save_event(s3, prefix, local, event):
    event = {**event, "at": utc_now(), "event_id": uuid.uuid4().hex}
    name = event["event_id"] + ".json"
    atomic_json(Path(local) / "events" / name, event)
    put_immutable(s3, BUCKET, prefix + "/events/" + name, json_bytes(event))


class StageClient:
    """Record this run's native lock tokens before conditional acquisition.

    With the host OS lock held, a restart can release only the exact abandoned
    tokens belonging to this run. Foreign locks are never removed.
    """
    def __init__(self, s3, local, request):
        self.s3, self.local = s3, Path(local)
        self.run_id = request["run_id"]
        self.allowed = {"depsdev/v1/package-version/_writer.lock",
            f"depsdev/v1/repository-metrics/snapshot={request['snapshot']}/run_id={request['run_id']}/_writer.lock"}

    def __getattr__(self, name):
        return getattr(self.s3, name)

    def put_object(self, **kwargs):
        if kwargs.get("Bucket") == BUCKET and kwargs.get("Key") in self.allowed:
            if kwargs.get("IfNoneMatch") != "*":
                raise ValueError("Native writer lock must be conditionally acquired")
            body = kwargs["Body"]
            if not isinstance(body, bytes):
                raise ValueError("Native lock body must be bytes")
            value = {"key": kwargs["Key"], "body": body.decode("utf-8")}
            atomic_json(self.local / "lock-ownership" / (sha(body) + ".json"), value)
        return self.s3.put_object(**kwargs)

    def recover(self):
        released = []
        for path in sorted((self.local / "lock-ownership").glob("*.json")):
            value = json.loads(path.read_bytes())
            if value["key"] not in self.allowed:
                raise ValueError("Saved lock ownership is outside this run")
            found = read_optional(self.s3, BUCKET, value["key"])
            if found is not None and found[0] == value["body"].encode("utf-8"):
                self.s3.delete_object(Bucket=BUCKET, Key=value["key"], IfMatch=found[1])
                released.append(value["key"])
        local_marker = self.local / "repository-local-lock-owner.json"
        if local_marker.exists():
            if json.loads(local_marker.read_bytes()) != {"run_id": self.run_id}:
                raise ValueError("Local writer lock owner differs from this run")
            expected = self.local / "repository" / self.run_id / ".writer.lock"
            if not expected.resolve().is_relative_to(self.local.resolve()):
                raise ValueError("Local writer lock escapes run workspace")
            expected.unlink(missing_ok=True)
        return released
