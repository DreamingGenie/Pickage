"""MinIO 목록 집계 — 버킷·경로별로 무엇이 얼마나 있고, 최근에 무엇이 생겼는가.

MinIO 의 Prometheus 메트릭은 **버킷 단위**까지만 준다. "어느 스냅샷·어느 run 에 새 파일이
들어왔나" 는 목록을 직접 훑어야 안다. 그래서 주기마다 버킷 전체를 LIST 한다 —
객체 1,000개당 요청 하나이고, 지금 규모(수만 객체)에서 몇 초다. `max_objects` 를 넘기면
거기서 멈추고 `truncated` 를 켠다 — 조용히 절반만 세고 정상인 척하지 않는다.

**`_SUCCESS` 가 곧 "데이터셋 실행 하나가 끝났다" 는 표시다.** 이 저장소의 입고기·빌더가
전부 마지막에 그 객체를 찍으므로(`pipeline/minio/README.md` 의 저장 경로 규칙),
그 객체들의 시각을 최신순으로 놓으면 "배치로 무엇이 생겼나" 의 답이 된다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

SUCCESS = "_SUCCESS"
POINTER = "_current.json"


@dataclass(frozen=True)
class Obj:
    key: str
    size: int
    modified: datetime


def list_bucket(s3, bucket: str, *, max_objects: int) -> tuple[list[Obj], bool]:
    """버킷 전체. (객체들, 잘렸는가)."""
    found: list[Obj] = []
    token = None
    while True:
        request = {"Bucket": bucket}
        if token:
            request["ContinuationToken"] = token
        page = s3.list_objects_v2(**request)
        for item in page.get("Contents", []) or []:
            found.append(Obj(item["Key"], int(item.get("Size") or 0), _utc(item["LastModified"])))
            if len(found) >= max_objects:
                return found, True
        if not page.get("IsTruncated"):
            return found, False
        token = page.get("NextContinuationToken")


def _utc(moment) -> datetime:
    if isinstance(moment, str):
        moment = datetime.fromisoformat(moment.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _iso(moment: datetime | None) -> str | None:
    return None if moment is None else moment.isoformat(timespec="seconds")


def prefix_of(key: str, depth: int) -> str:
    """키의 디렉터리 부분에서 앞 depth 세그먼트. 파일이 루트에 있으면 "(root)"."""
    parts = key.split("/")[:-1]
    if not parts:
        return "(root)"
    return "/".join(parts[:depth])


class _Agg:
    __slots__ = ("objects", "bytes", "latest", "new_objects", "new_bytes", "week_objects", "week_bytes", "recent")

    def __init__(self):
        self.objects = 0
        self.bytes = 0
        self.latest = None
        self.new_objects = 0
        self.new_bytes = 0
        self.week_objects = 0
        self.week_bytes = 0
        self.recent: list[Obj] = []

    def add(self, obj: Obj, since: datetime, week_since: datetime):
        self.objects += 1
        self.bytes += obj.size
        if self.latest is None or obj.modified > self.latest:
            self.latest = obj.modified
        if obj.modified >= week_since:
            self.week_objects += 1
            self.week_bytes += obj.size
        if obj.modified >= since:
            self.new_objects += 1
            self.new_bytes += obj.size
            self.recent.append(obj)

    def row(self, recent_cap: int, window_hours: int) -> dict:
        recent = sorted(self.recent, key=lambda o: o.modified, reverse=True)[:recent_cap]
        return {
            "objects": self.objects, "bytes": self.bytes, "latest": _iso(self.latest),
            "new": {"window_hours": window_hours, "objects": self.new_objects, "bytes": self.new_bytes},
            "new_7d": {"objects": self.week_objects, "bytes": self.week_bytes},
            "recent": [{"key": o.key, "size": o.size, "modified": _iso(o.modified)} for o in recent],
        }


def aggregate(bucket: str, objects: list[Obj], *, depth: int, now: datetime,
              window_hours: int, recent_per_prefix: int, truncated: bool) -> dict:
    since = now - timedelta(hours=window_hours)
    week_since = now - timedelta(days=7)
    total = _Agg()
    prefixes: dict[str, _Agg] = {}
    for obj in objects:
        total.add(obj, since, week_since)
        prefixes.setdefault(prefix_of(obj.key, depth), _Agg()).add(obj, since, week_since)
    rows = []
    for name in sorted(prefixes):
        row = prefixes[name].row(recent_per_prefix, window_hours)
        row["prefix"] = name
        rows.append(row)
    summary = total.row(0, window_hours)
    summary.pop("recent")
    summary.update({"name": bucket, "depth": depth, "truncated": truncated, "prefixes": rows})
    return summary


def completed_runs(bucket: str, objects: list[Obj], *, limit: int = 200) -> list[dict]:
    """`_SUCCESS` 하나당 실행 하나. 그 아래 객체 수·바이트를 붙여 최신순으로."""
    marks = {}
    for obj in objects:
        if obj.key == SUCCESS or obj.key.endswith("/" + SUCCESS):
            marks[obj.key[:-len(SUCCESS)].rstrip("/")] = obj
    if not marks:
        return []
    stats = {prefix: [0, 0] for prefix in marks}
    for obj in objects:
        parts = obj.key.split("/")
        # 상위 디렉터리를 하나씩 올라가며 _SUCCESS 가 찍힌 곳을 찾는다. 깊이만큼만 본다 —
        # 객체 수 × 표시 수 를 다 대조하면 수십만 × 수백이 된다.
        for depth in range(len(parts) - 1, 0, -1):
            parent = "/".join(parts[:depth])
            if parent in stats:
                stats[parent][0] += 1
                stats[parent][1] += obj.size
                break
    rows = [{"bucket": bucket, "prefix": prefix or "(root)", "completed_at": _iso(mark.modified),
             "objects": stats[prefix][0], "bytes": stats[prefix][1]}
            for prefix, mark in marks.items()]
    rows.sort(key=lambda r: r["completed_at"], reverse=True)
    return rows[:limit]


def read_pointers(s3, specs: list[str]) -> list[dict]:
    """`bucket/key` 목록의 `_current.json` 류를 읽는다. 없는 것은 없다고 적는다."""
    rows = []
    for spec in specs:
        bucket, key = spec.split("/", 1)
        row = {"bucket": bucket, "key": key}
        try:
            response = s3.get_object(Bucket=bucket, Key=key)
            with response["Body"] as stream:
                body = stream.read().decode("utf-8")
            row["modified"] = _iso(_utc(response["LastModified"])) if response.get("LastModified") else None
            try:
                row["value"] = json.loads(body)
            except ValueError:
                row["value"] = None
                row["error"] = "JSON 이 아니다"
        except Exception as error:   # botocore 의 NoSuchKey 포함. 없는 포인터는 화면에 "없음" 으로
            row["missing"] = True
            row["error"] = _short(error)
        rows.append(row)
    return rows


def _short(error: Exception) -> str:
    response = getattr(error, "response", None)
    if isinstance(response, dict):
        code = response.get("Error", {}).get("Code")
        if code:
            return str(code)
    return f"{type(error).__name__}: {error}"[:200]


def collect(s3, *, buckets: list[str], depth: int, depth_overrides: dict[str, int],
            max_objects: int, now: datetime, window_hours: int, recent_per_prefix: int,
            pointers: list[str]) -> dict:
    if not buckets:
        buckets = sorted(b["Name"] for b in (s3.list_buckets().get("Buckets") or []))
    out_buckets = []
    runs = []
    errors = []
    for bucket in buckets:
        try:
            objects, truncated = list_bucket(s3, bucket, max_objects=max_objects)
        except Exception as error:
            errors.append({"bucket": bucket, "error": _short(error)})
            out_buckets.append({"name": bucket, "error": _short(error)})
            continue
        out_buckets.append(aggregate(bucket, objects, depth=depth_overrides.get(bucket, depth),
                                     now=now, window_hours=window_hours,
                                     recent_per_prefix=recent_per_prefix, truncated=truncated))
        runs.extend(completed_runs(bucket, objects))
    runs.sort(key=lambda r: r["completed_at"], reverse=True)
    return {
        "listed_at": _iso(now),
        "buckets": out_buckets,
        "completed_runs": runs[:200],
        "pointers": read_pointers(s3, pointers) if pointers else [],
        "errors": errors,
    }
