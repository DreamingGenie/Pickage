"""수집 대상 설정 로딩과 예산 검증 (Jira 98).

`collector/targets.toml`을 읽어 스케줄러가 쓰는 `Settings`로 만든다.
설정 오류는 **기동 시점에** 전부 잡는다. 잘못된 파라미터로 하루를 수집하면
그 호출은 quota를 소모하고, 실시간 데이터는 backfill이 불가능해 되돌릴 수 없다.

예산 검증은 계획서(DATA_PLATFORM_PLAN 5-3절) 산식을 그대로 구현한다.

    풀별로  sum(86,400 / interval_seconds) <= hard_cap

지하철 세 API가 인증키 1개의 한도를 공유하므로, 풀 단위로 합산해야 실제
초과를 잡을 수 있다. 대상별로 따로 검사하면 3개 노선이 각각 288회라 통과해
버리고 합계 864회가 상한을 넘는 상황을 놓친다.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from ..sources import registry
from ..sources.registry import SourceSpec
from .quota import DEFAULT_HARD_CAP

_COLLECTOR_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = _COLLECTOR_ROOT / "targets.toml"

SECONDS_PER_DAY = 86_400

# 이보다 짧은 주기는 설정 오타로 본다. 단자릿수 오타(1~14초)를 막되, 일괄 도착을
# 다키 rotation으로 촘촘히(예: 4키 20초) 돌리는 의도된 설정은 통과시킨다. 실제
# 오버구독 방어는 budget_report(유효상한 대비)와 hard_cap이 담당한다.
MIN_INTERVAL_SECONDS = 15


class ConfigError(ValueError):
    """설정 파일이 잘못됐다. 기동을 중단한다."""


@dataclass(frozen=True)
class Target:
    """폴링 대상 1건."""

    name: str
    spec: SourceSpec
    interval_seconds: int
    params: dict
    enabled: bool
    max_attempts: int
    hard_cap: int

    @property
    def calls_per_day(self) -> float:
        return SECONDS_PER_DAY / self.interval_seconds

    def call_kwargs(self) -> dict:
        """어댑터 함수에 넘길 키워드 인자. fmt이 없으면 source 기본값을 쓴다."""
        kwargs = dict(self.params)
        kwargs.setdefault("fmt", self.spec.default_fmt)
        return kwargs


@dataclass(frozen=True)
class Settings:
    retry_reserve: int
    stagger_seconds: float
    heartbeat_seconds: float
    stall_factor: float
    permanent_error_limit: int
    targets: tuple[Target, ...]

    def enabled(self) -> tuple[Target, ...]:
        return tuple(t for t in self.targets if t.enabled)


def _enabled(entry: dict, name: str) -> bool:
    value = entry.get("enabled", True)
    if not isinstance(value, bool):
        raise ConfigError(f"{name}: enabled는 true/false여야 합니다.")
    return value


def _require_int(table: dict, key: str, default: int, *, where: str) -> int:
    value = table.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigError(f"{where}.{key}는 정수여야 합니다: {value!r}")
    return value


def _require_float(table: dict, key: str, default: float, *, where: str) -> float:
    value = table.get(key, default)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ConfigError(f"{where}.{key}는 숫자여야 합니다: {value!r}")
    return float(value)


def load(path: Path | None = None) -> Settings:
    """설정 파일을 읽어 검증까지 마친 Settings를 반환한다."""
    cfg_path = path or DEFAULT_CONFIG_PATH
    if not cfg_path.exists():
        raise ConfigError(f"설정 파일이 없습니다: {cfg_path}")

    try:
        raw = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{cfg_path} TOML 파싱 실패: {exc}") from None

    defaults = raw.get("defaults", {})
    if not isinstance(defaults, dict):
        raise ConfigError("[defaults]는 테이블이어야 합니다.")

    default_attempts = _require_int(defaults, "max_attempts", 2, where="defaults")
    default_cap = _require_int(defaults, "hard_cap", DEFAULT_HARD_CAP, where="defaults")

    entries = raw.get("targets", [])
    if not isinstance(entries, list) or not entries:
        raise ConfigError("[[targets]] 항목이 하나도 없습니다.")

    seen: set[str] = set()
    targets: list[Target] = []
    for index, entry in enumerate(entries):
        where = f"targets[{index}]"
        if not isinstance(entry, dict):
            raise ConfigError(f"{where}는 테이블이어야 합니다.")

        name = entry.get("name")
        if not isinstance(name, str) or not name:
            raise ConfigError(f"{where}.name이 없습니다.")
        if name in seen:
            raise ConfigError(f"대상 이름이 중복됩니다: {name}")
        seen.add(name)

        source = entry.get("source")
        if not isinstance(source, str):
            raise ConfigError(f"{name}: source가 없습니다.")
        spec = registry.get(source)

        interval = _require_int(entry, "interval_seconds", 0, where=name)
        if interval < MIN_INTERVAL_SECONDS:
            raise ConfigError(
                f"{name}: interval_seconds가 {interval}초입니다. "
                f"최소 {MIN_INTERVAL_SECONDS}초 이상이어야 합니다(설정 오타 방어)."
            )

        params = entry.get("params", {})
        if not isinstance(params, dict):
            raise ConfigError(f"{name}: params는 테이블이어야 합니다.")

        # 버스 노선 fleet 확장: params.bus_route_id에 리스트를 주면 노선마다
        # 대상 하나로 펼친다. 노선 수십 개를 [[targets]] 블록 수십 개로 손으로
        # 쓰는 대신 한 줄 리스트로 관리하기 위해서다.
        route_ids = params.get("bus_route_id")
        if isinstance(route_ids, list):
            if not route_ids:
                raise ConfigError(f"{name}: bus_route_id 리스트가 비어 있습니다.")
            base_attempts = _require_int(entry, "max_attempts", default_attempts, where=name)
            base_cap = _require_int(entry, "hard_cap", default_cap, where=name)
            for rid in route_ids:
                if not isinstance(rid, str) or not rid:
                    raise ConfigError(f"{name}: bus_route_id 원소는 비어 있지 않은 문자열이어야 합니다: {rid!r}")
                one = dict(params, bus_route_id=rid)
                registry.validate_params(spec, one)
                sub_name = f"{name}_{rid}"
                if sub_name in seen:
                    raise ConfigError(f"대상 이름이 중복됩니다: {sub_name}")
                seen.add(sub_name)
                targets.append(
                    Target(
                        name=sub_name, spec=spec, interval_seconds=interval,
                        params=one, enabled=_enabled(entry, name),
                        max_attempts=base_attempts, hard_cap=base_cap,
                    )
                )
            continue

        registry.validate_params(spec, params)

        targets.append(
            Target(
                name=name,
                spec=spec,
                interval_seconds=interval,
                params=params,
                enabled=_enabled(entry, name),
                max_attempts=_require_int(entry, "max_attempts", default_attempts, where=name),
                hard_cap=_require_int(entry, "hard_cap", default_cap, where=name),
            )
        )

    return Settings(
        retry_reserve=_require_int(defaults, "retry_reserve", 60, where="defaults"),
        stagger_seconds=_require_float(defaults, "stagger_seconds", 7.0, where="defaults"),
        heartbeat_seconds=_require_float(defaults, "heartbeat_seconds", 900.0, where="defaults"),
        stall_factor=_require_float(defaults, "stall_factor", 3.0, where="defaults"),
        permanent_error_limit=_require_int(
            defaults, "permanent_error_limit", 3, where="defaults"
        ),
        targets=tuple(targets),
    )


def budget_report(
    settings: Settings, key_counts: dict[str, int] | None = None
) -> list[tuple[str, float, int, bool]]:
    """활성 대상의 일일 호출 수를 quota 풀 단위로 합산한다.

    반환: (풀 이름, 일일 호출 수, 유효 상한, 초과 여부)

    풀 단위로 합산하는 이유는 지하철 세 API가 인증키 1개의 한도를 공유하기
    때문이다. 대상별로 검사하면 합계 초과를 놓친다.

    `key_counts`는 `key_env → 키 개수`다(key rotation). 한 풀을 N개 키가
    번갈아 쓰면 하루 예산이 `상한 × N`이 되므로 유효 상한을 그만큼 키운다.
    None이면 키 1개로 본다(기존 동작).
    """
    key_counts = key_counts or {}
    per_pool: dict[str, float] = {}
    caps: dict[str, int] = {}
    envs: dict[str, str] = {}
    for target in settings.enabled():
        pool = target.spec.pool_name
        per_pool[pool] = per_pool.get(pool, 0.0) + target.calls_per_day
        # 같은 풀에 다른 상한이 설정되면 더 보수적인 값을 쓴다.
        caps[pool] = min(caps.get(pool, target.hard_cap), target.hard_cap)
        envs[pool] = target.spec.key_env

    out = []
    for pool, calls in sorted(per_pool.items()):
        n_keys = max(1, key_counts.get(envs[pool], 1))
        effective = caps[pool] * n_keys
        out.append((pool, calls, effective, calls > effective))
    return out
