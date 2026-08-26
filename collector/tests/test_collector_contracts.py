import json
import os
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from collector.config import SourceRegistry
from collector.contracts import CollectionItem, HttpExchange, Purpose
from collector.http_client import HttpClient
from collector.parser import parse_exchange
from collector.service import CollectionService
from collector.safety import sha256_bytes
from collector.storage import MetadataRepository


FIXTURES = Path(__file__).parent / "fixtures"


def _service(tmpdir, http_client=None):
    repository = MetadataRepository(root=tmpdir, db_path=Path(tmpdir) / "collector.sqlite3")
    return CollectionService(repository=repository, http_client=http_client)


class CollectorContractTests(unittest.TestCase):
    def test_valid_bus_position_fixture_is_contract_usable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = _service(tmpdir)
            try:
                run = service.collect_fixture(
                    "bus-position",
                    FIXTURES / "bus_position_success.json",
                    params={"busRouteId": "100100001", "startOrd": "1", "endOrd": "30"},
                )
                self.assertEqual(run.report.verdict.value, "USABLE")
                self.assertEqual(run.report.scope.evidence_mode, "FIXTURE")
                self.assertEqual(run.report.metrics["row_count"], 1)
                self.assertEqual(run.report.metrics["source_time_count"], 1)
            finally:
                service.close()

    def test_http_200_business_error_fails_business_check(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = _service(tmpdir)
            try:
                run = service.collect_fixture("bus-position", FIXTURES / "bus_position_business_error.json")
                check = next(item for item in run.report.checks if item.code == "DQ-014")
                self.assertEqual(check.status.value, "FAIL")
                self.assertEqual(run.report.verdict.value, "UNUSABLE")
            finally:
                service.close()

    def test_default_deny_does_not_write_raw_or_normalized_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = _service(tmpdir)
            try:
                run = service.collect_fixture(
                    "bus-position",
                    FIXTURES / "bus_position_success.json",
                    params={"serviceKey": "secret-key"},
                )
                self.assertEqual(service.repository.artifact_count("raw"), 0)
                self.assertEqual(service.repository.artifact_count("normalized"), 0)
                self.assertNotIn("secret-key", json.dumps(run.to_summary()))
                for artifact in Path(tmpdir).rglob("*"):
                    if artifact.is_file():
                        self.assertNotIn(b"secret-key", artifact.read_bytes(), str(artifact))
            finally:
                service.close()

    def test_credential_value_is_redacted_even_under_arbitrary_param_name(self):
        secret = "super-secret/value+1"
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ, {"DATA_GO_BUS_API_KEY": secret}, clear=False
            ):
                service = _service(tmpdir)
                try:
                    run = service.collect_fixture(
                        "bus-position",
                        FIXTURES / "bus_position_success.json",
                        params={"foo": f"prefix-{secret}-suffix"},
                        target=f"target-{secret}",
                    )
                    rows = service.repository.connection.execute(
                        """SELECT r.target, r.safe_params_json, e.safe_params_json
                        FROM collection_run r
                        JOIN http_exchange e ON e.run_id=r.run_id
                        WHERE r.run_id=?""",
                        (run.run_id,),
                    ).fetchall()
                    persisted = json.dumps(
                        [dict(row) for row in rows], ensure_ascii=False
                    )
                    self.assertNotIn(secret, persisted)
                    self.assertNotIn(secret, json.dumps(run.to_summary()))
                    self.assertIn("<redacted>", persisted)
                finally:
                    service.close()

    def test_reviewed_local_policy_persists_raw_and_normalized_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            policy_path = Path(tmpdir) / "policy.json"
            policy_path.write_text(
                json.dumps(
                    {
                        "sources": {
                            "bus-position": {
                                "raw": "ALLOW_LOCAL_ONLY",
                                "normalized": "ALLOW_LOCAL_ONLY",
                                "reason": "test approval",
                                "review_ticket": "TEST-APPROVAL-1",
                                "reviewed_at": "2026-08-25",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            registry = SourceRegistry(local_policy_path=policy_path)
            repository = MetadataRepository(
                root=tmpdir, db_path=Path(tmpdir) / "collector.sqlite3"
            )
            service = CollectionService(registry=registry, repository=repository)
            try:
                run = service.collect_fixture(
                    "bus-position", FIXTURES / "bus_position_success.json"
                )
                self.assertEqual(service.repository.artifact_count("raw"), 1)
                self.assertEqual(service.repository.artifact_count("normalized"), 1)
                self.assertTrue(run.report.scope.policy_version.startswith("sha256:"))
            finally:
                service.close()

    def test_db_failure_removes_newly_created_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repository = MetadataRepository(
                root=tmpdir, db_path=Path(tmpdir) / "collector.sqlite3"
            )
            spec = SourceRegistry().get("bus-position")
            exchange = CollectionService._fixture_exchange(
                "bus-position", FIXTURES / "bus_position_success.json", {}
            )
            batch = parse_exchange(spec, exchange.body, exchange.content_type)
            run = CollectionService._new_run("bus-position", {}, None)
            policy = {
                "raw": "ALLOW_LOCAL_ONLY",
                "normalized": "ALLOW_LOCAL_ONLY",
                "reason": "test approval",
                "review_ticket": "TEST-APPROVAL-2",
                "reviewed_at": "2026-08-25",
            }
            try:
                with self.assertRaises(Exception):
                    repository.save_item(
                        run, CollectionItem(exchange=exchange, batch=batch), spec, policy
                    )
                self.assertEqual(list(Path(tmpdir).rglob("*.gz")), [])
            finally:
                repository.close()

    def test_url_encoded_credential_echo_is_never_persisted(self):
        secret = "SENTINEL/a+b=%25"
        encoded = "SENTINEL%2Fa%2Bb%3D%2525"
        with tempfile.TemporaryDirectory() as tmpdir:
            repository = MetadataRepository(
                root=tmpdir, db_path=Path(tmpdir) / "collector.sqlite3"
            )
            spec = SourceRegistry().get("bus-position")
            run = CollectionService._new_run("bus-position", {}, None)
            repository.begin_run(run, "FIXTURE", "test")
            exchange = CollectionService._fixture_exchange(
                "bus-position", FIXTURES / "bus_position_success.json", {}
            )
            exchange.body = json.dumps({"echo": encoded}).encode("utf-8")
            exchange.body_sha256 = sha256_bytes(exchange.body)
            exchange.body_bytes = len(exchange.body)
            batch = parse_exchange(spec, exchange.body, "application/json")
            policy = {
                "raw": "ALLOW_LOCAL_ONLY",
                "normalized": "ALLOW_LOCAL_ONLY",
                "reason": "test approval",
                "review_ticket": "TEST-APPROVAL-3",
                "reviewed_at": "2026-08-25",
            }
            try:
                with patch.dict(
                    os.environ, {"DATA_GO_BUS_API_KEY": secret}, clear=False
                ):
                    with self.assertRaises(ValueError):
                        repository.save_item(
                            run,
                            CollectionItem(exchange=exchange, batch=batch),
                            spec,
                            policy,
                        )
                self.assertEqual(list(Path(tmpdir).rglob("*.gz")), [])
            finally:
                repository.close()

    def test_json_escaped_credential_echo_is_never_persisted(self):
        for secret in ('foo"bar', "foo\\bar", "foo\nbar"):
            with self.subTest(secret=repr(secret)), tempfile.TemporaryDirectory() as tmpdir:
                repository = MetadataRepository(
                    root=tmpdir, db_path=Path(tmpdir) / "collector.sqlite3"
                )
                spec = SourceRegistry().get("bus-position")
                run = CollectionService._new_run("bus-position", {}, None)
                repository.begin_run(run, "FIXTURE", "test")
                exchange = CollectionService._fixture_exchange(
                    "bus-position", FIXTURES / "bus_position_success.json", {}
                )
                payload = {
                    "msgHeader": {"headerCd": "0", "headerMsg": "ok"},
                    "msgBody": {
                        "itemList": [
                            {
                                "routeId": "100100001",
                                "vehId": "V-1",
                                "sectOrd": "10",
                                "sectionId": "S-10",
                                "stopFlag": "0",
                                "dataTm": "2026-08-25 09:00:00",
                                "echo": secret,
                            }
                        ]
                    },
                }
                exchange.body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                exchange.body_sha256 = sha256_bytes(exchange.body)
                exchange.body_bytes = len(exchange.body)
                batch = parse_exchange(spec, exchange.body, "application/json")
                policy = {
                    "raw": "ALLOW_LOCAL_ONLY",
                    "normalized": "ALLOW_LOCAL_ONLY",
                    "reason": "test approval",
                    "review_ticket": "TEST-APPROVAL-4",
                    "reviewed_at": "2026-08-25",
                }
                try:
                    with patch.dict(
                        os.environ, {"DATA_GO_BUS_API_KEY": secret}, clear=False
                    ):
                        with self.assertRaises(ValueError):
                            repository.save_item(
                                run,
                                CollectionItem(exchange=exchange, batch=batch),
                                spec,
                                policy,
                            )
                    self.assertEqual(list(Path(tmpdir).rglob("*.gz")), [])
                finally:
                    repository.close()

    def test_json_unicode_escaped_credential_echo_is_never_persisted(self):
        secret = "é"
        with tempfile.TemporaryDirectory() as tmpdir:
            repository = MetadataRepository(
                root=tmpdir, db_path=Path(tmpdir) / "collector.sqlite3"
            )
            spec = SourceRegistry().get("bus-position")
            run = CollectionService._new_run("bus-position", {}, None)
            repository.begin_run(run, "FIXTURE", "test")
            exchange = CollectionService._fixture_exchange(
                "bus-position", FIXTURES / "bus_position_success.json", {}
            )
            payload = {
                "msgHeader": {"headerCd": "0", "headerMsg": "ok"},
                "msgBody": {"itemList": [{"echo": secret}]},
            }
            exchange.body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
            self.assertIn(b"\\u00e9", exchange.body)
            exchange.body_sha256 = sha256_bytes(exchange.body)
            exchange.body_bytes = len(exchange.body)
            batch = parse_exchange(spec, exchange.body, "application/json")
            policy = {
                "raw": "ALLOW_LOCAL_ONLY",
                "normalized": "ALLOW_LOCAL_ONLY",
                "reason": "test approval",
                "review_ticket": "TEST-APPROVAL-5",
                "reviewed_at": "2026-08-25",
            }
            try:
                with patch.dict(
                    os.environ, {"DATA_GO_BUS_API_KEY": secret}, clear=False
                ):
                    with self.assertRaises(ValueError):
                        repository.save_item(
                            run,
                            CollectionItem(exchange=exchange, batch=batch),
                            spec,
                            policy,
                        )
                self.assertEqual(list(Path(tmpdir).rglob("*.gz")), [])
            finally:
                repository.close()

    def test_fixture_manifest_is_reproducible(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = _service(tmpdir)
            try:
                params = {"busRouteId": "100100001", "startOrd": "1", "endOrd": "30"}
                first = service.collect_fixture(
                    "bus-position", FIXTURES / "bus_position_success.json", params=params
                )
                second = service.collect_fixture(
                    "bus-position", FIXTURES / "bus_position_success.json", params=params
                )
                self.assertEqual(first.report.manifest_sha256, second.report.manifest_sha256)
            finally:
                service.close()

    def test_http_prepare_redacts_secret_from_safe_exchange_metadata(self):
        registry = SourceRegistry()
        spec = registry.get("bus-position")
        with patch.dict(os.environ, {"DATA_GO_BUS_API_KEY": "super-secret"}, clear=False):
            url, safe_url, safe_params, secrets = HttpClient().prepare(
                spec,
                {"busRouteId": "100100001", "startOrd": "1", "endOrd": "30"},
                allow_insecure_http=True,
            )
        self.assertIn("super-secret", url)
        self.assertNotIn("super-secret", safe_url)
        self.assertEqual(safe_params["resultType"], "json")
        self.assertEqual(secrets, ["super-secret"])

    def test_duplicate_metadata_and_quota_survive_repository_restart(self):
        class FakeHttpClient:
            max_retries = 0

            def prepare(self, spec, params, *, allow_insecure_http):
                return "http://provider", "http://provider", {}, ["secret"]

            def fetch(self, spec, params, *, allow_insecure_http=False):
                body = (FIXTURES / "bus_position_success.json").read_bytes()
                return CollectionService._fixture_exchange(spec.source_id, FIXTURES / "bus_position_success.json", params)

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "collector.sqlite3"
            with patch.dict(os.environ, {"DATA_GO_BUS_API_KEY": "secret"}, clear=False):
                service = _service(tmpdir, FakeHttpClient())
                try:
                    run = service.collect_live(
                        "bus-position",
                        {"busRouteId": "100100001", "startOrd": "1", "endOrd": "30"},
                        count=2,
                        allow_insecure_http=True,
                    )
                    duplicate = service.repository.connection.execute(
                        "SELECT duplicate_of FROM http_exchange WHERE run_id=? ORDER BY requested_at",
                        (run.run_id,),
                    ).fetchall()
                    self.assertIsNone(duplicate[0][0])
                    self.assertIsNotNone(duplicate[1][0])
                    quota_date = datetime.now(
                        timezone(timedelta(hours=9))
                    ).date().isoformat()
                    self.assertEqual(
                        service.repository.quota_usage(
                            "data-go-bus-position", quota_date
                        ),
                        2,
                    )
                finally:
                    service.close()

            reopened = MetadataRepository(root=tmpdir, db_path=db_path)
            try:
                quota_date = datetime.now(
                    timezone(timedelta(hours=9))
                ).date().isoformat()
                self.assertEqual(
                    reopened.quota_usage("data-go-bus-position", quota_date), 2
                )
                self.assertEqual(reopened.artifact_count("raw"), 0)
            finally:
                reopened.close()

    def test_provider_quota_code_stops_remaining_poll_count(self):
        class QuotaHttpClient:
            max_retries = 0
            timeout_seconds = 1800

            def __init__(self):
                self.calls = 0

            def prepare(self, spec, params, *, allow_insecure_http):
                return "http://provider", "http://provider", {}, ["secret"]

            def fetch(self, spec, params, *, allow_insecure_http=False):
                self.calls += 1
                return CollectionService._fixture_exchange(
                    spec.source_id,
                    FIXTURES / "bus_position_quota_error.json",
                    params,
                )

        with tempfile.TemporaryDirectory() as tmpdir:
            client = QuotaHttpClient()
            with patch.dict(os.environ, {"DATA_GO_BUS_API_KEY": "secret"}, clear=False):
                service = _service(tmpdir, client)
                try:
                    run = service.collect_live(
                        "bus-position",
                        {"busRouteId": "100100001", "startOrd": "1", "endOrd": "30"},
                        count=5,
                        allow_insecure_http=True,
                    )
                    self.assertEqual(client.calls, 1)
                    self.assertEqual(len(run.items), 1)
                    self.assertEqual(run.failure_code, "PROVIDER_QUOTA_EXHAUSTED")
                    self.assertEqual(run.report.verdict.value, "UNUSABLE")
                    row = service.repository.connection.execute(
                        "SELECT status FROM collection_run WHERE run_id=?",
                        (run.run_id,),
                    ).fetchone()
                    self.assertEqual(row["status"], "FAILED")
                    lease = service.repository.connection.execute(
                        "SELECT created_at, expires_at FROM quota_reservation "
                        "WHERE run_id=?",
                        (run.run_id,),
                    ).fetchone()
                    lease_seconds = (
                        datetime.fromisoformat(lease["expires_at"])
                        - datetime.fromisoformat(lease["created_at"])
                    ).total_seconds()
                    self.assertGreater(lease_seconds, client.timeout_seconds)
                finally:
                    service.close()

    def test_partial_live_failure_is_finalized_and_reported(self):
        class PartialFailureHttpClient:
            max_retries = 0

            def __init__(self):
                self.calls = 0

            def prepare(self, spec, params, *, allow_insecure_http):
                return "http://provider", "http://provider", {}, ["secret"]

            def fetch(self, spec, params, *, allow_insecure_http=False):
                self.calls += 1
                if self.calls == 2:
                    raise OSError("simulated network failure")
                return CollectionService._fixture_exchange(
                    spec.source_id,
                    FIXTURES / "bus_position_success.json",
                    params,
                )

        with tempfile.TemporaryDirectory() as tmpdir:
            client = PartialFailureHttpClient()
            with patch.dict(
                os.environ, {"DATA_GO_BUS_API_KEY": "secret"}, clear=False
            ):
                service = _service(tmpdir, client)
                try:
                    run = service.collect_live(
                        "bus-position",
                        {
                            "busRouteId": "100100001",
                            "startOrd": "1",
                            "endOrd": "30",
                        },
                        count=2,
                        allow_insecure_http=True,
                    )
                    self.assertEqual(run.failure_code, "OSERROR")
                    self.assertEqual(run.report.verdict.value, "UNUSABLE")
                    completion = next(
                        check
                        for check in run.report.checks
                        if check.code == "DQ-COLLECTION"
                    )
                    self.assertEqual(completion.status.value, "FAIL")
                    row = service.repository.connection.execute(
                        "SELECT ended_at, status FROM collection_run WHERE run_id=?",
                        (run.run_id,),
                    ).fetchone()
                    self.assertIsNotNone(row["ended_at"])
                    self.assertEqual(row["status"], "FAILED")
                    report_count = service.repository.connection.execute(
                        "SELECT COUNT(*) FROM validation_report WHERE run_id=?",
                        (run.run_id,),
                    ).fetchone()[0]
                    self.assertEqual(report_count, 1)
                finally:
                    service.close()

    def test_oa15799_xml_parser_uses_rows_and_declared_count(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = _service(tmpdir)
            try:
                run = service.collect_fixture("subway-arrival-all", FIXTURES / "oa15799_success.xml")
                self.assertEqual(len(run.items[0].batch.rows), 2)
                self.assertEqual(run.items[0].batch.declared_count, 2)
                count_check = next(item for item in run.report.checks if item.code == "DQ-COUNT")
                self.assertEqual(count_check.status.value, "PASS")
            finally:
                service.close()

    def test_eta_row_is_not_promoted_to_actual_without_transition(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = _service(tmpdir)
            try:
                run = service.collect_fixture(
                    "subway-arrival",
                    FIXTURES / "subway_arrival_eta_only.json",
                    purpose=Purpose.ACTUAL_LABEL,
                )
                self.assertEqual(run.report.metrics["actual_interval_count"], 0)
                actual = next(item for item in run.report.checks if item.code == "DQ-ACTUAL")
                self.assertIn("not promoted", actual.message.lower())
                eligibility = next(item for item in run.report.eligibility if item.purpose == Purpose.ACTUAL_LABEL)
                self.assertIn("FIXTURE_EVIDENCE_ONLY", eligibility.reason_codes)
            finally:
                service.close()

    def test_subway_directions_are_distinct_effective_events(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fixture = json.loads(
                (FIXTURES / "subway_arrival_eta_only.json").read_text(
                    encoding="utf-8"
                )
            )
            first = fixture["body"]["realtimeArrivalList"][0]
            second = deepcopy(first)
            second["updnLine"] = "하행"
            fixture["body"]["realtimeArrivalList"].append(second)
            fixture["body"]["errorMessage"]["total"] = 2
            path = Path(tmpdir) / "two_directions.json"
            path.write_text(json.dumps(fixture), encoding="utf-8")
            service = _service(tmpdir)
            try:
                run = service.collect_fixture("subway-arrival", path)
                self.assertEqual(run.report.metrics["raw_row_count"], 2)
                self.assertEqual(run.report.metrics["effective_event_count"], 2)
                self.assertEqual(run.report.metrics["revision_count"], 0)
                identity = next(
                    check
                    for check in run.report.checks
                    if check.code == "DQ-IDENTITY"
                )
                self.assertEqual(identity.status.value, "PASS")
            finally:
                service.close()

    def test_bus_position_state_transition_creates_interval_candidate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = _service(tmpdir)
            try:
                run = service.collect_fixtures(
                    "bus-position",
                    [
                        FIXTURES / "bus_position_before.json",
                        FIXTURES / "bus_position_after.json",
                    ],
                )
                self.assertEqual(run.report.metrics["actual_interval_count"], 1)
                self.assertEqual(run.report.metrics["max_actual_interval_width_seconds"], 30.0)
            finally:
                service.close()

    def test_cross_section_or_zero_width_state_change_is_not_actual(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = _service(tmpdir)
            try:
                for case in ("cross_section", "zero_width"):
                    before = json.loads(
                        (FIXTURES / "bus_position_before.json").read_text(
                            encoding="utf-8"
                        )
                    )
                    after = json.loads(
                        (FIXTURES / "bus_position_after.json").read_text(
                            encoding="utf-8"
                        )
                    )
                    after_row = after["body"]["msgBody"]["itemList"][0]
                    before_row = before["body"]["msgBody"]["itemList"][0]
                    if case == "cross_section":
                        after_row["sectionId"] = "S-11"
                    else:
                        after_row["dataTm"] = before_row["dataTm"]
                    before_path = Path(tmpdir) / f"{case}_before.json"
                    after_path = Path(tmpdir) / f"{case}_after.json"
                    before_path.write_text(json.dumps(before), encoding="utf-8")
                    after_path.write_text(json.dumps(after), encoding="utf-8")
                    with self.subTest(case=case):
                        run = service.collect_fixtures(
                            "bus-position", [before_path, after_path]
                        )
                        self.assertEqual(
                            run.report.metrics["actual_interval_count"], 0
                        )
            finally:
                service.close()

    def test_partial_transport_cannot_be_realtime_usable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = _service(tmpdir)
            try:
                run = service.collect_fixture(
                    "bus-position", FIXTURES / "bus_position_success.json"
                )
                failed = deepcopy(run.items[0])
                failed.exchange.exchange_id = "failed-exchange"
                failed.exchange.http_status = 500
                failed.exchange.transport_error = "HTTPError:500"
                run.items.append(failed)
                spec = service.registry.get("bus-position")
                spec.data["profiled"] = True
                spec.data["mapping_status"] = "VERIFIED"
                report = service.validator.evaluate(
                    run,
                    spec,
                    Purpose.REALTIME_FEATURE,
                    service.registry.policy("bus-position"),
                    evidence_mode="LIVE",
                )
                self.assertNotEqual(report.verdict.value, "USABLE")
                selected = next(
                    item
                    for item in report.eligibility
                    if item.purpose == Purpose.REALTIME_FEATURE
                )
                self.assertIn("DQ-TRANSPORT_NOT_PASS", selected.reason_codes)
            finally:
                service.close()

    def test_two_raw_rows_without_support_gate_cannot_be_historical_usable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = _service(tmpdir)
            try:
                run = service.collect_fixture(
                    "bus-position", FIXTURES / "bus_position_transition.json"
                )
                spec = service.registry.get("bus-position")
                spec.data["profiled"] = True
                spec.data["mapping_status"] = "VERIFIED"
                policy = {
                    "raw": "ALLOW_LOCAL_ONLY",
                    "normalized": "ALLOW_LOCAL_ONLY",
                    "reason": "test",
                    "review_ticket": "TEST-1",
                    "reviewed_at": "2026-08-25",
                }
                report = service.validator.evaluate(
                    run,
                    spec,
                    Purpose.HISTORICAL_MODEL,
                    policy,
                    evidence_mode="LIVE",
                )
                self.assertNotEqual(report.verdict.value, "USABLE")
                selected = next(
                    item
                    for item in report.eligibility
                    if item.purpose == Purpose.HISTORICAL_MODEL
                )
                self.assertIn(
                    "HISTORICAL_SUPPORT_GATE_NOT_CONFIGURED",
                    selected.reason_codes,
                )
            finally:
                service.close()


if __name__ == "__main__":
    unittest.main()
