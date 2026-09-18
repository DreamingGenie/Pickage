"""배치 결과를 PostgreSQL similar_package 에 원자 게시한다.

산출물은 #1 data 의 MinIO 에 있다 (run-similarity-batch.sh 의 ai-collect 가 올린다).
--run 으로 실행 하나를 지정하면 받아서 적재하고, --run-dir 로 이미 받아 둔
디렉터리를 줄 수도 있다.

    python -m pipeline.similar_package.load --run model=v3/corpus=package-text-20260908-v1 \
      --execution-id <id> --docker-container <name> --database <db>
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

try:  # Windows 콘솔 cp949 에서 한글 출력 보장
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[2]
# 받은 산출물과 게시 기록(psql.log·execution_report.json)을 둘 곳. --work-dir 를 주면 그게 이긴다.
#
# ⚠ **기본값이 저장소 안이라 배포에서는 환경변수로 밖을 가리켜야 한다.** app 노드는
#   CI 러너의 작업 디렉터리를 마운트하고 그 소유자는 gitlab-runner 다 — uid 1000 인
#   컨테이너가 mkdir 에서 Permission denied 로 죽는다 (S15P21A506-385).
#
# ⚠ compose 의 `command:` 가 아니라 `environment:` 로 주는 이유:
#   `docker compose run --rm similarity-loader --once` 는 command 를 **통째로** 덮어써서
#   거기 넣은 인자가 사라진다. 그러면 상주는 멀쩡한데 손으로 한 번 돌릴 때만 깨진다.
DEFAULT_WORK_DIR = Path(os.environ.get("PICKAGE_SIMILAR_PACKAGE_WORK_DIR")
                        or ROOT / "data/similar_package")
SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,200}\Z")
DATASET = "similar-package"
# .env 의 AI_DST_RESULT 와 같은 값. ai-collect 가 여기에 올린다
RESULT_BUCKET = "pickage-vectors"
# run-similarity-batch.sh 의 OUT_RUN="model=v$MODEL_VER/corpus=$CORPUS_RUN"
RUN_PATTERN = re.compile(r"model=[A-Za-z0-9_.-]{1,40}/corpus=[A-Za-z0-9_.-]{1,64}\Z")
# ai-collect 가 /work/out 에서 그대로 올린 파일들
RUN_FILES = ("candidates.parquet", "run_manifest.json")
# curated 적재기와 다른 advisory lock 키
LOCK_KEY = 5150211                        # TODO(팀 합의): advisory lock 키 관리 규칙이 있으면 맞출 것
# CK_SIMILAR_PACKAGE_RANK — rank BETWEEN 1 AND 50
RANK_MAX = 50
# 전량 교체가 남긴 dead tuple 정리. 트랜잭션 밖이어야 하고, 실패해도 적재는 유효하다.
VACUUM = """
\\set ON_ERROR_STOP off
VACUUM (ANALYZE) public."similar_package";
"""


# 적재기 코드와 DB 마이그레이션을 하나의 해시로 묶는다.
def contract_sha256() -> str:
    digest = hashlib.sha256()
    paths = sorted(p for p in Path(__file__).parent.glob("*.py") if not p.name.startswith("test_"))
    paths += sorted((ROOT / "backend/src/main/resources/db/migration").glob("V*.sql"))
    for path in paths:
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


# 접두사 아래 객체 키를 나열한다.
def list_keys(s3, prefix: str) -> list[str]:
    keys, token = [], None
    while True:
        kwargs = {"Bucket": RESULT_BUCKET, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        page = s3.list_objects_v2(**kwargs)
        keys += [item["Key"] for item in page.get("Contents", [])]
        if not page.get("IsTruncated"):
            return keys
        token = page.get("NextContinuationToken")


# _SUCCESS 가 있는 실행을 최신순으로 나열한다.
def list_runs(s3) -> list[str]:
    runs = [key[: -len("/_SUCCESS")] for key in list_keys(s3, "model=")
            if key.endswith("/_SUCCESS")]
    # corpus 이름에 수집일이 들어가 문자열 정렬이 곧 시간 순서다 (S15P21A506-348)
    return sorted(runs, key=lambda r: r.split("corpus=")[-1])


# 지정한 실행을 로컬로 받아 run-dir 를 만든다.
def pull_run(s3, run: str, target: Path) -> Path:
    from pipeline.minio.ingest_raw import exists

    if not exists(s3, RESULT_BUCKET, f"{run}/_SUCCESS"):
        raise SystemExit(f"완료 마커가 없다: s3://{RESULT_BUCKET}/{run}/_SUCCESS\n"
                         "배치가 끝나지 않았거나 채점 게이트를 통과하지 못한 실행이다")
    target.mkdir(parents=True, exist_ok=True)
    for name in RUN_FILES:
        key = f"{run}/{name}"
        if not exists(s3, RESULT_BUCKET, key):
            raise SystemExit(f"필수 객체가 없다: s3://{RESULT_BUCKET}/{key}")
        path = target / name
        temporary = path.with_suffix(path.suffix + ".part")
        s3.download_file(RESULT_BUCKET, key, str(temporary))
        temporary.replace(path)  # 중간에 끊긴 파일을 완성본으로 오인하지 않게 한다
        print(f"  ↓ {name}  ({path.stat().st_size / 1e6:.1f} MB)", flush=True)
    (target / "_SUCCESS").write_bytes(b"")
    return target


# 배치 산출물이 게시해도 되는 상태인지 확인하고 manifest 를 돌려준다.
def select_run(run_dir: Path, allow_gate_skip: bool) -> dict:
    marker = run_dir / "_SUCCESS"
    manifest_path = run_dir / "run_manifest.json"
    candidates = run_dir / "candidates.parquet"
    for path in (marker, manifest_path, candidates):
        if not path.exists():
            raise SystemExit(f"필수 파일이 없다: {path}")

    body = manifest_path.read_bytes()
    manifest = json.loads(body)
    gate = manifest.get("scoring_gate") or {}
    status = gate.get("status")
    if status == "PASSED":
        pass
    elif status == "SKIPPED":
        if not allow_gate_skip:
            raise SystemExit(
                "채점 게이트가 SKIPPED 다. 검증되지 않은 결과를 게시하려면 --allow-gate-skip 을 명시할 것"
            )
    else:
        raise SystemExit(f"채점 게이트가 {status} 다 — 게시하지 않는다")

    model_ver = manifest.get("model_ver")
    if not isinstance(model_ver, str) or not model_ver:
        raise SystemExit("manifest 에 model_ver 이 없다")
    if model_ver == "unknown":
        print("경고: model_ver 이 unknown 이다 — 모델 run_manifest.json 확인", flush=True)

    # etl_load_execution 이 snapshot_at 을 NOT NULL 로 요구해 없으면 실행 시각을 쓴다.
    created = manifest.get("created_at")
    if not isinstance(created, str) or len(created) < 10:
        created = dt.datetime.now().isoformat(timespec="seconds")
        print(f"manifest 에 created_at 이 없어 실행 시각을 쓴다: {created}", flush=True)

    expected_rows = manifest.get("candidate_rows")
    return {
        "manifest": manifest,
        "manifest_sha256": hashlib.sha256(body).hexdigest(),
        "model_ver": model_ver,
        "created_at": created,
        "snapshot_at": created[:10],
        "expected_rows": expected_rows if isinstance(expected_rows, int) else None,
        "candidates": candidates,
    }


_ESCAPE = str.maketrans({"\\": "\\\\", "\t": "\\t", "\n": "\\n", "\r": "\\r"})


# candidates.parquet 을 COPY 용 TSV 로 옮기고 행 수를 돌려준다.
def write_transport(candidates: Path, target: Path) -> int:
    import pyarrow.parquet as pq

    rows = 0
    with target.open("w", encoding="utf-8", newline="\n") as stream:
        for batch in pq.ParquetFile(candidates).iter_batches(
            batch_size=50_000,
            columns=["base_package", "candidate_package", "rank", "final_score"],
        ):
            for base, candidate, rank, score in zip(
                batch.column("base_package").to_pylist(),
                batch.column("candidate_package").to_pylist(),
                batch.column("rank").to_pylist(),
                batch.column("final_score").to_pylist(),
            ):
                if base is None or candidate is None or rank is None or score is None:
                    raise SystemExit("candidates.parquet 에 NULL 이 있다 — 배치 출력 확인")
                stream.write(
                    f"{str(base).translate(_ESCAPE)}\t{str(candidate).translate(_ESCAPE)}"
                    f"\t{int(rank)}\t{float(score)!r}\n"
                )
                rows += 1
    if rows == 0:
        raise SystemExit("candidates.parquet 이 비어 있다")
    return rows


# psql 스크립트를 TSV 삽입 지점 앞뒤로 나눠 돌려준다. 스크립트는 psql 표준입력으로 넣는다.
def build_sql(verify_only: bool) -> tuple[str, str]:
    head = f"""
