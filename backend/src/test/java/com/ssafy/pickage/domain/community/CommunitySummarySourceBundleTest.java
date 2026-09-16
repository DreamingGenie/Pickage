package com.ssafy.pickage.domain.community;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.pickage.domain.community.collection.CollectedComment;
import com.ssafy.pickage.domain.community.collection.CollectedIssue;
import com.ssafy.pickage.domain.community.collection.CommentCollectionStatus;

import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

/**
 * S15P21A506-373 2단계 — {@link CommunitySummarySourceBundle#from}의 반응 수 기반 선택 로직
 * 전용 시험. 4000자 per-comment 상한 때문에 예산을 강제로 소진시키려면 다수의 필러(filler)
 * 댓글이 필요하다(각 시나리오 주석에 산수를 남겨 둔다).
 */
class CommunitySummarySourceBundleTest {

    private static final Instant BASE = Instant.parse("2026-01-01T00:00:00Z");
    private static final String FULL_COMMENT = "x".repeat(4000);

    private static CollectedComment comment(
            String id, String authorId, int reactionCount, Instant createdAt) {
        return new CollectedComment(
                id, "user-" + authorId, "NONE", false, createdAt, FULL_COMMENT, authorId, reactionCount);
    }

    private static CollectedIssue issue(String authorId, List<CollectedComment> comments) {
        return new CollectedIssue(
                1,
                "제목",
                "open",
                BASE,
                "author-login",
                comments.size(),
                0,
                CommentCollectionStatus.COMPLETE,
                comments,
                List.of(),
                "701",
                BASE,
                authorId,
                "");
    }

    @Test
    void 반응_수가_높은_과거_댓글이_반응_수가_낮은_최신_댓글보다_우선_선택된다() {
        // remaining = 48000(제목·본문 없음). old-popular(100) + filler 11개(50) = 12개 * 4000 =
        // 48000으로 예산을 정확히 채운다. new-unpopular(0)는 우선순위가 가장 낮아 예산이 하나도
        // 안 남아 통째로 탈락한다.
        var oldPopular = comment("old-popular", "other", 100, BASE);
        var filler = new ArrayList<CollectedComment>();
        for (int i = 0; i < 11; i++)
            filler.add(comment("filler-" + i, "other", 50, BASE.plusSeconds(i)));
        var newUnpopular = comment("new-unpopular", "other", 0, BASE.plusSeconds(999));

        var comments = new ArrayList<CollectedComment>();
        comments.add(oldPopular);
        comments.addAll(filler);
        comments.add(newUnpopular);
        var bundle = CommunitySummarySourceBundle.from(issue("issue-author", comments));

        assertThat(bundle.sources())
                .containsKey(new TopicSummary.SourceRef("COMMENT", "old-popular"));
        assertThat(bundle.sources())
                .doesNotContainKey(new TopicSummary.SourceRef("COMMENT", "new-unpopular"));
        assertThat(bundle.limited()).isTrue();
    }

    @Test
    void 반응_수가_동률이면_최신_댓글이_우선된다() {
        // 13개 전부 reactionCount=0(전부 동률) → 순수 recency tie-break만 작동. 12개(48000)만
        // 예산에 들어가고 가장 오래된 1개가 탈락해야 한다.
        var comments = new ArrayList<CollectedComment>();
        for (int i = 0; i < 13; i++)
            comments.add(comment("c" + i, "other", 0, BASE.plusSeconds(i)));
        var bundle = CommunitySummarySourceBundle.from(issue("issue-author", comments));

        assertThat(bundle.sources()).doesNotContainKey(new TopicSummary.SourceRef("COMMENT", "c0"));
        assertThat(bundle.sources()).containsKey(new TopicSummary.SourceRef("COMMENT", "c12"));
    }

