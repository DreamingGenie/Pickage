package com.ssafy.pickage.domain.curatedload;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.sql.Connection;
import java.time.LocalDate;
import java.util.HexFormat;
import java.util.List;
import java.util.ArrayList;
import java.util.Map;
import javax.sql.DataSource;

import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

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
    private static String sha(String value) throws Exception { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes())); }
    private long count(String table) { return jdbc("SELECT count(*) FROM " + table); }
    private long jdbc(String sql) { return new org.springframework.jdbc.core.JdbcTemplate(database).queryForObject(sql, Long.class); }
    private void jdbcUpdate(String sql) { new org.springframework.jdbc.core.JdbcTemplate(database).update(sql); }
}
