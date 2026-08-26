import json
import re
import string
import tempfile
import unittest
from pathlib import Path

from collector.config import SourceRegistry
from collector.contracts import Purpose
from collector.validator import canonical_value


class SourceRegistryTests(unittest.TestCase):
    def test_component_owned_assets_are_colocated_under_collector(self):
        collector_dir = Path(__file__).resolve().parents[1]
        repository_root = collector_dir.parent

        for relative_path in (
            "tests",
            ".env.example",
            "docs/api & data",
            "var/collector",
        ):
            self.assertFalse(repository_root.joinpath(relative_path).exists(), relative_path)
        for relative_path in (
            "tests",
            ".env.example",
            "docs/api & data",
        ):
            self.assertTrue(collector_dir.joinpath(relative_path).exists(), relative_path)

    def test_collector_document_links_resolve_after_monorepo_moves(self):
        collector_dir = Path(__file__).resolve().parents[1]
        markdown_link = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
        broken_links = []

        # API 조사 문서는 collector 소유지만 프로젝트 기획 문서는 루트 docs에
        # 남아 있으므로, 컴포넌트를 옮길 때 상대 링크가 깨지지 않았는지 확인한다.
        for document in collector_dir.joinpath("docs").rglob("*.md"):
            content = document.read_text(encoding="utf-8")
            for target in markdown_link.findall(content):
                target = target.strip().strip("<>")
                if target.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                path_text = target.split("#", 1)[0]
                if path_text and not document.parent.joinpath(path_text).exists():
                    broken_links.append(f"{document}: {target}")

        self.assertEqual(broken_links, [])

    def test_all_source_templates_have_declared_placeholders_and_credentials(self):
        registry = SourceRegistry()
        repository_root = Path(__file__).resolve().parents[2]
        env_example = (Path(__file__).resolve().parents[1] / ".env.example").read_text(
            encoding="utf-8"
        )
        specs = registry.list()
        self.assertEqual(len(specs), 24)
        for spec in specs:
            auth = spec.get("auth", {})
            if registry.supports_live(spec.source_id):
                self.assertIn(auth["env"], env_example)
                declared = (
                    set(spec.get("required_params", []))
                    | set(spec.get("path_defaults", {}))
                    | {auth.get("name")}
                )
                placeholders = {
                    name
                    for _, name, _, _ in string.Formatter().parse(
                        spec.get("endpoint_template")
                    )
                    if name
                }
                self.assertFalse(placeholders - declared, spec.source_id)
                evidence = spec.get("quota_evidence")
                if evidence:
                    evidence_path = str(evidence).split("#", 1)[0]
                    self.assertTrue(
                        repository_root.joinpath(evidence_path).is_file(),
                        evidence,
                    )
            if registry.supports_file(spec.source_id):
                self.assertTrue(spec.get("file_formats"), spec.source_id)
            for purpose in spec.get("purposes", []):
                Purpose(purpose)

    def test_additional_team_sources_are_registered_by_real_collection_mode(self):
        registry = SourceRegistry()
        expected_hybrid = {
            "seoul-bus-ridership-monthly",
            "seoul-subway-ridership-monthly",
            "seoul-subway-congestion-quarterly",
            "seoul-station-travel-time",
            "seoul-bus-route-master",
        }
        expected_file_only = {
            "seoul-subway-timetable-file",
            "seoul-subway-transfer-file",
        }
        expected_request_time = {
            "seoul-path-location",
            "seoul-path-subway",
            "seoul-path-bus",
            "seoul-path-mixed",
        }
        for source_id in expected_hybrid:
            self.assertTrue(registry.supports_live(source_id), source_id)
            self.assertTrue(registry.supports_file(source_id), source_id)
        for source_id in expected_file_only:
            self.assertFalse(registry.supports_live(source_id), source_id)
            self.assertTrue(registry.supports_file(source_id), source_id)
            with self.assertRaises(ValueError):
                registry.quota(source_id)
        for source_id in expected_request_time:
            self.assertTrue(registry.supports_live(source_id), source_id)
            self.assertFalse(registry.supports_file(source_id), source_id)
            self.assertEqual(
                registry.get(source_id).get("collection_mode"),
                "REQUEST_TIME_REFERENCE",
            )

    def test_arbitrary_allow_policy_and_unreviewed_example_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            policy_path = Path(tmpdir) / "policy.json"
            policy_path.write_text(
                json.dumps(
                    {
                        "sources": {
                            "bus-position": {
                                "raw": "ALLOW_NOT_REVIEWED",
                                "normalized": "DENY",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            registry = SourceRegistry(local_policy_path=policy_path)
            with self.assertRaises(ValueError):
                registry.policy("bus-position")

            policy_path.write_text(
                json.dumps(
                    {
                        "sources": {
                            "bus-position": {
                                "raw": "ALLOW_LOCAL_ONLY",
                                "normalized": "DENY",
                                "review_ticket": "REPLACE_WITH_APPROVED_DECISION_ID",
                                "reviewed_at": "YYYY-MM-DD",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            registry = SourceRegistry(local_policy_path=policy_path)
            with self.assertRaises(ValueError):
                registry.policy("bus-position")

    def test_tdata_smoke_defaults_and_snake_case_aliases_are_conservative(self):
        registry = SourceRegistry()
        bis = registry.get("tdata-bis-history")
        road = registry.get("tdata-road-hourly")
        self.assertEqual(bis.get("default_params")["rowCnt"], "1")
        self.assertEqual(road.get("default_params")["rowCnt"], "1")
        self.assertIn("arrival_time", bis.get("required_fields"))
        row = {
            "stnd_dt": "20260824",
            "time_cd": "17",
            "link_id": "1080012200",
            "avg_spd": "40.42",
            "road_div_cd": "04",
            "axis_cd": "1",
            "axis_dir_div_cd": "1",
            "day_cd": "2",
            "day_grp_cd": "01",
        }
        for field in road.get("required_fields"):
            self.assertIsNotNone(canonical_value(road, row, field), field)

    def test_quota_contracts_are_shared_or_fail_closed(self):
        registry = SourceRegistry()
        self.assertEqual(
            registry.quota("tdata-bis-history")["pool"], "tdata-shared"
        )
        self.assertEqual(
            registry.quota("tdata-road-hourly")["pool"], "tdata-shared"
        )
        self.assertNotEqual(
            registry.quota("bus-arrival")["pool"],
            registry.quota("bus-position")["pool"],
        )
        nowcast_quota = registry.quota("kma-ultra-short-nowcast")
        forecast_quota = registry.quota("kma-ultra-short-forecast")
        self.assertEqual(nowcast_quota["pool"], "data-go-kma-15084084-shared")
        self.assertEqual(forecast_quota["pool"], nowcast_quota["pool"])
        self.assertEqual(nowcast_quota["daily_limit"], 10_000)
        self.assertEqual(forecast_quota["daily_limit"], 10_000)
        with self.assertRaises(ValueError):
            registry.quota("seoul-road-realtime")
        for source_id in (
            "seoul-bus-ridership-monthly",
            "seoul-subway-ridership-monthly",
            "seoul-subway-congestion-quarterly",
            "seoul-station-travel-time",
            "seoul-bus-route-master",
            "seoul-path-bus",
        ):
            with self.subTest(source_id=source_id):
                with self.assertRaises(ValueError):
                    registry.quota(source_id)

    def test_reviewed_quota_override_enables_unconfirmed_source(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            quota_path = Path(tmpdir) / "quota.json"
            quota_path.write_text(
                json.dumps(
                    {
                        "sources": {
                            "seoul-road-realtime": {
                                "status": "LOCAL_OVERRIDE",
                                "pool": "seoul-open-general-shared",
                                "daily_limit": 250,
                                "verified_at": "2026-08-25",
                                "review_ticket": "OPS-QUOTA-1",
                                "evidence": "account console",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            registry = SourceRegistry(quota_override_path=quota_path)
            quota = registry.quota("seoul-road-realtime")
            self.assertEqual(quota["daily_limit"], 250)
            self.assertEqual(quota["status"], "LOCAL_OVERRIDE")

    def test_shared_pool_overrides_must_use_one_limit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            quota_path = Path(tmpdir) / "quota.json"
            common = {
                "status": "LOCAL_OVERRIDE",
                "pool": "data-go-seoul-pathinfo-shared",
                "verified_at": "2026-08-25",
                "review_ticket": "OPS-QUOTA-2",
                "evidence": "account console",
            }
            quota_path.write_text(
                json.dumps(
                    {
                        "sources": {
                            "seoul-path-location": {
                                **common,
                                "daily_limit": 10000,
                            },
                            "seoul-path-subway": {
                                **common,
                                "daily_limit": 9000,
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                SourceRegistry(quota_override_path=quota_path)

    def test_quota_override_cannot_expand_confirmed_source_or_split_pool(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            quota_path = Path(tmpdir) / "quota.json"
            quota_path.write_text(
                json.dumps(
                    {
                        "sources": {
                            "bus-arrival": {
                                "status": "LOCAL_OVERRIDE",
                                "pool": "operator-created-pool",
                                "daily_limit": 999999,
                                "verified_at": "2026-08-25",
                                "review_ticket": "OPS-QUOTA-3",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                SourceRegistry(quota_override_path=quota_path)

            quota_path.write_text(
                json.dumps(
                    {
                        "sources": {
                            "seoul-road-realtime": {
                                "status": "LOCAL_OVERRIDE",
                                "pool": "split-a",
                                "daily_limit": 250,
                                "verified_at": "2026-08-25",
                                "review_ticket": "OPS-QUOTA-4",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                SourceRegistry(quota_override_path=quota_path)


if __name__ == "__main__":
    unittest.main()
