package com.ssafy.pickage.domain.curatedload;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.http.AbortableInputStream;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;
import software.amazon.awssdk.services.s3.model.NoSuchKeyException;
import java.io.ByteArrayInputStream;
import java.lang.reflect.Proxy;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class CuratedLoadJobTest {
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final String ROOT = "depsdev/v1/curated-bundle";
    @TempDir Path work;

    @Test void ordersCompletedParentsBeforeLatest() throws Exception {
        Map<String, byte[]> objects = new HashMap<>();
        Map<String, String> first = bundle(objects, "2026-08-28", null);
        Map<String, String> second = bundle(objects, "2026-08-31", first);
        objects.put(ROOT + "/_current.json", JSON.writeValueAsBytes(second));
        var history = new CuratedLoadJob(s3(objects), null, work).history();
        assertEquals(List.of("2026-08-28", "2026-08-31"), history.stream().map(c -> c.snapshot().toString()).toList());
    }

    @Test void rejectsParentThatIsNotOlder() throws Exception {
        Map<String, byte[]> objects = new HashMap<>();
        var parent = bundle(objects, "2026-09-14", null);
        var child = bundle(objects, "2026-08-31", parent);
        objects.put(ROOT + "/_current.json", JSON.writeValueAsBytes(child));
        assertThrows(IllegalArgumentException.class, () -> new CuratedLoadJob(s3(objects), null, work).history());
    }

    @Test void missingCurrentWaitsWithoutConsumingRetries() throws Exception {
        new CuratedLoadJob(s3(Map.of()), null, work).tick();
        var state = JSON.readTree(Files.readString(work.resolve("poll-state.json")));
        assertEquals("WAITING_INPUT", state.path("status").asText());
        assertEquals(0, state.path("failures").asInt());
    }

    @org.junit.jupiter.params.ParameterizedTest
    @org.junit.jupiter.params.provider.ValueSource(strings = {"run_manifest.json", "_SUCCESS"})
    void missingReferencedObjectBlocksInsteadOfWaiting(String missing) throws Exception {
        Map<String, byte[]> objects = new HashMap<>();
        var pointer = bundle(objects, "2026-08-31", null);
        objects.put(ROOT + "/_current.json", JSON.writeValueAsBytes(pointer));
        objects.remove(pointer.get("run_prefix") + "/" + missing);
        new CuratedLoadJob(s3(objects), null, work).tick();
        var state = JSON.readTree(Files.readString(work.resolve("poll-state.json")));
        assertEquals("BLOCKED", state.path("status").asText());
        assertEquals(1, state.path("failures").asInt());
    }

    @Test void modifiedManifestBlocksInsteadOfPublishing() throws Exception {
        Map<String, byte[]> objects = new HashMap<>();
        var pointer = bundle(objects, "2026-08-31", null);
        objects.put(ROOT + "/_current.json", JSON.writeValueAsBytes(pointer));
        objects.put(pointer.get("run_prefix") + "/run_manifest.json", "{}".getBytes());
        new CuratedLoadJob(s3(objects), null, work).tick();
        assertEquals("BLOCKED", JSON.readTree(Files.readString(work.resolve("poll-state.json"))).path("status").asText());
    }

    @Test void contractIsStableWithinBuild() {
        assertTrue(LoadContract.sha256().matches("[0-9a-f]{64}"));
        assertEquals(LoadContract.sha256(), LoadContract.sha256());
    }

    private static Map<String, String> bundle(Map<String, byte[]> objects, String day, Map<String, String> parent) throws Exception {
        String prefix = ROOT + "/snapshot=" + day + "/run_id=test";
        Map<String, Object> request = new LinkedHashMap<>();
        request.put("snapshot", day); request.put("run_id", "test"); request.put("parent_bundle", parent);
        byte[] bytes = JSON.writeValueAsBytes(Map.of("status", "COMPLETE", "request", request));
        String sha = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        objects.put(prefix + "/run_manifest.json", bytes);
        objects.put(prefix + "/_SUCCESS", JSON.writeValueAsBytes(Map.of("manifest_sha256", sha)));
        return Map.of("run_prefix", prefix, "manifest_sha256", sha, "snapshot", day);
    }

    private static S3Client s3(Map<String, byte[]> objects) {
        return (S3Client) Proxy.newProxyInstance(S3Client.class.getClassLoader(), new Class<?>[]{S3Client.class}, (p, method, args) -> {
            if (method.getName().equals("getObject")) {
                String key = ((GetObjectRequest) args[0]).key();
                if (!objects.containsKey(key)) throw NoSuchKeyException.builder().statusCode(404).message("Missing fixture key").build();
                return new ResponseInputStream<>(GetObjectResponse.builder().build(), AbortableInputStream.create(new ByteArrayInputStream(objects.get(key))));
            }
            if (method.getName().equals("serviceName")) return "s3";
            if (method.getName().equals("close")) return null;
            throw new UnsupportedOperationException(method.getName());
        });
    }
}
