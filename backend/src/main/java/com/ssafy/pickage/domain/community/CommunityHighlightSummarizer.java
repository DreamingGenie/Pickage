package com.ssafy.pickage.domain.community;

import com.ssafy.pickage.domain.community.collection.CollectedIssue;

import java.time.Duration;
import java.util.concurrent.CompletableFuture;

/**
 * {@link CommunityRefreshOrchestrator}가 쓰는 이슈 단위 요약 진입점. 이슈 크기와 무관하게
 * {@link CommunitySummarySourceBundle#highlights}(반응 최다 댓글 + 유지관리자 답글 + 그 주변
 * 댓글, 최대 3개)로 입력을 항상 작게 유지한 뒤 {@link BoundedCommunitySummarizer}로 단일
 * 호출한다(2026-09-16 오세진 님 결정 — 논의 전체를 배치로 나눠 재구성하는 Map-Reduce 방식은
 * 시연에 필요한 시간·비용을 못 맞춰 폐기했다).
 *
 * <p>최종 검증은 여기서 하지 않는다 — {@link CommunityRefreshOrchestrator}가
 * {@link CommunitySummaryValidator#validate}를 한 번 호출하되, 그 대상 bundle을 {@link
 * SummaryAttempt#bundle()}로 받는다.
 */
public final class CommunityHighlightSummarizer {
    private final BoundedCommunitySummarizer bounded;

    public CommunityHighlightSummarizer(BoundedCommunitySummarizer bounded) {
        this.bounded = bounded;
    }

    public CompletableFuture<SummaryAttempt> summarizeAsync(CollectedIssue issue, Duration budget) {
        var single = CommunitySummarySourceBundle.highlights(issue);
        return bounded.summarizeAsync(single, budget).thenApply(raw -> new SummaryAttempt(single, raw));
    }

    /** 요약 결과(raw, 미검증) + 그 결과를 검증해야 할 bundle. */
    public record SummaryAttempt(CommunitySummarySourceBundle bundle, TopicSummary raw) {}
}
