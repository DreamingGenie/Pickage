"""package_text 생성 — MinIO 원본 → Spark 변환 → MinIO 게시.

    python -m pipeline.similar_package.build --collected-date 2026-09-15 --publish
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import uuid

from botocore.exceptions import ClientError

from pipeline.minio.ingest_raw import client, digest
from pipeline.similar_package.docker_runtime import transform_docker

try:  # Windows 콘솔 cp949 에서 한글 출력 보장

    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

RAW_BUCKET = "pickage-raw"
RAW_PREFIX = "ecosystems-keywords/v1"
CURATED_BUCKET = "pickage-curated"        # TODO(팀 합의): fetch.py 와 같은 값이어야 한다
CURATED_PREFIX = "package_text"           # TODO(팀 합의): fetch.py 와 같은 값이어야 한다
DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,200}\Z")


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


# 하위 폴더 목록을 나열한다.
def _prefixes(s3, bucket: str, prefix: str) -> list[str]:
    result, token = [], None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": prefix, "Delimiter": "/"}
        if token:
            kwargs["ContinuationToken"] = token
        page = s3.list_objects_v2(**kwargs)
        result += [item["Prefix"] for item in page.get("CommonPrefixes", [])]
        if not page.get("IsTruncated"):
            return result
        token = page.get("NextContinuationToken")


# 완결 검증된 수집 run 하나를 고르고 manifest 를 돌려준다.
def select_run(s3, collected_date: str, run_id: str | None) -> dict:
    base = f"{RAW_PREFIX}/collected_date={collected_date}"
    runs = sorted(_prefixes(s3, RAW_BUCKET, base + "/"))
    if not runs:
        raise SystemExit(f"수집 run 이 없다: s3://{RAW_BUCKET}/{base}/")
    if run_id:
        wanted = f"{base}/run_id={run_id}/"
        if wanted not in runs:
            raise SystemExit(f"run_id 를 찾을 수 없다: {wanted}")
        prefix = wanted.rstrip("/")
    else:
        prefix = runs[-1].rstrip("/")
        if len(runs) > 1:
            log(f"run_id 가 {len(runs)} 개다. 최신을 쓴다: {prefix.rsplit('/', 1)[-1]}")

    if _get(s3, RAW_BUCKET, prefix + "/_SUCCESS") is None:
        raise SystemExit(f"완료 마커가 없다: s3://{RAW_BUCKET}/{prefix}/_SUCCESS")
    body = _get(s3, RAW_BUCKET, prefix + "/run_manifest.json")
    if body is None:
        raise SystemExit(f"run_manifest.json 이 없다: s3://{RAW_BUCKET}/{prefix}/")
    manifest = json.loads(body)
    if (manifest.get("contract_version") != 1 or manifest.get("status") != "PASSED"
            or manifest.get("verification") != "GET_SHA256_ALL_FILES"
            or manifest.get("collected_date") != collected_date):
        raise SystemExit("승인되지 않은 수집 manifest 다")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise SystemExit("manifest 에 파일 목록이 없다")
    for record in files:
        key = record.get("key")
        if not isinstance(key, str) or not key.startswith(prefix + "/data/"):
            raise SystemExit(f"manifest 의 파일이 이 run 소속이 아니다: {key}")
        if not re.fullmatch(r"[0-9a-f]{64}", record.get("sha256") or ""):
            raise SystemExit(f"sha256 이 올바르지 않다: {key}")
    log(f"수집 run 승인: {prefix}  files={len(files)} bytes={manifest.get('bytes')}")
    return {"prefix": prefix, "manifest": manifest, "manifest_sha256": hashlib.sha256(body).hexdigest(),
            "files": files, "collected_date": collected_date}


# 원본을 내려받고 manifest 의 sha256 과 대조한다.
def download_raw(s3, selected: dict, target: Path, workers: int) -> list[Path]:
    target.mkdir(parents=True, exist_ok=True)

    def fetch(record: dict) -> Path:
        path = target / Path(record["key"]).name
        if not path.exists() or path.stat().st_size != record.get("bytes"):
            temporary = path.with_suffix(path.suffix + ".part")
            s3.download_file(RAW_BUCKET, record["key"], str(temporary))
            temporary.replace(path)
        with path.open("rb") as stream:
            actual = digest(stream)
        if actual != record["sha256"]:
            raise SystemExit(f"체크섬이 다르다: {record['key']}")
        return path

    with ThreadPoolExecutor(max_workers=workers) as pool:
        paths = sorted(pool.map(fetch, selected["files"]))
    log(f"원본 {len(paths)} 개 내려받고 체크섬 확인")
    return paths


# 산출 parquet 과 manifest 를 올리고 마지막에 _SUCCESS 를 기록한다.
def publish(s3, run: str, outputs: Path, summary: dict, selected: dict, workers: int) -> dict:
    prefix = f"{CURATED_PREFIX}/run={run}"
    if _get(s3, CURATED_BUCKET, prefix + "/_SUCCESS") is not None:
        raise SystemExit(f"이미 게시된 run 이다: s3://{CURATED_BUCKET}/{prefix}/")

    files = sorted(p for p in (outputs / "data").glob("*.parquet"))
    if not files:
        raise SystemExit("게시할 parquet 이 없다")

    def upload(path: Path) -> dict:
        key = f"{prefix}/data/{path.name}"
        with path.open("rb") as stream:
            checksum = digest(stream)
        s3.upload_file(str(path), CURATED_BUCKET, key, ExtraArgs={"Metadata": {"sha256": checksum}})
        with s3.get_object(Bucket=CURATED_BUCKET, Key=key)["Body"] as stream:
            if digest(stream) != checksum:
                raise SystemExit("업로드 후 체크섬이 다르다: " + key)
        return {"key": key, "bytes": path.stat().st_size, "sha256": checksum}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        records = list(pool.map(upload, files))

    manifest = {
        "contract_version": 1, "status": "PASSED", "dataset": "package_text", "run": run,
        "verification": "GET_SHA256_ALL_FILES",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "rows": summary["rows"]["written"],
        "source": {"bucket": RAW_BUCKET, "prefix": selected["prefix"],
                   "manifest_sha256": selected["manifest_sha256"]},
        "summary": summary,
        "files": records,
    }
    body = json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode()
    s3.put_object(Bucket=CURATED_BUCKET, Key=prefix + "/run_manifest.json", Body=body)
    s3.put_object(Bucket=CURATED_BUCKET, Key=prefix + "/_SUCCESS",
                  Body=json.dumps({"manifest_sha256": hashlib.sha256(body).hexdigest()}).encode())
    log(f"게시 완료: s3://{CURATED_BUCKET}/{prefix}/  files={len(records)} rows={manifest['rows']}")
    return manifest


# 입력 승인 → 내려받기 → Spark 변환 → (선택) 게시 순으로 실행한다.
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collected-date", required=True, help="수집 날짜 (예: 2026-09-08)")
    parser.add_argument("--run-id", default=None, help="업로드 run_id. 생략하면 최신")
    parser.add_argument("--run", default=None, help="게시할 run 이름. 생략하면 collected-date")
    parser.add_argument("--work", type=Path, default=Path("data/package_text"))
    parser.add_argument("--curated", type=Path, default=None,
                        help="Curated 산출 디렉터리 (package/data·version/data 를 품은 곳). "
                             "주면 description 이 빈 패키지를 Curated 최신 버전 것으로 채운다")
    parser.add_argument("--publish", action="store_true", help="결과를 MinIO 에 게시한다")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--container-memory", default="6g")
    parser.add_argument("--shuffle-partitions", type=int, default=32)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--keep-raw", action="store_true", help="내려받은 원본을 지우지 않는다")
    args = parser.parse_args(argv)

    if not DATE_PATTERN.fullmatch(args.collected_date):
        raise SystemExit("collected-date 는 YYYY-MM-DD")
    run = args.run or args.collected_date
    if not SAFE_ID.fullmatch(run):
        raise SystemExit("run 이름은 영문·숫자·밑줄·하이픈")
    if args.run_id and not SAFE_ID.fullmatch(args.run_id):
        raise SystemExit("run-id 가 올바르지 않다")

    work = (args.work / run).resolve()
    attempt = work / ("attempt-" + uuid.uuid4().hex[:12])
    attempt.mkdir(parents=True, exist_ok=False)
    raw_dir = work / "raw"

    s3 = client()
    selected = select_run(s3, args.collected_date, args.run_id)
    raw_paths = download_raw(s3, selected, raw_dir, args.workers)

    sources = {"raw": str(raw_dir)}
    package_paths, version_paths = [], []
    if args.curated:
        curated = args.curated.resolve()
        package_paths = sorted(str(p) for p in curated.rglob("package/data/*.parquet"))
        version_paths = sorted(str(p) for p in curated.rglob("version/data/*.parquet"))
        if not package_paths or not version_paths:
            raise SystemExit(f"Curated 의 package/data·version/data parquet 을 찾을 수 없다: {curated}")
        sources["curated"] = str(curated)

    inputs = {"raw_paths": [str(p) for p in raw_paths],
              "curated_package_paths": package_paths, "curated_version_paths": version_paths,
              "sources": sources, "collected_date": args.collected_date, "run": run}
    result = transform_docker(inputs, attempt / "outputs", threads=args.threads,
                              container_memory=args.container_memory,
                              shuffle_partitions=args.shuffle_partitions)

    (attempt / "summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(json.dumps(result, ensure_ascii=False, indent=2))

    if args.publish:
        publish(s3, run, attempt / "outputs", result, selected, args.workers)
    else:
        log(f"게시하지 않았다 (--publish 없음). 결과: {attempt / 'outputs'}")

    if not args.keep_raw and raw_dir.exists():
        shutil.rmtree(raw_dir)
        log(f"내려받은 원본 삭제: {raw_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
