package com.ssafy.pickage.domain.community;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.pickage.domain.community.collection.CollectedComment;
import com.ssafy.pickage.domain.community.collection.CollectedIssue;
import com.ssafy.pickage.domain.community.collection.CommentCollectionStatus;
import com.ssafy.pickage.domain.community.dto.SummaryStatus;
import com.ssafy.pickage.domain.community.payload.MessagePayload;

import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

/**
 * S15P21A506-412 — 모델이 요구한 길이를 넘겨도 요약을 버리지 않고 마지막 완결 문장까지 잘라 쓴다.
 *
 * <p>2026-09-20 실측(lodash #6106): 발화 250자를 요구했는데 324자가 나와 "message text not plain/too long" 으로 이슈 요약
 * 전체가 실패했다. 같은 조건에서 264·286·373자가 나오는 것도 확인했다.
 */
class CommunitySummaryFitTest {

    private static int cps(String s) {
        return s.codePointCount(0, s.length());
    }

    // ---- fit(): 자르는 규칙

    @Test
    void 상한_안의_글은_그대로_둔다() {
        String text = "짧은 글이다. 두 문장이다.";

        assertThat(CommunitySummaryValidator.fit(text, 100, "message")).isSameAs(text);
        assertThat(CommunitySummaryValidator.fit(null, 100, "message")).isNull();
    }

    @Test
    void 상한을_넘으면_마지막_완결_문장까지_자른다() {
        String s1 = "첫 문장은 설정을 확인하는 방법을 설명한다.";
        String s2 = "둘째 문장은 예외 상황을 덧붙인다.";
        String s3 = "셋째 문장은 상한을 넘어서 잘려 나가야 한다.";
        String text = s1 + " " + s2 + " " + s3;
        int max = cps(s1 + " " + s2) + 5;

        String fitted = CommunitySummaryValidator.fit(text, max, "message");

        assertThat(fitted).isEqualTo(s1 + " " + s2);
        assertThat(fitted).doesNotContain("…");
        assertThat(cps(fitted)).isLessThanOrEqualTo(max);
    }

    @Test
    void 소수점은_문장_끝으로_보지_않는다() {
        // 상한이 "3." 바로 뒤에 떨어지도록 맞춘다 — 뒤에 공백이 없으므로 여기서 끊으면 안 된다.
        String text = "이 문제는 버전 3.5부터 재현되며 그 전에는 나타나지 않는다고 여러 사용자가 보고했다";
        int max = text.indexOf("3.") + 2;

        String fitted = CommunitySummaryValidator.fit(text, max, "message");

        assertThat(fitted).doesNotEndWith("3.");
        assertThat(cps(fitted)).isLessThanOrEqualTo(max);
        assertThat(fitted).endsWith("…");
    }

    @Test
    void 문장_끝이_없으면_단어_경계에서_자르고_줄임표를_붙인다() {
        String text = "설정을 다시 불러오는 방법과 예외 처리 그리고 남은 문제점 " + "추가로 언급된 여러 가지 세부 사항들 ".repeat(30);
        int max = 100;

        String fitted = CommunitySummaryValidator.fit(text, max, "message");

        assertThat(fitted).endsWith("…").doesNotContain(" …");
        assertThat(cps(fitted)).isLessThanOrEqualTo(max);
        // 단어 중간이 아니라 공백에서 잘렸다 — "…" 앞 글자가 원문의 어느 단어의 끝이다.
        String beforeEllipsis = fitted.substring(0, fitted.length() - 1);
        assertThat(text).startsWith(beforeEllipsis);
        assertThat(text.charAt(beforeEllipsis.length())).isEqualTo(' ');
    }

    @Test
    void 공백도_없으면_상한에서_자르고_줄임표를_붙인다() {
        String fitted = CommunitySummaryValidator.fit("가".repeat(400), 300, "message");

        assertThat(cps(fitted)).isEqualTo(300);
        assertThat(fitted).endsWith("…");
    }

    @Test
    void 앞쪽_3분의_1_안의_문장_끝은_쓰지_않는다() {
        // "네." 에서 끊으면 글의 대부분을 잃는다 — 대신 단어 경계에서 자른다.
        String text = "네. " + "이어지는 설명은 마침표 없이 길게 계속되며 ".repeat(12);

        String fitted = CommunitySummaryValidator.fit(text, 120, "message");

        assertThat(fitted).isNotEqualTo("네.");
        assertThat(fitted).endsWith("…");
        assertThat(cps(fitted)).isLessThanOrEqualTo(120);
    }

    @Test
    void 이모지_같은_서로게이트_쌍을_깨뜨리지_않는다() {
        String fitted = CommunitySummaryValidator.fit("😀".repeat(400), 300, "message");

        assertThat(cps(fitted)).isLessThanOrEqualTo(300);
        // 외톨이 서로게이트가 있으면 UTF-8 왕복에서 값이 달라진다.
        assertThat(new String(fitted.getBytes(StandardCharsets.UTF_8), StandardCharsets.UTF_8)).isEqualTo(fitted);
    }

