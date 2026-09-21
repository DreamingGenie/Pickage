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

    /** 하이라이트 댓글 하나당 clip 상한(2026-09-16 4,000→2,000으로 낮춤 — 댓글 4개를 보여줘도
     * 이슈당 최악 입력을 작게 묶어 두기 위해서다. 하이라이트는 원래 짧은 글이 대부분이라
     * 실질적 손실은 거의 없다). */
    private static final int HIGHLIGHT_COMMENT_CLIP = 2000;

    /** 대표 발화(=GMS 에 보내는 댓글) 상한. 2026-09-20 3→4(S15P21A506-408). {@link CommunitySummaryValidator#MAX_MESSAGES}와 같다. */
    static final int MAX_HIGHLIGHTS = CommunitySummaryValidator.MAX_MESSAGES;

    /**
     * "논의 전체 재구성" 대신 반응이 가장 많은 댓글 + 그에 대한 유지관리자
     * (OWNER/MEMBER/COLLABORATOR) 답글 + (있으면) 그 답글 주변 댓글 1개를 먼저 고르고, 남는 자리(최대
     * {@value #MAX_HIGHLIGHTS}개까지)는 **아직 안 고른 댓글 중 반응이 많은 순**(동률은 최신)으로 채워 GMS에 보낸다
     * (2026-09-16 오세진 님 결정 — Map-Reduce로도 시연에 필요한 시간·비용을 못 맞춰 방향을 바꿨다. 2026-09-20 대표
     * 발화를 최대 4개로 늘리면서 채우기를 더했다). 유지관리자 답글이 없어도 같은 채우기로 4개까지 모은다.
     * 입력이 이슈 본문 + 댓글 최대 4개로 항상 작아 {@link #batches}가 사실상 필요 없다.
     *
     * <p>Bot 댓글은 후보에서 뺀다 — 요약 검증기({@link CommunitySummaryValidator})가 Bot 댓글이 발화로 나오면 요약
     * 전체를 실패시키므로, 고르는 댓글이 늘수록 그 위험이 커지기 때문이다.
     */
    public static CommunitySummarySourceBundle highlights(CollectedIssue source) {
        var refs = new LinkedHashMap<TopicSummary.SourceRef, String>();
        String title = clip(source.title(), 4000), body = clip(source.body(), 4000);
        if (!body.isBlank())
            refs.put(new TopicSummary.SourceRef("ISSUE_BODY", source.sourceIssueId()), body);

        var comments = source.comments();
        var candidates =
                comments.stream()
                        .filter(c -> c.body() != null && !c.body().isBlank())
                        .filter(c -> !c.isBot())
                        .toList();
        var byReaction =
                Comparator.comparingInt(CollectedComment::reactionCount)
                        .thenComparing(CollectedComment::createdAt);
        var topComment = candidates.stream().max(byReaction).orElse(null);

        var selected = new ArrayList<CollectedComment>();
        var chosen = new HashSet<String>();
        boolean limited = false;
        if (topComment != null) {
            limited |= addHighlight(refs, selected, chosen, topComment);

            var maintainerReply =
                    candidates.stream()
                            .filter(c -> !chosen.contains(c.sourceCommentId()))
                            .filter(c -> c.createdAt().isAfter(topComment.createdAt()))
                            .filter(c -> isMaintainer(c.authorAssociation()))
                            .min(Comparator.comparing(CollectedComment::createdAt))
                            .orElse(null);

            if (maintainerReply != null) {
                limited |= addHighlight(refs, selected, chosen, maintainerReply);

                // 유지관리자 답변 주변(그 이후 처음 나오는) 댓글 하나 — 사람들이 그 답변에
                // 어떻게 반응했는지 보여주기 위해 함께 담는다.
                var nearby =
                        candidates.stream()
                                .filter(c -> !chosen.contains(c.sourceCommentId()))
                                .filter(c -> c.createdAt().isAfter(maintainerReply.createdAt()))
                                .min(Comparator.comparing(CollectedComment::createdAt))
                                .orElse(null);
                if (nearby != null) limited |= addHighlight(refs, selected, chosen, nearby);
            }

            // 남는 자리는 반응이 많은 순으로 채운다(유지관리자 답글이 없을 때도 같다).
            var fillers =
                    candidates.stream()
                            .filter(c -> !chosen.contains(c.sourceCommentId()))
                            .sorted(byReaction.reversed())
                            .toList();
            for (var c : fillers) {
                if (selected.size() >= MAX_HIGHLIGHTS) break;
                limited |= addHighlight(refs, selected, chosen, c);
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

    /** 댓글 하나를 {@link #HIGHLIGHT_COMMENT_CLIP}로 잘라 refs·selected에 담는다. 잘렸으면 true. */
    private static boolean addHighlight(
            Map<TopicSummary.SourceRef, String> refs,
            List<CollectedComment> selected,
            Set<String> chosen,
            CollectedComment comment) {
        String text = clip(comment.body(), HIGHLIGHT_COMMENT_CLIP);
        boolean clipped = !text.equals(comment.body());
        refs.put(new TopicSummary.SourceRef("COMMENT", comment.sourceCommentId()), text);
        selected.add(withBody(comment, text));
        chosen.add(comment.sourceCommentId());
        return clipped;
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
