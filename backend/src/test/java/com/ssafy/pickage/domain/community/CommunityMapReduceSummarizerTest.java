package com.ssafy.pickage.domain.community;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.pickage.domain.community.collection.CollectedComment;
import com.ssafy.pickage.domain.community.collection.CollectedIssue;
import com.ssafy.pickage.domain.community.collection.CommentCollectionStatus;
import com.ssafy.pickage.domain.community.dto.SummaryStatus;
import com.ssafy.pickage.domain.community.payload.DiscussionStepPayload;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * S15P21A506-373 4단계 — {@link CommunityMapReduceSummarizer}가 제한되지 않은 이슈는 기존 단일
 * 호출 경로를 그대로 쓰고, 제한된 이슈만 배치 Map(+배치별 검증) → Reduce로 처리하는지 검증한다.
 */
class CommunityMapReduceSummarizerTest {

    private static final Instant BASE = Instant.parse("2026-01-01T00:00:00Z");
    private static final Duration BUDGET = Duration.ofSeconds(10);

    private BoundedCommunitySummarizer bounded;

    @AfterEach
    void tearDown() {
        if (bounded != null) bounded.close();
    }

    private CommunityMapReduceSummarizer mapReduce(RecordingSummarizer delegate) {
        bounded = new BoundedCommunitySummarizer(delegate);
        return new CommunityMapReduceSummarizer(bounded);
    }

    private static CollectedIssue smallIssue() {
        return new CollectedIssue(
                1,
                "제목",
                "open",
                BASE,
                "issue-author",
                1,
                0,
                CommentCollectionStatus.COMPLETE,
                List.of(
                        new CollectedComment(
                                "c0", "user0", "NONE", false, BASE, "짧은 댓글", "author-0", 0)),
                List.of(),
                "701",
                BASE,
                "issue-author-id",
                "본문");
    }

    /** 4000자 댓글 15개(60,000자) — 단일 48,000자 예산은 넘지만, 배치당(12,000자) 2~3개씩만 들어가 5배치 상한에 걸린다. */
    private static CollectedIssue bigIssue() {
        var comments = new ArrayList<CollectedComment>();
        for (int i = 0; i < 15; i++)
            comments.add(
                    new CollectedComment(
                            "c" + i,
                            "user" + i,
                            "NONE",
                            false,
                            BASE.plusSeconds(i),
                            "x".repeat(4000),
                            "author-" + i,
                            0));
        return new CollectedIssue(
                1,
                "제목",
                "open",
                BASE,
                "issue-author",
                15,
                0,
                CommentCollectionStatus.COMPLETE,
                comments,
                List.of(),
                "701",
                BASE,
                "issue-author-id",
                "본문");
    }

    private static TopicSummary readySummaryCitingIssueBody(CollectedIssue issue) {
        var support = List.of(new TopicSummary.SourceRef("ISSUE_BODY", issue.sourceIssueId()));
        return new TopicSummary(
                "제목",
                "요약",
                List.of(new DiscussionStepPayload("흐름")),
                List.of(),
                SummaryStatus.READY,
                support,
                List.of(support));
    }

    @Test
    void 댓글이_없어도_본문만으로_limited인_이슈는_배치_대신_단일_호출_경로로_떨어진다() {
        // 본문이 4000자를 넘어 from().limited()는 true지만 댓글이 하나도 없어 batches()는
        // 빈 리스트를 돌려준다(/code-review 지적) — unionBundle()이 빈 리스트를 받아
        // IndexOutOfBoundsException을 던지지 않고, 단일 호출 경로로 안전하게 떨어져야 한다.
        var issue =
                new CollectedIssue(
                        1,
                        "제목",
                        "open",
                        BASE,
                        "issue-author",
                        0,
                        0,
                        CommentCollectionStatus.COMPLETE,
                        List.of(),
                        List.of(),
                        "701",
                        BASE,
                        "issue-author-id",
                        "x".repeat(5000));
        var delegate = RecordingSummarizer.alwaysReady();

        var attempt = mapReduce(delegate).summarizeAsync(issue, BUDGET).join();

        assertThat(delegate.summarizeCalls).hasSize(1);
        assertThat(delegate.reduceCalls.get()).isZero();
        assertThat(attempt.raw().status()).isEqualTo(SummaryStatus.READY);
    }

