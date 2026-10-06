package com.ssafy.pickage.domain.community;

import static org.junit.jupiter.api.Assertions.*;

import com.ssafy.pickage.domain.community.collection.*;
import com.ssafy.pickage.domain.community.dto.*;
import com.ssafy.pickage.domain.community.payload.*;
import com.ssafy.pickage.domain.community.refresh.*;
import com.ssafy.pickage.domain.community.verification.*;

import org.junit.jupiter.api.Test;

import java.time.*;
import java.util.*;

// 기대값은 구현계획 §5/6에서 가져왔다. 수정 전 실패를 보존하는 검수 전용 시험.
@org.junit.jupiter.api.extension.ExtendWith(
        com.ssafy.pickage.domain.community.CommunityTestFixtures.Cleanup.class)
class CommunityContractReviewTest {
    @Test
    void R10_failureLogsContainOnlySafeIdentifiers() {
        var logger =
                (ch.qos.logback.classic.Logger)
                        org.slf4j.LoggerFactory.getLogger(CommunityRefreshOrchestrator.class);
        var appender =
                new ch.qos.logback.core.read.ListAppender<
                        ch.qos.logback.classic.spi.ILoggingEvent>();
        appender.start();
        logger.addAppender(appender);
        try {
            store.failNextUpsertWith(new IllegalStateException("raw-source-token-sentinel"));
            orchestrator(new FakeCommunitySummarizer())
                    .run(new RefreshTask(7, RefreshStatus.RUNNING), "fixture", 7, null);
            assertFalse(appender.list.isEmpty());
            for (var event : appender.list) {
                assertFalse(event.getFormattedMessage().contains("raw-source-token-sentinel"));
                assertNull(event.getThrowableProxy());
            }
        } finally {
            logger.detachAppender(appender);
            appender.stop();
        }
    }

    @Test
    void R05_summaryCannotInventSourceOrAuthorMetadata() {
        var original = issue(1);
        var comment =
                new CollectedComment(
                        "2001",
                        "actual-user",
                        "NONE",
                        false,
                        original.createdAt(),
                        "verified comment",
                        "456",
                        0);
        var source =
                new CollectedIssue(
                        1,
                        original.title(),
                        original.state(),
                        original.updatedAt(),
                        "renamed-author",
                        1,
                        2,
                        CommentCollectionStatus.COMPLETE,
                        List.of(comment),
                        List.of(),
                        original.sourceIssueId(),
                        original.createdAt(),
                        "123",
                        original.body());
        var bundle = CommunitySummarySourceBundle.from(source);
        var support = List.of(new TopicSummary.SourceRef("COMMENT", "2001"));
        var summary =
                new TopicSummary(
                        "제목",
                        "요약",
                        List.of(
                                new MessagePayload(
                                        "2001",
                                        "invented",
                                        "OWNER",
                                        true,
                                        "DISCUSSION",
                                        Instant.now(),
                                        "메시지")),
                        SummaryStatus.READY,
                        support);
        var result = CommunitySummaryValidator.validate(bundle, summary);
        assertEquals(SummaryStatus.READY, result.status());
        var message = result.messages().getFirst();
        assertEquals("actual-user", message.authorLogin());
        assertEquals("NONE", message.authorAssociation());
        assertFalse(message.isIssueAuthor());
        assertEquals(comment.createdAt(), message.createdAt());
        var invented = List.of(new TopicSummary.SourceRef("COMMENT", "9999"));
        assertEquals(
                SummaryStatus.FAILED,
                CommunitySummaryValidator.validate(
                                bundle,
                                new TopicSummary(
                                        summary.titleKo(),
                                        summary.summaryKo(),
                                        summary.messages(),
                                        summary.status(),
                                        invented))
                        .status());
    }

