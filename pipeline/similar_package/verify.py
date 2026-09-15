"""적재 상태를 확인한다. DB 를 바꾸지 않는다.

    python -m pipeline.similar_package.verify status \\
      --docker-container <name> --database <db>

    python -m pipeline.similar_package.verify diff --run model=v3/corpus=<코퍼스> \\
      --docker-container <name> --database <db>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

from pipeline.similar_package.load import (
    DATASET, RESULT_BUCKET, RUN_PATTERN, list_runs, psql_command, pull_run,
    select_run, write_transport,
)

try:  # Windows 콘솔 cp949 에서 한글 출력 보장
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# 매칭 실패·잔재를 몇 건까지 예시로 보여 줄지
SAMPLE = 10

# 지금 DB 에 무엇이 실려 있는지
STATUS_SQL = f"""
\\set ON_ERROR_STOP on
SELECT json_build_object(
  'published', (SELECT json_build_object(
        'execution_id', c.execution_id, 'snapshot_at', c.snapshot_at,
        'published_at', c.published_at,
        'run_prefix', e.run_prefix, 'curated_run_id', e.curated_run_id,
        'model_ver', e.input_metadata ->> 'model_ver',
        'scoring_gate', e.input_metadata -> 'scoring_gate' ->> 'status',
        'expected', e.expected_counts, 'actual', e.actual_counts)
      FROM public.etl_dataset_current c
      JOIN public.etl_load_execution e USING (execution_id)
     WHERE c.dataset = '{DATASET}'),
  'table', (SELECT json_build_object(
        'rows', count(*), 'base_packages', count(DISTINCT package_id),
        'model_vers', array_agg(DISTINCT model_ver),
        'max_rank', max(rank), 'min_score', min(score), 'max_score', max(score))
      FROM public."similar_package"),
  'attempts', (SELECT json_agg(a ORDER BY a.created_at DESC)
      FROM (SELECT status, phase, created_at, completed_at, error_message
              FROM public.etl_load_attempt
             ORDER BY created_at DESC LIMIT 5) a)
) AS report;
"""

# 후보 파일과 DB 현재 내용을 맞춰 본다. 임시 테이블만 쓰고 커밋하지 않는다.
DIFF_HEAD = """
\\set ON_ERROR_STOP on
BEGIN;
CREATE TEMP TABLE stage_check (
    base_package TEXT NOT NULL, candidate_package TEXT NOT NULL,
    rank INT NOT NULL, score DOUBLE PRECISION NOT NULL) ON COMMIT DROP;
COPY stage_check (base_package, candidate_package, rank, score)
  FROM STDIN WITH (FORMAT text, NULL '\\N', ENCODING 'UTF8');
"""

DIFF_TAIL = """
-- 이름 → package_id 변환. 적재기와 같은 규칙으로 맞춰야 수치가 일치한다.
CREATE TEMP TABLE resolved_check ON COMMIT DROP AS
SELECT bp.package_id, cp.package_id AS similar_package_id, s.rank, s.score
  FROM stage_check s
  LEFT JOIN public."package" bp ON bp."name" = s.base_package
  LEFT JOIN public."package" cp ON cp."name" = s.candidate_package;

SELECT json_build_object(
  'file_rows', (SELECT count(*) FROM stage_check),
  'db_rows', (SELECT count(*) FROM public."similar_package"),
  'unresolved_bases', (SELECT count(DISTINCT base_package) FROM stage_check s
      WHERE NOT EXISTS (SELECT 1 FROM public."package" p WHERE p."name" = s.base_package)),
  'unresolved_candidates', (SELECT count(DISTINCT candidate_package) FROM stage_check s
      WHERE NOT EXISTS (SELECT 1 FROM public."package" p WHERE p."name" = s.candidate_package)),
  'over_rank', (SELECT count(*) FROM stage_check WHERE rank > 50),
  'self_pairs', (SELECT count(*) FROM stage_check WHERE base_package = candidate_package),
  -- 파일에 있는데 DB 에 없다 = 이 실행이 아직 적재되지 않았거나 매칭에 실패했다
  'missing_in_db', (SELECT count(*) FROM resolved_check r
      WHERE r.package_id IS NOT NULL AND r.similar_package_id IS NOT NULL
        AND NOT EXISTS (SELECT 1 FROM public."similar_package" t
                        WHERE t.package_id = r.package_id
                          AND t.similar_package_id = r.similar_package_id)),
  -- DB 에 있는데 파일에 없다 = 이전 실행의 잔재다. 전량 교체가 끝났으면 0 이어야 한다
  'stale_in_db', (SELECT count(*) FROM public."similar_package" t
      WHERE NOT EXISTS (SELECT 1 FROM resolved_check r
                        WHERE r.package_id = t.package_id
                          AND r.similar_package_id = t.similar_package_id)),
  'score_mismatch', (SELECT count(*) FROM public."similar_package" t
      JOIN resolved_check r ON r.package_id = t.package_id
                           AND r.similar_package_id = t.similar_package_id
     WHERE abs(t.score - r.score) > 1e-9)
) AS report;