    @Test
    void 이슈_작성자의_최초_댓글은_반응_수가_낮아도_우선_포함되고_나머지_작성자_댓글은_특례가_없다() {
        // firstAuthorComment(0순위 특례)가 먼저 4000을 쓰고 나면 남은 예산은 44000.
        // filler 12개(100, 4000자씩)는 48000이 필요해 그중 11개(44000)만 들어가고 1개가
        // 탈락해야 한다. secondAuthorComment(특례 없음, reaction 0)는 우선순위가 가장 낮아
        // 자리가 아예 없어 탈락한다 — "나머지 작성자 댓글은 특례 없음"을 이 탈락으로 증명한다.
        var firstAuthorComment = comment("first-author", "issue-author", 0, BASE);
        var secondAuthorComment =
                comment("second-author", "issue-author", 0, BASE.plusSeconds(999));
        var filler = new ArrayList<CollectedComment>();
        for (int i = 0; i < 12; i++)
            filler.add(comment("filler-" + i, "other", 100, BASE.plusSeconds(i + 1)));

        var comments = new ArrayList<CollectedComment>();
        comments.add(firstAuthorComment);
        comments.add(secondAuthorComment);
        comments.addAll(filler);
        var bundle = CommunitySummarySourceBundle.from(issue("issue-author", comments));

        assertThat(bundle.sources())
                .containsKey(new TopicSummary.SourceRef("COMMENT", "first-author"));
        assertThat(bundle.sources())
                .doesNotContainKey(new TopicSummary.SourceRef("COMMENT", "second-author"));
    }

    // --- S15P21A506-373 4단계: batches() ---------------------------------------------------

    @Test
    void 단일_bundle이_잘리지_않으면_batches는_빈_리스트를_반환한다() {
        var comments = List.of(comment("c1", "other", 0, BASE));
        assertThat(CommunitySummarySourceBundle.batches(issue("issue-author", comments))).isEmpty();
    }

    @Test
    void 단일_bundle_예산을_넘는_이슈는_여러_배치로_나뉘고_배치_상한_안이면_전부_보존된다() {
        // 200자 댓글 250개(50000자) — 단일 48000자 예산은 넘지만, 배치당(12000자) 여유가
        // 충분해(배치 하나에 대략 55~60개) 배치 수 상한(5)에 걸리지 않고 전부 보존돼야 한다.
        var comments = new ArrayList<CollectedComment>();
        for (int i = 0; i < 250; i++)
            comments.add(
                    new CollectedComment(
                            "c" + i,
                            "user-other",
                            "NONE",
                            false,
                            BASE.plusSeconds(i),
                            "x".repeat(200),
                            "other",
                            0));
        var batches = CommunitySummarySourceBundle.batches(issue("issue-author", comments));

        assertThat(batches).isNotEmpty();
        assertThat(batches.size()).isLessThanOrEqualTo(CommunityProperties.MAX_SUMMARY_BATCHES);
        var selectedIds =
                batches.stream()
                        .flatMap(b -> b.issue().comments().stream())
                        .map(CollectedComment::sourceCommentId)
                        .toList();
        assertThat(selectedIds).hasSize(250);
        assertThat(new java.util.HashSet<>(selectedIds)).hasSize(250);
        batches.forEach(
                b -> {
                    int len =
                            b.issue().comments().stream()
                                    .mapToInt(c -> c.body().codePointCount(0, c.body().length()))
                                    .sum();
                    assertThat(len).isLessThanOrEqualTo(CommunityProperties.SUMMARY_BATCH_CHAR_BUDGET);
                    assertThat(b.limited()).isFalse();
                });
    }

