from __future__ import annotations

import io
import json
import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from collector.logging_utils import configure_logging
from collector.service import CollectionService
from collector.storage import MetadataRepository


class _FailingClient:
    max_retries = 0

    def prepare(self, _spec, _params, *, allow_insecure_http):  # type: ignore[no-untyped-def]
        return "http://provider", "http://provider", {}, ["secret-value"]

    def fetch(self, _spec, _params, *, allow_insecure_http=False, context=None):  # type: ignore[no-untyped-def]
        raise OSError("simulated failure containing secret-value")


class _ReportFailingRepository(MetadataRepository):
    def save_report(self, _report):  # type: ignore[no-untyped-def]
        raise OSError("simulated report persistence failure containing secret-value")


class ServiceLoggingTests(unittest.TestCase):
    def tearDown(self):
        logger = logging.getLogger("collector")
        for handler in list(logger.handlers):
            if getattr(handler, "_collector_configured", False):
                logger.removeHandler(handler)
                handler.close()
        logger.setLevel(logging.NOTSET)

    def test_failure_logs_phase_quota_and_redacted_debug_traceback(self):
        stream = io.StringIO()
        configure_logging(
            level="DEBUG",
            output_format="json",
            secrets=["secret-value"],
            stream=stream,
        )
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            os.environ, {"DATA_GO_BUS_API_KEY": "secret-value"}, clear=False
        ):
            service = CollectionService(
                repository=MetadataRepository(
                    root=tmpdir, db_path=Path(tmpdir) / "collector.sqlite3"
                ),
                http_client=_FailingClient(),
                sleeper=lambda _seconds: None,
            )
            try:
                run = service.collect_live(
                    "bus-position",
                    {"busRouteId": "100100001", "startOrd": "1", "endOrd": "30"},
                    allow_insecure_http=True,
                )
            finally:
                service.close()

        self.assertEqual(run.failure_code, "OSERROR")
        rendered = stream.getvalue()
        self.assertNotIn("secret-value", rendered)
        records = [json.loads(line) for line in rendered.splitlines()]
        events = {record["event"] for record in records}
        self.assertIn("quota.reserved", events)
        self.assertIn("quota.released", events)
        self.assertIn("collection.failed", events)
        self.assertIn("collection.traceback", events)
        self.assertIn("validation.finished", events)
        failure = next(record for record in records if record["event"] == "collection.failed")
        self.assertEqual(failure["context"]["phase"], "http_and_parse")

    def test_report_persistence_failure_is_logged_and_run_is_marked_failed(self):
        stream = io.StringIO()
        configure_logging(
            level="DEBUG",
            output_format="json",
            secrets=["secret-value"],
            stream=stream,
        )
        fixture = Path(__file__).parent / "fixtures" / "bus_position_success.json"
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            os.environ, {"DATA_GO_BUS_API_KEY": "secret-value"}, clear=False
        ):
            repository = _ReportFailingRepository(
                root=tmpdir, db_path=Path(tmpdir) / "collector.sqlite3"
            )
            service = CollectionService(repository=repository)
            try:
                with self.assertRaisesRegex(OSError, "report persistence failure"):
                    service.collect_fixture("bus-position", fixture)
                row = repository.connection.execute(
                    "SELECT status, failure_code, failure_message FROM collection_run "
                    "ORDER BY started_at DESC LIMIT 1"
                ).fetchone()
            finally:
                service.close()

        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "FAILED")
        self.assertEqual(row["failure_code"], "OSERROR")
        self.assertNotIn("secret-value", row["failure_message"])
        rendered = stream.getvalue()
        self.assertNotIn("secret-value", rendered)
        records = [json.loads(line) for line in rendered.splitlines()]
        finalization = next(
            record
            for record in records
            if record["event"] == "collection.finalization_failed"
        )
        self.assertEqual(finalization["context"]["phase"], "report_persistence")
        self.assertIn("collection.failed", {record["event"] for record in records})


if __name__ == "__main__":
    unittest.main()
