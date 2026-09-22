"""관측된 교체 흐름 이동쌍을 git 데이터셋에서 PostgreSQL 에 게시한다 (S15P21A506-424).

입력  datasets/migration_pairs_260908/migration_pairs_all.csv      (dep_kind=regular)
      datasets/migration_pairs_dev_260914/migration_pairs_all.csv  (dep_kind=dev)
출력  public.migration_pair (전량 교체) + etl_* 이력

    .venv-bq/Scripts/python.exe -m pipeline.migration_pairs.load \\
      --run-id migration-pairs-20260922-v1 \\
      --docker-container pickage-local-postgres-1 --database pickage --db-user postgres \\
      --verify-only

## 왜 MinIO 회차가 아니라 git 의 CSV 를 읽나

형제 적재기 둘(`dependent_transitions` · `removal_reasons`)은 MinIO 회차의 parquet 을 받아
온다. 이동쌍은 다르다 — **쌍 CSV 를 MinIO 에 올리지 않기로** 이미 정해져 있다.

    pipeline/minio/ingest_derived.py:135
    쌍 CSV 3종과 removal_*.csv 는 git datasets/migration_pairs_260908/ 에 있다.

그 결정이 옳다. 23,629행 · 3.4 MB 라 git 이 감당하고, 추적 파일이라 **어느 회차로 적재했는지
를 커밋으로 되짚을 수 있다.** MinIO 를 거치면 자격증명과 터널이 필요해지는데 얻는 것이 없다.

대신 회차 식별을 manifest 가 아니라 **CSV 파일의 SHA-256** 으로 한다. 형제 적재기가 manifest
와 parquet 을 대조하는 자리에서, 이 적재기는 읽은 파일의 해시를 그대로 이력에 남긴다.

**데이터셋을 다시 만들었으면 `--run-id` 를 올린다.** 같은 회차 이름에 다른 내용을 올리려 하면
적재기가 CSV 를 보내기 전에 끊는다. 형제 적재기는 run_id 가 불변 MinIO 회차를 가리켜 이런 일이
없지만, 여기서는 입력이 git 의 파일이라 내용이 바뀔 수 있다 — 자세한 이유는 `build_sql` 의
`publish_key` 주석에 있다.

## dep_kind 는 여기서 붙인다 (S15P21A506-211 결정 3-1)

네 데이터셋의 CSV 열 구성이 완전히 같아 **구분이 디렉터리 이름뿐이다.** 빌더를 고쳐 열을
내게 할 일이 아니라 적재기가 어디서 읽었는지로 붙인다. 아래 SOURCES 가 그 대응표다.

적재하지 않는 둘을 여기 적어 둔다 — 지우면 다음 사람이 다시 판단해야 한다.

    migration_pairs_regular_legacy_260914  재분류 과대 계상 12.15% 를 재려고 만든 **대조군**.
                                           서빙 자료가 아니다 (결정 3-2)
    migration_pairs_regular_260914         이탈 비율 보정용. .gitignore:47 에 있어 저장소에
                                           없다 — 입력으로 쓰면 다른 PC 에서 재현되지 않는다

## 두 원천의 기준일이 다르다 (결정 3-4)

regular 는 deps.dev **2026-08-31 스냅샷**, dev 는 npm registry 수집분이 담은 **2026-09-16**
까지다. 한 표에 기준일이 둘 섞이므로 행마다 `snapshot_at` 을 넣는다. `etl_load_execution`
은 스냅샷을 하나만 갖는 구조라 주력인 regular 의 날짜를 쓰고, 두 값 모두 manifest 에 남긴다.

`last_seen` 이 `snapshot_at` 을 넘는 행이 있는데 오류가 아니다. 이유는 V13 마이그레이션의
머리말에 적었다 — regular 는 추출 사고, dev 는 정상 수집 범위다. 그래서 막지 않고 **세어서
quality 에 남긴다.** 다음 회차에서 갑자기 늘면 추출이 또 샌 것이다.

## 도착지는 package 에 없어도 버리지 않는다

출발 패키지만 `package` 와 이름으로 붙인다. 도착지는 이름 그대로 넣는다. 2026-09-22 실측에서
도착지 327쌍이 `package` 에 없었고 그중 61건은 기본 필터를 통과하면서 상위 5 안에 든다.
**버리면 55개 패키지의 분포가 거짓이 된다.** 근거는 V13 머리말에 있다.

출발 쪽이 안 붙는 489쌍은 빠진다. 조회가 `package_id` 로 들어오므로 어차피 닿지 않는다 —
`removal_reasons/load.py` 가 "미해결은 경고가 아니다" 라고 적은 것과 같은 이유다.

## 운영에 게시하기

`dependent_transitions/load.py` 의 "운영에 게시하기" 절이 그대로 적용된다. PC 에서 돌리고
서버의 psql 만 원격으로 쓴다.

    $env:DOCKER_HOST='ssh://a506app'

이 적재기는 MinIO 를 보지 않으므로 **터널이 필요 없다.** `--verify-only` 로 매칭률을 먼저
확인한 뒤 게시한다.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import uuid

try:  # Windows 콘솔 cp949 에서 한글 출력 보장
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[2]
# etl 이력에 남기는 이름. removal_reasons/load.py 가 SOURCE_DATASET 으로 부르는 MinIO 회차
# 이름과 글자가 같지만, 그쪽이 etl 에 남기는 이름은 removal-reasons 라 겹치지 않는다.
DATASET = "migration-pairs"
TABLE = "migration_pair"
CSV_NAME = "migration_pairs_all.csv"

# dep_kind → (데이터셋 디렉터리, 원천 기준일, 그 날짜가 무엇인지)
#
# 디렉터리를 바꿀 때는 기준일도 함께 고친다. CLI 인자로 받지 않는 이유는, 데이터셋 폴더가
# 이름에 날짜를 달고 git 에 고정돼 있어 **둘이 따로 움직일 수 없기** 때문이다. 인자로 열어
# 두면 폴더와 날짜가 어긋난 채로 적재할 수 있게 된다.
SOURCES = {
    "regular": ("datasets/migration_pairs_260908", "2026-08-31",
                "deps.dev BigQuery 스냅샷 (전이 3,958만)"),
    "dev": ("datasets/migration_pairs_dev_260914", "2026-09-16",
            "npm registry 수집분(S15P21A506-280, run 2026-09-09)이 담은 마지막 발행일 (전이 726만)"),
}
# etl_load_execution 은 스냅샷을 하나만 갖는다. 주력 원천의 날짜를 쓴다.
PRIMARY_KIND = "regular"

# CSV 열 순서. 빌더의 SELECT_COLS 와 같아야 하고, 아래 COPY 문의 열 목록과도 같아야 한다.
COLUMNS = ("from_pkg", "to_pkg", "votes", "co_events", "removal_events", "publisher_months",
           "dependents", "a_pct", "b_pct", "lift", "share_pct", "share_pm_pct",
           "bidirectional", "first_seen", "last_seen")

SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,200}\Z")

# 이름에서 유도해 다른 데이터셋과 겹치지 않는다 (dependent_transitions/load.py 와 같은 방식).
LOCK_KEY = f"hashtextextended('curated:{DATASET}', 0)"

# 전량 교체가 남긴 dead tuple 정리. 트랜잭션 밖이어야 하고, 실패해도 적재는 유효하다.
VACUUM = f"""
\\set ON_ERROR_STOP off
VACUUM (ANALYZE) public."{TABLE}";
"""


def contract_sha256() -> str:
    """적재기 코드와 DB 마이그레이션을 하나의 해시로 묶는다. 둘 중 하나만 바뀌어도 값이 달라져
    etl 이력에서 "어떤 계약으로 적재했는지" 를 구분할 수 있다."""
    digest = hashlib.sha256()
    paths = sorted(p for p in Path(__file__).parent.glob("*.py") if not p.name.startswith("test_"))
    paths += sorted((ROOT / "backend/src/main/resources/db/migration").glob("V*.sql"))
    for path in paths:
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def relative_path(path: Path) -> str:
    """이력에 남길 경로. 저장소 안이면 상대 경로로 줄여 커밋과 맞춰 읽을 수 있게 한다.

    밖이면 절대 경로를 그대로 쓴다 — 여기서 예외를 던지면 저장소 밖 디렉터리로는 적재기를
    돌릴 수 없게 되는데, 그건 이력 표기의 편의가 실행을 막는 것이라 앞뒤가 바뀐다.
    """
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_source(kind: str, directory: Path, snapshot: str, writer) -> dict:
    """한 데이터셋을 읽어 전송 CSV 로 옮기고 회차 정보를 돌려준다.

    이스케이프를 손으로 만들지 않고 csv 모듈에 맡긴다. 형제 적재기는 같은 자리에서 DuckDB 를
    쓰는데, 그쪽 입력은 parquet 이라 변환이 필요했다. 여기는 입력이 이미 CSV 라 DuckDB 를
    새로 들일 이유가 없다 — 적재기가 40 GB 짜리 의존을 갖지 않는 편이 낫다.

    BOM 을 utf-8-sig 로 벗긴다. 빌더가 BOM 을 붙여 내보내므로(엑셀 호환) 그냥 읽으면 첫 열
    이름이 '\\ufefffrom_pkg' 가 되어 조용히 KeyError 가 난다.
    """
    path = directory / CSV_NAME
    if not path.exists():
        raise SystemExit(f"입력 CSV 가 없다: {path}\n"
                         f"  dep_kind={kind} 의 데이터셋 디렉터리를 확인할 것")

    rows = 0
    self_pairs = []
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != COLUMNS:
            raise SystemExit(f"{path} 의 열 구성이 계약과 다르다\n"
                             f"  기대: {COLUMNS}\n  실제: {tuple(reader.fieldnames or ())}")
        for row in reader:
            # 자기 자신으로 가는 이동은 이동이 아니다. DB CHECK 로는 볼 수 없어(package 를
            # 조인해야 한다) 여기서 본다. 빌더는 만들지 않지만 조용히 들어오면 화면이
            # "X 에서 X 로" 를 그린다.
            if row["from_pkg"] == row["to_pkg"]:
                self_pairs.append(row["from_pkg"])
            writer.writerow([kind, snapshot] + [row[column] for column in COLUMNS])
            rows += 1

    if self_pairs:
        raise SystemExit(f"{path} 에 자기 자신으로 가는 쌍이 {len(self_pairs)}개 있다: "
                         f"{self_pairs[:5]}")
    if rows == 0:
        raise SystemExit(f"{path} 이 비어 있다")
    return {"dep_kind": kind, "path": relative_path(path), "rows": rows,
            "sha256": file_sha256(path), "bytes": path.stat().st_size, "snapshot_at": snapshot}


def build_sql(verify_only: bool) -> tuple[str, str]:
    """psql 스크립트를 CSV 삽입 지점 앞뒤로 나눠 돌려준다."""
    head = f"""
