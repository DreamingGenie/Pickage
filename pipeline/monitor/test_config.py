import unittest

from . import config as cfg

MINIMAL = {"node": "data"}


class ParseTest(unittest.TestCase):
    def test_defaults_fill_in(self):
        s = cfg.parse(MINIMAL)
        self.assertEqual(s.node, "data")
        self.assertEqual(s.listen, ["127.0.0.1:19998"])
        self.assertEqual(s.peers, {})
        self.assertTrue(s.minio.inventory)
        self.assertTrue(s.minio.events)
        self.assertEqual(s.minio.events_retention_hours, 24)
        self.assertEqual(s.inventory_timeout_seconds, 600)
        self.assertEqual(s.local.paths, [])
        # 에러 줄 기준은 로그 종류별 — 컨테이너 3줄, 단계 로그 1줄
        self.assertEqual((s.docker.error_min_lines, s.local.error_min_lines), (3, 1))
        self.assertEqual(s.local.error_pattern, s.docker.error_pattern)
        with self.assertRaises(cfg.ConfigError):
            cfg.parse({**MINIMAL, "docker": {"error_ignore_pattern": "("}})          # 깨진 정규식은 시작 때 멈춘다
        with self.assertRaises(cfg.ConfigError):
            cfg.parse({**MINIMAL, "local": {"error_min_lines": -1}})

    def test_paths_become_specs(self):
        s = cfg.parse({"node": "data", "local": {"paths": [
            {"path": "/host/srv/x", "label": "/srv/x"}, {"path": "/host/y"},
            {"path": "/host/docs", "refresh_seconds": 600, "note": "RAG 캐시"}]}})
        self.assertEqual([(p.path, p.label) for p in s.local.paths],
                         [("/host/srv/x", "/srv/x"), ("/host/y", "/host/y"), ("/host/docs", "/host/docs")])
        self.assertEqual([(p.refresh_seconds, p.note) for p in s.local.paths],
                         [(0, ""), (0, ""), (600, "RAG 캐시")])
        with self.assertRaises(cfg.ConfigError):
            cfg.parse({"node": "data", "local": {"paths": [{"path": "/x", "refresh": 5}]}})   # 오타는 멈춘다
        with self.assertRaises(cfg.ConfigError):
            cfg.parse({"node": "data", "local": {"paths": [{"path": "/x", "refresh_seconds": -1}]}})

    def test_unknown_key_is_an_error_not_silence(self):
        with self.assertRaises(cfg.ConfigError):
            cfg.parse({"node": "data", "minio": {"deptth": 3}})
        with self.assertRaises(cfg.ConfigError):
            cfg.parse({"node": "data", "web_dir": "/web"})      # 옛 키. 조용히 무시되면 안 된다

    def test_node_name_must_be_safe(self):
        for bad in ("", "Data", "app node", "../x"):
            with self.assertRaises(cfg.ConfigError):
                cfg.parse({"node": bad})

    def test_listen_and_peers_validated(self):
        s = cfg.parse({"node": "app", "listen": ["127.0.0.1:19998", "172.26.6.235:19998"],
                       "peers": {"data": "http://172.26.8.249:19998"}})
        self.assertEqual(cfg.parse_listen(s.listen[1]), ("172.26.6.235", 19998))
        for bad in ({"listen": ["19998"]}, {"peers": {"app": "http://x"}}, {"peers": {"data": "x:19998"}},
                    {"peers": {"Bad Name": "http://x"}}):
            with self.assertRaises(cfg.ConfigError):
                cfg.parse({"node": "app", **bad})

    def test_pointer_needs_bucket(self):
        with self.assertRaises(cfg.ConfigError):
            cfg.parse({"node": "data", "minio": {"pointers": ["_current.json"]}})

    def test_bad_regex_fails_early(self):
        with self.assertRaises(Exception):
            cfg.parse({"node": "data", "docker": {"name_pattern": "("}})


class CredentialsTest(unittest.TestCase):
    def test_reads_pickage_s3_names(self):
        creds = cfg.s3_credentials({"PICKAGE_S3_ENDPOINT": "http://m:9000",
                                    "PICKAGE_S3_ACCESS_KEY": "a", "PICKAGE_S3_SECRET_KEY": "s"})
        self.assertEqual((creds.endpoint, creds.access_key, creds.secret_key), ("http://m:9000", "a", "s"))

    def test_missing_names_are_listed(self):
        with self.assertRaises(cfg.ConfigError) as caught:
            cfg.s3_credentials({"PICKAGE_S3_ENDPOINT": "http://m:9000"})
        self.assertIn("PICKAGE_S3_ACCESS_KEY", str(caught.exception))
        self.assertIn("PICKAGE_S3_SECRET_KEY", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
