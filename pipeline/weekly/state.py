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

from .schedule import (MAX_CONSECUTIVE_FAILURES, STEPS, RunRecord,
                       is_manual_pending, window_end, window_start)

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


# 우편함 객체의 이름. `ObjectStore.manual_weeks()` 가 키 목록에서 이 이름으로 회차를
# 골라내므로 두 곳에 따로 적지 않는다.
MANUAL_NAME = "manual-request.json"


def manual_key(week_of: date) -> str:
    return f"{PREFIX}/{week_of.isoformat()}/{MANUAL_NAME}"


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

    def manual_weeks(self) -> list[date]:
        """**우편함 객체가 있는** 회차 날짜. 오래된 것부터.

        `weeks()` 를 쓰고 회차마다 우편함을 GET 하면 1년에 52회다 — 10분마다 그걸 하면
        "대부분의 발화는 객체 하나를 읽고 끝난다" 가 거짓이 된다. 여기서는 Delimiter 없이
        키를 직접 훑어 **LIST 한 번**으로 우편함이 있는 주만 걸러 낸다. 우편함은 사람이
        누를 때만 생기므로 평소에는 빈 목록이고, 뒤따르는 GET 이 0이다.
        """
        suffix = "/" + MANUAL_NAME
        found = []
        token = None
        while True:
            request = {"Bucket": self.bucket, "Prefix": PREFIX + "/"}
            if token:
                request["ContinuationToken"] = token
            page = self.s3.list_objects_v2(**request)
            for item in page.get("Contents", []):
                key = item["Key"]
                if not key.endswith(suffix):
                    continue
                name = key[len(PREFIX) + 1:-len(suffix)]
                try:
                    found.append(date.fromisoformat(name))
                except ValueError:
                    continue   # 회차 날짜가 아닌 것은 건드리지 않는다. weeks() 와 같은 태도다
            if not page.get("IsTruncated"):
                break
            token = page.get("NextContinuationToken")
        return sorted(found)


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


class StagedStore:
    """**드라이런 전용.** 읽기는 진짜 저장소를 보고, 쓰기는 메모리에만 남긴다.

    드라이런이 운영 회차 객체를 건드리면 안 된다. 단계를 하나도 돌리지 않고 `SUCCEEDED`
    를 적어 버리면 **그 주 수집이 통째로 건너뛰어진다** — `decide()` 가 "이미 끝났다" 로
    보고 창이 열려도 시작하지 않는다. 운영 README 의 설치 절차가 타이머를 켜기 전에
    드라이런을 한 번 돌리게 하므로, 그 절차가 곧 사고 경로였다.

    **쓰기를 막기만 하면 안 된다.** 실행기는 마지막에 저장소를 다시 읽어 끝났는지 본다
    (`run.py` 의 `_execute`). 쓴 것이 안 보이면 드라이런은 늘 "남은 단계가 있다" 로
    끝나 판정을 흉내 내지 못한다. 그래서 버리지 않고 **메모리에 쌓아 그것을 읽게** 한다 —
    드라이런은 진짜 실행과 같은 경로를 그대로 탄다.
    """

    def __init__(self, inner: ObjectStore):
        self.inner = inner
        self.bucket = inner.bucket
        self.staged: dict[str, dict] = {}

    def get(self, key: str) -> dict | None:
        if key in self.staged:
            return _copy(self.staged[key])
        return self.inner.get(key)

    def put(self, key: str, payload: dict) -> None:
        # 부르는 쪽이 같은 dict 를 계속 고쳐 쓰므로(WeeklyState._document) 사본을 둔다.
        # 참조를 그대로 두면 "저장된 것" 이 나중 수정에 따라 바뀐다.
        self.staged[key] = _copy(payload)

    def weeks(self) -> list[date]:
        return self.inner.weeks()

    def manual_weeks(self) -> list[date]:
        return self.inner.manual_weeks()


def _copy(payload: dict) -> dict:
    # 상태 객체는 JSON 직렬화가 계약이다. 그 왕복으로 깊은 사본을 만든다 —
    # 직렬화할 수 없는 값이 섞이면 드라이런에서 먼저 드러난다.
    return json.loads(json.dumps(payload))


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


