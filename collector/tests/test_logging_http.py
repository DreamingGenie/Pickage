import io
import json
import logging
import os
import unittest
from unittest.mock import patch

from collector.config import SourceSpec
from collector.contracts import HttpExchange
from collector.http_client import HttpClient
from collector.logging_utils import configure_logging, log_event
from collector.safety import sha256_bytes


def _exchange(status: int, attempt: int) -> HttpExchange:
    body = b"{}"
    return HttpExchange(
        exchange_id=f"exchange-{attempt}",
        source_id="logging-test",
        safe_endpoint="https://provider.example/data?serviceKey=%3Credacted%3E",
        safe_params={},
        requested_at="2026-08-25T00:00:00+00:00",
        headers_received_at="2026-08-25T00:00:00.001000+00:00",
        body_completed_at="2026-08-25T00:00:00.002000+00:00",
        http_status=status,
        content_type="application/json",
        body=body,
        body_sha256=sha256_bytes(body),
        body_bytes=len(body),
        attempts=attempt,
        elapsed_ms=2.0,
        retry_after=None,
    )


class _Response:
    def __init__(self, status: int) -> None:
        self.status = status
        self.headers = {"Content-Type": "application/json"}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit: int) -> bytes:
        return b'{"items": []}'


class _Opener:
    def __init__(self, statuses: list[int]) -> None:
        self.statuses = statuses

    def open(self, _request, timeout: float):  # type: ignore[no-untyped-def]
        return _Response(self.statuses.pop(0))


class LoggingAndHttpTests(unittest.TestCase):
    def test_log_record_never_carries_raw_secret_as_extra_metadata(self):
        """A host handler may serialize every LogRecord attribute, not just our formatter."""
        records: list[logging.LogRecord] = []

        class CaptureHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        logger = logging.getLogger("collector.test.raw-record")
        logger.handlers.clear()
        logger.propagate = False
        logger.setLevel(logging.INFO)
        logger.addHandler(CaptureHandler())

        log_event(
            logger,
            logging.INFO,
            "test.event",
            "request used TOPSECRET",
            secrets=["TOPSECRET"],
            nested={"credential": "TOPSECRET"},
        )

        self.assertEqual(len(records), 1)
        serialized = repr(records[0].__dict__)
        self.assertNotIn("TOPSECRET", serialized)
        self.assertNotIn("collector_secrets", records[0].__dict__)

    def tearDown(self):
        # Restore the library's quiet default for other tests in the process.
        logger = logging.getLogger("collector")
        for handler in list(logger.handlers):
            if getattr(handler, "_collector_configured", False):
                logger.removeHandler(handler)
                handler.close()
        logger.setLevel(logging.NOTSET)

    def test_json_formatter_redacts_message_and_nested_context(self):
        stream = io.StringIO()
        logger = configure_logging(
            level=logging.INFO,
            output_format="json",
            secrets=["secret-value"],
            stream=stream,
        )
        log_event(
            logger,
            logging.INFO,
            "test.completed",
            "credential=secret-value",
            secrets=["secret-value"],
            run_id="run-1",
            endpoint="https://provider.example/?token=secret-value",
            nested={"value": "secret-value"},
        )

        payload = json.loads(stream.getvalue())
        rendered = stream.getvalue()
        self.assertEqual(payload["event"], "test.completed")
        self.assertEqual(payload["context"]["run_id"], "run-1")
        self.assertNotIn("secret-value", rendered)
        self.assertIn("<redacted>", rendered)

    def test_http_retry_logs_safe_correlation_context_without_body_or_url_secret(self):
        stream = io.StringIO()
        configure_logging(
            level=logging.INFO,
            output_format="json",
            stream=stream,
        )
        spec = SourceSpec(
            "logging-test",
            {
                "endpoint_template": "https://provider.example/data",
                "auth": {
                    "env": "LOGGING_TEST_KEY",
                    "location": "query",
                    "name": "serviceKey",
                },
                "required_params": [],
            },
        )
        client = HttpClient(max_retries=1, sleeper=lambda _: None)
        client.opener = _Opener([500, 200])
        with patch.dict(os.environ, {"LOGGING_TEST_KEY": "secret-value"}, clear=False):
            exchange = client.fetch(
                spec,
                {},
                context={"run_id": "run-1", "poll_index": 3},
            )

        records = [json.loads(line) for line in stream.getvalue().splitlines()]
        events = [record["event"] for record in records]
        self.assertEqual(exchange.http_status, 200)
        self.assertIn("http.attempt_finished", events)
        self.assertIn("http.retry_scheduled", events)
        rendered = stream.getvalue()
        self.assertNotIn("secret-value", rendered)
        self.assertNotIn('"body"', rendered)
        self.assertIn('"run_id": "run-1"', rendered)
        self.assertIn('"poll_index": 3', rendered)


if __name__ == "__main__":
    unittest.main()