\\set ON_ERROR_STOP on
BEGIN;

-- 동시 적재 차단 (트랜잭션 종료 시 자동 해제)
SELECT pg_advisory_xact_lock({LOCK_KEY});

CREATE TEMP TABLE stage_similar (
    base_package      text             NOT NULL,
    candidate_package text             NOT NULL,
    rank              integer          NOT NULL CHECK (rank >= 1),
    score             double precision NOT NULL
) ON COMMIT DROP;

COPY stage_similar (base_package, candidate_package, rank, score) FROM STDIN WITH (FORMAT text, NULL '\\N', ENCODING 'UTF8');
"""
    tail = f"""

-- 이름 → package_id 변환. 매칭 실패분을 버리고 순위를 1부터 다시 매긴다.
CREATE TEMP TABLE resolved ON COMMIT DROP AS
SELECT package_id, similar_package_id, score,
       row_number() OVER (PARTITION BY package_id ORDER BY source_rank)::int AS rank
  FROM (SELECT DISTINCT ON (bp.package_id, cp.package_id)
               bp.package_id                AS package_id,
               cp.package_id                AS similar_package_id,
               s.score                      AS score,
               s.rank                       AS source_rank
          FROM stage_similar s
          JOIN "package" bp ON bp."name" = s.base_package
          JOIN "package" cp ON cp."name" = s.candidate_package
         WHERE bp.package_id <> cp.package_id      -- CK_SIMILAR_PACKAGE_SELF
         ORDER BY bp.package_id, cp.package_id, s.rank) d;