    @Test
    void 제한되지_않은_이슈는_배치_없이_기존_단일_호출_경로를_그대로_쓴다() {
        var delegate = RecordingSummarizer.alwaysReady();
        var attempt = mapReduce(delegate).summarizeAsync(smallIssue(), BUDGET).join();

        assertThat(delegate.summarizeCalls).hasSize(1);
        assertThat(delegate.reduceCalls.get()).isZero();
        assertThat(attempt.raw().status()).isEqualTo(SummaryStatus.READY);
        assertThat(attempt.bundle()).isEqualTo(CommunitySummarySourceBundle.from(smallIssue()));
    }

    @Test
    void 제한된_이슈는_배치별로_검증된_결과만_모아_Reduce를_한_번_호출한다() {
        var delegate = RecordingSummarizer.alwaysReady();
        var attempt = mapReduce(delegate).summarizeAsync(bigIssue(), BUDGET).join();

        int batchCount = CommunitySummarySourceBundle.batches(bigIssue()).size();
        assertThat(delegate.summarizeCalls).hasSize(batchCount);
        assertThat(delegate.reduceCalls.get()).isEqualTo(1);
        assertThat(delegate.lastReduceParts).hasSize(batchCount); // 전부 검증 통과
        assertThat(attempt.bundle().sources()).isNotEmpty();
    }

    @Test
    void 모든_배치가_검증에_실패하면_Reduce를_호출하지_않고_실패를_반환한다() {
        var delegate = RecordingSummarizer.alwaysFailed();
        var attempt = mapReduce(delegate).summarizeAsync(bigIssue(), BUDGET).join();

        assertThat(delegate.reduceCalls.get()).isZero();
        assertThat(attempt.raw().status()).isEqualTo(SummaryStatus.FAILED);
    }

    @Test
    void 일부_배치만_검증을_통과하면_Reduce에는_그_배치들만_넘어간다() {
        var delegate = RecordingSummarizer.failFirstCall();
        var attempt = mapReduce(delegate).summarizeAsync(bigIssue(), BUDGET).join();

        int batchCount = CommunitySummarySourceBundle.batches(bigIssue()).size();
        assertThat(delegate.reduceCalls.get()).isEqualTo(1);
        assertThat(delegate.lastReduceParts).hasSize(batchCount - 1);
        assertThat(attempt).isNotNull();
    }

    /** 호출 인자·횟수를 기록하는 {@link CommunitySummarizer} 대역. */
    private static final class RecordingSummarizer implements CommunitySummarizer {
        final List<CollectedIssue> summarizeCalls = new CopyOnWriteArrayList<>();
        final AtomicInteger reduceCalls = new AtomicInteger();
        final AtomicInteger summarizeCallIndex = new AtomicInteger();
        volatile List<BatchSummary> lastReduceParts = List.of();
        private final java.util.function.IntPredicate failOnCallIndex;

        private RecordingSummarizer(java.util.function.IntPredicate failOnCallIndex) {
            this.failOnCallIndex = failOnCallIndex;
        }

        static RecordingSummarizer alwaysReady() {
            return new RecordingSummarizer(i -> false);
        }

        static RecordingSummarizer alwaysFailed() {
            return new RecordingSummarizer(i -> true);
        }

        static RecordingSummarizer failFirstCall() {
            return new RecordingSummarizer(i -> i == 0);
        }

        @Override
        public TopicSummary summarize(CollectedIssue issue, Duration budget) {
            summarizeCalls.add(issue);
            int index = summarizeCallIndex.getAndIncrement();
            return failOnCallIndex.test(index) ? TopicSummary.failed() : readySummaryCitingIssueBody(issue);
        }

        @Override
        public TopicSummary reduce(List<BatchSummary> parts, Duration budget) {
            reduceCalls.incrementAndGet();
            lastReduceParts = parts;
            return readySummaryCitingIssueBody(bigIssue());
        }
    }
}
