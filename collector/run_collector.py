"""수집 1회 실행 CLI (Jira 95 / 96의 "1회 수집 수동 실행" 항목용).

    # 지하철 (실제 키 없으면 sample로 스모크)
    python -m collector.run_collector subway-arrival-all
    python -m collector.run_collector subway-arrival-all --key sample
    python -m collector.run_collector subway-position --line 1호선

    # 버스 (sample 키 없음 — 실제 키 필요)
    python -m collector.run_collector bus-position --route 100100118 --start 1 --end 110
    python -m collector.run_collector bus-arrival-all --route 100100118

키는 collector/.env.local에서 읽는다. `--key`로 덮어쓸 수 있다.
`--dry-run`은 호출만 하고 Bronze에 쓰지 않는다(quota는 소모된다).

호출은 quota 원장(data/quota_ledger.json)에 운행일 단위로 기록되며 일일
상한(기본 950)에 도달하면 종료 코드 3으로 중단한다. 지하철 세 API는 인증키
1개의 한도를 공유하므로 하나의 카운터를 쓰고, 버스는 상세기능마다 독립
카운터를 쓴다. 재시도도 quota를 소모하며, 재시도해도 결과가 달라지지 않는
오류(권한 없음·잘못된 질의 등)는 1회만 소모하고 중단한다.
"""
from __future__ import annotations

import argparse
import sys

from .common import console, runner, storage
from .common.env import MissingSecretError, require_key, warn_if_encoded
from .common.quota import DEFAULT_HARD_CAP, QuotaExceeded, QuotaLedger
from .common.storage import OK, CollectionResult
from .sources import registry


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


def _params_from_args(target: str, args, parser) -> dict:
    """CLI 플래그를 어댑터 키워드 인자로 옮긴다.

    설정 파일(targets.toml)은 어댑터 인자 이름을 그대로 쓰지만, CLI는 이미
    `--line`·`--route` 같은 짧은 플래그로 문서화돼 있어 여기서만 변환한다.
    """
    if target == "subway-arrival-all":
        return {}
    if target == "subway-position":
        params: dict = {"line_name": args.line}
        if args.start is not None:
            params["start"] = args.start
        if args.end is not None:
            params["end"] = args.end
        return params
    if target == "subway-arrival-station":
        return {
            "station_name": args.station,
            "start": args.start or 0,
            "end": args.end or 20,
        }
    if not args.route:
        parser.error("버스 수집에는 --route(busRouteId)가 필요합니다.")
    if target == "bus-position":
        return {
            "bus_route_id": args.route,
            "start_ord": args.start or 1,
            "end_ord": args.end or 200,
        }
    return {"bus_route_id": args.route}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bronze 수집 1회 실행")
    parser.add_argument("target", choices=registry.names())
    parser.add_argument("--key", help="환경변수 대신 사용할 키. sample 지정 가능")
    parser.add_argument("--line", default="1호선", help="지하철 노선명")
    parser.add_argument("--station", default="서울", help="지하철 역명")
    parser.add_argument("--route", help="버스 노선 ID(busRouteId)")
    parser.add_argument("--start", type=int, help="조회 시작 순번")
    parser.add_argument("--end", type=int, help="조회 종료 순번")
    parser.add_argument("--format", default=None, help="응답 포맷(json/xml)")
    parser.add_argument("--dry-run", action="store_true", help="호출만 하고 저장하지 않음")
    parser.add_argument("--max-attempts", type=int, default=3, help="재시도 포함 최대 시도 횟수")
    parser.add_argument("--hard-cap", type=int, default=DEFAULT_HARD_CAP, help="일일 호출 상한")
    args = parser.parse_args(argv)
    console.use_utf8()

    ledger = QuotaLedger()

    # 어댑터·quota 풀·재시도 판정은 레지스트리가 정본이다. 스케줄러와 같은 정의를 쓴다.
    spec = registry.get(args.target)
    params = _params_from_args(args.target, args, parser)
    registry.validate_params(spec, params)

    try:
        key = _resolve_key(args.key, spec.key_env)
        pool = registry.make_pool(spec, key, args.hard_cap)
        result = runner.collect(
            spec.fn,
            key,
            ledger=ledger,
            pool=pool,
            business_check=spec.business_check,
            max_attempts=args.max_attempts,
            fmt=args.format or spec.default_fmt,
            **params,
        )
    except MissingSecretError as exc:
        print(f"키 없음: {exc}", file=sys.stderr)
        return 2
    except QuotaExceeded as exc:
        print(f"quota 상한: {exc}", file=sys.stderr)
        return 3

    meta_path = None if args.dry_run else storage.record(result)
    _report(result, meta_path)
    print(
        f"  quota: {pool.counter_key} {ledger.used(pool)}/{pool.hard_cap} "
        f"(잔여 {ledger.remaining(pool)})"
    )
    return 0 if result.outcome == OK else 1


if __name__ == "__main__":
    sys.exit(main())
