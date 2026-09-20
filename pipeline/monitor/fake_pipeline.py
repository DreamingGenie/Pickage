"""가짜 파이프라인 — 화면을 눈으로 확인하기 위한 것. **운영에서 돌리지 않는다.**

실제 주간 회차가 남기는 흔적을 같은 모양으로 흉내 낸다:

    pickage-raw/_ops/weekly/<week>/run.json        단계가 하나씩 진행된다 (PENDING → RUNNING → SUCCEEDED)
    pickage-raw/depsdev/v1/.../_SUCCESS            입고가 끝나면 완료 표시가 찍힌다
    pickage-raw/npm-downloads/v1/run_id=.../data/  parquet 파트가 몇 초마다 하나씩 늘어난다
    <ingest-work>/downloads-weekly/<week>/logs/    단계별 로그가 쌓인다 (가끔 WARN·ERROR 줄)
    stdout                                          컨테이너 로그 (이름이 pickage-weekly-run 이라 화면에 잡힌다)

한 회차가 끝나면 다음 주차로 넘어가 계속 돈다. 지난 회차 셋(성공·성공·BLOCKED + 수동 요청)은
시작할 때 한 번 심는다 — 화면의 상태 종류를 다 볼 수 있게.

    FAKE_STEP_SECONDS   한 틱(파트 하나) 간격. 기본 8초
    FAKE_INGEST_WORK    로컬 산출물 루트. 기본 /host/srv/pickage/ingest-work
    PICKAGE_S3_*        MinIO 자격증명 (config.s3_credentials 와 같다)
"""
from __future__ import annotations

import json
import os
import random
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import boto3
from botocore.config import Config

RAW = "pickage-raw"
CURATED = "pickage-curated"
VECTORS = "pickage-vectors"
STEPS = ("depsdev_t2", "gcs_sync", "downloads_weekly", "downloads_parquet", "bronze_depsdev", "bronze_downloads")
TICKS = {"depsdev_t2": 3, "gcs_sync": 2, "downloads_weekly": 5, "downloads_parquet": 2,
         "bronze_depsdev": 3, "bronze_downloads": 3}


def log(msg: str) -> None:
    print(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} [fake] {msg}", flush=True)


def s3_client():
    return boto3.client("s3", endpoint_url=os.environ["PICKAGE_S3_ENDPOINT"],
                        aws_access_key_id=os.environ["PICKAGE_S3_ACCESS_KEY"],
                        aws_secret_access_key=os.environ["PICKAGE_S3_SECRET_KEY"],
                        region_name="us-east-1", config=Config(signature_version="s3v4"))


