"""raw jsonl.gz → registry_versions/part-00000.parquet + registry_status.parquet (수집계획 §2-2).

  python to_parquet.py --raw data/registry/raw/run=2026-09-09 --out data/registry/parquet
  python to_parquet.py --raw data/registry/raw/run=2026-09-16-s* --out data/registry/parquet   # 4분할 수집(샤드 폴더 여러 개)

registry_versions: 한 행 = 패키지 × 버전. 열 이름은 deps.dev requirements 와 같게(Dependencies·PeerDependencies·OptionalDependencies)
                   + DevDependencies. 배열은 STRUCT(Name, Requirement)[]. unpublish 버전의 의존 네 열은 NULL(모름). Name 순 정렬, zstd.
형태 6열(S15P21A506-366): unpacked_size · file_count · module_type · main · types · exports.
                   6열이 없던 09-09 raw 도 그대로 읽힌다(없는 키는 NULL). license 는 여기서 받지 않고 deps.dev 와 조인한다.
registry_status  : 패키지 1행. status = READY / NOT_FOUND / UNPUBLISHED / FAILED / PENDING (체크포인트 기준).
                   화면·통계에서 "자료 없음"을 0과 구분하는 용도.
수집 중에도 실행 가능: 수집기가 쓰고 있는 마지막 part 는 건너뛰고, 수집기가 없는데 잘린 part(강제 종료)는 읽히는 줄까지 복구한다.
체크포인트(checkpoint.sqlite)가 없으면 아무것도 바꾸지 않고 멈춘다. 출력은 임시 폴더에 쓴 뒤 교체해 실패 시 이전 결과가 남는다.
출력 폴더에는 어느 --raw 로 만들었는지 registry_source.json 으로 남기고, 다른 run 으로 덮어쓰려 하면 멈춘다(--force 로 해제).
옵션: --repair-newest(수집기 실행 여부를 알 수 없는 환경에서 마지막 part 까지 복구) --force(다른 run 의 결과 덮어쓰기)
"""
import argparse
import glob
import gzip
import json
import os
import shutil
import sys
import time
import zlib

import duckdb

try:
    # 하위 프로세스로 불릴 때 출력이 파이프·파일이면 인코딩이 로캘(cp949)로 정해진다. 한글 메시지가 죽지 않게 고정한다.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from status import alive  # noqa: E402  수집기 실행 여부(마지막 part 를 '쓰는 중' 으로 볼지 판단)

