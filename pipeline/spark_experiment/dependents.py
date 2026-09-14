"""Spark implementation of the single-snapshot direct dependents stage.

The resolver is deliberately the task08 npm worker. Spark owns all joins and
aggregation; only one package-name group is materialized in an executor
partition while talking to Node.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import queue
import subprocess
import tempfile
import threading


_WORKER = Path(__file__).resolve().parents[1] / "version_dependents" / "historical_semver_worker.cjs"


def _read(spark, value):
    paths = value if isinstance(value, (list, tuple)) else [value]
    return spark.read.parquet(*[str(p) for p in paths])


class _Node:
    def __init__(self, runtime, worker):
        self.runtime = runtime
        self.log = tempfile.NamedTemporaryFile(prefix="spark-dependents-node-", suffix=".log", delete=False)
        self.process = subprocess.Popen(
            [runtime["node"], str(worker), runtime["semver_module"], runtime["package_arg_module"]],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log,
            text=True, encoding="utf-8", bufsize=1)
        self.responses = queue.Queue()
        self.closed = False
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            while True:
                line = self.process.stdout.readline(8 * 1024 * 1024 + 1)
                if not line:
                    self.responses.put(None)
                    return
                if len(line.encode("utf-8")) > 8 * 1024 * 1024 or not line.endswith("\n"):
                    self.responses.put(ValueError("Node response exceeds framing limit"))
                    return
                self.responses.put(line)
        except BaseException as error:
            self.responses.put(error)

    def request(self, message):
        if self.closed:
            raise RuntimeError("Node resolver is closed")
        try:
            payload = json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n"
            if len(payload.encode("utf-8")) > 7 * 1024 * 1024:
                raise ValueError("Node request exceeds framing limit")
            self.process.stdin.write(payload)
            self.process.stdin.flush()
            line = self.responses.get(timeout=60)
        except (queue.Empty, BrokenPipeError, OSError):
            self.close()
            raise RuntimeError("Node resolver timed out or stopped")
        except BaseException:
            self.close()
            raise
        if line is None or isinstance(line, BaseException):
            self.close()
            if isinstance(line, BaseException):
                raise RuntimeError("Node resolver framing failed") from line
            raise RuntimeError("Node resolver exited before returning a response")
            raise RuntimeError("Node resolver exited before returning a response")
        response = json.loads(line)
        if response.get("ok") is not True:
            raise RuntimeError("Node resolver rejected request: " + str(response.get("error", "unknown error")))
        return response["result"]

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            if self.process.poll() is None:
                try:
                    self.process.stdin.close()
                except OSError:
                    pass
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=10)
            self.reader.join(timeout=2)
            self.process.stdout.close()
        finally:
            self.log.close()


def _resolve_names(rows, runtime, worker):
    """Resolve grouped declarations, yielding one resolved direct edge each."""
    node = _Node(runtime, worker)
    try:
        for name, grouped in rows:
            values = list(grouped)
            if not values:
                continue
            package_id = values[0]["target_package_id"]
            candidates = values[0]["candidates"]
            requirements = sorted({v["requirement"] for v in values}, key=lambda value: (value is not None, value or ""))
            by_requirement = {}
            for start in range(0, len(requirements), 512):
                batch = requirements[start:start + 512]
                reply = node.request({"op": "package", "name": name,
                                      "known_package": package_id is not None,
                                      "snapshot_count": 1, "candidates": candidates,
                                      "requirements": batch})
                if reply.get("rejected") or reply.get("accepted") != candidates:
                    raise ValueError("Worker candidate validation differs from Spark target population")
                by_requirement.update({r["requirement"]: r for r in reply["lookups"]})
            for value in values:
                result = by_requirement[value["requirement"]]
                for interval in result["intervals"]:
                    if interval["status"] == "RESOLVED":
                        yield (value["lookup_id"], name, package_id, interval["target_version"], value["requirement"],
                               interval["status"], interval["normalized_range"])
                    else:
                        yield (value["lookup_id"], name, None, None, value["requirement"], interval["status"],
                               interval["normalized_range"])
    finally:
        node.close()


def _classify(rows, runtime, worker):
    node = _Node(runtime, worker)
    try:
        for package_id, values in rows:
            versions = list(values)
            node.request({"op": "start", "name": "spark-population"})
            result = node.request({"op": "candidates", "versions": [v[0] for v in versions]})
            rejected = {r["version"]: r["reason"] for r in result["rejected"]}
            for version, published_at, dependency_error in versions:
                yield (package_id, version, published_at, dependency_error,
                       rejected.get(version, "ELIGIBLE"))
    finally:
        node.close()


def calculate(spark, *, files: dict, snapshot: str, snapshot_timestamp: str,
              output: str, runtime: dict | None = None) -> dict:
    """Calculate one snapshot without collecting populations on the driver."""
    from pyspark.sql import functions as F, types as T

    if not files.get("targets"):
        raise ValueError("Missing dependents target selection")
    runtime = dict(runtime or {})
    worker = Path(runtime.pop("worker", _WORKER))
    classifier_worker = Path(runtime.pop("classifier_worker", worker.parent.parent / "requirements_resolution" / "semver_worker.cjs"))
    if not worker.is_file() or not classifier_worker.is_file():
        raise ValueError("Spark executor Node worker is unavailable")
    stamp = datetime.fromisoformat(snapshot_timestamp.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)

    package = _read(spark, files["package"]).select("package_id", "name")
    version = _read(spark, files["version"]).select("package_id", "version", "published_at")
    raw = _read(spark, files["versions_full"])
    requirements = _read(spark, files["requirements"])
    targets = _read(spark, files["targets"]).select(F.col("name").alias("target_name"))
    if targets.limit(1).count() == 0:
        raise ValueError("Empty dependents target selection")
    if targets.where((F.col("target_name").isNull()) | (F.col("target_name") != F.trim("target_name")) |
                     (F.col("target_name") == "") | (F.instr("target_name", "\u0000") > 0)).limit(1).count():
        raise ValueError("Invalid dependents target name")
    if targets.groupBy("target_name").count().where("count <> 1").limit(1).count():
        raise ValueError("Duplicate dependents target name")

    # Pin raw release/date provenance before the distributed npm classification.
    raw_cols = raw.columns
    if "dependency_error" not in raw_cols:
        raw = raw.withColumn("dependency_error", F.lit(None).cast("boolean"))
    raw = raw.select(F.col("Name").alias("name"), F.col("Version").alias("version"),
                     F.col("published_at").alias("raw_published_at"), "is_release", "dependency_error")
    base = (version.join(package, "package_id").join(raw, ["name", "version"], "inner")
            .where((F.col("is_release") == True) & F.col("published_at").isNotNull()
                   & (F.col("published_at") <= F.lit(stamp))))
    cls_schema = T.StructType([T.StructField("package_id", T.IntegerType()), T.StructField("version", T.StringType()),
                               T.StructField("published_at", T.TimestampType()), T.StructField("dependency_error", T.BooleanType()),
                               T.StructField("target_status", T.StringType())])
    cls = (base.select("package_id", "version", "published_at", "dependency_error").dropDuplicates(["package_id", "version"])
           .rdd.map(lambda r: (r.package_id, (r.version, r.published_at, r.dependency_error)))
           .groupByKey().mapPartitions(lambda it: _classify(it, runtime, classifier_worker))
           .toDF(cls_schema))
    stable = cls.where(F.col("target_status") == "ELIGIBLE").cache()
    selected = targets.join(package, targets.target_name == package.name, "left")
    target = (stable.join(selected, [stable.package_id == selected.package_id], "inner")
              .select(stable.package_id.alias("target_package_id"), stable.version.alias("target_version"),
                      stable.published_at, selected.target_name.alias("name")))
    source = (cls.join(package, "package_id").select(F.col("package_id").alias("source_package_id"),
              F.col("version").alias("source_version"), "name", "dependency_error"))
    req_input = requirements.select(F.col("Name").alias("req_name"), F.col("Version").alias("req_version"), "Dependencies")
    source_quality = source.join(req_input, (F.col("name") == F.col("req_name")) & (F.col("source_version") == F.col("req_version")), "left")
    req = (req_input.join(source, (F.col("req_name") == F.col("name")) & (F.col("req_version") == F.col("source_version")), "inner")
           .select("source_package_id", "source_version", "name", "Dependencies"))
    declarations = (req.where(F.col("Dependencies").isNotNull()).select(
        "source_package_id", "source_version", F.explode("Dependencies").alias("item"))
        .select("source_package_id", "source_version", F.col("item.Name").alias("declared_name"),
                F.col("item.Requirement").alias("requirement"))
        .join(targets, F.col("declared_name") == targets.target_name, "inner")
        .drop("target_name"))
    from pyspark.sql.window import Window
    lookup_keys = declarations.select("declared_name", "requirement").dropDuplicates()
    lookup_window = Window.orderBy(F.col("declared_name"), F.col("requirement").asc_nulls_first())
    lookup_keys = lookup_keys.withColumn("lookup_id", (F.row_number().over(lookup_window) - 1).cast("long"))
    declarations = declarations.join(lookup_keys,
        (declarations.declared_name == lookup_keys.declared_name) & declarations.requirement.eqNullSafe(lookup_keys.requirement), "inner") \
        .select(declarations["*"], lookup_keys.lookup_id)
    candidates = target.select("name", F.struct(F.col("target_version").alias("version"),
                                                  F.lit(0).cast("int").alias("birth_index")).alias("candidate"))
    candidate_groups = candidates.groupBy("name").agg(F.collect_list("candidate").alias("candidates"))
    target_ids = selected.select(F.col("target_name").alias("declared_name"), F.col("package_id").alias("target_package_id")).dropDuplicates()
    grouped = (lookup_keys.join(candidate_groups, lookup_keys.declared_name == candidate_groups.name, "left")
               .join(target_ids, "declared_name", "left")
               .select("declared_name", "requirement", "lookup_id", "target_package_id", "candidates")
               .rdd.map(lambda r: (r.declared_name, {"requirement": r.requirement, "lookup_id": r.lookup_id,
                       "target_package_id": r.target_package_id,
                       "candidates": [x.asDict() for x in (r.candidates or [])]})).groupByKey())
    lookup_schema = T.StructType([T.StructField("lookup_id", T.LongType()), T.StructField("declared_name", T.StringType()), T.StructField("target_package_id", T.IntegerType()), T.StructField("target_version", T.StringType()), T.StructField("requirement", T.StringType()), T.StructField("status", T.StringType()), T.StructField("normalized_range", T.StringType())])
    lookups = grouped.mapPartitions(lambda it: _resolve_names(it, runtime, worker)).toDF(lookup_schema)
    edge_schema = T.StructType([T.StructField("lookup_id", T.LongType()), T.StructField("source_package_id", T.IntegerType()), T.StructField("source_version", T.StringType()),
                                T.StructField("target_package_id", T.IntegerType()), T.StructField("target_version", T.StringType()),
                                T.StructField("requirement", T.StringType()), T.StructField("status", T.StringType()), T.StructField("normalized_range", T.StringType())])
    edges = (declarations.join(lookups, "lookup_id", "inner")
             .select(declarations.lookup_id, declarations.source_package_id, declarations.source_version,
                     lookups.target_package_id, lookups.target_version, declarations.requirement,
                     lookups.status, lookups.normalized_range))
    resolved = edges.where(F.col("status") == "RESOLVED").select("source_package_id", "source_version", "target_package_id", "target_version").dropDuplicates()
    counts = resolved.groupBy("target_package_id", "target_version").count().withColumnRenamed("count", "dependents_count")
    target_keys = target.select(F.col("target_package_id").alias("package_id"), F.col("target_version").alias("version")) \
        .dropDuplicates().withColumn("is_target", F.lit(True))
    counts = counts.select(F.col("target_package_id").alias("package_id"), F.col("target_version").alias("version"), "dependents_count")
    result = (version.join(package, "package_id").select("package_id", "version")
              .join(target_keys, ["package_id", "version"], "left")
              .join(counts, ["package_id", "version"], "left")
              .withColumn("snapshot_at", F.to_date(F.lit(snapshot)))
              .withColumn("dependents_count", F.when(F.col("is_target").isNotNull(), F.coalesce("dependents_count", F.lit(0))).otherwise(F.lit(None).cast("long")))
              .select("package_id", "version", "snapshot_at", "dependents_count"))
    out = str(output).rstrip("/")
    result.write.mode("error").parquet(out + "/version_dependents")
    quality_result = (result.join(package, "package_id")
                      .join(target_keys.select("package_id", "version", "is_target"), ["package_id", "version"], "left")
                      .join(targets, F.col("name") == targets.target_name, "left")
                      .withColumn("null_reason", F.when(F.col("is_target").isNotNull(), F.lit(None).cast("string"))
                                  .when(F.col("target_name").isNull(), F.lit("NOT_SELECTED_TARGET"))
                                  .otherwise(F.lit("INELIGIBLE_TARGET_VERSION")))
                      .select("package_id", "version", "snapshot_at", "dependents_count", "null_reason"))
    quality_result.write.mode("error").parquet(out + "/quality")
    quality_df = quality_result.select(F.count("*").alias("rows"),
                               F.sum(F.when(F.col("dependents_count") == 0, 1).otherwise(0)).alias("zero_rows"),
                               F.sum(F.when(F.col("dependents_count").isNull(), 1).otherwise(0)).alias("null_rows"))
    lookup = (lookups.select("lookup_id", "status", "normalized_range", "target_package_id", "target_version")
              .withColumn("start_index", F.lit(0).cast("int")).withColumn("end_index", F.lit(1).cast("int"))
              .select("lookup_id", "start_index", "end_index", "status", "normalized_range", "target_package_id", "target_version"))
    lookup.write.mode("error").parquet(out + "/resolution_lookup")
    stats = quality_df.first().asDict()
    gap_row = source_quality.select(
        F.sum(F.when(F.col("req_name").isNull(), 1).otherwise(0)).alias("missing_requirements"),
        F.sum(F.when(F.col("req_name").isNotNull() & F.col("Dependencies").isNull(), 1).otherwise(0)).alias("null_dependency_list"),
        F.sum(F.when(F.col("dependency_error") == True, 1).otherwise(0)).alias("extraction_error"),
        F.sum(F.when(F.col("dependency_error").isNull(), 1).otherwise(0)).alias("unknown_extraction_status")).first().asDict()
    unresolved = edges.where(F.col("status") != "RESOLVED").count()
    return {"outputs": {"version_dependents": out + "/version_dependents", "quality": out + "/quality",
                         "resolution_lookup": out + "/resolution_lookup"},
            "quality": {"calculation_status": "COMPLETE", "resolution_status": "PARTIAL" if unresolved or any(gap_row.values()) else "COMPLETE",
                        "rows": stats["rows"], "zero_rows": stats["zero_rows"], "null_rows": stats["null_rows"],
                        "snapshot": snapshot, "unresolved_declarations": unresolved,
                        "source_gaps": {k: int(v or 0) for k, v in gap_row.items()}},
            "resolution_lookup": {"rows": lookups.count()}}
