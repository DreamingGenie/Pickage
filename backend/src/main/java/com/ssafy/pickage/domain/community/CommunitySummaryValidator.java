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

    /** 대표 발화 상한(2026-09-20 3→4, S15P21A506-408). 하이라이트 댓글 선택·GMS 스키마·스냅샷 검증기와 같은 값이다. */
    public static final int MAX_MESSAGES = 4;

    /** 강조 상한. 강조가 많아지면 강조가 아니게 되므로 개수와 길이를 모두 묶는다. */
    static final int MAX_KEY_SENTENCES = 2;

    static final int MAX_KEY_TERMS = 6;
    static final int MAX_KEY_SENTENCE_LENGTH = 160;
    static final int MAX_KEY_TERM_LENGTH = 30;
    /** 핵심 문장 하나가 요약문의 이 비율보다 길면 "전부 강조"와 다르지 않아 버린다. */
    private static final double MAX_KEY_SENTENCE_SHARE = 0.6;

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
            require(summary.messages() != null && summary.messages().size() <= MAX_MESSAGES, "messages size");
            var messages = new ArrayList<MessagePayload>();
            var seen = new HashSet<String>();
            for (var m : summary.messages()) {
                require(m != null, "message null");
                String messageText = stripLinks(m.text());
                require(seen.add(m.sourceCommentId()), "duplicate message sourceCommentId");
                require(
                        CommunitySnapshotValidator.plain(messageText, 300),
                        "message text not plain/too long ("
                                + describe(messageText)
                                + ")");
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
                    List.copyOf(messages),
                    summary.status(),
                    List.of(),
                    List.of(),
                    List.of(),
                    marks(summaryKo, summary.keySentences(), summary.keyTerms()));
        } catch (RuntimeException e) {
            log.warn(
                    "요약 검증 실패: {} ({}) — messages={}, summarySupport={}",
                    e.getClass().getSimpleName(),
                    e.getMessage(),
                    summary == null ? null : summary.messages().size(),
                    summary == null ? null : summary.summarySupport().size());
            return TopicSummary.failed();
        }
    }

    /**
     * 모델이 준 핵심 문장·핵심어를 **최종 요약문 안에서 찾아** 강조 구간으로 바꾼다.
     *
     * <p>강조는 읽기 보조라 어긋난 것은 **버릴 뿐 요약을 실패시키지 않는다**(모델이 요약문에 없는 말을 "핵심어"로 줘도 요약은
     * 멀쩡하다). 요약문에 글자 그대로 있는 것만 인정하고, 위치는 서버가 계산한다 — 모델이 준 오프셋은 믿지 않는다. 링크
     * 제거({@link #stripLinks}) 뒤의 문장 기준이라 반드시 그 뒤에 부른다.
     *
     * <p>규칙: 핵심 문장 ≤ {@value #MAX_KEY_SENTENCES}개·{@value #MAX_KEY_SENTENCE_LENGTH}자(요약문의 60% 이하), 핵심어 ≤
     * {@value #MAX_KEY_TERMS}개·{@value #MAX_KEY_TERM_LENGTH}자. 같은 종류끼리는 겹치지 않는다. 핵심어는 핵심 문장 안에
     * 통째로 들어가는 것만 허용하고(굵게+형광펜), 문장 경계에 걸치는 것은 버린다.
     */
    static List<SummaryMarkPayload> marks(
            String summaryKo, List<String> keySentences, List<String> keyTerms) {
        if (summaryKo == null || summaryKo.isBlank()) return List.of();
        var marks = new ArrayList<SummaryMarkPayload>();
        var sentences = new ArrayList<SummaryMarkPayload>();
        for (String raw : orEmpty(keySentences)) {
            if (sentences.size() >= MAX_KEY_SENTENCES) break;
            var mark = locate(summaryKo, raw, MAX_KEY_SENTENCE_LENGTH, SummaryMarkPayload.KEY_SENTENCE);
            if (mark == null) continue;
            if ((mark.end() - mark.start()) > summaryKo.length() * MAX_KEY_SENTENCE_SHARE) continue;
            if (sentences.stream().anyMatch(o -> overlaps(o, mark))) continue;
            sentences.add(mark);
        }
        var terms = new ArrayList<SummaryMarkPayload>();
        for (String raw : orEmpty(keyTerms)) {
            if (terms.size() >= MAX_KEY_TERMS) break;
            var mark = locate(summaryKo, raw, MAX_KEY_TERM_LENGTH, SummaryMarkPayload.KEY_TERM);
            if (mark == null) continue;
            if (terms.stream().anyMatch(o -> overlaps(o, mark))) continue;
            // 문장 경계에 걸치거나(일부만 겹침) 문장과 똑같은 범위이면 버린다.
            boolean straddles =
                    sentences.stream()
                            .anyMatch(
                                    s ->
                                            overlaps(s, mark)
                                                    && !(s.start() <= mark.start()
                                                            && mark.end() <= s.end()
                                                            && (s.start() != mark.start()
                                                                    || s.end() != mark.end())));
            if (straddles) continue;
            terms.add(mark);
        }
        marks.addAll(sentences);
        marks.addAll(terms);
        marks.sort(
                Comparator.comparingInt(SummaryMarkPayload::start)
                        .thenComparing(SummaryMarkPayload::end)
                        .thenComparing(SummaryMarkPayload::kind));
        return List.copyOf(marks);
    }

    private static List<String> orEmpty(List<String> values) {
        return values == null ? List.of() : values;
    }

    /** {@code text}가 요약문에 글자 그대로 처음 나오는 구간. 없거나 길이 제한을 넘으면 null. */
    private static SummaryMarkPayload locate(String summaryKo, String text, int maxLength, String kind) {
        if (text == null) return null;
        String value = text.strip();
        if (value.isEmpty() || value.length() > maxLength) return null;
        int start = summaryKo.indexOf(value);
        if (start < 0) return null;
        return new SummaryMarkPayload(start, start + value.length(), kind);
    }

    private static boolean overlaps(SummaryMarkPayload a, SummaryMarkPayload b) {
        return a.start() < b.end() && b.start() < a.end();
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

    /** 검증 실패 원인을 좁힐 수 있게 본문 대신 모양만 적는다(외부 글이라 로그에 내용을 남기지 않는다). */
    private static String describe(String text) {
        if (text == null) return "null";
        return "length="
                + text.codePointCount(0, text.length())
                + ", angleBracket="
                + (text.indexOf('<') >= 0 || text.indexOf('>') >= 0)
                + ", blank="
                + text.isBlank();
    }

    private static void require(boolean value, String reason) {
        if (!value) throw new IllegalArgumentException(reason);
    }
}
