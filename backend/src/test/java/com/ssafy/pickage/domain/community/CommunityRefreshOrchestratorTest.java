package com.ssafy.pickage.domain.community;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.pickage.domain.community.collection.CollectedIssue;
import com.ssafy.pickage.domain.community.collection.CommentCollectionStatus;
import com.ssafy.pickage.domain.community.collection.IssueCollectionResult;
import com.ssafy.pickage.domain.community.collection.RepositoryIssueCounts;
import com.ssafy.pickage.domain.community.dto.CommunityErrorCode;
import com.ssafy.pickage.domain.community.dto.SummaryStatus;
import com.ssafy.pickage.domain.community.refresh.RefreshStatus;
import com.ssafy.pickage.domain.community.refresh.RefreshTask;
import com.ssafy.pickage.domain.community.verification.RepositoryScope;
import com.ssafy.pickage.domain.community.verification.RepositoryVerificationResult;

import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;

/**
 * Mockito 없이 하위 클래스 대역({@code Stub*}·{@code InMemoryCommunitySnapshotRepository})으로 213/212/314를
 * 대체해 {@link CommunityRefreshOrchestrator}의 분기·게시 로직만 검증한다.
 */
@org.junit.jupiter.api.extension.ExtendWith(
        com.ssafy.pickage.domain.community.CommunityTestFixtures.Cleanup.class)
class CommunityRefreshOrchestratorTest {

    private static final int PACKAGE_ID = 42;
    private static final CommunitySummarizer SKIPPED_SUMMARIZER =
            FakeCommunitySummarizer_asFunction();

    private static CommunitySummarizer FakeCommunitySummarizer_asFunction() {
        return (issue, budget) ->
                new TopicSummary(
                        null,
                        null,
                        List.of(),
                        SummaryStatus.SKIPPED,
                        List.of());
    }

    private static CollectedIssue issue(int number, List<String> limitations) {
        return new CollectedIssue(
                number,
                "title",
                "open",
                Instant.parse("2026-05-01T00:00:00Z"),
                "octocat",
                10,
                3,
                CommentCollectionStatus.COMPLETE,
                List.of(),
                limitations,
                String.valueOf(1000L + number),
                Instant.parse("2026-05-01T00:00:00Z"),
                "123",
                "fixture body");
    }

    private static RefreshTask newTask() {
        return new RefreshTask(PACKAGE_ID, RefreshStatus.RUNNING);
    }

    @Test
    void 검증_성공_수집_성공_제한없음이면_AVAILABLE로_게시하고_task를_완료한다() {
        RepositoryVerificationResult verified =
                new RepositoryVerificationResult.Verified(
                        "pinojs", "pino", RepositoryScope.PACKAGE_SCOPED, false, false, List.of());
        IssueCollectionResult success =
                new IssueCollectionResult.Success(List.of(issue(1, List.of())), List.of(), 180);
        InMemoryCommunitySnapshotRepository repository = new InMemoryCommunitySnapshotRepository();
        CommunityRefreshOrchestrator orchestrator =
                com.ssafy.pickage.domain.community.CommunityTestFixtures.orchestrator(
                        new StubRepositoryVerificationService(verified),
                        new StubIssueCollectionService(success),
                        SKIPPED_SUMMARIZER,
                        repository);
        RefreshTask task = newTask();

        orchestrator.run(task, "pino", PACKAGE_ID, "https://github.com/pinojs/pino");

        CommunitySnapshotRow row = repository.findByPackageId(PACKAGE_ID).orElseThrow();
        assertThat(row.dataStatus()).isEqualTo(DataStatus.AVAILABLE);
        assertThat(row.result().repository().fullName()).isEqualTo("pinojs/pino");
        assertThat(row.result().topics()).hasSize(1);
        assertThat(row.result().topics().getFirst().state()).isEqualTo("OPEN");
        assertThat(row.result().limitations()).extracting("code").contains("SUMMARY_UNAVAILABLE");
        assertThat(task.snapshot().status()).isEqualTo(RefreshStatus.COMPLETED);
    }

    // ---- 저장소 전체 Issue 수 (S15P21A506-413)

    private static final RepositoryVerificationResult VERIFIED =
            new RepositoryVerificationResult.Verified(
                    "pinojs", "pino", RepositoryScope.PACKAGE_SCOPED, false, false, List.of());

