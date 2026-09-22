"""버전별 소비 조건 parquet — package_env 원천 (기능-11-R01, S15P21A506-366 수집분).

입력  pickage-raw/npm-registry/v1/collected_date=<날짜>/run_id=<회차>/
        data/shard=sN/part-*.jsonl.gz    한 줄 = 패키지 × 버전
        run_manifest.json                받을 목록과 파일별 sha256
        _SUCCESS                         완료 표시
출력  data/package_env/package_env.parquet
        Name, Version, module_format, types_bundled, direct_dependencies, peer_dependencies

    python -m pipeline.duckdb.build_package_env \\
      --collected-date 2026-09-16 --run-id registry-20260916-v1

**회차를 여럿 줄 수 있다.** 대상 목록을 나눠 여러 번에 걸쳐 수집했으면 한 표를 만들려고
둘 이상을 같이 읽어야 한다. `--collected-date` 와 `--run-id` 를 같은 수만큼 반복해 적으면
앞에서부터 짝지어진다 (S15P21A506-452: 상위 10만 + 추가분 36.9만 = 46.9만).

    python -m pipeline.duckdb.build_package_env \\
      --collected-date 2026-09-16 --run-id registry-20260916-v1 \\
      --collected-date 2026-09-22 --run-id registry-20260922-additions-v1

회차가 둘 이상이면 `(Name, Version)` 이 겹치는지 보고 겹치면 멈춘다. `package_env` 의 PK 가
`(package_id, version)` 이라 그냥 두면 적재에서 막히는데, 그때는 어느 회차가 겹쳤는지
알아내기가 훨씬 번거롭다. 회차가 하나면 이 검사를 하지 않는다 — 수집기 체크포인트의 PK 가
패키지 이름이라 한 회차 안에서는 겹칠 수 없고, 검사 비용만 든다.

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
        -- JSON 열이라 SQL NULL 과 JSON null 둘 다 올 수 있다. 길이를 물으면
        -- 배열이 아닌 것은 전부 NULL 이 되어 한 번에 걸러진다.
        WHEN json_array_length(Dependencies) IS NULL
             AND json_array_length(PeerDependencies) IS NULL THEN 'UNKNOWN'
        WHEN {DUAL} THEN 'ESM_CJS'
        WHEN module_type = 'module' THEN 'ESM_ONLY'
        ELSE 'CJS'
    END AS module_format,
    (types IS NOT NULL AND types <> '') AS types_bundled,
    json_array_length(Dependencies) AS direct_dependencies,
    json_array_length(PeerDependencies) AS peer_dependencies
FROM raw
"""


# 요청한 회차의 manifest 가 맞는지 본다. 경로만 믿으면 객체를 손으로 옮겨 놓았을 때 못 잡는다.
def check_manifest(manifest: dict, collected_date: str, run_id: str) -> list[dict]:
    if manifest.get('status') != 'PASSED':
        raise SystemExit(f"입고가 통과되지 않은 회차다: status={manifest.get('status')}")
    for key, want in (('source', 'registry'), ('collected_date', collected_date),
                      ('run_id', run_id)):
        if manifest.get(key) != want:
            raise SystemExit(f'manifest 의 {key} 가 다르다: {manifest.get(key)} (기대 {want})')
    files = [f for f in manifest.get('files', []) if f.get('key', '').endswith('.jsonl.gz')]
    if not files or len(files) != manifest.get('file_count'):
        raise SystemExit(f"manifest 의 file_count({manifest.get('file_count')})와 "
                         f'목록({len(files)})이 다르다')
    print(f"  회차 확인 · part {len(files)}개 · {manifest.get('bytes', 0) / 1e6:.0f} MB")
    return files


# 샤드가 다 있는지 본다. 하나가 빠져도 오류가 안 나고 원본의 1/4 이 조용히 사라진다.
def check_shards(keys: list[str], manifest: dict) -> None:
    found = {int(m.group(1)) for k in keys if (m := SHARD.search(k))}
    if not found:
        if manifest.get('shards'):
            raise SystemExit(f"manifest 는 샤드 {manifest['shards']}개라는데 경로에 shard= 가 없다")
        return  # 분할하지 않은 회차
    if found != set(range(1, max(found) + 1)):
        raise SystemExit(f'샤드가 빠졌다: 있는 것 {sorted(found)}')
    if manifest.get('shards') not in (None, len(found)):
        raise SystemExit(f"샤드 수가 manifest 와 다르다: {len(found)} vs {manifest['shards']}")
    print(f'  샤드 {len(found)}개')


