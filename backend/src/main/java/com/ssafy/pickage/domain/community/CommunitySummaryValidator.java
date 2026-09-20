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

    /**
     * 모델이 만든 글의 길이 상한(코드 포인트). 저장 검증기({@link CommunitySnapshotValidator})도 같은 값을 쓴다.
     *
     * <p>GMS 프롬프트가 요구하는 길이(제목 100·요약 400·발화 200)보다 넉넉하다 — 모델은 요구한 길이를 자주 넘긴다(발화 250 을 요구했는데
     * 264·286·373 자가 나온 것을 2026-09-20 실측으로 확인, S15P21A506-412). 넘긴 글은 실패로 버리지 않고 {@link #fit} 이 자른다.
     */
    public static final int MAX_TITLE = 200;

    public static final int MAX_SUMMARY = 500;
    public static final int MAX_MESSAGE_TEXT = 300;

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
            // ① 링크를 지우고 ② 꺾쇠를 전각으로 바꾸고 ③ 길이를 맞춘다. 링크 문구("(링크 생략)")가 길이를 바꾸므로 길이가 맨 끝이다.
            String titleKo = fit(neutralize(stripLinks(summary.titleKo()), "titleKo"), MAX_TITLE, "titleKo");
            String summaryKo =
                    fit(neutralize(stripLinks(summary.summaryKo()), "summaryKo"), MAX_SUMMARY, "summaryKo");
            require(CommunitySnapshotValidator.plain(titleKo, MAX_TITLE), "titleKo not plain/too long");
            require(
                    CommunitySnapshotValidator.plain(summaryKo, MAX_SUMMARY),
                    "summaryKo not plain/too long");
            support(bundle, summary.summarySupport(), "summarySupport");
            require(summary.messages() != null && summary.messages().size() <= MAX_MESSAGES, "messages size");
            var messages = new ArrayList<MessagePayload>();
            var seen = new HashSet<String>();
            for (var m : summary.messages()) {
                require(m != null, "message null");
                String messageText =
                        fit(neutralize(stripLinks(m.text()), "message"), MAX_MESSAGE_TEXT, "message");
                require(seen.add(m.sourceCommentId()), "duplicate message sourceCommentId");
                require(
                        CommunitySnapshotValidator.plain(messageText, MAX_MESSAGE_TEXT),
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
                    // 핵심어·핵심 문장도 같은 치환을 거쳐야 치환된 요약문 안에서 찾아진다.
                    marks(
                            summaryKo,
                            neutralizeAll(summary.keySentences()),
                            neutralizeAll(summary.keyTerms())));
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
     * HTML 꺾쇠({@code <} {@code >})를 전각({@code ＜} {@code ＞})으로 바꿔 **태그로 읽히지 않게** 한다. 길이는 그대로다.
     *
     * <p>이전에는 꺾쇠가 하나라도 있으면 그 이슈의 요약 전체를 실패로 버렸다(XSS 방어). 프롬프트가 금지해도 모델은 코드 조각이 든 논의(예:
     * {@code <script>}·제네릭 {@code List<String>})를 옮기며 꺾쇠를 쓴다 — axios #5366 에서 확인했고, 그 한 글자 때문에 요약이 통째로
     * 사라졌다(S15P21A506-412). 전각 문자는 HTML 에서 태그를 여는 글자가 아니라서 방어는 그대로이고, 코드 조각은 {@code ＜div＞} 처럼
     * 그대로 읽힌다. 저장 검증기({@link CommunitySnapshotValidator#plain})는 원본 꺾쇠를 계속 거부한다 — 이 치환을 거치지 않은 값이 저장되면
     * 막는 이중 방어다. 내용은 로그에 남기지 않는다.
     */
    static String neutralize(String text, String field) {
        if (text == null || (text.indexOf('<') < 0 && text.indexOf('>') < 0)) return text;
        log.info("요약 꺾쇠 치환: field={}", field);
        return text.replace('<', '＜').replace('>', '＞');
    }

    private static List<String> neutralizeAll(List<String> values) {
        if (values == null) return null;
        var out = new ArrayList<String>(values.size());
        for (String v : values) out.add(neutralize(v, "mark"));
        return out;
    }

    /**
     * 길이 상한({@code max}, 코드 포인트)을 넘은 글을 **마지막 완결 문장까지** 잘라 돌려준다. 넘지 않았으면 그대로다.
     *
     * <p>길이 초과는 요약 전체를 버릴 이유가 아니다 — 모델은 요구한 길이를 자주 넘기고, 넘겼다는 이유로 이슈 하나의 요약이 통째로 사라지면
     * 사용자는 아무것도 못 본다(S15P21A506-412). 그렇다고 스키마 {@code maxLength} 로 막으면 GMS 가 문장 중간·단어 중간에서 글을 끊는다(실측:
     * "…우회책을 Type").
     *
     * <p>자르는 규칙: ① 상한 안에서 문장이 끝나는 마지막 자리(., !, ?, … 뒤에 공백이나 끝이 오는 곳)까지. ② 그런 자리가 앞쪽 3분의 1
     * 안이면(너무 많이 잃는다) 마지막 공백까지 자르고 "…"을 붙인다. ③ 공백도 없으면 상한에서 자르고 "…"을 붙인다. 소수점(3.5)·약어처럼
     * 뒤에 공백이 없는 마침표는 문장 끝으로 보지 않는다. 결과는 언제나 {@code max} 이하다.
     *
     * <p>내용은 로그에 남기지 않는다(외부 글이다) — 어느 필드가 몇 자에서 몇 자로 줄었는지만 남긴다.
     */
    static String fit(String text, int max, String field) {
        if (text == null) return null;
        int length = text.codePointCount(0, text.length());
        if (length <= max) return text;
        String fitted = cut(text, max);
        log.info(
                "요약 길이 보정: field={}, {}자 → {}자",
                field,
                length,
                fitted.codePointCount(0, fitted.length()));
        return fitted;
    }

    private static String cut(String text, int max) {
        int limit = text.offsetByCodePoints(0, max);
        int floor = text.offsetByCodePoints(0, max / 3);
        for (int i = limit - 1; i >= floor; i--) {
            if (isSentenceEnd(text.charAt(i))
                    && (i + 1 >= text.length() || Character.isWhitespace(text.charAt(i + 1)))) {
                String head = text.substring(0, i + 1).stripTrailing();
                if (!head.isBlank()) return head;
            }
        }
        // "…" 한 글자를 붙일 자리를 남긴다.
        int room = text.offsetByCodePoints(0, max - 1);
        int space = text.lastIndexOf(' ', room);
        int end = space >= floor ? space : room;
        String head = text.substring(0, end).stripTrailing();
        return head.isBlank() ? text.substring(0, room) + "…" : head + "…";
    }

    private static boolean isSentenceEnd(char c) {
        return c == '.' || c == '!' || c == '?' || c == '…' || c == '。';
    }

    /**
     * 모델이 준 핵심 문장·핵심어를 **최종 요약문 안에서 찾아** 강조 구간으로 바꾼다.
     *
     * <p>강조는 읽기 보조라 어긋난 것은 **버릴 뿐 요약을 실패시키지 않는다**(모델이 요약문에 없는 말을 "핵심어"로 줘도 요약은
     * 멀쩡하다). 요약문에 글자 그대로 있는 것만 인정하고, 위치는 서버가 계산한다 — 모델이 준 오프셋은 믿지 않는다. 링크
     * 제거({@link #stripLinks})·꺾쇠 치환({@link #neutralize}) 뒤의 문장 기준이라 반드시 그 뒤에 부른다.
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
     * 태그, XSS 방어)는 여기서 건드리지 않고 {@link #neutralize} 가 전각으로 바꾼다 —
     * {@link CommunitySnapshotValidator#plain}이 이 메서드와 그 치환을 거친 텍스트를 마지막으로 한 번 더 검사한다.
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
