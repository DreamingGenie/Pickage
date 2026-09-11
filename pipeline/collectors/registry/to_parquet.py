"""raw jsonl.gz → registry_versions/part-00000.parquet + registry_status.parquet (수집계획 §2-2).

  python to_parquet.py --raw data/registry/raw/run=2026-09-09 --out data/registry/parquet

registry_versions: 한 행 = 패키지 × 버전. 열 이름은 deps.dev requirements 와 같게(Dependencies·PeerDependencies·OptionalDependencies)
                   + DevDependencies. 배열은 STRUCT(Name, Requirement)[]. unpublish 버전의 의존 네 열은 NULL(모름). Name 순 정렬, zstd.
registry_status  : 패키지 1행. status = READY / NOT_FOUND / UNPUBLISHED / FAILED / PENDING (체크포인트 기준).
                   화면·통계에서 "자료 없음"을 0과 구분하는 용도.
수집 중에도 실행 가능: 수집기가 쓰고 있는 마지막 part 는 건너뛰고, 수집기가 없는데 잘린 part(강제 종료)는 읽히는 줄까지 복구한다.
체크포인트(checkpoint.sqlite)가 없으면 아무것도 바꾸지 않고 멈춘다. 출력은 임시 폴더에 쓴 뒤 교체해 실패 시 이전 결과가 남는다.
"""
import argparse
import glob
import gzip
import json
import os
import shutil
import sys
import zlib

import duckdb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from status import alive  # noqa: E402  수집기 실행 여부(마지막 part 를 '쓰는 중' 으로 볼지 판단)

GZ_ERRORS = (EOFError, OSError, zlib.error)  # 절단=EOFError, 헤더/CRC 손상=BadGzipFile(OSError), deflate 블록 손상=zlib.error

ap = argparse.ArgumentParser()
ap.add_argument("--raw", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()

ckpath = os.path.join(a.raw, "checkpoint.sqlite")
assert os.path.exists(ckpath), f"checkpoint.sqlite not found under {a.raw} — 패키지 상태의 정본이라 없으면 변환하지 않는다"
files = sorted(glob.glob(os.path.join(a.raw, "part-*.jsonl.gz")))
assert files, "no parts under " + a.raw


def _complete(path):
    """끝까지 정상으로 읽히는 gzip 인가. 0바이트(회전 직후 종료, gzip 헤더도 없음)는 읽을 게 없으니 불완전으로 본다."""
    if os.path.getsize(path) == 0:
        return False
    try:
        with gzip.open(path, "rb") as f:
            while f.read(1 << 20):
                pass
        return True
    except GZ_ERRORS:
        return False


def _repair(path):
    """강제 종료로 잘린 part: JSON 으로 읽히는 온전한 줄까지 살려 다시 쓰고 원본은 .broken 으로 보관.
    CRC 손상 스트림은 예외 전에 쓰레기 줄을 내놓을 수 있어 줄마다 JSON 파싱으로 확인한다."""
    lines = []
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                if not line.endswith("\n"):
                    break
                try:
                    json.loads(line)
                except ValueError:
                    break
                lines.append(line)
    except GZ_ERRORS:
        pass
    os.replace(path, path + ".broken")
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"[to_parquet] repaired {os.path.basename(path)}: {len(lines)} lines salvaged (original kept as .broken)")


def _p(path):
    return path.replace(os.sep, "/")


newest = files[-1]
incomplete = [f for f in files if not _complete(f)]
collector_running = alive() > 0
for f in incomplete:
    if f == newest and collector_running:
        continue  # 수집기가 지금 쓰는 파일 — 건너뜀
    _repair(f)    # 수집기가 없으면 마지막 part 도 잘린 파일이므로 살릴 수 있는 만큼 살린다
if newest in incomplete and collector_running:
    print(f"[to_parquet] skipping in-progress part: {os.path.basename(newest)}")
    files = files[:-1]
files = [f for f in files if os.path.getsize(f) > 0]  # 복구 결과가 빈 gzip(헤더만)인 part 는 DuckDB 에 넘길 필요 없음
assert files, "no complete parts yet"