DELETE FROM resolved WHERE rank > {RANK_MAX};      -- CK_SIMILAR_PACKAGE_RANK

CREATE TEMP TABLE quality ON COMMIT DROP AS
SELECT (SELECT count(*)                    FROM stage_similar)          AS staged_rows,
       (SELECT count(DISTINCT base_package) FROM stage_similar)         AS staged_bases,
       (SELECT count(*)                    FROM resolved)               AS loaded_rows,
       (SELECT count(DISTINCT package_id)  FROM resolved)               AS loaded_bases,
       (SELECT count(DISTINCT s.base_package) FROM stage_similar s
          LEFT JOIN "package" p ON p."name" = s.base_package
         WHERE p.package_id IS NULL)                                    AS unresolved_bases,
       (SELECT count(DISTINCT s.candidate_package) FROM stage_similar s
          LEFT JOIN "package" p ON p."name" = s.candidate_package
         WHERE p.package_id IS NULL)                                    AS unresolved_candidates;

-- 한 건도 못 붙으면 중단
DO $$ BEGIN
  IF (SELECT loaded_rows FROM quality) = 0 THEN
    RAISE EXCEPTION 'package 테이블과 이름이 하나도 맞지 않는다 — 입력 코퍼스를 확인할 것';
  END IF;
END $$;

-- 실행 이력 등록
INSERT INTO public.etl_load_execution
    (execution_id, dataset, status, snapshot_at, snapshot_timestamp, curated_run_id, run_prefix,
     manifest_sha256, contract_sha256, input_metadata, expected_counts, active_attempt_id)
VALUES (:'execution_id', '{DATASET}', 'PREPARING', :'snapshot_at', :'snapshot_timestamp',
        :'curated_run_id', :'run_prefix', :'manifest_sha256', :'contract_sha256',
        :'manifest'::jsonb, :'expected_counts'::jsonb, :'attempt_id')
ON CONFLICT (execution_id) DO UPDATE
   SET status='PREPARING', active_attempt_id=EXCLUDED.active_attempt_id,
       manifest_sha256=EXCLUDED.manifest_sha256, contract_sha256=EXCLUDED.contract_sha256,
       input_metadata=EXCLUDED.input_metadata, expected_counts=EXCLUDED.expected_counts,
       error_message=NULL, updated_at=clock_timestamp();

INSERT INTO public.etl_load_attempt
    (attempt_id, execution_id, status, phase, validation_contract_sha256)
VALUES (:'attempt_id', :'execution_id', 'PREPARING', 'VALIDATE_INPUT', :'contract_sha256');

