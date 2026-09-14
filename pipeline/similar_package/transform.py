"""keywords 원본 + Curated description → package_text parquet."""
from __future__ import annotations

from pathlib import Path
from typing import Any


class ValidationError(ValueError):
    pass


# 수집 원본 JSONL 의 명시 스키마. 추론에 맡기면 페이지마다 필드가 달라 결과가 흔들린다.
def raw_schema():
    from pyspark.sql import types as T

    repo = T.StructType([
        T.StructField("full_name", T.StringType()),
        T.StructField("description", T.StringType()),
        T.StructField("archived", T.BooleanType()),
    ])
    return T.StructType([
        T.StructField("name", T.StringType()),
        T.StructField("rank", T.LongType()),
        T.StructField("fetched_at", T.StringType()),
        T.StructField("description", T.StringType()),
        T.StructField("keywords", T.ArrayType(T.StringType())),
        T.StructField("dependent_packages_count", T.LongType()),
        T.StructField("latest_release_published_at", T.StringType()),
        T.StructField("status", T.StringType()),
        T.StructField("repo", repo),
    ])


# 공백만 있는 문자열을 NULL 로 본다.
def _blank_to_null(column):
    from pyspark.sql import functions as F

    trimmed = F.trim(column)
    return F.when(F.length(trimmed) > 0, trimmed)


# Curated 에서 패키지 이름별 최신 버전(ordinal 기준) description 을 뽑는다.
def _curated_description(spark, package_paths: list[str], version_paths: list[str]):
    from pyspark.sql import functions as F

    package = spark.read.parquet(*package_paths).select("package_id", "name")
    version = spark.read.parquet(*version_paths).select("package_id", "description", "ordinal")
    return (version.join(package, "package_id")
            .groupBy("name")
            .agg(F.expr("max_by(description, ordinal)").alias("description_curated")))


# parquet 으로 쓰고, 기록된 파일을 다시 읽어 행 수를 돌려준다.
def _write(frame: Any, output: Path, name: str) -> int:
    target = Path(output) / name
    (frame.write.mode("errorifexists")
     .option("compression", "zstd")
     .option("maxRecordsPerFile", 1_000_000)
     .parquet(str(target)))
    return frame.sparkSession.read.parquet(str(target)).count()


# 원본을 읽어 name 중복을 제거하고 description 을 보강한 뒤 package_text 8개 컬럼을 쓴다.
def transform(spark: Any, inputs: dict, output: Path) -> dict:
    from pyspark import StorageLevel
    from pyspark.sql import Window, functions as F

    raw_paths = inputs.get("raw_paths")
    if not isinstance(raw_paths, list) or not raw_paths:
        raise ValidationError("raw_paths 가 비어 있다")

    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValidationError("산출 디렉터리는 비어 있어야 한다")
    output.mkdir(parents=True, exist_ok=True)
    spark.conf.set("spark.sql.session.timeZone", "UTC")

    cached = []
    try:
        raw = spark.read.schema(raw_schema()).json(raw_paths).select(
            "name", "rank", "fetched_at", "description", "keywords",
            "dependent_packages_count", "latest_release_published_at", "status",
            F.col("repo.description").alias("repo_description"),
            F.col("repo.archived").alias("repo_archived"),
        ).persist(StorageLevel.DISK_ONLY)
        cached.append(raw)

        n_raw = raw.count()
        if n_raw == 0:
            raise ValidationError("원본이 비어 있다")
        if raw.where(F.col("name").isNull() | (F.length(F.trim("name")) == 0)).limit(1).count():
            raise ValidationError("name 이 비어 있는 행이 있다")
        print(f"RAW_READ_VERIFIED rows={n_raw}", flush=True)

        order = Window.partitionBy("name").orderBy(F.col("fetched_at").desc(), F.col("rank").asc())
        rows = (raw.withColumn("_rn", F.row_number().over(order)).where("_rn = 1").drop("_rn")
                .persist(StorageLevel.DISK_ONLY))
        cached.append(rows)
        n_dedup = rows.count()
        print(f"DEDUP_VERIFIED raw={n_raw} dedup={n_dedup} removed={n_raw - n_dedup}", flush=True)

        package_paths = inputs.get("curated_package_paths") or []
        version_paths = inputs.get("curated_version_paths") or []
        if bool(package_paths) != bool(version_paths):
            raise ValidationError("Curated 는 package 와 version 을 함께 줘야 한다")
        if package_paths:
            rows = rows.join(_curated_description(spark, package_paths, version_paths), "name", "left")
        else:
            rows = rows.withColumn("description_curated", F.lit(None).cast("string"))
            print("CURATED_SKIPPED", flush=True)

        rows = (rows
                .withColumn("desc_eco", _blank_to_null(F.col("description")))
                .withColumn("desc_curated", _blank_to_null(F.col("description_curated")))
                .withColumn("desc_repo", _blank_to_null(F.col("repo_description")))
                .persist(StorageLevel.DISK_ONLY))
        cached.append(rows)
        curated_filled = rows.where(F.col("desc_eco").isNull()
                                    & F.col("desc_curated").isNotNull()).count()

        package_text = rows.select(
            F.col("name"),
            F.coalesce("desc_eco", "desc_curated", "desc_repo").alias("description"),
            F.coalesce(F.col("keywords"), F.array()).alias("keywords"),
            F.col("dependent_packages_count").cast("int").alias("dependent_packages_count"),
            F.to_timestamp(F.substring(F.col("latest_release_published_at"), 1, 19))
             .alias("latest_release_published_at"),
            F.col("status"),
            F.lit(False).alias("is_spam"),
            F.col("repo_archived"),
        ).persist(StorageLevel.DISK_ONLY)
        cached.append(package_text)

        written = _write(package_text, output, "data")
        if written != n_dedup:
            raise ValidationError(f"산출 행 수가 중복 제거 결과와 다르다: {written} vs {n_dedup}")
        print(f"WRITE_VERIFIED rows={written}", flush=True)

        has_description = F.col("description").isNotNull()
        return {
            "rows": {"raw": n_raw, "dedup": n_dedup, "written": written},
            "description_from_curated": curated_filled,
            "null_description": package_text.where(~has_description).count(),
            "empty_keywords": package_text.where(F.size("keywords") == 0).count(),
            "null_dependents": package_text.where(F.col("dependent_packages_count").isNull()).count(),
            "repo_archived": package_text.where(F.col("repo_archived")).count(),
            "curated_joined": bool(package_paths),
        }
    finally:
        for frame in cached:
            frame.unpersist()