\\set ON_ERROR_STOP on
BEGIN;

-- 동시 적재 차단 (트랜잭션 종료 시 자동 해제)
SELECT pg_advisory_xact_lock({LOCK_KEY});

-- 같은 회차 이름에 **다른 내용**을 덮으려는 것을 여기서 끊는다.
--
-- etl_dataset_current 는 (dataset, execution_id, snapshot_at, manifest_sha256) 복합 FK 로
-- etl_load_execution 을 가리키는데 ON UPDATE CASCADE 가 없다. 그래서 아래 ON CONFLICT
-- DO UPDATE 가 manifest_sha256 을 바꾸는 순간 그 참조가 끊겨 FK 위반으로 죽는다. 데이터는
-- 롤백되어 안전하지만, 사람에게 남는 것은
-- "violates foreign key constraint etl_dataset_current_…_fkey" 라는 원문뿐이라 **무엇을
-- 해야 하는지 알 수 없다.** --verify-only 도 같은 지점에서 막혀 확인할 길조차 없다.
--
-- **형제 적재기는 이 자리에 닿지 않는다.** 그쪽 run_id 는 불변 MinIO 회차를 가리켜서 같은
-- run_id 면 manifest_sha256 도 같고, DO UPDATE 가 FK 열을 건드리지 않는다. 이 적재기는
-- manifest 를 git CSV 내용에서 유도하므로 **데이터셋을 다시 만들면 같은 run_id 라도 해시가
-- 반드시 달라진다** — 재생성은 이 저장소에서 일상이다(S15P21A506-395 09-21 · -422 09-22,
-- 그리고 -136 9번 "새 스냅샷마다 30분 전체 재실행").
--
-- 막기만 하고 자동으로 새 회차를 만들지는 않는다. 덮어쓰기는 사람이 뜻을 확인해야 하는
-- 일이고, "옛 회차를 덮지 않고 새 run_id 로 올린다" 가 이 저장소의 원칙이다
-- (datasets/dependent_transitions_260917/README.md §1).
--
-- CSV 전송 **앞**에 두어 2.3만 행을 보내기 전에 끊는다. psql 변수는 달러 인용(DO $$) 안에서
-- 치환되지 않으므로 임시 표를 거쳐 넘긴다.
CREATE TEMP TABLE publish_key ON COMMIT DROP AS
SELECT :'execution_id'::text AS execution_id, :'manifest_sha256'::text AS manifest_sha256;

