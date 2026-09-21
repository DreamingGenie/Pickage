"""적재 전 검사가 **엉뚱한 회차**와 **손상된 파일**을 막는지 본다 (S15P21A506-361).

깨지면 알게 되는 것 — 경로만 맞고 내용이 다른 산출물이 그대로 게시된다. 표는 전량 교체라
한 번 잘못 넣으면 이전 회차가 남아 있지 않다.

DB 도 MinIO 도 건드리지 않는다. 실제 게시 경로는 --verify-only 로 따로 확인한다.

    .venv-bq/Scripts/python.exe pipeline/dependent_transitions/test_load.py
"""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

# pipeline 은 namespace package 라 저장소 루트를 경로에 넣으면 import 된다.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline.dependent_transitions.load import (  # noqa: E402
    DATASET, PARQUET, check_manifest, check_parquet, parse_args)

SNAPSHOT = "2026-08-31"
RUN_ID = "dependent-transitions-20260917-v1"


def manifest(**over):
    base = {
        "dataset": DATASET, "snapshot": SNAPSHOT, "run_id": RUN_ID,
        "files": [{"file": PARQUET, "rows": 899964, "bytes": 5740220, "sha256": "ab" * 32}],
    }
    base.update(over)
    return base


class CheckManifest(unittest.TestCase):
    """경로만 믿지 않는다 — 객체를 손으로 옮기면 경로와 내용이 어긋난다."""

    def test_맞으면_parquet_항목을_돌려준다(self):
        entry = check_manifest(manifest(), SNAPSHOT, RUN_ID)
        self.assertEqual(entry["rows"], 899964)

    def test_다른_회차의_manifest_는_거부한다(self):
        for field, value in (("dataset", "package-dependents"),
                             ("snapshot", "2026-07-31"),
                             ("run_id", "dependent-transitions-20260916-v1")):
            with self.subTest(field=field):
                with self.assertRaises(SystemExit) as cm:
                    check_manifest(manifest(**{field: value}), SNAPSHOT, RUN_ID)
                self.assertIn(field, str(cm.exception))

    def test_parquet_항목이_하나가_아니면_거부한다(self):
        with self.assertRaises(SystemExit):
            check_manifest(manifest(files=[]), SNAPSHOT, RUN_ID)
        entry = {"file": PARQUET, "rows": 1, "bytes": 1, "sha256": "aa"}
        with self.assertRaises(SystemExit):
            check_manifest(manifest(files=[entry, entry]), SNAPSHOT, RUN_ID)

    def test_필수_키가_없으면_거부한다(self):
        for key in ("rows", "sha256", "bytes"):
            with self.subTest(key=key):
                entry = {"file": PARQUET, "rows": 1, "bytes": 1, "sha256": "aa"}
                del entry[key]
                with self.assertRaises(SystemExit) as cm:
                    check_manifest(manifest(files=[entry]), SNAPSHOT, RUN_ID)
                self.assertIn(key, str(cm.exception))


class CheckParquet(unittest.TestCase):
    """받아 온 파일이 manifest 가 말한 그 파일인가."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "x.parquet"
        self.path.write_bytes(b"hello")
        self.addCleanup(self.dir.cleanup)

    def entry(self, **over):
        base = {"bytes": 5, "sha256": hashlib.sha256(b"hello").hexdigest()}
        base.update(over)
        return base

    def test_맞으면_통과한다(self):
        check_parquet(self.path, self.entry())

    def test_크기가_다르면_거부한다(self):
        with self.assertRaises(SystemExit):
            check_parquet(self.path, self.entry(bytes=6))

    def test_해시가_다르면_거부한다(self):
        """크기가 같아도 내용이 다를 수 있다 — 같은 길이의 다른 회차 파일."""
        with self.assertRaises(SystemExit) as cm:
            check_parquet(self.path, self.entry(sha256="cd" * 32))
        self.assertIn("SHA-256", str(cm.exception))


class ParseArgs(unittest.TestCase):

    BASE = ["--snapshot", SNAPSHOT, "--run-id", RUN_ID,
            "--database", "pickage", "--docker-container", "pg"]

    def test_execution_id_는_회차에서_만든다(self):
        args = parse_args(self.BASE)
        self.assertEqual(args.execution_id, f"{DATASET}-{SNAPSHOT}-{RUN_ID}")

    def test_스냅샷_형식을_검사한다(self):
        with self.assertRaises(SystemExit):
            parse_args(["--snapshot", "2026-8-31", "--run-id", RUN_ID,
                        "--database", "pickage", "--docker-container", "pg"])

    def test_run_id_에_경로_문자를_허용하지_않는다(self):
        """run_id 는 객체 키에 그대로 들어간다. ../ 가 섞이면 다른 접두사를 읽는다."""
        with self.assertRaises(SystemExit):
            parse_args(["--snapshot", SNAPSHOT, "--run-id", "../other/run",
                        "--database", "pickage", "--docker-container", "pg"])

    def test_대상_DB_를_반드시_지정해야_한다(self):
        with self.assertRaises(SystemExit):
            parse_args(["--snapshot", SNAPSHOT, "--run-id", RUN_ID, "--database", "pickage"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
