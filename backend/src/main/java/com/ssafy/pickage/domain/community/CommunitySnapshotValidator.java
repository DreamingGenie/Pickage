package com.ssafy.pickage.domain.community;

import com.fasterxml.jackson.databind.JsonNode;
import com.ssafy.pickage.domain.community.payload.*;

import java.math.BigInteger;
import java.time.Instant;
import java.util.*;

/** 지원되는 snapshot만 엄격하게 복원한다. 예외에는 payload 원문을 담지 않는다. */
public final class CommunitySnapshotValidator {
    private CommunitySnapshotValidator() {}

    private static void require(boolean ok) {
        if (!ok)
            throw new CommunitySnapshotPayloadException(
                    "Invalid community snapshot structure", null);
    }

    public static boolean decimalId(String id) {
        return id != null && id.matches("[1-9][0-9]{0,99}");
    }

    public static boolean plain(String text, int max) {
        return text != null
                && !text.isBlank()
                && text.codePointCount(0, text.length()) <= max
                && !text.matches("(?s).*([<>]|(?i:https?://|www\\.)|\\[[^]]*]\\([^)]*\\)).*");
    }

    public static void validate(CommunitySnapshotRow row) {
        require(
                row != null
                        && row.packageId() > 0
                        && row.snapshotId() != null
                        && row.collectedAt() != null
                        && row.dataStatus() != null);
        require(row.payloadVersion() == CommunityPolicy.PAYLOAD_VERSION);
        validate(row.result());
        boolean terminal =
                Set.of(
                                DataStatus.UNVERIFIED_REPOSITORY,
                                DataStatus.UNSUPPORTED_HOST,
                                DataStatus.AMBIGUOUS_SCOPE)
                        .contains(row.dataStatus());
        require(
                !terminal
                        || (row.result().repository() == null && row.result().topics().isEmpty()));
        require(terminal || row.result().repository() != null);
        require(
                row.dataStatus() != DataStatus.NO_DISCUSSION_DATA
                        || row.result().topics().isEmpty());
    }

    public static void validate(CommunityResultPayload p) {
        require(
                p != null
                        && CommunityPolicy.VERSION.equals(p.policyVersion())
                        && (p.lookbackDays() == 180 || p.lookbackDays() == 365));
        require(
                p.topics() != null
                        && p.topics().size() <= 2
                        && p.limitations() != null
                        && p.limitations().size() <= 32);
        if (p.repository() != null) {
            var r = p.repository();
            require(
                    r.owner() != null
                            && r.owner().matches("[A-Za-z0-9_.-]+")
                            && r.name() != null
                            && r.name().matches("[A-Za-z0-9_.-]+"));
            require(
                    (r.owner() + "/" + r.name()).equals(r.fullName())
                            && Set.of("PACKAGE_SCOPED", "REPOSITORY_WIDE").contains(r.scope()));
        }
        Set<Integer> numbers = new HashSet<>();
        Set<String> sources = new HashSet<>();
        for (var t : p.topics()) {
            require(
                    t != null
                            && decimalId(t.sourceIssueId())
                            && sources.add(t.sourceIssueId())
                            && t.issueNumber() > 0
                            && numbers.add(t.issueNumber()));
            require(
                    t.state() != null
                            && Set.of("OPEN", "CLOSED").contains(t.state())
                            && t.createdAt() != null
                            && t.updatedAt() != null);
            require(
                    !t.updatedAt().isBefore(t.createdAt())
                            && t.titleOriginal() != null
                            && !t.titleOriginal().isBlank()
                            && t.titleOriginal().codePointCount(0, t.titleOriginal().length())
                                    <= 200);
            require(
                    t.commentsCount() >= 0
                            && t.commentsCount() <= Integer.MAX_VALUE
                            && t.reactionsCount() >= 0
                            && t.reactionsCount() <= Integer.MAX_VALUE);
            require(
                    t.collectionStatus() != null
                            && Set.of("COMPLETE", "TRUNCATED", "FAILED")
                                    .contains(t.collectionStatus()));
            require(
                    t.summaryStatus() != null
                            && Set.of("READY", "PARTIAL", "FAILED").contains(t.summaryStatus()));
            require(
                    t.flow() != null
                            && t.messages() != null
                            && t.flow().size() <= 4
                            && t.messages().size() <= CommunitySummaryValidator.MAX_MESSAGES
                            && t.summaryMarks() != null
                            && t.summaryMarks().size()
                                    <= CommunitySummaryValidator.MAX_KEY_SENTENCES
                                            + CommunitySummaryValidator.MAX_KEY_TERMS);
            if ("FAILED".equals(t.summaryStatus()))
                require(
                        t.titleKo() == null
                                && t.summaryKo() == null
                                && t.flow().isEmpty()
                                && t.messages().isEmpty()
                                && t.summaryMarks().isEmpty());
            else {
                require(
                        plain(t.titleKo(), 200)
                                && plain(t.summaryKo(), 500)
                                && !t.flow().isEmpty());
                for (var f : t.flow()) require(f != null && plain(f.text(), 200));
                // 강조 구간은 요약문 범위 안의 [start, end) 여야 한다. 종류는 둘뿐이다.
                for (var k : t.summaryMarks())
                    require(
                            k != null
                                    && k.start() >= 0
                                    && k.start() < k.end()
                                    && k.end() <= t.summaryKo().length()
                                    && Set.of(
                                                    SummaryMarkPayload.KEY_TERM,
                                                    SummaryMarkPayload.KEY_SENTENCE)
                                            .contains(k.kind()));
            }
            Set<String> ids = new HashSet<>();
            Instant previous = null;
            BigInteger previousId = null;
            for (var m : t.messages()) {
                require(
                        m != null
                                && decimalId(m.sourceCommentId())
                                && ids.add(m.sourceCommentId())
                                && m.createdAt() != null
                                && plain(m.text(), 300));
                require(
                        m.kind() != null
                                && Set.of("DISCUSSION", "USER_SOLUTION").contains(m.kind()));
                require(m.authorLogin() == null || m.authorLogin().matches("[A-Za-z0-9-]{1,100}"));
                require(
                        m.authorAssociation() == null
                                || Set.of(
                                                "OWNER",
                                                "MEMBER",
                                                "COLLABORATOR",
                                                "CONTRIBUTOR",
                                                "FIRST_TIMER",
                                                "FIRST_TIME_CONTRIBUTOR",
                                                "MANNEQUIN",
                                                "NONE")
                                        .contains(m.authorAssociation()));
                require(
                        m.authorLogin() != null
                                || (m.authorAssociation() == null && !m.isIssueAuthor()));
                BigInteger id = new BigInteger(m.sourceCommentId());
                require(
                        previous == null
                                || m.createdAt().isAfter(previous)
                                || (m.createdAt().equals(previous)
                                        && id.compareTo(previousId) > 0));
                previous = m.createdAt();
                previousId = id;
            }
        }
        for (var l : p.limitations())
            require(
                    CommunityPolicy.validLimitation(l)
                            && (l.issueNumber() == null || numbers.contains(l.issueNumber())));
        require(
                (CommunityPolicy.summaryStatus(p.topics())
                                == com.ssafy.pickage.domain.community.dto.SummaryStatus.FAILED)
                        == (p.summaryRetryAt() != null));
    }

