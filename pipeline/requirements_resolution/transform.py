"""Spark stages preserving all observed source versions and declaration outcomes."""
from pathlib import Path

from pyspark import StorageLevel
from pyspark.sql import functions as F

from .policy import validate_policy

SOURCE_KEY = ["source_package_id", "source_version"]
EDGE_KEY = ["snapshot_at", *SOURCE_KEY, "target_package_id", "target_version"]
MAPPING_COLUMNS = ["lookup_id", "declared_name", "requirement", "normalized_range", "target_version", "status"]
MAPPING_STATUSES = ["RESOLVED", "INVALID_PACKAGE_NAME", "INVALID_SPEC", "UNSUPPORTED_ALIAS",
                    "UNSUPPORTED_TAG", "UNSUPPORTED_GIT", "UNSUPPORTED_FILE", "UNSUPPORTED_URL",
                    "NO_ELIGIBLE_TARGET", "NO_SATISFYING_VERSION"]


def _read(spark, inputs, table):
    paths = inputs.get("files", {}).get(table)
    if not isinstance(paths, list) or not paths:
        raise ValueError("Missing input file list: " + table)
    return spark.read.parquet(*paths)


def _zero(frame, message):
    if frame.limit(1).count():
        raise ValueError(message)


def _unique(frame, keys, label):
    _zero(frame.groupBy(*keys).count().where(F.col("count") > 1), "Duplicate " + label)


def _write(spark, frame, output, group):
    path = Path(output) / group
    frame.write.mode("errorifexists").option("maxRecordsPerFile", 250000).parquet(str(path))
    # Read the materialized file rather than repeatedly evaluating the source DAG.
    return spark.read.parquet(str(path))


def _timestamp(value):
    return F.to_timestamp(F.lit(value))