    @Test
    void R05_sourceBudgetCountsUnicodeCharactersAndExcludesDroppedSources() {
        var original = issue(1);
        var comments = new ArrayList<CollectedComment>();
        for (int i = 0; i < 20; i++)
            comments.add(
                    new CollectedComment(
                            Integer.toString(2000 + i),
                            "fixture",
                            "NONE",
                            false,
                            original.createdAt().plusSeconds(i),
                            "😀".repeat(5000),
                            "456",
                            0));
        var source =
                new CollectedIssue(
                        1,
                        original.title(),
                        original.state(),
                        original.updatedAt(),
                        original.authorLogin(),
                        20,
                        2,
                        CommentCollectionStatus.COMPLETE,
                        comments,
                        List.of(),
                        original.sourceIssueId(),
                        original.createdAt(),
                        original.authorId(),
                        "😀".repeat(5000));
        var bundle = CommunitySummarySourceBundle.from(source);
        int count = bundle.issue().title().codePointCount(0, bundle.issue().title().length());
        for (String value : bundle.sources().values()) {
            int length = value.codePointCount(0, value.length());
            assertTrue(length <= 4000);
            count += length;
        }
        assertEquals(48000, count);
        assertTrue(bundle.limited());
        assertFalse(bundle.sources().containsKey(new TopicSummary.SourceRef("COMMENT", "2000")));
        assertTrue(bundle.sources().containsKey(new TopicSummary.SourceRef("COMMENT", "2019")));
    }

    @Test
    void R05_summaryTimeoutCancelsWorkerAndPoolCanRecover() throws Exception {
        var interrupted = new java.util.concurrent.CountDownLatch(1);
        var first = new java.util.concurrent.atomic.AtomicBoolean(true);
        try (var bounded =
                new BoundedCommunitySummarizer(
                        (i, budget) -> {
                            if (first.getAndSet(false)) {
                                try {
                                    new java.util.concurrent.CountDownLatch(1).await();
                                } catch (InterruptedException e) {
                                    interrupted.countDown();
                                    Thread.currentThread().interrupt();
                                }
                                return TopicSummary.failed();
                            }
                            return ready(i);
                        })) {
            assertEquals(
                    SummaryStatus.FAILED,
                    bounded.summarize(
                                    CommunitySummarySourceBundle.from(issue(1)),
                                    Duration.ofMillis(100))
                            .status());
            assertTrue(interrupted.await(2, java.util.concurrent.TimeUnit.SECONDS));
            assertEquals(
                    SummaryStatus.READY,
                    bounded.summarize(
                                    CommunitySummarySourceBundle.from(issue(1)),
                                    Duration.ofSeconds(1))
                            .status());
        }
    }

    @Test
    void R05_modelMarkupCannotPassPlainTextContract() {
        for (String text :
                List.of(
                        "<script>bad</script>",
                        "[link](https://example.com)",
                        "https://example.com"))
            assertFalse(CommunitySnapshotValidator.plain(text, 500));
    }

    @Test
    void R05_요약에_포함된_URL은_지워지고_나머지_내용은_그대로_통과한다() {
        // 2026-09-16 오세진 님 결정 — <,>(XSS 방어)는 그대로 거부하되, URL/마크다운 링크는
        // "(링크 생략)"으로 지우고 나머지 텍스트는 살려서 요약 전체가 FAILED로 떨어지지
        // 않게 한다.
        var bundle = CommunitySummarySourceBundle.from(issue(1));
        var support = List.of(new TopicSummary.SourceRef("ISSUE_BODY", bundle.issue().sourceIssueId()));
        var summary =
                new TopicSummary(
                        "제목",
                        "자세한 내용은 https://example.com/advisory 를 참고하세요.",
                        List.of(),
                        SummaryStatus.READY,
                        support);

        var result = CommunitySummaryValidator.validate(bundle, summary);

        assertEquals(SummaryStatus.READY, result.status());
        assertEquals("자세한 내용은 (링크 생략) 를 참고하세요.", result.summaryKo());
        assertFalse(result.summaryKo().contains("https://"));
    }

