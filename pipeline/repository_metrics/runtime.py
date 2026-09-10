"""Create a bounded local Spark runtime in this task's output directory."""
import os
from pathlib import Path
import sys


def create_spark(directory, *, threads=2, driver_memory="4g", shuffle_partitions=16):
    if type(threads) is not int or threads < 1 or type(shuffle_partitions) is not int or shuffle_partitions < 1:
        raise ValueError("Spark thread and partition counts must be positive integers")
    from pyspark import SparkContext
    from pyspark.sql import SparkSession
    if SparkContext._active_spark_context is not None:
        raise ValueError("An existing Spark context cannot be reused as an isolated runtime")
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    os.environ["PYSPARK_PYTHON"] = sys.executable
    os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable
    os.environ.setdefault("SPARK_LOCAL_IP", "127.0.0.1")
    spark = (SparkSession.builder.appName("pickage-repository-metrics")
             .master(f"local[{threads}]")
             .config("spark.driver.memory", driver_memory)
             .config("spark.driver.maxResultSize", "128m")
             .config("spark.driver.host", "127.0.0.1")
             .config("spark.driver.bindAddress", "127.0.0.1")
             .config("spark.local.dir", str(directory / "scratch"))
             .config("spark.sql.warehouse.dir", (directory / "warehouse").as_uri())
             .config("spark.sql.session.timeZone", "UTC")
             .config("spark.sql.parquet.outputTimestampType", "TIMESTAMP_MICROS")
             .config("spark.sql.shuffle.partitions", str(shuffle_partitions))
             .config("spark.sql.adaptive.enabled", "true")
             .config("spark.hadoop.mapreduce.fileoutputcommitter.marksuccessfuljobs", "false")
             .config("spark.ui.enabled", "false")
             .getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")
    return spark
