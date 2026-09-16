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
import shard_targets  # noqa: E402
import status  # noqa: E402
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


class ParseShapeColumns(unittest.TestCase):
    """형태 6열(S15P21A506-366). 사전 실측에서 나온 함정만 고정한다."""

    def test_size_columns_come_from_dist_not_top_level(self):
        """unpackedSize·fileCount 는 versions[v] 가 아니라 versions[v].dist 안에 있다.
        top level 로 읽으면 두 열이 통째로 NULL 이 되고, 결측 79%가 '오래된 버전' 이라 눈에 안 띈다."""
        rows, _ = collect.parse(
            doc({"1.0.0": {"dist": {"unpackedSize": 35047, "fileCount": 7}},
                 "0.9.0": {"dist": {}},                      # 2018년 이전 발행 — 레지스트리가 계산하기 전
                 "0.8.0": {"unpackedSize": 999, "fileCount": 9}}),   # top level 에 있는 값은 쓰지 않는다
            "chalk", 9, FETCHED)
        got = {r["Version"]: (r["unpacked_size"], r["file_count"]) for r in rows}
        self.assertEqual(got["1.0.0"], (35047, 7))
        self.assertEqual(got["0.9.0"], (None, None))
        self.assertEqual(got["0.8.0"], (None, None))

    def test_size_columns_survive_odd_types(self):
        """정수가 아닌 값이 와도 Parquet 의 BIGINT 열이 깨지지 않아야 한다."""
        rows, _ = collect.parse(
            doc({"1.0.0": {"dist": {"unpackedSize": "35047", "fileCount": 7.0}},
                 "1.1.0": {"dist": {"unpackedSize": "many", "fileCount": None}},
                 "1.2.0": {"dist": "not-an-object"}}),
            "p", 1, FETCHED)
        got = {r["Version"]: (r["unpacked_size"], r["file_count"]) for r in rows}
        self.assertEqual(got["1.0.0"], (35047, 7))
        self.assertEqual(got["1.1.0"], (None, None))
        self.assertEqual(got["1.2.0"], (None, None))

    def test_out_of_range_size_becomes_null(self):
        """Parquet 의 BIGINT 를 넘거나 음수인 값은 모름으로 둔다. 4.5시간 수집 뒤의 30분짜리 변환이
        이상치 한 줄에 통째로 실패하는 것보다 그 행만 비는 게 낫다."""
        rows, _ = collect.parse(
            doc({"1.0.0": {"dist": {"unpackedSize": 2 ** 63, "fileCount": -1}},
                 "1.1.0": {"dist": {"unpackedSize": 0, "fileCount": 0}}}),
            "p", 1, FETCHED)
        got = {r["Version"]: (r["unpacked_size"], r["file_count"]) for r in rows}
        self.assertEqual(got["1.0.0"], (None, None))
        self.assertEqual(got["1.1.0"], (0, 0))      # 0 은 실제 값이다. NULL 로 바꾸면 '빈 패키지'를 잃는다

    def test_types_falls_back_to_typings(self):
        """실측: ajv 는 typings 만 있는 버전이 127개다. types 만 보면 타입 제공 버전을 과소 계상한다."""
        rows, _ = collect.parse(
            doc({"1.0.0": {"types": "./index.d.ts"},
                 "1.1.0": {"typings": "./legacy.d.ts"},
                 "1.2.0": {"types": "./a.d.ts", "typings": "./b.d.ts"},
                 "1.3.0": {}}),
            "ajv", 21, FETCHED)
        got = {r["Version"]: r["types"] for r in rows}
        self.assertEqual(got["1.0.0"], "./index.d.ts")
        self.assertEqual(got["1.1.0"], "./legacy.d.ts")
        self.assertEqual(got["1.2.0"], "./a.d.ts")     # types 가 정본
        self.assertIsNone(got["1.3.0"])

    def test_exports_is_serialized_to_json_text(self):
        """exports 는 중첩 객체(실측 dict 799 · str 15)라 열에 그대로 못 넣는다. 문자열로 적고 읽는 쪽에서 판다.
        객체를 그대로 두면 Parquet 스키마가 버전마다 달라져 변환이 실패한다."""
        rows, _ = collect.parse(
            doc({"1.0.0": {"exports": {".": {"import": "./x.mjs", "require": "./x.cjs"}}},
                 "1.1.0": {"exports": "./index.js"},
                 "1.2.0": {}}),
            "p", 1, FETCHED)
        got = {r["Version"]: r["exports"] for r in rows}
        self.assertEqual(json.loads(got["1.0.0"]), {".": {"import": "./x.mjs", "require": "./x.cjs"}})
        self.assertEqual(json.loads(got["1.1.0"]), "./index.js")
        self.assertIsNone(got["1.2.0"])

    def test_unpublished_version_has_null_shape_columns(self):
        """unpublish 된 버전은 선언을 모른다. 의존 네 열과 같은 뜻으로 6열도 NULL 이어야 한다 —
        0 이나 ''로 두면 '파일 0개', '진입점 없음' 으로 잘못 집계된다."""
        rows, _ = collect.parse(
            doc({"1.0.0": {"dist": {"unpackedSize": 10, "fileCount": 1}, "main": "./i.js"}},
                {"1.0.0": "2020-01-01T00:00:00Z", "1.0.1": "2020-02-01T00:00:00Z"}),
            "p", 1, FETCHED)
        gone = [r for r in rows if r["Version"] == "1.0.1"][0]
        self.assertTrue(gone["unpublished"])
        for col in ("unpacked_size", "file_count", "module_type", "main", "types", "exports"):
            self.assertIsNone(gone[col], col)

    def test_non_string_text_field_is_kept_as_json(self):
        """main 이 문자열이 아니면 조용히 버리지 않는다. deprecated 를 다루는 방식과 같다."""
        rows, _ = collect.parse(doc({"1.0.0": {"main": {"browser": "./b.js"}, "type": "module"}}), "p", 1, FETCHED)
        self.assertEqual(json.loads(rows[0]["main"]), {"browser": "./b.js"})
        self.assertEqual(rows[0]["module_type"], "module")