    @Test
    void 배치_수_상한을_넘으면_남는_댓글은_버려지고_마지막_배치가_limited로_표시된다() {
        // FULL_COMMENT(4000자)짜리 30개 — 배치 하나에 2~3개씩만 들어가 5배치로는 다 못 담는다.
        var comments = new ArrayList<CollectedComment>();
        for (int i = 0; i < 30; i++) comments.add(comment("c" + i, "other", 0, BASE.plusSeconds(i)));
        var batches = CommunitySummarySourceBundle.batches(issue("issue-author", comments));

        assertThat(batches).hasSize(CommunityProperties.MAX_SUMMARY_BATCHES);
        var selectedIds =
                batches.stream()
                        .flatMap(b -> b.issue().comments().stream())
                        .map(CollectedComment::sourceCommentId)
                        .toList();
        assertThat(selectedIds.size()).isLessThan(30);
        assertThat(batches.get(batches.size() - 1).limited()).isTrue();
    }

    @Test
    void 선택된_댓글은_반응_수_우선순위와_무관하게_항상_시각순으로_전달된다() {
        var newest = comment("newest", "other", 100, BASE.plusSeconds(300));
        var oldest = comment("oldest", "other", 0, BASE.plusSeconds(100));
        var middle = comment("middle", "other", 50, BASE.plusSeconds(200));

        var bundle =
                CommunitySummarySourceBundle.from(issue("issue-author", List.of(newest, oldest, middle)));

        assertThat(bundle.issue().comments())
                .extracting(CollectedComment::sourceCommentId)
                .containsExactly("oldest", "middle", "newest");
    }

    // --- 2026-09-16: highlights() — 반응 최다 댓글 + 유지관리자 답글만 -----------------------

    private static CollectedComment commentWithAssociation(
            String id, String authorId, String association, int reactionCount, Instant createdAt) {
        return new CollectedComment(
                id, "user-" + authorId, association, false, createdAt, FULL_COMMENT, authorId, reactionCount);
    }

    @Test
    void highlights는_반응_최다_댓글과_그_이후_첫_유지관리자_답글만_고른다() {
        var topComment = comment("top", "other", 100, BASE.plusSeconds(1));
        var earlyMaintainer =
                commentWithAssociation("early-maintainer", "maint", "MEMBER", 0, BASE); // top보다 먼저 — 제외돼야 함
        var lateMaintainer =
                commentWithAssociation("late-maintainer", "maint", "OWNER", 0, BASE.plusSeconds(2));
        var laterMaintainer =
                commentWithAssociation("later-maintainer", "maint", "COLLABORATOR", 0, BASE.plusSeconds(3));
        var noise = comment("noise", "other", 5, BASE.plusSeconds(4));

        var bundle =
                CommunitySummarySourceBundle.highlights(
                        issue(
                                "issue-author",
                                List.of(topComment, earlyMaintainer, lateMaintainer, laterMaintainer, noise)));

        assertThat(bundle.issue().comments())
                .extracting(CollectedComment::sourceCommentId)
                .containsExactly("top", "late-maintainer"); // top 이후 첫 유지관리자만, 시각순
        assertThat(bundle.limited()).isTrue();
    }

    @Test
    void highlights는_유지관리자_답글이_없으면_반응_최다_댓글만_고른다() {
        var topComment = comment("top", "other", 10, BASE);
        var otherComment = comment("other", "other", 1, BASE.plusSeconds(1));

        var bundle =
                CommunitySummarySourceBundle.highlights(
                        issue("issue-author", List.of(topComment, otherComment)));

        assertThat(bundle.issue().comments())
                .extracting(CollectedComment::sourceCommentId)
                .containsExactly("top");
    }

    @Test
    void highlights는_댓글이_하나도_없으면_담을_댓글이_없고_limited는_false다() {
        // 공용 issue() fixture는 본문이 비어 있다(다른 시험들이 본문 내용에 의존하지 않아서) —
        // 그래서 이 경우 sources는 비고, limited도 false여야 한다(잃어버린 정보가 없으므로).
        var bundle = CommunitySummarySourceBundle.highlights(issue("issue-author", List.of()));

        assertThat(bundle.issue().comments()).isEmpty();
        assertThat(bundle.sources()).isEmpty();
        assertThat(bundle.limited()).isFalse();
    }
}