-- 전량 교체
LOCK TABLE public."similar_package", public.etl_dataset_current IN SHARE ROW EXCLUSIVE MODE;
DELETE FROM public."similar_package";
INSERT INTO public."similar_package" (package_id, similar_package_id, "rank", score, model_ver)
SELECT package_id, similar_package_id, rank, score, :'model_ver' FROM resolved;

UPDATE public.etl_load_attempt
   SET status='PUBLISHED', phase='COMMIT', completed_at=clock_timestamp(),
       actual_counts=jsonb_build_object('similar_package', (SELECT loaded_rows FROM quality)),
       quality_report=(SELECT to_jsonb(q) FROM quality q)
 WHERE attempt_id=:'attempt_id';

UPDATE public.etl_load_execution
   SET status='PUBLISHED', updated_at=clock_timestamp(), error_message=NULL,
       actual_counts=jsonb_build_object('similar_package', (SELECT loaded_rows FROM quality))
 WHERE execution_id=:'execution_id' AND active_attempt_id=:'attempt_id';

-- 현재 게시된 실행을 가리키는 포인터 갱신
INSERT INTO public.etl_dataset_current (dataset, execution_id, snapshot_at, manifest_sha256, manifest)
VALUES ('{DATASET}', :'execution_id', :'snapshot_at', :'manifest_sha256', :'manifest'::jsonb)
ON CONFLICT (dataset) DO UPDATE
   SET execution_id=EXCLUDED.execution_id, snapshot_at=EXCLUDED.snapshot_at,
       manifest_sha256=EXCLUDED.manifest_sha256, manifest=EXCLUDED.manifest,
       published_at=clock_timestamp();

SELECT to_jsonb(q) FROM quality q;

