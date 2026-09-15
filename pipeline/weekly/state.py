"""주간 회차의 상태를 MinIO 객체로 읽고 쓴다.

    pickage-raw/_ops/weekly/<week_of>/run.json             러너만 쓴다
    pickage-raw/_ops/weekly/<week_of>/manual-request.json  백엔드만 쓴다 (우편함)

**객체마다 필자가 하나라 경쟁이 없다.** 러너는 한 번에 하나만 돌고(호스트 flock + 고정
컨테이너 이름), 백엔드는 우편함만 쓴다. 그래서 읽고-고쳐-쓰기를 잠금 없이 해도 된다.

왜 `pickage-raw` 안인가 — 이 저장소의 관례가 "실행 메타데이터는 데이터 옆, 같은 버킷"이다
(`run_manifest.json`·`_SUCCESS`, curated 의 `_current.json`). `pipeline/minio/README.md` 의
버킷 표도 `pickage-raw` 의 저장 대상에 "원본·검증 manifest, 완료 표시"를 이미 넣어 두었고,
주간 회차 6단계의 산출물이 전부 이 한 버킷에 떨어진다. 운영용 버킷을 따로 파면 데이터와
그 입고 이력이 갈린다.

목록 조회용 `_index.json` 은 두지 않는다. 주 단위라 1년치가 객체 52개뿐이고, 인덱스를 두면
`run.json` 과 어긋날 수 있는 **두 번째 진실**이 생긴다.

시계는 이 프로세스의 것을 쓴다. 이전 구현(PostgreSQL)은 `now()` 를 DB 에서 받아 왔는데,
`started_at` 을 쓰는 쪽과 `STALE_RUNNING` 을 재는 쪽이 다른 시계일 수 있었기 때문이다.
지금은 **둘 다 이 프로세스**라 그 문제가 없다.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

from .schedule import (MAX_CONSECUTIVE_FAILURES, STEPS, RunRecord, window_end,
                       window_start)

BUCKET = "pickage-raw"
# 최상위 `_ops/`. 이 저장소의 `list_objects_v2` 는 전부 prefix 한정이라(`depsdev/v1/…`,
# `npm-downloads/v1/run_id=…`) 버킷 루트를 훑는 코드가 없다. 그래서 새 prefix 가 기존
# 입고·검증 로직에 걸리지 않는다. `_` 는 이미 `_SUCCESS`·`_MANIFEST.json`·`_current.json`
# 으로 "데이터가 아닌 것" 을 뜻한다.
PREFIX = "_ops/weekly"
# 실패 메시지를 이만큼만 싣는다. 전문은 단계별 로그 파일에 남는다.
ERROR_LIMIT = 4000


def run_key(week_of: date) -> str:
    return f"{PREFIX}/{week_of.isoformat()}/run.json"


def manual_key(week_of: date) -> str:
    return f"{PREFIX}/{week_of.isoformat()}/manual-request.json"


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


def _moment(value) -> datetime | None:
    return None if value in (None, "") else datetime.fromisoformat(value)


def coverage(week_of: date) -> dict:
    """이 회차가 **어느 날짜 데이터까지** 담는지.

    전부 `week_of` 에서 유도되므로 계산해서 넣어도 되지만, 그러면 읽는 쪽이 규칙을 알아야
    한다. 이전 스키마에 이 값이 없어서 "언제까지 수집됐나" 에 답하려면 코드를 봐야 했다.
    """
    return {
        "depsdev_snapshot": week_of.isoformat(),
        "downloads_through": window_end(week_of).isoformat(),
        "downloads_window": [window_start(week_of).isoformat(),
                             window_end(week_of).isoformat()],
    }


class ObjectStore:
    """JSON 객체 하나를 읽고 쓰는 것이 한 단위다. 세션을 유지하지 않는다."""

    def __init__(self, s3, bucket: str = BUCKET):
        self.s3 = s3
        self.bucket = bucket

    def get(self, key: str) -> dict | None:
        """없으면 None. 없는 것과 비어 있는 것을 구별한다."""
        try:
            response = self.s3.get_object(Bucket=self.bucket, Key=key)
        except Exception as error:  # botocore 예외 이름에 묶이지 않게 코드로 본다
            if _missing(error):
                return None
            raise
        with response["Body"] as stream:
            return json.loads(stream.read().decode("utf-8"))

    def put(self, key: str, payload: dict) -> None:
        # 사람이 `mc cat` 으로 읽는 파일이다(운영 API 가 배포되기 전까지는 그게 유일한
        # 확인 경로다). 들여쓰기와 한글을 그대로 둔다.
        body = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False)
        self.s3.put_object(Bucket=self.bucket, Key=key,
                           Body=body.encode("utf-8"),
                           ContentType="application/json; charset=utf-8")

    def weeks(self) -> list[date]:
        """저장된 회차 날짜. 최신순."""
        found = []
        token = None
        while True:
            request = {"Bucket": self.bucket, "Prefix": PREFIX + "/", "Delimiter": "/"}
            if token:
                request["ContinuationToken"] = token
            page = self.s3.list_objects_v2(**request)
            for item in page.get("CommonPrefixes", []):
                name = item["Prefix"].rstrip("/").rsplit("/", 1)[-1]
                try:
                    found.append(date.fromisoformat(name))
                except ValueError:
                    # 회차 날짜가 아닌 것이 섞여 있어도 멈추지 않는다. 지우는 판단에
                    # 쓰이는 목록이라, 모르는 이름은 건드리지 않는 쪽이 안전하다.
                    continue
            if not page.get("IsTruncated"):
                break
            token = page.get("NextContinuationToken")
        return sorted(found, reverse=True)


def _missing(error) -> bool:
    response = getattr(error, "response", None)
    if not isinstance(response, dict):
        return False
    code = str(response.get("Error", {}).get("Code", ""))
    status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    return code in ("NoSuchKey", "404", "NotFound") or status == 404


def open_store(bucket: str = BUCKET) -> ObjectStore:
    """자격증명 파일을 읽어 S3 클라이언트를 만든다.

    `client()` 는 `pipeline/minio/<PICKAGE_MINIO_ENV 또는 .env>` **파일**에서
    엔드포인트와 키를 읽는다(환경변수가 아니다). 열 개 넘는 모듈이 쓰는 그 함수를 그대로
    쓴다 — 다섯 번째 자격증명 로더를 만들 이유가 없다.

    임포트를 함수 안에 두는 이유: 저 모듈이 최상단에서 boto3·duckdb 를 끌어와서, 단위
    시험이 그 의존성까지 불러오게 된다. `similar_package/load.py` 가 같은 이유로 같은
    모양을 쓴다.
    """
    from pipeline.minio.ingest_raw import client

    return ObjectStore(client(), bucket=bucket)


def blank(week_of: date) -> dict:
    return {
        "week_of": week_of.isoformat(),
        "status": "PENDING",
        "coverage": coverage(week_of),
        "started_at": None,
        "finished_at": None,
        "consecutive_failures": 0,
        "last_error": None,
        "manual_claimed_at": None,
        "updated_at": None,
        "steps": [],
    }


def _record(document: dict, manual: dict) -> RunRecord:
    return RunRecord(
        week_of=date.fromisoformat(document["week_of"]),
        status=document["status"],
        started_at=_moment(document.get("started_at")),
        finished_at=_moment(document.get("finished_at")),
        consecutive_failures=document.get("consecutive_failures") or 0,
        # 우편함은 다른 객체다. 백엔드가 쓰고 러너가 읽는다.
        manual_request_at=_moment(manual.get("requested_at")),
        manual_claimed_at=_moment(document.get("manual_claimed_at")),
        last_error=document.get("last_error"),
    )


class WeeklyState:
    def __init__(self, store: ObjectStore, *,
                 max_failures: int = MAX_CONSECUTIVE_FAILURES, clock=None):
        self.store = store
        self.max_failures = max_failures
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._document: dict | None = None

    # ── 읽기 ────────────────────────────────────────────────────

    def load(self, week_of: date) -> tuple[datetime, RunRecord | None, list[dict]]:
        """현재 시각·회차·단계를 읽는다.

        **우편함만 있고 회차 객체가 없는 경우도 회차로 친다.** 이전 구현에서는 백엔드가
        수동 요청을 쓸 때 `INSERT … ON CONFLICT` 로 회차 행까지 만들었지만, 지금 백엔드는
        `manual-request.json` 하나만 쓴다. 여기서 None 을 돌려주면 한 번도 돌지 않은 주에
        건 수동 요청이 **수집 창이 열릴 때까지 무시된다.**
        """
        document = self.store.get(run_key(week_of))
        manual = self.store.get(manual_key(week_of)) or {}
        now = self._clock()
        if document is None and not manual:
            self._document = blank(week_of)
            return now, None, []
        self._document = document or blank(week_of)
        return now, _record(self._document, manual), list(self._document.get("steps", []))

    def purgeable_weeks(self, week_of: date, keep: int) -> list[date]:
        """로컬 산출물을 지워도 되는 지난 회차. 가장 최근 keep 개는 남긴다.

        **SUCCEEDED 만 고른다.** 실패했거나 도는 중인 회차의 산출물을 지우면 체크포인트가
        사라져 그 주를 처음부터 다시 받아야 한다(약 23시간). SUCCEEDED 는 Bronze 입고까지
        끝났다는 뜻이고, 그 뒤로 로컬 사본은 사본일 뿐이다.
        """
        if keep < 0:
            raise ValueError("keep must not be negative")
        done = []
        for week in self.store.weeks():
            if week >= week_of:
                continue
            document = self.store.get(run_key(week))
            if document and document.get("status") == "SUCCEEDED":
                done.append(week)
        return sorted(done, reverse=True)[keep:]

    # ── 쓰기 ────────────────────────────────────────────────────

    def _flush(self) -> None:
        assert self._document is not None, "load() 를 먼저 불러야 한다"
        self._document["updated_at"] = _stamp(self._clock())
        self.store.put(run_key(date.fromisoformat(self._document["week_of"])),
                       self._document)

    def _step(self, step: str) -> dict:
        for item in self._document["steps"]:
            if item["step"] == step:
                return item
        item = {"step": step, "status": "PENDING", "attempt_count": 0,
                "started_at": None, "finished_at": None,
                "error_message": None, "detail": {}}
        # STEPS 순서를 지킨다. 사람이 읽는 파일이라 실행 순서대로 보여야 한다.
        self._document["steps"].append(item)
        order = {name: index for index, name in enumerate(STEPS)}
        self._document["steps"].sort(key=lambda row: order.get(row["step"], len(STEPS)))
        return item

    def begin(self, week_of: date, *, claim_manual: bool) -> None:
        now = _stamp(self._clock())
        document = self._document
        document["status"] = "RUNNING"
        document["started_at"] = now
        document["finished_at"] = None
        document["coverage"] = coverage(week_of)
        if claim_manual:
            document["manual_claimed_at"] = now
            # 수동 요청을 집어 간 회차는 실패 누적을 0으로 되돌린다.
            # 그래야 BLOCKED 가 실제로 풀린다.
            document["consecutive_failures"] = 0
        self._flush()

    def step_start(self, week_of: date, step: str) -> None:
        item = self._step(step)
        item["status"] = "RUNNING"
        item["attempt_count"] = (item.get("attempt_count") or 0) + 1
        item["started_at"] = _stamp(self._clock())
        item["finished_at"] = None
        item["error_message"] = None
        self._flush()

    def step_finish(self, week_of: date, step: str, status: str, *,
                    detail: dict | None = None, error: str | None = None) -> None:
        item = self._step(step)
        item["status"] = status
        item["finished_at"] = _stamp(self._clock())
        item["error_message"] = error[:ERROR_LIMIT] if error else None
        item["detail"] = detail or {}
        self._flush()

    def succeed(self, week_of: date) -> None:
        document = self._document
        document["status"] = "SUCCEEDED"
        document["finished_at"] = _stamp(self._clock())
        document["consecutive_failures"] = 0
        document["last_error"] = None
        self._flush()

    def pause(self, week_of: date) -> None:
        """실패 없이 끝났지만 아직 남은 단계가 있는 회차.

        `--only` 로 한 단계만 돌렸거나 원천이 아직 준비되지 않았을 때가 이 경우다. 실패가
        아니므로 연속 실패 횟수는 건드리지 않고, RUNNING 만 풀어 다음 발화가 이어받게 한다.
        """
        document = self._document
        document["status"] = "PENDING"
        document["finished_at"] = _stamp(self._clock())
        self._flush()

    def fail(self, week_of: date, error: str) -> tuple[str, int]:
        """실패를 기록하고 (새 상태, 연속 실패 횟수) 를 돌려준다."""
        document = self._document
        count = (document.get("consecutive_failures") or 0) + 1
        document["consecutive_failures"] = count
        document["status"] = "BLOCKED" if count >= self.max_failures else "FAILED"
        document["finished_at"] = _stamp(self._clock())
        document["last_error"] = error[:ERROR_LIMIT]
        self._flush()
        return document["status"], count
