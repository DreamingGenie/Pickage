"""설정·rotation·키별 hard_cap 검증. 네트워크 호출도 quota 소모도 없다.

이 파일은 최근 추가된 세 기능을 커버한다.
  1. 버스 노선 fleet 확장 (bus_route_id 리스트 → 노선마다 대상)
  2. key rotation (키A 소진 → 키B로 이어받기)
  3. 키별 hard_cap (운영/개발 계정 혼용: 키마다 다른 한도)
  4. 설정 검증 실패 경로 (오타를 기동 시점에 잡는다)
"""
from __future__ import annotations

import dataclasses
import io
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from collector.common import env, storage, targets as T
from collector.common.quota import QuotaLedger
from collector.common.scheduler import Scheduler
from collector.common.storage import OK, CollectionResult
from collector.sources import registry

out = io.TextIOWrapper(open(1, "wb", closefd=False), encoding="utf-8", errors="replace")
P, F = [], []


def check(name, cond, detail=""):
    (P if cond else F).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{('  '+detail) if detail else ''}", file=out)


def write_cfg(body: str) -> Path:
    f = tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False, encoding="utf-8")
    f.write(body)
    f.close()
    return Path(f.name)


# ── 1. 버스 노선 fleet 확장 ────────────────────────────────────────────
print("\n1. 버스 노선 fleet 확장", file=out)
cfg = write_cfg("""
[defaults]
hard_cap = 950
[[targets]]
name = "buspos"
source = "bus-position"
interval_seconds = 300
params = { bus_route_id = ["100100022", "100100033", "100100048"], start_ord = 1, end_ord = 200 }
""")
s = T.load(cfg)
cfg.unlink()
names = [t.name for t in s.targets]
check("노선 3개로 확장", len(s.targets) == 3, str(names))
check("이름에 route_id 붙음", names == ["buspos_100100022", "buspos_100100033", "buspos_100100048"])
check("각 대상 bus_route_id 분리",
      [t.params["bus_route_id"] for t in s.targets] == ["100100022", "100100033", "100100048"])

# ── 2. 키별 hard_cap + 예산 합산 ───────────────────────────────────────
print("\n2. 키별 hard_cap (운영/개발 혼용)", file=out)
cfg = write_cfg("""
[defaults]
hard_cap = 950
[key_caps]
DATA_GO_BUS_API_KEY = [9500, 950, 950]
[[targets]]
name = "buspos"
source = "bus-position"
interval_seconds = 300
params = { bus_route_id = ["R1", "R2"], start_ord = 1, end_ord = 200 }
""")
s = T.load(cfg)
cfg.unlink()
check("caps_for: 운영1+개발2", s.caps_for("DATA_GO_BUS_API_KEY", 3) == [9500, 950, 950])
check("caps_for: 목록보다 키 많으면 default", s.caps_for("DATA_GO_BUS_API_KEY", 4) == [9500, 950, 950, 950])
check("caps_for: 미지정 env는 default", s.caps_for("SEOUL_SUBWAY_REALTIME_KEY", 2) == [950, 950])
rep = T.budget_report(s, {"DATA_GO_BUS_API_KEY": 3})
pool, calls, cap, over = rep[0]
check("유효상한 = 캡의 합(11400)", cap == 11400, f"cap={cap}")

# ── 3. 스케줄러 rotation + 키별 캡 적용 ────────────────────────────────
print("\n3. key rotation — 키A 소진 후 키B로 이어받기", file=out)


def fake_fn(key, quota_seq_today=None, quota_pool=None, fmt="xml", **params):
    now = storage.now_iso()
    return CollectionResult(
        source_key="bus_position", provider="t", endpoint="e",
        requested_at=now, received_at=storage.now_iso(), request_url_masked="x",
        http_status=200, payload=b"x", payload_ext="xml", business_code="0",
        row_count=1, outcome=OK, quota_seq_today=quota_seq_today,
        key_id=None, quota_pool=quota_pool)


