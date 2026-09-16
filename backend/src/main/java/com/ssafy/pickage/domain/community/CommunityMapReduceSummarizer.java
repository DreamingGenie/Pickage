package com.ssafy.pickage.domain.community;

import com.ssafy.pickage.domain.community.collection.CollectedComment;
import com.ssafy.pickage.domain.community.collection.CollectedIssue;
import com.ssafy.pickage.domain.community.dto.SummaryStatus;

import java.time.Duration;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.CompletableFuture;

/**
 * S15P21A506-373 4단계 — Map-Reduce 오케스트레이션. {@link CommunityRefreshOrchestrator}가
 * 쓰던 {@link BoundedCommunitySummarizer#summarizeAsync}을 이슈 단위로 감싸, 이슈 요약 입력이
 * 48,000자 예산을 넘는 경우({@link CommunitySummarySourceBundle#batches}가 비어 있지 않은 경우)
 * 만 배치 Map(배치별 호출+검증) → Reduce(합성 호출)로 처리하고, 그 외에는 기존 단일 호출
 * 경로를 그대로 위임한다.
 *
 * <p>최종 검증은 여기서 하지 않는다 — {@link CommunityRefreshOrchestrator}가 기존과 동일하게
 * {@link CommunitySummaryValidator#validate}를 한 번 호출하되, 그 대상 bundle을 {@link
 * SummaryAttempt#bundle()}(배치 미사용이면 단일 bundle, 사용이면 배치들의 합집합 bundle)로
 * 바꿔 받는다 — 단일 호출/Map-Reduce 두 경로 모두 "호출자가 자신이 쓴 bundle로 한 번만
 * 검증한다"는 기존 계약을 그대로 유지한다.
 */
public final class CommunityMapReduceSummarizer {
    private final BoundedCommunitySummarizer bounded;

    public CommunityMapReduceSummarizer(BoundedCommunitySummarizer bounded) {
        this.bounded = bounded;
    }

    public CompletableFuture<SummaryAttempt> summarizeAsync(CollectedIssue issue, Duration budget) {
        var single = CommunitySummarySourceBundle.from(issue);
        // batches()는 댓글이 전부 비었거나 blank인 이슈(제목/본문만으로 이미 limited)에서는
        // 빈 리스트를 돌려줄 수 있다 — 이때는 배치가 아니라 단일 호출 경로로 그대로 떨어진다.
        var batches = single.limited() ? CommunitySummarySourceBundle.batches(issue) : List.<CommunitySummarySourceBundle>of();
        if (batches.isEmpty())
            return bounded.summarizeAsync(single, budget)
                    .thenApply(raw -> new SummaryAttempt(single, raw));

        return CompletableFuture.supplyAsync(() -> mapReduce(batches, budget));
    }

    private SummaryAttempt mapReduce(List<CommunitySummarySourceBundle> batches, Duration budget) {
        var start = Instant.now();
        // 배치는 같은 bounded executor에 동시에 디스패치되므로(BoundedCommunitySummarizer의
        // mapAsync), 예산을 배치 수로 나누지 않고 남은 예산 전체를 넘긴다 — 개별 호출 자체의
        // 상한은 GmsCommunitySummarizer.MAX_CALL_TIMEOUT(15초)이 이미 걸어 준다.
        var futures = batches.stream().map(b -> bounded.mapAsync(b, budget)).toList();

        var parts = new ArrayList<CommunitySummarizer.BatchSummary>();
        for (int i = 0; i < batches.size(); i++) {
            var raw = futures.get(i).join();
            var validated = CommunitySummaryValidator.validate(batches.get(i), raw);
            if (validated.status() != SummaryStatus.FAILED)
                parts.add(
                        new CommunitySummarizer.BatchSummary(
                                validated, batches.get(i).sources().keySet()));
        }

        var union = unionBundle(batches);
        if (parts.isEmpty()) return new SummaryAttempt(union, TopicSummary.failed());

        // Map은 동시에 끝나지만 Reduce는 그 뒤에 순차로 붙는다 — 실제로 걸린 시간을 빼고 남은
        // 예산만 Reduce에 넘긴다(전체 예산을 그대로 다시 주면 Reduce가 필요 이상 오래 기다릴
        // 수 있다).
        var remaining = budget.minus(Duration.between(start, Instant.now()));
        if (remaining.isNegative()) remaining = Duration.ZERO;
        var reduced = bounded.reduce(parts, remaining);
        return new SummaryAttempt(union, reduced);
    }

    /** 검증된 배치들의 source id·댓글을 합쳐, Reduce 결과를 검증할 union bundle을 만든다. */
    private static CommunitySummarySourceBundle unionBundle(List<CommunitySummarySourceBundle> batches) {
        var sources = new LinkedHashMap<TopicSummary.SourceRef, String>();
        var comments = new ArrayList<CollectedComment>();
        for (var b : batches) {
            sources.putAll(b.sources());
            comments.addAll(b.issue().comments());
        }
        comments.sort(Comparator.comparing(CollectedComment::createdAt));
        var base = batches.get(0).issue();
        var issue =
                new CollectedIssue(
                        base.issueNumber(),
                        base.title(),
                        base.state(),
                        base.updatedAt(),
                        base.authorLogin(),
                        base.totalCommentCount(),
                        base.reactionCount(),
                        base.collectionStatus(),
                        List.copyOf(comments),
                        base.limitations(),
                        base.sourceIssueId(),
                        base.createdAt(),
                        base.authorId(),
                        base.body());
        return new CommunitySummarySourceBundle(issue, Map.copyOf(sources), true);
    }

    /** 요약 결과(raw, 미검증) + 그 결과를 검증해야 할 bundle. */
    public record SummaryAttempt(CommunitySummarySourceBundle bundle, TopicSummary raw) {}
}
