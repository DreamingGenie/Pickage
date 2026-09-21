"""MinIO 버킷 이벤트 구독 — "방금 무엇이 올라왔나" 를 목록 조회 없이 안다.

MinIO 의 ListenBucketNotification(확장 API)로 버킷마다 연결 하나를 열어 두면, 객체가
생기거나 지워질 때 그 연결로 JSON 이 한 줄씩 흘러온다. 여기서는 그것을 메모리에
**retention_hours(기본 24시간)** 동안 들고 있다가 보고서에 싣는다.

⚠ **구독한 뒤의 것만 온다.** 서버가 켜지기 전이나 연결이 끊긴 사이의 것은 다시 받을 수
  없다(듣기 방식에는 재전송이 없다). 그래서 끊긴 구간(gap)을 기록해 화면이 "이 사이는
  모른다" 고 말하게 한다. 그 전 상태는 전체 목록 조회(s3inv.collect, 버튼)가 답한다.

연결·재연결은 스레드 하나가 버킷마다 맡는다. 붙는 데 실패하면 5초 → 60초로 늘려 가며
다시 붙는다. 어느 버킷에 붙어 있는지·마지막 이벤트가 언제였는지가 보고서에 남는다.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote_plus

from . import s3inv

CREATED = "s3:ObjectCreated:"
REMOVED = "s3:ObjectRemoved:"
SUBSCRIBE = ("s3:ObjectCreated:*", "s3:ObjectRemoved:*")


def _iso(moment: datetime | None) -> str | None:
    return None if moment is None else moment.astimezone(timezone.utc).isoformat(timespec="seconds")


def parse_record(record: dict) -> dict | None:
    """MinIO 알림 레코드 하나 → 우리가 쓰는 평평한 dict. 모양이 다르면 None."""
    try:
        s3 = record["s3"]
        key = unquote_plus(s3["object"]["key"])   # 알림의 키는 URL 인코딩돼 온다 (공백이 + 로)
        bucket = s3["bucket"]["name"]
        name = record.get("eventName", "")
        moment = record.get("eventTime")
        when = datetime.fromisoformat(moment.replace("Z", "+00:00")) if moment else datetime.now(timezone.utc)
    except (KeyError, TypeError, ValueError):
        return None
    return {
        "time": when.astimezone(timezone.utc),
        "bucket": bucket,
        "key": key,
        "size": int(s3["object"].get("size") or 0),
        "event": name,
        "created": name.startswith(CREATED),
        "removed": name.startswith(REMOVED),
        "principal": (record.get("userIdentity") or {}).get("principalId"),
        "source": (record.get("source") or {}).get("host"),
    }


class EventStore:
    """스레드 안전한 고리 버퍼 + 연결 상태. snapshot() 이 보고서 조각을 만든다."""

    def __init__(self, *, retention_hours: int = 24, max_events: int = 20_000, depth: int = 3,
                 depth_overrides: dict[str, int] | None = None, clock=None):
        self.retention = timedelta(hours=retention_hours)
        self.max_events = max_events
        self.depth = depth
        self.depth_overrides = depth_overrides or {}
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.lock = threading.Lock()
        self.events: deque[dict] = deque(maxlen=max_events)
        self.started_at = self.clock()
        self.buckets: dict[str, dict] = {}     # name → {connected, since, last_event, error, reconnects}
        self.gaps: list[dict] = []             # {bucket, from, to, error}
        # 버킷 목록을 아직 못 받았는가 (start_listeners_when_ready). pending 이면 구독은 하나도 없다.
        self.discovery: dict = {"pending": False, "error": None, "attempts": 0}

    # ── 버킷 목록 (구독 전 단계) ─────────────────────────────────
    def mark_discovery(self, *, pending: bool, error: str | None = None, attempts: int = 0) -> None:
        with self.lock:
            self.discovery = {"pending": pending, "error": error[:300] if error else None, "attempts": attempts}

    # ── 연결 상태 ───────────────────────────────────────────────
    def bucket_state(self, bucket: str) -> dict:
        return self.buckets.setdefault(bucket, {"connected": False, "since": None, "last_event": None,
                                                "error": None, "reconnects": -1, "events": 0})

    def mark_connected(self, bucket: str) -> None:
        with self.lock:
            state = self.bucket_state(bucket)
            state.update(connected=True, since=self.clock(), error=None)
            state["reconnects"] += 1
            for gap in self.gaps:
                if gap["bucket"] == bucket and gap["to"] is None:
                    gap["to"] = self.clock()

    def mark_disconnected(self, bucket: str, error: str) -> None:
        with self.lock:
            state = self.bucket_state(bucket)
            was = state["connected"]
            state.update(connected=False, error=error[:300])
            if was or not any(g["bucket"] == bucket and g["to"] is None for g in self.gaps):
                self.gaps.append({"bucket": bucket, "from": self.clock(), "to": None, "error": error[:300]})
                del self.gaps[:-200]

    # ── 이벤트 ──────────────────────────────────────────────────
    def add(self, event: dict) -> None:
        with self.lock:
            self.events.append(event)
            state = self.bucket_state(event["bucket"])
            state["last_event"] = event["time"]
            state["events"] += 1

    def _prune(self, now: datetime) -> None:
        cutoff = now - self.retention
        while self.events and self.events[0]["time"] < cutoff:
            self.events.popleft()

    # ── 보고서 조각 ─────────────────────────────────────────────
    def snapshot(self, *, recent: int = 200, recent_per_prefix: int = 10) -> dict:
        now = self.clock()
        with self.lock:
            self._prune(now)
            events = list(self.events)
            buckets = {name: dict(state) for name, state in self.buckets.items()}
            gaps = [dict(g) for g in self.gaps]
            discovery = dict(self.discovery)
        created = [e for e in events if e["created"]]
        # 경로별 집계 — 목록 조회의 prefixes 표와 같은 깊이 규칙이라 같은 눈으로 읽힌다.
        prefixes: dict[tuple[str, str], dict] = {}
        for e in created:
            depth = self.depth_overrides.get(e["bucket"], self.depth)
            key = (e["bucket"], s3inv.prefix_of(e["key"], depth))
            row = prefixes.setdefault(key, {"bucket": e["bucket"], "prefix": key[1], "objects": 0, "bytes": 0,
                                            "latest": None, "recent": []})
            row["objects"] += 1
            row["bytes"] += e["size"]
            if row["latest"] is None or e["time"] > row["latest"]:
                row["latest"] = e["time"]
            row["recent"].append(e)
        prefix_rows = []
        for row in sorted(prefixes.values(), key=lambda r: r["latest"], reverse=True):
            rec = sorted(row["recent"], key=lambda e: e["time"], reverse=True)[:recent_per_prefix]
            prefix_rows.append({**row, "latest": _iso(row["latest"]),
                                "recent": [self._public(e) for e in rec]})
        completed = [self._public(e) for e in sorted(created, key=lambda e: e["time"], reverse=True)
                     if e["key"] == s3inv.SUCCESS or e["key"].endswith("/" + s3inv.SUCCESS)]
        for row in completed:
            row["prefix"] = row["key"][:-len(s3inv.SUCCESS)].rstrip("/") or "(root)"
        latest = sorted(events, key=lambda e: e["time"], reverse=True)[:recent]
        return {
            "listening_since": _iso(self.started_at),
            "retention_hours": int(self.retention.total_seconds() // 3600),
            "held": len(events),
            "max_events": self.max_events,
            "discovery": discovery,
            "buckets": {name: {"connected": s["connected"], "since": _iso(s["since"]),
                               "last_event": _iso(s["last_event"]), "error": s["error"],
                               "reconnects": max(0, s["reconnects"]), "events": s["events"]}
                        for name, s in sorted(buckets.items())},
            "gaps": [{"bucket": g["bucket"], "from": _iso(g["from"]), "to": _iso(g["to"]), "error": g["error"]}
                     for g in gaps[-50:]],
            "recent": [self._public(e) for e in latest],
            "completed": completed[:200],
            "prefixes": prefix_rows,
            "totals": {"created": len(created), "removed": sum(1 for e in events if e["removed"]),
                       "bytes": sum(e["size"] for e in created)},
        }

    @staticmethod
    def _public(e: dict) -> dict:
        return {"time": _iso(e["time"]), "bucket": e["bucket"], "key": e["key"], "size": e["size"],
                "event": e["event"], "principal": e["principal"], "source": e["source"]}


def listen_forever(store: EventStore, bucket: str, *, open_stream, stop: threading.Event, log=print,
                   backoff_max: float = 60.0) -> None:
    """버킷 하나를 끝까지 듣는다. open_stream(bucket) 은 레코드 dict 를 내는 이터레이터를 준다.

    끊기면 gap 을 남기고 backoff 뒤 다시 붙는다. stop 이 서면 나온다.
    """
    backoff = min(5.0, backoff_max)
    while not stop.is_set():
        try:
            stream = open_stream(bucket)
            store.mark_connected(bucket)
            log(f"[events] {bucket} 구독 시작")
            backoff = min(5.0, backoff_max)
            for record in stream:
                if stop.is_set():
                    return
                event = parse_record(record)
                if event is not None:
                    store.add(event)
            raise ConnectionError("스트림이 끝났다")
        except Exception as error:   # 네트워크·인증·MinIO 재시작 전부 여기로. 죽지 않고 다시 붙는다
            if stop.is_set():
                return
            store.mark_disconnected(bucket, f"{type(error).__name__}: {error}")
            log(f"[events] {bucket} 끊김: {type(error).__name__}: {error} — {backoff:.0f}초 뒤 재시도")
            if stop.wait(backoff):
                return
            backoff = min(backoff * 2, backoff_max)


def minio_stream_opener(endpoint: str, access_key: str, secret_key: str):
    """minio SDK 로 ListenBucketNotification 을 연다. boto3 에는 이 확장 API 가 없다."""
    from urllib.parse import urlsplit

    from minio import Minio
    parts = urlsplit(endpoint)
    client = Minio(parts.netloc, access_key=access_key, secret_key=secret_key,
                   secure=parts.scheme == "https")

    def open_stream(bucket: str):
        def records():
            with client.listen_bucket_notification(bucket, events=SUBSCRIBE) as stream:
                for message in stream:
                    for record in (message or {}).get("Records") or []:
                        yield record
        return records()
    return open_stream


def _spawn(store: EventStore, buckets: list[str], *, open_stream, stop: threading.Event, log) -> None:
    for bucket in buckets:
        threading.Thread(target=listen_forever, args=(store, bucket),
                         kwargs={"open_stream": open_stream, "stop": stop, "log": log},
                         name=f"events-{bucket}", daemon=True).start()


def start_listeners(store: EventStore, buckets: list[str], *, open_stream, log=print) -> threading.Event:
    """버킷 목록이 이미 손에 있을 때. 목록을 MinIO 에 물어야 하면 start_listeners_when_ready."""
    stop = threading.Event()
    _spawn(store, buckets, open_stream=open_stream, stop=stop, log=log)
    return stop


def start_listeners_when_ready(store: EventStore, resolve_buckets, *, open_stream, log=print,
                               backoff_max: float = 60.0) -> threading.Event:
    """버킷 목록을 받을 수 있을 때까지 재시도한 뒤 구독을 건다.

    모니터링 스택과 운영 스택은 별개 compose 라 노드 재부팅 때 어느 쪽이 먼저 뜨는지 정해져
    있지 않다. MinIO 가 늦으면 시작 시점의 list_buckets 한 번은 실패하고, 그 자리에서 포기하면
    프로세스는 살아 있는데 구독은 영원히 없다 — restart 정책도 못 구한다. 그래서 스레드가
    5→60초 backoff 로 목록을 다시 청하고, 받으면 그때 버킷마다 리스너를 띄운다.
    기다리는 동안은 store.discovery 가 pending 이라 보고서가 "아직 구독 전" 이라고 말한다.
    """
    stop = threading.Event()

    def resolve_then_listen():
        backoff = min(5.0, backoff_max)
        attempts = 0
        while not stop.is_set():
            attempts += 1
            try:
                buckets = list(resolve_buckets())
            except Exception as error:   # MinIO 미기동·인증·네트워크 전부. 포기하지 않고 다시 묻는다
                message = f"{type(error).__name__}: {error}"
                store.mark_discovery(pending=True, error=message, attempts=attempts)
                log(f"[events] 버킷 목록을 못 받아 구독을 못 건다 ({attempts}회): {message} — {backoff:.0f}초 뒤 재시도")
                if stop.wait(backoff):
                    return
                backoff = min(backoff * 2, backoff_max)
                continue
            store.mark_discovery(pending=False, error=None, attempts=attempts)
            if not buckets:
                log("[events] 버킷 목록이 비어 있다 — 구독할 것이 없다 (계정이 보는 버킷이 없는가)")
            _spawn(store, buckets, open_stream=open_stream, stop=stop, log=log)
            return

    store.mark_discovery(pending=True, attempts=0)
    threading.Thread(target=resolve_then_listen, name="events-discover", daemon=True).start()
    return stop
