"""fetch_derived.py 단위 시험 — 실제 S3 없이 포인터 읽기와 키 조합만 본다 (S15P21A506-402).

  python -m unittest discover -s pipeline/minio -v

FakeS3 는 test_ingest_derived.py 의 것을 그대로 재사용한다 — 조건부 PUT 은 안 쓰지만
get_object 하나만 있으면 이 시험엔 충분하다.
"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_ingest_derived import FakeS3  # noqa: E402

import fetch_derived  # noqa: E402


class FetchDerived(unittest.TestCase):
    def _run(self, argv):
        old_argv = sys.argv
        sys.argv = ["fetch_derived.py"] + argv
        try:
            fetch_derived.main()
        finally:
            sys.argv = old_argv

    def test_downloads_object_named_by_current_pointer(self):
        """깨지면: 다른 run 의 파일을 받아오거나, 포인터가 가리키는 이름과 다른 경로를 본다."""
        pointer = {
            "collected_date": "2026-09-08",
            "manifest_sha256": "deadbeef",
            "run_id": "package-text-20260908-v1",
            "run_path": "collected_date=2026-09-08/run_id=package-text-20260908-v1",
        }
        key = ("ecosystems-keywords/v1/package-text/"
               "collected_date=2026-09-08/run_id=package-text-20260908-v1/data/package_text.parquet")
        fake = FakeS3({
            "ecosystems-keywords/v1/package-text/_current.json": json.dumps(pointer).encode(),
            key: b"parquet-bytes",
        })
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "out.parquet")
            with mock.patch("fetch_derived.client", return_value=fake):
                self._run(["--dataset", "package-text", "--out", out])
            with open(out, "rb") as f:
                self.assertEqual(f.read(), b"parquet-bytes")

    def test_refuses_dataset_without_pointer(self):
        """포인터가 없는 데이터셋은 "최신"을 정의할 방법이 없어 아예 거부한다."""
        with mock.patch("fetch_derived.client"):
            with self.assertRaises(SystemExit):
                self._run(["--dataset", "dependent-transitions", "--out", "x"])

    def test_refuses_dataset_without_fixed_object_name(self):
        """pointer 는 있어도 object_name 이 고정 안 된 데이터셋(회차마다 파일 여러 개)은 거부한다."""
        with mock.patch("fetch_derived.client"):
            with self.assertRaises(SystemExit):
                self._run(["--dataset", "peer-similarity", "--out", "x"])


if __name__ == "__main__":
    unittest.main()