    // ---- validate(): 길이 초과가 요약 전체를 실패시키지 않는다

    private static final Instant BASE = Instant.parse("2026-01-01T00:00:00Z");

    private static CommunitySummarySourceBundle bundle() {
        var comments = new ArrayList<CollectedComment>();
        for (int i = 0; i < 2; i++)
            comments.add(
                    new CollectedComment(
                            String.valueOf(100 + i), "user" + i, "NONE", false, BASE.plusSeconds(i), "댓글 " + i, "id" + i, i));
        var issue =
                new CollectedIssue(
                        1, "제목", "open", BASE, "author", 2, 0,
                        CommentCollectionStatus.COMPLETE, comments, List.of(), "701", BASE, "author-id", "본문");
        return CommunitySummarySourceBundle.highlights(issue);
    }

    private static TopicSummary summary(
            CommunitySummarySourceBundle bundle,
            String title,
            String summaryKo,
            String messageText,
            List<String> sentences) {
        var refs = List.of(new TopicSummary.SourceRef("ISSUE_BODY", "701"));
        var messages = new ArrayList<MessagePayload>();
        for (var c : bundle.issue().comments())
            messages.add(new MessagePayload(c.sourceCommentId(), null, null, false, "DISCUSSION", null, messageText));
        return new TopicSummary(title, summaryKo, messages, SummaryStatus.READY, refs, List.of(), sentences, List.of());
    }

    private static String sentences(String sentence, int count) {
        return (sentence + " ").repeat(count).strip();
    }

    @Test
    void 발화가_상한을_넘어도_요약은_실패하지_않고_문장까지_잘린다() {
        // lodash #6106 을 재현한다 — 발화 하나가 324자여서 이슈 요약 전체가 실패했다.
        String longMessage = sentences("설정을 다시 불러오는 방법을 댓글에서 설명했다.", 14);
        assertThat(cps(longMessage)).isGreaterThan(300);

        var result =
                CommunitySummaryValidator.validate(bundle(), summary(bundle(), "제목", "요약", longMessage, List.of()));

        assertThat(result.status()).isEqualTo(SummaryStatus.READY);
        assertThat(result.messages()).hasSize(2);
        for (var m : result.messages()) {
            assertThat(cps(m.text())).isLessThanOrEqualTo(CommunitySummaryValidator.MAX_MESSAGE_TEXT);
            assertThat(m.text()).endsWith("했다.");
        }
    }

    @Test
    void 요약문이_상한을_넘어도_실패하지_않고_잘려_나간_부분의_강조만_버린다() {
        String keptSentence = "유지되는 앞쪽 문장이다.";
        String endSentence = "맨 끝에만 있는 문장이다.";
        String summaryKo = sentences("중간을 채우는 문장이다.", 60) + " " + endSentence;
        summaryKo = keptSentence + " " + summaryKo;
        assertThat(cps(summaryKo)).isGreaterThan(CommunitySummaryValidator.MAX_SUMMARY);

        var result =
                CommunitySummaryValidator.validate(
                        bundle(), summary(bundle(), "제목", summaryKo, "발화", List.of(keptSentence, endSentence)));

        assertThat(result.status()).isEqualTo(SummaryStatus.READY);
        assertThat(cps(result.summaryKo())).isLessThanOrEqualTo(CommunitySummaryValidator.MAX_SUMMARY);
        assertThat(result.summaryKo()).doesNotContain(endSentence);
        // 잘린 글 기준으로 강조를 다시 찾는다 — 남은 문장만 표시되고, 잘려 나간 문장은 요약을 실패시키지 않고 버려진다.
        assertThat(result.summaryMarks())
                .extracting(m -> result.summaryKo().substring(m.start(), m.end()))
                .containsExactly(keptSentence);
    }

    @Test
    void 제목이_상한을_넘어도_실패하지_않는다() {
        String title = sentences("제목이 너무 길게 만들어졌다.", 20);
        assertThat(cps(title)).isGreaterThan(CommunitySummaryValidator.MAX_TITLE);

        var result = CommunitySummaryValidator.validate(bundle(), summary(bundle(), title, "요약", "발화", List.of()));

        assertThat(result.status()).isEqualTo(SummaryStatus.READY);
        assertThat(cps(result.titleKo())).isLessThanOrEqualTo(CommunitySummaryValidator.MAX_TITLE);
    }

    // ---- 꺾쇠 치환: 요약을 버리지 않는다 (axios #5366)

