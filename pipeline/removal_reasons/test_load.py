"""적재 전 검사와 **빠진 행의 분류**가 맞는지 본다 (S15P21A506-396).

깨지면 알게 되는 것 —

  ① 엉뚱한 회차·손상된 파일이 그대로 게시된다. 표는 전량 교체라 한 번 잘못 넣으면
     이전 회차가 남아 있지 않다 (dependent_transitions/test_load.py 와 같은 이유)
  ② 이 회차 manifest 에는 이동쌍 산출물이 함께 들어 있다. 엉뚱한 parquet 을 집으면
     열 수가 맞지 않아 COPY 에서 터지거나, 더 나쁘게는 숫자가 뒤바뀐 채 들어간다
  ③ 전송 CSV 의 열 순서가 COPY 문과 어긋나면 removals 자리에 dependents 가 들어간다.
     DB 의 CHECK 가 막아 주지만 31분짜리 적재를 돌린 뒤에 알게 된다
  ④ 빠진 행을 경고로 내면 매 실행이 경고가 된다. 원천의 27만 행 중 적재되는 것은 9.8만
     이고 나머지는 **둘 다 조치할 수 없는 이유로** 빠진다 — 범위 밖이거나, package 에 없어
     어차피 범위 밖이거나. 경고가 상수가 되면 정작 끊어야 할 상황이 묻힌다

DB 도 MinIO 도 건드리지 않는다. 실제 게시 경로는 --verify-only 로 따로 확인한다.

    .venv-bq/Scripts/python.exe pipeline/removal_reasons/test_load.py
"""
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

# pipeline 은 namespace package 라 저장소 루트를 경로에 넣으면 import 된다.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline.removal_reasons.load import (  # noqa: E402
    DATASET, PARQUET, SOURCE_DATASET, check_manifest, check_parquet, parse_args,
    report_quality, write_transport)

SNAPSHOT = "2026-08-31"
RUN_ID = "migration-pairs-20260918-v1"
OTHER_PARQUET = "data/migration_events.parquet"


def manifest(**over):
    """실제 회차처럼 **여러 산출물이 섞인** manifest 를 만든다.

    파일 이름이 회차 안에서는 평평하다(data/<파일명>). 로컬의 data/migration_pairs/ 를
    그대로 적으면 manifest 대조가 통과하지 못한다 — ingest_derived.py 가 basename 으로
    올린다.
    """
    base = {
        "dataset": SOURCE_DATASET, "snapshot": SNAPSHOT, "run_id": RUN_ID,
        "files": [
            {"file": OTHER_PARQUET, "rows": 190665, "bytes": 4741416, "sha256": "cd" * 32},
            {"file": PARQUET, "rows": 273610, "bytes": 282968, "sha256": "ab" * 32},
        ],
    }
    base.update(over)
    return base


class CheckManifest(unittest.TestCase):
    """경로만 믿지 않는다 — 객체를 손으로 옮기면 경로와 내용이 어긋난다."""

    def test_섞인_manifest_에서_우리_parquet_만_고른다(self):
        """이 회차에는 이동쌍 산출물이 함께 있다. 그중 하나만 적재 대상이다."""
        entry = check_manifest(manifest(), SNAPSHOT, RUN_ID)
        self.assertEqual(entry["file"], PARQUET)
        self.assertEqual(entry["rows"], 273610)

    def test_회차가_자기를_부르는_이름으로_대조한다(self):
        """manifest 는 migration-pairs 이고 etl 이력은 removal-reasons 다.
        둘을 같은 이름으로 보면 정상 회차를 거부한다."""
        self.assertNotEqual(SOURCE_DATASET, DATASET)
        check_manifest(manifest(dataset=SOURCE_DATASET), SNAPSHOT, RUN_ID)
        with self.assertRaises(SystemExit):
            check_manifest(manifest(dataset=DATASET), SNAPSHOT, RUN_ID)

    def test_다른_회차의_manifest_는_거부한다(self):
        with self.assertRaises(SystemExit):
            check_manifest(manifest(snapshot="2026-09-30"), SNAPSHOT, RUN_ID)
        with self.assertRaises(SystemExit):
            check_manifest(manifest(run_id="migration-pairs-20260909-v1"), SNAPSHOT, RUN_ID)

    def test_우리_parquet_이_없으면_거부한다(self):
        with self.assertRaises(SystemExit):
            check_manifest(manifest(files=[{"file": OTHER_PARQUET, "rows": 1,
                                            "bytes": 1, "sha256": "cd" * 32}]),
                           SNAPSHOT, RUN_ID)

    def test_필수_키가_없으면_거부한다(self):
        for key in ("rows", "sha256", "bytes"):
            entry = {"file": PARQUET, "rows": 1, "bytes": 1, "sha256": "ab" * 32}
            del entry[key]
            with self.assertRaises(SystemExit, msg=key):
                check_manifest(manifest(files=[entry]), SNAPSHOT, RUN_ID)