def prepare(spark, inputs, policy, output):
    doc = validate_policy(policy)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    timestamp = _timestamp(inputs["snapshot_timestamp"])
    package = _read(spark, inputs, "package").select("package_id", "name")
    version = _read(spark, inputs, "version").select("package_id", "version", "published_at")
    raw = _read(spark, inputs, "versions_full").select(
        "SnapshotAt", F.col("Name").alias("raw_name"), F.col("Version").alias("raw_version"),
        "is_release", F.col("published_at").alias("raw_published_at"), "dependency_error")
    req = _read(spark, inputs, "requirements").select(
        "SnapshotAt", F.col("Name").alias("source_name"), F.col("Version").alias("source_version"),
        "Dependencies", "PeerDependencies", "OptionalDependencies")
    _zero(package.where(F.col("package_id").isNull() | (F.col("package_id") <= 0)
                        | F.col("name").isNull() | (F.length(F.trim("name")) == 0)), "Invalid package identity")
    _zero(version.where(F.col("package_id").isNull() | F.col("version").isNull()
                        | (F.length(F.trim("version")) == 0)), "Invalid version identity")
    _unique(package, ["package_id"], "package ID")
    _unique(package, ["name"], "package name")
    _unique(version, ["package_id", "version"], "Curated version")
    _zero(version.join(package.select("package_id"), "package_id", "left_anti"), "Orphan Curated version")
    _unique(raw, ["raw_name", "raw_version"], "raw version")
    _unique(req, ["source_name", "source_version"], "requirements")
    for frame in (raw, req):
        _zero(frame.where(F.col("SnapshotAt").isNull() | (F.col("SnapshotAt") != timestamp)),
              "NULL or wrong raw SnapshotAt")
    _zero(raw.where(F.col("raw_name").isNull() | F.col("raw_version").isNull()), "Invalid raw version key")
    _zero(req.where(F.col("source_name").isNull() | F.col("source_version").isNull()), "Invalid requirements key")

    # A left join and explicit proof prevent an input mismatch from silently
    # deleting eligible Curated versions.
    proof = (version.join(package, "package_id")
             .join(raw, (F.col("name") == F.col("raw_name")) & (F.col("version") == F.col("raw_version")), "left")
             .persist(StorageLevel.DISK_ONLY))
    try:
        _zero(proof.where(F.col("raw_name").isNull() | ~F.col("is_release").eqNullSafe(F.lit(True))
                          | ~F.col("published_at").eqNullSafe(F.col("raw_published_at"))),
              "Curated version lacks matching raw release/date provenance")
        eligible = proof.where(F.col("published_at").isNull() | (F.col("published_at") <= timestamp))
        excluded_unknown = 0
        if doc["unknown_published_at"] == "exclude":
            excluded_unknown = eligible.where(F.col("published_at").isNull()).count()
            eligible = eligible.where(F.col("published_at").isNotNull())
        candidates = _write(spark, eligible.select("package_id", "name", "version", "published_at",
                             F.col("published_at").isNull().alias("published_at_unknown")),
                            output, "candidates")
        source_base = eligible.select(F.col("package_id").alias("source_package_id"),
                    F.col("version").alias("source_version"), F.col("name").alias("source_name"),
                    "published_at", F.col("published_at").isNull().alias("published_at_unknown"), "dependency_error")
        expanded = (source_base.join(req.drop("SnapshotAt").withColumn("requirements_present", F.lit(True)),
                                     ["source_name", "source_version"], "left")
                    .withColumn("requirements_present", F.coalesce("requirements_present", F.lit(False)))
                    .withColumn("selected_list_null", F.col("requirements_present") & F.col("Dependencies").isNull())
                    .withColumn("declaration_count", F.when(F.col("Dependencies").isNull(), 0).otherwise(F.size("Dependencies")).cast("long"))
                    .withColumn("excluded_peer_count", F.when(F.col("PeerDependencies").isNull(), None).otherwise(F.size("PeerDependencies")).cast("long"))
                    .withColumn("excluded_optional_count", F.when(F.col("OptionalDependencies").isNull(), None).otherwise(F.size("OptionalDependencies")).cast("long"))
                    .withColumn("source_processing_status", F.when(F.col("dependency_error") == True, "ERROR")
                                .when(F.col("dependency_error").isNull(), "UNKNOWN").otherwise("NO_RECORDED_ERROR"))
                    .persist(StorageLevel.DISK_ONLY))
        try:
            sources = _write(spark, expanded.drop("Dependencies", "PeerDependencies", "OptionalDependencies"),
                             output, "sources")
            declarations = (expanded.select(*SOURCE_KEY, F.posexplode("Dependencies").alias("declaration_index", "item"))
                            .select(*SOURCE_KEY, F.lit("dependencies").alias("kind"), "declaration_index",
                                    F.col("item.Name").alias("declared_name"), F.col("item.Requirement").alias("requirement"))
                            .withColumn("lookup_id", F.sha2(F.to_json(F.struct("declared_name", "requirement"),
                                                                    {"ignoreNullFields": "false"}), 256)))
            declarations = _write(spark, declarations, output, "declarations")
        finally:
            expanded.unpersist()
    finally:
        proof.unpersist()
    counts = {key: frame.count() for key, frame in
              (("sources", sources), ("declarations", declarations), ("candidates", candidates))}
    if not counts["sources"]:
        raise ValueError("No eligible source versions; refusing an empty population")
    summary = sources.agg(F.sum("declaration_count").alias("declared"),
                         F.sum("excluded_peer_count").alias("peers"),
                         F.sum("excluded_optional_count").alias("optional")).first()
    if summary["declared"] != counts["declarations"] or counts["sources"] != counts["candidates"]:
        raise ValueError("Source, declaration, and candidate counts disagree")
    return {"counts": counts, "excluded_unknown_publication_versions": excluded_unknown,
            "excluded_kind_counts": {"peerDependencies": summary["peers"] or 0,
                                     "optionalDependencies": summary["optional"] or 0},
            "metadata": {"dependencies_processed_available": False, "upstream_source_processing_verified": False},
            "snapshot": inputs["snapshot"], "input_sha256": inputs["input_sha256"], "policy_sha256": policy["sha256"]}


