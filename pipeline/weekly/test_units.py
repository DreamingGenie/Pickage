"""호스트 스크립트와 systemd 유닛이 **같은 이름을 보고 있는가.**

두 파일에 따로 적힌 값이 둘 있다 — 컨테이너 이름과 잠금 파일 경로. systemd 는 셸 변수를
읽을 수 없어서 어쩔 수 없이 양쪽에 박아 두었고, 그래서 한쪽만 고치면 조용히 어긋난다.

어긋났을 때 나는 일이 둘 다 나쁘다.

* 컨테이너 이름이 갈리면 `ExecStopPost` 가 **엉뚱한 이름을 지우고 진짜 유령은 살아남는다.**
  그 유령이 계속 npm 을 두드리며 checkpoint 를 쓰는 동안 다음 발화가 하나를 더 띄운다.
* 잠금 경로가 갈리면 `ExecStopPost` 의 `flock -n` 이 **늘 빈 잠금을 잡아** 통과하고,
  사람이 SSH 에서 돌리던 수동 실행의 컨테이너를 죽인다. 실제 수집이 23시간이라 타이머가
  켜져 있는 한 수동 실행이 끝까지 가지 못한다.

둘 다 실패가 아니라 "엉뚱한 것이 죽음" 으로 나타나서 로그만 봐서는 안 보인다.
"""
import re
import unittest
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "deploy/prod/data"
SCRIPT = (DATA / "run-weekly-ingest.sh").read_text(encoding="utf-8")
UNIT = (DATA / "systemd/pickage-weekly.service").read_text(encoding="utf-8")
STOP_POST = next(line for line in UNIT.splitlines() if line.startswith("ExecStopPost="))


def _assigned(source: str, name: str) -> str:
    found = re.search(rf"^{name}=(\S+)$", source, re.M)
    assert found, f"run-weekly-ingest.sh 에 {name} 대입이 없다"
    return found.group(1)


class CleanupContractTests(unittest.TestCase):
    def test_container_name_matches(self):
        self.assertIn(_assigned(SCRIPT, "CONTAINER"), STOP_POST)

    def test_lock_path_matches(self):
        self.assertIn(_assigned(SCRIPT, "LOCK"), STOP_POST)

    def test_neither_can_be_overridden_by_environment(self):
        """`${VAR:-기본값}` 으로 두면 환경변수 하나로 유닛과 갈릴 수 있다."""
        for name in ("CONTAINER", "LOCK"):
            self.assertNotIn("$", _assigned(SCRIPT, name), f"{name} 이 환경변수로 덮인다")

    def test_cleanup_goes_through_the_lock(self):
        """맨 `docker rm -f` 를 두면 남이 쥔 회차를 죽인다.

        ExecStopPost 는 ExecStart 가 어떻게 끝났든 **무조건** 돈다 — 잠금을 못 잡아
        곧바로 0 으로 끝난 발화 뒤에도 돈다.
        """
        self.assertRegex(STOP_POST, r"flock\s+-n\s+\S+\s+\S*docker\s+rm\s+-f")


if __name__ == "__main__":
    unittest.main()
