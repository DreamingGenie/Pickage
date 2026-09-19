package com.ssafy.pickage.domain.community;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.pickage.domain.community.collection.CollectedComment;
import com.ssafy.pickage.domain.community.collection.CollectedIssue;
import com.ssafy.pickage.domain.community.collection.CommentCollectionStatus;
import com.ssafy.pickage.domain.community.dto.SummaryStatus;
import com.ssafy.pickage.domain.community.payload.DiscussionStepPayload;
import com.ssafy.pickage.domain.community.payload.MessagePayload;
import com.ssafy.pickage.domain.community.payload.SummaryMarkPayload;

import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

/**
 * S15P21A506-408 — 모델이 준 핵심어·핵심 문장을 요약문 안의 강조 구간으로 바꾸는 규칙, 그리고 발화 4개 상한.
 * 강조는 읽기 보조라 어긋난 것은 버리되 요약을 실패시키지 않아야 한다.
 */
class CommunitySummaryMarksTest {

    private static final String SUMMARY =
            "사건은 유지관리자 계정이 탈취되어 악성 버전이 npm에 게시된 공급망 침해로 정리된다. "
                    + "악성 버전은 약 3시간 동안 노출되었고, 재발 방지 조치가 제시되었다.";
    private static final String KEY_SENTENCE = "악성 버전은 약 3시간 동안 노출되었고, 재발 방지 조치가 제시되었다.";

    private static List<SummaryMarkPayload> marks(List<String> sentences, List<String> terms) {
        return CommunitySummaryValidator.marks(SUMMARY, sentences, terms);
    }

    private static String cut(SummaryMarkPayload m) {
        return SUMMARY.substring(m.start(), m.end());
    }

    @Test
    void 요약문에_글자_그대로_있는_핵심어와_핵심_문장만_구간으로_바꾼다() {
        var result = marks(List.of(KEY_SENTENCE), List.of("공급망 침해", "유지관리자 계정"));

        assertThat(result).extracting(SummaryMarkPayload::kind)
                .containsExactly("KEY_TERM", "KEY_TERM", "KEY_SENTENCE");
        assertThat(result).extracting(CommunitySummaryMarksTest::cut)
                .containsExactly("유지관리자 계정", "공급망 침해", KEY_SENTENCE);
    }

    @Test
    void 요약문에_없는_말은_버리고_요약을_실패시키지_않는다() {
        var result = marks(List.of("요약문에 전혀 없는 문장이다."), List.of("없는 말", "공급망 침해"));

        assertThat(result).extracting(CommunitySummaryMarksTest::cut).containsExactly("공급망 침해");
    }

    @Test
    void 위치는_서버가_계산한다_모델이_준_값을_쓰지_않는다() {
        var result = marks(List.of(), List.of("npm"));

        assertThat(result).hasSize(1);
        assertThat(result.getFirst().start()).isEqualTo(SUMMARY.indexOf("npm"));
        assertThat(result.getFirst().end()).isEqualTo(SUMMARY.indexOf("npm") + 3);
    }

    @Test
    void 핵심어끼리_겹치면_먼저_온_것만_남긴다() {
        var result = marks(List.of(), List.of("악성 버전은 약 3시간", "3시간 동안"));

        assertThat(result).extracting(CommunitySummaryMarksTest::cut).containsExactly("악성 버전은 약 3시간");
    }

    @Test
    void 핵심어가_핵심_문장_안에_통째로_들어가면_함께_둔다() {
        var result = marks(List.of(KEY_SENTENCE), List.of("3시간"));

        assertThat(result).extracting(SummaryMarkPayload::kind)
                .containsExactly("KEY_SENTENCE", "KEY_TERM");
    }

    @Test
    void 핵심어가_핵심_문장_경계에_걸치면_버린다() {
        // "게시된 공급망 침해로 정리된다. 악성 버전은" 처럼 핵심 문장 시작을 넘나드는 구간
        var result = marks(List.of(KEY_SENTENCE), List.of("정리된다. 악성"));

        assertThat(result).extracting(SummaryMarkPayload::kind).containsExactly("KEY_SENTENCE");
    }

    @Test
    void 요약문_대부분을_덮는_핵심_문장은_강조가_아니라서_버린다() {
        var result = marks(List.of(SUMMARY), List.of());

        assertThat(result).isEmpty();
    }

    @Test
    void 개수와_길이_상한을_지킨다() {
        var terms = List.of("사건", "유지관리자", "계정", "악성", "npm", "공급망", "3시간", "재발");
        var result = marks(List.of(KEY_SENTENCE, "사건은 유지관리자 계정이 탈취되어", "세 번째 문장이다."), terms);

        assertThat(result.stream().filter(m -> m.kind().equals("KEY_SENTENCE")))
                .hasSizeLessThanOrEqualTo(CommunitySummaryValidator.MAX_KEY_SENTENCES);
        assertThat(result.stream().filter(m -> m.kind().equals("KEY_TERM")))
                .hasSizeLessThanOrEqualTo(CommunitySummaryValidator.MAX_KEY_TERMS);
        assertThat(marks(List.of(), List.of("악성 버전이 npm에 게시된 공급망 침해로 정리된다. 악성"))).isEmpty(); // 30자 초과
    }

