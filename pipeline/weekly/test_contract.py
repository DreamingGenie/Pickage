"""러너와 백엔드가 함께 지키는 규칙표를 러너 쪽에서 맞댄다.

  python -m unittest pipeline.weekly.test_contract -v

실행 주 계산·14일 창·수동 요청 대기 판정은 자바 백엔드(`WeeklyIngestService`)에도 따로 구현돼
있고, 전에는 주석("같은 규칙이어야 한다")으로만 묶여 있었다. 표는 `contract/weekly_rules.json`
하나이고 자바 쪽은 `WeeklyRulesContractTest` 가 같은 파일을 읽는다.

이 시험이 깨지면: 러너의 규칙이 표와 달라졌다. 표를 같이 고치지 않았다면 백엔드와도 달라진
것이라, 화면이 보여 주는 회차·수집 구간·"대기 중" 표시가 러너의 실제 거동과 어긋난다.
"""
import json
import unittest
from datetime import date, datetime
from pathlib import Path

from pipeline.weekly import schedule

RULES = json.loads((Path(__file__).parent / "contract" / "weekly_rules.json").read_text(encoding="utf-8"))


def moment(text):
    return None if text is None else datetime.fromisoformat(text.replace("Z", "+00:00"))


class SharedRules(unittest.TestCase):
    def test_current_week(self):
        for case in RULES["current_week"]:
            with self.subTest(case["why"]):
                self.assertEqual(schedule.current_week_of(moment(case["now_utc"])),
                                 date.fromisoformat(case["week_of"]))

    def test_window(self):
        for case in RULES["window"]:
            with self.subTest(case["why"]):
                week = date.fromisoformat(case["week_of"])
                self.assertEqual(schedule.window_start(week), date.fromisoformat(case["window_start"]))
                self.assertEqual(schedule.window_end(week), date.fromisoformat(case["window_end"]))

    def test_manual_pending(self):
        for case in RULES["manual_pending"]:
            with self.subTest(case["why"]):
                self.assertEqual(
                    schedule.is_manual_pending(moment(case["requested_at"]), moment(case["claimed_at"])),
                    case["pending"])

    def test_table_is_not_empty(self):
        """표가 비면 위 시험은 아무것도 보지 않고 통과한다."""
        for section in ("current_week", "window", "manual_pending"):
            self.assertGreaterEqual(len(RULES[section]), 3, section)


if __name__ == "__main__":
    unittest.main()