# MinIO 에서 회차를 받아 로컬에 둔다. 크기가 같은 파일은 다시 받지 않는다.
def pull_run(s3, collected_date: str, run_id: str) -> Path:
    from pipeline.minio.ingest_raw import exists

    prefix = f'{PREFIX}/collected_date={collected_date}/run_id={run_id}'
    # 입고기가 모든 검사(수집기 manifest 의 final·pending, 샤드 1..N, 객체별 sha256)를
    # 통과한 뒤에만 이 표시를 쓴다. 이것이 없으면 덜 올라간 회차다.
    if not exists(s3, BUCKET, f'{prefix}/_SUCCESS'):
        raise SystemExit(f'완료 표시가 없다: s3://{BUCKET}/{prefix}/_SUCCESS\n'
                         '입고가 끝나지 않았거나 회차 이름이 틀렸다')

    target = CACHE / f'collected_date={collected_date}' / f'run_id={run_id}'
    target.mkdir(parents=True, exist_ok=True)

    body = s3.get_object(Bucket=BUCKET, Key=f'{prefix}/run_manifest.json')['Body'].read()
    manifest = json.loads(body)
    # 받을 목록을 manifest 에서 가져온다. 버킷을 훑어 얻으면 그 사이 지워진 객체를
    # 알아챌 수 없다 — manifest 가 "이만큼이 있어야 한다" 를 말한다.
    files = check_manifest(manifest, collected_date, run_id)
    keys = [f['key'] for f in files]
    check_shards(keys, manifest)

    got = 0
    for entry in sorted(files, key=lambda f: f['key']):
        key = entry['key']
        path = target / key[len(prefix) + 1:]
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_file() and path.stat().st_size == entry['bytes']:
            continue
        temporary = path.with_suffix(path.suffix + '.part')
        s3.download_file(BUCKET, key, str(temporary))
        temporary.replace(path)  # 중간에 끊긴 파일을 완성본으로 오인하지 않게 한다
        got += 1
        if got % 200 == 0:
            print(f'    {got}개 받음', flush=True)
    print(f'  part {len(keys)}개 (새로 받은 것 {got}개)')
    return target


# 받은 part 가 끝까지 읽히는지 본다. 잘린 gz 를 DuckDB 에 넘기면 어디서 멈췄는지 안 알려 준다.
def check_parts(targets: list[Path]) -> int:
    parts = []
    for target in targets:
        found = sorted(target.rglob('part-*.jsonl.gz'))
        # 회차가 여럿이면 폴더 이름을 잘못 적는 실수가 현실적으로 생긴다. 비어 있는 채로
        # 넘어가면 그 회차만 조용히 빠진 표가 나오거나 build 가 IndexError 로 죽는데,
        # 둘 다 어느 폴더가 문제인지 말해 주지 않는다.
        if not found:
            raise SystemExit(f'part 파일이 없다: {target} — 회차 폴더 이름을 확인할 것')
        parts += found
    for path in parts:
        try:
            with gzip.open(path, 'rb') as f:
                while f.read(1 << 20):
                    pass
        except (EOFError, OSError) as error:
            raise SystemExit(f'gz 가 온전하지 않다: {path} ({error})')
    return len(parts)


