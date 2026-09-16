package com.ssafy.pickage.domain.community;

import com.ssafy.pickage.domain.community.collection.*;

import java.util.*;

/**
 * 제목/본문 우선, 나머지는 댓글 반응(reaction) 수 내림차순(동률은 최신 우선)으로 48,000자 예산에 담되, 이슈
 * 작성자의 최초 댓글은 반응 수와 무관하게 우선 포함한다(PRD §4.1 "맥락상 필수인 댓글" 완화 규칙 — 구현계획
 * S15P21A506-373 2단계). 모델에는 항상 시각순으로 전달한다.
 */
public record CommunitySummarySourceBundle(
        CollectedIssue issue, Map<TopicSummary.SourceRef, String> sources, boolean limited) {
    public static CommunitySummarySourceBundle from(CollectedIssue source) {
        var refs = new LinkedHashMap<TopicSummary.SourceRef, String>();
        String title = clip(source.title(), 4000), body = clip(source.body(), 4000);
        int remaining =
                48000
                        - title.codePointCount(0, title.length())
                        - body.codePointCount(0, body.length());
        boolean limited =
                !title.equals(source.title())
                        || !body.equals(Objects.requireNonNullElse(source.body(), ""));
        if (!body.isBlank())
            refs.put(new TopicSummary.SourceRef("ISSUE_BODY", source.sourceIssueId()), body);
        var selected = new ArrayList<CollectedComment>();
        var input = source.comments();
        for (var c : priorityOrder(source, input)) {
            String text = clip(c.body(), Math.min(4000, remaining));
            if (!text.equals(Objects.requireNonNullElse(c.body(), ""))) limited = true;
            if (text.isBlank()) continue;
            remaining -= text.codePointCount(0, text.length());
            refs.put(new TopicSummary.SourceRef("COMMENT", c.sourceCommentId()), text);
            selected.add(
                    new CollectedComment(
                            c.sourceCommentId(),
                            c.authorLogin(),
                            c.authorAssociation(),
                            c.isBot(),
                            c.createdAt(),
                            text,
                            c.authorId(),
                            c.reactionCount()));
        }
        selected.sort(Comparator.comparing(CollectedComment::createdAt));
        var issue =
                new CollectedIssue(
                        source.issueNumber(),
                        title,
                        source.state(),
                        source.updatedAt(),
                        source.authorLogin(),
                        source.totalCommentCount(),
                        source.reactionCount(),
                        source.collectionStatus(),
                        List.copyOf(selected),
                        source.limitations(),
                        source.sourceIssueId(),
                        source.createdAt(),
                        source.authorId(),
                        body);
        return new CommunitySummarySourceBundle(issue, Map.copyOf(refs), limited);
    }

    /**
     * 이슈 작성자의 최초 댓글(있으면)을 0순위로, 나머지는 반응 수 내림차순(동률은 최신 우선)으로 정렬한 순서를
     * 만든다. 작성자의 나머지 댓글은 이 특례를 받지 않는다 — 전부 우선하면 반응 수 높은 다른 사용자 댓글을
     * 밀어낼 수 있다.
     */
    private static List<CollectedComment> priorityOrder(
            CollectedIssue source, List<CollectedComment> input) {
        String firstAuthorCommentId =
                input.stream()
                        .filter(
                                c ->
                                        c.authorId() != null
                                                && c.authorId().equals(source.authorId()))
                        .min(Comparator.comparing(CollectedComment::createdAt))
                        .map(CollectedComment::sourceCommentId)
                        .orElse(null);
        var ordered = new ArrayList<>(input);
        ordered.sort(
                Comparator.comparingInt(
                                (CollectedComment c) ->
                                        c.sourceCommentId().equals(firstAuthorCommentId) ? 0 : 1)
                        .thenComparing(
                                Comparator.comparingInt(CollectedComment::reactionCount)
                                        .reversed())
                        .thenComparing(Comparator.comparing(CollectedComment::createdAt).reversed()));
        return ordered;
    }

    static String clip(String value, int max) {
        value = Objects.requireNonNullElse(value, "");
        int count = value.codePointCount(0, value.length());
        return count <= max ? value : value.substring(0, value.offsetByCodePoints(0, max));
    }
}
