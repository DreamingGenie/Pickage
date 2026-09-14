"""배치 입력을 MinIO 에서 로컬로 내려받는다.

    python -m pipeline.similar_package.fetch --run 2026-09-15
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

try:  # Windows 콘솔 cp949 에서 한글 출력 보장
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

CURATED_BUCKET = "pickage-curated"        # TODO(팀 합의): build.py 와 같은 값이어야 한다
MODEL_BUCKET = "pickage-mlflow-artifacts"
PACKAGE_TEXT_PREFIX = "package_text"      # TODO(팀 합의): build.py 와 같은 값이어야 한다
# ai/MODEL_CONTRACT.md 의 v7 업로드 경로
MODEL_PREFIX = "onnx_bge_v7"
MODEL_FILES = ("model.onnx", "tokenizer.json", "tokenizer_config.json")
MODEL_OPTIONAL = ("run_manifest.json",)
RUN_PATTERN = re.compile(r"[0-9A-Za-z_.-]{1,64}\Z")

# 없으면 중단하는 컬럼
REQUIRED_COLUMNS = ("name", "description", "keywords", "dependent_packages_count")
# 없으면 경고만 하는 컬럼
EXPECTED_COLUMNS = ("latest_release_published_at", "status", "is_spam", "repo_archived")
DEPRECATED_STATUSES = {"deprecated", "removed", "unpublished"}


# 표준출력에 한 줄 남긴다.
def log(message: str) -> None:
    print(message, flush=True)


# 객체 하나를 읽는다. 없으면 None.
def _get(s3, bucket: str, key: str) -> bytes | None:
    try:
        with s3.get_object(Bucket=bucket, Key=key)["Body"] as stream:
            return stream.read()
    except ClientError as error:
        if error.response["Error"]["Code"] in ("NoSuchKey", "404"):
            return None
        raise


# 객체를 내려받는다. 받는 동안은 .part 로 두고 끝나면 이름을 바꾼다.
def _download(s3, bucket: str, key: str, target: Path) -> int:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".part")
    s3.download_file(bucket, key, str(temporary))
    temporary.replace(target)  # 중간에 끊긴 파일을 완성본으로 오인하지 않게 한다
    size = target.stat().st_size
    log(f"  {key}  →  {target}  ({size / 1e6:.1f} MB)")
    return size


# 접두사 아래 객체 키를 나열한다.
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


# 게시가 끝난 run 인지 확인하고 package_text parquet 을 받는다.
def fetch_package_text(s3, run: str, work: Path) -> tuple[Path, dict]:
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
        target = work / "package_text.parquet"
        _download(s3, CURATED_BUCKET, keys[0], target)
    else:
        # 여러 개면 디렉터리 경로를 넘긴다.
        for key in keys:
            _download(s3, CURATED_BUCKET, key, target_dir / Path(key).name)
        target = target_dir
    (work / "package_text_manifest.json").write_bytes(body)
    return target, manifest


# ONNX 모델 디렉터리를 받는다.
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
            log(f"  경고: {name} 이 없다 — model_ver 이 unknown 이 되어 적재가 거부된다")
    return target


# 직전 실행의 text_hash_state.parquet 을 받는다. 없으면 None.
def fetch_state(s3, bucket: str, key: str, work: Path) -> Path | None:
    target = work / "text_hash_state.parquet"
    try:
        _download(s3, bucket, key, target)
    except ClientError:
        log(f"  직전 상태 없음 ({key}) — 전수 재임베딩한다")
        return None
    log("  경고: 현재 배치는 --state 를 읽지 못한다 (load_state 가 vector 컬럼을 요구)")
    return target


# 받은 parquet 의 컬럼·행 수를 확인하고 품질 수치를 남긴다.
def preflight(path: Path, manifest: dict, min_dependents: int, max_age_months: int) -> dict:
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

            # 배치의 qualify() 와 같은 조건
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
        raise SystemExit(f"name 이 {stat['duplicate_names']} 건 중복이다 — 생성 쪽 중복 제거 확인")
    if stat["qualified"] == 0:
        raise SystemExit("자격을 통과하는 행이 하나도 없다 — 배치가 즉시 중단된다")
    if stat["null_description"] / rows > 0.5:
        log("  경고: description 이 절반 이상 비어 있다 — 임베딩 품질이 크게 떨어진다")
    return stat


# package_text·모델·상태를 받고 배치 실행 명령을 출력한다.
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