    @Test
    void 발화에_꺾쇠가_있어도_요약은_실패하지_않고_전각으로_바뀐다() {
        // axios #5366 을 재현한다 — 코드 조각이 든 논의를 옮기며 모델이 꺾쇠를 써서 이슈 요약 전체가 실패했다.
        String message = "타입을 List<String> 으로 두고 <script> 태그는 쓰지 말라고 설명했다.";

        var result = CommunitySummaryValidator.validate(bundle(), summary(bundle(), "제목", "요약", message, List.of()));

        assertThat(result.status()).isEqualTo(SummaryStatus.READY);
        for (var m : result.messages()) {
            assertThat(m.text()).isEqualTo("타입을 List＜String＞ 으로 두고 ＜script＞ 태그는 쓰지 말라고 설명했다.");
            assertThat(m.text()).doesNotContain("<").doesNotContain(">");
            // 저장 검증기가 마지막으로 한 번 더 거른다 — 치환된 값은 통과해야 게시가 실패하지 않는다.
            assertThat(CommunitySnapshotValidator.plain(m.text(), CommunitySummaryValidator.MAX_MESSAGE_TEXT)).isTrue();
        }
    }

    @Test
    void 제목과_요약문의_꺾쇠도_바꾼다() {
        var result =
                CommunitySummaryValidator.validate(
                        bundle(), summary(bundle(), "<b>굵게</b> 제목", "a > b 이고 c < d 이다.", "발화", List.of()));

        assertThat(result.status()).isEqualTo(SummaryStatus.READY);
        assertThat(result.titleKo()).isEqualTo("＜b＞굵게＜/b＞ 제목");
        assertThat(result.summaryKo()).isEqualTo("a ＞ b 이고 c ＜ d 이다.");
    }

    @Test
    void 꺾쇠가_든_핵심_문장도_치환된_요약문에서_강조로_찾는다() {
        String key = "Promise<void> 를 반환한다.";
        String summaryKo = "핵심 함수는 " + key + " 나머지는 부수적이다.";

        var result =
                CommunitySummaryValidator.validate(
                        bundle(), summary(bundle(), "제목", summaryKo, "발화", List.of(key)));

        assertThat(result.status()).isEqualTo(SummaryStatus.READY);
        assertThat(result.summaryMarks())
                .extracting(m -> result.summaryKo().substring(m.start(), m.end()))
                .containsExactly("Promise＜void＞ 를 반환한다.");
    }

    @Test
    void 꺾쇠가_든_긴_발화도_치환과_자르기를_함께_거쳐_실패하지_않는다() {
        String longWithTag = sentences("설정을 <script> 태그로 넣으라고 설명했다.", 14);
        assertThat(cps(longWithTag)).isGreaterThan(CommunitySummaryValidator.MAX_MESSAGE_TEXT);

        var result = CommunitySummaryValidator.validate(bundle(), summary(bundle(), "제목", "요약", longWithTag, List.of()));

        assertThat(result.status()).isEqualTo(SummaryStatus.READY);
        for (var m : result.messages()) {
            assertThat(cps(m.text())).isLessThanOrEqualTo(CommunitySummaryValidator.MAX_MESSAGE_TEXT);
            assertThat(m.text()).doesNotContain("<").doesNotContain(">").contains("＜script＞");
        }
    }

    @Test
    void 꺾쇠_치환은_길이를_바꾸지_않고_꺾쇠가_없는_글은_그대로_둔다() {
        String plain = "꺾쇠가 없는 글이다.";

        assertThat(CommunitySummaryValidator.neutralize(plain, "message")).isSameAs(plain);
        assertThat(CommunitySummaryValidator.neutralize(null, "message")).isNull();
        String withTag = "a<b>c";
        assertThat(CommunitySummaryValidator.neutralize(withTag, "message")).hasSize(withTag.length());
    }

    @Test
    void 링크와_꺾쇠가_함께_있어도_링크는_지우고_꺾쇠는_바꾼다() {
        var result =
                CommunitySummaryValidator.validate(
                        bundle(),
                        summary(bundle(), "제목", "요약", "<https://example.com/a> 를 참고하라고 했다.", List.of()));

        assertThat(result.status()).isEqualTo(SummaryStatus.READY);
        for (var m : result.messages()) {
            assertThat(m.text()).doesNotContain("https://").doesNotContain("<").doesNotContain(">");
            assertThat(m.text()).contains("링크 생략");
        }
    }

    @Test
    void 저장_검증기는_원본_꺾쇠가_든_값을_계속_거부한다() {
        // 이중 방어 — 치환을 거치지 않은 값이 저장 경로로 들어오면 게시 검증에서 막힌다.
        assertThat(CommunitySnapshotValidator.plain("<script>", 500)).isFalse();
        assertThat(CommunitySnapshotValidator.plain("a > b", 500)).isFalse();
        assertThat(CommunitySnapshotValidator.plain("＜script＞", 500)).isTrue();
    }
}
