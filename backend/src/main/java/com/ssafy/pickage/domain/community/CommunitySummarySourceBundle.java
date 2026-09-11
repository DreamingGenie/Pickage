package com.ssafy.pickage.domain.community;

import com.ssafy.pickage.domain.community.collection.*;

import java.util.*;

/** 제목/본문 우선, 최신 댓글 우선으로 48,000자 예산에 담은 뒤 시각순으로 전달한다. */
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
        for (int i = input.size() - 1; i >= 0; i--) {
            var c = input.get(i);
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
                            c.authorId()));
        }
        Collections.reverse(selected);
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

    static String clip(String value, int max) {
        value = Objects.requireNonNullElse(value, "");
        int count = value.codePointCount(0, value.length());
        return count <= max ? value : value.substring(0, value.offsetByCodePoints(0, max));
    }
}