class CheckParquet(unittest.TestCase):
    """받아 온 파일이 manifest 가 말한 그 파일인가."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = Path(self.dir.name) / "removal_by_period.parquet"
        self.path.write_bytes(b"payload-1")
        self.entry = {"file": PARQUET, "rows": 1, "bytes": self.path.stat().st_size,
                      "sha256": hashlib.sha256(b"payload-1").hexdigest()}

    def test_맞으면_통과한다(self):
        check_parquet(self.path, self.entry)

    def test_크기가_다르면_거부한다(self):
        check_parquet(self.path, self.entry)
        self.path.write_bytes(b"payload-1-longer")
        with self.assertRaises(SystemExit):
            check_parquet(self.path, self.entry)

    def test_해시가_다르면_거부한다(self):
        """크기가 같아도 내용이 다를 수 있다 — 같은 길이의 다른 회차 파일."""
        self.path.write_bytes(b"payload-2")
        with self.assertRaises(SystemExit):
            check_parquet(self.path, self.entry)


class WriteTransport(unittest.TestCase):
    """전송 CSV 의 열 순서는 psql COPY 의 열 목록과 **같아야 한다.**"""

    def make(self, rows):
        import duckdb

        directory = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: None)
        parquet = directory / "removal_by_period.parquet"
        con = duckdb.connect()
        con.execute("""CREATE TABLE t(period VARCHAR, removed_pkg VARCHAR, removals INT,
                       removals_no_replacement INT, removals_with_replacement INT, dependents INT)""")
        for row in rows:
            con.execute("INSERT INTO t VALUES (?, ?, ?, ?, ?, ?)", list(row))
        con.execute(f"COPY t TO '{parquet.as_posix()}' (FORMAT PARQUET)")
        con.close()
        return parquet, directory / "out.csv"

    def test_열_순서와_이름이_COPY_문과_맞는다(self):
        """removed_pkg 가 target 으로 앞에 오고, t1·t2 는 싣지 않는다.
        어긋나면 removals 자리에 dependents 가 들어가 DB CHECK 에서야 걸린다."""
        parquet, out = self.make([("3y", "left-pad", 10, 7, 3, 6)])
        self.assertEqual(write_transport(parquet, out), 1)
        self.assertEqual(out.read_text(encoding="utf-8").strip(),
                         "left-pad,3y,10,7,3,6")

    def test_구간_이름_순으로_정렬한다(self):
        parquet, out = self.make([("5y", "b", 2, 1, 1, 1), ("1y", "a", 1, 1, 0, 1),
                                  ("1y", "b", 3, 2, 1, 2)])
        self.assertEqual(write_transport(parquet, out), 3)
        self.assertEqual([line.split(",")[:2]
                          for line in out.read_text(encoding="utf-8").splitlines()],
                         [["a", "1y"], ["b", "1y"], ["b", "5y"]])

    def test_비어_있으면_거부한다(self):
        parquet, out = self.make([])
        with self.assertRaises(SystemExit):
            write_transport(parquet, out)


class ReportQuality(unittest.TestCase):
    """빠진 행을 **경고 없이** 갈라 보여 준다.

    2026-09-18 로컬 실측값을 기본으로 쓴다. 처음에는 이름 미해결을 경고로 냈는데,
    실제로 돌려 보니 17,433종이 걸려 매 실행이 경고가 됐다. 그 수는 조치할 수 있는
    항목이 아니다 — dependent_transition 이 package 를 FK 로 참조하므로 package 에 없는
    이름은 어차피 범위 밖이다.
    """

    def report(self, **over):
        quality = {"staged_rows": 273610, "staged_targets": 132686,
                   "named_rows": 236412, "named_targets": 115253,
                   "loaded_rows": 97853, "loaded_targets": 42382,
                   "unresolved_targets": 17433, "scope_targets": 97745,
                   "out_of_scope_rows": 138559, "out_of_scope_targets": 72871}
        quality.update(over)
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            report_quality(quality)
        return buffer.getvalue()

    def test_경고를_붙이지_않는다(self):
        """빠진 행 둘 다 조치할 수 없다. 경고로 내면 매 실행이 경고가 되어
        정작 끊어야 할 상황(범위가 비었다·0행 적재)이 묻힌다."""
        self.assertNotIn("경고", self.report())

    def test_어디서_얼마나_빠졌는지_네_줄이_다_나온다(self):
        """한 줄이라도 빠지면 '왜 27만이 9만이 됐나' 를 로그만 보고 답할 수 없다."""
        text = self.report()
        for piece in ("273,610", "138,559", "37,198", "97,853"):
            self.assertIn(piece, text, piece)

    def test_이름_미해결도_범위_밖이라고_적는다(self):
        """이 문장이 없으면 다음 사람이 17,433종을 고치려 든다."""
        self.assertIn("어차피 범위 밖", self.report())

    def test_범위_커버리지를_낸다(self):
        """회차끼리 비교할 수 있는 유일한 수다. 갑자기 줄면 한쪽 적재가 어긋난 것이다.

        분모가 99,996(계산 대상)이 아니라 97,745 인 것에 주의 — 유지·유입·이탈 적재 자체가
        package 에 없는 2,251개를 못 붙였다. 범위는 계산이 아니라 **DB 에 실제로 들어간 것**이
        정한다."""
        text = self.report()
        self.assertIn("42,382 / 97,745", text)
        self.assertIn("43.4%", text)

    def test_scope_targets_가_없으면_커버리지를_생략한다(self):
        """옛 회차의 execution_report 를 다시 읽어도 죽지 않아야 한다."""
        text = self.report(scope_targets=None)
        self.assertNotIn("커버리지", text)

    def test_비면_아무_말도_하지_않는다(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            report_quality({})
        self.assertEqual(buffer.getvalue(), "")


class ParseArgs(unittest.TestCase):
    base = ["--snapshot", SNAPSHOT, "--run-id", RUN_ID,
            "--database", "pickage", "--psql", "psql"]

    def test_execution_id_는_회차에서_만든다(self):
        args = parse_args(self.base)
        self.assertEqual(args.execution_id, f"{DATASET}-{SNAPSHOT}-{RUN_ID}")

    def test_스냅샷_형식을_검사한다(self):
        with self.assertRaises(SystemExit):
            parse_args(["--snapshot", "2026-8-31", "--run-id", RUN_ID,
                        "--database", "pickage", "--psql", "psql"])

    def test_run_id_에_경로_문자를_허용하지_않는다(self):
        """run_id 는 객체 키에 그대로 들어간다. ../ 가 섞이면 다른 접두사를 읽는다."""
        with self.assertRaises(SystemExit):
            parse_args(["--snapshot", SNAPSHOT, "--run-id", "../other",
                        "--database", "pickage", "--psql", "psql"])

    def test_대상_DB_를_반드시_지정해야_한다(self):
        with self.assertRaises(SystemExit):
            parse_args(["--snapshot", SNAPSHOT, "--run-id", RUN_ID, "--database", "pickage"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