    @Test
    void R05_HTML_태그는_요약을_버리지_않고_전각으로_바꿔_태그로_읽히지_않게_한다() {
        var bundle = CommunitySummarySourceBundle.from(issue(1));
        var support = List.of(new TopicSummary.SourceRef("ISSUE_BODY", bundle.issue().sourceIssueId()));
        var summary =
                new TopicSummary(
                        "제목",
                        "<script>alert(1)</script>",
                        List.of(),
                        SummaryStatus.READY,
                        support);

        var result = CommunitySummaryValidator.validate(bundle, summary);

        // S15P21A506-412 — 예전에는 여기서 요약 전체가 FAILED 였다. 이제는 꺾쇠만 전각으로 바꿔 살린다.
        assertEquals(SummaryStatus.READY, result.status());
        assertEquals("＜script＞alert(1)＜/script＞", result.summaryKo());
        assertFalse(result.summaryKo().contains("<") || result.summaryKo().contains(">"));
        // 저장 검증기의 원본 꺾쇠 거부는 그대로다 — 치환된 값은 통과한다.
        assertTrue(CommunitySnapshotValidator.plain(result.summaryKo(), 500));
        assertFalse(CommunitySnapshotValidator.plain("<script>", 500));
    }

    final InMemoryCommunitySnapshotRepository store = new InMemoryCommunitySnapshotRepository();
    final RefreshTaskRegistry registry = new RefreshTaskRegistry();

    CommunityService service(RefreshAdmissionCoordinator coordinator) {
        return new CommunityService(
                new StubCommunityPackageLookup(
                        Map.of(
                                "fixture",
                                new CommunityPackageLookup.PackageIdentity(
                                        7, "https://github.com/fixture/repo"))),
                registry,
                coordinator,
                store,
                orchestrator(new FakeCommunitySummarizer()),
                new com.ssafy.pickage.domain.community.CommunityReadiness(true, true, true),
                new com.ssafy.pickage.domain.community.verification.GitHubRateGate());
    }

    CommunityRefreshOrchestrator orchestrator(CommunitySummarizer summarizer) {
        return com.ssafy.pickage.domain.community.CommunityTestFixtures.orchestrator(
                new StubRepositoryVerificationService(
                        new RepositoryVerificationResult.Verified(
                                "fixture",
                                "repo",
                                RepositoryScope.PACKAGE_SCOPED,
                                false,
                                false,
                                List.of())),
                new StubIssueCollectionService(
                        new IssueCollectionResult.Success(
                                List.of(issue(1), issue(2)), List.of(), 180)),
                summarizer,
                store);
    }

    static CollectedIssue issue(int number) {
        return new CollectedIssue(
                number,
                "Fixture",
                "open",
                Instant.parse("2026-09-01T00:00:00Z"),
                "fixture",
                1,
                2,
                CommentCollectionStatus.COMPLETE,
                List.of(),
                List.of(),
                String.valueOf(1000L + number),
                Instant.parse("2026-09-01T00:00:00Z"),
                "123",
                "fixture body");
    }

    static TopicPayload topic(String status) {
        return new TopicPayload(
                String.valueOf(1000L + 1),
                1,
                "OPEN",
                Instant.now(),
                Instant.now(),
                "Fixture",
                null,
                1,
                2,
                "COMPLETE",
                status,
                null,
                List.of());
    }

