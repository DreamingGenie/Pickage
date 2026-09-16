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
        // 2026-09-16 오세진 님 결정 — 논의 전체를 배치로 나눠 재구성하는 대신
        // CommunitySummarySourceBundle.highlights(반응 최다 댓글 + 유지관리자 답글만)로 입력을
        // 항상 작게 유지한다. 이 bundle은 사실상 48,000자를 넘길 일이 없어 배치(Map-Reduce)가
        // 필요 없다 — batches()/mapReduce()는 코드는 남겨두되(추후 재사용 가능) 이 경로에서는
        // 더 이상 호출하지 않는다.
        var single = CommunitySummarySourceBundle.highlights(issue);
        return bounded.summarizeAsync(single, budget).thenApply(raw -> new SummaryAttempt(single, raw));
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
            // validate()가 돌려주는 객체는 summarySupport/flowSupport를 의도적으로 비운다
            // (최종 payload에는 근거가 필요 없어서, CommunitySummaryValidator.java 참고) —
            // 그래서 검증 "통과 여부"는 validated.status()로 판정하되, Reduce에 넘길
            // BatchSummary는 support가 살아있는 raw를 담는다. validate()가 실패로 던지지
            // 않았다는 것 자체가 raw의 summarySupport/flowSupport가 이미 bundle에 대해
            // 유효하다는 걸 보장한다.
            if (validated.status() != SummaryStatus.FAILED)
                parts.add(
                        new CommunitySummarizer.BatchSummary(
                                raw, batches.get(i).sources().keySet()));
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
