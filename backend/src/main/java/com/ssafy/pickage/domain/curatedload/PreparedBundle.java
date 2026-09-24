package com.ssafy.pickage.domain.curatedload;

import java.nio.file.Path;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;

/** Verified immutable input and bounded COPY transport files. */
public record PreparedBundle(String prefix, String manifestSha256, String runId,
        LocalDate snapshot, String snapshotTimestamp, String manifestJson,
        String parentPrefix, String parentSha256, LocalDate parentSnapshot,
        List<CopyFile> files, Map<String, Long> excludedDependentsReasons,
        Map<String, Long> dependencyDefaultedReasons, String dependencyDefaultedInputSha256) {
    public PreparedBundle(String prefix, String manifestSha256, String runId,
            LocalDate snapshot, String snapshotTimestamp, String manifestJson,
            String parentPrefix, String parentSha256, LocalDate parentSnapshot,
            List<CopyFile> files, Map<String, Long> excludedDependentsReasons) {
        this(prefix, manifestSha256, runId, snapshot, snapshotTimestamp, manifestJson,
                parentPrefix, parentSha256, parentSnapshot, files, excludedDependentsReasons,
                Map.of(), null);
    }

    public PreparedBundle {
        files = List.copyOf(files);
        excludedDependentsReasons = Map.copyOf(excludedDependentsReasons);
        dependencyDefaultedReasons = Map.copyOf(dependencyDefaultedReasons);
    }

    public record CopyFile(String role, Path path, String sha256, long sourceRows,
                           long loadedRows, long excludedRows) {
        public CopyFile {
            if (sourceRows < 0 || loadedRows < 0 || excludedRows < 0
                    || loadedRows > sourceRows || excludedRows != sourceRows - loadedRows) {
                throw new IllegalArgumentException("Inconsistent Curated COPY row counts");
            }
            if (path == null || sha256 == null || !sha256.matches("[0-9a-f]{64}")) {
                throw new IllegalArgumentException("Invalid Curated COPY identity");
            }
        }
    }
}