    void save(List<TopicPayload> topics) {
        store.upsert(
                new CommunitySnapshotRow(
                        7,
                        UUID.randomUUID(),
                        (short) 2,
                        Instant.now().minusSeconds(90000),
                        DataStatus.AVAILABLE,
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
                                topics,
                                List.of())));
    }

    @Test
    void R07_exact24HoursMustBeStale() {
        Instant start = Instant.parse("2026-01-01T00:00:00Z");
        assertFalse(CommunitySnapshotTtl.isFresh(start, start.plus(Duration.ofHours(24))));
    }

    @Test
    void R07_exact7DaysMustNotBeServed() {
        Instant start = Instant.parse("2026-01-01T00:00:00Z");
        assertFalse(CommunitySnapshotTtl.isServable(start, start.plus(Duration.ofDays(7))));
    }

    @Test
    void R08_initialGetMustBeIdleWithNullRefresh() {
        var response = service(null).getStatus("fixture");
        assertAll(
                () -> assertEquals("IDLE", response.viewStatus().name()),
                () -> assertNull(response.refresh()));
    }

    @Test
    void R08_staleWithActiveMustKeepResultView() {
        save(List.of());
        registry.createOrJoin(7, () -> new RefreshTask(7, RefreshStatus.RUNNING));
        assertEquals("RESULT", service(null).getStatus("fixture").viewStatus().name());
    }

    @Test
    void R08_completedStageMustBeNull() {
        var task = registry.createOrJoin(7, () -> new RefreshTask(7, RefreshStatus.RUNNING)).task();
        task.markCompleted();
        assertNull(service(null).getStatus("fixture").refresh().stage());
    }

    @Test
    void R05_mixedSummariesMustBePartial() {
        save(List.of(topic("READY"), topic("FAILED")));
        assertEquals(
                SummaryStatus.PARTIAL, service(null).getStatus("fixture").result().summaryStatus());
    }

    @Test
    void R05_fakeForExistingTopicsMustReportFailure() {
        assertEquals(
                SummaryStatus.FAILED,
                new FakeCommunitySummarizer().summarize(issue(1), Duration.ofSeconds(1)).status());
    }

    @Test
    void R05_partialSummaryMustNotScheduleFiveMinuteRetry() {
        orchestrator((i, budget) -> i.issueNumber() == 1 ? ready(i) : TopicSummary.failed())
                .run(new RefreshTask(7, RefreshStatus.RUNNING), "fixture", 7, null);
        assertNull(store.findByPackageId(7).orElseThrow().result().summaryRetryAt());
    }

    static TopicSummary ready(CollectedIssue issue) {
        var support = List.of(new TopicSummary.SourceRef("ISSUE_BODY", issue.sourceIssueId()));
        return new TopicSummary(
                "확인된 제목",
                "확인된 요약",
                List.of(),
                SummaryStatus.READY,
                support);
    }

    @Test
    void R11_failedTaskMustNotPublishLateResult() {
        var task = new RefreshTask(7, RefreshStatus.RUNNING);
        task.markFailed(
                CommunityErrorCode.REFRESH_DEADLINE_EXCEEDED, Instant.now().plusSeconds(300));
        orchestrator(new FakeCommunitySummarizer()).run(task, "fixture", 7, null);
        assertTrue(store.findByPackageId(7).isEmpty());
    }

    @Test
    void R11_collectedAtMustBeWorkerStart() {
        var task = new RefreshTask(7, RefreshStatus.RUNNING);
        orchestrator(new FakeCommunitySummarizer()).run(task, "fixture", 7, null);
        assertEquals(
                task.snapshot().startedAt(), store.findByPackageId(7).orElseThrow().collectedAt());
    }

    @Test
    void R07_recentFailureMustRejectNewRefresh() {
        var task = registry.createOrJoin(7, () -> new RefreshTask(7, RefreshStatus.RUNNING)).task();
        task.markFailed(CommunityErrorCode.GITHUB_RATE_LIMITED, Instant.now().plusSeconds(300));
        var coordinator = new RefreshAdmissionCoordinator(registry);
        try {
            assertFalse(
                    service(coordinator).refresh("fixture", RefreshTrigger.TAB_OPENED).accepted());
        } finally {
            coordinator.shutdown();
        }
    }

    @Test
    void R08_fullResultKeysMustMatchContract() throws Exception {
        save(List.of(topic("FAILED")));
        var json =
                new CommunityConfig()
                        .communityObjectMapper()
                        .valueToTree(service(null).getStatus("fixture"));
        var result = json.path("result");
        assertAll(
                () -> assertTrue(result.has("summary_retry_at")),
                () -> assertTrue(result.path("summary").has("issue_count")),
                () -> assertTrue(result.path("topics").get(0).has("created_at")),
                () -> assertTrue(result.path("topics").get(0).has("title_original")),
                () -> assertTrue(result.path("repository").has("full_name")),
                () -> assertTrue(result.path("data_limits").has("policy_version")),
                () -> assertTrue(result.path("data_limits").has("lookback_days")));
    }

    @Test
    void R06_typedPayloadMustRejectMissingRequiredFields() {
        assertThrows(
                Exception.class,
                () ->
                        new CommunityConfig()
                                .communityObjectMapper()
                                .readValue("{}", CommunityResultPayload.class));
    }
}
