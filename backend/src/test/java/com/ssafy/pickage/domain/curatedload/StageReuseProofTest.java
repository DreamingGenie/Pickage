package com.ssafy.pickage.domain.curatedload;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.Path;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.util.HexFormat;
import static org.assertj.core.api.Assertions.*;

class StageReuseProofTest {
    @TempDir Path root;
    @AfterEach void cleanup() {
        System.clearProperty("pickage.curated.stage-reuse-proof");
        System.clearProperty("pickage.curated.stage-reuse-proof-sha256");
    }
    @Test void defaultDoesNotAllowOldContract() throws Exception {
        assertThat(StageReuseProof.receiptContract("a".repeat(64), "run", "manifest")).isEqualTo("a".repeat(64));
    }
    @Test void proofIsScopedAndRejectsChangedManifestAndCurrentBuild() throws Exception {
        pin();
        assertThat(StageReuseProof.receiptContract("a".repeat(64), "run", "manifest")).isEqualTo("b".repeat(64));
        assertThat(StageReuseProof.receiptContract("a".repeat(64), "next", "other")).isEqualTo("a".repeat(64));
        assertThatThrownBy(() -> StageReuseProof.receiptContract("a".repeat(64), "run", "changed")).hasMessageContaining("manifest mismatch");
        assertThatThrownBy(() -> StageReuseProof.receiptContract("c".repeat(64), "run", "manifest")).hasMessageContaining("proof contract");
    }
    @Test void tamperingAndMissingPinAreRejected() throws Exception {
        Path proof = pin();
        Files.writeString(proof, "{}");
        assertThatThrownBy(() -> StageReuseProof.receiptContract("a".repeat(64), "run", "manifest")).hasMessageContaining("hash mismatch");
        System.clearProperty("pickage.curated.stage-reuse-proof-sha256");
        assertThatThrownBy(() -> StageReuseProof.receiptContract("a".repeat(64), "run", "manifest")).hasMessageContaining("Incomplete");
    }
    private Path pin() throws Exception {
        Path file = root.resolve("proof.json");
        Files.writeString(file, "{\"format\":\"curated-stage-reuse-v1\",\"current_contract_sha256\":\"" + "a".repeat(64)
            + "\",\"previous_contract_sha256\":\"" + "b".repeat(64)
            + "\",\"execution_id\":\"run\",\"manifest_sha256\":\"manifest\",\"reviewed_staging_compatible\":true,\"review_evidence\":\"fixture\"}");
        System.setProperty("pickage.curated.stage-reuse-proof", file.toString());
        System.setProperty("pickage.curated.stage-reuse-proof-sha256", HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(file))));
        return file;
    }
}
