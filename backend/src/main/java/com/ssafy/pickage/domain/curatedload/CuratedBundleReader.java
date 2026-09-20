package com.ssafy.pickage.domain.curatedload;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;

import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * Reads one immutable, completed Curated bundle and prepares bounded PostgreSQL COPY files.
 * This class deliberately does not discover the latest pointer and does not write to S3.
 */
public final class CuratedBundleReader {
    private static final String BUCKET = "pickage-curated";
    private static final String[] STAGES = {"snapshot", "package_version", "downloads", "repository", "package_snapshot", "dependents"};
    private static final Pattern SHA = Pattern.compile("[0-9a-f]{64}");
    private static final Pattern PREFIX = Pattern.compile(
            "depsdev/v1/curated-bundle/snapshot=\\d{4}-\\d{2}-\\d{2}/run_id=[A-Za-z0-9][A-Za-z0-9_-]{0,63}");
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final String DEFAULT_DEPENDENCY_JSON = "{\"dependencies\":{},\"peerDependencies\":{},\"optionalDependencies\":{}}";
    private static final long MAX_OBJECT_BYTES = 8L * 1024 * 1024 * 1024;

    private final S3Client s3;
    private final Path workDir;

    public CuratedBundleReader(S3Client s3, Path workDir) {
        this.s3 = java.util.Objects.requireNonNull(s3, "s3");
        this.workDir = java.util.Objects.requireNonNull(workDir, "workDir").toAbsolutePath().normalize();
    }

    /** Validate the bundle and create COPY TEXT files without buffering a dataset in the JVM. */
    public PreparedBundle prepare(String prefix, String expectedSha256) throws Exception {
        validateArguments(prefix, expectedSha256);
        Files.createDirectories(workDir);
        Path attempt = Files.createTempDirectory(workDir, "curated-input-");
        try {
            byte[] manifestBytes = getBytes(prefix + "/run_manifest.json", 16L * 1024 * 1024);
            String actualManifestSha = sha256(manifestBytes);
            if (!actualManifestSha.equals(expectedSha256)) {
                throw invalid("bundle manifest SHA mismatch");
            }
            byte[] completion = getBytes(prefix + "/_SUCCESS", 1024 * 1024);
            if (!completionEquals(completion, expectedSha256)) throw invalid("bundle completion marker mismatch");
            JsonNode manifest = JSON.readTree(manifestBytes);
            validateBundle(prefix, manifest);
            JsonNode request = manifest.path("request");
            LocalDate snapshot = LocalDate.parse(request.path("snapshot").asText());
            String snapshotTimestamp = request.path("snapshot_timestamp").asText();
            String runId = request.path("run_id").asText();
            List<RemoteFile> files = selectFiles(manifest, request);
            List<PreparedBundle.CopyFile> prepared = new ArrayList<>();
            Map<String, Long> excluded = new LinkedHashMap<>();
            try (Connection duck = DriverManager.getConnection("jdbc:duckdb:" + attempt.resolve("working.duckdb"))) {
                try (var statement = duck.createStatement()) {
                    statement.execute("SET threads=1");
                    statement.execute("SET memory_limit='256MB'");
                    statement.execute("SET preserve_insertion_order=false");
                    statement.execute("SET temp_directory='" + sqlLiteral(attempt.resolve("scratch")) + "'");
                }
                for (RemoteFile file : files) {
                    Path parquet = download(file, attempt.resolve("objects"));
                    if ("quality".equals(file.role())) {
                        scanExcludedReasons(duck, parquet, excluded);
                        continue;
                    }
                    Prepared preparedFile = convert(duck, file.role(), parquet, attempt.resolve("copy"));
                    if (file.rowCount() >= 0 && file.rowCount() != preparedFile.sourceRows()) {
                        throw invalid("Parquet row count mismatch: " + file.role());
                    }
                    prepared.add(new PreparedBundle.CopyFile(file.role(), preparedFile.path(),
                    fileSha(preparedFile.path()), preparedFile.sourceRows(), preparedFile.loadedRows(), preparedFile.excludedRows()));
                    if (preparedFile.excludedReasons() != null) {
                        preparedFile.excludedReasons().forEach((key, value) -> excluded.merge(key, value, Long::sum));
                    }
                    if ("version".equals(file.role())) writeDependencyQuality(duck, parquet, attempt.resolve("quality"));
                }
            }
            long excludedRows = prepared.stream().filter(f -> "version_snapshot".equals(f.role()))
                    .mapToLong(PreparedBundle.CopyFile::excludedRows).sum();
            long qualityExcluded = excluded.values().stream().mapToLong(Long::longValue).sum();
            if (excludedRows != qualityExcluded) throw invalid("dependents NULL quality count mismatch");
            Parent parent = parent(request);
            return new PreparedBundle(prefix, expectedSha256, runId, snapshot, snapshotTimestamp,
                    new String(manifestBytes, StandardCharsets.UTF_8), parent.prefix(), parent.sha256(),
                    parent.snapshot(), prepared, excluded);
        } catch (Exception e) {
            // Preserve the attempt directory as evidence for caller logging, but never publish it.
            throw e;
        }
    }