DO $$
DECLARE previous text;
BEGIN
  SELECT e.manifest_sha256 INTO previous
    FROM public.etl_load_execution e
    JOIN publish_key k ON k.execution_id = e.execution_id;
  IF previous IS NOT NULL AND previous <> (SELECT manifest_sha256 FROM publish_key) THEN
    RAISE EXCEPTION E'같은 회차 이름에 다른 입력을 올리려 한다 — 새 회차로 올릴 것\\n'
                     '  회차          %\\n'
                     '  이미 게시된 것 %\\n'
                     '  지금 읽은 것   %\\n'
                     '데이터셋 CSV 를 다시 만들었다면 --run-id 를 올린다.',
                    (SELECT execution_id FROM publish_key), previous,
                    (SELECT manifest_sha256 FROM publish_key);
  END IF;
END $$;

CREATE TEMP TABLE stage_pair (
    dep_kind         text    NOT NULL,
    snapshot_at      date    NOT NULL,
    from_pkg         text    NOT NULL,
    to_pkg           text    NOT NULL,
    votes            numeric NOT NULL,
    co_events        integer NOT NULL,
    removal_events   integer NOT NULL,
    publisher_months integer NOT NULL,
    dependents       integer NOT NULL,
    a_pct            numeric NOT NULL,
    b_pct            numeric NOT NULL,
    lift             numeric NOT NULL,
    share_pct        numeric NOT NULL,
    share_pm_pct     numeric NOT NULL,
    bidirectional    boolean NOT NULL,
    first_seen       date    NOT NULL,
    last_seen        date    NOT NULL
) ON COMMIT DROP;

