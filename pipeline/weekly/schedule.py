"""주간 수집 회차의 날짜 규약과 "지금 무엇을 할 것인가" 판정.

부수효과가 없다. DB도 네트워크도 건드리지 않으므로 단위 시험으로 전부 덮을 수 있고,
이 파일이 틀리면 같은 주를 두 번 받거나 한 주를 통째로 건너뛴다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

# 한국은 서머타임이 없어 고정 오프셋으로 충분하다.
KST = timezone(timedelta(hours=9))

STEPS = (
    "depsdev_t2",
    "gcs_sync",
    "downloads_weekly",
    "downloads_parquet",
    "bronze_depsdev",
    "bronze_downloads",
)

MAX_CONSECUTIVE_FAILURES = 10
# 회차가 끝난 뒤 로컬에 남겨 둘 지난 회차 수. 이보다 오래된 SUCCEEDED 회차는 지운다.
# 산출물이 주당 약 10 GB 라 그냥 두면 data 노드 디스크를 잠식한다 — 거기서는 MinIO 데이터와
# 같은 파티션이라, 채우면 수집만 멈추는 게 아니라 저장소가 통째로 선다.
# 2주를 남기는 이유는 downloads 창이 14일이라 직전 한 주까지만 다시 필요할 수 있어서다.
KEEP_WEEKS = 2
# RUNNING 인 채로 이만큼 지나면 죽은 실행으로 보고 회수한다.
# downloads 한 바퀴가 약 23시간이라(상위 10만 중 스코프 54.6%는 벌크를 못 써서 개별 호출,
# IP 지속 한도 분당 약 40건) 그보다 넉넉해야 정상 실행을 죽이지 않는다.
STALE_RUNNING = timedelta(hours=26)
# 원천(deps.dev 스냅샷)이 아직 안 나왔을 때 얼마나 조용히 기다릴지. 창이 열린 뒤 이만큼은
# 실패로 세지 않는다 — 공급자 지연은 실패가 아니라 "아직" 이고, 기다리면 해결된다.
# 이 시간을 넘기면 그때는 사람이 봐야 할 일로 보고 실패로 올린다.
# 12시간이면 화 10:00 KST 에서 화 22:00 KST 까지다. 기다리는 동안 10분마다 BigQuery
# Snapshots 를 한 번씩 보는데 쿼리당 최소 과금 10 MB 라 최악이 720 MB 다.
SNAPSHOT_GRACE = timedelta(hours=12)
# 수집 창은 화요일 10:00 KST 에 열린다. deps.dev 는 월요일 21:01 UTC(= 화 06:01 KST)에
# 스냅샷을 올리고, downloads 수집계획 2-2 가 갱신 시각을 화 10:00 KST 이후로 정했다.
WINDOW_OPEN_KST_HOUR = 10


def _aware(moment: datetime) -> datetime:
    """시간대 없는 datetime 을 거부한다.

    astimezone() 은 naive 값을 시스템 지역시간으로 가정해 조용히 다른 답을 낸다.
    회차 판정이 서버 지역시간에 따라 달라지면 재현이 안 된다.
    """
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("시간대가 없는 datetime 은 쓸 수 없다: " + moment.isoformat())
    return moment


def current_week_of(now_utc: datetime) -> date:
    """그 시점이 속한 주의 월요일(UTC). deps.dev 스냅샷 날짜와 같은 값이다."""
    day = _aware(now_utc).astimezone(timezone.utc).date()
    return day - timedelta(days=day.weekday())


def run_day(week_of: date) -> date:
    """수집 실행일 = 그 주 화요일."""
    return week_of + timedelta(days=1)


def window_end(week_of: date) -> date:
    """downloads 14일 창의 끝 = 직전 일요일.

    npm 일별 집계는 UTC 기준이고 확정까지 이틀쯤 걸린다. 화요일 10:00 KST(= 01:00 UTC)에
    마지막으로 확정된 날이 직전 일요일이며, 이는 수집기 자체 기본값(utcnow - 2일)과도 같다.
    실행일이 아니라 week_of 에서 계산하므로 수요일에 재시작해도 창이 흔들리지 않는다 —
    창이 바뀌면 작업 id가 전부 달라져 처음부터 다시 받는다.
    """
    return week_of - timedelta(days=1)


def window_start(week_of: date) -> date:
    """14일 창의 시작. 직전 회차와 7일이 겹치고 7일이 새로 들어온다."""
    return window_end(week_of) - timedelta(days=13)


def window_open_at(week_of: date) -> datetime:
    """그 회차의 수집 창이 열리는 시각."""
    return datetime.combine(run_day(week_of), time(WINDOW_OPEN_KST_HOUR), tzinfo=KST)


def window_open(week_of: date, now_utc: datetime) -> bool:
    return _aware(now_utc).astimezone(KST) >= window_open_at(week_of)


def snapshot_grace_expired(week_of: date, now_utc: datetime, *,
                           grace: timedelta = SNAPSHOT_GRACE) -> bool:
    """원천을 더 기다리지 않고 실패로 올릴 때가 됐는가.

    창이 열린 시각부터 잰다. 실행기가 처음 시도한 시각이 아니다 — 타이머가 멈춰 있다가
    늦게 깨어났다고 해서 유예가 늘어나면 안 된다.
    """
    return _aware(now_utc) >= window_open_at(week_of) + grace


def download_run(week_of: date) -> str:
    """downloads 수집기의 --run 값. 실행일이 아니라 회차에서 유도해 재시작에 흔들리지 않게 한다."""
    return run_day(week_of).isoformat()


def bronze_run_id(week_of: date, source: str) -> str:
    """MinIO Bronze run_id.

    --run-id 를 생략하면 입고기가 타임스탬프와 uuid 로 새 값을 만들어 매번 다른 경로에 같은
    데이터를 또 올린다. 회차에서 유도한 결정적 값이라야 재실행이 멱등이 된다.
    """
    if source not in ("bronze", "downloads"):
        raise ValueError("unknown bronze source: " + source)
    return f"{source}-weekly-{week_of:%Y%m%d}"


@dataclass(frozen=True)
class RunRecord:
    """회차 하나의 상태.

    **저장소를 모른다.** 이 파일 전체가 그렇다 — 값만 채워 주면 decide() 가 돈다.
    지금은 state.py 가 MinIO 의 run.json 에서 만들어 넣는다.
    """

    week_of: date
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    consecutive_failures: int = 0
    manual_request_at: datetime | None = None
    manual_claimed_at: datetime | None = None
    last_error: str | None = None

    @property
    def manual_pending(self) -> bool:
        """백엔드가 넣은 수동 실행 요청 중 아직 집어 가지 않은 것이 있는가."""
        if self.manual_request_at is None:
            return False
        return self.manual_claimed_at is None or self.manual_claimed_at < self.manual_request_at


@dataclass(frozen=True)
class Decision:
    run: bool
    reason: str
    claim_manual: bool = False


def decide(
    record: RunRecord | None,
    week_of: date,
    now_utc: datetime,
    *,
    force: bool = False,
    max_failures: int = MAX_CONSECUTIVE_FAILURES,
    stale_after: timedelta = STALE_RUNNING,
) -> Decision:
    """이번 발화에서 실행할지 판정한다.

    호출 순서가 곧 비용 순서다 — 여기까지는 PostgreSQL 한 번만 읽었고 BigQuery 는 아직
    건드리지 않았다. Snapshots 조회는 쿼리당 최소 과금 10 MB라 10분마다 부르면 낭비다.
    """
    manual = record is not None and record.manual_pending

    # RUNNING 검사가 force 보다 앞이다. --force 로도 살아 있는 실행을 밀어내지 않는다 —
    # 같은 checkpoint.sqlite 를 두 프로세스가 쓰고 같은 IP 에서 npm 을 두 배로 두드리게 된다.
    # 셸 래퍼의 flock 이 막아 주지만 `python -m pipeline.weekly.run` 을 직접 부르면 그것도 없다.
    # 죽은 것으로 보이는(stale) 실행은 force 없이도 회수하므로 force 가 할 일이 없다.
    if record is not None and record.status == "RUNNING":
        started = record.started_at
        if started is not None and now_utc - started < stale_after:
            return Decision(False, "다른 실행이 진행 중이다")
        return Decision(True, "멈춘 실행을 회수한다", claim_manual=manual)

    if force:
        return Decision(True, "강제 실행(--force)", claim_manual=manual)

    if record is not None and record.status == "SUCCEEDED" and not manual:
        return Decision(False, "이번 주 회차는 이미 끝났다")

    if record is not None and record.status == "BLOCKED" and not manual:
        return Decision(
            False,
            f"연속 {record.consecutive_failures}회 실패로 멈춰 있다. 수동 실행 요청을 기다린다",
        )

    if not manual and not window_open(week_of, now_utc):
        return Decision(False, f"수집 창이 아직 열리지 않았다(화 {WINDOW_OPEN_KST_HOUR}:00 KST)")

    if manual:
        return Decision(True, "수동 실행 요청", claim_manual=True)
    if record is None:
        return Decision(True, "이번 주 회차가 아직 없다")
    return Decision(True, f"이어받기(직전 상태 {record.status})")