    private CommunitySnapshotRow runWith(
            StubIssueCollectionService collection, InMemoryCommunitySnapshotRepository repository) {
        CommunityRefreshOrchestrator orchestrator =
                com.ssafy.pickage.domain.community.CommunityTestFixtures.orchestrator(
                        new StubRepositoryVerificationService(VERIFIED),
                        collection,
                        SKIPPED_SUMMARIZER,
                        repository);
        orchestrator.run(newTask(), "pino", PACKAGE_ID, null);
        return repository.findByPackageId(PACKAGE_ID).orElseThrow();
    }

    private static StubIssueCollectionService successCollection() {
        return new StubIssueCollectionService(
                new IssueCollectionResult.Success(List.of(issue(1, List.of())), List.of(), 180));
    }

    @Test
    void 공용_풀이_막혀_있어도_수집을_끝내고_저장소_Issue_수를_싣는다() throws Exception {
        // S15P21A506-415 — 코어가 적은 배포 서버에서 모든 패키지의 수치가 비었다. 수치 조회를 GMS 와 나란히 공용 풀에 올렸는데,
        // 그 풀이 GMS 응답 대기에 다 잡혀 조회가 예산이 바닥난 뒤에야 시작했기 때문이다. 풀을 전부 붙잡아 그 상황을 만든다.
        var collection = successCollection();
        collection.counts = new RepositoryIssueCounts(1234, 56);

        try (var blocked = new CommonPoolBlocker()) {
            var row =
                    org.junit.jupiter.api.Assertions.assertTimeoutPreemptively(
                            java.time.Duration.ofSeconds(15),
                            () -> runWith(collection, new InMemoryCommunitySnapshotRepository()),
                            "공용 풀에 기대면 수집이 멈추거나 수치가 빈다");

            assertThat(row.dataStatus()).isEqualTo(DataStatus.AVAILABLE);
            assertThat(row.result().repository().issueCount()).isEqualTo(1234);
            assertThat(row.result().repository().openIssueCount()).isEqualTo(56);
        }
    }

    @Test
    void 저장소_전체_Issue_수와_열린_수를_결과에_싣는다() {
        var collection = successCollection();
        collection.counts = new RepositoryIssueCounts(1234, 56);

        var row = runWith(collection, new InMemoryCommunitySnapshotRepository());

        assertThat(row.result().repository().issueCount()).isEqualTo(1234);
        assertThat(row.result().repository().openIssueCount()).isEqualTo(56);
        assertThat(row.dataStatus()).isEqualTo(DataStatus.AVAILABLE);
    }

    @Test
    void 최근_논의가_없어도_저장소_전체_Issue_수는_싣는다() {
        var collection =
                new StubIssueCollectionService(new IssueCollectionResult.NoDiscussionData(365, List.of()));
        collection.counts = new RepositoryIssueCounts(800, 12);

        var row = runWith(collection, new InMemoryCommunitySnapshotRepository());

        assertThat(row.dataStatus()).isEqualTo(DataStatus.NO_DISCUSSION_DATA);
        assertThat(row.result().repository().issueCount()).isEqualTo(800);
        assertThat(row.result().repository().openIssueCount()).isEqualTo(12);
    }

    @Test
    void Issue_수를_못_구해도_결과는_그대로_게시하고_수치만_비운다() {
        var collection = successCollection();
        collection.countsFailure = new IllegalStateException("boom");

        var row = runWith(collection, new InMemoryCommunitySnapshotRepository());

        assertThat(row.dataStatus()).isEqualTo(DataStatus.AVAILABLE);
        assertThat(row.result().topics()).hasSize(1);
        assertThat(row.result().repository().issueCount()).isNull();
        assertThat(row.result().repository().openIssueCount()).isNull();
    }

    @Test
    void 앞뒤가_맞지_않는_수치는_게시_검증에서_실패하지_않도록_버린다() {
        // 열린 수가 전체보다 크거나 음수인 값이 게시 검증까지 가면 결과 전체가 PUBLISH_FAILED 가 된다.
        var collection = successCollection();
        collection.counts = new RepositoryIssueCounts(5, 9);
        var row = runWith(collection, new InMemoryCommunitySnapshotRepository());
        assertThat(row.dataStatus()).isEqualTo(DataStatus.AVAILABLE);
        assertThat(row.result().repository().issueCount()).isNull();

        var negative = successCollection();
        negative.counts = new RepositoryIssueCounts(-1, 0);
        var row2 = runWith(negative, new InMemoryCommunitySnapshotRepository());
        assertThat(row2.dataStatus()).isEqualTo(DataStatus.AVAILABLE);
        assertThat(row2.result().repository().issueCount()).isNull();
    }