class ShardTargets(unittest.TestCase):
    """대상 분할. 여기서 틀리면 패키지가 조용히 빠지거나(수집 누락) 겹쳐서(to_parquet 가 멈춤) 사고가 늦게 드러난다."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.csv = os.path.join(self.dir, "t.csv")
        with open(self.csv, "w", encoding="utf-8", newline="") as f:
            f.write("rank,name,status" + chr(10))
            for i in range(1, 101):
                f.write(f"{i},pkg{i},active" + chr(10))

    def test_shards_partition_targets_exactly_once(self):
        parts, _ = shard_targets.shard(self.csv, 4, os.path.join(self.dir, "out"))
        names = [r["name"] for _, part in parts for r in part]
        self.assertEqual(len(names), 100)
        self.assertEqual(len(set(names)), 100)          # 겹치면 to_parquet 의 상태 표가 두 배가 된다
        self.assertEqual(sorted(names), sorted(f"pkg{i}" for i in range(1, 101)))

    def test_shards_get_the_same_rank_mix(self):
        """앞에서부터 끊으면 상위권 샤드는 문서가 크고 하위권 샤드는 CDN 이 차가워 같이 끝나지 않는다.
        돌아가며 나누면 네 샤드의 순위 평균이 거의 같다."""
        parts, _ = shard_targets.shard(self.csv, 4, os.path.join(self.dir, "out"))
        means = [sum(int(r["rank"]) for r in part) / len(part) for _, part in parts]
        # 돌아가며 나누면 샤드 평균이 1씩만 어긋난다(여기서는 49·50·51·52).
        # 앞에서부터 25개씩 끊었다면 12.5·37.5·62.5·87.5 로 75 만큼 벌어진다.
        self.assertLess(max(means) - min(means), 4, means)

    def test_duplicate_names_are_kept_once_with_the_best_rank(self):
        """실측: 상위 10만 CSV 에 이름 중복이 4건 있다. 직렬 수집은 체크포인트의 INSERT OR IGNORE 가
        하나로 합쳐 왔는데(작업 99,996건), 나눠 돌리면 두 샤드가 같은 패키지를 따로 받는다."""
        dup = os.path.join(self.dir, "dup.csv")
        with open(dup, "w", encoding="utf-8", newline="") as f:
            f.write("rank,name,status" + chr(10))
            for rank, name in [(1, "a"), (2, "b"), (3, "a"), (4, "c")]:
                f.write(f"{rank},{name},active" + chr(10))
        parts, dropped = shard_targets.shard(dup, 2, os.path.join(self.dir, "dupout"))
        rows = [r for _, part in parts for r in part]
        self.assertEqual(dropped, 1)
        self.assertEqual(sorted(r["name"] for r in rows), ["a", "b", "c"])
        self.assertEqual([r["rank"] for r in rows if r["name"] == "a"], ["1"])   # 상위 순위를 남긴다

    def test_extra_columns_are_preserved(self):
        """collect.py 가 --exclude-status 로 status 열을 본다. 분할에서 열이 떨어지면 제외가 조용히 무력화된다."""
        parts, _ = shard_targets.shard(self.csv, 4, os.path.join(self.dir, "out"))
        with open(parts[0][0], encoding="utf-8") as f:
            self.assertEqual(f.readline().strip(), "rank,name,status")


class RemainingTime(unittest.TestCase):
    """현황 창의 '남은 N시간 M분'. 값이 맞아도 표기가 깨지면 계산이 틀린 것처럼 읽힌다."""

    def test_minutes_never_reach_sixty(self):
        """시와 분을 따로 반올림하면 2.9955h 가 '2시간 60분' 이 된다."""
        self.assertEqual(status.hours_to_hm(2.9955), (3, 0))
        self.assertEqual(status.hours_to_hm(3.0), (3, 0))
        self.assertEqual(status.hours_to_hm(2.5), (2, 30))
        self.assertEqual(status.hours_to_hm(0.01), (0, 1))
        for h in (0.0, 0.004, 0.5, 1.999, 4.4999, 17.9):
            self.assertLess(status.hours_to_hm(h)[1], 60, h)


class AliveForRun(unittest.TestCase):
    """샤드별 실행 여부. 이름이 접두사로 겹치면 현황판이 엉뚱한 샤드를 RUNNING 으로 본다."""

    def test_run_name_is_matched_on_a_boundary(self):
        lines = ["python collect.py --targets a.csv --run 2026-09-16-s1 --out raw --interval 0.5",
                 "python collect.py --targets b.csv --run 2026-09-16-s10 --out raw --interval 0.5"]
        self.assertEqual(status.alive_for("2026-09-16-s1", lines), 1)
        self.assertEqual(status.alive_for("2026-09-16-s10", lines), 1)
        self.assertEqual(status.alive_for("2026-09-16-s2", lines), 0)

    def test_unknown_when_process_list_is_unavailable(self):
        """PowerShell 이 없거나 시간초과면 -1(모름)이다. 0(없음)으로 읽으면 to_parquet 가 살아 있는 part 를
        .broken 으로 옮기고, 수집기는 고아 파일에 계속 써서 그 뒤 행이 전부 사라진다."""
        self.assertEqual(status.alive_for("x", None), -1)
        orig = status.cmdlines
        status.cmdlines = lambda: None
        try:
            self.assertEqual(status.alive(), -1)
        finally:
            status.cmdlines = orig


if __name__ == "__main__":
    unittest.main()
