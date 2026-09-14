"""배치 산출물을 EC2 #1 → MinIO → EC2 #2 로 옮긴다.

    ship push --run <run> --run-dir <dir>      # EC2 #1
    ship pull --run <run> --target <dir>       # EC2 #2
    ship prune --keep 3
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import sys

from botocore.exceptions import ClientError

from pipeline.minio.ingest_raw import client, digest

try:  # Windows 콘솔 cp949 에서 한글 출력 보장
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

BUCKET = "pickage-vectors"                # TODO(팀 합의): candidates 보관 버킷
PREFIX = "candidates"                     # TODO(팀 합의): candidates 보관 접두사
RUN_PATTERN = re.compile(r"[0-9A-Za-z_.-]{1,64}\Z")
REQUIRED = ("candidates.parquet", "run_manifest.json")
OPTIONAL = ("text_hash_state.parquet",)


# 표준출력에 한 줄 남긴다.
def log(message: str) -> None:
    print(message, flush=True)


# 객체 하나를 읽는다. 없으면 None.
def _get(s3, key: str) -> bytes | None:
    try:
        with s3.get_object(Bucket=BUCKET, Key=key)["Body"] as stream:
            return stream.read()
    except ClientError as error:
        if error.response["Error"]["Code"] in ("NoSuchKey", "404"):
            return None
        raise


# 접두사 아래 객체 키를 나열한다.
def _keys(s3, prefix: str) -> list[str]:
    keys, token = [], None
    while True:
        kwargs = {"Bucket": BUCKET, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        page = s3.list_objects_v2(**kwargs)
        keys += [item["Key"] for item in page.get("Contents", [])]
        if not page.get("IsTruncated"):
            return keys
        token = page.get("NextContinuationToken")


# 배치 산출물을 MinIO 에 올리고 전달 manifest 와 _SUCCESS 를 남긴다.
def push(s3, run: str, run_dir: Path, workers: int, force: bool) -> dict:
    prefix = f"{PREFIX}/run={run}"
    if not force and _get(s3, prefix + "/_SUCCESS") is not None:
        raise SystemExit(f"이미 올라간 run 이다: s3://{BUCKET}/{prefix}/  (--force 로 덮어쓴다)")

    if not (run_dir / "_SUCCESS").exists():
        raise SystemExit(f"배치 완료 마커가 없다: {run_dir / '_SUCCESS'}\n"
                         "채점 게이트를 통과하지 못한 실행이다")
    for name in REQUIRED:
        if not (run_dir / name).exists():
            raise SystemExit(f"필수 파일이 없다: {run_dir / name}")

    manifest_bytes = (run_dir / "run_manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    gate = (manifest.get("scoring_gate") or {}).get("status")
    log(f"배치 결과 {run_dir}  model_ver={manifest.get('model_ver')} "
        f"rows={manifest.get('candidate_rows')} gate={gate}")

    files = [run_dir / n for n in REQUIRED] + [run_dir / n for n in OPTIONAL if (run_dir / n).exists()]

    def upload(path: Path) -> dict:
        key = f"{prefix}/{path.name}"
        with path.open("rb") as stream:
            checksum = digest(stream)
        s3.upload_file(str(path), BUCKET, key, ExtraArgs={"Metadata": {"sha256": checksum}})
        with s3.get_object(Bucket=BUCKET, Key=key)["Body"] as stream:
            if digest(stream) != checksum:
                raise SystemExit("업로드 후 체크섬이 다르다: " + key)
        log(f"  ↑ {path.name}  ({path.stat().st_size / 1e6:.1f} MB)")
        return {"key": key, "name": path.name, "bytes": path.stat().st_size, "sha256": checksum}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        records = list(pool.map(upload, files))

    transfer = {"contract_version": 1, "run": run, "verification": "GET_SHA256_ALL_FILES",
                "batch_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                "scoring_gate": manifest.get("scoring_gate"),
                "model_ver": manifest.get("model_ver"), "files": records}
    body = json.dumps(transfer, ensure_ascii=False, sort_keys=True).encode()
    s3.put_object(Bucket=BUCKET, Key=prefix + "/transfer_manifest.json", Body=body)
    s3.put_object(Bucket=BUCKET, Key=prefix + "/_SUCCESS",
                  Body=json.dumps({"manifest_sha256": hashlib.sha256(body).hexdigest()}).encode())
    log(f"올림 완료: s3://{BUCKET}/{prefix}/  files={len(records)}")
    return transfer


# MinIO 에서 산출물을 내려받아 적재 가능한 디렉터리를 만든다.
def pull(s3, run: str, target: Path, workers: int) -> dict:
    prefix = f"{PREFIX}/run={run}"
    marker = _get(s3, prefix + "/_SUCCESS")
    if marker is None:
        raise SystemExit(f"완료 마커가 없다: s3://{BUCKET}/{prefix}/_SUCCESS\n"
                         "아직 올리는 중이거나 run 이름이 틀렸다")
    body = _get(s3, prefix + "/transfer_manifest.json")
    if body is None:
        raise SystemExit(f"transfer_manifest.json 이 없다: s3://{BUCKET}/{prefix}/")
    if json.loads(marker) != {"manifest_sha256": hashlib.sha256(body).hexdigest()}:
        raise SystemExit("_SUCCESS 와 transfer_manifest.json 이 어긋난다 — 올리기가 끝나지 않았다")

    transfer = json.loads(body)
    target = target.resolve()
    target.mkdir(parents=True, exist_ok=True)

    def download(record: dict) -> Path:
        path = target / record["name"]
        temporary = path.with_suffix(path.suffix + ".part")
        s3.download_file(BUCKET, record["key"], str(temporary))
        temporary.replace(path)
        with path.open("rb") as stream:
            if digest(stream) != record["sha256"]:
                raise SystemExit(f"체크섬이 다르다: {record['key']}")
        log(f"  ↓ {record['name']}  ({record['bytes'] / 1e6:.1f} MB)")
        return path

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(download, transfer["files"]))

    # load.py 가 보는 _SUCCESS 를 같은 자리에 만든다.
    (target / "_SUCCESS").write_bytes(marker)
    gate = (transfer.get("scoring_gate") or {}).get("status")
    log(f"내려받음: {target}  model_ver={transfer.get('model_ver')} gate={gate}")
    log("")
    log("적재 명령:")
    log(f"  python -m pipeline.similar_package.load \\")
    log(f"    --run-dir {target} \\")
    log(f"    --execution-id similar-package-{run.replace('-', '')} \\")
    log(f"    --docker-container <컨테이너> --database <DB>"
        + ("  --allow-gate-skip" if gate == "SKIPPED" else ""))
    return transfer


# 최신 keep 개만 남기고 오래된 run 을 지운다.
def prune(s3, keep: int) -> list[str]:
    runs = sorted({key.split("/")[1] for key in _keys(s3, PREFIX + "/") if key.count("/") >= 2})
    stale = runs[:-keep] if keep > 0 else runs
    removed = []
    for run in stale:
        for key in _keys(s3, f"{PREFIX}/{run}/"):
            s3.delete_object(Bucket=BUCKET, Key=key)
            removed.append(key)
        log(f"  삭제 {run}")
    log(f"정리: {len(runs)} 개 중 {len(stale)} 개 삭제, {min(keep, len(runs))} 개 유지")
    return removed


# push·pull·prune 중 하나를 실행한다.
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)

    p = sub.add_parser("push", help="EC2 #1: 배치 산출물을 MinIO 에 올린다")
    p.add_argument("--run", required=True)
    p.add_argument("--run-dir", type=Path, required=True, help="배치의 --out 디렉터리")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--force", action="store_true", help="이미 올라간 run 을 덮어쓴다")

    p = sub.add_parser("pull", help="EC2 #2: 적재할 산출물을 내려받는다")
    p.add_argument("--run", required=True)
    p.add_argument("--target", type=Path, required=True)
    p.add_argument("--workers", type=int, default=4)

    p = sub.add_parser("prune", help="오래된 run 을 지운다")
    p.add_argument("--keep", type=int, default=3)

    args = parser.parse_args(argv)
    if getattr(args, "run", None) and not RUN_PATTERN.fullmatch(args.run):
        raise SystemExit("run 이름은 영문·숫자·점·밑줄·하이픈만 쓴다")

    s3 = client()
    if args.action == "push":
        push(s3, args.run, args.run_dir.resolve(), args.workers, args.force)
    elif args.action == "pull":
        pull(s3, args.run, args.target, args.workers)
    else:
        prune(s3, args.keep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
