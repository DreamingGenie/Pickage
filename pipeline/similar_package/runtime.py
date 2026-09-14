"""로컬 Spark 세션 생성."""
import os
from pathlib import Path
import sys


# 주어진 디렉터리 안에서만 동작하는 자원 제한 Spark 세션을 만든다.
def create_spark(directory, *, threads=2, driver_memory="4g", shuffle_partitions=32):
    if type(threads) is not int or threads < 1 or type(shuffle_partitions) is not int or shuffle_partitions < 1:
        raise ValueError("threads 와 shuffle_partitions 는 양의 정수여야 한다")
    from pyspark import SparkContext
    from pyspark.sql import SparkSession
    if SparkContext._active_spark_context is not None:
        raise ValueError("이미 떠 있는 Spark 컨텍스트는 재사용하지 않는다")
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    os.environ["PYSPARK_PYTHON"] = sys.executable
    os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable
    os.environ.setdefault("SPARK_LOCAL_IP", "127.0.0.1")
    spark = (SparkSession.builder.appName("pickage-package-text")
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