    @Test
    void 결과는_시작_위치_순으로_정렬된다() {
        var result = marks(List.of(KEY_SENTENCE), List.of("재발 방지", "유지관리자"));

        assertThat(result).extracting(SummaryMarkPayload::start).isSorted();
    }

    @Test
    void null_이나_빈_입력은_빈_목록이다() {
        assertThat(CommunitySummaryValidator.marks(SUMMARY, null, null)).isEmpty();
        assertThat(CommunitySummaryValidator.marks(null, List.of("a"), List.of("b"))).isEmpty();
        assertThat(marks(List.of(" "), java.util.Arrays.asList((String) null))).isEmpty();
    }

    // ---- validate() 통합: 링크 제거 뒤 문장 기준, 발화 4개

    private static final Instant BASE = Instant.parse("2026-01-01T00:00:00Z");

    private static CollectedComment comment(int n) {
        return new CollectedComment(
                String.valueOf(100 + n), "user" + n, "NONE", false, BASE.plusSeconds(n), "댓글 " + n, "id" + n, n);
    }

    private static CommunitySummarySourceBundle bundle(int commentCount) {
        var comments = new ArrayList<CollectedComment>();
        for (int i = 0; i < commentCount; i++) comments.add(comment(i));
        var issue =
                new CollectedIssue(
                        1, "제목", "open", BASE, "author", commentCount, 0,
                        CommentCollectionStatus.COMPLETE, comments, List.of(), "701", BASE, "author-id", "본문");
        return CommunitySummarySourceBundle.highlights(issue);
    }

    private static TopicSummary summary(
            CommunitySummarySourceBundle bundle, String summaryKo, List<String> terms, List<String> sentences) {
        var refs = List.of(new TopicSummary.SourceRef("ISSUE_BODY", "701"));
        var messages = new ArrayList<MessagePayload>();
        for (var c : bundle.issue().comments())
            messages.add(new MessagePayload(c.sourceCommentId(), null, null, false, "DISCUSSION", null, "발화 " + c.sourceCommentId()));
        return new TopicSummary(
                "제목", summaryKo, List.of(new DiscussionStepPayload("흐름")), messages, SummaryStatus.READY,
                refs, List.of(refs), terms, sentences, List.of());
    }

    @Test
    void 검증기는_강조_구간을_계산해_결과에_담는다() {
        var b = bundle(2);

        var validated = CommunitySummaryValidator.validate(b, summary(b, SUMMARY, List.of("공급망 침해"), List.of(KEY_SENTENCE)));

        assertThat(validated.status()).isEqualTo(SummaryStatus.READY);
        assertThat(validated.summaryMarks()).extracting(CommunitySummaryMarksTest::cut)
                .containsExactly("공급망 침해", KEY_SENTENCE);
        // raw 핵심어는 결과에 남기지 않는다 — 검증을 통과한 구간만 나간다.
        assertThat(validated.keyTerms()).isEmpty();
    }

    @Test
    void 링크가_제거된_뒤의_요약문_기준으로_구간을_계산한다() {
        var b = bundle(1);
        String raw = "자세한 내용은 https://example.com/post 에 있고 핵심은 재발 방지다.";

        var validated = CommunitySummaryValidator.validate(b, summary(b, raw, List.of("재발 방지"), List.of()));

        assertThat(validated.status()).isEqualTo(SummaryStatus.READY);
        assertThat(validated.summaryKo()).contains("(링크 생략)").doesNotContain("example.com");
        var mark = validated.summaryMarks().getFirst();
        assertThat(validated.summaryKo().substring(mark.start(), mark.end())).isEqualTo("재발 방지");
    }

    @Test
    void 엉뚱한_핵심어가_와도_요약은_성공한다() {
        var b = bundle(1);

        var validated = CommunitySummaryValidator.validate(b, summary(b, SUMMARY, List.of("전혀 없는 말"), List.of("없는 문장")));

        assertThat(validated.status()).isEqualTo(SummaryStatus.READY);
        assertThat(validated.summaryMarks()).isEmpty();
    }

    @Test
    void 발화는_4개까지_통과하고_5개는_실패한다() {
        var four = bundle(6); // highlights 가 4개로 자른다
        assertThat(four.issue().comments()).hasSize(4);
        assertThat(CommunitySummaryValidator.validate(four, summary(four, SUMMARY, List.of(), List.of())).status())
                .isEqualTo(SummaryStatus.READY);

        // 모델이 번들에 없는 다섯 번째 발화까지 만들어 오면 검증에서 탈락한다.
        var messages = new ArrayList<>(summary(four, SUMMARY, List.of(), List.of()).messages());
        messages.add(new MessagePayload("999", null, null, false, "DISCUSSION", null, "여분 발화"));
        var refs = List.of(new TopicSummary.SourceRef("ISSUE_BODY", "701"));
        var five =
                new TopicSummary("제목", SUMMARY, List.of(new DiscussionStepPayload("흐름")), messages,
                        SummaryStatus.READY, refs, List.of(refs));
        assertThat(CommunitySummaryValidator.validate(four, five).status()).isEqualTo(SummaryStatus.FAILED);
    }
}
