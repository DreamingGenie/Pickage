"""적재 전 검사가 **엉뚱한 입력**과 **적재 금지 데이터셋**을 막는지 본다 (S15P21A506-424).

깨지면 알게 되는 것 — 표는 전량 교체라 한 번 잘못 넣으면 이전 회차가 남아 있지 않다. 그리고
이 적재기는 형제들과 달리 manifest 가 없다. 입력이 git 의 CSV 라 **열 구성과 디렉터리 이름이
계약의 전부**다. 그 둘이 어긋나면 막아 주는 것이 없다.

DB 도 MinIO 도 건드리지 않는다. 실제 게시 경로는 --verify-only 로 따로 확인한다.

    .venv-bq/Scripts/python.exe pipeline/migration_pairs/test_load.py
"""
import csv
import io
from pathlib import Path
import sys
import tempfile
import unittest

# pipeline 은 namespace package 라 저장소 루트를 경로에 넣으면 import 된다.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline.migration_pairs.load import (  # noqa: E402
    COLUMNS, CSV_NAME, PRIMARY_KIND, SOURCES, parse_args, read_source)

ROW = {
    "from_pkg": "moment", "to_pkg": "dayjs", "votes": "19.3", "co_events": "22",
    "removal_events": "32", "publisher_months": "22", "dependents": "22", "a_pct": "68.75",
    "b_pct": "0.0023", "lift": "29771.0", "share_pct": "60.4", "share_pm_pct": "43.1",
    "bidirectional": "false", "first_seen": "2015-02-16", "last_seen": "2015-11-16",
}


def write_csv(directory: Path, rows, *, columns=COLUMNS, bom=True):
    """빌더가 내는 것과 같은 모양으로 쓴다 — UTF-8 BOM 이 붙는다."""
    path = directory / CSV_NAME
    with path.open("w", encoding="utf-8-sig" if bom else "utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row[column] for column in columns})
    return path


def read(rows, **kwargs):
    """read_source 를 임시 디렉터리에서 돌리고 (회차정보, 전송행들) 을 돌려준다."""
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        write_csv(directory, rows, **kwargs)
        buffer = io.StringIO()
        entry = read_source("regular", directory, "2026-08-31",
                            csv.writer(buffer, lineterminator="\n"))
        return entry, list(csv.reader(io.StringIO(buffer.getvalue())))


class ReadSource(unittest.TestCase):
    def test_BOM_을_벗기고_읽는다(self):
        """빌더가 엑셀 호환으로 BOM 을 붙인다. 그냥 읽으면 첫 열 이름이 '﻿from_pkg' 가
        되어 KeyError 가 난다 — 그것도 헤더 검사를 통과한 뒤에 난다."""
        entry, sent = read([ROW])
        self.assertEqual(entry["rows"], 1)
        self.assertEqual(sent[0][2], "moment")

    def test_dep_kind_와_기준일을_앞에_붙인다(self):
        """CSV 에는 이 두 열이 없다. 디렉터리로만 구분되므로 적재기가 부여한다
        (S15P21A506-211 결정 3-1)."""
        _, sent = read([ROW])
        self.assertEqual(sent[0][:2], ["regular", "2026-08-31"])
        self.assertEqual(len(sent[0]), len(COLUMNS) + 2)

    def test_열_구성이_다르면_거부한다(self):
        """빌더의 SELECT_COLS 가 바뀌면 열이 밀린 채 적재된다. DB CHECK 가 일부를 잡지만
        (votes <= co_events 등) 같은 타입끼리 밀리면 통과해 버린다."""
        shuffled = tuple(reversed(COLUMNS))
        with self.assertRaises(SystemExit) as cm:
            read([ROW], columns=shuffled)
        self.assertIn("열 구성이 계약과 다르다", str(cm.exception))

    def test_자기_자신으로_가는_쌍을_거부한다(self):
        """package 를 조인해야 해서 DB CHECK 로는 볼 수 없는 자리다. 들어오면 화면이
        'X 에서 X 로' 를 그린다."""
        with self.assertRaises(SystemExit) as cm:
            read([ROW, dict(ROW, to_pkg="moment")])
        self.assertIn("자기 자신", str(cm.exception))

    def test_빈_CSV_를_거부한다(self):
        with self.assertRaises(SystemExit) as cm:
            read([])
        self.assertIn("비어 있다", str(cm.exception))

    def test_파일이_없으면_어느_종류인지_말한다(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit) as cm:
                read_source("dev", Path(tmp), "2026-09-16", csv.writer(io.StringIO()))
        self.assertIn("dep_kind=dev", str(cm.exception))


class Sources(unittest.TestCase):
    """**적재하면 안 되는 데이터셋이 들어오는 것을 막는다** (S15P21A506-211 결정 3-2).

    깨지면 알게 되는 것 — legacy 는 재분류 과대 계상 12.15% 를 재려고 만든 대조군이라,
    적재하면 같은 이동이 두 번 세어진다. regular_260914 는 .gitignore 에 있어 다른 PC 에서
    적재기가 돌지 않는다. 둘 다 이름이 비슷해 손이 미끄러지기 쉽다.
    """

    def test_대조군과_비추적_데이터셋은_없다(self):
        directories = {directory for directory, _, _ in SOURCES.values()}
        for forbidden in ("datasets/migration_pairs_regular_legacy_260914",
                          "datasets/migration_pairs_regular_260914"):
            self.assertNotIn(forbidden, directories)

    def test_주력_종류가_SOURCES_에_있다(self):
        """etl 이력의 snapshot_at 을 여기서 가져온다. 이름이 어긋나면 KeyError 로 죽는다."""
        self.assertIn(PRIMARY_KIND, SOURCES)

    def test_기준일이_종류마다_다르다(self):
        """두 원천의 스냅샷이 9일 이상 다르다(S15P21A506-211 결정 3-4). 같아지면 둘 중
        하나를 잘못 적은 것이다 — 그래야 행마다 snapshot_at 을 두는 이유가 성립한다."""
        snapshots = {snapshot for _, snapshot, _ in SOURCES.values()}
        self.assertEqual(len(snapshots), len(SOURCES))

    def test_입력_디렉터리가_저장소에_있다(self):
        """git 에 추적되는 CSV 를 읽는 것이 이 적재기의 전제다. 데이터셋을 옮기거나
        .gitignore 에 넣으면 여기서 걸린다."""
        root = Path(__file__).resolve().parents[2]
        for kind, (directory, _, _) in SOURCES.items():
            with self.subTest(kind=kind):
                self.assertTrue((root / directory / CSV_NAME).exists(),
                                f"{directory}/{CSV_NAME} 이 없다")


class ParseArgs(unittest.TestCase):
    BASE = ["--run-id", "migration-pairs-20260922-v1", "--database", "pickage",
            "--docker-container", "pickage-local-postgres-1"]

    def test_execution_id_는_회차에서_유도한다(self):
        args = parse_args(self.BASE)
        self.assertEqual(args.execution_id, "migration-pairs-migration-pairs-20260922-v1")

    def test_대상을_주지_않으면_거부한다(self):
        """--docker-container 도 --psql 도 없으면 어디에 게시할지 알 수 없다."""
        with self.assertRaises(SystemExit):
            parse_args(["--run-id", "r", "--database", "pickage"])

    def test_회차_이름에_이상한_글자를_막는다(self):
        """psql -v 로 넘어가는 값이다."""
        with self.assertRaises(SystemExit):
            parse_args(["--run-id", "a b;c", "--database", "pickage",
                        "--docker-container", "pickage-local-postgres-1"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
