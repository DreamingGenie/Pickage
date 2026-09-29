package com.ssafy.pickage.domain.curatedload;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import javax.sql.DataSource;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.junit.jupiter.api.Assumptions;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.S3Configuration;
import software.amazon.awssdk.services.s3.model.DeleteObjectsRequest;
import software.amazon.awssdk.services.s3.model.ObjectIdentifier;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

/**
 * Opt-in, cross-language Curated producer -> MinIO -> Spring/JDBC test.
 *
 * <p>The Python fixture is generated with {@code export_spring_load_fixture.py}.
 * This test is intentionally not part of the normal integration suite: it needs
 * an actual MinIO and a separately prepared PostgreSQL database.
 */
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class CuratedBundleEndToEndTest {
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final String BUCKET = "pickage-curated";

    private Path fixtureDir;
    private JsonNode fixture;
    private S3Client s3;
    private DataSource dataSource;

    @BeforeEach
    void setUp() throws Exception {
        Assumptions.assumeTrue("1".equals(System.getenv("CURATED_LOAD_E2E")),
            "Set CURATED_LOAD_E2E=1 to run the real MinIO/PostgreSQL test");
        String fixturePath = System.getenv("CURATED_TEST_FIXTURE");
        String endpoint = System.getenv("CURATED_TEST_S3_ENDPOINT");
        String dbUrl = System.getenv("CURATED_TEST_DB_URL");
        Assumptions.assumeTrue(fixturePath != null && endpoint != null && dbUrl != null,
            "CURATED_TEST_FIXTURE, CURATED_TEST_S3_ENDPOINT and CURATED_TEST_DB_URL are required");
        Assumptions.assumeTrue(dbUrl.matches("jdbc:postgresql://localhost:15439/curated_load_test(?:[?].*)?"),
            "Refusing to clean a non-dedicated DB; expected localhost:15439/curated_load_test");
        Assumptions.assumeTrue(endpoint.matches("https?://localhost:19039/?"),
            "Refusing to clean a non-dedicated MinIO endpoint; expected localhost:19039");
        fixtureDir = Path.of(fixturePath).toAbsolutePath().normalize();
        fixture = JSON.readTree(Files.readString(fixtureDir.resolve("fixture.json")));
        ((com.fasterxml.jackson.databind.node.ObjectNode) fixture).set("expected",
                JSON.readTree(Files.readString(fixtureDir.resolve("expected.json"))));
        String access = System.getenv().getOrDefault("CURATED_TEST_S3_ACCESS_KEY", "pickage-admin");
        String secret = System.getenv().getOrDefault("CURATED_TEST_S3_SECRET_KEY", "");
        s3 = S3Client.builder()
            .endpointOverride(java.net.URI.create(endpoint))
            .region(Region.US_EAST_1)
            .credentialsProvider(StaticCredentialsProvider.create(AwsBasicCredentials.create(access, secret)))
            .serviceConfiguration(S3Configuration.builder().pathStyleAccessEnabled(true).build())
            .build();
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setUrl(dbUrl);
        ds.setUsername(System.getenv().getOrDefault("CURATED_TEST_DB_USER", "postgres"));
        ds.setPassword(System.getenv().getOrDefault("CURATED_TEST_DB_PASSWORD", "pickage"));
        dataSource = ds;
        cleanMinio();
        cleanDatabase();
        uploadFixtureObjects();
    }

    @AfterEach
    void tearDown() throws Exception {
        if (s3 != null) {
            cleanMinio();
            s3.close();
        }
    }

    @Test
    void baseline_weekly_null_dependents_and_idempotent_replay() throws Exception {
        CuratedBundleReader reader = new CuratedBundleReader(s3, fixtureDir.resolve("reader-work"));
        CuratedBundlePublisher publisher = new CuratedBundlePublisher(dataSource);
        JsonNode baseline = fixture.path("baseline");
        JsonNode weekly = fixture.path("weekly");

        assertThat(publisher.publish(reader.prepare(baseline.path("prefix").asText(), baseline.path("sha256").asText())))
            .isEqualTo("PUBLISHED");
        assertThat(publisher.publish(reader.prepare(weekly.path("prefix").asText(), weekly.path("sha256").asText())))
            .isEqualTo("PUBLISHED");
        assertThat(publisher.publish(reader.prepare(weekly.path("prefix").asText(), weekly.path("sha256").asText())))
            .isEqualTo("SKIPPED");

        assertExactPublishedRows(fixture.path("expected"));
        try (Connection c = dataSource.getConnection(); var statement = c.createStatement()) {
            try (var rows = statement.executeQuery("SELECT count(*) FROM package")) {
                rows.next();
                assertThat(rows.getLong(1)).isEqualTo(fixture.path("expected").path("master").path("package").size());
            }
            try (var rows = statement.executeQuery("SELECT count(*) FROM version")) {
                rows.next();
                assertThat(rows.getLong(1)).isEqualTo(fixture.path("expected").path("master").path("version").size());
            }
            try (var rows = statement.executeQuery(
                "SELECT count(*), count(*) FILTER (WHERE dependents_count = 0) "
                    + "FROM package_version_snapshot WHERE snapshot_at = DATE '2026-08-31'")) {
                rows.next();
                assertThat(rows.getLong(1)).isEqualTo(fixture.path("expected").path("weekly").path("version_snapshot").size());
                assertThat(rows.getLong(2)).isEqualTo(fixture.path("expected").path("dependents_loaded_zero_rows").asLong());
            }
            try (var rows = statement.executeQuery(
                "SELECT count(*) FROM package_version_snapshot WHERE dependents_count IS NULL")) {
                rows.next();
                assertThat(rows.getLong(1)).isZero(); // NULL source rows are excluded before COPY.
            }
            try (var rows = statement.executeQuery(
                "SELECT count(*) FROM etl_load_execution WHERE dataset = 'curated-bundle'")) {
                rows.next();
                assertThat(rows.getLong(1)).isEqualTo(2); // replay does not create a third load.
            }
        }
    }

    private void assertExactPublishedRows(JsonNode expected) throws Exception {
        JsonNode master = expected.path("master");
        JsonNode weekly = expected.path("weekly");
        try (Connection c = dataSource.getConnection()) {
            try (var q = c.prepareStatement("SELECT package_id,name,repo_url FROM package ORDER BY package_id");
                 var rows = q.executeQuery()) {
                for (JsonNode want : master.path("package")) {
                    assertThat(rows.next()).isTrue();
                    assertThat(rows.getInt("package_id")).isEqualTo(want.path("package_id").asInt());
                    assertThat(rows.getString("name")).isEqualTo(want.path("name").asText());
                    assertNullable(rows.getString("repo_url"), want.get("repo_url"));
                }
                assertThat(rows.next()).isFalse();
            }
            try (var q = c.prepareStatement("SELECT version,package_id,published_at,ordinal,description,licenses::text,deprecated,dependency::text FROM version ORDER BY version,package_id");
                 var rows = q.executeQuery()) {
                for (JsonNode want : master.path("version")) {
                    assertThat(rows.next()).isTrue();
                    assertThat(rows.getString("version")).isEqualTo(want.path("version").asText());
                    assertThat(rows.getInt("package_id")).isEqualTo(want.path("package_id").asInt());
                    if (want.path("published_at").isNull()) assertThat(rows.getTimestamp("published_at")).isNull();
                    else assertThat(rows.getTimestamp("published_at").toLocalDateTime())
                            .isEqualTo(java.time.LocalDateTime.parse(want.path("published_at").asText()));
                    assertThat(rows.getLong("ordinal")).isEqualTo(want.path("ordinal").asLong());
                    assertNullable(rows.getString("description"), want.get("description"));
                    assertJson(rows.getString("licenses"), want.get("licenses"));
                    assertNullable(rows.getString("deprecated"), want.get("deprecated"));
                    assertJson(rows.getString("dependency"), want.get("dependency"));
                }
                assertThat(rows.next()).isFalse();
            }
            try (var q = c.prepareStatement("SELECT package_id,snapshot_at,downloads,stars,open_issues FROM package_snapshot WHERE snapshot_at=DATE '2026-08-31' ORDER BY package_id");
                 var rows = q.executeQuery()) {
                for (JsonNode want : weekly.path("package_snapshot")) {
                    assertThat(rows.next()).isTrue();
                    assertThat(rows.getInt("package_id")).isEqualTo(want.path("package_id").asInt());
                    assertThat(rows.getDate("snapshot_at").toLocalDate().toString()).isEqualTo(want.path("snapshot_at").asText());
                    assertNullableLong(rows.getObject("downloads"), want.get("downloads"));
                    assertNullableLong(rows.getObject("stars"), want.get("stars"));
                    assertNullableLong(rows.getObject("open_issues"), want.get("open_issues"));
                }
                assertThat(rows.next()).isFalse();
            }
            try (var q = c.prepareStatement("SELECT package_id,version,snapshot_at,dependents_count FROM package_version_snapshot WHERE snapshot_at=DATE '2026-08-31' ORDER BY package_id,version");
                 var rows = q.executeQuery()) {
                for (JsonNode want : weekly.path("version_snapshot")) {
                    assertThat(rows.next()).isTrue();
                    assertThat(rows.getInt("package_id")).isEqualTo(want.path("package_id").asInt());
                    assertThat(rows.getString("version")).isEqualTo(want.path("version").asText());
                    assertThat(rows.getDate("snapshot_at").toLocalDate().toString()).isEqualTo(want.path("snapshot_at").asText());
                    assertThat(rows.getInt("dependents_count")).isEqualTo(want.path("dependents_count").asInt());
                }
                assertThat(rows.next()).isFalse();
            }
        }
    }

    private static void assertNullable(String actual, JsonNode expected) {
        if (expected == null || expected.isNull()) assertThat(actual).isNull();
        else assertThat(actual).isEqualTo(expected.asText());
    }

    private static void assertNullableLong(Object actual, JsonNode expected) {
        if (expected == null || expected.isNull()) assertThat(actual).isNull();
        else assertThat(((Number) actual).longValue()).isEqualTo(expected.asLong());
    }

    private static void assertJson(String actual, JsonNode expected) throws Exception {
        if (expected == null || expected.isNull()) {
            assertThat(actual).isNull();
        } else {
            assertThat(JSON.readTree(actual)).isEqualTo(JSON.readTree(expected.asText()));
        }
    }

    private void uploadFixtureObjects() throws IOException {
        for (JsonNode object : fixture.path("objects")) {
            Path path = fixtureDir.resolve(object.path("path").asText());
            s3.putObject(PutObjectRequest.builder().bucket(object.path("bucket").asText())
                    .key(object.path("key").asText()).build(), RequestBody.fromFile(path));
        }
    }

    private void cleanMinio() {
        if (s3 == null) return;
        var keys = s3.listObjectsV2(b -> b.bucket(BUCKET)).contents().stream()
            .map(o -> ObjectIdentifier.builder().key(o.key()).build()).toList();
        if (!keys.isEmpty()) {
            s3.deleteObjects(DeleteObjectsRequest.builder().bucket(BUCKET)
                .delete(d -> d.objects(keys)).build());
        }
    }

    private void cleanDatabase() throws Exception {
        try (Connection c = dataSource.getConnection(); var statement = c.createStatement()) {
            statement.execute("TRUNCATE package_version_snapshot, package_snapshot, version, package, snapshot, "
                + "etl_curated_stage_package, etl_curated_stage_version, etl_curated_stage_package_snapshot, "
                + "etl_curated_stage_version_snapshot, etl_curated_load_file_receipt, etl_load_attempt, "
                + "etl_load_execution, etl_dataset_current CASCADE");
        }
    }
}