    private static void validateArguments(String prefix, String expectedSha256) {
        if (!PREFIX.matcher(prefix).matches() || !SHA.matcher(expectedSha256).matches()) {
            throw invalid("invalid Curated bundle prefix or manifest SHA");
        }
    }

    private void validateBundle(String prefix, JsonNode manifest) throws IOException {
        if (manifest.path("format_version").asInt(-1) != 1
                || !"curated-bundle".equals(manifest.path("dataset").asText())
                || !manifest.path("calculation_complete").asBoolean(false)
                || !"COMPLETE".equals(manifest.path("status").asText())
                || !"RAW_TO_CURATED_ONLY".equals(manifest.path("scope").asText())
                || manifest.path("db_loaded").asBoolean(true)) {
            throw invalid("bundle is not an un-loaded COMPLETE Curated bundle");
        }
        JsonNode stages = manifest.path("stages");
        if (!stages.isObject()) throw invalid("bundle stages are missing");
        for (String stage : STAGES) {
            JsonNode descriptor = stages.path(stage);
            String manifestKey = descriptor.path("manifest_key").asText();
            String descriptorSha = descriptor.path("manifest_sha256").asText();
            if (manifestKey.isBlank() || !SHA.matcher(descriptorSha).matches()
                    || !descriptorSha.equals(sha256(getBytes(manifestKey, 16L * 1024 * 1024)))) {
                throw invalid("stage manifest checksum mismatch: " + stage);
            }
            JsonNode stageManifest = JSON.readTree(getBytes(manifestKey, 16L * 1024 * 1024));
            if (!Set.of("PASSED", "COMPLETE", "LOCAL_VALIDATED").contains(stageManifest.path("status").asText())) {
                throw invalid("stage is not complete: " + stage);
            }
            byte[] markerBytes = getBytes(descriptor.path("marker_key").asText(), 1024 * 1024);
            String markerSha = descriptor.path("marker_sha256").asText();
            if (!SHA.matcher(markerSha).matches() || !markerSha.equals(sha256(markerBytes))) {
                throw invalid("stage marker checksum mismatch: " + stage);
            }
            boolean jsonMarker = false;
            try {
                JsonNode marker = JSON.readTree(markerBytes);
                jsonMarker = marker.has("manifest_sha256") && descriptorSha.equals(marker.path("manifest_sha256").asText());
            } catch (IOException ignored) {
                // Some existing native stages use the canonical SHA plus a newline marker.
            }
            if (!jsonMarker && !new String(markerBytes, StandardCharsets.UTF_8).equals(descriptorSha + "\n")) {
                throw invalid("stage completion marker mismatch: " + stage);
            }
            if (!descriptor.path("files").isArray() || descriptor.path("files").isEmpty()) {
                throw invalid("stage has no approved files: " + stage);
            }
            for (JsonNode record : descriptor.path("files")) {
                validateInventoryRecord(record); // validate every approved inventory record, not only service files
                if (!containsFile(stageManifest.path("files"), record, descriptor, stage)) throw invalid("stage inventory mismatch: " + stage);
            }
            if (stageManifest.path("files").size() != descriptor.path("files").size()) {
                throw invalid("stage inventory is incomplete: " + stage);
            }
        }
        JsonNode request = manifest.path("request");
        if (!prefix.equals("depsdev/v1/curated-bundle/snapshot=" + request.path("snapshot").asText()
                + "/run_id=" + request.path("run_id").asText())) {
            throw invalid("bundle request identity mismatch");
        }
    }