COPY stage_pair (dep_kind, snapshot_at, from_pkg, to_pkg, votes, co_events, removal_events,
                 publisher_months, dependents, a_pct, b_pct, lift, share_pct, share_pm_pct,
                 bidirectional, first_seen, last_seen)
FROM STDIN WITH (FORMAT csv, ENCODING 'UTF8');
"""
    tail = f"""

-- 출발 이름 → package_id. 도착지는 이름 그대로 간다 (머리말 참고).
CREATE TEMP TABLE resolved ON COMMIT DROP AS
SELECT p.package_id AS from_package_id, s.to_pkg AS to_package_name, s.dep_kind,
       s.votes, s.co_events, s.removal_events, s.publisher_months, s.dependents,
       s.a_pct, s.b_pct, s.lift, s.share_pct, s.share_pm_pct, s.bidirectional,
       s.first_seen, s.last_seen, s.snapshot_at
  FROM stage_pair s
  JOIN "package" p ON p."name" = s.from_pkg;

CREATE TEMP TABLE quality ON COMMIT DROP AS
SELECT (SELECT count(*)                     FROM stage_pair)  AS staged_rows,
       (SELECT count(DISTINCT from_pkg)     FROM stage_pair)  AS staged_from_pkgs,
       (SELECT count(*)                     FROM resolved)    AS loaded_rows,
       (SELECT count(DISTINCT from_package_id) FROM resolved) AS loaded_from_pkgs,
       (SELECT count(DISTINCT s.from_pkg)   FROM stage_pair s
          LEFT JOIN "package" p ON p."name" = s.from_pkg
         WHERE p.package_id IS NULL)                          AS unresolved_from_pkgs,
       -- 도착지가 package 에 없는 쌍. **빠지지 않고 들어간 것들이다** — 이름으로만 그린다.
       -- 세어 두는 것은 화면이 "상세로 갈 수 없는 도착지" 를 얼마나 그리는지 알기 위해서다.
       (SELECT count(*) FROM resolved r
          LEFT JOIN "package" p ON p."name" = r.to_package_name
         WHERE p.package_id IS NULL)                          AS dest_not_in_package,
       -- 기준일을 넘는 관측. regular 는 추출 사고, dev 는 정상 수집 범위다 (V13 머리말).
       -- **다음 회차에서 regular 쪽이 갑자기 늘면 추출이 또 샌 것이다.**
       (SELECT jsonb_object_agg(k.dep_kind, k.n) FROM
          (SELECT dep_kind, count(*) AS n FROM resolved
            WHERE last_seen > snapshot_at GROUP BY dep_kind) k) AS beyond_snapshot,
       (SELECT jsonb_object_agg(k.dep_kind, jsonb_build_object(
                   'rows', k.n, 'from_pkgs', k.f, 'snapshot_at', k.s,
                   'default_filter_rows', k.d))
          FROM (SELECT dep_kind, count(*) AS n, count(DISTINCT from_package_id) AS f,
                       max(snapshot_at)::text AS s,
                       count(*) FILTER (WHERE votes >= 5 AND publisher_months >= 3) AS d
                  FROM resolved GROUP BY dep_kind) k)          AS by_dep_kind;