def _lineage(frame, inputs, policy, run_id):
    fields = {"snapshot_at": F.to_date(F.lit(inputs["snapshot"])),
              "snapshot_timestamp": _timestamp(inputs["snapshot_timestamp"]),
              "run_id": F.lit(run_id), "input_sha256": F.lit(inputs["input_sha256"]),
              "curated_run_id": F.lit(inputs["curated_run_id"]), "bronze_run_id": F.lit(inputs["bronze_run_id"]),
              "policy_sha256": F.lit(policy["sha256"])}
    for key, expression in fields.items():
        frame = frame.withColumn(key, expression)
    return frame


def finalize(spark, prepared_dir, bridge_dir, inputs, policy, output, run_id):
    doc = validate_policy(policy)
    prepared_dir, bridge_dir, output = map(Path, (prepared_dir, bridge_dir, output))
    output.mkdir(parents=True, exist_ok=False)
    source = spark.read.parquet(str(prepared_dir / "sources"))
    declarations = spark.read.parquet(str(prepared_dir / "declarations"))
    candidates = spark.read.parquet(str(prepared_dir / "candidates"))
    mapping = spark.read.parquet(str(bridge_dir / "mappings"))
    target_quality = spark.read.parquet(str(bridge_dir / "target_quality"))
    if set(mapping.columns) != set(MAPPING_COLUMNS) or any(field.dataType.simpleString() != "string" for field in mapping.schema):
        raise ValueError("Unexpected bridge mapping schema")
    _unique(mapping, ["lookup_id"], "bridge lookup")
    _zero(mapping.where(F.col("lookup_id").isNull() | F.col("status").isNull()
                        | ~F.col("status").isin(MAPPING_STATUSES)), "Invalid bridge status or lookup ID")
    _zero(mapping.where(((F.col("status") == "RESOLVED") & F.col("target_version").isNull())
                        | ((F.col("status") != "RESOLVED") & F.col("target_version").isNotNull())),
          "Bridge target version disagrees with resolution status")
    lookups = declarations.select("lookup_id", "declared_name", "requirement").distinct()
    _unique(lookups, ["lookup_id"], "declaration lookup")
    _zero(lookups.join(mapping.select("lookup_id"), "lookup_id", "left_anti"), "Missing bridge lookup")
    _zero(mapping.join(lookups.select("lookup_id"), "lookup_id", "left_anti"), "Unexpected bridge lookup")
    joined = declarations.join(mapping.select("lookup_id", F.col("declared_name").alias("bridge_name"),
                                F.col("requirement").alias("bridge_requirement"), "normalized_range", "target_version", "status"),
                               "lookup_id", "inner")
    _zero(joined.where(~F.col("declared_name").eqNullSafe(F.col("bridge_name"))
                       | ~F.col("requirement").eqNullSafe(F.col("bridge_requirement"))),
          "Bridge changed original declaration fields")
    targets = candidates.select(F.col("name").alias("target_name"), F.col("version").alias("candidate_version"),
                                F.col("package_id").alias("target_package_id"),
                                F.col("published_at_unknown").alias("target_published_at_unknown"))
    outcome = joined.join(targets, (F.col("declared_name") == F.col("target_name"))
                          & (F.col("target_version") == F.col("candidate_version")), "left")
    _zero(outcome.where((F.col("status") == "RESOLVED") & F.col("target_package_id").isNull()),
          "RESOLVED bridge target is absent from eligible candidates")
    known = _read(spark, inputs, "package").select(F.col("name").alias("known_target_name"))
    outcome = (outcome.join(known, F.col("declared_name") == F.col("known_target_name"), "left")
               .withColumn("status", F.when((F.col("status") == "NO_ELIGIBLE_TARGET") & F.col("known_target_name").isNull(),
                                            "UNMAPPED_TARGET_PACKAGE").otherwise(F.col("status")))
               .select("lookup_id", *SOURCE_KEY, "kind", "declaration_index", "declared_name", "requirement",
                       "normalized_range", "status", "target_package_id", "target_version", "target_published_at_unknown"))
    outcomes = _write(spark, _lineage(outcome, inputs, policy, run_id), output, "declaration_outcomes")
    expected_declarations = declarations.count()
    if outcomes.count() != expected_declarations:
        raise ValueError("Final declaration count differs from prepared declarations")
    _unique(outcomes, [*SOURCE_KEY, "kind", "declaration_index"], "declaration outcome")
    aggregates = outcomes.groupBy(*SOURCE_KEY).agg(F.count("*").alias("observed_declaration_count"),
                   F.sum(F.when(F.col("status") == "RESOLVED", 1).otherwise(0)).cast("long").alias("resolved_count"))
    source_outcomes = (source.join(aggregates, SOURCE_KEY, "left")
                       .fillna(0, ["observed_declaration_count", "resolved_count"])
                       .withColumn("unresolved_count", F.col("declaration_count") - F.col("resolved_count")))
    _zero(source_outcomes.where(F.col("observed_declaration_count") != F.col("declaration_count")),
          "A source declaration was dropped or multiplied")
    source_outcomes = source_outcomes.withColumn("status",
        F.when(~F.col("requirements_present"), "MISSING_REQUIREMENTS")
         .when(F.col("selected_list_null"), "NULL_DEPENDENCY_LIST")
         .when(F.col("dependency_error") == True, "DEPENDENCY_EXTRACTION_ERROR")
         .when(F.col("dependency_error").isNull(), "DEPENDENCY_EXTRACTION_UNKNOWN")
         .when(F.col("declaration_count") == 0, "OBSERVED_NO_DEPENDENCIES")
         .when(F.col("resolved_count") == F.col("declaration_count"), "RESOLVED")
         .when(F.col("resolved_count") > 0, "PARTIAL").otherwise("UNRESOLVED"))
    source_outcomes = _write(spark, _lineage(source_outcomes, inputs, policy, run_id), output, "source_outcomes")
    _unique(source_outcomes, SOURCE_KEY, "source outcome")
    source_count = source.count()
    if source_count != source_outcomes.count():
        raise ValueError("Eligible source population changed")
    edges = (outcomes.where(F.col("status") == "RESOLVED").groupBy(*EDGE_KEY)
             .agg(F.sort_array(F.collect_set("kind")).alias("dependency_kinds"),
                  F.count("*").cast("long").alias("declaration_count")))
    edges = _write(spark, _lineage(edges, inputs, policy, run_id), output, "edges")
    quality = _write(spark, _lineage(target_quality, inputs, policy, run_id), output, "target_quality")
    _unique(edges, EDGE_KEY, "edge")
    source_status_counts = {row["status"]: row["count"] for row in source_outcomes.groupBy("status").count().collect()}
    declaration_status_counts = {row["status"]: row["count"] for row in outcomes.groupBy("status").count().collect()}
    resolved = declaration_status_counts.get("RESOLVED", 0)
    unresolved = expected_declarations - resolved
    counted_edges = edges.agg(F.sum("declaration_count")).first()[0] or 0
    if counted_edges != resolved:
        raise ValueError("Edge counts do not reconcile to resolved declarations")
    complete = unresolved == 0 and sum(source_status_counts.get(s, 0) for s in
               ("MISSING_REQUIREMENTS", "NULL_DEPENDENCY_LIST", "DEPENDENCY_EXTRACTION_ERROR", "DEPENDENCY_EXTRACTION_UNKNOWN")) == 0
    if not complete and doc["unresolved"] == "fail":
        raise ValueError("Incomplete source or unresolved declaration under fail policy")
    return {"output_counts": {"declaration_outcomes": expected_declarations, "source_outcomes": source_count,
                             "edges": edges.count(), "target_quality": quality.count()},
            "selected_declarations": expected_declarations, "resolved_declarations": resolved,
            "unresolved_declarations": unresolved, "source_status_counts": source_status_counts,
            "declaration_status_counts": declaration_status_counts,
            "resolution_status": "COMPLETE" if complete else "PARTIAL", "ready_for_dependents": complete,
            "metadata": {"dependencies_processed_available": False, "upstream_source_processing_verified": False,
                         "metric_scope": "observed_declared_requirements_under_selected_resolver_policy"},
            "snapshot": inputs["snapshot"], "run_id": run_id, "input_sha256": inputs["input_sha256"],
            "curated_run_id": inputs["curated_run_id"], "bronze_run_id": inputs["bronze_run_id"],
            "policy_sha256": policy["sha256"]}
