"""서버 시험 — 실제 소켓으로 돈다 (127.0.0.1 의 빈 포트). Windows 에서도 된다."""
import json
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

from . import server


class _Counter:
    def __init__(self, node="app", fail=False):
        self.calls = 0
        self.node = node
        self.fail = fail

    def __call__(self, *, fresh=False):
        self.calls += 1
        if self.fail:
            raise RuntimeError("MinIO 안 붙음")
        return {"schema": 2, "node": self.node, "generated_at": "t", "errors": [], "calls": self.calls, "fresh": fresh}


def _start(node, peers, builder, ttl=60, web_dir=None, inventory=None):
    cache = server.ReportCache(builder, ttl)
    handler = server.make_handler(node=node, cache=cache, peers=peers, peer_timeout=5, inventory=inventory,
                                  inventory_timeout=5, web_dir=web_dir or Path(tempfile.mkdtemp()), log=lambda *_: None)
    srv = server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def _get(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


class CacheTest(unittest.TestCase):
    def test_ttl_and_fresh(self):
        counter = _Counter()
        cache = server.ReportCache(counter, 60)
        a = cache.get(); b = cache.get()
        self.assertEqual((a["calls"], b["calls"], b.get("cached")), (1, 1, True))
        c = cache.get(fresh=True)
        self.assertEqual((c["calls"], c["fresh"], c.get("cached")), (2, True, None))

    def test_expiry(self):
        cache = server.ReportCache(_Counter(), 0.05)
        cache.get(); time.sleep(0.1)
        self.assertEqual(cache.get()["calls"], 2)


class RoutesTest(unittest.TestCase):
    def setUp(self):
        self.data_srv, data_url = _start("data", {}, _Counter("data"))
        self.app_builder = _Counter("app")
        self.app_srv, self.url = _start("app", {"data": data_url, "gone": "http://127.0.0.1:1"}, self.app_builder,
                                        web_dir=Path(tempfile.mkdtemp()))

    def tearDown(self):
        self.app_srv.shutdown(); self.data_srv.shutdown()

    def test_nodes(self):
        status, body = _get(self.url + "/api/nodes")
        self.assertEqual(status, 200)
        self.assertEqual(body["self"], "app")
        self.assertEqual(body["nodes"], ["app", "data", "gone"])

    def test_own_report_uses_cache_unless_fresh(self):
        _get(self.url + "/api/report"); status, body = _get(self.url + "/api/report")
        self.assertEqual((status, body["calls"], body["cached"]), (200, 1, True))
        status, body = _get(self.url + "/api/report?fresh=1")
        self.assertEqual((body["calls"], body["fresh"]), (2, True))

    def test_peer_is_relayed_with_provenance(self):
        status, body = _get(self.url + "/api/report?node=data")
        self.assertEqual(status, 200)
        self.assertEqual(body["node"], "data")
        self.assertEqual(body["fetched_via"], "app")
        self.assertTrue(body["fetched_at"])

    def test_unreachable_peer_is_a_json_error_not_a_crash(self):
        status, body = _get(self.url + "/api/report?node=gone")
        self.assertEqual(status, 502)
        self.assertTrue(body["unreachable"])
        self.assertEqual(body["errors"][0]["section"], "fetch")

    def test_unknown_node_404(self):
        status, body = _get(self.url + "/api/report?node=nope")
        self.assertEqual(status, 404)

    def test_builder_failure_is_reported(self):
        srv, url = _start("x", {}, _Counter("x", fail=True))
        try:
            status, body = _get(url + "/api/report")
            self.assertEqual(status, 500)
            self.assertIn("MinIO", body["errors"][0]["message"])
        finally:
            srv.shutdown()

    def test_inventory_local_relay_and_absent(self):
        calls = []
        def inventory(*, force):
            calls.append(force)
            return {"available": True, "listed_at": "t", "forced": force}
        data_srv, data_url = _start("data", {}, _Counter("data"), inventory=inventory)
        app_srv, url = _start("app", {"data": data_url}, _Counter("app"))
        try:
            status, body = _get(url + "/api/inventory?node=data")
            self.assertEqual((status, body["forced"], body["fetched_via"]), (200, False, "app"))
            status, body = _get(url + "/api/inventory?node=data&fresh=1")
            self.assertEqual((status, body["forced"]), (200, True))
            self.assertEqual(calls, [False, True])
            status, body = _get(url + "/api/inventory")            # app 자신은 목록을 안 한다
            self.assertEqual((status, body["available"]), (404, False))
        finally:
            app_srv.shutdown(); data_srv.shutdown()

    def test_index_page_served(self):
        web = Path(tempfile.mkdtemp()); (web / "index.html").write_text("<title>x</title>", encoding="utf-8")
        srv, url = _start("y", {}, _Counter("y"), web_dir=web)
        try:
            with urllib.request.urlopen(url + "/", timeout=5) as r:
                self.assertEqual(r.headers["Content-Type"], "text/html; charset=utf-8")
                self.assertIn(b"<title>x</title>", r.read())
        finally:
            srv.shutdown()


if __name__ == "__main__":
    unittest.main()