class CorruptState(RuntimeError):
    """상태 객체를 믿을 수 없다. **사람이 고쳐야 한다.**

    빠진 값을 기본값으로 때우지 않는 이유가 있다. `status` 를 None 으로 채우면
    `decide()` 의 세 가드(RUNNING·SUCCEEDED·BLOCKED)를 전부 빠져나가 "이어받기" 로
    떨어지는데, 그러면 **이미 성공한 주를 23시간 들여 다시 받고 Bronze 에 중복 업로드한다.**
    조용히 틀리는 것보다 멈추는 쪽이 싸다.
    """


def _record(document: dict, manual: dict) -> RunRecord:
    # 이 둘이 없으면 회차를 식별할 수도, 무엇을 할지 정할 수도 없다.
    missing = [key for key in ("week_of", "status") if not document.get(key)]
    if missing:
        raise CorruptState(
            "회차 객체에 " + ", ".join(missing) + " 가 없다. "
            "손으로 고쳤거나 다른 내용이 덮어써진 것이다 — "
            "pickage-raw/_ops/weekly/<week_of>/run.json 을 확인할 것")
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

    def pending_manual_weeks(self, exclude: date) -> list[date]:
        """아직 집어 가지 않은 수동 실행 요청이 걸린 지난 회차. **오래된 것부터.**

        타이머는 이번 주만 본다. 그래서 지난주가 `BLOCKED` 인 채 주가 넘어가면, 그 주에
        건 수동 요청은 **영원히 읽히지 않는다** — 백엔드는 200 을 주고 `manual_pending`
        을 계속 참으로 돌려주므로 요청한 사람은 처리되는 줄 안다. `BLOCKED` 를 푸는
        유일한 수단이 수동 요청이니, 그 경우 회차를 되살릴 방법이 아예 없어진다.

        오래된 것부터 고르는 이유: npm 개별 호출의 구간 상한이 18개월이라 **다시 받을 수
        있는 한계에 가장 가까운 것이 가장 급하다.**

        회차 객체가 없고 우편함만 있는 주도 센다. 한 번도 돌지 않은 주에 건 요청이 그렇다.
        """
        found = []
        for week in self.store.manual_weeks():
            if week == exclude:
                continue
            manual = self.store.get(manual_key(week)) or {}
            requested = _moment(manual.get("requested_at"))
            if requested is None:
                continue
            # 손상된 지난 회차 하나가 이번 발화를 통째로 막지 않게, 여기서는 _record()
            # (CorruptState 를 던진다) 를 태우지 않고 필요한 값만 본다. 고를 뿐이고,
            # 고른 뒤 load() 가 제대로 읽으면서 손상은 그때 드러난다.
            document = self.store.get(run_key(week)) or {}
            if is_manual_pending(requested, _moment(document.get("manual_claimed_at"))):
                found.append(week)
        return sorted(found)

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

    def reset_steps(self, week_of: date, steps: list[str]) -> None:
        """이 단계들의 기록을 지운다. `--force` 만 부른다.

        지우지 않으면 강제 재실행이 중간에 실패했을 때 **뒤 단계의 옛 `SUCCEEDED` 가
        그대로 남는다.** 다음 발화는 실패한 단계만 다시 돌리고 뒤를 건너뛰므로, 새로 받은
        상류 산출물 위에 **이전 회차의 입고 결과가 최신인 척** 남는다.

        ⚠ **`selected` 만 지운다. 전부 지우면 안 된다.** `--force --only bronze_downloads`
        로 전부 지우면 앞 다섯 단계의 기록이 사라지고 회차가 `PENDING` 으로 내려가,
        다음 발화가 23시간짜리 수집을 처음부터 다시 돈다.
        """
        target = set(steps)
        keep = [item for item in self._document["steps"] if item["step"] not in target]
        if len(keep) == len(self._document["steps"]):
            return   # 지울 것이 없으면 PUT 도 하지 않는다
        self._document["steps"] = keep
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
