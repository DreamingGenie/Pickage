"""Spark implementation of the bounded package/version Curated transform."""

from __future__ import annotations

import json
from typing import Sequence

from pipeline.preprocessing.curated.repository import normalize_repository_url

try:
    from pyspark.sql import DataFrame, SparkSession, functions as F, types as T
    from pyspark.sql.window import Window
except ImportError:  # pragma: no cover - exercised by environments without Spark
    DataFrame = SparkSession = F = T = Window = None


class ValidationError(ValueError):
    """A quality gate failed. Messages contain counts, never raw field values."""


def _require_zero(label: str, count: int) -> None:
    if count:
        raise ValidationError(f"{label}: {count} invalid rows/groups")


def _paths(output: str, name: str) -> str:
    # String joining preserves the double slash in s3a:// URIs.
    return output.rstrip("/") + "/" + name


def _json_dependencies(dependencies, peers, optional) -> str | None:
    def convert(value):
        if value is None:
            return None
        values = []
        for item in value:
            if item is None:
                return None
            name = item["Name"] if isinstance(item, dict) else item.Name
            requirement = item["Requirement"] if isinstance(item, dict) else item.Requirement
            if name is None or not str(name).strip() or "\x00" in name or requirement is None:
                return None
            values.append((name, requirement))
        # Exact duplicate structs are removed by DuckDB's list_distinct; same
        # name with different requirements makes the whole array invalid.
        if len(set(name for name, _ in values)) != len(set(values)):
            return None
        return {name: requirement for name, requirement in sorted(set(values))}

    converted = [convert(value) for value in (dependencies, peers, optional)]
    if any(value is None for value in converted):
        return None
    return json.dumps(
        {"dependencies": converted[0], "peerDependencies": converted[1], "optionalDependencies": converted[2]},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def transform(
    spark: SparkSession,
    versions: Sequence[str],
    requirements: Sequence[str],
    previous_ids: Sequence[str] | None,
    snapshot: str,
    output: str,
) -> dict:
    """Validate raw inputs and write the seven package/version Parquet groups.

    ``versions``/``requirements``/``previous_ids`` are exact manifest-listed
    Parquet paths or URIs. Spark's default error-if-exists write mode makes the
    output a fresh publication directory.
    """
    if not versions:
        raise ValidationError("No input files: versions")
    if not requirements:
        raise ValidationError("No input files: requirements")
    raw_versions = spark.read.parquet(*[str(path) for path in versions])
    raw_requirements = spark.read.parquet(*[str(path) for path in requirements])
    snapshot_date = F.to_date(F.lit(snapshot))
    _require_zero("raw_versions snapshot mismatch", raw_versions.where(
        F.col("SnapshotAt").isNull() | (F.to_date("SnapshotAt") != snapshot_date)).count())
    _require_zero("raw_requirements snapshot mismatch", raw_requirements.where(
        F.col("SnapshotAt").isNull() | (F.to_date("SnapshotAt") != snapshot_date)).count())

    vtime = raw_versions.agg(F.min("SnapshotAt"), F.max("SnapshotAt")).first()
    rtime = raw_requirements.agg(F.min("SnapshotAt"), F.max("SnapshotAt")).first()
    if vtime[0] is None or vtime[0] != vtime[1] or (rtime[0] is not None and (rtime[0] != vtime[0] or rtime[1] != vtime[1])):
        raise ValidationError("Inputs must describe the same exact SnapshotAt")

    report = {
        "input_versions": raw_versions.count(),
        "release_versions": raw_versions.where(F.col("is_release") == True).count(),
        "nonrelease_versions": raw_versions.where(F.col("is_release") == False).count(),
        "unknown_release_versions": raw_versions.where(F.col("is_release").isNull()).count(),
        "excluded_future_versions": raw_versions.where(
            (F.col("is_release") == True) & (F.col("published_at") > F.col("SnapshotAt"))).count(),
        "snapshot_timestamp": vtime[0].isoformat(),
    }
    eligible = raw_versions.where(
        (F.col("is_release") == True)
        & (F.col("published_at").isNull() | (F.col("published_at") <= F.col("SnapshotAt")))
    ).withColumn("repo_key", F.sha2("source_repo", 256))
    required_invalid = eligible.where(
        F.col("Name").isNull() | (F.trim("Name") == "") | (F.length("Name") > 300) | (F.instr("Name", "\x00") > 0)
        | F.col("Version").isNull() | (F.trim("Version") == "") | (F.length("Version") > 100) | (F.instr("Version", "\x00") > 0)
        | F.col("ordinal").isNull() | (F.col("ordinal") < 0) | (F.instr("Deprecated", "\x00") > 0)
    ).count()
    _require_zero("Version required fields/lengths", required_invalid)
    _require_zero("Duplicate version keys", eligible.groupBy("Name", "Version").count().where(F.col("count") > 1).count())
    report["versions"] = eligible.count()
    report["missing_published_at"] = eligible.where(F.col("published_at").isNull()).count()
    report["nul_descriptions"] = eligible.where(F.instr("Description", "\x00") > 0).count()
    if not report["versions"]:
        raise ValidationError("No eligible versions; refusing empty publication")

    names = eligible.select(F.col("Name").alias("name")).distinct()
    id_schema = T.StructType([T.StructField("package_id", T.IntegerType()), T.StructField("name", T.StringType())])
    if previous_ids:
        old_source = spark.read.parquet(*[str(path) for path in previous_ids])
        _require_zero("Invalid existing package ID mapping", old_source.where(
            F.col("name").isNull() | (F.trim("name") == "") | (F.length("name") > 300) | (F.instr("name", "\x00") > 0)
            | F.col("package_id").isNull() | (F.col("package_id") < 1) | (F.col("package_id") > 2147483647)
            | (F.col("package_id") != F.floor("package_id"))).count())
        _require_zero("Duplicate existing package ID mapping", old_source.groupBy("name").count().where(F.col("count") > 1).count())
        _require_zero("Duplicate existing package ID mapping", old_source.groupBy("package_id").count().where(F.col("count") > 1).count())
        old_ids = old_source.select(F.col("package_id").cast("int"), F.col("name").cast("string"))
    else:
        old_ids = spark.createDataFrame([], id_schema)
    maximum = old_ids.agg(F.coalesce(F.max("package_id"), F.lit(0))).first()[0]
    new_names = names.join(old_ids.select("name"), "name", "left_anti")
    report["new_packages"] = new_names.count()
    if maximum + report["new_packages"] > 2147483647:
        raise ValidationError("package_id exceeds PostgreSQL INT capacity")
    new_ids = new_names.withColumn("package_id", F.row_number().over(Window.orderBy("name")) + F.lit(maximum)) \
        .select(F.col("package_id").cast("int"), "name")
    package_ids = old_ids.unionByName(new_ids)
    report["registry_packages"] = package_ids.count()

    normalize = F.udf(normalize_repository_url, T.StringType())
    distinct_repos = eligible.where(F.col("source_repo").isNotNull()).select("repo_key", "source_repo").distinct()
    normalized = distinct_repos.withColumn("repo_url", normalize("source_repo"))
    report["invalid_or_unsupported_repo_values"] = normalized.where(F.col("repo_url").isNull()).count()
    report["ordinal_tie_groups"] = eligible.groupBy("Name", "ordinal").count().where(F.col("count") > 1).count()
    repo_window = Window.partitionBy("Name").orderBy(F.col("ordinal").desc(), F.col("published_at").desc_nulls_last(), F.col("Version").asc())
    chosen_repos = eligible.join(normalized.select("repo_key", "repo_url"), "repo_key").where(F.col("repo_url").isNotNull()) \
        .withColumn("rn", F.row_number().over(repo_window)).where(F.col("rn") == 1) \
        .select(F.col("Name").alias("name"), F.col("Version").alias("version"), "ordinal", "repo_url", F.col("repo_key").alias("source_repo_sha256"))
    packages = names.join(package_ids, "name").join(chosen_repos.select("name", "repo_url"), "name", "left") \
        .select("package_id", "name", "repo_url")
    report["packages"] = packages.count()
    report["packages_without_repo"] = packages.where(F.col("repo_url").isNull()).count()

    matched = raw_requirements.join(eligible.select("Name", "Version", "SnapshotAt"), ["Name", "Version", "SnapshotAt"], "left_semi")
    _require_zero("Duplicate requirements keys", matched.groupBy("Name", "Version").count().where(F.col("count") > 1).count())
    json_udf = F.udf(_json_dependencies, T.StringType())
    requirements_json = matched.select("Name", "Version", json_udf("Dependencies", "PeerDependencies", "OptionalDependencies").alias("dependency")) \
        .withColumn("invalid", F.col("dependency").isNull()).withColumn("req_present", F.lit(1))
    report["invalid_requirements"] = requirements_json.where("invalid").count()
    report["missing_requirements"] = eligible.join(requirements_json.select("Name", "Version"), ["Name", "Version"], "left_anti").count()
    final_versions = eligible.join(package_ids, eligible.Name == package_ids.name).join(
        requirements_json.select("Name", "Version", "dependency"), ["Name", "Version"], "left"
    ).select(F.col("Version").alias("version"), "package_id", "published_at", F.col("ordinal").cast("long"),
             F.when(F.instr("Description", "\x00") > 0, F.lit(None)).otherwise(F.col("Description")).cast("string").alias("description"),
             F.to_json("Licenses").alias("licenses"), F.col("Deprecated").cast("string").alias("deprecated"), "dependency")
    _require_zero("Output FK", final_versions.join(packages.select("package_id").distinct(), "package_id", "left_anti").count())
    final_count = final_versions.count()
    if final_count != report["versions"] or final_count + report["excluded_future_versions"] != report["release_versions"]:
        raise ValidationError("Version count reconciliation failed")
    _require_zero("Output repository length", packages.where(F.length("repo_url") > 200).count())
    _require_zero("Output duplicate version keys", final_versions.groupBy("package_id", "version").count().where(F.col("count") > 1).count())
    old_alias = old_ids.alias("old")
    new_alias = package_ids.alias("new")
    _require_zero("Changed existing IDs", old_alias.join(new_alias, "name", "left").where(
        F.col("new.package_id").isNull() | (F.col("new.package_id") != F.col("old.package_id"))).count())

    exports = {
        "package/data": packages,
        "version/data": final_versions,
        "package_ids/data": package_ids,
        "quality/repository_selection": chosen_repos.join(packages.select("name", "package_id"), "name").select("package_id", "version", "ordinal", "repo_url", "source_repo_sha256"),
        "quality/excluded_versions": raw_versions.where((F.col("is_release") == True) & (F.col("published_at") > F.col("SnapshotAt"))).select("Name", "Version", "SnapshotAt", "published_at", F.lit("PUBLISHED_AFTER_SNAPSHOT").alias("reason")),
        "quality/dependency_issues": eligible.join(requirements_json, ["Name", "Version"], "left").where(F.col("req_present").isNull() | F.col("invalid")).select("Name", "Version", F.when(F.col("req_present").isNull(), "MISSING_REQUIREMENTS").otherwise("INVALID_REQUIREMENTS").alias("reason")),
        "quality/metadata_issues": eligible.where(F.instr("Description", "\x00") > 0).select("Name", "Version", F.lit("description").alias("field"), F.lit("NUL_IN_DESCRIPTION").alias("reason")),
    }
    output_counts = {}
    for name, frame in exports.items():
        target = _paths(output, name)
        frame.write.mode("errorifexists").parquet(target)
        actual = spark.read.parquet(target).count()
        expected = frame.count()
        if actual != expected:
            raise ValidationError(f"Export count mismatch: {name}")
        output_counts[name] = actual
    report["output_counts"] = output_counts
    return report


__all__ = ["ValidationError", "transform"]
