"""registry 수집기·변환기 단위 시험.

  .venv-bq/Scripts/python.exe -m unittest discover -s pipeline/collectors/registry -v

이 폴더에는 __init__.py 가 없어 패키지 경로(pipeline.collectors.registry.…)로는 import 되지 않는다.
discover 가 이 폴더를 sys.path 에 올려 주므로 `from collect import …` 로 쓴다.

여기 있는 시험은 전부 "깨지면 무엇을 알게 되는가"에 답이 있는 것만 넣었다. 2026-09-11 자체 리뷰에서
실제로 나온 결함이거나(회귀 방지), 계획 문서가 약속한 계약이다.
"""
import gzip
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import collect  # noqa: E402
import to_parquet  # noqa: E402

FETCHED = "2026-09-11T00:00:00+00:00"


def doc(versions, times=None):
    d = {"versions": versions}
    if times is not None:
        d["time"] = times
    return d


class ParseVersionKeys(unittest.TestCase):
    """time 의 키를 무엇까지 버전으로 받아들이는가."""

    def test_unpublished_version_kept_with_null_deps(self):
        """계획 §2-1 의 계약. []('의존 없음')로 쓰면 lag() 비교에서 '의존 전부 제거'가 된다."""
        rows, _ = collect.parse(
            doc({"1.0.0": {"dependencies": {"a": "^1"}}},
                {"created": "2020-01-01T00:00:00Z", "1.0.0": "2020-01-01T00:00:00Z", "1.0.1": "2020-02-01T00:00:00Z"}),
            "p", 1, FETCHED)
        self.assertEqual([r["Version"] for r in rows], ["1.0.0", "1.0.1"])
        gone = [r for r in rows if r["Version"] == "1.0.1"][0]
        self.assertTrue(gone["unpublished"])
        for col in ("Dependencies", "DevDependencies", "PeerDependencies", "OptionalDependencies"):
            self.assertIsNone(gone[col], col)

    def test_non_version_time_key_is_not_a_version(self):
        """실측: appdirsjs 의 time 에 'undefined' 키가 있어 2014년 발행 가짜 행이 생겼고
        그 패키지의 first_published_at 이 6년 반 틀렸다."""
        stats = {}
        rows, _ = collect.parse(
            doc({"1.0.0": {}},
                {"created": "2014-03-14T03:30:24.592Z", "modified": "2020-10-24T00:00:00Z",
                 "undefined": "2014-03-14T03:30:24.592Z", "1.0.0": "2020-10-24T00:00:00Z"}),
            "appdirsjs", 6343, FETCHED, stats)
        self.assertEqual([r["Version"] for r in rows], ["1.0.0"])
        self.assertEqual(stats["odd_time_keys"], 1)

    def test_known_non_version_keys_are_not_counted_as_odd(self):
        stats = {}
        collect.parse(doc({"1.0.0": {}}, {"created": "x", "modified": "y", "unpublished": {}, "1.0.0": "z"}),
                      "p", 1, FETCHED, stats)
        self.assertEqual(stats.get("odd_time_keys", 0), 0)


class ParseDeprecated(unittest.TestCase):
    """deprecated 는 '폐기 문구, 없으면 NULL' 이 계약이다(README 열 계약)."""

    def test_boolean_and_empty_are_normalized(self):
        """실측: 불리언 false 9,561행 · true 1,145행 · "" 4행이 문자열로 저장돼
        deprecated IS NOT NULL 이 폐기되지 않은 버전을 세고 있었다."""
        rows, _ = collect.parse(
            doc({"1.0.0": {"deprecated": False}, "1.1.0": {"deprecated": ""},
                 "1.2.0": {"deprecated": True}, "1.3.0": {"deprecated": "쓰지 마세요"},
                 "1.4.0": {}}),
            "p", 1, FETCHED)
        got = {r["Version"]: r["deprecated"] for r in rows}
        self.assertIsNone(got["1.0.0"])
        self.assertIsNone(got["1.1.0"])
        self.assertEqual(got["1.2.0"], "true")    # 문구 없는 폐기. NULL 로 바꾸면 진짜 폐기 1,145행을 잃는다
        self.assertEqual(got["1.3.0"], "쓰지 마세요")
        self.assertIsNone(got["1.4.0"])


class ParseMalformed(unittest.TestCase):
    """200 응답이라도 문서 모양이 예상과 다를 수 있다. 예외를 밖으로 흘리면 작업이 pending 으로 남아
    재시작마다 같은 패키지에서 죽는다(--retry-failed 로도 못 벗어난다)."""

    def test_non_object_document_raises_valueerror(self):
        with self.assertRaises(ValueError):
            collect.parse([1, 2, 3], "p", 1, FETCHED)

    def test_whole_package_unpublished_returns_none(self):
        rows, modified = collect.parse(
            {"time": {"modified": "2021-01-01T00:00:00Z", "unpublished": {"name": "p"}}}, "p", 1, FETCHED)
        self.assertIsNone(rows)
        self.assertEqual(modified, "2021-01-01T00:00:00Z")   # 주간 갱신(-273)이 비교에 쓴다

    def test_missing_versions_without_unpublished_raises(self):
        with self.assertRaises(ValueError):
            collect.parse({"time": {"modified": "x"}}, "p", 1, FETCHED)