    private List<RemoteFile> selectFiles(JsonNode manifest, JsonNode request) {
        boolean bootstrap = request.path("parent").isNull() || request.path("parent").isMissingNode();
        Map<String, List<RemoteFile>> selected = new LinkedHashMap<>();
        addStageFiles(selected, manifest.path("stages").path("package_version"), bootstrap ? "package" : "changes/package_upserts");
        addStageFiles(selected, manifest.path("stages").path("package_version"), bootstrap ? "version" : "changes/version_upserts");
        addStageFiles(selected, manifest.path("stages").path("package_snapshot"), "package_snapshot");
        addStageFiles(selected, manifest.path("stages").path("dependents"), "version_dependents");
        addStageFiles(selected, manifest.path("stages").path("dependents"), "quality");
        if (!selected.containsKey("package") || !selected.containsKey("version")
                || !selected.containsKey("package_snapshot") || !selected.containsKey("version_snapshot")
                || !selected.containsKey("quality")) {
            throw invalid("bundle lacks required service files");
        }
        return selected.values().stream().flatMap(List::stream).toList();
    }

    private static void addStageFiles(Map<String, List<RemoteFile>> out, JsonNode descriptor, String fragment) {
        for (JsonNode record : descriptor.path("files")) {
            String key = record.path("key").asText();
            String producerRole = record.path("role").asText();
            String role = switch (fragment) {
                case "changes/package_upserts" -> "package";
                case "changes/version_upserts" -> "version";
                case "version_dependents" -> "version_snapshot";
                default -> fragment;
            };
            boolean roleMatch = producerRole.equals(fragment)
                    || ("changes/package_upserts".equals(fragment) && producerRole.equals("package_upserts"))
                    || ("changes/version_upserts".equals(fragment) && producerRole.equals("version_upserts"));
            if (roleMatch || key.contains("/" + fragment + "/") || key.endsWith("/" + fragment + ".parquet")
                    || key.contains("/" + fragment + ".parquet")) {
                out.computeIfAbsent(role, ignored -> new ArrayList<>()).add(remoteFile(role, record));
            }
        }
    }

    private static RemoteFile remoteFile(String role, JsonNode record) {
        validateInventoryRecord(record);
        String key = record.path("key").asText();
        String sha = record.path("sha256").asText();
        if (!key.endsWith(".parquet")) throw invalid("approved service file is not Parquet");
        long bytes = record.path("bytes").asLong(-1);
        long rows = record.path("row_count").asLong(-1);
        return new RemoteFile(role, key, sha, bytes, rows);
    }

    private static void validateInventoryRecord(JsonNode record) {
        String key = record.path("key").asText();
        String sha = record.path("sha256").asText();
        if (key.isBlank() || !SHA.matcher(sha).matches() || key.startsWith("/") || key.contains("\\")
                || key.contains("..") || key.contains("\u0000")) throw invalid("unsafe approved file record");
    }

    private Path download(RemoteFile file, Path root) throws IOException {
        Path target = root.resolve(file.role() + "-" + file.sha256() + ".parquet").normalize();
        if (!target.startsWith(root.toAbsolutePath().normalize())) throw invalid("download path escapes work directory");
        Files.createDirectories(root);
        MessageDigest digest = digest();
        long total = 0;
        try (ResponseInputStream<?> in = s3.getObject(GetObjectRequest.builder().bucket(BUCKET).key(file.key()).build());
             var out = Files.newOutputStream(target)) {
            byte[] buffer = new byte[1024 * 1024];
            int n;
            while ((n = in.read(buffer)) >= 0) {
                total += n;
                if (total > MAX_OBJECT_BYTES) throw invalid("approved object exceeds download limit");
                digest.update(buffer, 0, n);
                out.write(buffer, 0, n);
            }
        }
        if (file.bytes() >= 0 && total != file.bytes()) throw invalid("Parquet byte count mismatch: " + file.role());
        if (!file.sha256().equals(hex(digest.digest()))) throw invalid("Parquet SHA mismatch: " + file.role());
        return target;
    }

    private static Prepared convert(Connection con, String role, Path parquet, Path outputRoot) throws SQLException, IOException {
        Schema schema = Schema.forRole(role);
        validateParquet(con, schema, parquet);
        Files.createDirectories(outputRoot);
        Path output = outputRoot.resolve(role + "-" + fileToken(parquet) + ".copy.tsv");
        String sql = "SELECT " + schema.select() + " FROM read_parquet(?)";
        long source = 0, excluded = 0;
        Map<String, Long> reasons = new LinkedHashMap<>();
        try (PreparedStatement ps = con.prepareStatement(sql)) {
            ps.setString(1, parquet.toString());
            try (ResultSet rs = ps.executeQuery(); BufferedWriter writer = Files.newBufferedWriter(output, StandardCharsets.UTF_8)) {
                while (rs.next()) {
                    source++;
                    if (("version_dependents".equals(role) || "version_snapshot".equals(role)) && rs.getObject(4) == null) {
                        excluded++;
                        continue;
                    }
                    for (int i = 1; i <= schema.columns(); i++) {
                        if (i > 1) writer.write('\t');
                        Object value = rs.getObject(i);
                        writer.write(copyText(value == null ? null : value.toString()));
                    }
                    writer.write('\n');
                }
            }
        }
        return new Prepared(output, source, source - excluded, excluded, reasons);
    }

