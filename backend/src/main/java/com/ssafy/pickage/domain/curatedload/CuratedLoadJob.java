package com.ssafy.pickage.domain.curatedload;

import java.io.IOException;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.channels.OverlappingFileLockException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.sql.SQLException;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import javax.sql.DataSource;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.S3Exception;

/** Sequential opt-in consumer. Completion is always read from PostgreSQL, not local status. */
public final class CuratedLoadJob {
    private static final Logger log = LoggerFactory.getLogger(CuratedLoadJob.class);
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final String BUCKET = "pickage-curated";
    private static final String ROOT = "depsdev/v1/curated-bundle";
    private final S3Client s3;
    private final DataSource database;
    private final Path workDir;

    public CuratedLoadJob(S3Client s3, DataSource database, Path workDir) {
        this.s3 = s3;
        this.database = database;
        this.workDir = workDir.toAbsolutePath().normalize();
    }

    public String once(String prefix, String sha256, boolean adopt) throws Exception {
        Files.createDirectories(workDir);
        try (FileChannel channel = FileChannel.open(workDir.resolve("loader.lock"), StandardOpenOption.CREATE, StandardOpenOption.WRITE);
             FileLock lock = acquire(channel)) {
            return execute(new Candidate(prefix, sha256, null), adopt);
        }
    }

    private String execute(Candidate candidate, boolean adopt) throws Exception {
        Map<String, Object> state = new LinkedHashMap<>();
        state.put("prefix", candidate.prefix());
        state.put("manifest_sha256", candidate.sha256());
        state.put("started_at", Instant.now().toString());
        state.put("status", "PREPARING");
        save("last-run.json", state);
        try {
            PreparedBundle bundle = new CuratedBundleReader(s3, workDir.resolve("inputs")).prepare(candidate.prefix(), candidate.sha256());
            CuratedBundlePublisher publisher = new CuratedBundlePublisher(database);
            String result = adopt ? publisher.adoptBaseline(bundle) : publisher.publish(bundle);
            state.put("status", result);
            state.put("snapshot", bundle.snapshot().toString());
            state.put("excluded_dependents_reasons", bundle.excludedDependentsReasons());
            state.put("files", bundle.files().stream().map(file -> Map.of("role", file.role(),
                "source_rows", file.sourceRows(), "loaded_rows", file.loadedRows(), "excluded_rows", file.excludedRows())).toList());
            log.info("Curated load {}: {}", result, candidate.prefix());
            return result;
        } catch (Exception failure) {
            state.put("status", "FAILED");
            state.put("error", failure.getClass().getSimpleName() + ": " + failure.getMessage());
            log.error("Curated load failed: {}", candidate.prefix(), failure);
            throw failure;
        } finally {
            state.put("finished_at", Instant.now().toString());
            save("last-run.json", state);
            save("events/" + java.util.UUID.randomUUID() + ".json", state);
        }
    }

    public void tick() throws Exception {
        Files.createDirectories(workDir);
        try (FileChannel channel = FileChannel.open(workDir.resolve("loader.lock"), StandardOpenOption.CREATE, StandardOpenOption.WRITE)) {
            FileLock lock;
            try { lock = acquire(channel); }
            catch (LoaderBusyException busy) { log.info("Another local Curated loader is active"); return; }
            try (lock) {
                JsonNode previous = Files.exists(workDir.resolve("poll-state.json"))
                    ? JSON.readTree(Files.readAllBytes(workDir.resolve("poll-state.json"))) : JSON.createObjectNode();
                // A blocked generation requires an explicit once/adopt run or operator resolution.
                if (previous.path("status").asText().equals("BLOCKED")) {
                    String prefix = previous.path("prefix").asText();
                    String sha = previous.path("manifest_sha256").asText();
                    if (!prefix.isEmpty() && published(prefix, sha)) save("poll-state.json", Map.of("status", "IDLE"));
                    else { log.warn("Curated automatic load is BLOCKED; see poll-state.json"); return; }
                }
                if (!previous.path("next_retry_at").asText().isEmpty()
                        && Instant.parse(previous.path("next_retry_at").asText()).isAfter(Instant.now())) return;
                Candidate candidate = null;
                try {
                    for (Candidate item : history()) {
                        if (!published(item.prefix(), item.sha256())) { candidate = item; break; }
                    }
                    if (candidate == null) { save("poll-state.json", Map.of("status", "IDLE")); return; }
                    int failures = same(previous, candidate) ? previous.path("failures").asInt(0) : 0;
                    if (same(previous, candidate) && previous.path("status").asText().equals("RUNNING")) failures++;
                    if (failures >= 10) {
                        save("poll-state.json", pollState(candidate, "BLOCKED", failures, null, "Interrupted attempts exhausted retries"));
                        return;
                    }
                    save("poll-state.json", pollState(candidate, "RUNNING", failures, null, null));
                    previous = JSON.valueToTree(pollState(candidate, "RUNNING", failures, null, null));
                    execute(candidate, false);
                    save("poll-state.json", pollState(candidate, "PUBLISHED", 0, null, null));
                } catch (Exception failure) {
                    boolean waiting = failure instanceof MissingCurrentException;
                    int failures = (same(previous, candidate) ? previous.path("failures").asInt(0) : 0) + (waiting ? 0 : 1);
                    boolean blocked = !waiting && (permanent(failure) || failures >= 10);
                    Instant retry = blocked ? null : Instant.now().plusSeconds(Math.min(3600, 600L << Math.min(3, Math.max(0, failures - 1))));
                    save("poll-state.json", pollState(candidate, waiting ? "WAITING_INPUT" : blocked ? "BLOCKED" : "FAILED",
                            failures, retry, failure.getClass().getSimpleName() + ": " + failure.getMessage()));
                    log.error("Curated tick failed", failure);
                }
            }
        }
    }

