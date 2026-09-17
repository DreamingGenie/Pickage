package com.ssafy.pickage.domain.community;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import com.ssafy.pickage.PickageApplication;
import com.ssafy.pickage.domain.community.payload.*;
import com.ssafy.pickage.support.DisposableTestDatabase;

import org.junit.jupiter.api.*;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.context.WebApplicationContext;

import java.time.*;
import java.util.*;

class CommunityAcceptanceIntegrationTest {
    static DisposableTestDatabase database;
    static ConfigurableApplicationContext context;
    static JdbcTemplate jdbc;
    static CommunitySnapshotRepository repository;
    static MockMvc mvc;

    @BeforeAll
    static void start() {
        database = DisposableTestDatabase.createFor("315");
        startApplication();
    }

    static void startApplication() {
        var ds = (DriverManagerDataSource) database.dataSource();
        try {
            context =
                    new SpringApplicationBuilder(PickageApplication.class)
                            .run(
                                    "--server.port=0",
                                    "--server.address=127.0.0.1",
                                    "--spring.datasource.url=" + ds.getUrl(),
                                    "--spring.datasource.username=" + ds.getUsername(),
                                    "--spring.datasource.password=" + ds.getPassword());
            jdbc = context.getBean(JdbcTemplate.class);
            repository = context.getBean(CommunitySnapshotRepository.class);
            mvc =
                    MockMvcBuilders.webAppContextSetup((WebApplicationContext) context)
                            .addFilters(context.getBean(CommunityNoStoreFilter.class))
                            .build();
        } catch (RuntimeException e) {
            database.close();
            database = null;
            throw e;
        }
    }

    @AfterAll
    static void stop() {
        if (context != null) context.close();
        if (database != null) database.close();
    }

    @BeforeEach
    void seed() {
        jdbc.update("DELETE FROM package");
        jdbc.update("INSERT INTO package(package_id,name) VALUES (7,'fixture')");
    }

    static CommunitySnapshotRow row() {
        return new CommunitySnapshotRow(
                7,
                UUID.randomUUID(),
                (short) 2,
                Instant.now(),
                DataStatus.NO_DISCUSSION_DATA,
                new CommunityResultPayload(
                        new RepositoryPayload(
                                ("fixture/repo").split("/", 2)[0],
                                ("fixture/repo").split("/", 2)[1],
                                "fixture/repo",
                                "PACKAGE_SCOPED",
                                false),
                        "github-active-v1",
                        180,
                        null,
                        List.of(),
                        List.of()));
    }