    @Test
    void 검색_불완전_제한이_있으면_PARTIAL로_게시한다() {
        RepositoryVerificationResult verified =
                new RepositoryVerificationResult.Verified(
                        "pinojs", "pino", RepositoryScope.PACKAGE_SCOPED, false, false, List.of());
        IssueCollectionResult success =
                new IssueCollectionResult.Success(
                        List.of(issue(1, List.of())), List.of("SEARCH_INCOMPLETE"), 180);
        InMemoryCommunitySnapshotRepository repository = new InMemoryCommunitySnapshotRepository();
        CommunityRefreshOrchestrator orchestrator =
                com.ssafy.pickage.domain.community.CommunityTestFixtures.orchestrator(
                        new StubRepositoryVerificationService(verified),
                        new StubIssueCollectionService(success),
                        SKIPPED_SUMMARIZER,
                        repository);

        orchestrator.run(newTask(), "pino", PACKAGE_ID, null);

        CommunitySnapshotRow row = repository.findByPackageId(PACKAGE_ID).orElseThrow();
        assertThat(row.dataStatus()).isEqualTo(DataStatus.PARTIAL);
        assertThat(row.result().limitations()).extracting("code").contains("SEARCH_INCOMPLETE");
    }

    @Test
    void 범위가_제한되고_archived면_REPOSITORY_WIDE_ARCHIVED_제한과_함께_AVAILABLE로_게시한다() {
        RepositoryVerificationResult verified =
                new RepositoryVerificationResult.Verified(
                        "owner",
                        "repo",
                        RepositoryScope.REPOSITORY_WIDE,
                        true,
                        true,
                        List.of(
                                CommunityPolicy.limitation("REPOSITORY_WIDE_SCOPE", null),
                                CommunityPolicy.limitation("REPOSITORY_ARCHIVED", null)));
        IssueCollectionResult success =
                new IssueCollectionResult.Success(List.of(issue(1, List.of())), List.of(), 180);
        InMemoryCommunitySnapshotRepository repository = new InMemoryCommunitySnapshotRepository();
        CommunityRefreshOrchestrator orchestrator =
                com.ssafy.pickage.domain.community.CommunityTestFixtures.orchestrator(
                        new StubRepositoryVerificationService(verified),
                        new StubIssueCollectionService(success),
                        SKIPPED_SUMMARIZER,
                        repository);

        orchestrator.run(newTask(), "pkg", PACKAGE_ID, null);

        CommunitySnapshotRow row = repository.findByPackageId(PACKAGE_ID).orElseThrow();
        assertThat(row.dataStatus()).isEqualTo(DataStatus.AVAILABLE);
        assertThat(row.result().limitations())
                .extracting("code")
                .contains("REPOSITORY_WIDE_SCOPE", "REPOSITORY_ARCHIVED");
    }

    @Test
    void 저장소_미확인이면_repository_없이_UNVERIFIED_REPOSITORY로_게시한다() {
        RepositoryVerificationResult unverified =
                new RepositoryVerificationResult.UnverifiedRepository("npm registry에 패키지가 없음");
        InMemoryCommunitySnapshotRepository repository = new InMemoryCommunitySnapshotRepository();
        CommunityRefreshOrchestrator orchestrator =
                com.ssafy.pickage.domain.community.CommunityTestFixtures.orchestrator(
                        new StubRepositoryVerificationService(unverified),
                        new StubIssueCollectionService(
                                new IssueCollectionResult.NoDiscussionData(180, List.of())),
                        SKIPPED_SUMMARIZER,
                        repository);

        orchestrator.run(newTask(), "pkg", PACKAGE_ID, null);

        CommunitySnapshotRow row = repository.findByPackageId(PACKAGE_ID).orElseThrow();
        assertThat(row.dataStatus()).isEqualTo(DataStatus.UNVERIFIED_REPOSITORY);
        assertThat(row.result().repository()).isNull();
        assertThat(row.result().topics()).isEmpty();
    }

