"""유사 패키지 배치 결과를 PostgreSQL `similar_package` 에 원자 게시한다 (방식 C 의 LOAD).

    python -m pipeline.similar_package.load \
      --run-dir data/similarity/2026-09-15 \
      --execution-id similar-package-20260915 \
      --docker-container pickage-postgres --database pickage

`ai/similarity` 배치는 PostgreSQL 을 건드리지 않는다 (컨테이너에 PG 드라이버가 없다).
그 배치가 로컬 디렉터리에 낸 산출물을 읽어 DB 에 올리는 것이 이 모듈의 역할이다.

입력 (배치의 `--out` 디렉터리):

    candidates.parquet    base_package · candidate_package · rank · final_score · cos_score
    run_manifest.json     model_ver · candidate_rows · scoring_gate
    _SUCCESS              채점 게이트를 통과했을 때만 생긴다

게시 규칙은 `pipeline/postgresql/` 의 curated 적재기를 따른다 — psql 프로세스 하나,
Python DB 드라이버 없음, 임시 테이블에 COPY 한 뒤 한 트랜잭션에서 본 테이블 교체,
`etl_load_execution` · `etl_load_attempt` · `etl_dataset_current` 에 실행 이력 기록.

curated 와 다른 점 두 가지.

1. **전량 교체다.** `ON CONFLICT DO UPDATE` 로 누적하지 않는다. 지난 실행의 후보가 남으면
   `UK_SIMILAR_PACKAGE_RANK` 와 충돌하고, 남더라도 이번 모델이 내리지 않은 후보가 섞인다.
2. **이름을 package_id 로 바꾼다.** 배치는 패키지를 이름으로 내고 테이블은 번호로 받는다.
   `package` 에 없는 이름은 버리는데, 후보만 버려지면 순위에 구멍이 생기므로 **버린 뒤
   순위를 1부터 다시 매긴다.** 버린 양은 `etl_load_attempt.quality_report` 에 남는다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,200}\Z")
DATASET = "similar-package"
# curated 적재기(pipeline/postgresql/postgres.py)와 다른 키를 쓴다. 같으면 서로를 막는다.
LOCK_KEY = 5150211
# CK_SIMILAR_PACKAGE_RANK — rank BETWEEN 1 AND 50
RANK_MAX = 50


def contract_sha256() -> str:
    """이 적재기 코드와 DB 마이그레이션을 하나의 해시로 묶는다.

    어떤 계약으로 게시했는지가 실행 이력에 남아야 재검증이 성립한다
    (`pipeline/postgresql/load.py` 와 같은 판단).
    """
    digest = hashlib.sha256()
    paths = sorted(p for p in Path(__file__).parent.glob("*.py") if not p.name.startswith("test_"))
    paths += sorted((ROOT / "backend/src/main/resources/db/migration").glob("V*.sql"))
    for path in paths:
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


# ── 입력 승인 ────────────────────────────────────────────────────────────

def select_run(run_dir: Path, allow_gate_skip: bool) -> dict:
    """배치 산출물이 게시해도 되는 상태인지 확인하고 manifest 를 돌려준다."""
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
        # 배치가 --allow-gate-skip 으로 돌면 _SUCCESS 는 찍히지만 채점은 안 한 상태다.
        # 마커만 믿으면 품질이 검증되지 않은 결과가 조용히 서비스로 나간다.
        if not allow_gate_skip:
            raise SystemExit(
                "채점 게이트가 SKIPPED 다. 검증되지 않은 결과를 게시하려면 --allow-gate-skip 을 명시할 것"
            )
    else:
        raise SystemExit(f"채점 게이트가 {status} 다 — 게시하지 않는다")

    model_ver = manifest.get("model_ver")
    if not isinstance(model_ver, str) or not model_ver or model_ver == "unknown":
        # model_ver 은 similar_package 에 그대로 들어가 롤백의 기준이 된다.
        # "unknown" 이 적재되면 어느 모델이 만든 결과인지 추적이 끊긴다.
        raise SystemExit("manifest 의 model_ver 이 비어 있거나 unknown 이다 — 모델 run_manifest.json 확인")

    created = manifest.get("created_at")
    if not isinstance(created, str):
        raise SystemExit("manifest 에 created_at 이 없다")
    return {
        "manifest": manifest,
        "manifest_sha256": hashlib.sha256(body).hexdigest(),
        "model_ver": model_ver,
        "created_at": created,
        "snapshot_at": created[:10],
        "candidates": candidates,
    }


# ── candidates.parquet → COPY 전송 파일 ──────────────────────────────────

_ESCAPE = str.maketrans({"\\": "\\\\", "\t": "\\t", "\n": "\\n", "\r": "\\r"})


def write_transport(candidates: Path, target: Path) -> int:
    """COPY text 형식 TSV 로 옮긴다. 이름·순위·점수 네 열만 쓴다.

    `user_visible` · `default_selected` 는 테이블에 컬럼이 없다. 특히 `default_selected` 는
    구상안 0910 §4.2 에서 "기본 선택: 없음" 으로 폐기된 개념이라 적재 대상이 아니다.
    `cos_score` 도 쓰지 않는다 — 테이블의 score 는 `final_score` 다.
    """
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


# ── 게시 SQL ────────────────────────────────────────────────────────────

def build_sql(transport: Path, verify_only: bool) -> str:
    copy_path = str(transport.resolve()).replace("\\", "/").replace("'", "''")
    return f"""
