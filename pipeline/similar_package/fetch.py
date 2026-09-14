"""유사도 배치의 입력을 MinIO 에서 로컬로 내려받는다 (입력 잡).

    python -m pipeline.similar_package.fetch --run 2026-09-15 --work data/similarity

배치 컨테이너(`ai/similarity`)는 s3 클라이언트가 없다. 로컬 경로만 받아 계산한다.
그래서 누군가 대신 받아 로컬에 놔 줘야 하고, 그게 이 모듈이다.

받는 것 셋:

    package_text.parquet    pickage-curated/package_text/run=<run>/
    ONNX 모델 디렉터리        pickage-mlflow-artifacts/onnx_bge_v7/
    text_hash_state.parquet  (선택) 직전 실행 출력 — 증분 재임베딩용

끝나면 배치에 넘길 명령을 출력한다.

접속 정보는 `pipeline/minio/ingest_raw.py` 의 `client()` 를 그대로 쓴다
(`pipeline/minio/.env`, 서버는 `PICKAGE_MINIO_ENV=.env.server`).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys

from botocore.exceptions import ClientError

from pipeline.minio.ingest_raw import client

CURATED_BUCKET = "pickage-curated"
MODEL_BUCKET = "pickage-mlflow-artifacts"
PACKAGE_TEXT_PREFIX = "package_text"
# ai/MODEL_CONTRACT.md — 계약 경로(models/similar-packages/vN/)가 아니라 실제 업로드 위치다.
# v6 과 달리 model.onnx.data 가 없다. 단일 파일.
MODEL_PREFIX = "onnx_bge_v7"
MODEL_FILES = ("model.onnx", "tokenizer.json", "tokenizer_config.json")
MODEL_OPTIONAL = ("run_manifest.json",)
RUN_PATTERN = re.compile(r"[0-9A-Za-z_.-]{1,64}\Z")

# 배치가 없으면 죽거나 결과가 0이 되는 컬럼.
REQUIRED_COLUMNS = ("name", "description", "keywords", "dependent_packages_count")
# 없어도 배치는 돌지만 그 검사만 조용히 무효가 되는 컬럼.
EXPECTED_COLUMNS = ("latest_release_published_at", "status", "is_spam", "repo_archived")
DEPRECATED_STATUSES = {"deprecated", "removed", "unpublished"}


def log(message: str) -> None:
    print(message, flush=True)


def _get(s3, bucket: str, key: str) -> bytes | None:
    try:
        with s3.get_object(Bucket=bucket, Key=key)["Body"] as stream:
            return stream.read()
    except ClientError as error:
        if error.response["Error"]["Code"] in ("NoSuchKey", "404"):
            return None
        raise


def _download(s3, bucket: str, key: str, target: Path) -> int:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".part")
    s3.download_file(bucket, key, str(temporary))
    temporary.replace(target)  # 중간에 끊긴 파일을 완성본으로 오인하지 않게 한다
    size = target.stat().st_size
    log(f"  {key}  →  {target}  ({size / 1e6:.1f} MB)")
    return size


def _list(s3, bucket: str, prefix: str) -> list[str]:
    keys, token = [], None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        page = s3.list_objects_v2(**kwargs)
        keys += [item["Key"] for item in page.get("Contents", [])]
        if not page.get("IsTruncated"):
            return keys
        token = page.get("NextContinuationToken")


# ── package_text ────────────────────────────────────────────────────────

def fetch_package_text(s3, run: str, work: Path) -> tuple[Path, dict]:
    """게시가 끝난 run 인지 확인하고 parquet 을 받는다.

    `_SUCCESS` 는 빈 파일이 아니라 manifest 의 sha256 을 담는다
    (`pipeline/postgresql/input.py` 의 curated 승인 방식과 같다). 마커만 있고
    내용이 어긋나면 게시 도중이거나 파일이 바뀐 것이므로 받지 않는다.
    """
    prefix = f"{PACKAGE_TEXT_PREFIX}/run={run}"
    marker = _get(s3, CURATED_BUCKET, f"{prefix}/_SUCCESS")
    if marker is None:
        raise SystemExit(f"완료 마커가 없다: s3://{CURATED_BUCKET}/{prefix}/_SUCCESS\n"
                         "아직 게시 중이거나 run 이름이 틀렸다")
    body = _get(s3, CURATED_BUCKET, f"{prefix}/run_manifest.json")
    if body is None:
        raise SystemExit(f"run_manifest.json 이 없다: s3://{CURATED_BUCKET}/{prefix}/")

    expected = hashlib.sha256(body).hexdigest()
    try:
        marker_json = json.loads(marker or b"{}")
    except json.JSONDecodeError:
        marker_json = None
    if marker_json is None:
        # 게시 쪽이 아직 빈 마커를 쓴다면 해시 대조를 못 한다. 막지는 않되 남긴다.
        log("  경고: _SUCCESS 에 manifest_sha256 이 없다 — 내용 검증을 건너뛴다")
    elif marker_json != {"manifest_sha256": expected}:
        raise SystemExit("_SUCCESS 와 run_manifest.json 이 어긋난다 — 게시가 끝나지 않았거나 파일이 바뀌었다")

    manifest = json.loads(body)
    log(f"package_text run={run}  (manifest rows={manifest.get('rows', '?')})")

    keys = [k for k in _list(s3, CURATED_BUCKET, prefix + "/") if k.endswith(".parquet")]
    if not keys:
        raise SystemExit(f"parquet 이 없다: s3://{CURATED_BUCKET}/{prefix}/")

    target_dir = work / "package_text"
    if len(keys) == 1:
        # 파일 하나면 파일 경로를 그대로 배치에 넘긴다.
        target = work / "package_text.parquet"
        _download(s3, CURATED_BUCKET, keys[0], target)
    else:
        # Spark 로 쓰면 part-*.parquet 여러 개다. 배치는 pyarrow 로 디렉터리째 읽는다.
        for key in keys:
            _download(s3, CURATED_BUCKET, key, target_dir / Path(key).name)
        target = target_dir
    (work / "package_text_manifest.json").write_bytes(body)
    return target, manifest


# ── 모델 ────────────────────────────────────────────────────────────────

def fetch_model(s3, work: Path) -> Path:
    target = work / MODEL_PREFIX
    log(f"모델 {MODEL_PREFIX}")
    for name in MODEL_FILES:
        key = f"{MODEL_PREFIX}/{name}"
        try:
            _download(s3, MODEL_BUCKET, key, target / name)
        except ClientError as error:
            raise SystemExit(f"모델 파일이 없다: s3://{MODEL_BUCKET}/{key} ({error})")
    for name in MODEL_OPTIONAL:
        try:
            _download(s3, MODEL_BUCKET, f"{MODEL_PREFIX}/{name}", target / name)
        except ClientError:
            # run_manifest.json 이 없으면 배치가 model_ver 을 "unknown" 으로 넣고,
            # 적재기가 그걸 거부한다. 미리 알려 준다.
            log(f"  경고: {name} 이 없다 — model_ver 이 unknown 이 되어 적재가 거부된다")
    return target


# ── state (선택) ────────────────────────────────────────────────────────

def fetch_state(s3, bucket: str, key: str, work: Path) -> Path | None:
    """직전 실행의 text_hash_state.parquet.

    ⚠ 현재 배치는 이 파일을 읽지 못한다. `write_output` 은 {name, text_hash} 만 쓰는데
    `load_state` 는 vector 컬럼을 요구해 KeyError 로 죽는다. 고쳐지기 전까지는
    --state-key 를 주지 말 것 (전수 재임베딩, 10만 건 약 20분).
    """
    target = work / "text_hash_state.parquet"
    try:
        _download(s3, bucket, key, target)
    except ClientError:
        log(f"  직전 상태 없음 ({key}) — 전수 재임베딩한다")
        return None
    log("  경고: 현재 배치는 --state 를 읽지 못한다 (load_state 가 vector 컬럼을 요구)")
    return target


# ── 프리플라이트 ────────────────────────────────────────────────────────

def preflight(path: Path, manifest: dict, min_dependents: int, max_age_months: int) -> dict:
    """배치에 넘기기 전에 parquet 을 훑어 본다.

    배치는 모든 컬럼을 `.get()` 으로 읽는다. 컬럼이 통째로 빠져도 에러 없이 돌고
    그 검사만 무효가 된다 — `is_spam` 이 없으면 스팸이 전부 통과하고,
    `repo_archived` 가 없으면 보관 저장소 관문이 사라진다. 결과가 나빠질 뿐
    아무도 이유를 모른다. 그래서 넘기기 전에 여기서 본다.

    필수 컬럼 누락과 manifest 행 수 불일치는 중단. 나머지는 숫자만 남긴다.
    매주 같은 숫자를 비교하면 입력이 언제 달라졌는지 보인다.
    """
    import pyarrow.dataset as pads

    dataset = pads.dataset(str(path), format="parquet")
    names = set(dataset.schema.names)

    missing_required = [c for c in REQUIRED_COLUMNS if c not in names]
    if missing_required:
        raise SystemExit(f"필수 컬럼이 없다: {', '.join(missing_required)}\n"
                         "배치는 에러 없이 돌지만 결과가 비거나 무의미해진다")
    missing_expected = [c for c in EXPECTED_COLUMNS if c not in names]
    for column in missing_expected:
        log(f"  경고: {column} 컬럼이 없다 — 이 검사가 조용히 무효가 된다")

    columns = [c for c in REQUIRED_COLUMNS + EXPECTED_COLUMNS if c in names]
    cutoff = dt.date.today() - dt.timedelta(days=int(max_age_months * 30.44))
    seen: set[str] = set()
    stat = dict.fromkeys(
        ("rows", "duplicate_names", "null_name", "null_description", "empty_keywords",
         "null_dependents", "is_spam", "repo_archived", "deprecated_status", "qualified"), 0)

    for batch in dataset.to_batches(columns=columns):
        block = {c: batch.column(c).to_pylist() for c in columns}
        for i in range(batch.num_rows):
            stat["rows"] += 1
            name = block["name"][i]
            if name is None:
                stat["null_name"] += 1
            elif name in seen:
                stat["duplicate_names"] += 1
            else:
                seen.add(name)

            if block["description"][i] is None or not str(block["description"][i]).strip():
                stat["null_description"] += 1
            if not (block["keywords"][i] or []):
                stat["empty_keywords"] += 1

            dependents = block["dependent_packages_count"][i]
            if dependents is None:
                stat["null_dependents"] += 1

            status = (block.get("status", [None] * batch.num_rows)[i] or "").lower()
            if status in DEPRECATED_STATUSES:
                stat["deprecated_status"] += 1
            spam = bool(block.get("is_spam", [None] * batch.num_rows)[i])
            if spam:
                stat["is_spam"] += 1
            if block.get("repo_archived", [None] * batch.num_rows)[i]:
                stat["repo_archived"] += 1

            # 배치의 qualify() 와 같은 조건. 실제로 임베딩될 행 수를 미리 본다.
            released = block.get("latest_release_published_at", [None] * batch.num_rows)[i]
            if isinstance(released, (dt.datetime,)):
                released = released.date()
            elif isinstance(released, str):
                try:
                    released = dt.date.fromisoformat(released[:10])
                except ValueError:
                    released = None
            elif not isinstance(released, dt.date):
                released = None
            if (dependents is not None and dependents >= min_dependents
                    and (released is None or released >= cutoff)
                    and status not in DEPRECATED_STATUSES and not spam):
                stat["qualified"] += 1

    expected_rows = manifest.get("rows") or manifest.get("row_count")
    if isinstance(expected_rows, int) and expected_rows != stat["rows"]:
        raise SystemExit(f"행 수가 manifest 와 다르다: manifest {expected_rows} vs 실제 {stat['rows']}")

    stat["missing_columns"] = missing_expected
    rows = stat["rows"] or 1
    log("")
    log("프리플라이트")
    log(f"  행 수            {stat['rows']:,}")
    log(f"  자격 통과 예상    {stat['qualified']:,}  ({stat['qualified'] / rows:.1%})"
        f"  [dependents>={min_dependents}, 최근 {max_age_months}개월]")
    log(f"  name 중복        {stat['duplicate_names']:,}")
    log(f"  description 없음  {stat['null_description']:,}  ({stat['null_description'] / rows:.1%})")
    log(f"  keywords 없음     {stat['empty_keywords']:,}  ({stat['empty_keywords'] / rows:.1%})")
    log(f"  dependents NULL   {stat['null_dependents']:,}")
    log(f"  deprecated       {stat['deprecated_status']:,}")
    log(f"  is_spam          {stat['is_spam']:,}")
    log(f"  repo_archived    {stat['repo_archived']:,}")

    if stat["duplicate_names"]:
        # 이름이 배치의 증분 상태 키이자 적재기의 조인 키다. 중복은 조용히 틀어진다.
        raise SystemExit(f"name 이 {stat['duplicate_names']} 건 중복이다 — 생성 쪽 중복 제거 확인")
    if stat["qualified"] == 0:
        raise SystemExit("자격을 통과하는 행이 하나도 없다 — 배치가 즉시 중단된다")
    if stat["null_description"] / rows > 0.5:
        # 빈 description 은 'DESCRIPTION:  / KEYWORDS: ' 가 되어 내용 없는 벡터를 만든다.
        # 그런 것끼리 서로 유사하다고 나온다. 막지는 않되 눈에 띄게 남긴다.
        log("  경고: description 이 절반 이상 비어 있다 — 임베딩 품질이 크게 떨어진다")
    return stat


# ── main ────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, help="package_text 의 run 이름 (예: 2026-09-15)")
    parser.add_argument("--work", type=Path, default=Path("data/similarity"),
                        help="받은 파일을 놓을 상위 디렉터리. 실제 경로는 <work>/<run>/")
    parser.add_argument("--state-key", default=None,
                        help="직전 실행의 text_hash_state.parquet s3 키 (pickage-vectors). "
                             "생략하면 전수 재임베딩")
    parser.add_argument("--state-bucket", default="pickage-vectors")
    parser.add_argument("--min-dependents", type=int, default=5,
                        help="프리플라이트의 자격 통과 예상 계산용. 배치 기본값과 맞춘다")
    parser.add_argument("--max-age-months", type=int, default=12)
    parser.add_argument("--skip-preflight", action="store_true",
                        help="받기만 하고 내용 검사를 건너뛴다")
    args = parser.parse_args(argv)

    if not RUN_PATTERN.fullmatch(args.run):
        raise SystemExit("run 이름은 영문·숫자·점·밑줄·하이픈만 쓴다")

    work = (args.work / args.run).resolve()
    work.mkdir(parents=True, exist_ok=True)

    s3 = client()
    package_text, manifest = fetch_package_text(s3, args.run, work)
    model_dir = fetch_model(s3, work)
    state = fetch_state(s3, args.state_bucket, args.state_key, work) if args.state_key else None

    if not args.skip_preflight:
        stat = preflight(package_text, manifest, args.min_dependents, args.max_age_months)
        (work / "preflight.json").write_text(
            json.dumps(stat, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    out = work / "out"
    log("")
    log("받기 완료. 배치 실행 명령:")
    log("")
    log(f"  docker run --rm \\")
    log(f"    -v {work}:/work \\")
    log(f"    similarity-batch \\")
    log(f"    --package-text /work/{package_text.relative_to(work).as_posix()} \\")
    log(f"    --model-dir /work/{model_dir.relative_to(work).as_posix()} \\")
    if state:
        log(f"    --state /work/{state.relative_to(work).as_posix()} \\")
    log(f"    --out /work/out")
    log("")
    log(f"산출물은 {out} 에 생긴다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