SELECT 'UNRESOLVED_BASE' AS kind, s.base_package AS name FROM stage_check s
 WHERE NOT EXISTS (SELECT 1 FROM public."package" p WHERE p."name" = s.base_package)
 GROUP BY 1, 2 LIMIT {sample}
UNION ALL
SELECT 'UNRESOLVED_CANDIDATE', s.candidate_package FROM stage_check s
 WHERE NOT EXISTS (SELECT 1 FROM public."package" p WHERE p."name" = s.candidate_package)
 GROUP BY 1, 2 LIMIT {sample}
UNION ALL
SELECT 'STALE_IN_DB', p."name" FROM public."similar_package" t
  JOIN public."package" p ON p.package_id = t.package_id
 WHERE NOT EXISTS (SELECT 1 FROM resolved_check r
                   WHERE r.package_id = t.package_id
                     AND r.similar_package_id = t.similar_package_id)
 GROUP BY 1, 2 LIMIT {sample};

ROLLBACK;
"""


# 표준출력에 한 줄 남긴다.
def log(message: str) -> None:
    print(message, flush=True)


# psql 을 돌리고 표준출력을 돌려준다.
def run_psql(args, script: str) -> str:
    command = psql_command(args) + ["-v", "ON_ERROR_STOP=1", "-t", "-A", "-q", "-F", "\t"]
    completed = subprocess.run(command, input=script, capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
    if completed.returncode != 0:
        log((completed.stderr or "").strip()[-2000:])
        raise SystemExit("psql 실패")
    return completed.stdout or ""


# 출력에서 JSON 한 줄만 골라낸다.
def take_json(output: str) -> dict:
    for line in reversed(output.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    return {}


# DB 에 실려 있는 실행과 MinIO 의 최신 실행을 견주어 보여 준다.
def status(args) -> int:
    report = take_json(run_psql(args, STATUS_SQL))
    published = report.get("published")
    table = report.get("table") or {}

    log("현재 게시")
    if not published:
        log("  없음 — etl_dataset_current 에 similar-package 가 없다. 아직 한 번도 적재하지 않았다")
    else:
        log(f"  실행        {published['execution_id']}")
        log(f"  산출물 경로  {published['run_prefix']}")
        log(f"  코퍼스      {published['curated_run_id']}")
        log(f"  모델        {published['model_ver']}  게이트={published['scoring_gate']}")
        log(f"  게시 시각    {published['published_at']}")

    log("")
    log("테이블")
    if not table.get("rows"):
        log("  similar_package 가 비어 있다 — 후보 API 가 NO_DATA 를 돌려준다")
    else:
        log(f"  행 수        {table['rows']:,}   기준 패키지 {table['base_packages']:,}")
        log(f"  모델 버전    {table['model_vers']}   최대 rank {table['max_rank']}")
        log(f"  점수 범위    {table['min_score']:.4f} ~ {table['max_score']:.4f}")
        if len(table["model_vers"] or []) > 1:
            log("  경고: 모델 버전이 섞여 있다 — 전량 교체가 끝나지 않았다")

    if args.skip_remote:
        return 0

    from pipeline.minio.ingest_raw import client
    runs = list_runs(client())
    log("")
    log("MinIO 산출물")
    if not runs:
        log(f"  없음 — s3://{RESULT_BUCKET}/ 에 _SUCCESS 가 붙은 실행이 없다")
        return 0
    for run in runs[-5:]:
        mark = " *" if run == runs[-1] else "  "
        here = "  ← 게시됨" if published and published.get("run_prefix") == run else ""
        log(f"{mark} {run}{here}")
    if published and published.get("run_prefix") == runs[-1]:
        log("")
        log("최신 실행이 이미 게시돼 있다. 할 일 없음")
    else:
        log("")
        log(f"갱신 필요 — load --run {runs[-1]}")
    return 0


# 후보 파일과 DB 현재 내용을 견주어 무엇이 빠졌는지 보여 준다.
def diff(args) -> int:
    if args.run:
        if not RUN_PATTERN.fullmatch(args.run):
            raise SystemExit("--run 은 model=<버전>/corpus=<코퍼스> 형태여야 한다")
        from pipeline.minio.ingest_raw import client
        run_dir = (args.work_dir / "runs" / args.run.replace("/", "_")).resolve()
        log(f"산출물 받기: s3://{RESULT_BUCKET}/{args.run}/")
        pull_run(client(), args.run, run_dir)
    else:
        run_dir = args.run_dir.resolve()

    selected = select_run(run_dir, allow_gate_skip=True)
    work = run_dir / "verify"
    work.mkdir(exist_ok=True)
    transport = work / "candidates.copy.tsv"
    staged = write_transport(selected["candidates"], transport)
    log(f"후보 파일 {staged:,} 행  model_ver={selected['model_ver']}")

    script = work / "verify.sql"
    with script.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(DIFF_HEAD)
        with transport.open("r", encoding="utf-8") as data:
            shutil.copyfileobj(data, stream)
        stream.write("\\.\n")
        stream.write(DIFF_TAIL.format(sample=SAMPLE))

    output = run_psql(args, script.read_text(encoding="utf-8"))
    report = take_json(output)

    log("")
    log("대조")
    log(f"  파일 행 수        {report['file_rows']:,}")
    log(f"  DB 행 수          {report['db_rows']:,}")
    log(f"  DB 에 없는 후보    {report['missing_in_db']:,}"
        + ("   ← 이 실행이 아직 적재되지 않았다" if report["missing_in_db"] else ""))
    log(f"  파일에 없는 DB 행  {report['stale_in_db']:,}"
        + ("   ← 이전 실행의 잔재다" if report["stale_in_db"] else ""))
    log(f"  점수 불일치        {report['score_mismatch']:,}")
    log("")
    log("파일 자체 점검")
    log(f"  이름 못 찾은 기준   {report['unresolved_bases']:,}")
    log(f"  이름 못 찾은 후보   {report['unresolved_candidates']:,}")
    log(f"  rank > 50         {report['over_rank']:,}")
    log(f"  자기 자신 추천      {report['self_pairs']:,}")

    samples = [line.split("\t", 1) for line in output.splitlines()
               if "\t" in line and not line.strip().startswith("{")]
    if samples:
        log("")
        log(f"예시 (종류별 최대 {SAMPLE}건)")
        for kind, name in samples:
            log(f"  {kind:22} {name}")

    if report["missing_in_db"] == 0 and report["stale_in_db"] == 0 and report["file_rows"]:
        log("")
        log("이 실행이 그대로 적재돼 있다")
    return 0


# status·diff 중 하나를 실행한다.
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)

    def db_args(p):
        target = p.add_mutually_exclusive_group(required=True)
        target.add_argument("--docker-container", help="로컬 PostgreSQL 컨테이너 이름")
        target.add_argument("--psql", help="psql 실행 파일 경로")
        p.add_argument("--database", required=True)
        p.add_argument("--db-user", default="postgres")

    p = sub.add_parser("status", help="DB 에 실려 있는 실행과 MinIO 최신 실행을 견준다")
    db_args(p)
    p.add_argument("--skip-remote", action="store_true", help="MinIO 를 보지 않는다")

    p = sub.add_parser("diff", help="후보 파일과 DB 현재 내용을 견준다")
    db_args(p)
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--run", help="MinIO 의 실행 경로")
    source.add_argument("--run-dir", type=Path, help="이미 받아 둔 디렉터리")
    p.add_argument("--work-dir", type=Path,
                   default=Path(__file__).resolve().parents[2] / "data/similar_package")

    args = parser.parse_args(argv)
    return status(args) if args.action == "status" else diff(args)


if __name__ == "__main__":
    sys.exit(main())