    private static long writeDependencyQuality(Connection con, Path parquet, Path qualityRoot) throws SQLException, IOException {
        Files.createDirectories(qualityRoot);
        Path output = qualityRoot.resolve("dependency_defaulted.jsonl");
        long count = 0;
            try (PreparedStatement ps = con.prepareStatement("SELECT package_id,version FROM read_parquet(?) WHERE dependency IS NULL ORDER BY package_id,version")) {
            ps.setString(1, parquet.toString());
            try (ResultSet rs = ps.executeQuery(); BufferedWriter writer = Files.newBufferedWriter(output, StandardCharsets.UTF_8,
                    java.nio.file.StandardOpenOption.CREATE, java.nio.file.StandardOpenOption.APPEND)) {
                while (rs.next()) {
                    writer.write("{\"package_id\":" + rs.getInt(1) + ",\"version\":\""
                            + jsonEscape(rs.getString(2)) + "\",\"reason\":\"DEPENDENCY_SQL_NULL_DEFAULTED\"}\n");
                    count++;
                }
            }
        }
        return count;
    }

    private static void scanExcludedReasons(Connection con, Path parquet, Map<String, Long> excluded) throws SQLException {
        String sql = "SELECT null_reason, count(*) FROM read_parquet(?) WHERE dependents_count IS NULL GROUP BY null_reason";
        try (PreparedStatement ps = con.prepareStatement(sql)) {
            ps.setString(1, parquet.toString());
            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) excluded.merge(reason(rs, 1), rs.getLong(2), Long::sum);
            }
        }
    }

    private static void validateParquet(Connection con, Schema schema, Path path) throws SQLException {
        String q = "SELECT count(*), sum(CASE WHEN " + schema.requiredNullCheck() + " THEN 1 ELSE 0 END), count(DISTINCT " + schema.key() + ") FROM read_parquet(?)";
        try (PreparedStatement ps = con.prepareStatement(q)) {
            ps.setString(1, path.toString());
            try (ResultSet rs = ps.executeQuery()) {
                rs.next();
                long rows = rs.getLong(1);
                long nulls = rs.getLong(2);
                long distinct = rs.getLong(3);
                if (nulls != 0 || rows != distinct) throw invalid("invalid or duplicate rows in " + schema.role());
            }
        }
        if ("version".equals(schema.role())) {
            try (PreparedStatement ps = con.prepareStatement("SELECT count(*) FROM read_parquet(?) WHERE (licenses IS NOT NULL AND NOT json_valid(CAST(licenses AS VARCHAR))) OR (dependency IS NOT NULL AND NOT json_valid(CAST(dependency AS VARCHAR)))")) {
                ps.setString(1, path.toString());
                try (ResultSet rs = ps.executeQuery()) { rs.next(); if (rs.getLong(1) != 0) throw invalid("invalid version JSON"); }
            }
        }
    }

    private static String reason(ResultSet rs, int index) throws SQLException {
        String value = rs.getString(index);
        return value == null || value.isBlank() ? "UNKNOWN" : value;
    }

    private static boolean containsFile(JsonNode files, JsonNode wanted, JsonNode descriptor, String stage) {
        String wantedKey = canonicalKey(wanted, descriptor, stage);
        for (JsonNode file : files) if (canonicalKey(file, descriptor, stage).equals(wantedKey)
                && file.path("sha256").asText().equals(wanted.path("sha256").asText())) return true;
        return false;
    }

    private static String canonicalKey(JsonNode record, JsonNode descriptor, String stage) {
        String key = record.path("key").asText();
        if (!key.isBlank()) return key;
        String path = record.path("path").asText();
        String base = descriptor.path("prefix").asText();
        if (base.isBlank() || path.isBlank()) return "";
        return base + (("downloads".equals(stage) || "package_snapshot".equals(stage)) ? "/data/" : "/") + path;
    }

    private static boolean completionEquals(byte[] bytes, String sha) throws IOException {
        String text = new String(bytes, StandardCharsets.UTF_8).trim();
        if (text.equals(sha)) return true;
        JsonNode marker = JSON.readTree(bytes);
        return marker.has("manifest_sha256") && sha.equals(marker.path("manifest_sha256").asText());
    }

    private static String copyText(String value) {
        if (value == null) return "\\N";
        return value.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r");
    }

    private static String jsonEscape(String value) {
        return value.replace("\\", "\\\\").replace("\"", "\\\"")
                .replace("\n", "\\n").replace("\r", "\\r");
    }

    private JsonNode getJson(String key) throws IOException {
        if (key.isBlank() || key.contains("..") || key.startsWith("/")) throw invalid("unsafe marker key");
        return JSON.readTree(getBytes(key, 1024 * 1024));
    }

    private byte[] getBytes(String key, long max) throws IOException {
        try (InputStream in = s3.getObject(GetObjectRequest.builder().bucket(BUCKET).key(key).build())) {
            java.io.ByteArrayOutputStream out = new java.io.ByteArrayOutputStream();
            byte[] buffer = new byte[8192];
            long total = 0;
            int n;
            while ((n = in.read(buffer)) >= 0) {
                total += n;
                if (total > max) throw invalid("object exceeds read limit");
                out.write(buffer, 0, n);
            }
            return out.toByteArray();
        }
    }

    private static Parent parent(JsonNode request) {
        JsonNode p = request.path("parent_bundle");
        if (!p.isObject()) return new Parent(null, null, null);
        return new Parent(p.path("run_prefix").asText(null), p.path("manifest_sha256").asText(null),
                p.hasNonNull("snapshot") ? LocalDate.parse(p.path("snapshot").asText()) : null);
    }

    private static String sqlLiteral(Path path) { return path.toString().replace("'", "''"); }
    private static String fileToken(Path path) { return path.getFileName().toString().replace(".parquet", ""); }
    private static String fileSha(Path path) throws IOException {
        MessageDigest digest = digest();
        try (InputStream in = Files.newInputStream(path)) {
            byte[] buffer = new byte[1024 * 1024];
            int n;
            while ((n = in.read(buffer)) >= 0) digest.update(buffer, 0, n);
        }
        return hex(digest.digest());
    }
    private static MessageDigest digest() { try { return MessageDigest.getInstance("SHA-256"); } catch (Exception e) { throw new IllegalStateException(e); } }
    private static String sha256(byte[] bytes) { MessageDigest d = digest(); return hex(d.digest(bytes)); }
    private static String hex(byte[] bytes) { StringBuilder s = new StringBuilder(); for (byte b : bytes) s.append("%02x".formatted(b)); return s.toString(); }
    private static IllegalArgumentException invalid(String message) { return new IllegalArgumentException(message); }

    private record RemoteFile(String role, String key, String sha256, long bytes, long rowCount) {}
    private record Prepared(Path path, long sourceRows, long loadedRows, long excludedRows, Map<String, Long> excludedReasons) {}
    private record Parent(String prefix, String sha256, LocalDate snapshot) {}

    private record Schema(String role, String select, String key, String requiredNullCheck, int columns) {
        static Schema forRole(String role) {
            return switch (role) {
                case "package" -> new Schema(role, "package_id::INTEGER,name::VARCHAR,repo_url::VARCHAR", "(package_id)", "package_id IS NULL OR name IS NULL", 3);
                case "version" -> new Schema(role, "version::VARCHAR,package_id::INTEGER,published_at::TIMESTAMP,ordinal::BIGINT,description::VARCHAR,CAST(licenses AS VARCHAR),deprecated::VARCHAR,COALESCE(CAST(dependency AS VARCHAR),'" + DEFAULT_DEPENDENCY_JSON + "')", "(package_id,version)", "package_id IS NULL OR version IS NULL", 8);
                case "package_snapshot" -> new Schema(role, "package_id::INTEGER,snapshot_at::DATE,downloads::BIGINT,stars::INTEGER,open_issues::INTEGER", "(package_id,snapshot_at)", "package_id IS NULL OR snapshot_at IS NULL", 5);
                case "version_dependents", "version_snapshot" -> new Schema(role, "package_id::INTEGER,version::VARCHAR,snapshot_at::DATE,dependents_count::BIGINT", "(package_id,version,snapshot_at)", "package_id IS NULL OR version IS NULL OR snapshot_at IS NULL", 4);
                default -> throw invalid("unsupported service role: " + role);
            };
        }
    }
}
