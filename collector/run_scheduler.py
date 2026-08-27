"""실시간 수집 상시 실행 (Jira 98).

    # 설정·키 검증 — 활성 대상을 1회씩만 호출하고 종료
    python -m collector.run_scheduler --once

    # 상시 수집 (Ctrl+C로 정상 종료)
    python -m collector.run_scheduler

    # 일부 대상만
    python -m collector.run_scheduler --only subway_position_line1 bus_position_100100118

    # 호출은 하되 Bronze에 쓰지 않음 (quota는 소모된다)
    python -m collector.run_scheduler --once --dry-run

대상과 주기는 `collector/targets.toml`, 키는 `collector/.env.local`에서 읽는다.
로그는 stderr와 `data/logs/collector.log`(회전 5개)에 동시에 남는다.

자동 재시작 설정(systemd / Windows 작업 스케줄러)은 `collector/OPERATIONS.md`
를 따른다. 이 프로세스는 대상 단위로 예외를 흡수하므로 스스로 죽는 일은
드물지만, 재부팅·절전 복귀까지 보장하려면 OS 수준 재시작이 필요하다.

종료 코드
    0  정상 종료 / 1회 실행 전부 성공
    1  1회 실행에서 실패한 대상이 있음
    2  설정 오류 또는 실행할 대상이 없음
"""
from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
import signal
import sys
import threading
from dataclasses import replace
from pathlib import Path

from .common import console, targets as targets_mod
from .common.env import MissingSecretError, list_keys, warn_if_encoded
from .common.quota import QuotaLedger
from .common.scheduler import Scheduler
from .common.targets import ConfigError
from .sources import registry

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOG_PATH = _REPO_ROOT / "data" / "logs" / "collector.log"
LOG_FORMAT = "%(asctime)s %(levelname)-7s %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_logging(log_path: Path, level: int = logging.INFO) -> None:
    root = logging.getLogger("collector")
    root.setLevel(level)
    root.handlers.clear()
    fmt = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATEFMT)

    # 콘솔 핸들러는 stderr가 있을 때만 붙인다.
    #
    # Windows 작업 스케줄러로 백그라운드 구동할 때는 콘솔 창을 띄우지 않으려고
    # `pythonw.exe`를 쓰는데, 이 실행기에서는 sys.stderr가 None이다.
    # StreamHandler(None)은 emit 시점에 None.write를 호출해 깨진다. 로그가 안
    # 남는 정도가 아니라 매 로그마다 예외가 나므로 반드시 걸러야 한다.
    # (지역 이름이 `console` 모듈을 가리지 않도록 이름을 따로 둔다.)
    if sys.stderr is not None:
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setFormatter(fmt)
        root.addHandler(stream_handler)

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        # 상시 프로세스라 로그가 무한히 커지지 않게 회전시킨다. 5MB x 5개.
        rotating = logging.handlers.RotatingFileHandler(
            log_path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        rotating.setFormatter(fmt)
        root.addHandler(rotating)
    except OSError as exc:
        root.warning("로그 파일을 열 수 없어 콘솔에만 기록합니다: %s", exc)


def resolve_keys(settings: targets_mod.Settings) -> dict[str, list[str]]:
    """활성 대상이 필요로 하는 키를 env별로 **목록**으로 읽는다(key rotation).

    `SEOUL_SUBWAY_REALTIME_KEY`, `_2`, `_3` … 를 순서대로 모은다. 팀원 키를
    함께 쓰면 그 provider의 하루 예산이 키 수만큼 배가 된다.

    키가 없으면 예외를 던지지 않는다. 버스 키가 없어도 지하철 수집은 돌아야
    하고, 실시간 데이터는 하루를 멈추면 하루가 영구 손실이기 때문이다.
    없는 키는 스케줄러가 해당 대상만 건너뛰며 경고한다.
    """
    keys: dict[str, list[str]] = {}
    for target in settings.enabled():
        env_name = target.spec.key_env
        if env_name in keys:
            continue
        values = list_keys(env_name)
        for v in values:
            warn_if_encoded(env_name, v)
        if values:
            keys[env_name] = values
    return keys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="실시간 Bronze 수집 상시 실행")
    parser.add_argument("--config", type=Path, help="설정 파일 경로 (기본 collector/targets.toml)")
    parser.add_argument("--once", action="store_true", help="활성 대상을 1회씩만 호출하고 종료")
    parser.add_argument("--only", nargs="+", metavar="NAME", help="이 이름의 대상만 실행")
    parser.add_argument("--dry-run", action="store_true", help="호출하되 Bronze에 쓰지 않음")
    parser.add_argument("--log-file", type=Path, default=DEFAULT_LOG_PATH)
    parser.add_argument("--verbose", action="store_true", help="DEBUG 로그까지 출력")
    args = parser.parse_args(argv)

    console.use_utf8()
    setup_logging(args.log_file, logging.DEBUG if args.verbose else logging.INFO)
    log = logging.getLogger("collector.run")

    try:
        settings = targets_mod.load(args.config)
    except (ConfigError, registry.UnknownSource, registry.BadParams) as exc:
        log.error("설정 오류: %s", exc)
        return 2

    if args.only:
        wanted = set(args.only)
        unknown = wanted - {t.name for t in settings.targets}
        if unknown:
            log.error("--only에 없는 대상이 있습니다: %s", ", ".join(sorted(unknown)))
            return 2
        kept = tuple(replace(t, enabled=t.name in wanted) for t in settings.targets)
        settings = replace(settings, targets=kept)

    try:
        keys = resolve_keys(settings)
    except MissingSecretError as exc:
        log.error("%s", exc)
        return 2

    scheduler = Scheduler(
        settings=settings, ledger=QuotaLedger(), keys=keys, dry_run=args.dry_run
    )

    if args.once:
        return scheduler.run_once()

    _install_signal_handlers(scheduler.stop, log)
    log.info("PID %d. 정지는 Ctrl+C 또는 SIGTERM.", os.getpid())
    return scheduler.run()


def _install_signal_handlers(stop: threading.Event, log: logging.Logger) -> None:
    """SIGINT/SIGTERM을 받으면 진행 중인 호출을 마치고 요약 후 종료한다.

    호출 도중에 프로세스를 강제 종료하면 quota는 소모됐는데 원문이 Bronze에
    남지 않는다. 정상 종료 경로를 두는 이유다.
    """

    def handler(signum, _frame):
        log.info("신호 %s 수신. 정리 후 종료합니다.", signum)
        stop.set()

    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, handler)
        except (OSError, ValueError):
            # 플랫폼이 지원하지 않는 신호는 조용히 넘긴다(Windows의 SIGTERM 등).
            pass


if __name__ == "__main__":
    sys.exit(main())
