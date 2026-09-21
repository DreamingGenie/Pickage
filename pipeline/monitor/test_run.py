import unittest
from datetime import datetime, timezone

from . import config as cfg
from . import run
from .test_events import record
from .test_support import FakeDocker, FakeS3

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def seeded_s3():
    s3 = FakeS3()
    s3.add("pickage-raw", "depsdev/v1/projects/snapshot=2026-09-21/run_id=r/_SUCCESS", b"", NOW)
    s3.add("pickage-raw", "_ops/weekly/2026-09-21/run.json",
           {"week_of": "2026-09-21", "status": "SUCCEEDED", "steps": []}, NOW)
    return s3


def stream_of(*keys):
    """구독 스트림 흉내 — 레코드 몇 개를 주고 영원히 기다린다(스레드가 끝나지 않게)."""
    import threading
    def opener(bucket):
        def gen():
            for k in keys:
                if k.startswith(bucket + ":"):
                    yield record(k.split(":", 1)[1], bucket=bucket)
            threading.Event().wait()      # 더 이상 안 온다 — 끊긴 척하지 않는다
        return gen()
    return opener


class BuildReportTest(unittest.TestCase):
    def test_sections_present_and_failures_isolated(self):
        settings = cfg.parse({"node": "data", "minio": {"pointers": ["pickage-vectors/_current.json"]},
                              "local": {"paths": [{"path": "/definitely/missing", "label": "/x"}]}})
        docker = FakeDocker(containers=[], details={}, logs={})
        builder = run.Builder(settings, s3=seeded_s3(), docker_client=docker,
                              open_stream=stream_of("pickage-raw:depsdev/v1/x/snapshot=2026-09-21/run_id=r/_SUCCESS"))
        import time; time.sleep(0.3)      # 구독 스레드가 레코드를 넣을 시간
        report = builder.build()
        self.assertEqual(report["node"], "data")
        self.assertTrue(report["minio"]["pointers"][0]["missing"])
        self.assertEqual(report["minio"]["events"]["completed"][0]["prefix"], "depsdev/v1/x/snapshot=2026-09-21/run_id=r")
        self.assertTrue(report["minio"]["events"]["buckets"]["pickage-raw"]["connected"])
        self.assertEqual(report["minio"]["inventory"], {"available": False})   # 자동으로는 안 긁는다
        self.assertEqual(report["weekly"]["runs"][0]["status"], "SUCCEEDED")
        self.assertTrue(report["local"]["paths"][0]["missing"])
        self.assertEqual(report["docker"]["matched"], 0)
        self.assertEqual(report["errors"], [])

    def test_a_broken_section_does_not_take_the_others(self):
        settings = cfg.parse({"node": "app", "minio": {"inventory": False, "weekly": False, "events": False}})

        class Broken:
            def containers(self):
                raise RuntimeError("소켓 없음")
        report = run.Builder(settings, s3=None, docker_client=Broken()).build()
        self.assertIsNone(report["docker"])
        self.assertEqual(report["errors"][0]["section"], "docker")
        self.assertNotIn("minio", report)

    def test_local_path_with_refresh_is_scanned_on_a_schedule(self):
        """refresh_seconds 를 둔 경로는 주기 안에서는 마지막 결과를 낸다. fresh(지금 확인)는 바로 훑는다."""
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a").mkdir(); (Path(tmp) / "a" / "x@1.md").write_text("doc")
            settings = cfg.parse({"node": "app", "minio": {"events": False, "weekly": False, "inventory": False},
                                  "local": {"paths": [{"path": tmp, "label": "/srv/docs", "refresh_seconds": 600,
                                                       "note": "캐시"},
                                                      {"path": tmp, "label": "/srv/live"}]}})
            builder = run.Builder(settings, s3=None, docker_client=None)
            first = builder.build()["local"]["paths"]
            self.assertEqual((first[0]["files"], first[0]["refresh_seconds"], first[0]["note"]), (1, 600, "캐시"))
            self.assertNotIn("cached", first[0])
            (Path(tmp) / "a" / "y@2.md").write_text("doc2")
            second = builder.build()["local"]["paths"]
            self.assertEqual((second[0]["files"], second[0]["cached"]), (1, True))       # 캐시 — 새 파일을 아직 모른다
            self.assertEqual(second[0]["scanned_at"], first[0]["scanned_at"])
            self.assertEqual(second[1]["files"], 2)                                      # refresh 0 인 경로는 매번 훑는다
            self.assertNotIn("cached", second[1])
            third = builder.build(fresh=True)["local"]["paths"]
            self.assertEqual(third[0]["files"], 2)
            self.assertNotIn("cached", third[0])

    def test_full_inventory_only_on_force_and_then_sticks(self):
        s3 = seeded_s3()
        settings = cfg.parse({"node": "data", "minio": {"events": False, "weekly": False, "curated": False}})
        builder = run.Builder(settings, s3=s3, docker_client=None)
        builder.build(); builder.build()
        self.assertEqual(s3.list_calls, 0)                                   # 보고서는 목록을 안 긁는다 (weekly·curated 의 _ops LIST 는 끔)
        self.assertEqual(builder.full_inventory(force=False), {"available": False})
        inv = builder.full_inventory(force=True)
        self.assertTrue(inv["available"])
        self.assertEqual(inv["completed_runs"][0]["prefix"], "depsdev/v1/projects/snapshot=2026-09-21/run_id=r")
        calls = s3.list_calls
        self.assertEqual(builder.full_inventory(force=False)["listed_at"], inv["listed_at"])
        self.assertEqual(s3.list_calls, calls)                               # 누르기 전엔 마지막 결과 그대로
        self.assertEqual(builder.build()["minio"]["inventory"]["available"], True)


if __name__ == "__main__":
    unittest.main()
