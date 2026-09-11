"""Container entrypoint; invoked only through the host runtime adapter."""
import json
from pathlib import Path

from pyspark.sql import SparkSession

from pipeline.requirements_resolution.policy import canonical_bytes
from pipeline.requirements_resolution.transform import prepare, finalize


def main():
    request = json.loads(Path("/run/invocation.json").read_bytes())
    spark = (SparkSession.builder.appName("pickage-requirements-" + request["stage"])
             .config("spark.driver.maxResultSize", "64m")
             .config("spark.driver.host", "127.0.0.1")
             .config("spark.driver.bindAddress", "127.0.0.1")
             .config("spark.local.dir", "/run/scratch")
             .config("spark.sql.warehouse.dir", "file:///run/warehouse")
             .config("spark.sql.session.timeZone", "UTC")
             .config("spark.sql.shuffle.partitions", str(request["shuffle_partitions"]))
             .config("spark.sql.adaptive.enabled", "true")
             .config("spark.sql.parquet.outputTimestampType", "TIMESTAMP_MICROS")
             .config("spark.hadoop.mapreduce.fileoutputcommitter.marksuccessfuljobs", "false")
             .config("spark.ui.enabled", "false").getOrCreate())
    spark.sparkContext.setLogLevel("WARN")
    try:
        if request["stage"] == "prepare":
            result = prepare(spark, request["inputs"], request["policy"], Path("/run/outputs"))
        else:
            result = finalize(spark, Path(request["prepared_dir"]), Path(request["bridge_dir"]),
                              request["inputs"], request["policy"], Path("/run/outputs"), request["run_id"])
        with Path("/run/result.json").open("xb") as stream:
            stream.write(canonical_bytes(result))
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