\\set ON_ERROR_STOP on
BEGIN;

-- 두 적재가 겹치면 전량 교체가 서로를 덮는다. 트랜잭션이 끝나면 자동으로 풀린다.
SELECT pg_advisory_xact_lock({LOCK_KEY});

CREATE TEMP TABLE stage_similar (
    base_package      text             NOT NULL,
    candidate_package text             NOT NULL,
    rank              integer          NOT NULL CHECK (rank >= 1),
    score             double precision NOT NULL
) ON COMMIT DROP;

\\copy stage_similar (base_package, candidate_package, rank, score) FROM '{copy_path}' WITH (FORMAT text, NULL '\\N', ENCODING 'UTF8')

-- 이름 → package_id. 매칭 실패분은 여기서 사라지고, 그만큼 순위에 구멍이 난다.
-- row_number 로 1부터 다시 매겨 연속을 회복한다. 그대로 두면 화면이 rank<=3 으로
-- 세 개를 기대하는데 한둘만 나온다.
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

-- 하나도 못 붙었다면 이름 공간이 어긋난 것이다. 비우고 끝내면 서비스가 죽는다.
DO $$ BEGIN
  IF (SELECT loaded_rows FROM quality) = 0 THEN
    RAISE EXCEPTION 'package 테이블과 이름이 하나도 맞지 않는다 — 입력 코퍼스를 확인할 것';
  END IF;
END $$;

-- 실행 이력. curated 적재기와 같은 세 테이블을 dataset='{DATASET}' 으로 쓴다.
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

-- 전량 교체. DELETE 가 먼저여야 UK_SIMILAR_PACKAGE_RANK 와 부딪히지 않는다.
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

-- 지금 서비스가 보고 있는 결과가 어느 실행인지. 롤백은 이 포인터가 기준이다.
INSERT INTO public.etl_dataset_current (dataset, execution_id, snapshot_at, manifest_sha256, manifest)
VALUES ('{DATASET}', :'execution_id', :'snapshot_at', :'manifest_sha256', :'manifest'::jsonb)
ON CONFLICT (dataset) DO UPDATE
   SET execution_id=EXCLUDED.execution_id, snapshot_at=EXCLUDED.snapshot_at,
       manifest_sha256=EXCLUDED.manifest_sha256, manifest=EXCLUDED.manifest,
       published_at=clock_timestamp();

SELECT to_jsonb(q) FROM quality q;

{"ROLLBACK;" if verify_only else "COMMIT;"}
"""


# ── 실행 ────────────────────────────────────────────────────────────────

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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True, help="배치의 --out 디렉터리")
    parser.add_argument("--execution-id", required=True, help="이 게시의 식별자. 재실행 시 같은 값을 준다")
    parser.add_argument("--work-dir", type=Path, default=ROOT / "data/similar_package")
    parser.add_argument("--allow-gate-skip", action="store_true",
                        help="채점 게이트가 SKIPPED 여도 게시한다 (게이트 미구현 기간용)")
    parser.add_argument("--verify-only", action="store_true",
                        help="게시 직전까지 전부 실행한 뒤 ROLLBACK. DB 는 그대로 둔다")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--docker-container", help="로컬 PostgreSQL 컨테이너 이름")
    target.add_argument("--psql", help="psql 실행 파일 경로")
    parser.add_argument("--database", required=True)
    parser.add_argument("--db-user", default="postgres")
    args = parser.parse_args(argv)

    if not SAFE_ID.fullmatch(args.execution_id):
        raise SystemExit("execution-id 는 영문·숫자·밑줄·하이픈 1~200자")

    run_dir = args.run_dir.resolve()
    selected = select_run(run_dir, args.allow_gate_skip)
    attempt_id = uuid.uuid4().hex
    work = (args.work_dir / args.execution_id / attempt_id).resolve()
    work.mkdir(parents=True, exist_ok=False)

    transport = work / "candidates.copy.tsv"
    staged = write_transport(selected["candidates"], transport)
    print(f"전송 파일 준비: {staged} 행 ({transport})", flush=True)

    script = work / "publish.sql"
    script.write_text(build_sql(transport, args.verify_only), encoding="utf-8")

    command = psql_command(args) + [
        "-v", "ON_ERROR_STOP=1", "-t", "-A", "-q",
        "-v", f"execution_id={args.execution_id}",
        "-v", f"attempt_id={attempt_id}",
        "-v", f"model_ver={selected['model_ver']}",
        "-v", f"snapshot_at={selected['snapshot_at']}",
        "-v", f"snapshot_timestamp={selected['created_at']}",
        "-v", f"curated_run_id={run_dir.name}",
        "-v", f"run_prefix={run_dir.as_posix()}",
        "-v", f"manifest_sha256={selected['manifest_sha256']}",
        "-v", f"contract_sha256={contract_sha256()}",
        "-v", "manifest=" + json.dumps(selected["manifest"], ensure_ascii=False),
        "-v", "expected_counts=" + json.dumps({"similar_package": staged}),
        "-f", str(script),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
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