class Serialize(unittest.TestCase):
    """행은 전부 만들어 인코딩까지 확인한 뒤에 써야 한다. 쓰는 도중 실패하면 체크포인트는 failed 인데
    앞부분 행만 raw 에 남고, 그 고아 행은 (Name, Version) 중복 제거로 걸러지지 않는다."""

    def test_lone_surrogate_raises_before_any_line_is_written(self):
        rows = [{"Name": "p", "Version": "1.0.0"},
                {"Name": "p", "Version": "1.1.0", "Requirement": "\ud800"},
                {"Name": "p", "Version": "1.2.0"}]
        with self.assertRaises(UnicodeEncodeError):
            collect.serialize(rows)

    def test_clean_rows_round_trip(self):
        rows = [{"Name": "차트", "Version": "1.0.0"}]
        self.assertEqual(json.loads(collect.serialize(rows)[0]), rows[0])


class LogEncoding(unittest.TestCase):
    """start_registry.cmd 는 stdout 을 로그 파일로 넘긴다. 콘솔이 아니면 인코딩이 cp949 로 정해져
    cp949 에 없는 글자 하나에 수집기가 죽는다. 끊김을 버티려고 넣은 wait_online 이 바로 그 경로였다."""

    def test_wait_online_message_encodes_on_cp949_stream(self):
        class FakeResponse:
            status_code = 200

        class FakeSession:
            def get(self, *args, **kwargs):
                return FakeResponse()

        buf = io.TextIOWrapper(io.BytesIO(), encoding="cp949")
        old = sys.stdout
        sys.stdout = buf
        try:
            collect.wait_online(FakeSession())
        finally:
            sys.stdout = old
        buf.flush()
        self.assertIn("offline", buf.buffer.getvalue().decode("cp949"))


class GzipRecovery(unittest.TestCase):
    """강제 종료로 잘린 part 를 어떻게 다루는가. 변환기가 여기서 틀리면 행이 조용히 사라진다."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def test_zero_byte_part_is_incomplete(self):
        """회전 직후 종료되면 0바이트 파일이 남는다(실측: 09-09 run 의 part-01744).
        gzip 헤더도 없어 읽을 게 없으므로 완전한 파일로 보면 안 된다."""
        p = os.path.join(self.dir, "part-00000.jsonl.gz")
        open(p, "wb").close()
        self.assertFalse(to_parquet._complete(p))

    def test_complete_part_is_complete(self):
        p = os.path.join(self.dir, "part-00001.jsonl.gz")
        with gzip.open(p, "wt", encoding="utf-8") as f:
            f.write('{"Name":"a"}\n')
        self.assertTrue(to_parquet._complete(p))

    def test_repair_keeps_whole_lines_only(self):
        """마지막 줄이 잘린 파일에서 온전한 줄까지만 살리고 원본은 .broken 으로 남긴다."""
        p = os.path.join(self.dir, "part-00002.jsonl.gz")
        with gzip.open(p, "wb") as f:
            f.write(b'{"Name":"a"}\n{"Name":"b"}\n{"Name":"c"')
        to_parquet._repair(p)
        with gzip.open(p, "rt", encoding="utf-8") as f:
            kept = [json.loads(x)["Name"] for x in f]
        self.assertEqual(kept, ["a", "b"])
        self.assertTrue(os.path.exists(p + ".broken"))


class OutputSourceGuard(unittest.TestCase):
    """--refresh-parquet 가 스모크 run 을 가리킨 채 본 Parquet 를 덮어쓰는 사고를 막는다.
    출력은 rmtree 후 교체라 되돌릴 수 없다."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def test_missing_marker_is_allowed(self):
        self.assertTrue(to_parquet.check_output_source(self.dir, "C:/x/run=A").endswith("registry_source.json"))

    def test_different_run_is_refused(self):
        with open(os.path.join(self.dir, "registry_source.json"), "w", encoding="utf-8") as f:
            json.dump({"raw": "C:/x/run=2026-09-09"}, f)
        with self.assertRaises(SystemExit):
            to_parquet.check_output_source(self.dir, "C:/x/run=smoke-2026-09-11")

    def test_same_run_is_allowed(self):
        with open(os.path.join(self.dir, "registry_source.json"), "w", encoding="utf-8") as f:
            json.dump({"raw": "C:/x/run=2026-09-09"}, f)
        to_parquet.check_output_source(self.dir, "C:/x/run=2026-09-09")

    def test_force_overrides(self):
        with open(os.path.join(self.dir, "registry_source.json"), "w", encoding="utf-8") as f:
            json.dump({"raw": "C:/x/run=2026-09-09"}, f)
        to_parquet.check_output_source(self.dir, "C:/x/run=smoke", force=True)


if __name__ == "__main__":
    unittest.main()