    @Test
    void R08_realApplicationInitialWire() throws Exception {
        var response =
                mvc.perform(get("/api/packages/community").param("name", "fixture"))
                        .andReturn()
                        .getResponse();
        System.out.println("INITIAL_WIRE=" + response.getContentAsString());
        mvc.perform(get("/api/packages/community").param("name", "fixture"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.view_status").value("IDLE"));
    }

    @Test
    void R08_blankNameMustBeV001() throws Exception {
        mvc.perform(get("/api/packages/community").param("name", ""))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("V001"));
    }

    @Test
    void R08_malformedNameMustBeV004() throws Exception {
        mvc.perform(get("/api/packages/community").param("name", "bad/name"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("V004"));
    }

    @Test
    void R08_errorMustAlsoBeNoStore() throws Exception {
        mvc.perform(get("/api/packages/community"))
                .andExpect(status().isBadRequest())
                .andExpect(header().string("Cache-Control", "no-store"));
    }

    @Test
    void R06_unsupportedPayloadMustBeIgnored() {
        repository.upsert(row());
        jdbc.update("UPDATE community_snapshot SET payload_version=99");
        assertTrue(repository.findByPackageId(7).isEmpty());
    }

    @Test
    void R06_unsupportedPolicyMustBeIgnored() {
        repository.upsert(row());
        jdbc.update(
                "UPDATE community_snapshot SET result=jsonb_set(result,'{policy_version}','99')");
        assertTrue(repository.findByPackageId(7).isEmpty());
    }

    @Test
    void R06_invalidSupportedPayloadMustBeRejected() {
        repository.upsert(row());
        jdbc.update("UPDATE community_snapshot SET result='{}'::jsonb");
        assertThrows(CommunitySnapshotPayloadException.class, () -> repository.findByPackageId(7));
    }

    @Test
    void R11_realTransactionRollbackKeepsPreviousRow() {
        var old = row();
        repository.upsert(old);
        var tx = new TransactionTemplate(context.getBean(PlatformTransactionManager.class));
        assertThrows(
                IllegalStateException.class,
                () ->
                        tx.executeWithoutResult(
                                status -> {
                                    repository.upsert(row());
                                    throw new IllegalStateException("synthetic rollback");
                                }));
        assertEquals(old.snapshotId(), repository.findByPackageId(7).orElseThrow().snapshotId());
    }

    @Test
    void R12_existingPackageSearchStillWorks() throws Exception {
        mvc.perform(get("/api/packages/search").param("q", "fixture"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.success").value(true));
    }

    /**
     * 이 목록은 {@code deploy/local/seed/*.sql} 의 TRUNCATE 문과 **같아야 한다.** package 를
     * 참조하는 표를 새로 만들면 여기에도 넣는다 — TRUNCATE 는 참조하는 표가 비어 있어도 같이
     * 지정하지 않으면 거절한다. community_snapshot 은 V3(S15P21A506-315),
     * dependent_transition 은 V8(S15P21A506-361)에서 이 이유로 추가됐다.
     */
    @Test
    void R14_existingSeedTruncateMustRemainExecutable() {
        assertDoesNotThrow(
                () ->
                        jdbc.execute(
                                "TRUNCATE community_snapshot, dependent_transition,"
                                        + " similar_package, package_version_snapshot,"
                                        + " package_snapshot, version, package"));
    }

    @Test
    void R12_actualRuntimeSnakeCaseAndNullKeys() throws Exception {
        repository.upsert(row());
        var response =
                mvc.perform(get("/api/packages/community").param("name", "fixture"))
                        .andReturn()
                        .getResponse();
        System.out.println("RESULT_WIRE=" + response.getContentAsString());
        var json =
                new com.fasterxml.jackson.databind.ObjectMapper()
                        .readTree(response.getContentAsString());
        assertAll(
                () -> assertTrue(json.path("data").has("package_name")),
                () -> assertTrue(json.path("data").has("refresh")),
                () -> assertTrue(json.path("data").path("refresh").isNull()));
    }

    @Test
    void R11_publisherLockTimeoutPreservesOldResultAndRecovers() throws Exception {
        var old = row();
        repository.upsert(old);
        try (var lock = database.dataSource().getConnection();
                var publisher = new CommunitySnapshotPublisher(repository)) {
            lock.setAutoCommit(false);
            try (var statement = lock.createStatement()) {
                statement.execute(
                        "SELECT pg_advisory_xact_lock(hashtextextended('community:snapshot:7',0))");
            }
            var task =
                    new com.ssafy.pickage.domain.community.refresh.RefreshTask(
                            7, com.ssafy.pickage.domain.community.refresh.RefreshStatus.RUNNING);
            long start = System.nanoTime();
            assertThrows(IllegalStateException.class, () -> publisher.publish(row(), task));
            assertTrue(
                    Duration.ofNanos(System.nanoTime() - start).compareTo(Duration.ofSeconds(3))
                            < 0);
            assertEquals(
                    old.snapshotId(), repository.findByPackageId(7).orElseThrow().snapshotId());
            lock.rollback();
            var next = row();
            publisher.publish(next, task);
            assertEquals(
                    next.snapshotId(), repository.findByPackageId(7).orElseThrow().snapshotId());
            assertEquals(
                    com.ssafy.pickage.domain.community.refresh.RefreshStatus.COMPLETED,
                    task.snapshot().status());
        }
    }

    @Test
    void R11_cancelledTaskCannotReplaceOldResult() {
        var old = row();
        repository.upsert(old);
        var task =
                new com.ssafy.pickage.domain.community.refresh.RefreshTask(
                        7, com.ssafy.pickage.domain.community.refresh.RefreshStatus.RUNNING);
        task.markFailed(
                com.ssafy.pickage.domain.community.dto.CommunityErrorCode.REFRESH_DEADLINE_EXCEEDED,
                Instant.now().plusSeconds(300));
        try (var publisher = new CommunitySnapshotPublisher(repository)) {
            assertThrows(IllegalStateException.class, () -> publisher.publish(row(), task));
        }
        assertEquals(old.snapshotId(), repository.findByPackageId(7).orElseThrow().snapshotId());
    }

    @Test
    void R11_lateConnectionIsClosedWithoutPublication() throws Exception {
        var old = row();
        repository.upsert(old);
        var release = new java.util.concurrent.CountDownLatch(1);
        var closed = new java.util.concurrent.CountDownLatch(1);
        var ds = org.mockito.Mockito.mock(javax.sql.DataSource.class);
        org.mockito.Mockito.when(ds.getConnection())
                .thenAnswer(
                        invocation -> {
                            if (!release.await(5, java.util.concurrent.TimeUnit.SECONDS))
                                throw new java.sql.SQLException("fixture timeout");
                            var c = org.mockito.Mockito.spy(database.dataSource().getConnection());
                            org.mockito.Mockito.doAnswer(
                                            call -> {
                                                try {
                                                    return call.callRealMethod();
                                                } finally {
                                                    closed.countDown();
                                                }
                                            })
                                    .when(c)
                                    .close();
                            return c;
                        });
        var slowRepository =
                new CommunitySnapshotRepository(
                        new JdbcTemplate(ds), new CommunityConfig().communityObjectMapper());
        try (var publisher = new CommunitySnapshotPublisher(slowRepository)) {
            var task =
                    new com.ssafy.pickage.domain.community.refresh.RefreshTask(
                            7, com.ssafy.pickage.domain.community.refresh.RefreshStatus.RUNNING);
            long start = System.nanoTime();
            try {
                assertThrows(IllegalStateException.class, () -> publisher.publish(row(), task));
            } finally {
                release.countDown();
            }
            assertTrue(
                    Duration.ofNanos(System.nanoTime() - start).compareTo(Duration.ofSeconds(3))
                            < 0);
            assertTrue(closed.await(3, java.util.concurrent.TimeUnit.SECONDS));
        } finally {
            release.countDown();
        }
        assertEquals(old.snapshotId(), repository.findByPackageId(7).orElseThrow().snapshotId());
    }

    @Test
    void R06_corruptSupportedSnapshotReturnsSafeError() throws Exception {
        repository.upsert(row());
        jdbc.update("UPDATE community_snapshot SET result=result #- '{repository,archived}'");
        mvc.perform(get("/api/packages/community").param("name", "fixture"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.code").value("S001"))
                .andExpect(header().string("Cache-Control", "no-store"));
    }

    @Test
    void R12_restartPreservesCompleteWireContract() throws Exception {
        Instant date = Instant.parse("2026-09-01T00:00:00Z");
        var topic =
                new TopicPayload(
                        "1001",
                        1,
                        "OPEN",
                        date,
                        date,
                        "Original title",
                        "확인된 제목",
                        2,
                        3,
                        "COMPLETE",
                        "READY",
                        "확인된 요약",
                        List.of(new DiscussionStepPayload("확인된 흐름")),
                        List.of(
                                new MessagePayload(
                                        "2001",
                                        "fixture",
                                        "MEMBER",
                                        true,
                                        "DISCUSSION",
                                        date,
                                        "확인된 메시지")));
        repository.upsert(
                new CommunitySnapshotRow(
                        7,
                        UUID.randomUUID(),
                        (short) 2,
                        Instant.now(),
                        DataStatus.AVAILABLE,
                        new CommunityResultPayload(
                                new RepositoryPayload(
                                        "fixture", "repo", "fixture/repo", "PACKAGE_SCOPED", false),
                                "github-active-v1",
                                365,
                                null,
                                List.of(topic),
                                List.of())));
        var mapper = new com.fasterxml.jackson.databind.ObjectMapper();
        var before =
                mapper.readTree(
                        mvc.perform(get("/api/packages/community").param("name", "fixture"))
                                .andExpect(status().isOk())
                                .andReturn()
                                .getResponse()
                                .getContentAsString());
        var result = before.path("data").path("result");
        assertEquals(365, result.path("data_limits").path("lookback_days").asInt());
        assertEquals(
                "ISSUE_AUTHOR",
                result.path("topics").get(0).path("messages").get(0).path("role").asText());
        assertFalse(result.toString().contains("source_comment_id"));
        assertFalse(result.toString().contains("source_issue_id"));
        assertEquals(2, result.path("summary").path("comment_count").asInt());
        assertEquals(3, result.path("summary").path("reaction_count").asInt());
        context.close();
        startApplication();
        var after =
                mapper.readTree(
                        mvc.perform(get("/api/packages/community").param("name", "fixture"))
                                .andExpect(status().isOk())
                                .andReturn()
                                .getResponse()
                                .getContentAsString());
        assertEquals(before, after);
        var normalized = before.deepCopy();
        var normalizedResult =
                (com.fasterxml.jackson.databind.node.ObjectNode)
                        normalized.path("data").path("result");
        normalizedResult.put("snapshot_id", "<snapshot>");
        for (String field : List.of("collected_at", "fresh_until", "serve_until"))
            normalizedResult.put(field, "<time>");
        try (var fixture = getClass().getResourceAsStream("/community/contract/result.json")) {
            assertNotNull(fixture);
            assertEquals(mapper.readTree(fixture), normalized);
        }
    }

    @Test
    void R14_allSharedSeedScriptsExecuteWithCommunityForeignKey() throws Exception {
        for (String file :
                List.of(
                        "seed_sample.sql",
                        "seed_service_full.sql",
                        "seed_mock_parity.sql",
                        "seed_reset.sql")) {
            // 이 시험이 생성한 격리 DB에서만 공용 script를 실행한다.
            try (var connection = database.dataSource().getConnection();
                    var statement = connection.createStatement()) {
                statement.execute(
                        java.nio.file.Files.readString(
                                java.nio.file.Path.of("../deploy/local/seed", file)));
            }
            assertEquals(
                    0,
                    jdbc.queryForObject("SELECT count(*) FROM community_snapshot", Integer.class),
                    file);
            int count = jdbc.queryForObject("SELECT count(*) FROM package", Integer.class);
            assertEquals(file.equals("seed_reset.sql"), count == 0, file);
            if (count > 0) {
                int id = jdbc.queryForObject("SELECT min(package_id) FROM package", Integer.class);
                var value = row();
                repository.upsert(
                        new CommunitySnapshotRow(
                                id,
                                value.snapshotId(),
                                value.payloadVersion(),
                                value.collectedAt(),
                                value.dataStatus(),
                                value.result()));
            }
        }
    }
}
