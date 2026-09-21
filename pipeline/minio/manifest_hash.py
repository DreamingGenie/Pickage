"""S3 객체의 sha256 을 계산해 표준출력 마지막 줄에 찍는다.

    python -m pipeline.minio.manifest_hash --bucket pickage-vectors \
      --key "model=v3/corpus=package-text-20260908-v1/run_manifest.json"

load.py 의 select_run() 이 같은 파일을 나중에 내려받아 계산하는 값과 바이트
단위로 같아야 한다 (S15P21A506-376) — 둘 다 원본 바이트를 그대로 해시하고
어떤 변환도 하지 않는다. ingest_derived.py 가 코퍼스 쪽 manifest_sha256 을
계산할 때 쓰는 것과 같은 client()/digest() 를 그대로 쓴다.

client() 가 진단용 줄(PICKAGE_S3_ENDPOINT=...)을 표준출력에 같이 찍으므로,
호출 쪽에서는 마지막 줄만 취할 것.
"""
from __future__ import annotations

import argparse
import sys

from pipeline.minio.ingest_raw import client, digest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--key", required=True)
    args = parser.parse_args(argv)

    s3 = client()
    body = s3.get_object(Bucket=args.bucket, Key=args.key)["Body"]
    print(digest(body))
    return 0


if __name__ == "__main__":
    sys.exit(main())
