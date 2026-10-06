package com.ssafy.pickage.domain.curatedload;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.io.ByteArrayInputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.sql.Connection;
import java.sql.DriverManager;
import java.time.LocalDate;
import java.util.HexFormat;
import java.util.List;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.Map;
import java.lang.reflect.Proxy;
import javax.sql.DataSource;

import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.duckdb.DuckDBConnection;
import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.http.AbortableInputStream;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;

/** PostgreSQL contract tests for the Spring Curated publisher. */
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class CuratedBundlePublisherIntegrationTest {
    private DataSource database;
    private Path temporary;

    @BeforeAll
    void connect() {
        String url = System.getenv("CURATED_TEST_DB_URL");
        Assumptions.assumeTrue(url != null && !url.isBlank(), "CURATED_TEST_DB_URL is required");
        Assumptions.assumeTrue(url.equals("jdbc:postgresql://127.0.0.1:15439/curated_load_test")
            || url.equals("jdbc:postgresql://localhost:15439/curated_load_test"),
            "refusing to truncate a non-dedicated Curated test database");
        DriverManagerDataSource ds = new DriverManagerDataSource(url,
            System.getenv().getOrDefault("CURATED_TEST_DB_USER", "postgres"),
            System.getenv().getOrDefault("CURATED_TEST_DB_PASSWORD", "curated-local-only"));
        Flyway.configure().dataSource(ds).load().migrate();
        database = ds;
    }

    @AfterEach
    @org.junit.jupiter.api.BeforeEach
    void clean() throws Exception {
        if (database == null) return;
        try (Connection c = database.getConnection(); var s = c.createStatement()) {
            s.execute("TRUNCATE etl_dataset_current, etl_load_attempt, etl_load_execution, "
                + "etl_curated_load_file_receipt, etl_curated_stage_version_snapshot, "
                + "etl_curated_stage_package_snapshot, etl_curated_stage_version, etl_curated_stage_package, "
                + "package_version_snapshot, package_snapshot, version, package, snapshot CASCADE");
        }
        if (temporary != null) { try (var files = Files.walk(temporary)) { files.sorted(java.util.Comparator.reverseOrder()).forEach(p -> { try { Files.deleteIfExists(p); } catch (Exception ignored) {} }); } temporary = null; }
    }

    @Test
    void null_dependents_is_rejected_and_does_not_publish() throws Exception {
        PreparedBundle bundle = bundle("null-input", LocalDate.of(2099, 1, 1), null, null, null, true);
        assertThatThrownBy(() -> new CuratedBundlePublisher(database).publish(bundle))
            .hasMessageContaining("NULL dependents_count");
        assertThat(count("etl_dataset_current")).isZero();
        assertThat(count("package")).isZero();
        assertThat(jdbc("SELECT count(*) FROM etl_load_execution WHERE status='FAILED'" )).isEqualTo(1);
        assertThat(jdbc("SELECT count(*) FROM etl_load_attempt WHERE status='FAILED'" )).isEqualTo(1);
    }

    @Test
    void calculated_zero_is_kept_and_exact_replay_is_skipped() throws Exception {
        PreparedBundle bundle = bundle("baseline-zero", LocalDate.of(2099, 1, 2), null, null, null, false);
        CuratedBundlePublisher publisher = new CuratedBundlePublisher(database);
        assertThat(publisher.publish(bundle)).isEqualTo("PUBLISHED");
        assertThat(jdbc("SELECT dependents_count FROM package_version_snapshot")).isEqualTo(0);
        jdbcUpdate("UPDATE etl_curated_load_file_receipt SET contract_sha256=repeat('0',64)");
        assertThat(publisher.publish(bundle)).isEqualTo("SKIPPED");
        assertThat(count("etl_load_execution")).isEqualTo(1);
    }

    @Test
    void same_snapshot_with_different_manifest_is_rejected() throws Exception {
        CuratedBundlePublisher publisher = new CuratedBundlePublisher(database);
        publisher.publish(bundle("same-a", LocalDate.of(2099, 1, 3), null, null, null, false));
        assertThatThrownBy(() -> publisher.publish(bundle("same-b", LocalDate.of(2099, 1, 3), null, null, null, false)))
            .hasMessageContaining("not newer");
    }

    @Test
    void weekly_parent_must_match_current_and_nonempty_db_cannot_bootstrap() throws Exception {
        CuratedBundlePublisher publisher = new CuratedBundlePublisher(database);
        PreparedBundle baseline = bundle("parent-base", LocalDate.of(2099, 1, 4), null, null, null, false);
        publisher.publish(baseline);
        assertThatThrownBy(() -> publisher.publish(bundle("wrong-parent", LocalDate.of(2099, 1, 5),
            "wrong-prefix", "0".repeat(64), baseline.snapshot(), false)))
            .hasMessageContaining("parent bundle");

        clean();
        jdbcUpdate("INSERT INTO package(package_id,name) VALUES (99,'already-there')");
        assertThatThrownBy(() -> publisher.publish(bundle("unadopted", LocalDate.of(2099, 1, 6), null, null, null, false)))
            .hasMessageContaining("baseline");
    }

    @Test
    void matching_baseline_can_be_adopted_without_service_mutation_and_mismatch_fails() throws Exception {
        CuratedBundlePublisher publisher = new CuratedBundlePublisher(database);
        PreparedBundle baseline = bundle("adopt-source", LocalDate.of(2099, 1, 7), null, null, null, false);
        publisher.publish(baseline);
        jdbcUpdate("TRUNCATE etl_dataset_current, etl_load_attempt, etl_load_execution CASCADE");
        PreparedBundle adoption = bundle("adopted", baseline.snapshot(), null, null, null, false);
        long packages = count("package");
        assertThat(publisher.adoptBaseline(adoption)).isEqualTo("PUBLISHED");
        assertThat(count("package")).isEqualTo(packages);

        jdbcUpdate("TRUNCATE etl_dataset_current, etl_load_attempt, etl_load_execution CASCADE");
        jdbcUpdate("UPDATE package SET name='tampered' WHERE package_id=1");
        assertThatThrownBy(() -> publisher.adoptBaseline(bundle("adopt-mismatch", baseline.snapshot(), null, null, null, false)))
            .hasMessageContaining("Baseline differs");
    }

    @Test
    void monthly_partition_that_already_covers_snapshot_is_reused() throws Exception {
        try (Connection c = database.getConnection(); var s = c.createStatement()) {
            s.execute("CREATE TABLE IF NOT EXISTS package_version_snapshot_209902 "
                + "PARTITION OF package_version_snapshot FOR VALUES FROM ('2099-02-01') TO ('2099-03-01')");
        }
        assertThat(new CuratedBundlePublisher(database).publish(bundle("monthly", LocalDate.of(2099, 2, 15), null, null, null, false)))
            .isEqualTo("PUBLISHED");
    }

    @Test
    void multiple_shards_of_one_role_accumulate_and_retry_reuses_each_receipt() throws Exception {
        PreparedBundle base = bundle("sharded", LocalDate.of(2099, 3, 15), null, null, null, false);
        Path shard = write("package-shard-2", "2\tbeta\thttps://example.test/beta\n");
        List<PreparedBundle.CopyFile> files = new ArrayList<>(base.files());
        files.add(copy("package", shard, 1, 1, 0));
        PreparedBundle sharded = new PreparedBundle(base.prefix(), base.manifestSha256(), base.runId(),
            base.snapshot(), base.snapshotTimestamp(), base.manifestJson(), base.parentPrefix(),
            base.parentSha256(), base.parentSnapshot(), files, base.excludedDependentsReasons());
        CuratedBundlePublisher publisher = new CuratedBundlePublisher(database);
        assertThat(publisher.publish(sharded)).isEqualTo("PUBLISHED");
        assertThat(count("package")).isEqualTo(2);
        assertThat(jdbc("SELECT count(*) FROM etl_curated_load_file_receipt WHERE role='package'"))
            .isEqualTo(2);
        assertThat(publisher.publish(sharded)).isEqualTo("SKIPPED");
    }

    @Test
    void failure_after_master_upserts_rolls_back_entire_service_change() throws Exception {
        PreparedBundle base = bundle("rollback", LocalDate.of(2099, 4, 1), null, null, null, false);
        Path invalid = write("orphan-snapshot", "999\t" + base.snapshot() + "\t0\t0\t0\n");
        List<PreparedBundle.CopyFile> files = new ArrayList<>(base.files());
        files.set(2, copy("package_snapshot", invalid, 1, 1, 0));
        PreparedBundle bad = replaceFiles(base, files);
        assertThatThrownBy(() -> new CuratedBundlePublisher(database).publish(bad)).isInstanceOf(java.sql.SQLException.class);
        assertThat(count("package")).isZero();
        assertThat(count("version")).isZero();
        assertThat(count("snapshot")).isZero();
        assertThat(count("etl_dataset_current")).isZero();
        assertThat(jdbc("SELECT count(*) FROM etl_load_attempt WHERE status='FAILED'")).isEqualTo(1);
    }

    @Test
    void weekly_with_no_master_changes_still_publishes_metrics() throws Exception {
        CuratedBundlePublisher publisher = new CuratedBundlePublisher(database);
        PreparedBundle baseline = bundle("empty-weekly-base", LocalDate.of(2099, 4, 2), null, null, null, false);
        publisher.publish(baseline);
        PreparedBundle next = bundle("empty-weekly", LocalDate.of(2099, 4, 3), baseline.prefix(), baseline.manifestSha256(), baseline.snapshot(), false);
        List<PreparedBundle.CopyFile> files = new ArrayList<>(next.files());
        files.set(0, copy("package", write("empty-package", ""), 0, 0, 0));
        files.set(1, copy("version", write("empty-version", ""), 0, 0, 0));
        assertThat(publisher.publish(replaceFiles(next, files))).isEqualTo("PUBLISHED");
        assertThat(count("version")).isEqualTo(1);
        assertThat(count("snapshot")).isEqualTo(2);
    }

    @Test
    void publication_persists_dependency_default_quality_summary_separately() throws Exception {
        PreparedBundle base = bundle("dependency-quality", LocalDate.of(2099, 4, 12), null, null, null, false);
        PreparedBundle quality = new PreparedBundle(base.prefix(), base.manifestSha256(), base.runId(), base.snapshot(),
            base.snapshotTimestamp(), base.manifestJson(), base.parentPrefix(), base.parentSha256(), base.parentSnapshot(),
            base.files(), base.excludedDependentsReasons(),
            Map.of("DEPENDENCY_SQL_NULL_DEFAULTED", 7L), "c".repeat(64));
        assertThat(new CuratedBundlePublisher(database).publish(quality)).isEqualTo("PUBLISHED");
        String report = jdbcText("SELECT quality_report::text FROM etl_load_attempt");
        assertThat(report).contains("dependency_defaulted_reasons", "DEPENDENCY_SQL_NULL_DEFAULTED", "dependency_defaulted_input_sha256");
        assertThat(report).contains("excluded_dependents_reasons");
    }

    @Test
    void weekly_replay_does_not_rewrite_unchanged_package_or_version_rows() throws Exception {
        CuratedBundlePublisher publisher = new CuratedBundlePublisher(database);
        PreparedBundle baseline = bundle("stable-base", LocalDate.of(2099, 4, 7), null, null, null, false);
        publisher.publish(baseline);
        String before = jdbcText("SELECT p.xmin::text || ':' || v.xmin::text FROM package p CROSS JOIN version v");

        PreparedBundle weekly = bundle("stable-weekly", LocalDate.of(2099, 4, 8),
            baseline.prefix(), baseline.manifestSha256(), baseline.snapshot(), false);
        assertThat(publisher.publish(weekly)).isEqualTo("PUBLISHED");

        assertThat(jdbcText("SELECT p.xmin::text || ':' || v.xmin::text FROM package p CROSS JOIN version v"))
            .isEqualTo(before);
    }

    @Test
    void weekly_version_change_updates_only_the_changed_master_row() throws Exception {
        CuratedBundlePublisher publisher = new CuratedBundlePublisher(database);
        PreparedBundle baseline = bundle("changed-base", LocalDate.of(2099, 4, 9), null, null, null, false);
        publisher.publish(baseline);
        String before = jdbcText("SELECT xmin::text FROM version WHERE package_id=1 AND version='1.0'");

        PreparedBundle weekly = bundle("changed-weekly", LocalDate.of(2099, 4, 10),
            baseline.prefix(), baseline.manifestSha256(), baseline.snapshot(), false);
        List<PreparedBundle.CopyFile> files = new ArrayList<>(weekly.files());
        files.set(1, copy("version", write("version-changed",
            "1.0\t1\t2026-01-01 00:00:00\t1\tBeta\t{}\t\\N\t{\"dependencies\":{}}\n"), 1, 1, 0));
        assertThat(publisher.publish(replaceFiles(weekly, files))).isEqualTo("PUBLISHED");

        assertThat(jdbcText("SELECT description FROM version WHERE package_id=1 AND version='1.0'"))
            .isEqualTo("Beta");
        assertThat(jdbcText("SELECT xmin::text FROM version WHERE package_id=1 AND version='1.0'"))
            .isNotEqualTo(before);
    }

    @Test
    void reviewed_stage_reuse_keeps_the_old_receipt_contract() throws Exception {
        PreparedBundle base = bundle("proof-retry", LocalDate.of(2099, 4, 11), null, null, null, false);
        CuratedBundlePublisher publisher = new CuratedBundlePublisher(database);
        jdbcUpdate("INSERT INTO package(package_id,name) VALUES(99,'temporary-blocker')");
        assertThatThrownBy(() -> publisher.publish(base)).hasMessageContaining("baseline");
        String execution = jdbcText("SELECT execution_id FROM etl_curated_load_file_receipt LIMIT 1");
        String oldContract = "b".repeat(64);
        jdbcUpdate("UPDATE etl_curated_load_file_receipt SET contract_sha256='" + oldContract + "'");
        jdbcUpdate("DELETE FROM package WHERE package_id=99");

        String proof = "{\"format\":\"curated-stage-reuse-v1\","
            + "\"current_contract_sha256\":\"" + LoadContract.sha256() + "\","
            + "\"previous_contract_sha256\":\"" + oldContract + "\","
            + "\"reviewed_staging_compatible\":true,\"review_evidence\":\"integration test\","
            + "\"execution_id\":\"" + execution + "\",\"manifest_sha256\":\"" + base.manifestSha256() + "\"}";
        Path proofFile = write("stage-reuse-proof", proof);
        String proofSha = fileSha(proofFile);
        String oldPath = System.getProperty("pickage.curated.stage-reuse-proof");
        String oldSha = System.getProperty("pickage.curated.stage-reuse-proof-sha256");
        try {
            System.setProperty("pickage.curated.stage-reuse-proof", proofFile.toString());
            System.setProperty("pickage.curated.stage-reuse-proof-sha256", proofSha);
            assertThat(publisher.publish(base)).isEqualTo("PUBLISHED");
            assertThat(jdbcText("SELECT DISTINCT contract_sha256 FROM etl_curated_load_file_receipt"))
                .isEqualTo(oldContract);
        } finally {
            if (oldPath == null) System.clearProperty("pickage.curated.stage-reuse-proof");
            else System.setProperty("pickage.curated.stage-reuse-proof", oldPath);
            if (oldSha == null) System.clearProperty("pickage.curated.stage-reuse-proof-sha256");
            else System.setProperty("pickage.curated.stage-reuse-proof-sha256", oldSha);
        }
    }

    @Test
    void compatible_python_lock_prevents_concurrent_publication() throws Exception {
        try (Connection c = database.getConnection(); var s = c.createStatement()) {
            s.execute("SELECT pg_advisory_lock(hashtextextended('curated:package-version',0))");
            try {
                assertThatThrownBy(() -> new CuratedBundlePublisher(database).publish(
                    bundle("locked", LocalDate.of(2099, 4, 4), null, null, null, false)))
                    .isInstanceOf(java.sql.SQLException.class).hasMessageContaining("lock is busy");
                assertThat(count("package")).isZero();
            } finally { s.execute("SELECT pg_advisory_unlock_all()"); }
        }
    }

    @Test
    void retry_after_failure_reuses_stage_and_updates_active_attempt() throws Exception {
        PreparedBundle base = bundle("retry", LocalDate.of(2099, 4, 5), null, null, null, false);
        CuratedBundlePublisher publisher = new CuratedBundlePublisher(database);
        jdbcUpdate("INSERT INTO package(package_id,name) VALUES(99,'temporary-blocker')");
        assertThatThrownBy(() -> publisher.publish(base)).hasMessageContaining("baseline");
        long receipts = count("etl_curated_load_file_receipt");
        jdbcUpdate("DELETE FROM package WHERE package_id=99");
        assertThat(publisher.publish(base)).isEqualTo("PUBLISHED");
        assertThat(count("etl_curated_load_file_receipt")).isEqualTo(receipts);
        assertThat(jdbc("SELECT count(*) FROM etl_load_execution e JOIN etl_load_attempt a ON a.attempt_id=e.active_attempt_id WHERE e.status='PUBLISHED' AND a.status='PUBLISHED' AND e.error_message IS NULL")).isEqualTo(1);
        assertThat(jdbc("SELECT count(*) FROM etl_load_attempt WHERE status='FAILED'")).isEqualTo(1);
    }

    @org.junit.jupiter.params.ParameterizedTest
    @org.junit.jupiter.params.provider.CsvSource({
        "UTC,2099-04-06T21:01:10.123456Z",
        "Asia/Seoul,2099-04-06T21:01:10.123456Z",
        "UTC,2099-04-06 21:01:10.123456",
        "Asia/Seoul,2099-04-06 21:01:10.123456"
    })
    void publication_and_failure_timestamps_do_not_depend_on_jvm_timezone(String zone, String timestamp) throws Exception {
        java.util.TimeZone original = java.util.TimeZone.getDefault();
        try {
            java.util.TimeZone.setDefault(java.util.TimeZone.getTimeZone(zone));
            for (boolean failure : new boolean[]{false, true}) {
                clean();
                PreparedBundle b = bundle("timezone-" + failure, LocalDate.of(2099, 4, 6), null, null, null, failure);
                PreparedBundle input = new PreparedBundle(b.prefix(), b.manifestSha256(), b.runId(), b.snapshot(), timestamp,
                        b.manifestJson(), b.parentPrefix(), b.parentSha256(), b.parentSnapshot(), b.files(), b.excludedDependentsReasons());
                CuratedBundlePublisher publisher = new CuratedBundlePublisher(database);
                if (failure) assertThatThrownBy(() -> publisher.publish(input)).hasMessageContaining("NULL dependents_count");
                else assertThat(publisher.publish(input)).isEqualTo("PUBLISHED");
                try (Connection c = database.getConnection(); var s = c.createStatement();
                     var rows = s.executeQuery("SELECT snapshot_timestamp::text,status FROM etl_load_execution")) {
                    assertThat(rows.next()).isTrue();
                    assertThat(rows.getString(1)).isEqualTo("2099-04-06 21:01:10.123456");
                    assertThat(rows.getString(2)).isEqualTo(failure ? "FAILED" : "PUBLISHED");
                }
            }
        } finally { java.util.TimeZone.setDefault(original); }
    }

    @Test
    void streaming_bootstrap_publishes_without_persistent_stage_rows() throws Exception {
        Map<String, byte[]> objects = streamingObjects(false, false);
        String prefix = streamingPrefix();
        CuratedBundleReader reader = new CuratedBundleReader(fakeS3(objects), temporary.resolve("streaming-success"));

        assertThat(new CuratedBundlePublisher(database)
            .publishStreamingBootstrap(reader, prefix, sha(objects.get(prefix + "/run_manifest.json"))).result())
            .isEqualTo("PUBLISHED");
        assertThat(count("package")).isEqualTo(1);
        assertThat(count("version")).isEqualTo(1);
        assertThat(count("snapshot")).isEqualTo(1);
        assertThat(count("package_snapshot")).isEqualTo(1);
        assertThat(count("package_version_snapshot")).isEqualTo(1);
        assertThat(count("etl_curated_stage_package")).isZero();
        assertThat(count("etl_curated_stage_version")).isZero();
        assertThat(count("etl_curated_stage_package_snapshot")).isZero();
        assertThat(count("etl_curated_stage_version_snapshot")).isZero();
        assertThat(count("etl_curated_load_file_receipt")).isZero();
        assertThat(count("etl_dataset_current")).isEqualTo(1);
    }

    @Test
    void streaming_bootstrap_cross_file_duplicate_rolls_back_everything() throws Exception {
        Map<String, byte[]> objects = streamingObjects(true, false);
        String prefix = streamingPrefix();
        CuratedBundleReader reader = new CuratedBundleReader(fakeS3(objects), temporary.resolve("streaming-duplicate"));

        assertThatThrownBy(() -> new CuratedBundlePublisher(database).publishStreamingBootstrap(
            reader, prefix, sha(objects.get(prefix + "/run_manifest.json"))))
            .hasMessageContaining("duplicate key");
        assertThat(count("package")).isZero();
        assertThat(count("version")).isZero();
        assertThat(count("snapshot")).isZero();
        assertThat(count("package_version_snapshot")).isZero();
        assertThat(count("etl_dataset_current")).isZero();
    }

    @Test
    void streaming_bootstrap_last_file_fk_failure_rolls_back_partition_and_rows() throws Exception {
        Map<String, byte[]> objects = streamingObjects(false, true);
        String prefix = streamingPrefix();
        CuratedBundleReader reader = new CuratedBundleReader(fakeS3(objects), temporary.resolve("streaming-failure"));
        jdbcUpdate("DROP TABLE IF EXISTS public.package_version_snapshot_20990501");
        long partitionsBefore = jdbc("SELECT count(*) FROM pg_class WHERE relname='package_version_snapshot_20990501'");
        assertThat(partitionsBefore).isZero();

        assertThatThrownBy(() -> new CuratedBundlePublisher(database).publishStreamingBootstrap(
            reader, prefix, sha(objects.get(prefix + "/run_manifest.json"))))
            .isInstanceOf(java.sql.SQLException.class);
        assertThat(count("package")).isZero();
        assertThat(count("version")).isZero();
        assertThat(count("snapshot")).isZero();
        assertThat(count("package_snapshot")).isZero();
        assertThat(count("package_version_snapshot")).isZero();
        assertThat(count("etl_dataset_current")).isZero();
        assertThat(jdbc("SELECT count(*) FROM pg_class WHERE relname='package_version_snapshot_20990501'")).isEqualTo(partitionsBefore);
    }

    @Test
    void streaming_bootstrap_rejects_nonempty_service() throws Exception {
        Map<String, byte[]> nonemptyObjects = streamingObjects(false, false);
        String prefix = streamingPrefix();
        jdbcUpdate("INSERT INTO package(package_id,name) VALUES (99,'existing')");
        CuratedBundleReader nonemptyReader = new CuratedBundleReader(fakeS3(nonemptyObjects), temporary.resolve("streaming-nonempty"));
        assertThatThrownBy(() -> new CuratedBundlePublisher(database).publishStreamingBootstrap(
            nonemptyReader, prefix, sha(nonemptyObjects.get(prefix + "/run_manifest.json"))))
            .hasMessageContaining("empty service database");
        assertThat(count("package")).isEqualTo(1);
    }

    @Test
    void streaming_bootstrap_rejects_parent_bundle_from_reader_contract() throws Exception {
        Map<String, byte[]> objects = streamingObjects(false, false);
        String prefix = streamingPrefix();
        ObjectMapper json = new ObjectMapper();
        ObjectNode manifest = (ObjectNode) json.readTree(objects.get(prefix + "/run_manifest.json"));
        manifest.with("request").set("parent_bundle", json.createObjectNode()
            .put("run_prefix", "depsdev/v1/curated-bundle/snapshot=2099-04-30/run_id=old")
            .put("manifest_sha256", "a".repeat(64)).put("snapshot", "2099-04-30"));
        byte[] bytes = json.writeValueAsBytes(manifest);
        objects.put(prefix + "/run_manifest.json", bytes);
        objects.put(prefix + "/_SUCCESS", ("{\"manifest_sha256\":\"" + sha(bytes) + "\"}").getBytes());
        CuratedBundleReader reader = new CuratedBundleReader(fakeS3(objects), temporary.resolve("streaming-parent"));
        assertThatThrownBy(() -> new CuratedBundlePublisher(database).publishStreamingBootstrap(reader, prefix, sha(bytes)))
            .hasMessageContaining("must not declare a parent");
        assertThat(count("package")).isZero();
        assertThat(count("snapshot")).isZero();
    }

    @Test
    void streaming_bootstrap_rejects_snapshot_date_mismatch_without_rows() throws Exception {
        Map<String, byte[]> objects = streamingObjects(false, false, true, false);
        String prefix = streamingPrefix();
        CuratedBundleReader reader = new CuratedBundleReader(fakeS3(objects), temporary.resolve("streaming-date"));
        assertThatThrownBy(() -> new CuratedBundlePublisher(database).publishStreamingBootstrap(reader, prefix, sha(objects.get(prefix + "/run_manifest.json"))))
            .isInstanceOf(java.sql.SQLException.class);
        assertThat(count("package")).isZero();
        assertThat(count("snapshot")).isZero();
        assertThat(count("etl_dataset_current")).isZero();
    }

    @Test
    void streaming_bootstrap_keeps_null_dependents_exclusion_with_quality_evidence() throws Exception {
        Map<String, byte[]> objects = streamingObjects(false, false, false, true);
        String prefix = streamingPrefix();
        CuratedBundleReader reader = new CuratedBundleReader(fakeS3(objects), temporary.resolve("streaming-null"));
        assertThat(new CuratedBundlePublisher(database).publishStreamingBootstrap(reader, prefix, sha(objects.get(prefix + "/run_manifest.json"))).result())
            .isEqualTo("PUBLISHED");
        assertThat(count("package_version_snapshot")).isZero();
        assertThat(jdbc("SELECT count(*) FROM etl_load_attempt WHERE quality_report::text LIKE '%NOT_SELECTED_TARGET%'")).isEqualTo(1);
    }

    @Test
    void bootstrap_chunks_match_original_transport_and_release_each_chunk() throws Exception {
        Map<String, byte[]> objects = streamingObjects(false, false);
        Path wide = temporary.resolve("wide.parquet");
        putParquet(wide, "CREATE TABLE t(version VARCHAR,package_id INTEGER,published_at TIMESTAMP,ordinal BIGINT,description VARCHAR,licenses JSON,deprecated VARCHAR,dependency JSON);"
            + "INSERT INTO t SELECT i::VARCHAR || '.0',1,TIMESTAMP '2026-01-01',i,repeat('description',8),'{}',NULL,'{}' FROM range(1,21) r(i);");
        objects.put("stage/version.parquet", Files.readAllBytes(wide));
        putStreamingManifest(objects);
        String prefix = streamingPrefix(), hash = sha(objects.get(prefix + "/run_manifest.json"));
        CuratedBundleReader original = new CuratedBundleReader(fakeS3(objects), temporary.resolve("oracle"));
        PreparedBundle expected = original.prepare(prefix, hash);
        java.util.Map<String, java.util.List<String>> wanted = new java.util.HashMap<>();
        for (var file : expected.files()) wanted.computeIfAbsent(file.role(), k -> new java.util.ArrayList<>()).addAll(Files.readAllLines(file.path()));
        java.util.Map<String, java.util.List<String>> got = new java.util.HashMap<>();
        java.util.List<Path> consumed = new java.util.ArrayList<>();
        String previous = System.getProperty("pickage.curated.bootstrap-copy-chunk-bytes");
        System.setProperty("pickage.curated.bootstrap-copy-chunk-bytes", "256");
        try {
            PreparedBundle actual = new CuratedBundleReader(fakeS3(objects), temporary.resolve("chunked"))
                .prepareBootstrapStreaming(prefix, hash, (partial, file) -> {
                    for (Path old : consumed) assertThat(Files.exists(old)).isFalse();
                    assertThat(Files.size(file.path())).isLessThanOrEqualTo(256);
                    got.computeIfAbsent(file.role(), k -> new java.util.ArrayList<>()).addAll(Files.readAllLines(file.path()));
                    consumed.add(file.path());
                });
            for (String role : wanted.keySet()) {
                assertThat(got.get(role)).containsExactlyInAnyOrderElementsOf(wanted.get(role));
                assertThat(actual.files().stream().filter(f -> f.role().equals(role)).mapToLong(PreparedBundle.CopyFile::sourceRows).sum())
                    .isEqualTo(expected.files().stream().filter(f -> f.role().equals(role)).mapToLong(PreparedBundle.CopyFile::sourceRows).sum());
            }
            assertThat(actual.files().stream().filter(f -> f.role().equals("version")).count()).isGreaterThan(1);
            for (Path old : consumed) assertThat(Files.exists(old)).isFalse();
            assertThat(new CuratedBundlePublisher(database).publishStreamingBootstrap(
                new CuratedBundleReader(fakeS3(objects), temporary.resolve("publish-chunks")), prefix, hash).result())
                .isEqualTo("PUBLISHED");
            assertThat(count("version")).isEqualTo(20);
            assertThat(count("etl_curated_stage_version")).isZero();
            java.util.concurrent.atomic.AtomicInteger failedCalls = new java.util.concurrent.atomic.AtomicInteger();
            assertThatThrownBy(() -> new CuratedBundleReader(fakeS3(objects), temporary.resolve("chunk-failure"))
                .prepareBootstrapStreaming(prefix, hash, (partial, file) -> {
                    if (file.role().equals("version")) {
                        failedCalls.incrementAndGet();
                        throw new java.io.IOException("injected chunk failure");
                    }
                })).hasMessageContaining("injected chunk failure");
            assertThat(failedCalls.get()).isEqualTo(1);
        } finally {
            if (previous == null) System.clearProperty("pickage.curated.bootstrap-copy-chunk-bytes");
            else System.setProperty("pickage.curated.bootstrap-copy-chunk-bytes", previous);
            original.cleanupActiveAttempt();
        }
    }

    private String streamingPrefix() {
        return "depsdev/v1/curated-bundle/snapshot=2099-05-01/run_id=streaming-test";
    }

    private Map<String, byte[]> streamingObjects(boolean duplicatePackage, boolean orphanDependent) throws Exception {
        return streamingObjects(duplicatePackage, orphanDependent, false, false);
    }

    private Map<String, byte[]> streamingObjects(boolean duplicatePackage, boolean orphanDependent,
                                                 boolean dateMismatch, boolean nullDependent) throws Exception {
        temporary = Files.createTempDirectory("curated-streaming-");
        Path source = temporary.resolve("source");
        Files.createDirectories(source);
        putParquet(source.resolve("package.parquet"),
            "CREATE TABLE t(package_id INTEGER,name VARCHAR,repo_url VARCHAR);"
                + "INSERT INTO t VALUES (1,'alpha',NULL);");
        putParquet(source.resolve("version.parquet"),
            "CREATE TABLE t(version VARCHAR,package_id INTEGER,published_at TIMESTAMP,ordinal BIGINT,description VARCHAR,licenses JSON,deprecated VARCHAR,dependency JSON);"
                + "INSERT INTO t VALUES ('1.0',1,'2026-01-01 00:00:00',1,'Alpha','{}',NULL,'{\"dependencies\":{}}');");
        putParquet(source.resolve("package_snapshot.parquet"),
            "CREATE TABLE t(package_id INTEGER,snapshot_at DATE,downloads BIGINT,stars INTEGER,open_issues INTEGER);"
                + "INSERT INTO t VALUES (1,'" + (dateMismatch ? "2099-05-02" : "2099-05-01") + "',0,2,1);");
        putParquet(source.resolve("version_dependents.parquet"),
            "CREATE TABLE t(package_id INTEGER,version VARCHAR,snapshot_at DATE,dependents_count BIGINT);"
                + "INSERT INTO t VALUES (" + (orphanDependent ? "99" : "1") + ",'1.0','2099-05-01'," + (nullDependent ? "NULL" : "0") + ");");
        putParquet(source.resolve("quality.parquet"),
            "CREATE TABLE t(package_id INTEGER,version VARCHAR,snapshot_at DATE,dependents_count BIGINT,null_reason VARCHAR);"
                + "INSERT INTO t VALUES (1,'1.0','2099-05-01'," + (nullDependent ? "NULL,'NOT_SELECTED_TARGET'" : "0,NULL") + ");");
        Map<String, byte[]> objects = new HashMap<>();
        objects.put("stage/package.parquet", Files.readAllBytes(source.resolve("package.parquet")));
        objects.put("stage/version.parquet", Files.readAllBytes(source.resolve("version.parquet")));
        objects.put("stage/package_snapshot.parquet", Files.readAllBytes(source.resolve("package_snapshot.parquet")));
        objects.put("stage/version_dependents.parquet", Files.readAllBytes(source.resolve("version_dependents.parquet")));
        objects.put("stage/quality.parquet", Files.readAllBytes(source.resolve("quality.parquet")));
        if (duplicatePackage) {
            putParquet(source.resolve("package-duplicate.parquet"),
                "CREATE TABLE t(package_id INTEGER,name VARCHAR,repo_url VARCHAR);"
                    + "INSERT INTO t VALUES (1,'duplicate',NULL);");
            objects.put("stage/shards/package.parquet", Files.readAllBytes(source.resolve("package-duplicate.parquet")));
        }
        putStreamingManifest(objects);
        return objects;
    }

    private void putStreamingManifest(Map<String, byte[]> objects) throws Exception {
        ObjectMapper json = new ObjectMapper();
        ObjectNode bundle = json.createObjectNode().put("format_version", 1).put("dataset", "curated-bundle")
            .put("status", "COMPLETE").put("scope", "RAW_TO_CURATED_ONLY").put("calculation_complete", true).put("db_loaded", false);
        bundle.putObject("request").put("format_version", 1).put("run_id", "streaming-test")
            .put("snapshot", "2099-05-01").put("snapshot_timestamp", "2099-05-01T00:00:00Z").putNull("parent");
        ObjectNode stages = bundle.putObject("stages");
        for (String stage : new String[]{"snapshot", "package_version", "downloads", "repository", "package_snapshot", "dependents"}) {
            ObjectNode descriptor = stages.putObject(stage).put("stage", stage).put("run_id", "streaming-test")
                .put("snapshot", "2099-05-01").put("status", "PASSED");
            String manifestKey = "stage-manifest/" + stage + ".json";
            String markerKey = "stage-marker/" + stage;
            descriptor.put("manifest_key", manifestKey);
            descriptor.put("marker_key", markerKey);
            ArrayNode files = descriptor.putArray("files");
            if (stage.equals("package_version")) {
                add(files, "stage/package.parquet", objects.get("stage/package.parquet"), "package");
                add(files, "stage/version.parquet", objects.get("stage/version.parquet"), "version");
                if (objects.containsKey("stage/shards/package.parquet")) add(files, "stage/shards/package.parquet", objects.get("stage/shards/package.parquet"), "package");
            } else if (stage.equals("package_snapshot")) {
                add(files, "stage/package_snapshot.parquet", objects.get("stage/package_snapshot.parquet"), "package_snapshot");
            } else if (stage.equals("dependents")) {
                add(files, "stage/version_dependents.parquet", objects.get("stage/version_dependents.parquet"), "version_dependents");
                add(files, "stage/quality.parquet", objects.get("stage/quality.parquet"), "quality");
            } else {
                String dummy = "stage/dummy-" + stage + ".json";
                objects.put(dummy, "{}".getBytes());
                add(files, dummy, objects.get(dummy), "dummy");
            }
            ObjectNode stageBody = json.createObjectNode().put("status", "PASSED");
            stageBody.set("files", files.deepCopy());
            byte[] stageManifest = json.writeValueAsBytes(stageBody);
            objects.put(manifestKey, stageManifest);
            descriptor.put("manifest_sha256", sha(stageManifest));
            byte[] marker = ("{\"manifest_sha256\":\"" + sha(stageManifest) + "\"}").getBytes();
            objects.put(markerKey, marker);
            descriptor.put("marker_sha256", sha(marker));
        }
        byte[] manifest = json.writeValueAsBytes(bundle);
        String prefix = streamingPrefix();
        objects.put(prefix + "/run_manifest.json", manifest);
        objects.put(prefix + "/_SUCCESS", ("{\"manifest_sha256\":\"" + sha(manifest) + "\"}").getBytes());
    }

    private void putParquet(Path path, String sql) throws Exception {
        try (Connection connection = DriverManager.getConnection("jdbc:duckdb:" + path.resolveSibling(path.getFileName() + ".db"));
             var statement = connection.createStatement()) {
            statement.execute(sql);
            statement.execute("COPY t TO '" + path.toString().replace("'", "''") + "' (FORMAT PARQUET)");
        }
    }

    private static void add(ArrayNode files, String key, byte[] body, String role) {
        files.addObject().put("key", key).put("role", role).put("bytes", body.length).put("sha256", sha(body));
    }

    private static S3Client fakeS3(Map<String, byte[]> objects) {
        return (S3Client) Proxy.newProxyInstance(S3Client.class.getClassLoader(), new Class[]{S3Client.class}, (proxy, method, args) -> {
            if (method.getName().equals("getObject")) {
                var request = (software.amazon.awssdk.services.s3.model.GetObjectRequest) args[0];
                byte[] body = objects.get(request.key());
                if (body == null) throw software.amazon.awssdk.services.s3.model.NoSuchKeyException.builder().statusCode(404).message("missing fake object").build();
                return new ResponseInputStream<>(GetObjectResponse.builder().build(), AbortableInputStream.create(new ByteArrayInputStream(body)));
            }
            if (method.getName().equals("close")) return null;
            if (method.getName().equals("serviceName")) return "S3";
            if (method.getName().equals("toString")) return "fake-s3";
            if (method.getName().equals("hashCode")) return System.identityHashCode(proxy);
            if (method.getName().equals("equals")) return proxy == args[0];
            throw new UnsupportedOperationException(method.toString());
        });
    }

    private PreparedBundle replaceFiles(PreparedBundle b, List<PreparedBundle.CopyFile> files) {
        return new PreparedBundle(b.prefix(), b.manifestSha256(), b.runId(), b.snapshot(), b.snapshotTimestamp(),
            b.manifestJson(), b.parentPrefix(), b.parentSha256(), b.parentSnapshot(), files, b.excludedDependentsReasons());
    }

    private PreparedBundle bundle(String run, LocalDate snapshot, String parentPrefix,
                                  String parentSha, LocalDate parentSnapshot, boolean nullDependent) throws Exception {
        temporary = Files.createTempDirectory("curated-publisher-");
        String suffix = snapshot.toString().replace('-', '_') + "_" + run;
        Path packageFile = write("package", "1\talpha\t\\N\n");
        Path versionFile = write("version", "1.0\t1\t2026-01-01 00:00:00\t1\tAlpha\t{}\t\\N\t{\"dependencies\":{}}\n");
        Path packageSnapshotFile = write("package-snapshot", "1\t" + snapshot + "\t0\t2\t1\n");
        String dependent = nullDependent ? "\\N" : "0";
        Path versionSnapshotFile = write("version-snapshot", "1\t1.0\t" + snapshot + "\t" + dependent + "\n");
        List<PreparedBundle.CopyFile> files = List.of(
            copy("package", packageFile, 1, 1, 0), copy("version", versionFile, 1, 1, 0),
            copy("package_snapshot", packageSnapshotFile, 1, 1, 0), copy("version_snapshot", versionSnapshotFile, nullDependent ? 2 : 1, 1, nullDependent ? 1 : 0));
        return new PreparedBundle("depsdev/v1/curated-bundle/snapshot=" + snapshot + "/run_id=" + run,
            sha("manifest-" + suffix), run, snapshot, snapshot + " 00:00:00", "{\"status\":\"COMPLETE\"}",
            parentPrefix, parentSha, parentSnapshot, files, Map.of());
    }

    private PreparedBundle.CopyFile copy(String role, Path path, long source, long loaded, long excluded) throws Exception {
        return new PreparedBundle.CopyFile(role, path, fileSha(path), source, loaded, excluded);
    }
    private Path write(String name, String value) throws Exception { Path p = temporary.resolve(name + ".copy"); Files.writeString(p, value); return p; }
    private static String fileSha(Path p) throws Exception { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(p))); }
    private static String sha(byte[] value) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value)); }
        catch (Exception e) { throw new IllegalStateException(e); }
    }
    private static String sha(String value) throws Exception { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes())); }
    private long count(String table) { return jdbc("SELECT count(*) FROM " + table); }
    private long jdbc(String sql) { return new org.springframework.jdbc.core.JdbcTemplate(database).queryForObject(sql, Long.class); }
    private String jdbcText(String sql) { return new org.springframework.jdbc.core.JdbcTemplate(database).queryForObject(sql, String.class); }
    private void jdbcUpdate(String sql) { new org.springframework.jdbc.core.JdbcTemplate(database).update(sql); }
}
