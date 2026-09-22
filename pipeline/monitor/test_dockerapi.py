import unittest

from . import dockerapi
from .test_support import FakeDocker


def frame(stream: int, payload: bytes) -> bytes:
    return bytes([stream, 0, 0, 0]) + len(payload).to_bytes(4, "big") + payload


class DemuxTest(unittest.TestCase):
    def test_strips_headers_and_keeps_order(self):
        raw = frame(1, b"out 1\n") + frame(2, b"err 1\n") + frame(1, b"out 2\n")
        self.assertEqual(dockerapi.demux(raw), b"out 1\nerr 1\nout 2\n")

    def test_partial_tail_is_kept(self):
        raw = frame(1, b"whole\n") + b"\x01\x00\x00\x00\x00\x00\x00\x10part"
        self.assertTrue(dockerapi.demux(raw).endswith(b"part"))

    def test_tty_output_passes_through(self):
        raw = b"plain text without headers\nsecond\n"
        self.assertEqual(dockerapi.demux(raw), raw)

    def test_split_lines_drops_blank_and_cr(self):
        self.assertEqual(dockerapi.split_lines(b"a\r\n\n b \n"), ["a", " b "])


class SummarizeTest(unittest.TestCase):
    def test_picks_display_fields(self):
        listing = {"Id": "abc", "Names": ["/pickage-data-minio-1"], "Image": "minio/minio:X",
                   "State": "running", "Status": "Up 3 hours"}
        detail = {"State": {"Status": "running", "ExitCode": 0, "OOMKilled": False,
                            "StartedAt": "2026-09-20T01:00:00Z", "FinishedAt": "0001-01-01T00:00:00Z",
                            "Health": {"Status": "healthy"}},
                  "RestartCount": 2, "Config": {"Tty": False, "Labels": {"com.docker.compose.service": "minio"}}}
        row = dockerapi.summarize(listing, detail)
        self.assertEqual(row["name"], "pickage-data-minio-1")
        self.assertEqual(row["health"], "healthy")
        self.assertIsNone(row["finished_at"])          # 0001-01-01 은 "없음"
        self.assertEqual(row["restart_count"], 2)
        self.assertEqual(row["compose_service"], "minio")

    def test_count_matches(self):
        lines = ["INFO ok", "ERROR boom", "Traceback (most recent call last):", "killed by signal"]
        self.assertEqual(dockerapi.count_matches(lines, r"(?i)\b(error|traceback|killed)\b"), 3)

    def test_default_pattern_sees_korean_failure_lines(self):
        """similarity-loader 의 watch.py 는 죽지 않고 한글로만 실패를 남긴다 — 영어 표지만 보면 놓친다."""
        from . import config as cfg
        lines = ["2026-09-22T03:00:00 오류: connection reset — 1800초 뒤 다시 시도",
                 "게시 실패  depsdev/v1/similar/2026-09-21  (load.py 종료코드 1)",
                 "경고: 12 행이 이름 매칭에 실패해 빠졌다",
                 "         성공 3,120 · 실패 0   버전 행 9,000",         # 수집기 진행 줄 — 걸리면 안 된다
                 "  ! 일시 오류(시도 1): timeout. 30초 후 재시도",           # 재시도 예고 — 콜론이 없어 걸리지 않는다
                 "게시 완료 depsdev/v1/similar/2026-09-21"]
        self.assertEqual(dockerapi.count_matches(lines, cfg.ERROR_PATTERN), 3)

    def test_ignore_pattern_drops_known_noise(self):
        """재기동 직후의 Connection refused 처럼 정상으로 아는 줄은 세지 않는다."""
        lines = ["ERROR connection refused 172.26.8.249:9000", "ERROR connection refused 172.26.8.249:9000",
                 "ERROR disk full", "INFO ok"]
        self.assertEqual(dockerapi.count_matches(lines, r"(?i)error"), 3)
        self.assertEqual(dockerapi.count_matches(lines, r"(?i)error", r"(?i)connection refused.*9000"), 1)


class CollectTest(unittest.TestCase):
    def setUp(self):
        self.client = FakeDocker(
            containers=[
                {"Id": "1", "Names": ["/pickage-data-minio-1"], "Image": "minio", "State": "running", "Status": "Up"},
                {"Id": "2", "Names": ["/pickage-weekly-run"], "Image": "ingest", "State": "exited", "Status": "Exited (1)"},
                {"Id": "3", "Names": ["/unrelated"], "Image": "x", "State": "running", "Status": "Up"},
            ],
            details={
                "1": {"State": {"Status": "running", "ExitCode": 0}, "Config": {"Tty": False}, "RestartCount": 0},
                "2": {"State": {"Status": "exited", "ExitCode": 1, "FinishedAt": "2026-09-20T02:00:00Z"},
                      "Config": {"Tty": True}, "RestartCount": 0},
                "3": {"State": {"Status": "running"}, "Config": {}, "RestartCount": 0},
            },
            logs={"1": ["API: ready"], "2": ["step failed", "ERROR budget exceeded"]},
        )

    def test_filters_by_name_and_attaches_logs(self):
        out = dockerapi.collect(self.client, name_pattern="pickage", log_tail=40,
                                log_since_hours=6, error_pattern=r"(?i)error", now_epoch=1_000_000)
        names = [c["name"] for c in out["containers"]]
        self.assertEqual(names, ["pickage-data-minio-1", "pickage-weekly-run"])
        weekly = out["containers"][1]
        self.assertEqual(weekly["exit_code"], 1)
        self.assertEqual(weekly["log"]["error_lines"], 1)
        # 기준(패턴·무시·임계)이 보고서에 실린다 — 화면이 같은 기준으로 칠하고 판정한다
        self.assertEqual((out["error_pattern"], out["error_ignore_pattern"], out["error_min_lines"]), (r"(?i)error", "", 3))
        # TTY 여부가 로그 호출에 그대로 전달된다 — 틀리면 헤더 바이트가 글자로 섞인다
        self.assertEqual([c["tty"] for c in self.client.log_calls], [False, True])
        self.assertEqual(self.client.log_calls[0]["since"], 1_000_000 - 6 * 3600)

    def test_log_failure_keeps_the_row(self):
        self.client._logs.pop("1")
        out = dockerapi.collect(self.client, name_pattern="minio", log_tail=10,
                                log_since_hours=1, error_pattern="x", now_epoch=0)
        self.assertEqual(out["matched"], 1)
        self.assertIn("error", out["containers"][0]["log"])


if __name__ == "__main__":
    unittest.main()