    private static void keys(JsonNode node, String names) {
        require(node != null && node.isObject());
        Set<String> expected = new HashSet<>(Arrays.asList(names.split(" ")));
        Set<String> actual = new HashSet<>();
        node.fieldNames().forEachRemaining(actual::add);
        require(expected.equals(actual));
    }

    /** Primitive/null/required keys must not silently acquire Jackson defaults. */
    public static void validateJson(JsonNode p) {
        keys(p, "repository policy_version lookback_days summary_retry_at topics limitations");
        texts(p, "policy_version", false);
        texts(p, "summary_retry_at", true);
        require(
                p.path("policy_version").isTextual()
                        && p.path("lookback_days").isInt()
                        && p.path("topics").isArray()
                        && p.path("limitations").isArray());
        if (!p.path("repository").isNull()) {
            keys(p.path("repository"), "owner name full_name scope archived");
            texts(p.path("repository"), "owner name full_name scope", false);
            require(p.path("repository").path("archived").isBoolean());
        }
        for (JsonNode t : p.path("topics")) {
            // `summary_marks` 는 payload_version 을 올리지 않고 더한 선택 키다 — 이전 스냅샷에는 없어도 읽는다.
            boolean hasMarks = t.has("summary_marks");
            keys(
                    t,
                    "source_issue_id issue_number state updated_at created_at title_original"
                            + " title_ko comments_count reactions_count collection_status"
                            + " summary_status summary_ko flow messages"
                            + (hasMarks ? " summary_marks" : ""));
            if (hasMarks) {
                require(t.path("summary_marks").isArray());
                for (JsonNode k : t.path("summary_marks")) {
                    keys(k, "start end kind");
                    texts(k, "kind", false);
                    require(k.path("start").isInt() && k.path("end").isInt());
                }
            }
            texts(
                    t,
                    "source_issue_id state updated_at created_at title_original collection_status"
                        + " summary_status",
                    false);
            texts(t, "title_ko summary_ko", true);
            require(
                    t.path("issue_number").isInt()
                            && t.path("comments_count").isIntegralNumber()
                            && t.path("reactions_count").isIntegralNumber()
                            && t.path("flow").isArray()
                            && t.path("messages").isArray());
            for (JsonNode f : t.path("flow")) {
                keys(f, "text");
                texts(f, "text", false);
            }
            for (JsonNode m : t.path("messages")) {
                keys(
                        m,
                        "source_comment_id author_login author_association is_issue_author kind"
                                + " created_at text");
                require(m.path("is_issue_author").isBoolean());
                texts(m, "source_comment_id kind created_at text", false);
                texts(m, "author_login author_association", true);
            }
        }
        for (JsonNode l : p.path("limitations")) {
            keys(l, "code message issue_number");
            texts(l, "code message", false);
            require(l.path("issue_number").isNull() || l.path("issue_number").isInt());
        }
    }

    private static void texts(JsonNode node, String fields, boolean nullable) {
        for (String field : fields.split(" "))
            require(node.path(field).isTextual() || (nullable && node.path(field).isNull()));
    }
}
