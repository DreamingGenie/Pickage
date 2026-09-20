package com.ssafy.pickage.domain.curatedload;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.duckdb.DuckDBConnection;
import org.junit.jupiter.api.Test;
import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.http.AbortableInputStream;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.lang.reflect.Proxy;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.Statement;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class CuratedBundleReaderTest {
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final String PREFIX = "depsdev/v1/curated-bundle/snapshot=2026-09-14/run_id=curated-test-1";

    @org.junit.jupiter.params.ParameterizedTest
    @org.junit.jupiter.params.provider.ValueSource(booleans = {false, true})
    void preparesCopyFilesAndDropsOnlyNullDependents(boolean sharded) throws Exception {
        Map<String, byte[]> objects = new HashMap<>();
        Path source = Files.createTempDirectory("curated-reader-source-");
        Path copy = Files.createTempDirectory("curated-reader-copy-");
        putParquet(source.resolve("package.parquet"), "CREATE TABLE t(package_id INTEGER,name VARCHAR,repo_url VARCHAR);"
                + "INSERT INTO t VALUES (1,'name\\tline','https://repo'),(2,'line\\nnext',NULL);");
        putParquet(source.resolve("version.parquet"), "CREATE TABLE t(version VARCHAR,package_id INTEGER,published_at TIMESTAMP,ordinal BIGINT,description VARCHAR,licenses JSON,deprecated VARCHAR,dependency JSON);"
                + "INSERT INTO t VALUES ('1.0.0',1,'2026-09-14 00:00:00',1,'desc','[\"MIT\"]',NULL,'{\"dependencies\":{}}');");
        putParquet(source.resolve("package_snapshot.parquet"), "CREATE TABLE t(package_id INTEGER,snapshot_at DATE,downloads BIGINT,stars INTEGER,open_issues INTEGER);"
                + "INSERT INTO t VALUES (1,'2026-09-14',0,2,3);");
        putParquet(source.resolve("version_dependents.parquet"), "CREATE TABLE t(package_id INTEGER,version VARCHAR,snapshot_at DATE,dependents_count BIGINT);"
                + "INSERT INTO t VALUES (1,'1.0.0','2026-09-14',0),(2,'2.0.0','2026-09-14',NULL);");
        putParquet(source.resolve("quality.parquet"), "CREATE TABLE t(package_id INTEGER,version VARCHAR,snapshot_at DATE,dependents_count BIGINT,null_reason VARCHAR);"
                + "INSERT INTO t VALUES (1,'1.0.0','2026-09-14',0,NULL),(2,'2.0.0','2026-09-14',NULL,'NOT_SELECTED_TARGET');");
        for (String name : new String[]{"package", "version", "package_snapshot", "version_dependents", "quality"}) {
            objects.put("stage/" + name + ".parquet", Files.readAllBytes(source.resolve(name + ".parquet")));
        }
        if (sharded) {
            putParquet(source.resolve("package-extra.parquet"), "CREATE TABLE t(package_id INTEGER,name VARCHAR,repo_url VARCHAR);INSERT INTO t VALUES (3,'extra',NULL);");
            putParquet(source.resolve("version-empty.parquet"), "CREATE TABLE t(version VARCHAR,package_id INTEGER,published_at TIMESTAMP,ordinal BIGINT,description VARCHAR,licenses JSON,deprecated VARCHAR,dependency JSON);");
            objects.put("stage/shards/package.parquet", Files.readAllBytes(source.resolve("package-extra.parquet")));
            objects.put("stage/shards/version.parquet", Files.readAllBytes(source.resolve("version-empty.parquet")));
        }
        putBundle(objects);

        PreparedBundle result = new CuratedBundleReader(fakeS3(objects), copy).prepare(PREFIX, sha(objects.get(PREFIX + "/run_manifest.json")));

        assertEquals("2026-09-14", result.snapshot().toString());
        assertEquals(1L, result.excludedDependentsReasons().get("NOT_SELECTED_TARGET"));
        assertEquals(sharded ? 6 : 4, result.files().size());
        assertEquals(result.files().size(), result.files().stream().map(PreparedBundle.CopyFile::path).distinct().count());
        if (sharded) {
            assertEquals(3, result.files().stream().filter(f -> f.role().equals("package")).mapToLong(PreparedBundle.CopyFile::loadedRows).sum());
            assertEquals(1, result.files().stream().filter(f -> f.role().equals("version") && f.loadedRows() == 0).count());
        }
        PreparedBundle.CopyFile dependents = result.files().stream().filter(f -> f.role().equals("version_snapshot")).findFirst().orElseThrow();
        assertEquals(2, dependents.sourceRows());
        assertEquals(1, dependents.loadedRows());
        assertEquals(1, dependents.excludedRows());
        String packageCopy = Files.readString(result.files().stream().filter(f -> f.role().equals("package")).findFirst().orElseThrow().path());
        assertTrue(packageCopy.contains("name"));
        assertTrue(packageCopy.contains("\\t") || packageCopy.contains("\\\\t"));
        assertMissingParquetBlocks(objects, copy.resolve("missing-parquet"));
    }

    private void assertMissingParquetBlocks(Map<String, byte[]> objects, Path work) throws Exception {
        objects.put("depsdev/v1/curated-bundle/_current.json", JSON.writeValueAsBytes(Map.of(
                "run_prefix", PREFIX, "snapshot", "2026-09-14",
                "manifest_sha256", sha(objects.get(PREFIX + "/run_manifest.json")))));
        objects.remove("stage/package.parquet");
        var database = org.mockito.Mockito.mock(javax.sql.DataSource.class);
        var connection = org.mockito.Mockito.mock(java.sql.Connection.class);
        var query = org.mockito.Mockito.mock(java.sql.PreparedStatement.class);
        var rows = org.mockito.Mockito.mock(java.sql.ResultSet.class);
        org.mockito.Mockito.when(database.getConnection()).thenReturn(connection);
        org.mockito.Mockito.when(connection.prepareStatement(org.mockito.ArgumentMatchers.anyString())).thenReturn(query);
        org.mockito.Mockito.when(query.executeQuery()).thenReturn(rows);
        new CuratedLoadJob(fakeS3(objects), database, work).tick();
        var state = JSON.readTree(Files.readString(work.resolve("poll-state.json")));
        assertEquals("BLOCKED", state.path("status").asText());
        assertEquals(1, state.path("failures").asInt());
        assertEquals(PREFIX, state.path("prefix").asText());
    }

    @Test
    void rejectsManifestHashMismatch() throws Exception {
        Map<String, byte[]> objects = new HashMap<>();
        putBundle(objects);
        CuratedBundleReader reader = new CuratedBundleReader(fakeS3(objects), Files.createTempDirectory("curated-reader-bad-"));
        assertThrows(IllegalArgumentException.class, () -> reader.prepare(PREFIX, "0".repeat(64)));
    }

    @Test
    void rejectsDuplicateServiceKeys() throws Exception {
        Map<String, byte[]> objects = new HashMap<>();
        Path source = Files.createTempDirectory("curated-reader-duplicate-");
        putParquet(source.resolve("package.parquet"), "CREATE TABLE t(package_id INTEGER,name VARCHAR,repo_url VARCHAR);INSERT INTO t VALUES (1,'a',NULL),(1,'b',NULL);");
        objects.put("stage/package.parquet", Files.readAllBytes(source.resolve("package.parquet")));
        // The remaining files are valid enough for manifest parsing; package validation fails first.
        putMinimalFiles(objects);
        putBundle(objects);
        CuratedBundleReader reader = new CuratedBundleReader(fakeS3(objects), Files.createTempDirectory("curated-reader-duplicate-out-"));
        assertThrows(IllegalArgumentException.class, () -> reader.prepare(PREFIX, sha(objects.get(PREFIX + "/run_manifest.json"))));
    }

    private static void putBundle(Map<String, byte[]> objects) throws Exception {
        putMinimalFiles(objects);
        ObjectNode bundle = JSON.createObjectNode().put("format_version", 1).put("dataset", "curated-bundle")
                .put("status", "COMPLETE").put("scope", "RAW_TO_CURATED_ONLY").put("calculation_complete", true).put("db_loaded", false);
        ObjectNode request = bundle.putObject("request").put("format_version", 1).put("run_id", "curated-test-1")
                .put("snapshot", "2026-09-14").put("snapshot_timestamp", "2026-09-14T00:00:00Z").putNull("parent");
        ObjectNode stages = bundle.putObject("stages");
        for (String stage : new String[]{"snapshot", "package_version", "downloads", "repository", "package_snapshot", "dependents"}) {
            ObjectNode descriptor = stages.putObject(stage).put("stage", stage).put("run_id", "curated-test-1")
                    .put("snapshot", "2026-09-14").put("status", "PASSED");
            String manifestKey = "stage-manifest/" + stage + ".json";
            byte[] stageManifest = "{\"status\":\"PASSED\"}".getBytes(StandardCharsets.UTF_8);
            objects.put(manifestKey, stageManifest);
            String stageSha = sha(stageManifest);
            descriptor.put("manifest_key", manifestKey).put("manifest_sha256", stageSha);
            String markerKey = "stage-marker/" + stage;
            byte[] initialMarker = ("{\"manifest_sha256\":\"" + stageSha + "\"}").getBytes(StandardCharsets.UTF_8);
            objects.put(markerKey, initialMarker);
            descriptor.put("marker_key", markerKey).put("marker_sha256", sha(initialMarker));
            ArrayNode files = descriptor.putArray("files");
            String role = switch (stage) { case "package_version" -> "package"; case "package_snapshot" -> "package_snapshot"; case "dependents" -> "version_dependents"; default -> "dummy"; };
            if (stage.equals("dependents")) {
                add(files, "stage/version_dependents.parquet", objects.get("stage/version_dependents.parquet"), "version_dependents");
                add(files, "stage/quality.parquet", objects.get("stage/quality.parquet"), "quality");
            } else if (stage.equals("package_version")) {
                add(files, "stage/package.parquet", objects.get("stage/package.parquet"), "package");
                add(files, "stage/version.parquet", objects.get("stage/version.parquet"), "version");
                for (String extra : new String[]{"package", "version"}) {
                    String key = "stage/shards/" + extra + ".parquet";
                    if (objects.containsKey(key)) add(files, key, objects.get(key), extra);
                }
            } else if (stage.equals("package_snapshot")) add(files, "stage/package_snapshot.parquet", objects.get("stage/package_snapshot.parquet"), "package_snapshot");
            else add(files, "stage/dummy-" + stage + ".json", objects.get("stage/dummy-" + stage + ".json"), role);
            ObjectNode stageBody = JSON.createObjectNode().put("status", "PASSED");
            stageBody.set("files", files.deepCopy());
            byte[] updatedStageManifest = JSON.writeValueAsBytes(stageBody);
            objects.put(manifestKey, updatedStageManifest);
            String updatedSha = sha(updatedStageManifest);
            descriptor.put("manifest_sha256", updatedSha);
            byte[] updatedMarker = ("{\"manifest_sha256\":\"" + updatedSha + "\"}").getBytes(StandardCharsets.UTF_8);
            descriptor.put("marker_sha256", sha(updatedMarker));
            objects.put(markerKey, updatedMarker);
        }
        byte[] manifest = JSON.writeValueAsBytes(bundle);
        objects.put(PREFIX + "/run_manifest.json", manifest);
        objects.put(PREFIX + "/_SUCCESS", ("{\"manifest_sha256\":\"" + sha(manifest) + "\"}").getBytes(StandardCharsets.UTF_8));
    }

    private static void putMinimalFiles(Map<String, byte[]> objects) {
        for (String stage : new String[]{"snapshot", "downloads", "repository"}) objects.putIfAbsent("stage/dummy-" + stage + ".json", "{}".getBytes(StandardCharsets.UTF_8));
        objects.putIfAbsent("stage/package.parquet", new byte[0]);
        objects.putIfAbsent("stage/version.parquet", new byte[0]);
        objects.putIfAbsent("stage/package_snapshot.parquet", new byte[0]);
        objects.putIfAbsent("stage/version_dependents.parquet", new byte[0]);
        objects.putIfAbsent("stage/quality.parquet", new byte[0]);
    }

    private static void add(ArrayNode files, String key, byte[] body, String role) {
        if (body == null) body = new byte[0];
        files.addObject().put("key", key).put("role", role).put("bytes", body.length).put("sha256", sha(body));
    }

    private static void putParquet(Path path, String sql) throws Exception {
        try (Connection connection = DriverManager.getConnection("jdbc:duckdb:" + path.resolveSibling(path.getFileName() + ".db")); Statement statement = connection.createStatement()) {
            statement.execute(sql);
            statement.execute("COPY t TO '" + path.toString().replace("'", "''") + "' (FORMAT PARQUET)");
        }
    }

    private static S3Client fakeS3(Map<String, byte[]> objects) {
        return (S3Client) Proxy.newProxyInstance(S3Client.class.getClassLoader(), new Class[]{S3Client.class}, (proxy, method, args) -> {
            if (method.getName().equals("getObject")) {
                String key = method.getParameterTypes()[0].equals(software.amazon.awssdk.services.s3.model.GetObjectRequest.class)
                        ? ((software.amazon.awssdk.services.s3.model.GetObjectRequest) args[0]).key() : "";
                byte[] body = objects.get(key);
                if (body == null) throw software.amazon.awssdk.services.s3.model.NoSuchKeyException.builder()
                        .statusCode(404).message("missing fake S3 object: " + key).build();
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

    private static String sha(byte[] body) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(body)); }
        catch (Exception e) { throw new IllegalStateException(e); }
    }
}
