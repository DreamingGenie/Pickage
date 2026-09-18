"""버전별 소비 조건 parquet — package_env 원천 (기능-11-R01, S15P21A506-366 수집분).

입력  pickage-raw/npm-registry/v1/collected_date=<날짜>/run_id=<회차>/
        data/shard=sN/part-*.jsonl.gz    한 줄 = 패키지 × 버전
        run_manifest.json                tasks_by_status 로 완료를 판단
출력  data/package_env/package_env.parquet
        Name, Version, module_format, types_bundled, direct_dependencies, peer_dependencies

    python -m pipeline.duckdb.build_package_env \\
      --collected-date 2026-09-16 --run-id registry-20260916-v1

**회차를 사람이 명시한다.** 최신 폴더를 자동으로 집지 않는다 — 형태 6열은 09-16 회차부터
들어갔고, 그 전 회차(09-09)에는 키 자체가 없어 전 행이 NULL 인 표가 조용히 만들어진다.
`pipeline/dependent_transitions/load.py` 가 `_current.json` 을 안 따라가는 것과 같은 이유다.

받은 raw 는 data/registry/raw/collected_date=<날짜>/ 에 남겨 두고 다음 실행에서 크기가
같으면 다시 받지 않는다.

## 판정은 여기서 하고 DB 에는 결과만 간다

`exports` 는 전수 기준 중앙값 179 B 인데 최대 2.69 MB(@dnb/eufemia 10.94.0)다. 그대로
싣고 다니면 행 하나가 페이지를 넘기므로 판정에만 쓰고 원문은 parquet 에도 두지 않는다.
규칙을 고쳐 다시 판정해야 하면 raw 가 MinIO 에 그대로 있으므로 여기서부터 다시 돌린다.

## module_format 판정 순서

    1. 의존 네 배열이 전부 NULL (unpublish)      -> UNKNOWN
    2. exports 에 "import" 와 "require" 가 둘 다  -> ESM_CJS
    3. module_type = 'module'                    -> ESM_ONLY
    4. 그 밖                                      -> CJS

`module_type` 이 NULL 인 것은 모름이 아니라 **commonjs 기본값**이다. 전수의 74.1% 가
NULL 이라 모름으로 읽으면 대부분이 UNKNOWN 이 되어 표가 아무 말도 못 한다.

듀얼을 `module_type` 보다 먼저 보는 이유는 양쪽을 다 내보내는 패키지가 `type` 을 module 로
적기도 하고 commonjs 로 적기도 해서다. 순서를 바꾸면 그런 것들이 ESM_ONLY 로 떨어져
CJS 프로젝트에서 못 쓰는 것처럼 보인다.

타입 전용(@types/*)은 값을 따로 두지 않았다. 6열만으로는 못 가른다 — `main` 이 없으면
npm 이 index.js 를 기본값으로 쓰므로 'main 없음' 이 'JS 없음' 이 아니다. 09-16 shard
5,000행에서 'main 없음 + types 있음' 으로 잡으면 1,963행 중 22행이 chalk·supports-color
처럼 런타임이 있는 패키지였다.

## 못 보는 것

`.mjs`/`.cjs` 확장자로 형식이 갈리는 패키지는 여기서 안 잡힌다. 파일 목록이 없어
`type` 과 `exports` 만 보기 때문이고, 오판이 아니라 관측 밖이다.
"""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
BUCKET = 'pickage-raw'
PREFIX = 'npm-registry/v1'
OUT = ROOT / 'data' / 'package_env' / 'package_env.parquet'
CACHE = ROOT / 'data' / 'registry' / 'raw'

SHARD = re.compile(r'/shard=s(\d+)/')

# 판정에서 exports 를 문자열로 본다. 조건 키는 따옴표째 "import" / "require" 로 나타나고,
# 서브경로 키는 "./import" 처럼 앞에 ./ 가 붙어 따옴표 바로 뒤에 오지 않는다. 그래서 값이
# 아주 클 수 있는 JSON 을 파싱하지 않고도 듀얼을 가른다.
DUAL = """(exports IS NOT NULL
           AND exports LIKE '%"import"%'
           AND exports LIKE '%"require"%')"""

JUDGE = f"""
SELECT
    Name,
    Version,
    CASE
        WHEN Dependencies IS NULL AND PeerDependencies IS NULL THEN 'UNKNOWN'
        WHEN {DUAL} THEN 'ESM_CJS'
        WHEN module_type = 'module' THEN 'ESM_ONLY'
        ELSE 'CJS'
    END AS module_format,
    (types IS NOT NULL AND types <> '') AS types_bundled,
    CASE WHEN Dependencies IS NULL THEN NULL
         ELSE len(Dependencies) END AS direct_dependencies,
    CASE WHEN PeerDependencies IS NULL THEN NULL
         ELSE len(PeerDependencies) END AS peer_dependencies
FROM raw
"""


# 회차가 끝난 것인지 manifest 로 확인한다. 남은 작업이 있으면 쓰다 만 패키지의 고아 행이 섞인다.
def check_manifest(manifest: dict) -> None:
    status = manifest.get('tasks_by_status') or {}
    if not status:
        raise SystemExit('run_manifest.json 에 tasks_by_status 가 없다. 회차 이름을 확인할 것')
    pending = status.get('pending', 0)
    if pending:
        raise SystemExit(f'수집이 끝나지 않았다: pending={pending} · {status}')
    print(f'  회차 상태 {status}')


# 샤드가 다 있는지 본다. 하나가 빠져도 오류가 안 나고 원본의 1/4 이 조용히 사라진다.
def check_shards(keys: list[str]) -> None:
    found = {int(m.group(1)) for k in keys if (m := SHARD.search(k))}
    if not found:
        return  # 분할하지 않은 회차
    if found != set(range(1, max(found) + 1)):
        raise SystemExit(f'샤드가 빠졌다: 있는 것 {sorted(found)}')
    print(f'  샤드 {len(found)}개')