-- 한 건도 못 붙으면 중단. 이름 규칙이 어긋났거나 package 가 비어 있다는 뜻이다.
DO $$ BEGIN
  IF (SELECT loaded_rows FROM quality) = 0 THEN
    RAISE EXCEPTION 'package 테이블과 이름이 하나도 맞지 않는다 — 적재 대상 DB 를 확인할 것';
  END IF;
END $$;

-- 한 종류가 통째로 빠지면 중단. 행 수만 보면 regular 만 들어와도 정상으로 보인다.
DO $$ BEGIN
  IF (SELECT count(DISTINCT dep_kind) FROM resolved) <> {len(SOURCES)} THEN
    RAISE EXCEPTION 'dep_kind 가 % 종류뿐이다 (기대 {len(SOURCES)})',
                    (SELECT count(DISTINCT dep_kind) FROM resolved);
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
       snapshot_at=EXCLUDED.snapshot_at, snapshot_timestamp=EXCLUDED.snapshot_timestamp,
       manifest_sha256=EXCLUDED.manifest_sha256, contract_sha256=EXCLUDED.contract_sha256,
       input_metadata=EXCLUDED.input_metadata, expected_counts=EXCLUDED.expected_counts,
       error_message=NULL, updated_at=clock_timestamp();

INSERT INTO public.etl_load_attempt
    (attempt_id, execution_id, status, phase, validation_contract_sha256)
VALUES (:'attempt_id', :'execution_id', 'PREPARING', 'VALIDATE_INPUT', :'contract_sha256');

-- 전량 교체. 한 회차가 표 전체를 대신한다 — 두 원천을 따로 적재하면 기준일이 섞인 채
-- 한쪽만 낡는다. TRUNCATE 가 아니라 DELETE 인 이유는 dependent_transitions/load.py 에 있다
-- (ACCESS EXCLUSIVE 로 조회가 멈춰 서는 것을 피한다).
LOCK TABLE public."{TABLE}", public.etl_dataset_current IN SHARE ROW EXCLUSIVE MODE;
DELETE FROM public."{TABLE}";
INSERT INTO public."{TABLE}"
    (from_package_id, to_package_name, dep_kind, votes, co_events, removal_events,
     publisher_months, dependents, a_pct, b_pct, lift, share_pct, share_pm_pct,
     bidirectional, first_seen, last_seen, snapshot_at)
SELECT from_package_id, to_package_name, dep_kind, votes, co_events, removal_events,
       publisher_months, dependents, a_pct, b_pct, lift, share_pct, share_pm_pct,
       bidirectional, first_seen, last_seen, snapshot_at
  FROM resolved;

UPDATE public.etl_load_attempt
   SET status='PUBLISHED', phase='COMMIT', completed_at=clock_timestamp(),
       actual_counts=jsonb_build_object('{TABLE}', (SELECT loaded_rows FROM quality)),
       quality_report=(SELECT to_jsonb(q) FROM quality q)
 WHERE attempt_id=:'attempt_id';