    private boolean published(String prefix, String sha256) throws SQLException {
        try (var connection = database.getConnection(); var query = connection.prepareStatement(
                "SELECT 1 FROM public.etl_load_execution WHERE dataset='curated-bundle' AND run_prefix=? AND manifest_sha256=? AND status='PUBLISHED'")) {
            query.setString(1, prefix); query.setString(2, sha256);
            try (var rows = query.executeQuery()) { return rows.next(); }
        }
    }

    /** Oldest first through verified parent pointers, never latest-only ingestion. */
    List<Candidate> history() throws Exception {
        JsonNode pointer;
        try {
            pointer = JSON.readTree(object(ROOT + "/_current.json"));
        } catch (S3Exception failure) {
            if (failure.statusCode() == 404) throw new MissingCurrentException(failure);
            throw failure;
        }
        List<Candidate> result = new ArrayList<>();
        HashSet<String> seen = new HashSet<>();
        LocalDate child = null;
        while (pointer != null && !pointer.isNull()) {
            String prefix = pointer.path("run_prefix").asText();
            String sha = pointer.path("manifest_sha256").asText();
            LocalDate day = LocalDate.parse(pointer.path("snapshot").asText());
            if (!prefix.matches(ROOT + "/snapshot=" + day + "/run_id=[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
                    || !sha.matches("[0-9a-f]{64}") || !seen.add(prefix) || (child != null && !day.isBefore(child)) || seen.size() > 10000) {
                throw new IllegalArgumentException("Invalid completed bundle lineage");
            }
            byte[] body = object(prefix + "/run_manifest.json");
            String actual = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(body));
            JsonNode marker = JSON.readTree(object(prefix + "/_SUCCESS"));
            JsonNode bundle = JSON.readTree(body);
            if (!actual.equals(sha) || !marker.path("manifest_sha256").asText().equals(sha)
                    || !bundle.path("status").asText().equals("COMPLETE")
                    || !bundle.path("request").path("snapshot").asText().equals(day.toString())
                    || !prefix.endsWith("/run_id=" + bundle.path("request").path("run_id").asText())) {
                throw new IllegalArgumentException("Completed bundle SHA/identity mismatch");
            }
            result.addFirst(new Candidate(prefix, sha, day));
            child = day;
            pointer = bundle.path("request").get("parent_bundle");
        }
        return List.copyOf(result);
    }

    private byte[] object(String key) throws IOException {
        try (var input = s3.getObject(GetObjectRequest.builder().bucket(BUCKET).key(key).build())) {
            byte[] body = input.readNBytes(16 * 1024 * 1024 + 1);
            if (body.length > 16 * 1024 * 1024) throw new IOException("Manifest exceeds 16MiB limit");
            return body;
        }
    }

    private void save(String name, Object state) throws IOException {
        Path target = workDir.resolve(name);
        Files.createDirectories(target.getParent());
        Path temporary = Files.createTempFile(target.getParent(), ".state-", ".tmp");
        try {
            Files.write(temporary, JSON.writeValueAsBytes(state));
            try { Files.move(temporary, target, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING); }
            catch (java.nio.file.AtomicMoveNotSupportedException unsupported) {
                Files.move(temporary, target, StandardCopyOption.REPLACE_EXISTING);
            }
        } finally { Files.deleteIfExists(temporary); }
    }

    private static FileLock acquire(FileChannel channel) throws IOException {
        try {
            FileLock lock = channel.tryLock();
            if (lock == null) throw new LoaderBusyException();
            return lock;
        } catch (OverlappingFileLockException busy) { throw new LoaderBusyException(); }
    }

    private static final class LoaderBusyException extends IOException {
        LoaderBusyException() { super("Another Curated loader is active"); }
    }

    private static final class MissingCurrentException extends IOException {
        MissingCurrentException(S3Exception cause) { super("No Curated current bundle has been published", cause); }
    }

    private static boolean same(JsonNode state, Candidate candidate) {
        return candidate == null ? state.path("prefix").asText().isEmpty()
            : candidate.prefix().equals(state.path("prefix").asText()) && candidate.sha256().equals(state.path("manifest_sha256").asText());
    }

    private static boolean permanent(Throwable error) {
        if (error instanceof IllegalArgumentException || error instanceof IllegalStateException) return true;
        if (error instanceof S3Exception s) return s.statusCode() >= 400 && s.statusCode() < 500 && s.statusCode() != 429;
        if (error instanceof SQLException sql && sql.getSQLState() != null) {
            return sql.getSQLState().startsWith("22") || sql.getSQLState().startsWith("23") || sql.getSQLState().startsWith("42");
        }
        return false;
    }

    private static Map<String, Object> pollState(Candidate candidate, String status, int failures, Instant retry, String error) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("status", status); result.put("failures", failures);
        result.put("prefix", candidate == null ? "" : candidate.prefix());
        result.put("manifest_sha256", candidate == null ? "" : candidate.sha256());
        result.put("updated_at", Instant.now().toString());
        result.put("next_retry_at", retry == null ? "" : retry.toString());
        result.put("error", error);
        return result;
    }

    record Candidate(String prefix, String sha256, LocalDate snapshot) {}
}
