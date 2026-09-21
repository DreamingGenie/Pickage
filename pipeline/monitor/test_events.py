import threading
import unittest
from datetime import datetime, timedelta, timezone

from . import events

T0 = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def record(key, *, size=10, when=T0, name="s3:ObjectCreated:Put", bucket="pickage-raw"):
    return {"eventName": name, "eventTime": when.isoformat().replace("+00:00", "Z"),
            "s3": {"bucket": {"name": bucket}, "object": {"key": key, "size": size}},
            "userIdentity": {"principalId": "pickage-ingest"}, "source": {"host": "172.26.8.249"}}


class Clock:
    def __init__(self, now=T0): self.now = now
    def __call__(self): return self.now


class ParseTest(unittest.TestCase):
    def test_decodes_key_and_flags(self):
        e = events.parse_record(record("a/b+c/part%2D1.parquet"))
        self.assertEqual(e["key"], "a/b c/part-1.parquet")
        self.assertTrue(e["created"]); self.assertFalse(e["removed"])
        self.assertEqual(e["principal"], "pickage-ingest")

    def test_garbage_is_none(self):
        self.assertIsNone(events.parse_record({"eventName": "x"}))


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.store = events.EventStore(retention_hours=24, max_events=5, depth=3,
                                       depth_overrides={"pickage-raw": 4}, clock=self.clock)

    def add(self, key, **kw):
        self.store.add(events.parse_record(record(key, **kw)))

    def test_prefix_aggregation_and_completed(self):
        run = "depsdev/v1/projects/snapshot=2026-09-21/run_id=r"
        self.add(f"{run}/data/p0.parquet", size=100, when=T0 - timedelta(minutes=3))
        self.add(f"{run}/data/p1.parquet", size=200, when=T0 - timedelta(minutes=2))
        self.add(f"{run}/_SUCCESS", size=0, when=T0 - timedelta(minutes=1))
        snap = self.store.snapshot()
        self.assertEqual(snap["totals"], {"created": 3, "removed": 0, "bytes": 300})
        self.assertEqual(snap["prefixes"][0]["prefix"], "depsdev/v1/projects/snapshot=2026-09-21")
        self.assertEqual(snap["prefixes"][0]["objects"], 3)
        self.assertEqual(snap["recent"][0]["key"], f"{run}/_SUCCESS")      # 최신이 먼저
        self.assertEqual(snap["completed"][0]["prefix"], run)

    def test_retention_prunes_old_and_ring_caps(self):
        self.add("old", when=T0 - timedelta(hours=25))
        for i in range(6):
            self.add(f"k{i}", when=T0 - timedelta(minutes=6 - i))
        snap = self.store.snapshot()
        self.assertEqual(snap["held"], 5)                                   # maxlen 5 — old 는 밀려났다
        self.assertNotIn("old", [e["key"] for e in snap["recent"]])

    def test_connection_state_and_gaps(self):
        self.store.mark_disconnected("pickage-raw", "refused")
        self.clock.now = T0 + timedelta(seconds=30)
        self.store.mark_connected("pickage-raw")
        snap = self.store.snapshot()
        self.assertTrue(snap["buckets"]["pickage-raw"]["connected"])
        self.assertEqual(snap["buckets"]["pickage-raw"]["reconnects"], 0)   # 첫 연결은 재연결로 안 센다
        self.assertEqual(snap["gaps"][0]["from"], "2026-09-21T12:00:00+00:00")
        self.assertEqual(snap["gaps"][0]["to"], "2026-09-21T12:00:30+00:00")
        self.store.mark_disconnected("pickage-raw", "reset")
        self.assertEqual(self.store.snapshot()["buckets"]["pickage-raw"]["error"], "reset")
        self.assertIsNone(self.store.snapshot()["gaps"][1]["to"])


class ListenTest(unittest.TestCase):
    def test_reconnects_after_stream_ends_then_stops(self):
        store = events.EventStore(clock=Clock())
        stop = threading.Event()
        calls = []

        def open_stream(bucket):
            calls.append(bucket)
            if len(calls) == 1:
                return iter([record("a"), record("b")])       # 두 개 주고 끝난다 → 끊김으로 본다
            stop.set()
            return iter([])
        logs = []
        events.listen_forever(store, "pickage-raw", open_stream=open_stream, stop=stop,
                              log=logs.append, backoff_max=0.01)
        self.assertEqual(len(calls), 2)
        self.assertEqual(store.snapshot()["held"], 2)
        self.assertEqual(len(store.snapshot()["gaps"]), 1)
        self.assertTrue(any("끊김" in l for l in logs))

    def test_open_failure_is_a_gap_not_a_crash(self):
        store = events.EventStore(clock=Clock())
        stop = threading.Event()
        n = {"i": 0}

        def open_stream(bucket):
            n["i"] += 1
            if n["i"] >= 2:
                stop.set()
            raise ConnectionRefusedError("no minio")
        # backoff 를 아주 짧게 — stop.wait 가 잠깐 자고 나온다
        t = threading.Thread(target=events.listen_forever, args=(store, "b"),
                             kwargs={"open_stream": open_stream, "stop": stop, "log": lambda *_: None,
                                     "backoff_max": 0.01})
        t.start(); t.join(timeout=10)
        self.assertFalse(t.is_alive())
        self.assertFalse(store.snapshot()["buckets"]["b"]["connected"])


class DiscoveryTest(unittest.TestCase):
    def test_bucket_list_is_retried_until_minio_answers(self):
        """MinIO 가 늦게 떠도 구독이 걸린다. 그동안 보고서는 '구독 전' 이라고 말한다."""
        store = events.EventStore(clock=Clock())
        attempts = {"n": 0}
        listening = threading.Event()

        def resolve():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ConnectionRefusedError("minio not up yet")
            return ["pickage-raw"]

        def open_stream(bucket):
            def gen():
                yield record("a")
                listening.set()
                threading.Event().wait()          # 붙어 있는 채로
            return gen()
        self.assertFalse(store.snapshot()["discovery"]["pending"])
        stop = events.start_listeners_when_ready(store, resolve, open_stream=open_stream,
                                                 log=lambda *_: None, backoff_max=0.01)
        self.assertTrue(listening.wait(timeout=10))
        snap = store.snapshot()
        self.assertEqual(attempts["n"], 3)
        self.assertEqual(snap["discovery"], {"pending": False, "error": None, "attempts": 3})
        self.assertTrue(snap["buckets"]["pickage-raw"]["connected"])
        self.assertEqual(snap["held"], 1)
        stop.set()

    def test_pending_state_carries_the_last_error(self):
        store = events.EventStore(clock=Clock())
        seen = threading.Event()

        def resolve():
            seen.set()
            raise PermissionError("AccessDenied")
        stop = events.start_listeners_when_ready(store, resolve, open_stream=None,
                                                 log=lambda *_: None, backoff_max=60)
        self.assertTrue(seen.wait(timeout=5))
        for _ in range(50):                        # mark_discovery 가 seen 직후에 온다 — 잠깐 기다린다
            disc = store.snapshot()["discovery"]
            if disc["error"]:
                break
            threading.Event().wait(0.02)
        self.assertTrue(disc["pending"])
        self.assertIn("AccessDenied", disc["error"])
        self.assertEqual(disc["attempts"], 1)
        self.assertEqual(store.snapshot()["buckets"], {})
        stop.set()


if __name__ == "__main__":
    unittest.main()