GZ_ERRORS = (EOFError, OSError, zlib.error)  # 절단=EOFError, 헤더/CRC 손상=BadGzipFile(OSError), deflate 블록 손상=zlib.error
NEWEST_QUIET_S = 120                         # 마지막 part 를 손댄 지 이만큼 지나야 '아무도 안 쓰는 파일' 로 본다


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
    CRC 손상 스트림은 예외 전에 쓰레기 줄을 내놓을 수 있어 줄마다 JSON 파싱으로 확인한다.
    원본을 rename 하므로 수집기가 그 파일을 쓰고 있지 않다는 것이 확실할 때만 부른다."""
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


def newest_is_busy(newest, repair_newest=False, n_alive=None):
    """마지막 part 를 건드려도 되는가. alive() 는 실패하면 -1 을 돌려주는데(PowerShell 부재·20초 시간초과),
    그것을 '수집기 없음' 으로 읽으면 살아 있는 파일을 .broken 으로 옮겨 버린다. 리눅스에서는 rename 이 성공해
    수집기가 고아 inode 에 계속 쓰고 그 뒤 행이 전부 사라진다. 그래서 확실히 0 일 때만, 그리고 파일이
    조용해진 뒤에만 손댄다. 알 수 없는 환경에서 강제로 복구하려면 --repair-newest 를 준다."""
    if repair_newest:
        return False
    n = alive() if n_alive is None else n_alive
    if n < 0:
        print("[to_parquet] 수집기 실행 여부를 알 수 없다(alive=-1). 마지막 part 는 건드리지 않는다. "
              "죽은 수집기의 잘린 part 를 살리려면 --repair-newest 를 줄 것")
        return True
    if n > 0:
        return True
    return time.time() - os.path.getmtime(newest) <= NEWEST_QUIET_S


def check_output_source(out, raw_abs, force=False):
    """출력 폴더가 다른 run 으로 만든 것이면 멈춘다. --refresh-parquet 가 스모크 run 을 가리킨 채 본 결과를
    덮어쓰는 사고를 막는다. 표식이 없으면(이 기능 이전에 만든 결과) 허용하고 새로 남긴다."""
    marker = os.path.join(out, "registry_source.json")
    prev = None
    if os.path.exists(marker):
        try:
            with open(marker, encoding="utf-8") as f:
                prev = json.load(f).get("raw")
        except Exception:
            prev = None
    if prev and prev != raw_abs and not force:
        raise SystemExit(
            f"[to_parquet] {out} 은 {prev} 로 만든 결과다. 다른 run({raw_abs})으로 덮어쓰려면 --force 를 줄 것")
    return marker


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True, nargs="+",
                    help="run 폴더. 4분할 수집이면 샤드 폴더를 전부 나열한다(쉘 글롭 가능)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--repair-newest", action="store_true",
                    help="수집기 실행 여부를 확인할 수 없는 환경에서 마지막 part 까지 복구 대상으로 본다")
    ap.add_argument("--force", action="store_true", help="다른 run 으로 만든 출력 폴더를 덮어쓴다")
    a = ap.parse_args()

    raws = [os.path.abspath(r) for r in a.raw]
    ckpaths = []
    for r in raws:
        ck = os.path.join(r, "checkpoint.sqlite")
        assert os.path.exists(ck), f"checkpoint.sqlite not found under {r}. 패키지 상태의 정본이라 없으면 변환하지 않는다"
        ckpaths.append(ck)
    # 정렬해서 잇는다. 나열 순서만 다른 같은 집합이 '다른 run' 으로 보이면 --force 를 습관적으로 붙이게 되고,
    # 그러면 스모크 run 이 본 결과를 덮어쓰는 것을 막으려던 가드가 무력해진다. raws 자체의 순서는 바꾸지 않는다.
    raw_abs = ";".join(sorted(_p(r) for r in raws))
    marker = check_output_source(a.out, raw_abs, a.force)   # raw 를 건드리기 전에 확인한다

    # alive() 는 PowerShell 을 띄운다(최대 20초). 샤드마다 부르면 그만큼 늘어나므로 한 번만 재서 나눠 쓴다.
    n_alive = None if a.repair_newest else alive()
    files = []
    for r in raws:
        fs = sorted(glob.glob(os.path.join(r, "part-*.jsonl.gz")))
        assert fs, "no parts under " + r
        newest = fs[-1]
        incomplete = [f for f in fs if not _complete(f)]
        busy = newest_is_busy(newest, a.repair_newest, n_alive)
        for f in incomplete:
            if f == newest and busy:
                continue  # 수집기가 지금 쓰고 있을 수 있는 파일
            _repair(f)    # 아무도 안 쓰는 잘린 파일이므로 살릴 수 있는 만큼 살린다
        if newest in incomplete and busy:
            print(f"[to_parquet] skipping in-progress part: {os.path.basename(r)}/{os.path.basename(newest)}")
            fs = fs[:-1]
        files.extend(fs)
    assert files, "no complete parts yet"

    DEP = "STRUCT(Name VARCHAR, Requirement VARCHAR)[]"
    con = duckdb.connect()
    # 패키지 단위 상태는 체크포인트가 정본이다. 버전 행도 체크포인트로 걸러, 쓰다 만 패키지(failed·pending)의
    # 고아 행이 registry_versions 에 남지 않게 한다. (Name, Version) 중복 제거로는 그 행을 걸러낼 수 없다.
    for i, ck in enumerate(ckpaths):
        con.execute(f"ATTACH '{_p(ck)}' AS ck{i} (TYPE sqlite, READ_ONLY)")
    con.execute("CREATE VIEW ck_tasks AS " +
                " UNION ALL ".join(f"SELECT * FROM ck{i}.tasks" for i in range(len(ckpaths))))
    # 샤드는 대상이 겹치지 않아야 한다(shard_targets.py 가 순위로 나눈다). 겹치면 같은 패키지가 상태 표에
    # 두 행으로 남아 합계가 틀어지므로, 조용히 넘어가지 않고 여기서 멈춘다.
    n_task, n_name = con.execute("SELECT count(*), count(DISTINCT name) FROM ck_tasks").fetchone()
    assert n_task == n_name, (
        f"샤드 대상이 겹친다: 작업 {n_task}건 중 이름 {n_name}개. --raw 로 준 run 폴더를 확인할 것")
    # read_json 결과를 바로 v 로 만든다(raw 를 따로 물질화하면 2,000만 행 기준 메모리가 두 배, 약 32 GB).
    # 같은 (Name, Version) 이 여러 번 받혔으면(재시작 중복·재시도) 가장 최근 fetched_at 만 남긴다.
    # 시각 문자열은 ISO 8601(Z 포함) → TIMESTAMPTZ 로 읽어 UTC 기준 TIMESTAMP 로 저장.
    # 정규화 두 가지(수집기도 같은 규칙이고, 09-09 raw 처럼 이전 규칙으로 쌓인 것도 여기서 맞춘다):
    #   - Version 이 semver 모양이 아닌 행은 time 의 비버전 키에서 생긴 가짜 버전이라 버린다.
    #   - deprecated 의 'false'·''(불리언 false·문구 없음)는 '폐기 아님' 이므로 NULL 로 바꾼다.
    #   - unpublish 행의 의존 네 열은 NULL(모름)로 강제한다. []('없음')로 두면 lag() 에서 '의존 전부 제거'가 된다.
    con.execute(
        rf"""CREATE TABLE v AS
       SELECT Name, Version,
              try_cast(published_at AS TIMESTAMPTZ) AT TIME ZONE 'UTC' AS published_at, rank,
              CASE WHEN unpublished THEN NULL ELSE Dependencies END AS Dependencies,
              CASE WHEN unpublished THEN NULL ELSE DevDependencies END AS DevDependencies,
              CASE WHEN unpublished THEN NULL ELSE PeerDependencies END AS PeerDependencies,
              CASE WHEN unpublished THEN NULL ELSE OptionalDependencies END AS OptionalDependencies,
              CASE WHEN deprecated IN ('false', '') THEN NULL ELSE deprecated END AS deprecated, unpublished,
              unpacked_size, file_count, module_type, main, types, exports,
              try_cast(fetched_at AS TIMESTAMPTZ) AT TIME ZONE 'UTC' AS fetched_at,
              try_cast(modified AS TIMESTAMPTZ) AT TIME ZONE 'UTC' AS modified
       FROM read_json({[_p(f) for f in files]!r}, format='newline_delimited',
            columns={{'Name':'VARCHAR','Version':'VARCHAR','published_at':'VARCHAR','rank':'INTEGER',
                     'Dependencies':'{DEP}','DevDependencies':'{DEP}','PeerDependencies':'{DEP}','OptionalDependencies':'{DEP}',
                     'deprecated':'VARCHAR','unpublished':'BOOLEAN',
                     'unpacked_size':'BIGINT','file_count':'BIGINT','module_type':'VARCHAR','main':'VARCHAR',
                     'types':'VARCHAR','exports':'VARCHAR',
                     'fetched_at':'VARCHAR','modified':'VARCHAR'}})
       WHERE regexp_matches(Version, '^\d+\.\d+')
         AND Name IN (SELECT name FROM ck_tasks WHERE status IN ('done', 'unpublished'))
       QUALIFY row_number() OVER (PARTITION BY Name, Version ORDER BY fetched_at DESC) = 1"""
    )

    # 요청은 했지만 버전 행이 없는 NOT_FOUND·UNPUBLISHED·FAILED 도 한 행씩 남긴다.
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
       FROM ck_tasks t
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
    with open(os.path.join(tmp, "registry_source.json"), "w", encoding="utf-8") as f:
        json.dump({"raw": raw_abs, "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}, f, ensure_ascii=False)

    outv = os.path.join(a.out, "registry_versions")
    old = outv + ".old"
    if os.path.isdir(old):
        shutil.rmtree(old)
    if os.path.isdir(outv):
        os.rename(outv, old)   # 지운 뒤 교체하면 그 사이 출력 폴더가 비어 보인다. 옆으로 치우고 바로 교체한다
    os.replace(os.path.join(tmp, "registry_versions"), outv)
    os.replace(os.path.join(tmp, "registry_status.parquet"), os.path.join(a.out, "registry_status.parquet"))
    os.replace(os.path.join(tmp, "registry_source.json"), marker)
    if os.path.isdir(old):
        shutil.rmtree(old)
    shutil.rmtree(tmp)

    n_v, n_pkg, n_unpub, n_dev, n_size, n_exp, n_types = con.execute(
        "SELECT count(*), count(DISTINCT Name), count(*) FILTER (WHERE unpublished), "
        "count(*) FILTER (WHERE len(DevDependencies) > 0), count(*) FILTER (WHERE unpacked_size IS NOT NULL), "
        "count(*) FILTER (WHERE exports IS NOT NULL), count(*) FILTER (WHERE types IS NOT NULL) FROM v"
    ).fetchone()
    n_st = con.execute("SELECT count(*) FROM st").fetchone()[0]
    by = dict(con.execute("SELECT status, count(*) FROM st GROUP BY status ORDER BY status").fetchall())
    con.close()
    print(f"[to_parquet] registry_versions rows={n_v} packages={n_pkg} unpublished_versions={n_unpub} rows_with_devDeps={n_dev} "
          f"| registry_status rows={n_st} {by} -> {a.out}")
    if n_v:
        print(f"[to_parquet] 형태 6열 채움: unpacked_size {n_size:,}({n_size/n_v:.1%}) "
              f"exports {n_exp:,}({n_exp/n_v:.1%}) types {n_types:,}({n_types/n_v:.1%})")


if __name__ == "__main__":
    main()