    @Test
    void host가_미지원이면_UNSUPPORTED_HOST로_게시한다() {
        RepositoryVerificationResult unsupported =
                new RepositoryVerificationResult.UnsupportedHost("https://gitlab.com/owner/repo");
        InMemoryCommunitySnapshotRepository repository = new InMemoryCommunitySnapshotRepository();
        CommunityRefreshOrchestrator orchestrator =
                com.ssafy.pickage.domain.community.CommunityTestFixtures.orchestrator(
                        new StubRepositoryVerificationService(unsupported),
                        new StubIssueCollectionService(
                                new IssueCollectionResult.NoDiscussionData(180, List.of())),
                        SKIPPED_SUMMARIZER,
                        repository);

        orchestrator.run(newTask(), "pkg", PACKAGE_ID, null);

        assertThat(repository.findByPackageId(PACKAGE_ID).orElseThrow().dataStatus())
                .isEqualTo(DataStatus.UNSUPPORTED_HOST);
    }

    @Test
    void 범위가_모호하면_repository_null로_AMBIGUOUS_SCOPE를_게시한다() {
        RepositoryVerificationResult ambiguous =
                new RepositoryVerificationResult.AmbiguousScope("owner", "repo");
        InMemoryCommunitySnapshotRepository repository = new InMemoryCommunitySnapshotRepository();
        CommunityRefreshOrchestrator orchestrator =
                com.ssafy.pickage.domain.community.CommunityTestFixtures.orchestrator(
                        new StubRepositoryVerificationService(ambiguous),
                        new StubIssueCollectionService(
                                new IssueCollectionResult.NoDiscussionData(180, List.of())),
                        SKIPPED_SUMMARIZER,
                        repository);

        orchestrator.run(newTask(), "pkg", PACKAGE_ID, null);

        CommunitySnapshotRow row = repository.findByPackageId(PACKAGE_ID).orElseThrow();
        assertThat(row.dataStatus()).isEqualTo(DataStatus.AMBIGUOUS_SCOPE);
        assertThat(row.result().repository()).isNull();
    }

    @Test
    void 논의가_없으면_검증된_저장소_정보와_함께_NO_DISCUSSION_DATA로_게시한다() {
        RepositoryVerificationResult verified =
                new RepositoryVerificationResult.Verified(
                        "owner", "repo", RepositoryScope.PACKAGE_SCOPED, false, false, List.of());
        InMemoryCommunitySnapshotRepository repository = new InMemoryCommunitySnapshotRepository();
        CommunityRefreshOrchestrator orchestrator =
                com.ssafy.pickage.domain.community.CommunityTestFixtures.orchestrator(
                        new StubRepositoryVerificationService(verified),
                        new StubIssueCollectionService(
                                new IssueCollectionResult.NoDiscussionData(180, List.of())),
                        SKIPPED_SUMMARIZER,
                        repository);

        orchestrator.run(newTask(), "pkg", PACKAGE_ID, null);

        CommunitySnapshotRow row = repository.findByPackageId(PACKAGE_ID).orElseThrow();
        assertThat(row.dataStatus()).isEqualTo(DataStatus.NO_DISCUSSION_DATA);
        assertThat(row.result().repository().fullName()).isEqualTo("owner/repo");
    }

    @Test
    void 검증에서_rate_limit이면_게시하지_않고_task를_GITHUB_RATE_LIMITED로_실패시킨다() {
        Instant retryAt = Instant.now().plusSeconds(600);
        RepositoryVerificationResult limited =
                new RepositoryVerificationResult.FetchLimited("GitHub rate limit", retryAt);
        InMemoryCommunitySnapshotRepository repository = new InMemoryCommunitySnapshotRepository();
        CommunityRefreshOrchestrator orchestrator =
                com.ssafy.pickage.domain.community.CommunityTestFixtures.orchestrator(
                        new StubRepositoryVerificationService(limited),
                        new StubIssueCollectionService(
                                new IssueCollectionResult.NoDiscussionData(180, List.of())),
                        SKIPPED_SUMMARIZER,
                        repository);
        RefreshTask task = newTask();

        orchestrator.run(task, "pkg", PACKAGE_ID, null);

        assertThat(repository.findByPackageId(PACKAGE_ID)).isEmpty();
        RefreshTask.Snapshot snapshot = task.snapshot();
        assertThat(snapshot.status()).isEqualTo(RefreshStatus.FAILED);
        assertThat(snapshot.errorCode()).isEqualTo(CommunityErrorCode.GITHUB_RATE_LIMITED);
        assertThat(snapshot.retryAt()).isEqualTo(retryAt);
    }

