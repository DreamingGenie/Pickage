package com.ssafy.pickage.domain.community;

import com.ssafy.pickage.domain.community.dto.SummaryStatus;
import com.ssafy.pickage.domain.community.payload.*;

import java.math.BigInteger;
import java.util.*;

/** 모델이 주장한 작성자/역할/시각은 사용하지 않고 전달했던 source에서만 복원한다. */
public final class CommunitySummaryValidator {
    private CommunitySummaryValidator() {}

    public static TopicSummary validate(CommunitySummarySourceBundle bundle, TopicSummary summary) {
        try {
            if (summary == null || summary.status() == SummaryStatus.FAILED)
                return TopicSummary.failed();
            require(
                    summary.status() == SummaryStatus.READY
                            || summary.status() == SummaryStatus.PARTIAL);
            require(
                    CommunitySnapshotValidator.plain(summary.titleKo(), 200)
                            && CommunitySnapshotValidator.plain(summary.summaryKo(), 500));
            support(bundle, summary.summarySupport());
            require(
                    summary.discussionFlow() != null
                            && !summary.discussionFlow().isEmpty()
                            && summary.discussionFlow().size() <= 4);
            require(
                    summary.flowSupport() != null
                            && summary.flowSupport().size() == summary.discussionFlow().size());
            for (int i = 0; i < summary.discussionFlow().size(); i++) {
                require(
                        CommunitySnapshotValidator.plain(
                                summary.discussionFlow().get(i).text(), 200));
                support(bundle, summary.flowSupport().get(i));
            }
            require(summary.messages() != null && summary.messages().size() <= 3);
            var messages = new ArrayList<MessagePayload>();
            var seen = new HashSet<String>();
            for (var m : summary.messages()) {
                require(
                        m != null
                                && seen.add(m.sourceCommentId())
                                && CommunitySnapshotValidator.plain(m.text(), 300));
                require(
                        m.kind() != null
                                && Set.of("DISCUSSION", "USER_SOLUTION").contains(m.kind()));
                require(
                        bundle.sources()
                                .containsKey(
                                        new TopicSummary.SourceRef(
                                                "COMMENT", m.sourceCommentId())));
                var c =
                        bundle.issue().comments().stream()
                                .filter(x -> x.sourceCommentId().equals(m.sourceCommentId()))
                                .findFirst()
                                .orElseThrow();
                require(!c.isBot());
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
                                m.text()));
            }
            messages.sort(
                    Comparator.comparing(MessagePayload::createdAt)
                            .thenComparing(m -> new BigInteger(m.sourceCommentId())));
            return new TopicSummary(
                    summary.titleKo(),
                    summary.summaryKo(),
                    List.copyOf(summary.discussionFlow()),
                    List.copyOf(messages),
                    summary.status(),
                    List.of(),
                    List.of());
        } catch (RuntimeException e) {
            return TopicSummary.failed();
        }
    }

    private static void support(
            CommunitySummarySourceBundle bundle, List<TopicSummary.SourceRef> refs) {
        require(
                refs != null
                        && !refs.isEmpty()
                        && refs.size() <= 101
                        && new HashSet<>(refs).size() == refs.size());
        for (var ref : refs) require(bundle.sources().containsKey(ref));
    }

    private static void require(boolean value) {
        if (!value) throw new IllegalArgumentException("Invalid summary evidence");
    }
}
