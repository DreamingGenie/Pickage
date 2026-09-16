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
 * S15P21A506-373 4단계 — {@link CommunityMapReduceSummarizer}가 이슈 크기와 무관하게 항상
 * {@link CommunitySummarySourceBundle#highlights}(반응 최다 댓글 + 유지관리자 답글)만으로 단일
 * 호출한다는 걸 검증한다. 2026-09-16 오세진 님 결정으로 배치(Map-Reduce) 경로는 이 진입점에서
 * 더 이상 쓰지 않는다 — {@code batches()}/{@code mapReduce()} 자체는 코드에 남아 있다
 * (재사용 가능성 대비, 이 경로에서 호출만 안 함).
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

    /** 4000자 댓글 15개 — 예전 배치(Map-Reduce) 경로였다면 여러 번 호출됐을 만큼 큰 이슈. */
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
    void 작은_이슈는_highlights_bundle로_단일_호출한다() {
        var delegate = RecordingSummarizer.alwaysReady();

        var attempt = mapReduce(delegate).summarizeAsync(smallIssue(), BUDGET).join();

        assertThat(delegate.summarizeCalls).hasSize(1);
        assertThat(delegate.reduceCalls.get()).isZero();
        assertThat(attempt.raw().status()).isEqualTo(SummaryStatus.READY);
        assertThat(attempt.bundle()).isEqualTo(CommunitySummarySourceBundle.highlights(smallIssue()));
    }

    @Test
    void 댓글이_많은_이슈도_배치_없이_highlights_bundle로_단일_호출한다() {
        // 2026-09-16 오세진 님 결정 — 논의 전체를 배치로 나눠 재구성하지 않고, 이슈 크기와
        // 무관하게 항상 반응 최다 댓글 + 유지관리자 답글만 골라 단일 호출한다.
        var delegate = RecordingSummarizer.alwaysReady();

        var attempt = mapReduce(delegate).summarizeAsync(bigIssue(), BUDGET).join();

        assertThat(delegate.summarizeCalls).hasSize(1);
        assertThat(delegate.reduceCalls.get()).isZero();
        assertThat(attempt.raw().status()).isEqualTo(SummaryStatus.READY);
        assertThat(attempt.bundle()).isEqualTo(CommunitySummarySourceBundle.highlights(bigIssue()));
        assertThat(attempt.bundle().issue().comments())
                .as("highlights는 댓글 최대 3개만 골라야 한다")
                .hasSizeLessThanOrEqualTo(3);
    }

    @Test
    void 요약이_실패하면_그대로_실패를_반환한다() {
        var delegate = RecordingSummarizer.alwaysFailed();

        var attempt = mapReduce(delegate).summarizeAsync(bigIssue(), BUDGET).join();

        assertThat(delegate.reduceCalls.get()).isZero();
        assertThat(attempt.raw().status()).isEqualTo(SummaryStatus.FAILED);
    }

    /** 호출 인자·횟수를 기록하는 {@link CommunitySummarizer} 대역. */
    private static final class RecordingSummarizer implements CommunitySummarizer {
        final List<CollectedIssue> summarizeCalls = new CopyOnWriteArrayList<>();
        final AtomicInteger reduceCalls = new AtomicInteger();
        private final boolean fail;

        private RecordingSummarizer(boolean fail) {
            this.fail = fail;
        }

        static RecordingSummarizer alwaysReady() {
            return new RecordingSummarizer(false);
        }

        static RecordingSummarizer alwaysFailed() {
            return new RecordingSummarizer(true);
        }

        @Override
        public TopicSummary summarize(CollectedIssue issue, Duration budget) {
            summarizeCalls.add(issue);
            return fail ? TopicSummary.failed() : readySummaryCitingIssueBody(issue);
        }

        @Override
        public TopicSummary reduce(List<BatchSummary> parts, Duration budget) {
            reduceCalls.incrementAndGet();
            return readySummaryCitingIssueBody(bigIssue());
        }
    }
}
