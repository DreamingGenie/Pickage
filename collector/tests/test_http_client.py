import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from collector.config import SourceSpec
from collector.http_client import ConfigurationError, HttpClient
from collector.safety import sanitize_url


class _SequenceHandler(BaseHTTPRequestHandler):
    statuses = []
    calls = 0

    def do_GET(self):
        type(self).calls += 1
        status = type(self).statuses.pop(0)
        body = b'{"response":{"header":{"resultCode":"00"}},"items":[{"id":"1"}]}'
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


class _RedirectHandler(BaseHTTPRequestHandler):
    location = ""

    def do_GET(self):
        self.send_response(302)
        self.send_header("Location", type(self).location)
        self.end_headers()

    def log_message(self, format, *args):
        return


class _SinkHandler(BaseHTTPRequestHandler):
    calls = 0

    def do_GET(self):
        type(self).calls += 1
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        return


class HttpClientTests(unittest.TestCase):
    def setUp(self):
        _SequenceHandler.calls = 0
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _SequenceHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def _spec(self):
        return SourceSpec(
            "local-test",
            {
                "endpoint_template": f"http://127.0.0.1:{self.server.server_port}/data",
                "auth": {"env": "LOCAL_TEST_KEY", "location": "query", "name": "serviceKey"},
                "required_params": ["target"],
                "default_params": {},
            },
        )

    def test_retries_transient_http_and_records_boundary_timestamps(self):
        _SequenceHandler.statuses = [500, 200]
        client = HttpClient(max_retries=2, sleeper=lambda _: None, jitter=lambda _a, _b: 0)
        with patch.dict(os.environ, {"LOCAL_TEST_KEY": "secret-value"}, clear=False):
            exchange = client.fetch(
                self._spec(), {"target": "A"}, allow_insecure_http=True
            )
        self.assertEqual(exchange.http_status, 200)
        self.assertEqual(exchange.attempts, 2)
        self.assertEqual(len(exchange.retry_history), 1)
        self.assertEqual(_SequenceHandler.calls, 2)
        self.assertLessEqual(exchange.requested_at, exchange.headers_received_at)
        self.assertLessEqual(exchange.headers_received_at, exchange.body_completed_at)
        self.assertNotIn("secret-value", exchange.safe_endpoint)

    def test_does_not_retry_non_transient_http_error(self):
        _SequenceHandler.statuses = [401]
        client = HttpClient(max_retries=2, sleeper=lambda _: None)
        with patch.dict(os.environ, {"LOCAL_TEST_KEY": "secret-value"}, clear=False):
            exchange = client.fetch(
                self._spec(), {"target": "A"}, allow_insecure_http=True
            )
        self.assertEqual(exchange.http_status, 401)
        self.assertEqual(exchange.attempts, 1)
        self.assertEqual(_SequenceHandler.calls, 1)

    def test_special_character_path_and_echoed_query_secret_are_redacted(self):
        secret = "SENTINEL/a+b=%25"
        registry_spec = SourceSpec(
            "path-test",
            {
                "endpoint_template": "https://provider.test/api/{key}/{target}",
                "auth": {"env": "PATH_TEST_KEY", "location": "path", "name": "key"},
                "required_params": ["target"],
                "path_defaults": {},
            },
        )
        with patch.dict(os.environ, {"PATH_TEST_KEY": secret}, clear=False):
            _url, safe_url, _params, _secrets = HttpClient().prepare(
                registry_spec, {"target": "rows"}, allow_insecure_http=False
            )
        self.assertNotIn(secret, safe_url)
        self.assertNotIn("SENTINEL", safe_url)
        echoed = sanitize_url(
            "https://provider.test/path?filter=SENTINEL%2Fa%2Bb%3D%2525",
            [secret],
        )
        self.assertNotIn("SENTINEL", echoed)

    def test_redirect_is_not_followed_with_query_credential(self):
        sink = ThreadingHTTPServer(("127.0.0.1", 0), _SinkHandler)
        sink_thread = threading.Thread(target=sink.serve_forever, daemon=True)
        sink_thread.start()
        redirect = ThreadingHTTPServer(("127.0.0.1", 0), _RedirectHandler)
        redirect_thread = threading.Thread(target=redirect.serve_forever, daemon=True)
        redirect_thread.start()
        _SinkHandler.calls = 0
        _RedirectHandler.location = (
            f"http://127.0.0.1:{sink.server_port}/sink?leak=secret-value"
        )
        spec = SourceSpec(
            "redirect-test",
            {
                "endpoint_template": f"http://127.0.0.1:{redirect.server_port}/start",
                "auth": {
                    "env": "LOCAL_TEST_KEY",
                    "location": "query",
                    "name": "serviceKey",
                },
                "required_params": [],
                "default_params": {},
            },
        )
        try:
            with patch.dict(
                os.environ, {"LOCAL_TEST_KEY": "secret-value"}, clear=False
            ):
                exchange = HttpClient(max_retries=0).fetch(
                    spec, {}, allow_insecure_http=True
                )
            self.assertEqual(exchange.http_status, 302)
            self.assertEqual(_SinkHandler.calls, 0)
            self.assertEqual(exchange.attempts, 1)
        finally:
            redirect.shutdown()
            redirect.server_close()
            redirect_thread.join(timeout=2)
            sink.shutdown()
            sink.server_close()
            sink_thread.join(timeout=2)

    def test_sensitive_location_parameters_are_removed_from_safe_metadata(self):
        spec = SourceSpec(
            "location-test",
            {
                "endpoint_template": "https://provider.test/path",
                "auth": {
                    "env": "LOCATION_TEST_KEY",
                    "location": "query",
                    "name": "serviceKey",
                },
                "required_params": ["startX", "startY"],
                "sensitive_params": ["startX", "startY"],
            },
        )
        with patch.dict(os.environ, {"LOCATION_TEST_KEY": "secret-value"}, clear=False):
            url, safe_url, safe_params, _secrets = HttpClient().prepare(
                spec,
                {"startX": "126.9780", "startY": "37.5665"},
                allow_insecure_http=False,
            )
        self.assertIn("126.9780", url)
        self.assertNotIn("126.9780", safe_url)
        self.assertNotIn("37.5665", safe_url)
        self.assertEqual(safe_params["startX"], "<redacted>")
        self.assertEqual(safe_params["startY"], "<redacted>")

    def test_optional_filters_are_appended_as_ordered_path_segments(self):
        spec = SourceSpec(
            "seoul-station-travel-time-test",
            {
                "endpoint_template": (
                    "http://provider.test/{key}/{type}/"
                    "StationDstncReqreTimeHm/{start}/{end}/"
                ),
                "auth": {"env": "LOCAL_TEST_KEY", "location": "path", "name": "key"},
                "required_params": [],
                "path_defaults": {"type": "json", "start": "1", "end": "5"},
                "optional_path_params": ["SBWY_ROUT_LN", "SBWY_STNS_NM"],
            },
        )
        client = HttpClient()
        with patch.dict(os.environ, {"LOCAL_TEST_KEY": "secret-value"}, clear=False):
            unfiltered, _, _, _ = client.prepare(
                spec, {}, allow_insecure_http=True
            )
            filtered, _, safe_params, _ = client.prepare(
                spec,
                {"SBWY_ROUT_LN": "8", "SBWY_STNS_NM": "암사"},
                allow_insecure_http=True,
            )

        self.assertTrue(unfiltered.endswith("/StationDstncReqreTimeHm/1/5/"))
        self.assertNotIn("/1/5///", unfiltered)
        self.assertIn("/StationDstncReqreTimeHm/1/5/8/%EC%95%94%EC%82%AC/", filtered)
        self.assertNotIn("SBWY_ROUT_LN=", filtered)
        self.assertNotIn("SBWY_STNS_NM=", filtered)
        self.assertEqual(safe_params["SBWY_ROUT_LN"], "8")

    def test_optional_path_segments_reject_a_missing_prefix(self):
        spec = SourceSpec(
            "ordered-path-test",
            {
                "endpoint_template": "http://provider.test/{key}/rows/",
                "auth": {"env": "LOCAL_TEST_KEY", "location": "path", "name": "key"},
                "required_params": [],
                "optional_path_params": ["line", "station"],
            },
        )
        with patch.dict(os.environ, {"LOCAL_TEST_KEY": "secret-value"}, clear=False):
            with self.assertRaisesRegex(ConfigurationError, "must be supplied in order"):
                HttpClient().prepare(
                    spec, {"station": "암사"}, allow_insecure_http=True
                )


if __name__ == "__main__":
    unittest.main()