DEP = "STRUCT(Name VARCHAR, Requirement VARCHAR)[]"
con = duckdb.connect()
# read_json 결과를 바로 v 로 만든다(raw 를 따로 물질화하면 2,000만 행 기준 메모리가 두 배, 약 32 GB).
# 같은 (Name, Version) 이 여러 번 받혔으면(재시작 중복·재시도) 가장 최근 fetched_at 만 남긴다.
# 시각 문자열은 ISO 8601(Z 포함) → TIMESTAMPTZ 로 읽어 UTC 기준 TIMESTAMP 로 저장.
# unpublish 행의 의존 네 열은 NULL 로 강제한다(09-09 run 은 [] 로 수집됐고, 이후 수집기는 NULL 로 쓴다).
con.execute(
    f"""CREATE TABLE v AS
       SELECT Name, Version,
              try_cast(published_at AS TIMESTAMPTZ) AT TIME ZONE 'UTC' AS published_at, rank,
              CASE WHEN unpublished THEN NULL ELSE Dependencies END AS Dependencies,
              CASE WHEN unpublished THEN NULL ELSE DevDependencies END AS DevDependencies,
              CASE WHEN unpublished THEN NULL ELSE PeerDependencies END AS PeerDependencies,
              CASE WHEN unpublished THEN NULL ELSE OptionalDependencies END AS OptionalDependencies,
              deprecated, unpublished,
              try_cast(fetched_at AS TIMESTAMPTZ) AT TIME ZONE 'UTC' AS fetched_at,
              try_cast(modified AS TIMESTAMPTZ) AT TIME ZONE 'UTC' AS modified
       FROM read_json({[_p(f) for f in files]!r}, format='newline_delimited',
            columns={{'Name':'VARCHAR','Version':'VARCHAR','published_at':'VARCHAR','rank':'INTEGER',
                     'Dependencies':'{DEP}','DevDependencies':'{DEP}','PeerDependencies':'{DEP}','OptionalDependencies':'{DEP}',
                     'deprecated':'VARCHAR','unpublished':'BOOLEAN','fetched_at':'VARCHAR','modified':'VARCHAR'}})
       QUALIFY row_number() OVER (PARTITION BY Name, Version ORDER BY fetched_at DESC) = 1"""
)

# 패키지 단위 상태는 체크포인트가 정본(요청은 했지만 버전 행이 없는 NOT_FOUND·UNPUBLISHED·FAILED 도 포함).
con.execute(f"ATTACH '{_p(ckpath)}' AS ck (TYPE sqlite, READ_ONLY)")
con.execute(
    """CREATE TABLE st AS
       SELECT t.name, t.rank::INTEGER AS rank,
              CASE t.status WHEN 'done' THEN 'READY' WHEN 'not_found' THEN 'NOT_FOUND' WHEN 'unpublished' THEN 'UNPUBLISHED'
                            WHEN 'failed' THEN 'FAILED' ELSE 'PENDING' END AS status,
              COALESCE(a.n_versions, 0) AS n_versions, COALESCE(a.n_unpub, 0) AS n_versions_unpublished,
              a.first_published_at, a.last_published_at,
              try_cast(t.modified AS TIMESTAMPTZ) AT TIME ZONE 'UTC' AS modified,
              try_cast(t.fetched_at AS TIMESTAMPTZ) AT TIME ZONE 'UTC' AS fetched_at,
              t.http::INTEGER AS http, t.bytes::BIGINT AS doc_bytes, t.error
       FROM ck.tasks t
       LEFT JOIN (SELECT Name, count(*) AS n_versions, count(*) FILTER (WHERE unpublished) AS n_unpub,
                         min(published_at) AS first_published_at, max(published_at) AS last_published_at
                  FROM v GROUP BY Name) a ON a.Name = t.name
       ORDER BY t.rank"""
)

# 임시 폴더에 쓰고 마지막에 교체한다. COPY 가 OOM·Ctrl+C 로 죽어도 이전 Parquet 가 그대로 남고, 빈 폴더가 생기지 않는다.
os.makedirs(a.out, exist_ok=True)
tmp = os.path.join(a.out, ".tmp_registry")
if os.path.isdir(tmp):
    shutil.rmtree(tmp)
os.makedirs(os.path.join(tmp, "registry_versions"))
con.execute(
    f"""COPY (SELECT * FROM v ORDER BY Name, published_at, Version)
        TO '{_p(os.path.join(tmp, 'registry_versions', 'part-00000.parquet'))}' (FORMAT PARQUET, COMPRESSION ZSTD)"""
)
con.execute(f"COPY st TO '{_p(os.path.join(tmp, 'registry_status.parquet'))}' (FORMAT PARQUET, COMPRESSION ZSTD)")
outv = os.path.join(a.out, "registry_versions")
if os.path.isdir(outv):
    shutil.rmtree(outv)
os.replace(os.path.join(tmp, "registry_versions"), outv)
os.replace(os.path.join(tmp, "registry_status.parquet"), os.path.join(a.out, "registry_status.parquet"))
shutil.rmtree(tmp)

n_v = con.execute("SELECT count(*) FROM v").fetchone()[0]
n_pkg = con.execute("SELECT count(DISTINCT Name) FROM v").fetchone()[0]
n_unpub = con.execute("SELECT count(*) FROM v WHERE unpublished").fetchone()[0]
n_dev = con.execute("SELECT count(*) FROM v WHERE len(DevDependencies) > 0").fetchone()[0]
n_st = con.execute("SELECT count(*) FROM st").fetchone()[0]
by = dict(con.execute("SELECT status, count(*) FROM st GROUP BY status ORDER BY status").fetchall())
print(f"[to_parquet] registry_versions rows={n_v} packages={n_pkg} unpublished_versions={n_unpub} rows_with_devDeps={n_dev} "
      f"| registry_status rows={n_st} {by} -> {a.out}")