with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    storage.BRONZE_DIR = tmp / "bronze"
    led = QuotaLedger(path=tmp / "l.json", rebuild_from_bronze=False)
    spec = dataclasses.replace(registry.SPECS["bus-position"], fn=fake_fn)
    # 키별 캡: 키A=3, 키B=2
    tgt = T.Target(name="buspos_R", spec=spec, interval_seconds=300,
                   params={"bus_route_id": "R", "start_ord": 1, "end_ord": 200},
                   enabled=True, max_attempts=1, hard_cap=950)
    st = T.Settings(retry_reserve=0, stagger_seconds=0, heartbeat_seconds=9e9, stall_factor=3,
                    permanent_error_limit=3, default_hard_cap=950,
                    key_caps={"DATA_GO_BUS_API_KEY": (3, 2)}, targets=(tgt,))
    sch = Scheduler(settings=st, ledger=led, keys={"DATA_GO_BUS_API_KEY": ["keyA", "keyB"]})
    state = sch.states[0]
    caps = [pool.hard_cap for _, pool in state.keypools]
    check("키풀이 키별 캡을 가짐 [3, 2]", caps == [3, 2], str(caps))
    for _ in range(7):
        sch._run_target(state)
    poolA, poolB = state.keypools[0][1], state.keypools[1][1]
    check("키A 캡 3 소진", led.used(poolA) == 3, f"A={led.used(poolA)}")
    check("키A 소진 후 키B 캡 2 소진", led.used(poolB) == 2, f"B={led.used(poolB)}")
    check("총 5회(3+2)에서 멈춤", led.used(poolA) + led.used(poolB) == 5)

# ── 4. env.list_keys (rotation 키 읽기) ────────────────────────────────
print("\n4. list_keys — 순서·정지·중복", file=out)
import os
for k in ["ZZ_TEST", "ZZ_TEST_2", "ZZ_TEST_3"]:
    os.environ.pop(k, None)
os.environ["ZZ_TEST"] = "a"; os.environ["ZZ_TEST_2"] = "b"; os.environ["ZZ_TEST_3"] = "c"
check("a,b,c 순서로 3개", env.list_keys("ZZ_TEST") == ["a", "b", "c"])
os.environ.pop("ZZ_TEST_2")
check("_2 비면 _3 안 읽음(빈 번호서 정지)", env.list_keys("ZZ_TEST") == ["a"])

# ── 5. 설정 검증 실패 경로 ─────────────────────────────────────────────
print("\n5. 설정 검증 실패 경로", file=out)
bad = {
    "없는 source": '[[targets]]\nname="a"\nsource="nope"\ninterval_seconds=300\n',
    "필수 파라미터 누락": '[[targets]]\nname="a"\nsource="subway-position"\ninterval_seconds=300\n',
    "주기 너무 짧음": '[[targets]]\nname="a"\nsource="subway-position"\ninterval_seconds=5\nparams={line_name="1호선"}\n',
    "이름 중복": '[[targets]]\nname="a"\nsource="subway-position"\ninterval_seconds=300\nparams={line_name="1호선"}\n[[targets]]\nname="a"\nsource="subway-position"\ninterval_seconds=300\nparams={line_name="2호선"}\n',
    "key_caps 정수 아님": '[key_caps]\nDATA_GO_BUS_API_KEY=[9500,"x"]\n[[targets]]\nname="a"\nsource="subway-position"\ninterval_seconds=300\nparams={line_name="1호선"}\n',
}
for label, body in bad.items():
    cfg = write_cfg(body)
    try:
        T.load(cfg)
        check(label + " 차단", False, "통과해버림")
    except (T.ConfigError, registry.UnknownSource, registry.BadParams):
        check(label + " 차단", True)
    finally:
        cfg.unlink()

print("\n" + "=" * 50, file=out)
print(f"통과 {len(P)} / 실패 {len(F)}", file=out)
if F:
    print("실패: " + ", ".join(F), file=out)
out.flush()
sys.exit(1 if F else 0)
