"""Spark implementation of the package snapshot projection."""
from __future__ import annotations

from pyspark.sql import functions as F


def transform(spark, prepared: dict, output: str) -> dict:
    """Join the exact prepared input groups into snapshot, identity and quality outputs."""
    def read(group):
        paths = prepared.get(group)
        if not isinstance(paths, list) or not paths:
            raise ValueError(f"{group} file inventory mismatch")
        frame = spark.read.parquet(*paths)
        return frame
    population = read("population_files")
    downloads = read("download_files")
    repository = read("repository_files")
    selection = read("selection_files")
    expected = prepared["population_rows"]
    population_ids = population.select("package_id").distinct()
    for name, frame in (("population", population), ("downloads", downloads), ("repository", repository), ("selection", selection)):
        if frame.count() != expected: raise ValueError(f"{name} population count mismatch")
        if frame.groupBy("package_id").count().filter("count <> 1").limit(1).count(): raise ValueError(f"{name} duplicate package ID")
        if population_ids.join(frame.select("package_id").distinct(), "package_id", "left_anti").limit(1).count() or frame.select("package_id").distinct().join(population_ids, "package_id", "left_anti").limit(1).count(): raise ValueError(f"{name} missing/extra package ID")
    service = population.join(downloads, "package_id").join(repository, ["package_id", "snapshot_at"]).select(F.col("package_id").cast("int"), F.col("snapshot_at").cast("date"), F.col("download_sum").cast("long").alias("downloads"), F.col("stars").cast("int"), F.col("open_issues").cast("int"))
    identity = population.select(F.col("package_id").cast("int"), "name")
    p, d, q, r = population.alias("p"), downloads.alias("d"), selection.alias("q"), repository.alias("r")
    joined = p.join(d, "package_id").join(q, (F.col("p.package_id") == F.col("q.package_id")) & (F.col("d.snapshot_at").cast("string") == F.col("q.snapshot"))).join(r, (F.col("p.package_id") == F.col("r.package_id")) & (F.col("d.snapshot_at") == F.col("r.snapshot_at")))
    quality = joined.select(F.col("p.package_id"), F.col("p.name"), *[F.col("d." + c) for c in downloads.columns if c != "package_id"], *[F.col("q." + c).alias("repository_" + c) for c in selection.columns if c != "package_id"], F.col("r.stars"), F.col("r.open_issues"), F.lit(None).cast("timestamp").alias("first_published_at"), F.lit(None).cast("timestamp").alias("selected_published_at"))
    counts = {"package_snapshot": service.count(), "package_identity": identity.count(), "quality": quality.count()}
    if any(value != expected for value in counts.values()): raise ValueError("output population count mismatch")
    service.write.mode("errorifexists").parquet(f"{output}/package_snapshot.parquet")
    identity.write.mode("errorifexists").parquet(f"{output}/package_identity.parquet")
    quality.write.mode("errorifexists").parquet(f"{output}/quality.parquet")
    return {"files":[{"path":"package_snapshot.parquet","role":"package_snapshot","row_count":counts["package_snapshot"]},{"path":"package_identity.parquet","role":"package_identity","row_count":counts["package_identity"]},{"path":"quality.parquet","role":"quality","row_count":counts["quality"]}],"quality":{"status":"PASSED","rows":expected}}