# MinIO 에서 회차를 받아 로컬에 둔다. 크기가 같은 파일은 다시 받지 않는다.
def pull_run(s3, collected_date: str, run_id: str) -> Path:
    from pipeline.minio.ingest_raw import exists

    prefix = f'{PREFIX}/collected_date={collected_date}/run_id={run_id}'
    if not exists(s3, BUCKET, f'{prefix}/run_manifest.json'):
        raise SystemExit(f'회차가 없다: s3://{BUCKET}/{prefix}/run_manifest.json')

    target = CACHE / f'collected_date={collected_date}' / f'run_id={run_id}'
    target.mkdir(parents=True, exist_ok=True)

    body = s3.get_object(Bucket=BUCKET, Key=f'{prefix}/run_manifest.json')['Body'].read()
    check_manifest(json.loads(body))

    keys = []
    token = None
    while True:
        page = s3.list_objects_v2(Bucket=BUCKET, Prefix=f'{prefix}/data/',
                                  **({'ContinuationToken': token} if token else {}))
        keys += [o['Key'] for o in page.get('Contents', []) if o['Key'].endswith('.jsonl.gz')]
        token = page.get('NextContinuationToken')
        if not page.get('IsTruncated'):
            break
    if not keys:
        raise SystemExit(f'part 파일이 없다: s3://{BUCKET}/{prefix}/data/')
    check_shards(keys)

    got = 0
    for key in sorted(keys):
        path = target / key[len(prefix) + 1:]
        path.parent.mkdir(parents=True, exist_ok=True)
        size = s3.head_object(Bucket=BUCKET, Key=key)['ContentLength']
        if path.is_file() and path.stat().st_size == size:
            continue
        temporary = path.with_suffix(path.suffix + '.part')
        s3.download_file(BUCKET, key, str(temporary))
        temporary.replace(path)  # 중간에 끊긴 파일을 완성본으로 오인하지 않게 한다
        got += 1
    print(f'  part {len(keys)}개 (새로 받은 것 {got}개)')
    return target


# 받은 part 가 끝까지 읽히는지 본다. 잘린 gz 를 DuckDB 에 넘기면 어디서 멈췄는지 안 알려 준다.
def check_parts(target: Path) -> int:
    parts = sorted(target.rglob('part-*.jsonl.gz'))
    for path in parts:
        try:
            with gzip.open(path, 'rb') as f:
                while f.read(1 << 20):
                    pass
        except (EOFError, OSError) as error:
            raise SystemExit(f'gz 가 온전하지 않다: {path} ({error})')
    return len(parts)


# 판정해서 parquet 으로 쓰고 분포를 찍는다.
def build(target: Path, out: Path) -> int:
    import duckdb

    glob = (target / '**' / 'part-*.jsonl.gz').as_posix()
    out.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"CREATE VIEW raw AS SELECT * FROM read_json_auto('{glob}', union_by_name=true)")

    missing = [c for c in ('module_type', 'main', 'types', 'exports', 'unpacked_size')
               if c not in {r[0] for r in con.execute('DESCRIBE raw').fetchall()}]
    if missing:
        raise SystemExit(f'형태 6열이 없는 회차다: {missing} 없음. 09-16 이후 회차를 쓸 것')

    con.execute(f"CREATE VIEW judged AS {JUDGE}")
    con.execute(f"""COPY (SELECT * FROM judged ORDER BY Name, Version)
                    TO '{out.as_posix()}' (FORMAT PARQUET, COMPRESSION zstd)""")

    rows = con.execute('SELECT count(*) FROM judged').fetchone()[0]
    print(f'\n  {rows:,} 행 -> {out.relative_to(ROOT)}'
          f' ({out.stat().st_size / 1e6:.1f} MB)')
    print('\n  [module_format]')
    for value, n in con.execute(
            'SELECT module_format, count(*) FROM judged'
            ' GROUP BY 1 ORDER BY 2 DESC').fetchall():
        print(f'    {value:9s} {n:>10,}  {n * 100 / rows:5.1f}%')
    bundled, direct, peer = con.execute("""
        SELECT count(*) FILTER (WHERE types_bundled),
               count(*) FILTER (WHERE direct_dependencies > 0),
               count(*) FILTER (WHERE peer_dependencies > 0) FROM judged""").fetchone()
    print(f'\n  types_bundled       {bundled:>10,}  {bundled * 100 / rows:5.1f}%')
    print(f'  직접 의존 1개 이상  {direct:>10,}  {direct * 100 / rows:5.1f}%')
    print(f'  peer 1개 이상       {peer:>10,}  {peer * 100 / rows:5.1f}%')
    con.close()
    return rows


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--collected-date', required=True, help='예: 2026-09-16')
    parser.add_argument('--run-id', required=True, help='예: registry-20260916-v1')
    parser.add_argument('--raw', type=Path,
                        help='이미 받아 둔 회차 폴더. 주면 MinIO 를 보지 않는다')
    parser.add_argument('--out', type=Path, default=OUT)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.raw:
        target = args.raw
        manifest = target / 'run_manifest.json'
        if manifest.is_file():
            check_manifest(json.loads(manifest.read_text(encoding='utf-8')))
        else:
            print('  run_manifest.json 이 없다. 완료 확인을 건너뛴다')
    else:
        from pipeline.minio.ingest_raw import client
        target = pull_run(client(), args.collected_date, args.run_id)

    print(f'  part 검사 {check_parts(target)}개 모두 온전함')
    build(target, args.out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