class Fake:
    def __init__(self):
        self.s3 = s3_client()
        self.work = Path(os.environ.get("FAKE_INGEST_WORK", "/host/srv/pickage/ingest-work"))
        self.tick = float(os.environ.get("FAKE_STEP_SECONDS", "8"))

    # ── 저장 ──────────────────────────────────────────────────
    def put(self, bucket: str, key: str, body=b"") -> None:
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False, indent=1).encode("utf-8")
        self.s3.put_object(Bucket=bucket, Key=key, Body=body)

    def write_local(self, rel: str, text: str, append: bool = False) -> None:
        path = self.work / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a" if append else "w", encoding="utf-8") as handle:
            handle.write(text)

    # ── 회차 문서 ──────────────────────────────────────────────
    @staticmethod
    def coverage(week: date) -> dict:
        end = week - timedelta(days=1)
        return {"depsdev_snapshot": week.isoformat(), "downloads_through": end.isoformat(),
                "downloads_window": [(end - timedelta(days=13)).isoformat(), end.isoformat()]}

    def run_doc(self, week: date, status: str, steps: list[dict], *, failures=0, last_error=None,
                started=None, finished=None, claimed=None) -> dict:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return {"week_of": week.isoformat(), "status": status, "coverage": self.coverage(week),
                "consecutive_failures": failures, "last_error": last_error,
                "manual_claimed_at": claimed, "started_at": started, "finished_at": finished,
                "updated_at": now, "steps": steps}

    def step(self, name: str, status: str, attempts: int = 1, error=None, detail=None) -> dict:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return {"step": name, "status": status, "attempt_count": attempts,
                "started_at": now if status != "PENDING" else None,
                "finished_at": now if status in ("SUCCEEDED", "FAILED") else None,
                "error_message": error, "detail": detail or {}}

    # ── 지난 회차 심기 ─────────────────────────────────────────
    def seed_history(self, this_week: date) -> None:
        for back, status in ((3, "BLOCKED"), (2, "SUCCEEDED"), (1, "SUCCEEDED")):
            week = this_week - timedelta(days=7 * back)
            tag = week.strftime("%Y%m%d")
            if status == "SUCCEEDED":
                steps = [self.step(s, "SUCCEEDED", detail={"rows": random.randint(10_000, 90_000)}) for s in STEPS]
                doc = self.run_doc(week, status, steps, started=f"{week}T01:00:00+00:00",
                                   finished=f"{week + timedelta(days=1)}T00:10:00+00:00")
                for table in ("projects", "packageversions"):
                    run = f"depsdev/v1/{table}/snapshot={week}/run_id=bronze-weekly-{tag}"
                    for i in range(3):
                        self.put(RAW, f"{run}/data/part-{i:05d}.parquet", os.urandom(1500))
                    self.put(RAW, f"{run}/run_manifest.json", {"files": 3, "week_of": week.isoformat()})
                    self.put(RAW, f"{run}/_SUCCESS")
                run = f"npm-downloads/v1/run_id=downloads-weekly-{tag}"
                for i in range(4):
                    self.put(RAW, f"{run}/data/part-{i:05d}.parquet", os.urandom(2500))
                self.put(RAW, f"{run}/_SUCCESS")
            else:
                steps = [self.step(s, "SUCCEEDED") for s in STEPS[:2]]
                steps.append(self.step("downloads_weekly", "FAILED", attempts=10,
                                       error="requests.exceptions.HTTPError: 429 Too Many Requests\n"
                                             "  npm api.npmjs.org/downloads/range — IP 한도 초과\n" * 2,
                                       detail={"tasks_by_status": {"done": 41200, "failed": 3, "pending": 58797}}))
                doc = self.run_doc(week, status, steps, failures=10,
                                   last_error="downloads_weekly 가 10회 연속 실패했다 (429)",
                                   started=f"{week}T01:00:00+00:00")
                self.put(RAW, f"_ops/weekly/{week}/manual-request.json",
                         {"requested_at": (datetime.now(timezone.utc) - timedelta(minutes=4)).isoformat(timespec="seconds")})
            self.put(RAW, f"_ops/weekly/{week}/run.json", doc)
            log(f"지난 회차 심음 {week} {status}")

        corpus = "ecosystems-keywords/v1/package-text"
        run_id = f"package-text-{(this_week - timedelta(days=13)).strftime('%Y%m%d')}-v1"
        path = f"collected_date={(this_week - timedelta(days=13))}/run_id={run_id}"
        self.put(CURATED, f"{corpus}/{path}/data/package_text.parquet", os.urandom(4000))
        self.put(CURATED, f"{corpus}/{path}/run_manifest.json", {"files": 1})
        self.put(CURATED, f"{corpus}/{path}/_SUCCESS")
        self.put(CURATED, f"{corpus}/_current.json",
                 {"collected_date": (this_week - timedelta(days=13)).isoformat(), "manifest_sha256": "f" * 8,
                  "run_id": run_id, "run_path": path})
        vec = f"model=v7/corpus={run_id}"
        self.put(VECTORS, f"{vec}/similar_package.parquet", os.urandom(3000))
        self.put(VECTORS, f"{vec}/_SUCCESS", b'{"manifest_sha256": "ff"}')
        self.put(VECTORS, "_current.json", {"run_path": vec, "run_id": run_id, "model": "v7"})
        log("포인터 심음 (코퍼스·벡터)")

    # ── 이번 회차 진행 ─────────────────────────────────────────
    def run_week(self, week: date) -> None:
        tag = week.strftime("%Y%m%d")
        started = datetime.now(timezone.utc).isoformat(timespec="seconds")
        steps = [self.step(s, "PENDING") for s in STEPS]
        root = f"downloads-weekly/{week}"
        self.write_local(f"{root}/targets.csv", "name,rank\nreact,1\nlodash,2\n")

        def flush(status="RUNNING", **kw):
            self.put(RAW, f"_ops/weekly/{week}/run.json",
                     self.run_doc(week, status, steps, started=started, **kw))

        flush()
        log(f"회차 시작 {week}")
        for index, name in enumerate(STEPS):
            steps[index] = self.step(name, "RUNNING")
            flush()
            logfile = f"{root}/logs/{name}.log"
            self.write_local(logfile, f"{datetime.now(timezone.utc):%H:%M:%S} INFO {name} 시작 week_of={week}\n")
            for t in range(TICKS[name]):
                time.sleep(self.tick)
                line = f"{datetime.now(timezone.utc):%H:%M:%S} INFO {name} 진행 {t + 1}/{TICKS[name]}"
                if name == "downloads_weekly" and t == 2:
                    line = f"{datetime.now(timezone.utc):%H:%M:%S} ERROR 429 Too Many Requests — 60초 뒤 재시도"
                elif name == "depsdev_t2" and t == 1:
                    line = f"{datetime.now(timezone.utc):%H:%M:%S} WARN 예산 8.2/26 GiB 사용"
                self.write_local(logfile, line + "\n", append=True)
                log(f"{name} {t + 1}/{TICKS[name]}")
                if name == "depsdev_t2":
                    self.put(RAW, f"depsdev/v1/projects/snapshot={week}/run_id=bronze-weekly-{tag}/data/part-{t:05d}.parquet",
                             os.urandom(1200))
                elif name == "downloads_weekly":
                    self.write_local(f"{root}/raw/run={week + timedelta(days=1)}/chunk-{t:03d}.jsonl", '{"pkg":"react"}\n')
                elif name == "downloads_parquet":
                    self.write_local(f"{root}/parquet/downloads/part-{t:03d}.parquet", "x" * 800)
                elif name == "bronze_downloads":
                    self.put(RAW, f"npm-downloads/v1/run_id=downloads-weekly-{tag}/data/part-{t:05d}.parquet",
                             os.urandom(2000))
            if name == "bronze_depsdev":
                run = f"depsdev/v1/projects/snapshot={week}/run_id=bronze-weekly-{tag}"
                self.put(RAW, f"{run}/run_manifest.json", {"files": TICKS['depsdev_t2']})
                self.put(RAW, f"{run}/_SUCCESS")
            if name == "bronze_downloads":
                self.put(RAW, f"npm-downloads/v1/run_id=downloads-weekly-{tag}/_SUCCESS")
            steps[index] = self.step(name, "SUCCEEDED", detail={"ticks": TICKS[name]})
            self.write_local(logfile, f"{datetime.now(timezone.utc):%H:%M:%S} INFO {name} 완료\n", append=True)
            flush()
        flush("SUCCEEDED", finished=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        log(f"회차 완료 {week} — {self.tick * 3:.0f}초 쉬고 다음 주차로")
        time.sleep(self.tick * 3)

    def main(self) -> None:
        today = date.today()
        this_week = today - timedelta(days=today.weekday())
        log(f"시작 week_of={this_week} tick={self.tick}s work={self.work} endpoint={os.environ['PICKAGE_S3_ENDPOINT']}")
        self.seed_history(this_week)
        week = this_week
        while True:
            self.run_week(week)
            week += timedelta(days=7)


if __name__ == "__main__":
    Fake().main()
