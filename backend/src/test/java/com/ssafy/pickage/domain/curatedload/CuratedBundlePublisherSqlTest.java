package com.ssafy.pickage.domain.curatedload;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class CuratedBundlePublisherSqlTest {
    @Test
    void bootstrapUsesPlainInsertsForPackageAndVersion() {
        assertFalse(CuratedBundlePublisher.packageMergeSql(true).contains("ON CONFLICT"));
        assertFalse(CuratedBundlePublisher.versionMergeSql(true).contains("ON CONFLICT"));
        assertTrue(CuratedBundlePublisher.packageMergeSql(true).contains("WHERE execution_id=?"));
        assertTrue(CuratedBundlePublisher.versionMergeSql(true).contains("WHERE execution_id=?"));
    }

    @Test
    void incrementalVersionMergeUpdatesOnlyChangedRows() {
        String sql = CuratedBundlePublisher.versionMergeSql(false);
        assertTrue(sql.contains("ON CONFLICT(package_id,version)"));
        assertTrue(sql.contains("version.description IS DISTINCT FROM EXCLUDED.description"));
        assertTrue(sql.contains("version.dependency::jsonb IS DISTINCT FROM EXCLUDED.dependency::jsonb"));
    }

    @Test
    void incrementalPackageMergeKeepsNameIdentityAndSkipsEqualRepository() {
        String sql = CuratedBundlePublisher.packageMergeSql(false);
        assertTrue(sql.contains("package.name=EXCLUDED.name"));
        assertTrue(sql.contains("package.repo_url IS DISTINCT FROM EXCLUDED.repo_url"));
    }
}
