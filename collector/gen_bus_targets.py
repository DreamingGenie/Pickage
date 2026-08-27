"""버스 노선 우선순위 목록에서 예산에 맞는 targets.toml 블록을 만든다.

    # 지금 키 수(.env.local)로 위치 300초에 담을 수 있는 만큼
    python -m collector.gen_bus_targets

    # 키 6개, 위치 600초 가정으로 미리 계산
    python -m collector.gen_bus_targets --keys 6 --interval 600 --arrival-interval 600

버스는 노선 단위 호출(1콜=1노선)이라 담을 수 있는 노선 수가 예산에 묶인다.

    최대 노선 수 = floor( 키수 × hard_cap ÷ (86400 / 주기) )

`collector/config/bus_routes_priority.tsv`의 순위 상위부터 그만큼 잘라
`bus_route_id = [...]` 리스트가 든 [[targets]] 블록을 출력한다. 출력은 화면에만
찍고 파일은 건드리지 않는다 — 붙여넣기 전에 사람이 확인하도록.

키 수를 지정하지 않으면 `.env.local`의 `DATA_GO_BUS_API_KEY[_2..]`를 세어
현재 실제 예산으로 계산한다. 순위 목록은 이미 busRouteId까지 해결돼 있으므로,
키만 늘리고 이 도구를 다시 돌려 더 큰 리스트로 교체하면 노선이 확장된다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .common import console, targets as targets_mod
from .common.env import list_keys

_ROOT = Path(__file__).resolve().parent
PRIORITY_TSV = _ROOT / "config" / "bus_routes_priority.tsv"
SECONDS_PER_DAY = 86_400
BUS_KEY_ENV = "DATA_GO_BUS_API_KEY"


def load_priority(path: Path) -> list[dict]:
    """순위 TSV를 읽어 busRouteId가 해결된 노선만 순서대로 반환한다.

    TSV 컬럼: rank, route_no, segment, boardings, bus_route_id (5칸).
    """
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = [p.strip() for p in line.split("\t")]
        if len(parts) < 5 or not parts[4]:
            continue  # 컬럼 부족 또는 아직 해결 안 된 노선은 건너뛴다
        rows.append(
            {"rank": parts[0], "route_no": parts[1], "name": parts[2],
             "boardings": parts[3], "route_id": parts[4]}
        )
    return rows


def bus_budget(n_keys: int, hard_cap_override: int | None) -> int:
    """버스 풀의 하루 예산 = 키별 한도의 합.

    targets.toml의 [key_caps]에서 운영/개발 계정별 실제 한도를 읽어 합산한다.
    예전엔 `키수 × 950`(개발계정)으로 고정돼 있어, 운영계정으로 바꾼 뒤 예산을
    10배 적게 잡았다. 이제 설정과 항상 일치한다. override를 주면 전 키 그 값으로 본다.
    """
    if hard_cap_override is not None:
        return n_keys * hard_cap_override
    settings = targets_mod.load()
    return sum(settings.caps_for(BUS_KEY_ENV, n_keys))


def max_routes(budget: int, interval: int) -> int:
    calls_per_route = SECONDS_PER_DAY / interval
    return int(budget / calls_per_route)


def render_block(routes: list[dict], interval: int, arrival_interval: int) -> str:
    ids = [r["route_id"] for r in routes]
    id_list = ", ".join(f'"{i}"' for i in ids)
    lines = []
    lines.append("# ── 버스 fleet (gen_bus_targets.py 생성) ─────────────────────────────")
    lines.append("# 순위 상위부터 예산에 맞춰 자른 목록. 노선번호는 아래 주석 참고.")
    for r in routes:
        lines.append(f"#   {r['rank']:>2}위 {r['route_no']:>6}번 {r['name']} ({r['route_id']})")
    lines.append("")
    lines.append("[[targets]]")
    lines.append('name = "bus_position"')
    lines.append('source = "bus-position"')
    lines.append(f"interval_seconds = {interval}")
    lines.append("enabled = true")
    lines.append(f"params = {{ bus_route_id = [{id_list}], start_ord = 1, end_ord = 200 }}")
    lines.append("")
    lines.append("[[targets]]")
    lines.append('name = "bus_arrival"')
    lines.append('source = "bus-arrival-all"')
    lines.append(f"interval_seconds = {arrival_interval}")
    lines.append("enabled = true")
    lines.append(f"params = {{ bus_route_id = [{id_list}] }}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="예산에 맞는 버스 fleet 블록 생성")
    parser.add_argument("--keys", type=int, help="버스 키 수 (기본: .env.local에서 자동 계수)")
    parser.add_argument("--interval", type=int, default=300, help="위치 폴링 주기 초 (기본 300)")
    parser.add_argument("--arrival-interval", type=int, default=600, help="도착 폴링 주기 초 (기본 600)")
    parser.add_argument("--hard-cap", type=int, default=None,
                        help="키별 한도 강제(생략 시 targets.toml의 key_caps를 읽음)")
    parser.add_argument("--priority", type=Path, default=PRIORITY_TSV)
    args = parser.parse_args(argv)
    console.use_utf8()

    routes = load_priority(args.priority)
    if not routes:
        print("해결된 노선이 없습니다. TSV의 bus_route_id 칸을 확인하세요.", file=sys.stderr)
        return 2

    keys = args.keys if args.keys is not None else max(1, len(list_keys(BUS_KEY_ENV)))
    budget = bus_budget(keys, args.hard_cap)
    cap = max_routes(budget, args.interval)
    take = min(cap, len(routes))

    print(f"# 버스 키 {keys}개 · 예산 {budget}/일 · 위치 {args.interval}초 → 최대 {cap}개 노선")
    print(f"# 우선순위 목록 {len(routes)}개 중 상위 {take}개를 넣습니다"
          + (f" (나머지 {len(routes) - take}개는 키·주기 여유 시 확장)" if take < len(routes) else " (전부 수용)"))
    if take == 0:
        print("# ⚠️ 예산이 0노선입니다. 주기를 늘리거나 키를 늘리세요.", file=sys.stderr)
        return 1
    print()
    print(render_block(routes[:take], args.interval, args.arrival_interval))
    return 0


if __name__ == "__main__":
    sys.exit(main())