UPDATE public.etl_load_execution
   SET status='PUBLISHED', updated_at=clock_timestamp(), error_message=NULL,
       actual_counts=jsonb_build_object('{TABLE}', (SELECT loaded_rows FROM quality))
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


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True,
                        help="이 게시의 회차 이름 (migration-pairs-20260922-v1)")
    parser.add_argument("--execution-id", help="이 게시의 식별자. 재실행 시 같은 값을 준다")
    parser.add_argument("--work-dir", type=Path, default=ROOT / "data/migration_pairs_load")
    parser.add_argument("--verify-only", action="store_true",
                        help="게시 직전까지 전부 실행한 뒤 ROLLBACK. DB 는 그대로 둔다")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--docker-container", help="PostgreSQL 컨테이너 이름")
    target.add_argument("--psql", help="psql 실행 파일 경로")
    parser.add_argument("--database", required=True)
    parser.add_argument("--db-user", default="postgres")
    args = parser.parse_args(argv)

    if not SAFE_ID.fullmatch(args.run_id):
        parser.error("--run-id 는 영문·숫자·밑줄·하이픈 1~200자")
    args.execution_id = args.execution_id or f"{DATASET}-{args.run_id}"
    if not SAFE_ID.fullmatch(args.execution_id):
        parser.error("--execution-id 는 영문·숫자·밑줄·하이픈 1~200자")
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    attempt_id = uuid.uuid4().hex

    work = (args.work_dir / args.execution_id / attempt_id).resolve()
    work.mkdir(parents=True, exist_ok=False)
    transport = work / "pairs.copy.csv"

    sources = []
    with transport.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        for kind, (directory, snapshot, origin) in SOURCES.items():
            entry = read_source(kind, ROOT / directory, snapshot, writer)
            entry["origin"] = origin
            sources.append(entry)
            print(f"  {kind:8} {entry['rows']:>7,}행  {snapshot}  {entry['sha256'][:12]}…  "
                  f"{entry['path']}", flush=True)

    staged = sum(entry["rows"] for entry in sources)
    manifest = {"dataset": DATASET, "run_id": args.run_id, "sources": sources}
    manifest_body = json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode()
    snapshot_at = SOURCES[PRIMARY_KIND][1]
    print(f"전송 파일 준비: {staged:,}행 ({transport.name})", flush=True)

    # psql 이 docker exec 로 컨테이너 안에서 돌 수 있다. 그쪽에서는 호스트 경로를 못 보므로
    # 스크립트와 COPY 데이터를 모두 표준입력으로 흘려보낸다.
    head, tail = build_sql(args.verify_only)
    script = work / "publish.sql"
    with script.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(head)
        with transport.open("r", encoding="utf-8") as data:
            for chunk in iter(lambda: data.read(1 << 20), ""):
                stream.write(chunk)
        stream.write("\\.\n")
        stream.write(tail)

    command = psql_command(args) + [
        "-v", "ON_ERROR_STOP=1", "-t", "-A", "-q",
        "-v", f"execution_id={args.execution_id}",
        "-v", f"attempt_id={attempt_id}",
        "-v", f"snapshot_at={snapshot_at}",
        # 이 데이터셋의 시각 기준은 원천 스냅샷의 끝이다. 형제 적재기들과 같은 값을 써야
        # 대조할 때 경계가 어긋나지 않는다 (dependent_transitions/load.py 의 SNAPSHOT_END_TIME).
        "-v", f"snapshot_timestamp={snapshot_at}T23:59:59",
        "-v", f"curated_run_id={args.run_id}",
        # MinIO 회차가 아니라 git 경로다. 어디서 읽었는지가 곧 회차의 출처다.
        "-v", "run_prefix=" + ";".join(entry["path"] for entry in sources),
        "-v", f"manifest_sha256={hashlib.sha256(manifest_body).hexdigest()}",
        "-v", f"contract_sha256={contract_sha256()}",
        "-v", "manifest=" + json.dumps(manifest, ensure_ascii=False),
        "-v", "expected_counts=" + json.dumps({TABLE: staged}),
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
              "run_id": args.run_id, "sources": sources, "quality": quality}
    (work / "execution_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(quality, ensure_ascii=False, indent=2), flush=True)
    if quality:
        lost = quality["staged_rows"] - quality["loaded_rows"]
        if lost:
            share = lost / quality["staged_rows"] * 100
            print(f"출발 패키지가 package 에 없어 {lost:,}행({share:.1f}%)이 빠졌다 — "
                  f"이름 {quality['unresolved_from_pkgs']:,}개. 조회가 package_id 로 들어오므로 "
                  f"어차피 닿지 않는 행이다", flush=True)
        if quality.get("dest_not_in_package"):
            print(f"도착지가 package 에 없는 쌍 {quality['dest_not_in_package']:,}행 — "
                  f"**빠지지 않았다.** 이름으로만 그리고 상세로는 못 간다", flush=True)
    print(("검증만 하고 되돌렸다" if args.verify_only else "게시 완료") + f" — {work}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
