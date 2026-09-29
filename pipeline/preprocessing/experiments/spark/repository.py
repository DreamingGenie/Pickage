"""Experiment copy of baseline repository mapping with shared output URIs."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from pipeline.preprocessing.curated.repository import normalize_repository_url
from pipeline.preprocessing.snapshot.policy import parse_timestamp


class ValidationError(ValueError):
    """An input or publication contract failed."""


_MAX_INT = 2_147_483_647


class _Location(str):
    def __truediv__(self, name):
        return _Location(self.rstrip("/") + "/" + name)


def _files(inputs: dict, name: str) -> list[str]:
    values = inputs.get("files", {}).get(name)
    if not isinstance(values, list) or not values or any(not isinstance(x, str) for x in values):
        raise ValidationError(f"missing input files: {name}")
    return values


def _read(spark: Any, inputs: dict, name: str):
    frame = spark.read.parquet(*_files(inputs, name))
    expected = inputs.get("counts", {}).get(name)
    if type(expected) is not int or expected < 0:
        raise ValidationError(f"missing manifest count: {name}")
    if frame.count() != expected:
        raise ValidationError(f"input row count mismatch: {name}")
    print(f"INPUT_COUNT_VERIFIED {name} rows={expected}", flush=True)
    return frame


def _require(frame: Any, name: str, columns: set[str]) -> None:
    missing = columns.difference(frame.columns)
    if missing:
        raise ValidationError(f"{name} schema missing: {','.join(sorted(missing))}")


def _write(frame: Any, output: Path, name: str) -> int:
    target = output / name
    frame.write.mode("error").option("maxRecordsPerFile", 1_000_000).parquet(str(target))
    return frame.sparkSession.read.parquet(str(target)).count()


def transform(spark: Any, inputs: dict, output: Path) -> dict:
    """Transform approved package/version and Projects Parquet into metric evidence."""
    from pyspark import StorageLevel
    from pyspark.sql import Window, functions as F, types as T

    if not isinstance(inputs, dict) or not isinstance(inputs.get("snapshot_timestamp"), str):
        raise ValidationError("snapshot_timestamp is required")
    snapshot = inputs.get("snapshot")
    if not isinstance(snapshot, str):
        raise ValidationError("snapshot is required")
    try:
        timestamp_text = inputs["snapshot_timestamp"]
        # Python before 3.11 needs an explicit zero offset instead of trailing Z.
        parsed = parse_timestamp(timestamp_text[:-1] + "+00:00" if timestamp_text.endswith("Z") else timestamp_text)
    except (TypeError, ValueError) as exc:
        raise ValidationError("invalid snapshot_timestamp") from exc
    if parsed.date().isoformat() != snapshot:
        raise ValidationError("snapshot_timestamp date does not match snapshot")
    spark.conf.set("spark.sql.session.timeZone", "UTC")
    # Curated's naive Parquet timestamps explicitly represent UTC instants.
    spark.conf.set("spark.sql.parquet.inferTimestampNTZ.enabled", "false")
    instant = F.to_timestamp(F.lit(inputs["snapshot_timestamp"]))
    if str(output).startswith("s3a://"):
        output = _Location(output)
    else:
        output = Path(output).resolve()
        if output.exists() and any(output.iterdir()):
            raise ValidationError("output must be a fresh empty directory")
        output.mkdir(parents=True, exist_ok=True)
    cached = []
    try:
        package, version = _read(spark, inputs, "package"), _read(spark, inputs, "version")
        raw, projects = _read(spark, inputs, "versions_full"), _read(spark, inputs, "projects")
        _require(package, "package", {"package_id", "name"})
        _require(version, "version", {"package_id", "version", "published_at", "ordinal"})
        _require(raw, "versions_full", {"SnapshotAt", "Name", "Version", "is_release", "published_at", "ordinal", "source_repo"})
        _require(projects, "projects", {"SnapshotAt", "Type", "project_name", "StarsCount", "OpenIssuesCount"})
        for frame, name, column in ((version, "version", "published_at"), (raw, "versions_full", "published_at"), (raw, "versions_full", "SnapshotAt"), (projects, "projects", "SnapshotAt")):
            if frame.schema[column].dataType != T.TimestampType():
                raise ValidationError(f"{name} timestamp schema must be TIMESTAMP")
        integral = (T.ByteType, T.ShortType, T.IntegerType, T.LongType)
        for frame, name, columns in ((package, "package", ("package_id",)), (version, "version", ("package_id", "ordinal")), (raw, "versions_full", ("ordinal",)), (projects, "projects", ("StarsCount", "OpenIssuesCount"))):
            if any(not isinstance(frame.schema[column].dataType, integral) for column in columns):
                raise ValidationError(f"{name} numeric schema is invalid")
        if not isinstance(raw.schema["is_release"].dataType, T.BooleanType):
            raise ValidationError("versions_full is_release schema is invalid")
        for frame, name, columns in ((package, "package", ("name",)), (version, "version", ("version",)), (raw, "versions_full", ("Name", "Version", "source_repo")), (projects, "projects", ("Type", "project_name"))):
            if any(not isinstance(frame.schema[column].dataType, T.StringType) for column in columns):
                raise ValidationError(f"{name} string schema is invalid")
        for frame, name in ((package, "package"), (version, "version")):
            if name == "package":
                bad = frame.where(F.col("package_id").isNull() | (F.col("package_id") < 1) | (F.col("package_id") > _MAX_INT) | F.col("name").isNull() | (F.length(F.trim("name")) == 0))
            else:
                bad = frame.where(F.col("package_id").isNull() | (F.col("package_id") < 1) | (F.col("package_id") > _MAX_INT) | F.col("version").isNull() | (F.length(F.trim("version")) == 0) | F.col("ordinal").isNull() | (F.col("ordinal") < 0))
            if bad.limit(1).count():
                raise ValidationError(f"invalid {name} key/range/null")
        if package.groupBy("package_id").count().where("count > 1").limit(1).count() or package.groupBy("name").count().where("count > 1").limit(1).count():
            raise ValidationError("duplicate package key")
        if version.groupBy("package_id", "version").count().where("count > 1").limit(1).count():
            raise ValidationError("duplicate curated version key")
        if version.join(package.select("package_id"), "package_id", "left_anti").limit(1).count():
            raise ValidationError("version package FK missing")
        if raw.where(F.col("SnapshotAt").isNull() | (F.col("SnapshotAt") != instant)).limit(1).count():
            raise ValidationError("versions_full has missing or wrong exact SnapshotAt")
        if projects.where(F.col("SnapshotAt").isNull() | (F.col("SnapshotAt") != instant)).limit(1).count():
            raise ValidationError("projects has missing or wrong exact SnapshotAt")
        print("KEYS_AND_EXACT_TIMESTAMPS_VERIFIED", flush=True)

        approved = version.join(package.select("package_id", "name"), "package_id").select("package_id", "name", "version", "ordinal", "published_at").persist(StorageLevel.DISK_ONLY)
        cached.append(approved)
        if approved.count() != inputs["counts"]["version"]:
            raise ValidationError("approved version count mismatch")
        print("APPROVED_VERSION_JOIN_VERIFIED", flush=True)
        raw = raw.select("Name", "Version", "ordinal", "published_at", "is_release", "source_repo")
        matched = (approved.alias("v").join(raw.alias("r"), (F.col("v.name") == F.col("r.Name")) & (F.col("v.version") == F.col("r.Version")), "left").persist(StorageLevel.DISK_ONLY))
        cached.append(matched)
        if matched.where(F.col("r.Name").isNull()).limit(1).count():
            raise ValidationError("approved version missing raw key")
        if matched.groupBy("v.package_id", "v.version").count().where("count > 1").limit(1).count():
            raise ValidationError("duplicate raw version key")
        if matched.where((~F.col("v.ordinal").eqNullSafe(F.col("r.ordinal"))) | (~F.col("v.published_at").eqNullSafe(F.col("r.published_at")))).limit(1).count():
            raise ValidationError("Curated/raw ordinal or published_at mismatch")
        if matched.where(F.col("r.is_release").isNull() | ~F.col("r.is_release") |
                         (F.col("r.published_at") > instant)).limit(1).count():
            raise ValidationError("approved version violates release/snapshot eligibility")
        print("BRONZE_VERSION_JOIN_VERIFIED", flush=True)

        candidate_base = matched.select(F.col("v.package_id"), F.col("v.name"), F.col("v.version"),
                                        F.col("r.ordinal").alias("ordinal"), F.col("r.published_at").alias("published_at"),
                                        F.col("r.source_repo").alias("source_repo"))
        distinct_urls = candidate_base.select("source_repo").where(F.col("source_repo").isNotNull()).dropDuplicates()
        normalized_urls = distinct_urls.withColumn("repo_url", F.udf(normalize_repository_url, T.StringType())("source_repo")).persist(StorageLevel.DISK_ONLY)
        cached.append(normalized_urls)
        candidates = (candidate_base.join(normalized_urls, "source_repo", "left")
                      .withColumn("eligible", F.col("repo_url").isNotNull())
                      .withColumn("reason", F.when(F.col("source_repo").isNull(), "NO_REPOSITORY_URL")
                                  .when(F.col("repo_url").isNull(), "INVALID_OR_UNSUPPORTED_REPOSITORY_URL")
                                  .otherwise("VALID_REPOSITORY_CANDIDATE"))
                      .persist(StorageLevel.DISK_ONLY))
        cached.append(candidates)
        order = Window.partitionBy("package_id").orderBy(F.col("ordinal").desc(), F.col("published_at").desc_nulls_last(), F.col("version").asc())
        selected = candidates.where("eligible").withColumn("rn", F.row_number().over(order)).where("rn = 1").drop("rn")
        selected = (selected.withColumn("provider", F.regexp_extract("repo_url", r"^https://([^/]+)/", 1))
                    .withColumn("project_path", F.regexp_extract("repo_url", r"^https://[^/]+/(.+)$", 1))
                    .withColumn("comparison_project_path", F.when(F.col("provider") == "github.com", F.lower("project_path")).otherwise(F.col("project_path")))
                    .withColumn("selected", F.lit(True))
                    .withColumn("repo_key", F.concat("provider", F.lit("|"), "comparison_project_path"))
                    .persist(StorageLevel.DISK_ONLY))
        cached.append(selected)

        obs = (projects.withColumn("provider", F.when(F.upper("Type") == "GITHUB", F.lit("github.com")).when(F.upper("Type") == "GITLAB", F.lit("gitlab.com")))
               .withColumn("source_project_path", F.col("project_name"))
               .withColumn("project_path", F.when(F.col("provider") == "github.com", F.lower("project_name")).otherwise(F.col("project_name")))
               .withColumn("repo_key", F.when(F.col("provider").isNotNull(), F.concat("provider", F.lit("|"), "project_path")))
               .withColumn("invalid_metric", (F.col("StarsCount") < 0) | (F.col("OpenIssuesCount") < 0) | (F.col("StarsCount") > _MAX_INT) | (F.col("OpenIssuesCount") > _MAX_INT)))
        obs = obs.withColumn("repo_key", F.when(F.length(F.trim("project_path")) > 0, F.col("repo_key")))
        # An unmappable observation cannot safely be assigned to any package.
        unmapped = obs.where(F.col("repo_key").isNull()).withColumn("reason", F.lit("PROVIDER_PATH_MAPPING_FAILED"))
        # Preserve original rows/counts independently from metric-pair deduplication.
        project_keys = ["repo_key", "provider", "project_path", "SnapshotAt"]
        pairs = (obs.where(F.col("repo_key").isNotNull())
                 .groupBy(*(project_keys + ["StarsCount", "OpenIssuesCount"]))
                 .agg(F.count(F.lit(1)).alias("source_rows"),
                      F.min("source_project_path").alias("source_project_path"),
                      F.max(F.coalesce(F.col("invalid_metric"), F.lit(False)).cast("int")).alias("invalid_metric"))
                 .persist(StorageLevel.DISK_ONLY))
        cached.append(pairs)
        group = pairs.groupBy(*project_keys).agg(F.count(F.lit(1)).alias("distinct_metric_pairs"))
        conflicts = group.where("distinct_metric_pairs > 1")
        canonical = (pairs.groupBy(*project_keys)
                     .agg(F.first("StarsCount").alias("stars_raw"), F.first("OpenIssuesCount").alias("open_issues_raw"),
                          F.min("source_project_path").alias("source_project_path"),
                          F.max("invalid_metric").alias("invalid"), F.sum("source_rows").alias("source_rows"),
                          F.count(F.lit(1)).alias("distinct_metric_pairs"))
                     .withColumn("stars", F.when((F.col("distinct_metric_pairs") > 1) | (F.col("invalid") == 1), None)
                                 .otherwise(F.col("stars_raw").cast(T.IntegerType())))
                     .withColumn("open_issues", F.when((F.col("distinct_metric_pairs") > 1) | (F.col("invalid") == 1), None)
                                 .otherwise(F.col("open_issues_raw").cast(T.IntegerType()))))
        selected = selected.withColumnRenamed("repo_key", "selected_repo_key")
        joined = (package.select("package_id").join(selected, "package_id", "left")
                  .join(canonical.drop("provider", "project_path").withColumnRenamed("repo_key", "observed_repo_key").withColumnRenamed("source_project_path", "observed_project_path"),
                        (F.col("selected_repo_key") == F.col("observed_repo_key")) & (F.col("SnapshotAt") == instant), "left")
                  .persist(StorageLevel.DISK_ONLY))
        cached.append(joined)
        observed = F.col("SnapshotAt").isNotNull()
        reason = F.when(F.col("selected_repo_key").isNull(), "NO_VALID_REPOSITORY").when(F.col("distinct_metric_pairs") > 1, "PROJECT_METRIC_CONFLICT").when(F.col("invalid") == 1, "INVALID_METRIC_VALUE").when(~observed, "NO_EXACT_OBSERVATION").otherwise("SELECTED")
        metric = joined.select("package_id", F.lit(snapshot).cast(T.DateType()).alias("snapshot_at"), "stars", "open_issues")
        selection = joined.select("package_id", "version", "ordinal", "repo_url", "provider", "project_path", "comparison_project_path", "observed_project_path", F.lit(snapshot).alias("snapshot"), F.lit(inputs["snapshot_timestamp"]).alias("snapshot_timestamp"), F.when(observed, F.col("SnapshotAt")).otherwise(F.lit(None).cast(T.TimestampType())).alias("observed_timestamp"), reason.alias("reason"))
        selection = selection.withColumn("mapping_status", F.when(F.col("repo_url").isNull(), "NO_SELECTED_REPOSITORY")
                                         .when(F.col("observed_timestamp").isNull(), "NO_EXACT_PROVIDER_PATH_MATCH")
                                         .otherwise("MATCHED"))
        candidates_out = candidates.select("package_id", "version", "source_repo", "repo_url", "ordinal", "published_at", "eligible", "reason").withColumn("selected", F.lit(False)).join(selected.select("package_id", "version").withColumn("chosen", F.lit(True)), ["package_id", "version"], "left").withColumn("selected", F.coalesce(F.col("chosen"), F.lit(False))).drop("chosen").withColumn("snapshot", F.lit(snapshot)).withColumn("snapshot_timestamp", F.lit(inputs["snapshot_timestamp"]))
        observations = canonical.select("repo_key", "provider", "project_path", "source_project_path", "SnapshotAt", "stars", "open_issues", "source_rows", "distinct_metric_pairs", "invalid")
        conflicts_out = pairs.join(conflicts.select("repo_key", "SnapshotAt"), ["repo_key", "SnapshotAt"], "inner").withColumn("reason", F.lit("PROJECT_METRIC_CONFLICT"))
        frames = {"metric/data": metric, "quality/selection": selection, "quality/candidates": candidates_out,
                  "quality/project_observations": observations, "quality/project_conflicts": conflicts_out,
                  "quality/unmapped_projects": unmapped}
        counts = {}
        for name, frame in frames.items():
            print(f"WRITING_OUTPUT {name}", flush=True)
            counts[name] = _write(frame, output, name)
            print(f"OUTPUT_COUNT_VERIFIED {name} rows={counts[name]}", flush=True)
        fresh = spark.read.parquet(str(output / "metric/data"))
        if fresh.count() != package.count() or fresh.groupBy("package_id", "snapshot_at").count().where("count > 1").limit(1).count():
            raise ValidationError("metric output count/key reconciliation failed")
        selection_reasons = {row.reason: row["count"] for row in selection.groupBy("reason").count().collect()}
        null_reasons = {row.reason: row["count"] for row in joined.where(F.col("stars").isNull() | F.col("open_issues").isNull())
                        .select(reason.alias("reason")).groupBy("reason").count().collect()}
        candidate_reasons = {row.reason: row["count"] for row in candidates.groupBy("reason").count().collect()}
        report = {"output_counts": counts,
                  "mapping": {"packages": inputs["counts"]["package"], "selected": selected.count(),
                              "null": metric.where(F.col("stars").isNull() & F.col("open_issues").isNull()).count()},
                  "selection_reasons": selection_reasons, "null_reasons": null_reasons,
                  "candidate_reasons": candidate_reasons, "conflicts": conflicts.count(),
                  "unsupported_project_rows": counts["quality/unmapped_projects"], "validation": "PASSED",
                  "lineage": {"snapshot": snapshot, "snapshot_timestamp": inputs["snapshot_timestamp"], "counts": inputs["counts"]}}
        return report
    finally:
        for frame in reversed(cached):
            frame.unpersist(blocking=False)
