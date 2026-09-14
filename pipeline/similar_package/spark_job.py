"""컨테이너 안에서 도는 Spark 잡. 호스트(build.py)만 호출한다."""
import argparse
import json
from pathlib import Path
import sys

from pipeline.similar_package.runtime import create_spark
from pipeline.similar_package.transform import transform

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


# invocation.json 을 읽어 변환을 실행하고 결과 보고서를 파일로 남긴다.
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()

    inputs = json.loads(args.input.read_bytes())
    scratch = Path("/tmp/similar-package-runtime")
    spark = create_spark(scratch, threads=inputs["threads"],
                         driver_memory=inputs["driver_memory"],
                         shuffle_partitions=inputs["shuffle_partitions"])
    try:
        report = transform(spark, inputs, args.output)
        report["runtime"] = {"spark": spark.version, "python": sys.version.split()[0],
                             "scratch": str(scratch)}
        with args.result.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, sort_keys=True)
        print("PACKAGE_TEXT_TRANSFORM_VERIFIED", flush=True)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
