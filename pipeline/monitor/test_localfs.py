import os
import tempfile
import time
import unittest
from pathlib import Path

from . import localfs


class ScanPathTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.now = time.time()
        old = self.now - 3 * 86400
        self._file("downloads-weekly/2026-09-14/raw/a.json", b"x" * 100, old)
        self._file("downloads-weekly/2026-09-21/raw/b.json", b"y" * 50, self.now - 60)
        self._file("downloads-weekly/2026-09-21/logs/downloads_weekly.log", b"line\n", self.now - 30)
        self._file("raw/projects/snapshot=2026-09-14/p.parquet", b"z" * 10, old + 3600)   # a.json 보다 한 시간 뒤

    def tearDown(self):
        self.tmp.cleanup()

    def _file(self, rel: str, body: bytes, mtime: float):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        os.utime(path, (mtime, mtime))

    def test_totals_entries_and_new_window(self):
        out = localfs.scan_path(str(self.root), "/srv/x", now_epoch=self.now,
                                window_hours=24, max_new_files=10, max_entries=10)
        self.assertEqual(out["label"], "/srv/x")
        self.assertEqual(out["files"], 4)
        self.assertEqual(out["bytes"], 165)
        names = [e["name"] for e in out["entries"]]
        self.assertEqual(names[0], "downloads-weekly")     # 최근에 바뀐 것이 먼저
        self.assertEqual(out["new"]["files"], 2)
        self.assertEqual(out["new"]["bytes"], 55)
        self.assertEqual(out["new"]["list"][0]["path"], "downloads-weekly/2026-09-21/logs/downloads_weekly.log")
        self.assertIsNotNone(out["disk"])
        # 가장 오래된 것부터. 항목 표에도 '가장 오래된' 시각이 붙는다 — 캐시를 언제부터 채웠는지
        self.assertEqual([f["path"] for f in out["oldest"][:2]],
                         ["downloads-weekly/2026-09-14/raw/a.json", "raw/projects/snapshot=2026-09-14/p.parquet"])
        entry = next(e for e in out["entries"] if e["name"] == "downloads-weekly")
        self.assertLess(entry["oldest"], entry["latest"])

    def test_lists_are_bounded_during_the_walk(self):
        """20만 파일을 훑어도 목록은 max_new_files 개만 든다 — 순회 중에 잘라 낸다."""
        out = localfs.scan_path(str(self.root), "/srv/x", now_epoch=self.now,
                                window_hours=24, max_new_files=1, max_entries=10)
        self.assertEqual(out["new"]["files"], 2)                     # 개수는 다 센다
        self.assertEqual(len(out["new"]["list"]), 1)                 # 목록은 가장 최근 하나
        self.assertEqual(out["new"]["list"][0]["path"], "downloads-weekly/2026-09-21/logs/downloads_weekly.log")
        self.assertEqual(len(out["oldest"]), 1)
        self.assertEqual(out["oldest"][0]["path"], "downloads-weekly/2026-09-14/raw/a.json")

    def test_missing_path_is_reported_not_raised(self):
        out = localfs.scan_path(str(self.root / "nope"), "/srv/nope", now_epoch=self.now,
                                window_hours=24, max_new_files=10, max_entries=10)
        self.assertTrue(out["missing"])


class TailTest(unittest.TestCase):
    def test_tail_reads_only_the_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "big.log"
            path.write_text("".join(f"line {i}\n" for i in range(20000)), encoding="utf-8")
            lines = localfs.tail_lines(path, 3)
            self.assertEqual(lines, ["line 19997", "line 19998", "line 19999"])

    def test_scan_logs_orders_by_mtime_and_counts_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "w1").mkdir(); (root / "w2").mkdir()
            a = root / "w1" / "s.log"; a.write_text("ok\nERROR one\n")
            b = root / "w2" / "s.log"; b.write_text("fine\n")
            now = time.time()
            os.utime(a, (now - 100, now - 100)); os.utime(b, (now, now))
            rows = localfs.scan_logs([str(root / "*" / "*.log")], tail=5, error_pattern=r"ERROR",
                                     max_logs=5, strip_prefix=str(root).replace(os.sep, "/"))
            self.assertEqual([r["path"] for r in rows], ["/w2/s.log", "/w1/s.log"])
            self.assertEqual(rows[1]["error_lines"], 1)


if __name__ == "__main__":
    unittest.main()
