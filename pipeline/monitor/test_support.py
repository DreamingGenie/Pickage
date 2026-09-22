"""시험용 가짜 — 메모리 dict 하나짜리 S3 와 Docker.

`pipeline/weekly/test_state.py` 의 FakeS3 와 같은 태도다. 실제 서비스 없이 도는 층은
여기서, 실제 MinIO·Docker 가 있어야 보이는 것(권한·소켓)은 로컬 리허설에서 본다.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone


class _Body:
    def __init__(self, data: bytes): self.data = data
    def read(self): return self.data
    def __enter__(self): return self
    def __exit__(self, *_): return False


class NotFound(Exception):
    response = {"Error": {"Code": "NoSuchKey"}, "ResponseMetadata": {"HTTPStatusCode": 404}}


class FakeS3:
    """objects[(bucket, key)] = (bytes, modified)."""

    def __init__(self, page_size: int = 1000):
        self.objects: dict[tuple[str, str], tuple[bytes, datetime]] = {}
        self.page_size = page_size
        self.list_calls = 0
        self.puts: list[tuple[str, str]] = []

    def add(self, bucket: str, key: str, body=b"", modified: datetime | None = None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.objects[(bucket, key)] = (body, modified or datetime(2026, 9, 20, tzinfo=timezone.utc))

    def list_buckets(self):
        names = sorted({b for b, _ in self.objects})
        return {"Buckets": [{"Name": n} for n in names]}

    def get_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise NotFound()
        body, modified = self.objects[(Bucket, Key)]
        return {"Body": _Body(body), "LastModified": modified}

    def put_object(self, Bucket, Key, Body, ContentType=None):
        self.puts.append((Bucket, Key))
        self.objects[(Bucket, Key)] = (Body, datetime.now(timezone.utc))

    def list_objects_v2(self, Bucket, Prefix="", Delimiter=None, ContinuationToken=None):
        self.list_calls += 1
        keys = sorted(k for b, k in self.objects if b == Bucket and k.startswith(Prefix))
        prefixes, contents = [], []
        seen = set()
        for key in keys:
            rest = key[len(Prefix):]
            if Delimiter and Delimiter in rest:
                folded = Prefix + rest.split(Delimiter, 1)[0] + Delimiter
                if folded not in seen:
                    seen.add(folded)
                    prefixes.append({"Prefix": folded})
            else:
                body, modified = self.objects[(Bucket, key)]
                contents.append({"Key": key, "Size": len(body), "LastModified": modified})
        start = int(ContinuationToken or 0)
        page = contents[start:start + self.page_size]
        truncated = start + self.page_size < len(contents)
        out = {"CommonPrefixes": prefixes, "Contents": page, "IsTruncated": truncated}
        if truncated:
            out["NextContinuationToken"] = str(start + self.page_size)
        return out


class FakeDocker:
    def __init__(self, containers: list[dict], details: dict[str, dict], logs: dict[str, list[str]]):
        self._containers = containers
        self._details = details
        self._logs = logs
        self.log_calls: list[dict] = []

    def containers(self):
        return self._containers

    def inspect(self, container_id):
        return self._details[container_id]

    def logs(self, container_id, *, tail, since, tty):
        self.log_calls.append({"id": container_id, "tail": tail, "since": since, "tty": tty})
        if container_id in self._logs:
            return self._logs[container_id]
        raise RuntimeError("no logs")
