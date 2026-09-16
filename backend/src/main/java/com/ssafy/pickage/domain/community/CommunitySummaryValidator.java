package com.ssafy.pickage.domain.community;

import com.ssafy.pickage.domain.community.dto.SummaryStatus;
import com.ssafy.pickage.domain.community.payload.*;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.math.BigInteger;
import java.util.*;

/** 모델이 주장한 작성자/역할/시각은 사용하지 않고 전달했던 source에서만 복원한다. */
public final class CommunitySummaryValidator {
    private static final Logger log = LoggerFactory.getLogger(CommunitySummaryValidator.class);

    private CommunitySummaryValidator() {}

    public static TopicSummary validate(CommunitySummarySourceBundle bundle, TopicSummary summary) {
        try {
            if (summary == null || summary.status() == SummaryStatus.FAILED)
                return TopicSummary.failed();
            require(
                    summary.status() == SummaryStatus.READY
                            || summary.status() == SummaryStatus.PARTIAL,
                    "status");
            String titleKo = stripLinks(summary.titleKo());
            String summaryKo = stripLinks(summary.summaryKo());
            require(CommunitySnapshotValidator.plain(titleKo, 200), "titleKo not plain/too long");
            require(CommunitySnapshotValidator.plain(summaryKo, 500), "summaryKo not plain/too long");
            support(bundle, summary.summarySupport(), "summarySupport");
            require(
                    summary.discussionFlow() != null
                            && !summary.discussionFlow().isEmpty()
                            && summary.discussionFlow().size() <= 4,
                    "discussionFlow size");
            require(
                    summary.flowSupport() != null
                            && summary.flowSupport().size() == summary.discussionFlow().size(),
                    "flowSupport size mismatch");
            var flow = new ArrayList<DiscussionStepPayload>();
            for (int i = 0; i < summary.discussionFlow().size(); i++) {
                String stepText = stripLinks(summary.discussionFlow().get(i).text());
                require(CommunitySnapshotValidator.plain(stepText, 200), "flow[" + i + "] not plain/too long");
                support(bundle, summary.flowSupport().get(i), "flowSupport[" + i + "]");
                flow.add(new DiscussionStepPayload(stepText));
            }
            require(summary.messages() != null && summary.messages().size() <= 3, "messages size");
            var messages = new ArrayList<MessagePayload>();
            var seen = new HashSet<String>();
            for (var m : summary.messages()) {
                require(m != null, "message null");
                String messageText = stripLinks(m.text());
                require(seen.add(m.sourceCommentId()), "duplicate message sourceCommentId");
                require(
                        CommunitySnapshotValidator.plain(messageText, 300),
                        "message text not plain/too long");
                require(
                        m.kind() != null && Set.of("DISCUSSION", "USER_SOLUTION").contains(m.kind()),
                        "message kind invalid");
                require(
                        bundle.sources()
                                .containsKey(new TopicSummary.SourceRef("COMMENT", m.sourceCommentId())),
                        "message sourceCommentId not in bundle");
                var c =
                        bundle.issue().comments().stream()
                                .filter(x -> x.sourceCommentId().equals(m.sourceCommentId()))
                                .findFirst()
                                .orElseThrow();
                require(!c.isBot(), "message comment author is bot");
                boolean author =
                        c.authorId() != null
                                && bundle.issue().authorId() != null
                                && c.authorId().equals(bundle.issue().authorId());
                messages.add(
                        new MessagePayload(
                                c.sourceCommentId(),
                                c.authorLogin(),
                                c.authorLogin() == null ? null : c.authorAssociation(),
                                c.authorLogin() != null && author,
                                m.kind(),
                                c.createdAt(),
                                messageText));
            }
            messages.sort(
                    Comparator.comparing(MessagePayload::createdAt)
                            .thenComparing(m -> new BigInteger(m.sourceCommentId())));
            return new TopicSummary(
                    titleKo,
                    summaryKo,
                    List.copyOf(flow),
                    List.copyOf(messages),
                    summary.status(),
                    List.of(),
                    List.of());
        } catch (RuntimeException e) {
            log.warn(
                    "요약 검증 실패: {} ({}) — flow={}, flowSupport={}, messages={}, summarySupport={}",
                    e.getClass().getSimpleName(),
                    e.getMessage(),
                    summary == null ? null : summary.discussionFlow().size(),
                    summary == null ? null : summary.flowSupport().size(),
                    summary == null ? null : summary.messages().size(),
                    summary == null ? null : summary.summarySupport().size());
            return TopicSummary.failed();
        }
    }

    /**
     * URL·마크다운 링크만 "(링크 생략)"으로 지우고 나머지 텍스트는 그대로 남긴다(2026-09-16
     * 오세진 님 결정 — 실측에서 axios/prisma/vitest처럼 보안 권고문·문서 링크가 많은 이슈가
     * 이 이유만으로 요약 전체가 FAILED로 떨어지는 사례가 잦았다). {@code <}/{@code >}(HTML
     * 태그, XSS 방어)는 여기서 건드리지 않는다 — {@link CommunitySnapshotValidator#plain}이
     * 이 메서드가 돌려준 텍스트에 대해서도 그대로 검사해 걸러낸다.
     */
    private static String stripLinks(String text) {
        if (text == null) return null;
        return text.replaceAll("\\[[^]]*]\\([^)]*\\)", "(링크 생략)")
                .replaceAll("(?i)https?://\\S+", "(링크 생략)")
                .replaceAll("(?i)\\bwww\\.\\S+", "(링크 생략)");
    }

    private static void support(
            CommunitySummarySourceBundle bundle, List<TopicSummary.SourceRef> refs, String label) {
        require(
                refs != null && !refs.isEmpty() && refs.size() <= 101,
                label + " empty/too large");
        require(new HashSet<>(refs).size() == refs.size(), label + " has duplicates");
        for (var ref : refs)
            require(bundle.sources().containsKey(ref), label + " ref not in bundle: " + ref);
    }

    private static void require(boolean value, String reason) {
        if (!value) throw new IllegalArgumentException(reason);
    }
}
