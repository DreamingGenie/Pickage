"""수집 1회 실행 CLI (Jira 95 / 96의 "1회 수집 수동 실행" 항목용).

    # 지하철 (실제 키 없으면 sample로 스모크)
    python -m collector.run_collector subway-arrival-all
    python -m collector.run_collector subway-arrival-all --key sample
    python -m collector.run_collector subway-position --line 1호선

    # 버스 (sample 키 없음 — 실제 키 필요)
    python -m collector.run_collector bus-position --route 100100118 --start 1 --end 110
    python -m collector.run_collector bus-arrival-all --route 100100118

키는 collector/.env.local에서 읽는다. `--key`로 덮어쓸 수 있다.
`--dry-run`은 호출만 하고 Bronze에 쓰지 않는다.

quota 상한은 아직 이 CLI가 강제하지 않는다(Jira 97). 그전까지는 수동
실행 횟수를 직접 관리한다.
"""
from __future__ import annotations

import argparse
import sys

from .common import storage
from .common.env import MissingSecretError, require_key, warn_if_encoded
from .common.storage import OK, CollectionResult
from .sources import seoul_bus, seoul_subway

SUBWAY_KEY = "SEOUL_SUBWAY_REALTIME_KEY"
BUS_KEY = "DATA_GO_BUS_API_KEY"


def _resolve_key(explicit: str | None, env_name: str) -> str:
    if explicit:
        return explicit
    key = require_key(env_name)
    warn_if_encoded(env_name, key)
    return key


def _report(result: CollectionResult, meta_path=None) -> None:
    line = (
        f"{result.source_key:22} outcome={result.outcome:15} "
        f"http={result.http_status} code={result.business_code} "
        f"rows={result.row_count} bytes={len(result.payload or b''):,} "
        f"latency={result.latency_ms:.0f}ms"
    )
    print(line)
    if result.outcome != OK:
        print(f"  사유: {result.error_code} {result.error_body or ''}".rstrip())
    print(f"  URL : {result.request_url_masked}")
    if meta_path:
        print(f"  저장 : {meta_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bronze 수집 1회 실행")
    parser.add_argument(
        "target",
        choices=[
            "subway-arrival-all",
            "subway-position",
            "subway-arrival-station",
            "bus-position",
            "bus-arrival-all",
        ],
    )
    parser.add_argument("--key", help="환경변수 대신 사용할 키. sample 지정 가능")
    parser.add_argument("--line", default="1호선", help="지하철 노선명")
    parser.add_argument("--station", default="서울", help="지하철 역명")
    parser.add_argument("--route", help="버스 노선 ID(busRouteId)")
    parser.add_argument("--start", type=int, help="조회 시작 순번")
    parser.add_argument("--end", type=int, help="조회 종료 순번")
    parser.add_argument("--format", default=None, help="응답 포맷(json/xml)")
    parser.add_argument("--dry-run", action="store_true", help="호출만 하고 저장하지 않음")
    args = parser.parse_args(argv)

    try:
        if args.target.startswith("subway"):
            key = args.key or _resolve_key(None, SUBWAY_KEY)
            fmt = args.format or "json"
            if args.target == "subway-arrival-all":
                result = seoul_subway.arrival_all(key, fmt=fmt)
            elif args.target == "subway-position":
                rng = {}
                if args.start is not None:
                    rng["start"] = args.start
                if args.end is not None:
                    rng["end"] = args.end
                result = seoul_subway.position(key, args.line, fmt=fmt, **rng)
            else:
                result = seoul_subway.arrival_station(
                    key, args.station, start=args.start or 0, end=args.end or 20, fmt=fmt
                )
        else:
            if not args.route:
                parser.error("버스 수집에는 --route(busRouteId)가 필요합니다.")
            key = _resolve_key(args.key, BUS_KEY)
            fmt = args.format or "xml"
            if args.target == "bus-position":
                result = seoul_bus.position(
                    key,
                    args.route,
                    start_ord=args.start or 1,
                    end_ord=args.end or 200,
                    fmt=fmt,
                )
            else:
                result = seoul_bus.arrival_all(key, args.route, fmt=fmt)
    except MissingSecretError as exc:
        print(f"키 없음: {exc}", file=sys.stderr)
        return 2

    meta_path = None if args.dry_run else storage.record(result)
    _report(result, meta_path)
    return 0 if result.outcome == OK else 1


if __name__ == "__main__":
    sys.exit(main())
