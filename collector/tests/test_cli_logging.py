from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from collector.cli import build_parser
from collector.config import PACKAGE_DIR


class CliLoggingTests(unittest.TestCase):
    def test_default_paths_stay_inside_collector_component(self):
        args = build_parser().parse_args(["sources"])

        self.assertEqual(Path(args.env_file), PACKAGE_DIR / ".env.local")
        self.assertEqual(Path(args.var_dir), PACKAGE_DIR / "var")
        self.assertEqual(
            Path(args.local_policy),
            PACKAGE_DIR / "config" / "provider_policies.local.json",
        )
        self.assertEqual(
            Path(args.quota_config),
            PACKAGE_DIR / "config" / "quota_limits.local.json",
        )
        self.assertTrue((PACKAGE_DIR / ".env.example").is_file())

    def test_collect_file_keeps_stdout_json_and_writes_json_logs_to_stderr(self):
        csv_body = (
            '"고유번호","환승시작역","환승시작 코드","환승시작 호선",'
            '"하차 열차 방면","하차위치(호차)","하차위치(문)","환승종료역",'
            '"환승종료역 코드","환승종료 호선","환승 열차 방면",'
            '"환승 승차위치(호차)","환승 승차위치(문)","소요시간"\n'
            '1,서울역,"0150","1",시청 방면,"1","1",서울역,"4201",'
            '공항철도,공덕 방면,"3","2","10:00"\n'
        ).encode("cp949")
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "transfer.csv"
            input_path.write_bytes(csv_body)
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "collector",
                    "--var-dir",
                    str(Path(tmpdir) / "runtime"),
                    "--log-format",
                    "json",
                    "--log-level",
                    "INFO",
                    "collect-file",
                    "--source",
                    "seoul-subway-transfer-file",
                    "--input",
                    str(input_path),
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual(summary["row_count"], 1)
        records = [json.loads(line) for line in result.stderr.splitlines() if line]
        events = {record["event"] for record in records}
        self.assertIn("collection.started", events)
        self.assertIn("file.parsed", events)
        self.assertIn("validation.finished", events)
        self.assertIn("collection.finished", events)
        for record in records:
            self.assertIn("timestamp", record)
            self.assertIn("context", record)

    def test_cli_configuration_error_is_structured_and_stdout_stays_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_path = Path(tmpdir) / "route.txt"
            bad_path.write_text("not an xlsx", encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "collector",
                    "--var-dir",
                    str(Path(tmpdir) / "runtime"),
                    "--log-format",
                    "json",
                    "collect-file",
                    "--source",
                    "seoul-bus-route-master",
                    "--input",
                    str(bad_path),
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

        self.assertEqual(result.returncode, 4)
        self.assertEqual(result.stdout, "")
        records = [json.loads(line) for line in result.stderr.splitlines() if line]
        self.assertEqual(records[-1]["event"], "cli.command_failed")
        self.assertEqual(records[-1]["context"]["error_type"], "ValueError")


if __name__ == "__main__":
    unittest.main()
