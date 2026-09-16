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
     * "논의 전체 재구성" 대신 반응이 가장 많은 댓글 1개 + 그 댓글 이후 처음 나오는 유지관리자
     * (OWNER/MEMBER/COLLABORATOR) 답글 1개(있으면)만 골라 GMS에 보낸다(2026-09-16 오세진 님
     * 결정 — Map-Reduce로도 시연에 필요한 시간·비용을 못 맞춰 방향을 바꿨다). 입력이 이슈
     * 본문 + 댓글 최대 2개로 항상 작아 {@link #batches}가 사실상 필요 없어진다 — 그래도
     * 단일 댓글이 4,000자를 넘는 극단적인 경우에 대비해 clip은 유지한다.
     */
    public static CommunitySummarySourceBundle highlights(CollectedIssue source) {
        var refs = new LinkedHashMap<TopicSummary.SourceRef, String>();
        String title = clip(source.title(), 4000), body = clip(source.body(), 4000);
        if (!body.isBlank())
            refs.put(new TopicSummary.SourceRef("ISSUE_BODY", source.sourceIssueId()), body);

        var comments = source.comments();
        var topComment =
                comments.stream()
                        .filter(c -> c.body() != null && !c.body().isBlank())
                        .max(
                                Comparator.comparingInt(CollectedComment::reactionCount)
                                        .thenComparing(CollectedComment::createdAt))
                        .orElse(null);

        var selected = new ArrayList<CollectedComment>();
        boolean limited = false;
        if (topComment != null) {
            String text = clip(topComment.body(), 4000);
            limited |= !text.equals(topComment.body());
            refs.put(new TopicSummary.SourceRef("COMMENT", topComment.sourceCommentId()), text);
            selected.add(withBody(topComment, text));

            var maintainerReply =
                    comments.stream()
                            .filter(c -> !c.sourceCommentId().equals(topComment.sourceCommentId()))
                            .filter(c -> c.body() != null && !c.body().isBlank())
                            .filter(c -> c.createdAt().isAfter(topComment.createdAt()))
                            .filter(c -> isMaintainer(c.authorAssociation()))
                            .min(Comparator.comparing(CollectedComment::createdAt))
                            .orElse(null);
            if (maintainerReply != null) {
                String replyText = clip(maintainerReply.body(), 4000);
                limited |= !replyText.equals(maintainerReply.body());
                refs.put(
                        new TopicSummary.SourceRef("COMMENT", maintainerReply.sourceCommentId()),
                        replyText);
                selected.add(withBody(maintainerReply, replyText));
            }
        }
        limited |= comments.size() > selected.size();
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

    private static boolean isMaintainer(String authorAssociation) {
        return authorAssociation != null
                && Set.of("OWNER", "MEMBER", "COLLABORATOR").contains(authorAssociation);
    }

    private static CollectedComment withBody(CollectedComment c, String body) {
        return new CollectedComment(
                c.sourceCommentId(),
                c.authorLogin(),
                c.authorAssociation(),
                c.isBot(),
                c.createdAt(),
                body,
                c.authorId(),
                c.reactionCount());
    }

    /**
     * 이슈 하나를 배치 여러 개로 나눈다(S15P21A506-373 4단계, Map-Reduce Map 입력). 단일
     * bundle({@link #from})이 잘리지 않으면(=제한 없음) 빈 리스트를 반환한다 — 호출자는 빈
     * 리스트를 "배치 불필요, 기존 단일 호출 경로 사용"으로 해석한다. 우선순위 순서는 {@link
     * #from}과 동일하게 {@link #priorityOrder}를 재사용한다. 배치 수가 {@link
     * CommunityProperties#MAX_SUMMARY_BATCHES}를 넘으면 그 뒤 댓글은 버리고 마지막 배치를
     * {@code limited=true}로 표시한다(48,000자 초과 시 버리는 것과 같은 종류의 저하).
     */
    public static List<CommunitySummarySourceBundle> batches(CollectedIssue source) {
        if (!from(source).limited()) return List.of();

        String title = clip(source.title(), 4000);
        String body = clip(source.body(), 4000);
        int headerLen =
                title.codePointCount(0, title.length())
                        + (body.isBlank() ? 0 : body.codePointCount(0, body.length()));

        var result = new ArrayList<CommunitySummarySourceBundle>();
        var currentComments = new ArrayList<CollectedComment>();
        var currentRefs = new LinkedHashMap<TopicSummary.SourceRef, String>();
        if (!body.isBlank())
            currentRefs.put(new TopicSummary.SourceRef("ISSUE_BODY", source.sourceIssueId()), body);
        int currentLen = headerLen;
        boolean currentLimited = false;
        boolean droppedByBatchCap = false;

        for (var c : priorityOrder(source, source.comments())) {
            if (result.size() >= CommunityProperties.MAX_SUMMARY_BATCHES) {
                droppedByBatchCap = true;
                break;
            }
            String text = clip(c.body(), Math.min(4000, CommunityProperties.SUMMARY_BATCH_CHAR_BUDGET));
            if (text.isBlank()) continue;
            boolean commentLimited = !text.equals(Objects.requireNonNullElse(c.body(), ""));
            int textLen = text.codePointCount(0, text.length());
            if (!currentComments.isEmpty()
                    && currentLen + textLen > CommunityProperties.SUMMARY_BATCH_CHAR_BUDGET) {
                result.add(closeBatch(source, title, body, currentComments, currentRefs, currentLimited));
                currentComments = new ArrayList<>();
                currentRefs = new LinkedHashMap<>();
                if (!body.isBlank())
                    currentRefs.put(
                            new TopicSummary.SourceRef("ISSUE_BODY", source.sourceIssueId()), body);
                currentLen = headerLen;
                currentLimited = false;
            }
            currentComments.add(
                    new CollectedComment(
                            c.sourceCommentId(),
                            c.authorLogin(),
                            c.authorAssociation(),
                            c.isBot(),
                            c.createdAt(),
                            text,
                            c.authorId(),
                            c.reactionCount()));
            currentRefs.put(new TopicSummary.SourceRef("COMMENT", c.sourceCommentId()), text);
            currentLen += textLen;
            currentLimited = currentLimited || commentLimited;
        }
        if (!currentComments.isEmpty() && result.size() < CommunityProperties.MAX_SUMMARY_BATCHES) {
            result.add(closeBatch(source, title, body, currentComments, currentRefs, currentLimited));
        }
        if (droppedByBatchCap && !result.isEmpty()) {
            var last = result.remove(result.size() - 1);
            result.add(new CommunitySummarySourceBundle(last.issue(), last.sources(), true));
        }
        return List.copyOf(result);
    }

    private static CommunitySummarySourceBundle closeBatch(
            CollectedIssue source,
            String title,
            String body,
            List<CollectedComment> comments,
            Map<TopicSummary.SourceRef, String> refs,
            boolean limited) {
        var sorted = new ArrayList<>(comments);
        sorted.sort(Comparator.comparing(CollectedComment::createdAt));
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
                        List.copyOf(sorted),
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