{"ROLLBACK;" if verify_only else "COMMIT;"}
{VACUUM if not verify_only else ""}"""
    return head, tail


# psql 실행 명령을 조립한다.
def psql_command(args) -> list[str]:
    if not SAFE_ID.fullmatch(args.database) or not SAFE_ID.fullmatch(args.db_user):
        raise SystemExit("database·user 는 단순 이름만 쓴다. 인증은 libpq 환경변수로 준다")
    if args.docker_container:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", args.docker_container):
            raise SystemExit("컨테이너 이름이 올바르지 않다")
        command = ["docker", "exec", "-i", args.docker_container, "psql"]
    else:
        command = [args.psql]
    return command + ["-U", args.db_user, "-d", args.database]


# 산출물 확인 → TSV 변환 → psql 실행 → 유실 통계 출력.
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--run", help="MinIO 의 실행 경로 (model=v3/corpus=package-text-20260908-v1)")
    source.add_argument("--run-dir", type=Path, help="이미 받아 둔 디렉터리")
    source.add_argument("--list", action="store_true", help="적재할 수 있는 실행을 나열하고 끝낸다")
    parser.add_argument("--execution-id", help="이 게시의 식별자. 재실행 시 같은 값을 준다. "
                                               "--run 이면 생략 시 실행 경로에서 만든다")
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_DIR)
    parser.add_argument("--allow-gate-skip", action="store_true",
                        help="채점 게이트가 SKIPPED 여도 게시한다 (게이트 미구현 기간용)")
    parser.add_argument("--verify-only", action="store_true",
                        help="게시 직전까지 전부 실행한 뒤 ROLLBACK. DB 는 그대로 둔다")
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--docker-container", help="로컬 PostgreSQL 컨테이너 이름")
    target.add_argument("--psql", help="psql 실행 파일 경로")
    parser.add_argument("--database")
    parser.add_argument("--db-user", default="postgres")
    args = parser.parse_args(argv)

    if args.list:
        from pipeline.minio.ingest_raw import client
        runs = list_runs(client())
        if not runs:
            print("적재할 수 있는 실행이 없다 (_SUCCESS 가 붙은 산출물 없음)", flush=True)
            return 1
        for run in runs:
            print(("* " if run == runs[-1] else "  ") + run, flush=True)
        return 0

    if not args.database or not (args.docker_container or args.psql):
        raise SystemExit("--database 와 --docker-container/--psql 이 필요하다")

    attempt_id = uuid.uuid4().hex
    if args.run:
        if not RUN_PATTERN.fullmatch(args.run):
            raise SystemExit("--run 은 model=<버전>/corpus=<코퍼스> 형태여야 한다")
        curated_run_id = args.run.split("corpus=")[-1]
        execution_id = args.execution_id or f"{DATASET}-{args.run.replace('/', '-').replace('=', '')}"
    else:
        run_dir = args.run_dir.resolve()
        curated_run_id = run_dir.name
        execution_id = args.execution_id or f"{DATASET}-{curated_run_id}"
    if not SAFE_ID.fullmatch(execution_id):
        raise SystemExit("execution-id 는 영문·숫자·밑줄·하이픈 1~200자")
    args.execution_id = execution_id

    if args.run:
        from pipeline.minio.ingest_raw import client
        run_dir = (args.work_dir / "runs" / args.run.replace("/", "_")).resolve()
        print(f"산출물 받기: s3://{RESULT_BUCKET}/{args.run}/", flush=True)
        pull_run(client(), args.run, run_dir)

    selected = select_run(run_dir, args.allow_gate_skip)
    selected["curated_run_id"] = curated_run_id
    work = (args.work_dir / args.execution_id / attempt_id).resolve()
    work.mkdir(parents=True, exist_ok=False)

    transport = work / "candidates.copy.tsv"
    staged = write_transport(selected["candidates"], transport)
    print(f"전송 파일 준비: {staged} 행 ({transport})", flush=True)

    # manifest 의 candidate_rows 와 실제 행 수 대조
    if selected["expected_rows"] is not None and selected["expected_rows"] != staged:
        raise SystemExit(f"manifest 의 candidate_rows 와 실제 행 수가 다르다: "
                         f"{selected['expected_rows']} vs {staged}")

    # psql 은 docker exec 로 컨테이너 안에서 돌 수 있다. 그쪽에서는 호스트 경로를 못 보므로
    # 스크립트와 COPY 데이터를 모두 표준입력으로 흘려보낸다.
    head, tail = build_sql(args.verify_only)
    script = work / "publish.sql"
    with script.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(head)
        with transport.open("r", encoding="utf-8") as data:
            shutil.copyfileobj(data, stream)
        stream.write("\\.\n")
        stream.write(tail)

    command = psql_command(args) + [
        "-v", "ON_ERROR_STOP=1", "-t", "-A", "-q",
        "-v", f"execution_id={args.execution_id}",
        "-v", f"attempt_id={attempt_id}",
        "-v", f"model_ver={selected['model_ver']}",
        "-v", f"snapshot_at={selected['snapshot_at']}",
        "-v", f"snapshot_timestamp={selected['created_at']}",
        "-v", f"curated_run_id={selected['curated_run_id']}",
        "-v", f"run_prefix={args.run or run_dir.as_posix()}",
        "-v", f"manifest_sha256={selected['manifest_sha256']}",
        "-v", f"contract_sha256={contract_sha256()}",
        "-v", "manifest=" + json.dumps(selected["manifest"], ensure_ascii=False),
        "-v", "expected_counts=" + json.dumps({"similar_package": staged}),
    ]
    with script.open("rb") as stream:
        completed = subprocess.run(command, stdin=stream, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace")
    log = work / "psql.log"
    log.write_text((completed.stdout or "") + "\n---- stderr ----\n" + (completed.stderr or ""),
                   encoding="utf-8")
    if completed.returncode != 0:
        print(f"게시 실패 — {log}", flush=True)
        print((completed.stderr or "").strip()[-2000:], flush=True)
        return 1

    lines = [line for line in (completed.stdout or "").splitlines() if line.strip().startswith("{")]
    quality = json.loads(lines[-1]) if lines else {}
    report = {"execution_id": args.execution_id, "attempt_id": attempt_id,
              "mode": "VERIFY_ONLY" if args.verify_only else "PUBLISH",
              "model_ver": selected["model_ver"],
              "scoring_gate": selected["manifest"].get("scoring_gate"),
              "quality": quality}
    (work / "execution_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(quality, ensure_ascii=False, indent=2), flush=True)
    if quality:
        lost = quality["staged_rows"] - quality["loaded_rows"]
        if lost:
            print(f"경고: {lost} 행이 이름 매칭에 실패해 빠졌다 "
                  f"(base {quality['unresolved_bases']} · candidate {quality['unresolved_candidates']})",
                  flush=True)
    print(("검증만 하고 되돌렸다" if args.verify_only else "게시 완료") + f" — {work}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
