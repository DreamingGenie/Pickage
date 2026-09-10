"""Container-side Spark job; the host owns input approval and publication."""
import argparse
import json
from pathlib import Path
import sys

from pipeline.repository_metrics.runtime import create_spark
from pipeline.repository_metrics.transform import transform


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    inputs = json.loads(args.input.read_bytes())
    scratch = Path("/tmp/repository-metrics-runtime")
    spark = create_spark(scratch, threads=inputs["threads"],
                         driver_memory=inputs["driver_memory"])
    try:
        report = transform(spark, inputs, args.output)
        report["runtime"] = {"spark": spark.version, "python": sys.version.split()[0],
                             "scratch": str(scratch), "scratch_storage": "container_local_ephemeral"}
        with args.result.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, sort_keys=True)
        print("REPOSITORY_METRICS_TRANSFORM_VERIFIED", flush=True)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
