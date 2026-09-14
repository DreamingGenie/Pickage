"""Spark implementation of the downloads interval aggregation contract."""
from __future__ import annotations

from datetime import date, timedelta
import re

from pyspark.sql import functions as F

MAX_BIGINT = 9223372036854775807
HASH_COLUMNS = ("input_manifest_sha256", "policy_sha256", "aggregation_policy_sha256")


def _iso(value, label):
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError(f"{label} must be an ISO date")
    return value


def _paths(prepared, key, empty=False):
    values = prepared.get(key)
    if not isinstance(values, list) or (not empty and not values) or any(not isinstance(x, str) or not x for x in values):
        raise ValueError(f"{key} must be a path list")
    return values


def _union(spark, paths, fmt="parquet", **options):
    if not paths:
        return None
    return spark.read.format(fmt).options(**options).load(paths)


def aggregate(spark, prepared: dict, output: str) -> dict:
    """Aggregate approved daily files and write Spark parquet outputs.

    ``prepared`` is the dictionary returned by downloads_interval.input.prepare;
    all paths are passed to Spark unchanged, so local paths and s3a URIs work.
    """
    package_files = _paths(prepared, "package_files")
    daily_files = _paths(prepared, "daily_files", empty=True)
    target_file = _paths({"target_file": [prepared.get("target_file")]}, "target_file")[0]
    status_file = _paths({"status_file": [prepared.get("status_file")]}, "status_file")[0]
    interval = prepared["interval"]
    end = _iso(interval["snapshot_at"], "snapshot_at")
    start = interval.get("previous_snapshot_at")
    start = None if start is None else _iso(start, "previous_snapshot_at")
    expected = None if start is None else (date.fromisoformat(end) - date.fromisoformat(start)).days
    if expected is not None and expected <= 0:
        raise ValueError("snapshot interval must be positive")
    if "interval_days" in interval and interval["interval_days"] != expected:
        raise ValueError("interval_days disagrees with boundaries")
    available_start, available_end = _iso(prepared["available_start"], "available_start"), _iso(prepared["available_end"], "available_end")
    if available_start > available_end: raise ValueError("available_start must not exceed available_end")
    if start is None and daily_files: raise ValueError("first snapshot cannot consume daily files")
    lineage = prepared["lineage"]
    for key in HASH_COLUMNS:
        if not isinstance(lineage.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", lineage[key]):
            raise ValueError(f"lineage {key} must be SHA-256 hex")

    packages = _union(spark, package_files).select("package_id", "name")
    if packages.filter((F.col("package_id").isNull()) | (F.col("package_id") <= 0) | F.col("name").isNull() | (F.col("name") == "")).limit(1).count(): raise ValueError("invalid package identity")
    if packages.groupBy("package_id").count().filter("count > 1").limit(1).count(): raise ValueError("duplicate package ID")
    if packages.groupBy("name").count().filter("count > 1").limit(1).count(): raise ValueError("duplicate package name")
    if prepared.get("expected_package_rows", packages.count()) != packages.count(): raise ValueError("approved package row count mismatch")
    targets = spark.read.option("header", True).option("inferSchema", False).csv(target_file).select("name").distinct()
    statuses = _union(spark, [status_file]).select("name", "status")
    if statuses.filter((F.col("name").isNull()) | (F.col("name") == "") | (~F.col("status").isin("READY", "NOT_FOUND"))).limit(1).count(): raise ValueError("invalid status row")
    if statuses.groupBy("name").count().filter("count > 1").limit(1).count(): raise ValueError("duplicate status name")
    if targets.join(statuses, "name", "left_anti").limit(1).count() or statuses.join(targets, "name", "left_anti").limit(1).count(): raise ValueError("target/status name sets differ")

    if daily_files:
        daily = _union(spark, daily_files).select("name", "downloads", "imputed_gap")
        # The input contract's Hive partition date is authoritative and is retained in output.
        dates = []
        for path in daily_files:
            m = re.search(r"(?:^|/)date=(\d{4}-\d{2}-\d{2})(?:/|$)", path.replace("\\", "/"))
            if not m: raise ValueError(f"daily file lacks Hive date: {path}")
            day = _iso(m.group(1), "daily partition date")
            if start is None or not start <= day < end or not available_start <= day <= available_end: raise ValueError("daily date outside [P,S)")
            dates.append(day)
        daily = daily.withColumn("date", F.element_at(F.array(*[F.lit(x) for x in dates]), F.spark_partition_id() * 0 + 1).cast("date")) if len(set(dates)) == 1 else daily
        # Files are loaded together; read each partition separately to avoid losing its date.
        frames = [_union(spark, [p]).select("name", "downloads", "imputed_gap").withColumn("date", F.lit(d).cast("date")) for p, d in zip(daily_files, dates)]
        daily = frames[0]
        for frame in frames[1:]: daily = daily.unionByName(frame)
    else:
        daily = spark.createDataFrame([], "name string, downloads long, imputed_gap boolean, date date")
    if daily.filter(F.col("name").isNull() | (F.col("name") == "") | F.col("imputed_gap").isNull() | (F.col("downloads") < 0)).limit(1).count(): raise ValueError("invalid daily name, negative value, or NULL imputed_gap")
    if daily.groupBy("name", "date").count().filter("count > 1").limit(1).count(): raise ValueError("duplicate daily (name,date)")
    if daily.join(statuses.filter("status='READY'"), "name", "left_anti").limit(1).count(): raise ValueError("daily name has no READY status (unknown or NOT_FOUND)")
    agg = daily.groupBy("name").agg(F.count("*").cast("int").alias("observed_days"), F.sum(F.when((F.col("downloads").isNotNull()) & (~F.col("imputed_gap")), F.col("downloads").cast("decimal(38,0)")).otherwise(F.lit(0).cast("decimal(38,0)"))).alias("total"), F.sum(F.when(F.col("downloads").isNotNull() & (~F.col("imputed_gap")), 1).otherwise(0)).cast("int").alias("valid_days"), F.sum(F.when(F.col("downloads").isNull(), 1).otherwise(0)).cast("int").alias("null_days"), F.sum(F.when(F.col("imputed_gap"), 1).otherwise(0)).cast("int").alias("gap_days"))
    if agg.filter(F.col("total") > MAX_BIGINT).limit(1).count(): raise ValueError("BIGINT sum overflow")
    h = [F.lit(lineage[k]).alias(k) for k in HASH_COLUMNS]
    if start is None:
        results = packages.select("package_id").withColumn("snapshot_at", F.lit(end).cast("date")).withColumn("previous_snapshot_at", F.lit(None).cast("date")).withColumn("download_sum", F.lit(None).cast("long")).withColumn("expected_days", F.lit(None).cast("int")).withColumn("observed_days", F.lit(0).cast("int")).withColumn("valid_days", F.lit(0).cast("int")).withColumn("data_status", F.lit("UNAVAILABLE")).withColumn("null_reason", F.lit("NO_PREVIOUS_SNAPSHOT")).withColumn("quality_reasons", F.array(F.lit("NO_PREVIOUS_SNAPSHOT")))
    else:
        overlap = max(0, (min(date.fromisoformat(end), date.fromisoformat(available_end)+timedelta(days=1))-max(date.fromisoformat(start), date.fromisoformat(available_start))).days)
        c = packages.join(targets.withColumn("targeted", F.lit(True)), "name", "left").join(statuses, "name", "left").join(agg, "name", "left").fillna({"observed_days":0,"valid_days":0,"null_days":0,"gap_days":0})
        reasons = F.filter(F.array(F.when(F.col("targeted").isNull(), "OUTSIDE_TARGET_LIST"), F.when(F.col("status")=="NOT_FOUND", "NOT_FOUND"), F.when(F.lit(overlap < expected), "OUTSIDE_AVAILABLE_RANGE"), F.when(F.col("targeted").isNotNull() & (F.col("valid_days") < expected), "MISSING_DAILY_VALUES"), F.when(F.col("targeted").isNotNull() & (F.col("observed_days") < overlap), "ROW_MISSING"), F.when(F.col("null_days") > 0, "NULL_VALUE"), F.when(F.col("gap_days") > 0, "IMPUTED_GAP")), lambda x: x.isNotNull())
        results = c.withColumn("snapshot_at", F.lit(end).cast("date")).withColumn("previous_snapshot_at", F.lit(start).cast("date")).withColumn("download_sum", F.when(F.col("valid_days") > 0, F.col("total").cast("long"))).withColumn("expected_days", F.lit(expected).cast("int")).withColumn("observed_days", F.col("observed_days").cast("int")).withColumn("valid_days", F.col("valid_days").cast("int")).withColumn("data_status", F.when(F.col("valid_days")==0,"UNAVAILABLE").when(F.col("valid_days")==expected,"COMPLETE").otherwise("PARTIAL")).withColumn("null_reason", F.when(F.col("valid_days")>0,F.lit(None).cast("string")).when(F.col("targeted").isNull(),"OUTSIDE_TARGET_LIST").when(F.col("status")=="NOT_FOUND","NOT_FOUND").when(F.lit(overlap==0),"OUTSIDE_AVAILABLE_RANGE").otherwise("MISSING_DAILY_VALUES")).withColumn("quality_reasons", reasons).select("package_id", "snapshot_at", "previous_snapshot_at", "download_sum", "expected_days", "observed_days", "valid_days", "data_status", "null_reason", "quality_reasons")
    for k in HASH_COLUMNS: results = results.withColumn(k, F.lit(lineage[k]))
    result_path, quality_path, unmatched_path = f"{output}/interval_downloads.parquet", f"{output}/daily_quality.parquet", f"{output}/unmatched_packages.parquet"
    if results.count() != packages.count(): raise ValueError("output population or status counts differ")
    results.orderBy("package_id").write.mode("errorifexists").parquet(result_path)
    if start is None:
        daily_quality = spark.createDataFrame([], "package_id int, name string, date date, reason string")
    else:
        day_frame = spark.range(expected).select(F.date_add(F.lit(start).cast("date"), F.col("id").cast("int")).alias("date"))
        names = targets.select("name")
        d = daily.withColumn("daily_name", F.col("name")).alias("d")
        q = names.crossJoin(day_frame).join(d, ["name", "date"], "left").join(packages, "name", "left")
        qreasons = F.filter(F.array(
            F.when((F.col("date") < F.lit(available_start).cast("date")) | (F.col("date") > F.lit(available_end).cast("date")), "OUTSIDE_AVAILABLE_RANGE"),
            F.when(F.col("date").between(available_start, available_end) & F.col("daily_name").isNull(), "ROW_MISSING"),
            F.when(F.col("daily_name").isNotNull() & F.col("downloads").isNull(), "NULL_VALUE"),
            F.when(F.col("imputed_gap"), "IMPUTED_GAP")), lambda x: x.isNotNull())
        daily_quality = q.select("package_id", "name", "date", F.explode(qreasons).alias("reason")).filter(F.col("reason").isNotNull())
    daily_quality.write.mode("errorifexists").parquet(quality_path)
    unmatched = targets.join(packages, "name", "left").join(statuses, "name").join(agg, "name", "left").filter(F.col("package_id").isNull()).select("name", F.col("status").alias("input_status"), F.coalesce(F.col("observed_days"), F.lit(0)).cast("int").alias("observed_days"), F.lit("TARGET_NOT_IN_APPROVED_POPULATION").alias("reason"))
    unmatched.write.mode("errorifexists").parquet(unmatched_path)
    count = results.count(); status_counts = {r[0]: r[1] for r in results.groupBy("data_status").count().collect()}
    return {"files":[{"path":"interval_downloads.parquet","role":"interval_downloads","row_count":count},{"path":"daily_quality.parquet","role":"daily_quality","row_count":daily_quality.count()},{"path":"unmatched_packages.parquet","role":"unmatched_packages","row_count":unmatched.count()}],"quality":{"package_rows":count,"complete_rows":status_counts.get("COMPLETE",0),"partial_rows":status_counts.get("PARTIAL",0),"unavailable_rows":status_counts.get("UNAVAILABLE",0),"daily_quality_rows":daily_quality.count(),"unmatched_names":unmatched.count()},"lineage":lineage}
