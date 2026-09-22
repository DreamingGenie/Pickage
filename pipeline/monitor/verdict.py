"""판정 규칙 — 보고서 하나를 읽어 "무엇이 문제이고 무엇이 주의인가" 목록(findings)을 만든다.

화면(web/index.html)은 이 목록을 **그대로 보여 주기만** 한다. 규칙이 여기 있는 이유:

- 시험이 붙는다. "정상 / 주의 / 문제" 를 실제로 정하는 층이 시험 없는 JS 에 있었고, 결함이 거기서 났다.
- 시계가 하나다. 브라우저 시계가 어긋나면 "3분 전" 이 거짓말이 되는데, 여기서는 보고서를 만든 서버 시각(now)으로 잰다.
- 실행기와 같은 값을 쓴다. 오래된 RUNNING 의 기준(STALE_RUNNING)처럼 실행기 상수가 보고서에 실려 오면 그것을 쓴다.

finding 하나: {"level": "bad"|"warn", "kind": 종류, "section": 절 id(<노드>-<탭> 또는 node-<노드>), "ref": 행 식별자, "text": 문장}
  kind 는 같은 종류를 묶어 접을 때, ref 는 화면이 그 행에 색을 칠할 때 쓴다. 문장은 사람이 읽고 어디를 볼지 알게 쓴다.

순수 함수다 — 네트워크·파일·전역 상태를 건드리지 않는다. 보고서에 없는 절은 조용히 건너뛴다(그 절이 없는 것은
report["errors"] 가 따로 말한다).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

# 임계 — 실행기 상수가 보고서에 있으면 그쪽이 우선이다 (weekly.stale_running_hours)
MISSING_WEEK_BAD_AFTER = timedelta(hours=6)    # 이번 주 창이 열리고 이 시간 넘게 회차 객체가 없으면 문제
CURATED_STALE_RUNNING = timedelta(hours=36)    # Curated 전처리 RUNNING 의 상한 (systemd TimeoutStartSec 와 같다)
DISK_FREE_BAD = 10                             # 파티션 남은 %
DISK_FREE_WARN = 20

STAGE_KO = {"snapshot": "스냅샷", "package_version": "패키지·버전", "downloads": "다운로드", "repository": "저장소 지표",
            "package_snapshot": "패키지 스냅샷", "dependents": "역의존"}


def _t(value) -> datetime | None:
    """ISO 문자열 → aware datetime. 없거나 이상하면 None."""
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _hours(delta: timedelta) -> str:
    h = delta.total_seconds() / 3600
    return f"{h:.1f}시간" if h < 48 else f"{h / 24:.0f}일"


class _Out:
    def __init__(self, node: str):
        self.node = node
        self.items: list[dict] = []

    def bad(self, kind, section, text, ref=None):
        self.items.append({"level": "bad", "kind": kind, "section": section, "ref": ref, "text": text})

    def warn(self, kind, section, text, ref=None):
        self.items.append({"level": "warn", "kind": kind, "section": section, "ref": ref, "text": text})


# ── 절별 규칙 ──────────────────────────────────────────────────────────

def _report_errors(report: dict, out: _Out) -> None:
    for error in report.get("errors") or []:
        out.warn("report", f"node-{out.node}",
                 f"{out.node}: 보고서의 {error.get('section')} 절이 실패했습니다 — {error.get('message')}", ref=error.get("section"))


def _weekly(weekly: dict | None, out: _Out, now: datetime) -> None:
    if not weekly:
        return
    sec = f"{out.node}-weekly"
    # 이번 주 회차가 시작조차 안 했다 — 창이 열렸는데 그 주 객체가 없다. 지난주 성공만 남아 초록으로 보이던 고장.
    ex = weekly.get("expected") or {}
    if ex.get("missing"):
        opened = _t(ex.get("window_open_at"))
        late = now - opened if opened else timedelta(0)
        level = out.bad if late > MISSING_WEEK_BAD_AFTER else out.warn
        level("weekly-missing", sec,
              f"이번 주({ex.get('week_of')}) 수집 회차가 시작조차 안 했습니다 — 창이 {_hours(late)} 전 열렸는데 _ops/weekly 에 "
              f"그 주 객체가 없습니다. 타이머가 멎었거나 실행기가 begin() 전에 죽은 것입니다. "
              f"data 노드에서 systemctl list-timers pickage-weekly.timer.", ref=f"expected:{ex.get('week_of')}")
    stale = timedelta(hours=weekly.get("stale_running_hours") or 26)
    # 모든 회차를 본다 — 타이머는 이번 주만 판정하므로 지난 회차의 BLOCKED·FAILED 는 수동 요청 외에 되살릴 길이 없다.
    for i, r in enumerate(weekly.get("runs") or []):
        week, status = r.get("week_of"), r.get("status")
        latest = i == 0
        pending = bool((r.get("manual") or {}).get("pending"))
        failures = r.get("consecutive_failures") or 0
        if status == "BLOCKED":
            if pending:
                out.warn("weekly-blocked", sec, f"{week} 가 BLOCKED 이고 수동 실행 요청이 걸려 있습니다 — 다음 발화(최대 10분)가 집어 갑니다.", ref=week)
            elif latest:
                out.bad("weekly-blocked", sec, f"주간 회차 {week} 가 BLOCKED — 연속 {failures}회 실패로 자동 재시도가 멈췄습니다. 수동 실행 요청이 필요합니다.", ref=week)
            else:
                out.bad("weekly-blocked", sec, f"지난 회차 {week} 가 BLOCKED 인 채 수동 요청도 없습니다 — 타이머는 이번 주만 보므로 이 회차를 되살릴 길은 "
                                              f"수동 실행 요청뿐입니다. npm 다운로드는 18개월 상한이라 오래 둘수록 다시 받을 수 없게 됩니다.", ref=week)
        elif status == "FAILED":
            if latest:
                out.warn("weekly-failed", sec, f"주간 회차 {week} 가 FAILED (연속 {failures}회). 10분 뒤 타이머가 다시 시도합니다.", ref=week)
            else:
                out.warn("weekly-failed", sec, f"지난 회차 {week} 가 FAILED 로 남았습니다 — 타이머는 이번 주만 보므로 자동 재시도가 없습니다."
                                              + (" 수동 요청이 걸려 있어 다음 발화가 집어 갑니다." if pending else " 수동 실행 요청이 필요합니다."), ref=week)
        elif status == "RUNNING":
            started = _t(r.get("started_at"))
            if started and now - started > stale:
                out.warn("weekly-stale", sec, f"{week} 가 {_hours(now - started)} 넘게 RUNNING 입니다 — 실행기가 죽은 것으로 보는 기준"
                                             f"({int(stale.total_seconds() // 3600)}시간)을 넘었습니다. 다음 발화가 이어받거나, systemd 상한에 걸려 "
                                             f"죽었을 수 있습니다. 로컬 디스크 탭의 단계 로그를 봅니다.", ref=week)
        if pending and status not in ("BLOCKED", "FAILED"):
            out.warn("weekly-manual", sec, f"{week} 수동 실행 요청이 아직 처리되지 않았습니다 (최대 10분).", ref=week)


def _curated(cur: dict | None, out: _Out, now: datetime) -> None:
    if not cur:
        return
    sec = f"{out.node}-curated"
    disp = cur.get("dispatcher")
    if disp and disp.get("status") != "TICK_FINISHED":
        message = (disp.get("error") or {}).get("message") or ""
        out.warn("curated-dispatcher", sec, f"Curated 디스패처가 회차를 고르기 전에 멈췄습니다 ({disp.get('status')}) — {message}. "
                                           f"MinIO 연결이나 baseline(_current.json) 을 봅니다.", ref="_dispatcher")
    for r in cur.get("runs") or []:
        snap, status = r.get("snapshot"), r.get("status")
        failing = next((s for s in r.get("stages") or [] if s.get("status") == "FAILED"), None)
        phase = r.get("phase")
        where = (f" ({STAGE_KO.get(phase, phase)} 단계)" if phase and phase != "COMPLETE"
                 else f" ({STAGE_KO.get(failing['stage'], failing['stage'])} 단계)" if failing else "")
        if status == "BLOCKED":
            out.bad("curated-blocked", sec, f"Curated 전처리 {snap} 가 BLOCKED{where} — 자동 재시도가 멈췄습니다. 원인을 고친 뒤 "
                                            f"run-curated-retry.sh --retry-snapshot {snap}.", ref=snap)
        elif status == "FAILED":
            retry = _t(r.get("next_retry_at"))
            when = ""
            if retry:
                left = retry - now
                when = " 다음 발화에 다시 시도합니다." if left <= timedelta(0) else f" {_hours(left)} 뒤 다시 시도합니다."
            out.warn("curated-failed", sec, f"Curated 전처리 {snap} 가 FAILED{where} (연속 {r.get('consecutive_failures') or 0}회, "
                                            f"시도 {r.get('attempt') or 0}회).{when}", ref=snap)
        elif status == "RUNNING":
            started = _t(r.get("started_at"))
            if started and now - started > CURATED_STALE_RUNNING:
                out.warn("curated-stale", sec, f"Curated 전처리 {snap} 가 {_hours(now - started)} 넘게 RUNNING 입니다{where}. "
                                               f"systemd 상한(36h)에 걸려 죽었을 수 있습니다.", ref=snap)


def _events(minio: dict | None, out: _Out) -> None:
    ev = (minio or {}).get("events")
    if not ev:
        return
    sec = f"{out.node}-events"
    disc = ev.get("discovery") or {}
    if disc.get("pending"):
        out.warn("events-discovery", sec, f"{out.node}: MinIO 버킷 목록을 아직 못 받아 이벤트 구독이 걸리지 않았습니다 ({disc.get('attempts') or 0}회 시도"
                                          + (f" — {disc.get('error')}" if disc.get("error") else "") + "). MinIO 가 뜨면 저절로 붙습니다.", ref="_discovery")
    for name, b in sorted((ev.get("buckets") or {}).items()):
        if not b.get("connected"):
            out.warn("events-disconnected", sec, f"{out.node}: MinIO {name} 이벤트 구독이 끊겨 있습니다 — {b.get('error') or ''}. 이 사이에 생긴 것은 화면에 안 옵니다.", ref=name)
    if ev.get("full") or (ev.get("held") or 0) >= (ev.get("max_events") or 1):
        dropped = ev.get("dropped") or 0
        out.warn("events-full", sec, f"{out.node}: MinIO 이벤트 버퍼가 한도({ev.get('max_events'):,}건)에 닿아 오래된 것은 버려졌습니다"
                                     + (f" (지금까지 {dropped:,}건)" if dropped else "")
                                     + " — 이 절의 개수·크기가 실제보다 적습니다. 백필 중이면 정상이고, 전체 개수는 \"MinIO 전체 목록\" 탭으로 봅니다. "
                                       "계속 그러면 events_max 를 올립니다.", ref="_buffer")


def _local(local: dict | None, out: _Out) -> None:
    if not local:
        return
    sec = f"{out.node}-local"
    for p in local.get("paths") or []:
        label = p.get("label")
        if p.get("missing"):
            out.warn("disk-missing", sec, f"{out.node}: {label} 이 없습니다 (마운트 확인).", ref=label)
            continue
        d = p.get("disk") or {}
        if d.get("total"):
            free = 100 - d["used"] / d["total"] * 100
            if free < DISK_FREE_BAD:
                out.bad("disk-free", sec, f"{out.node}: {label} 이 있는 파티션의 남은 공간이 {free:.0f}% 입니다.", ref=label)
            elif free < DISK_FREE_WARN:
                out.warn("disk-free", sec, f"{out.node}: {label} 이 있는 파티션의 남은 공간이 {free:.0f}% 입니다.", ref=label)
    min_lines = local.get("error_min_lines")
    min_lines = 1 if min_lines is None else min_lines
    for l in local.get("logs") or []:
        n = l.get("error_lines") or 0
        if n and min_lines > 0 and n >= min_lines:
            out.warn("log-error", sec, f"{out.node}: 단계 로그 {l.get('path')} 꼬리에 에러로 보이는 줄이 {n}개 있습니다 (기준 {min_lines}줄).", ref=l.get("path"))


def _docker(docker: dict | None, out: _Out, now: datetime) -> None:
    if not docker:
        return
    sec = f"{out.node}-docker"
    min_lines = docker.get("error_min_lines")
    min_lines = 3 if min_lines is None else min_lines
    for c in docker.get("containers") or []:
        name, state = c.get("name"), c.get("state")
        if state == "restarting":
            out.bad("container", sec, f"{out.node}: {name} 가 계속 재시작하고 있습니다.", ref=name)
        elif state == "paused":
            out.bad("container", sec, f"{out.node}: {name} 가 docker pause 로 멈춰 있습니다 — 살아 있는 것처럼 보이지만 아무 일도 하지 않습니다. docker unpause.", ref=name)
        elif state == "dead":
            out.bad("container", sec, f"{out.node}: {name} 가 dead 상태입니다 — 데몬이 정리하지 못한 컨테이너. docker rm 뒤 다시 up.", ref=name)
        elif state == "created":
            out.warn("container", sec, f"{out.node}: {name} 가 만들어졌지만 시작되지 않았습니다 — compose up 이 중간에 실패했거나 의존 컨테이너를 기다리다 멈춘 것. docker compose up -d 를 다시.", ref=name)
        elif state == "exited" and (c.get("exit_code") or 0) != 0:
            finished = _t(c.get("finished_at"))
            ago = f" ({_hours(now - finished)} 전)" if finished else ""
            out.warn("container", sec, f"{out.node}: {name} 가 종료 코드 {c.get('exit_code')} 로 끝났습니다{ago}.", ref=name)
        elif state not in ("running", "exited", "removing"):
            out.warn("container", sec, f"{out.node}: {name} 의 상태가 \"{state}\" 입니다 — 화면이 모르는 값. docker inspect 로 봅니다.", ref=name)
        if c.get("oom_killed"):
            out.bad("container-oom", sec, f"{out.node}: {name} 가 OOM 으로 죽었습니다 — mem_limit 을 보세요.", ref=name)
        if c.get("health") == "unhealthy":
            out.bad("container-health", sec, f"{out.node}: {name} healthcheck 실패.", ref=name)
        log = c.get("log") or {}
        n = log.get("error_lines") or 0
        if n and min_lines > 0 and n >= min_lines:
            out.warn("log-error", sec, f"{out.node}: {name} 로그 꼬리({log.get('since_hours')}시간)에 에러로 보이는 줄이 {n}개 있습니다 (기준 {min_lines}줄). "
                                       f"재기동 직후의 대기 메시지면 error_ignore_pattern 에 적습니다.", ref=name)


def evaluate(report: dict, *, now: datetime) -> list[dict]:
    """보고서 하나 → findings. 문제(bad)가 먼저, 그 다음 주의(warn). 같은 수준 안에서는 절 순서(만든 순서)다."""
    out = _Out(report.get("node") or "?")
    _report_errors(report, out)
    _weekly(report.get("weekly"), out, now)
    _curated(report.get("curated"), out, now)
    _events(report.get("minio"), out)
    _local(report.get("local"), out)
    _docker(report.get("docker"), out, now)
    return [f for f in out.items if f["level"] == "bad"] + [f for f in out.items if f["level"] == "warn"]


def worst(findings: list[dict]) -> str:
    if any(f["level"] == "bad" for f in findings):
        return "bad"
    return "warn" if findings else "ok"