# 판정해서 parquet 으로 쓰고 분포를 찍는다.
def build(targets: list[Path], out: Path, memory: str) -> int:
    import duckdb

    globs = [(target / '**' / 'part-*.jsonl.gz').as_posix() for target in targets]
    # 상대 경로로 받으면 아래 relative_to 가 ValueError 를 낸다. parquet 을 다 쓰고 나서
    # 통계를 찍다가 죽으므로 산출물은 멀쩡한데 분포를 못 본다. 여기서 절대 경로로 맞춘다.
    # resolve() 가 아니라 absolute() 다 — 작업 트리의 data/ 가 주 트리를 가리키는
    # 정션일 때 resolve() 는 링크를 풀어 리포 밖 경로로 바꿔 버리고, 그러면 같은
    # 자리에서 또 죽는다.
    out = out.absolute()
    out.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()

    # 정렬이 상한을 넘으면 여기로 흘린다. 없으면 그 자리에서 죽는다.
    temp = out.parent / 'tmp'
    temp.mkdir(exist_ok=True)
    con.execute(f"SET memory_limit='{memory}'")
    con.execute(f"SET temp_directory='{temp.as_posix()}'")
    con.execute('SET preserve_insertion_order=false')

    # 6열이 있는 회차인지 파일 하나로 본다. 전체를 추론시키면 4,000개 파일의 스키마를
    # 한꺼번에 들고 있어야 해서 읽기도 전에 메모리가 터진다 (실측: 988 MB 회차에서 OOM).
    #
    # **회차마다 본다.** 첫 회차만 보고 넘어가면 09-16 뒤에 09-09 를 붙였을 때 앞의 것만
    # 통과하고, 뒤 회차의 행은 여섯 열이 전부 NULL 인 채 섞여 들어간다. 그러면 그 패키지들이
    # 통째로 CJS·타입 없음으로 떨어지는데, 오류가 아니라 값으로 보여서 아무도 못 알아챈다.
    for target in targets:
        first = sorted(target.rglob('part-*.jsonl.gz'))[0]
        sample = {r[0] for r in con.execute(
            f"DESCRIBE SELECT * FROM read_json_auto('{first.as_posix()}')").fetchall()}
        missing = [c for c in ('module_type', 'types', 'exports') if c not in sample]
        if missing:
            raise SystemExit(f'형태 6열이 없는 회차다: {target} 에 {missing} 없음. '
                             '09-16 이후 회차를 쓸 것')

    # 열을 못 박는다. 추론을 안 시키려는 것이고, 쓰지 않는 열(DevDependencies·
    # unpacked_size·deprecated 등)은 아예 읽지 않아 그만큼 덜 든다.
    #
    # 의존 배열은 STRUCT 로 펼치지 않고 JSON 으로 둔다 — 개수만 세면 되는데 2,000만 행의
    # 배열을 통째로 구조체로 만들 이유가 없다.
    #
    # exports 만 VARCHAR 다. 원문에서 이 값은 JSON 객체가 아니라 **JSON 텍스트를 담은
    # 문자열**이라(수집기가 그렇게 적는다), JSON 으로 읽으면 한 겹 더 이스케이프돼
    # "import" 가 \"import\" 가 된다. 그러면 듀얼 판정이 한 건도 안 잡힌다 —
    # 실측으로 5,000행에서 11건이 0건이 됐다.
    sources = ', '.join(f"'{g}'" for g in globs)
    con.execute(f"""CREATE VIEW raw AS SELECT * FROM read_json([{sources}],
        format='newline_delimited',
        columns={{
            'Name': 'VARCHAR', 'Version': 'VARCHAR',
            'Dependencies': 'JSON', 'PeerDependencies': 'JSON',
            'module_type': 'VARCHAR', 'types': 'VARCHAR', 'exports': 'VARCHAR'
        }})""")

    con.execute(f"CREATE VIEW judged AS {JUDGE}")
    con.execute(f"""COPY (SELECT * FROM judged ORDER BY Name, Version)
                    TO '{out.as_posix()}' (FORMAT PARQUET, COMPRESSION zstd)""")

    # 회차를 여럿 읽었을 때만 본다. 한 회차 안에서는 수집기 체크포인트의 PK 가 패키지
    # 이름이라 겹칠 수 없어서, 회차가 하나면 2,000만 행 GROUP BY 를 공짜로 하지 않는다.
    # 정렬해 쓴 parquet 을 다시 읽는다 — judged 를 한 번 더 판정하는 것보다 싸다.
    if len(targets) > 1:
        dups = con.execute(f"""SELECT count(*) FROM (
            SELECT 1 FROM read_parquet('{out.as_posix()}')
            GROUP BY Name, Version HAVING count(*) > 1)""").fetchone()[0]
        if dups:
            raise SystemExit(
                f'(Name, Version) 이 {dups:,} 쌍 겹친다. 회차 둘이 같은 패키지를 담고 있다 — '
                'package_env 의 PK 가 (package_id, version) 이라 적재에서 막힌다. '
                '회차 선택을 확인할 것')

    rows = con.execute('SELECT count(*) FROM judged').fetchone()[0]
    # 표시일 뿐이라 여기서 죽지 않게 한다. --out 을 리포 밖으로 줄 수도 있다.
    try:
        shown = out.relative_to(ROOT)
    except ValueError:
        shown = out
    print(f'\n  {rows:,} 행 -> {shown}'
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
    # 회차를 여럿 주려면 둘을 같은 수만큼 반복한다. 앞에서부터 짝지어진다.
    parser.add_argument('--collected-date', action='append', default=[], metavar='날짜',
                        help='예: 2026-09-16. --run-id 와 같은 수만큼 반복할 수 있다')
    parser.add_argument('--run-id', action='append', default=[], metavar='회차',
                        help='예: registry-20260916-v1')
    parser.add_argument('--raw', type=Path, nargs='+', metavar='폴더',
                        help='이미 받아 둔 회차 폴더들. 주면 MinIO 를 보지 않는다')
    parser.add_argument('--out', type=Path, default=OUT)
    parser.add_argument('--memory', default='6GB',
                        help='DuckDB 상한. 넘으면 --out 옆 tmp/ 로 흘린다')
    args = parser.parse_args(argv)
    # 짝이 어긋나면 zip 이 조용히 짧은 쪽에서 끊는다. 회차 하나가 소리 없이 빠지는 것이
    # 이 파이프라인에서 가장 비싼 실수라 여기서 막는다.
    if len(args.collected_date) != len(args.run_id):
        parser.error(f'--collected-date 가 {len(args.collected_date)}개, '
                     f'--run-id 가 {len(args.run_id)}개다. 같은 수여야 짝이 맞는다')
    if not args.raw and not args.collected_date:
        parser.error('--collected-date 와 --run-id 짝, 또는 --raw 중 하나는 있어야 한다')
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.raw:
        targets = list(args.raw)
        print(f'  받아 둔 폴더 {len(targets)}개를 그대로 쓴다. 완료 확인을 건너뛴다')
    else:
        from pipeline.minio.ingest_raw import client
        s3 = client()
        targets = [pull_run(s3, date, run_id)
                   for date, run_id in zip(args.collected_date, args.run_id)]

    print(f'  part 검사 {check_parts(targets)}개 모두 온전함')
    build(targets, args.out, args.memory)
    return 0


if __name__ == '__main__':
    sys.exit(main())