    @Test
    void 검증에서_npm_통신_오류면_NPM_UNAVAILABLE로_실패시킨다() {
        RepositoryVerificationResult limited =
                new RepositoryVerificationResult.FetchLimited("npm registry 통신 오류", null);
        InMemoryCommunitySnapshotRepository repository = new InMemoryCommunitySnapshotRepository();
        CommunityRefreshOrchestrator orchestrator =
                com.ssafy.pickage.domain.community.CommunityTestFixtures.orchestrator(
                        new StubRepositoryVerificationService(limited),
                        new StubIssueCollectionService(
                                new IssueCollectionResult.NoDiscussionData(180, List.of())),
                        SKIPPED_SUMMARIZER,
                        repository);
        RefreshTask task = newTask();

        orchestrator.run(task, "pkg", PACKAGE_ID, null);

        assertThat(task.snapshot().errorCode()).isEqualTo(CommunityErrorCode.NPM_UNAVAILABLE);
        assertThat(task.snapshot().retryAt()).isAfter(Instant.now());
    }

    @Test
    void 수집에서_시간_예산_소진이면_deadline_exceeded로_실패시킨다() {
        RepositoryVerificationResult verified =
                new RepositoryVerificationResult.Verified(
                        "owner", "repo", RepositoryScope.PACKAGE_SCOPED, false, false, List.of());
        IssueCollectionResult limited = new IssueCollectionResult.FetchLimited("시간 예산 소진", null);
        InMemoryCommunitySnapshotRepository repository = new InMemoryCommunitySnapshotRepository();
        CommunityRefreshOrchestrator orchestrator =
                com.ssafy.pickage.domain.community.CommunityTestFixtures.orchestrator(
                        new StubRepositoryVerificationService(verified),
                        new StubIssueCollectionService(limited),
                        SKIPPED_SUMMARIZER,
                        repository);
        RefreshTask task = newTask();

        orchestrator.run(task, "pkg", PACKAGE_ID, null);

        assertThat(repository.findByPackageId(PACKAGE_ID)).isEmpty();
        assertThat(task.snapshot().errorCode())
                .isEqualTo(CommunityErrorCode.REFRESH_DEADLINE_EXCEEDED);
    }

    @Test
    void 이슈_요약이_실패해도_다른_이슈는_계속_진행하고_summary_retry_at을_채운다() {
        RepositoryVerificationResult verified =
                new RepositoryVerificationResult.Verified(
                        "owner", "repo", RepositoryScope.PACKAGE_SCOPED, false, false, List.of());
        IssueCollectionResult success =
                new IssueCollectionResult.Success(List.of(issue(1, List.of())), List.of(), 180);
        InMemoryCommunitySnapshotRepository repository = new InMemoryCommunitySnapshotRepository();
        CommunitySummarizer throwingSummarizer =
                (issueArg, budget) -> {
                    throw new RuntimeException("GMS 흉내 실패");
                };
        CommunityRefreshOrchestrator orchestrator =
                com.ssafy.pickage.domain.community.CommunityTestFixtures.orchestrator(
                        new StubRepositoryVerificationService(verified),
                        new StubIssueCollectionService(success),
                        throwingSummarizer,
                        repository);
        RefreshTask task = newTask();

        orchestrator.run(task, "pkg", PACKAGE_ID, null);

        CommunitySnapshotRow row = repository.findByPackageId(PACKAGE_ID).orElseThrow();
        // 요약 실패는 data_status(수집 관점)에 영향을 주지 않는다 — summary_status만의 문제다.
        assertThat(row.dataStatus()).isEqualTo(DataStatus.AVAILABLE);
        assertThat(row.result().topics().getFirst().summaryStatus()).isEqualTo("FAILED");
        assertThat(row.result().summaryRetryAt()).isNotNull();
        assertThat(task.snapshot().status()).isEqualTo(RefreshStatus.COMPLETED);
    }

