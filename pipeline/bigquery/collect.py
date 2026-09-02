#!/usr/bin/env python
"""deps.dev BigQuery → GCS Parquet 수집기 (OSS Shift).

한 번에 성공해야 하는 수집이라 모든 잡이 아래 관문을 순서대로 통과해야 실행된다.
  1. 멱등성   : GCS에 _MANIFEST.json 이 있으면 건너뜀 (--force 로 재수집)
  2. dry-run  : 스캔 바이트를 먼저 재고, 테이블별 하드캡 초과 → 전체 중단
  3. 기대치   : 최신 스냅샷은 실측 기대치와 25% 이상 어긋나면 중단 (--allow-deviation 으로 해제)
  4. 세션 예산: 이번 실행의 누적 dry-run 바이트가 --budget-gib 을 넘기면 그 앞에서 정지
  5. 실행 상한: maximum_bytes_billed = dry-run × 1.25 + 512 MiB. 일반 SELECT → 스테이징 테이블(staging 데이터셋,
               3일 자동 만료) → extract 잡으로 GCS Parquet(무과금) → 스테이징 삭제
  6. 검증     : 스테이징 테이블 행 수를 INFORMATION_SCHEMA.PARTITIONS 행 수와 대조, 매니페스트·원장 기록

사용법은 pipeline/bigquery/README.md. 계획서는 docs/api & data/수집계획_BigQuery_Parquet_v2_260902.md.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import sys
import time

from google.api_core import exceptions as gexc
from google.cloud import bigquery, storage

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

PROJECT = "oss-shift-a506"
BUCKET = "oss-shift-a506-raw"
DATASET = "bigquery-public-data.deps_dev_v1"
STAGING = "staging"  # oss-shift-a506.staging (US, 기본 테이블 만료 3일)
HERE = pathlib.Path(__file__).resolve().parent
SQL_DIR = HERE / "sql"
LEDGER = HERE / "ledger" / "ledger.jsonl"
GiB = 2**30
MiB = 2**20

# 테이블 → (SQL 템플릿, 하드캡 GiB, 최신 스냅샷 기대치 GiB[2026-08-31 dry-run 실측], 원천 테이블명)
TABLES = {
    "versions_full": ("versions_full.sql", 30.0, 24.51, "PackageVersions"),
    "versions_min": ("versions_min.sql", 8.0, 5.24, "PackageVersions"),
    "requirements": ("requirements.sql", 22.0, 17.51, "NPMRequirements"),
    "pkg_project": ("pkg_project.sql", 14.0, 10.37, "PackageVersionToProject"),
    "projects": ("projects.sql", 1.0, 0.32, "Projects"),
}

# 계층 → (테이블 순서, 기본 세션 예산 GiB, GCS 루트)
TIERS = {
    "rehearsal": (["versions_full", "requirements", "pkg_project", "projects"], 3.0, "_rehearsal"),
    "t0": (["versions_full", "requirements", "pkg_project", "projects"], 60.0, "raw"),
    "t1": (["projects"], 60.0, "raw"),  # 228 파티션 dry-run 합계 약 51 GiB (2026-09-02 실측)
    "t2": (["requirements", "versions_min", "projects"], 26.0, "raw"),
    "t2m": (["versions_full", "pkg_project"], 40.0, "raw"),
}
# 리허설: 클러스터 키로 프루닝되는 필터 → 4건 합계 약 1.3 GiB
REHEARSAL_FILTER = {"projects": " AND Name = 'expressjs/express'", "_default": " AND Name = 'express'"}

DEVIATION_LIMIT = 0.25


def log(msg: str) -> None:
    print(f"[{dt.datetime.now():%H:%M:%S}] {msg}", flush=True)


def gib(b: int | float) -> str:
    return f"{b / GiB:.3f} GiB"


class Collector:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.bq = bigquery.Client(project=PROJECT)
        self.gcs = storage.Client(project=PROJECT)
        self.bucket = self.gcs.bucket(BUCKET)
        self.tables, self.budget_gib, self.root = TIERS[args.tier]
        if args.budget_gib is not None:
            self.budget_gib = args.budget_gib
        self.cum_dry = 0
        self.cum_billed = 0
        self.rows_meta: dict[tuple[str, str], int] = {}
        self.results: list[dict] = []

    # ---------- 메타데이터 (각 10 MB 최소 과금) ----------
    def latest_snapshot(self) -> str:
        q = f"SELECT FORMAT_DATE('%Y-%m-%d', MAX(DATE(Time))) AS d FROM `{DATASET}.Snapshots`"
        return next(iter(self.bq.query(q).result())).d

    def load_partition_rows(self) -> None:
        src = ",".join(f"'{TABLES[t][3]}'" for t in self.tables)
        q = (
            "SELECT table_name, partition_id, total_rows FROM "
            f"`{DATASET}.INFORMATION_SCHEMA.PARTITIONS` WHERE table_name IN ({src})"
        )
        for r in self.bq.query(q).result():
            if r.partition_id and r.partition_id[:8].isdigit():
                d = f"{r.partition_id[:4]}-{r.partition_id[4:6]}-{r.partition_id[6:8]}"
                self.rows_meta[(r.table_name, d)] = int(r.total_rows)

    def t1_snapshots(self) -> list[str]:
        dates = sorted(d for (t, d) in self.rows_meta if t == "Projects")
        if self.args.since:
            dates = [d for d in dates if d >= self.args.since]
        if self.args.until:
            dates = [d for d in dates if d <= self.args.until]
        return dates

    # ---------- GCS ----------
    def prefix(self, table: str, snap: str) -> str:
        return f"{self.root}/{table}/snapshot={snap}/"

    def manifest_blob(self, table: str, snap: str) -> storage.Blob:
        return self.bucket.blob(self.prefix(table, snap) + "_MANIFEST.json")

    def list_parts(self, table: str, snap: str) -> tuple[int, int]:
        n = size = 0
        for b in self.gcs.list_blobs(BUCKET, prefix=self.prefix(table, snap) + "part-"):
            n += 1
            size += b.size or 0
        return n, size

    # ---------- 한 잡 ----------
    def build_sql(self, table: str, snap: str) -> str:
        """일반 SELECT 문. EXPORT DATA 문장은 쓰지 않는다.

        EXPORT DATA … AS SELECT 는 dry-run 추정치가 클러스터 프루닝을 반영하지 않고(PackageVersions 24.4 → 43.0 GiB),
        maximum_bytes_billed 검사가 그 추정치로 이뤄져 상한을 정확히 걸 수 없다(2026-09-02 리허설에서 거부 확인).
        일반 SELECT → 스테이징 테이블은 추정·상한·과금 모두 프루닝을 반영하고, 행 수도 테이블 메타에서 정확히 나온다.
        """
        tmpl = (SQL_DIR / TABLES[table][0]).read_text(encoding="utf-8")
        extra = ""
        if self.args.tier == "rehearsal":
            extra = REHEARSAL_FILTER.get(table, REHEARSAL_FILTER["_default"])
        return tmpl.format(snap=snap, extra=extra).strip()

    def expected_rows(self, table: str, snap: str) -> tuple[int | None, str]:
        """(기대 행수, 검증 방식). exact = 파티션 행수와 일치해야 함, near = 1% 이내, bound = 0 < n <= 파티션"""
        src = TABLES[table][3]
        part = self.rows_meta.get((src, snap))
        if self.args.tier == "rehearsal":
            return None, "none"
        if table in ("requirements", "projects"):
            return part, "exact"
        if table.startswith("versions"):
            # npm 버전 수 = NPMRequirements 파티션 행수 (2026-08-31 실측: 둘 다 78,559,731)
            return self.rows_meta.get(("NPMRequirements", snap)), "near"
        return part, "bound"

    def run_one(self, table: str, snap: str, is_latest: bool) -> dict:
        rec = {"tier": self.args.tier, "table": table, "snapshot": snap, "status": "pending",
               "started_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
        mblob = self.manifest_blob(table, snap)
        if mblob.exists() and not self.args.force:
            rec["status"] = "skipped_manifest_exists"
            log(f"  ↷ {table} {snap}: 매니페스트 있음, 건너뜀")
            return rec

        sql = self.build_sql(table, snap)
        rec["sql_sha"] = hashlib.sha1(sql.encode()).hexdigest()[:12]

        # 관문 2: dry-run (일반 SELECT — 클러스터 프루닝 반영)
        dry_cfg = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
        dry_bytes = int(self.bq.query(sql, job_config=dry_cfg).total_bytes_processed or 0)
        rec["dry_bytes"] = dry_bytes
        _, cap, expected, _ = TABLES[table]
        if dry_bytes > cap * GiB:
            rec["status"] = "abort_cap"
            raise SystemExit(f"중단: {table} {snap} dry-run {gib(dry_bytes)} > 하드캡 {cap} GiB. 쿼리·파티션 필터를 확인하라.")
        # 관문 3: 기대치 (최신 스냅샷·정규 계층만)
        if is_latest and self.args.tier != "rehearsal" and expected:
            dev = abs(dry_bytes / GiB - expected) / expected
            rec["deviation"] = round(dev, 3)
            if dev > DEVIATION_LIMIT and not self.args.allow_deviation:
                rec["status"] = "abort_deviation"
                raise SystemExit(f"중단: {table} {snap} dry-run {gib(dry_bytes)}, 기대 {expected} GiB (편차 {dev:.0%}). "
                                 f"의도된 변경이면 --allow-deviation.")
        # 관문 4: 세션 예산
        if self.cum_dry + dry_bytes > self.budget_gib * GiB:
            rec["status"] = "stopped_budget"
            log(f"  ■ {table} {snap}: 누적 {gib(self.cum_dry)} + {gib(dry_bytes)} > 예산 {self.budget_gib} GiB. 정지.")
            return rec
        self.cum_dry += dry_bytes
        log(f"  · {table} {snap}: dry-run {gib(dry_bytes)}  (누적 {gib(self.cum_dry)} / {self.budget_gib} GiB)")

        if self.args.plan:
            rec["status"] = "planned"
            return rec

        # 관문 5: 실행 상한 — 일반 SELECT → 스테이징 테이블 (추정·상한 모두 클러스터 프루닝 반영)
        max_billed = int(dry_bytes * 1.25) + 512 * MiB
        dest = f"{PROJECT}.{STAGING}.{self.root.strip('_')}__{table}__{snap.replace('-', '')}"
        cfg = bigquery.QueryJobConfig(
            destination=dest, write_disposition="WRITE_TRUNCATE",
            maximum_bytes_billed=max_billed, use_query_cache=False,
            labels={"app": "oss-shift", "tier": self.args.tier, "table": table, "snap": snap.replace("-", "")},
        )
        if self.args.force and mblob.exists():
            mblob.delete()
        t0 = time.time()
        # 이어하기: 쿼리는 끝났는데 extract 전에 끊긴 경우 스테이징 테이블이 남아 있다 → 재쿼리(재과금) 없이 재사용
        stg = None
        if not self.args.force:
            try:
                stg = self.bq.get_table(dest)
                log(f"  ↻ {table} {snap}: 스테이징 테이블 재사용 ({int(stg.num_rows or 0):,}행, 재쿼리 없음)")
                rec["job_id"] = "reused_staging"
                rec["billed_bytes"] = 0
            except gexc.NotFound:
                stg = None
        if stg is None:
            job = None
            for attempt in (1, 2):
                try:
                    job = self.bq.query(sql, job_config=cfg)
                    job.result()
                    break
                except (gexc.ServiceUnavailable, gexc.InternalServerError, gexc.DeadlineExceeded) as e:
                    log(f"  ! 일시 오류(시도 {attempt}): {e}. 실패 쿼리는 과금되지 않음. 30초 후 재시도")
                    if attempt == 2:
                        raise
                    time.sleep(30)
            assert job is not None
            rec["job_id"] = job.job_id
            rec["billed_bytes"] = int(job.total_bytes_billed or 0)
            stg = self.bq.get_table(dest)
        rec["query_s"] = round(time.time() - t0, 1)
        self.cum_billed += rec["billed_bytes"]
        rec["rows"] = int(stg.num_rows or 0)
        rec["staging_bytes"] = int(stg.num_bytes or 0)

        # 반출: 스테이징 테이블 → GCS Parquet (extract 잡은 무과금)
        t1 = time.time()
        for b in self.gcs.list_blobs(BUCKET, prefix=self.prefix(table, snap) + "part-"):
            b.delete()  # overwrite 의미 유지
        uri = f"gs://{BUCKET}/{self.prefix(table, snap)}part-*.parquet"
        xcfg = bigquery.ExtractJobConfig(destination_format="PARQUET")
        xcfg.compression = "SNAPPY"
        xjob = self.bq.extract_table(dest, uri, job_config=xcfg)
        xjob.result()
        rec["extract_job_id"] = xjob.job_id
        rec["extract_s"] = round(time.time() - t1, 1)
        rec["elapsed_s"] = round(time.time() - t0, 1)
        if not self.args.keep_staging:
            self.bq.delete_table(dest, not_found_ok=True)

        # 관문 6: 검증
        exp, mode = self.expected_rows(table, snap)
        rec["expected_rows"], rec["verify_mode"] = exp, mode
        ok = True
        if mode == "exact":
            ok = exp is not None and rec["rows"] == exp
        elif mode == "near":
            ok = exp is not None and exp > 0 and abs(rec["rows"] - exp) / exp <= 0.01
        elif mode == "bound":
            ok = rec["rows"] > 0 and (exp is None or rec["rows"] <= exp)
        else:
            ok = rec["rows"] > 0
        rec["verify"] = "ok" if ok else "MISMATCH"
        n_files, gcs_bytes = self.list_parts(table, snap)
        rec["gcs_files"], rec["gcs_bytes"] = n_files, gcs_bytes
        rec["status"] = "done" if ok else "done_verify_failed"
        rec["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        mblob.upload_from_string(json.dumps(rec, ensure_ascii=False, indent=2), content_type="application/json")
        log(f"  ✓ {table} {snap}: billed {gib(rec['billed_bytes'])} · rows {rec['rows']:,} "
            f"(기대 {exp:,} {mode})" if exp else f"  ✓ {table} {snap}: billed {gib(rec['billed_bytes'])} · rows {rec['rows']:,}")
        log(f"    files {n_files} · {gcs_bytes / MiB:,.0f} MiB · {rec['elapsed_s']}s · verify={rec['verify']} · job {job.job_id}")
        if not ok and not self.args.continue_on_mismatch:
            raise SystemExit(f"중단: {table} {snap} 행 수 검증 실패 (rows {rec['rows']:,}, 기대 {exp}). 매니페스트는 기록됨.")
        return rec

    # ---------- 전체 ----------
    def run(self) -> None:
        log(f"tier={self.args.tier} root=gs://{BUCKET}/{self.root} budget={self.budget_gib} GiB "
            f"mode={'PLAN(dry-run만)' if self.args.plan else 'EXECUTE'}")
        self.load_partition_rows()
        latest = self.latest_snapshot()
        if self.args.tier == "t1":
            snaps = self.t1_snapshots()
            if not self.args.include_latest:
                snaps = [s for s in snaps if s != latest]  # 최신은 T0에서 이미 받음
            plan = [("projects", s) for s in snaps]
        else:
            snap = self.args.snap or latest
            if (TABLES[self.tables[0]][3], snap) not in self.rows_meta:
                raise SystemExit(f"중단: {snap} 파티션이 {TABLES[self.tables[0]][3]}에 없다. 스냅샷 날짜를 확인하라. 최신={latest}")
            plan = [(t, snap) for t in self.tables]
        log(f"최신 스냅샷 {latest} · 잡 {len(plan)}개")
        try:
            for table, snap in plan:
                rec = self.run_one(table, snap, is_latest=(snap == latest))
                self.results.append(rec)
                if rec["status"] == "stopped_budget":
                    break
        finally:
            self.flush_ledger()
            self.summary()

    def flush_ledger(self) -> None:
        if self.args.plan:
            return  # 계획 모드는 원장에 남기지 않는다
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER.open("a", encoding="utf-8") as f:
            for r in self.results:
                if r["status"] not in ("planned", "skipped_manifest_exists"):
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")

    def summary(self) -> None:
        done = [r for r in self.results if r["status"].startswith("done")]
        log("── 요약 ──")
        log(f"잡 {len(self.results)}개 · 실행 {len(done)}개 · dry-run 누적 {gib(self.cum_dry)} · 과금 누적 {gib(self.cum_billed)}")
        bad = [r for r in self.results if r["status"] in ("done_verify_failed", "stopped_budget")]
        for r in bad:
            log(f"  ⚠ {r['table']} {r['snapshot']}: {r['status']}")
        if self.args.plan:
            log("PLAN 모드: 아무것도 실행하지 않았다. 위 dry-run 합계가 이번 실행의 과금 상한 근사치다.")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tier", required=True, choices=list(TIERS))
    p.add_argument("--snap", help="YYYY-MM-DD. 생략 시 Snapshots 최신. (t1은 무시)")
    p.add_argument("--plan", action="store_true", help="dry-run만 하고 실행하지 않음")
    p.add_argument("--budget-gib", type=float, help="이번 실행의 누적 dry-run 상한 (기본: 계층별)")
    p.add_argument("--force", action="store_true", help="매니페스트가 있어도 다시 수집")
    p.add_argument("--allow-deviation", action="store_true", help="기대치 편차 25%% 초과 허용")
    p.add_argument("--continue-on-mismatch", action="store_true", help="행 수 검증 실패해도 계속")
    p.add_argument("--since", help="t1: 이 날짜 이후 스냅샷만 (YYYY-MM-DD)")
    p.add_argument("--until", help="t1: 이 날짜 이전 스냅샷만")
    p.add_argument("--include-latest", action="store_true", help="t1: 최신 스냅샷도 포함")
    p.add_argument("--keep-staging", action="store_true", help="스테이징 테이블을 삭제하지 않음 (3일 후 자동 만료)")
    args = p.parse_args()
    Collector(args).run()


if __name__ == "__main__":
    main()
