package com.ssafy.pickage.domain.curatedload;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;

/** Explicit, hash-pinned approval of one reviewed staging-compatible recovery. */
final class StageReuseProof {
    private StageReuseProof() {}

    static String receiptContract(String current, String execution, String manifest) throws Exception {
        String path = System.getProperty("pickage.curated.stage-reuse-proof");
        String digest = System.getProperty("pickage.curated.stage-reuse-proof-sha256");
        if (path == null && digest == null) return current;
        if (path == null || digest == null || !digest.matches("[0-9a-f]{64}"))
            throw new IllegalArgumentException("Incomplete staging recovery proof pin");
        Path proofPath = Path.of(path);
        if (Files.size(proofPath) > 65536) throw new IllegalArgumentException("Staging recovery proof too large");
        byte[] bytes = Files.readAllBytes(proofPath);
        if (!digest.equals(HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes))))
            throw new IllegalArgumentException("Staging recovery proof hash mismatch");
        JsonNode proof = new ObjectMapper().readTree(bytes);
        if (!"curated-stage-reuse-v1".equals(proof.path("format").asText())
                || !current.equals(proof.path("current_contract_sha256").asText())
                || !proof.path("previous_contract_sha256").asText().matches("[0-9a-f]{64}")
                || !proof.path("reviewed_staging_compatible").asBoolean(false)
                || proof.path("review_evidence").asText().isBlank())
            throw new IllegalArgumentException("Invalid staging recovery proof contract");
        if (!execution.equals(proof.path("execution_id").asText())) return current;
        if (!manifest.equals(proof.path("manifest_sha256").asText()))
            throw new IllegalArgumentException("Staging recovery manifest mismatch");
        return proof.path("previous_contract_sha256").asText();
    }
}