    @Test
    void 이슈_두_개의_GMS_호출을_동시에_디스패치한다() {
        // S15P21A506-368 후속 — 순차 for 루프였을 때 대형 저장소에서 실제로 HttpTimeoutException/
        // InterruptedException으로 터졌던 문제의 재발 방지 시험. 각 호출을 300ms씩 일부러 늦추고,
        // 전체 refresh가 두 호출을 합친 시간(600ms)이 아니라 한 호출 시간(300ms) 안팎에 끝나는지,
        // 그리고 두 호출의 시작 시각이 실제로 거의 겹치는지를 함께 확인한다.
        var callStartedAtNanos = java.util.Collections.synchronizedList(new java.util.ArrayList<Long>());
        CommunitySummarizer slowSummarizer =
                (issueArg, budget) -> {
                    callStartedAtNanos.add(System.nanoTime());
                    try {
                        Thread.sleep(300);
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    }
                    return TopicSummary.failed();
                };
        RepositoryVerificationResult verified =
                new RepositoryVerificationResult.Verified(
                        "pinojs", "pino", RepositoryScope.PACKAGE_SCOPED, false, false, List.of());
        IssueCollectionResult success =
                new IssueCollectionResult.Success(
                        List.of(issue(1, List.of()), issue(2, List.of())), List.of(), 180);
        InMemoryCommunitySnapshotRepository repository = new InMemoryCommunitySnapshotRepository();
        CommunityRefreshOrchestrator orchestrator =
                com.ssafy.pickage.domain.community.CommunityTestFixtures.orchestrator(
                        new StubRepositoryVerificationService(verified),
                        new StubIssueCollectionService(success),
                        slowSummarizer,
                        repository);
        RefreshTask task = newTask();

        long startNanos = System.nanoTime();
        orchestrator.run(task, "pino", PACKAGE_ID, "https://github.com/pinojs/pino");
        long elapsedMs = (System.nanoTime() - startNanos) / 1_000_000;

        CommunitySnapshotRow row = repository.findByPackageId(PACKAGE_ID).orElseThrow();
        assertThat(row.result().topics()).hasSize(2);
        assertThat(row.result().topics())
                .extracting(t -> t.issueNumber())
                .containsExactly(1, 2); // 병렬로 돌아도 결과 순서는 원래 이슈 순서를 유지한다

        assertThat(callStartedAtNanos).hasSize(2);
        long startGapMs =
                Math.abs(callStartedAtNanos.get(0) - callStartedAtNanos.get(1)) / 1_000_000;
        assertThat(startGapMs)
                .as("두 GMS 호출이 순차였다면 300ms 가까이 벌어졌을 것이다")
                .isLessThan(150);
        assertThat(elapsedMs)
                .as("순차였다면 600ms 이상 걸린다 — 병렬이면 300ms 안팎(+오버헤드)이어야 한다")
                .isLessThan(550);
    }

    @Test
    void 게시_자체가_실패하면_PUBLISH_FAILED로_task를_실패시킨다() {
        RepositoryVerificationResult verified =
                new RepositoryVerificationResult.Verified(
                        "owner", "repo", RepositoryScope.PACKAGE_SCOPED, false, false, List.of());
        InMemoryCommunitySnapshotRepository repository = new InMemoryCommunitySnapshotRepository();
        repository.failNextUpsertWith(new RuntimeException("advisory lock timeout"));
        CommunityRefreshOrchestrator orchestrator =
                com.ssafy.pickage.domain.community.CommunityTestFixtures.orchestrator(
                        new StubRepositoryVerificationService(verified),
                        new StubIssueCollectionService(
                                new IssueCollectionResult.NoDiscussionData(180, List.of())),
                        SKIPPED_SUMMARIZER,
                        repository);
        RefreshTask task = newTask();

        orchestrator.run(task, "pkg", PACKAGE_ID, null);

        assertThat(task.snapshot().status()).isEqualTo(RefreshStatus.FAILED);
        assertThat(task.snapshot().errorCode()).isEqualTo(CommunityErrorCode.PUBLISH_FAILED);
    }

    @Test
    void 예상하지_못한_예외는_전체를_중단시키지_않고_실패로_귀결된다() {
        CommunitySummarizer unusedSummarizer = SKIPPED_SUMMARIZER;
        InMemoryCommunitySnapshotRepository repository = new InMemoryCommunitySnapshotRepository();
        com.ssafy.pickage.domain.community.verification.RepositoryVerificationService
                throwingVerification =
                        new StubRepositoryVerificationService(
                                new RepositoryVerificationResult.UnverifiedRepository("x")) {
                            @Override
                            public RepositoryVerificationResult verify(
                                    String packageName,
                                    String dbRepoUrl,
                                    java.time.Duration budget) {
                                throw new IllegalStateException("boom");
                            }
                        };
        CommunityRefreshOrchestrator orchestrator =
                com.ssafy.pickage.domain.community.CommunityTestFixtures.orchestrator(
                        throwingVerification,
                        new StubIssueCollectionService(
                                new IssueCollectionResult.NoDiscussionData(180, List.of())),
                        unusedSummarizer,
                        repository);
        RefreshTask task = newTask();

        orchestrator.run(task, "pkg", PACKAGE_ID, null);

        assertThat(task.snapshot().status()).isEqualTo(RefreshStatus.FAILED);
    }
}
