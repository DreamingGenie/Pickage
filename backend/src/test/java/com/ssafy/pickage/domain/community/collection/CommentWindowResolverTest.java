package com.ssafy.pickage.domain.community.collection;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.Test;

class CommentWindowResolverTest {

	private static CollectedComment comment(String id) {
		return new CollectedComment(id, "someone", "NONE", false, Instant.parse("2026-01-01T00:00:00Z"), "body");
	}

	@Test
	void 마지막_page가_1이면_추가_호출이_필요_없다() {
		assertThat(CommentWindowResolver.planAdditionalPages(1)).isEmpty();
	}

	@Test
	void 마지막_page가_2면_그_page만_추가로_부른다_1페이지는_이미_있음() {
		assertThat(CommentWindowResolver.planAdditionalPages(2)).containsExactly(2);
	}

	@Test
	void 마지막_page가_3이상이면_마지막과_그_직전_page를_부른다() {
		assertThat(CommentWindowResolver.planAdditionalPages(5)).containsExactly(5, 4);
	}

	@Test
	void id_내림차순으로_100개만_남긴다() {
		List<CollectedComment> candidates = java.util.stream.IntStream.rangeClosed(1, 150)
			.mapToObj(i -> comment(String.valueOf(i)))
			.toList();

		List<CollectedComment> selected = CommentWindowResolver.selectLatest(candidates);

		assertThat(selected).hasSize(100);
		assertThat(selected.getFirst().sourceCommentId()).isEqualTo("150");
		assertThat(selected.getLast().sourceCommentId()).isEqualTo("51");
	}

	@Test
	void 큰_ID도_BigInteger로_정확히_비교한다() {
		// long 최댓값 근처에서도 정밀도 손실 없이 비교돼야 한다.
		List<CollectedComment> candidates = List.of(
			comment("9223372036854775807"), // Long.MAX_VALUE
			comment("9223372036854775806"),
			comment("1"));

		List<CollectedComment> selected = CommentWindowResolver.selectLatest(candidates);

		assertThat(selected).extracting(CollectedComment::sourceCommentId)
			.containsExactly("9223372036854775807", "9223372036854775806", "1");
	}

	@Test
	void 겹치는_ID는_한_번만_남는다() {
		List<CollectedComment> candidates = List.of(comment("1"), comment("1"), comment("2"));

		assertThat(CommentWindowResolver.selectLatest(candidates)).hasSize(2);
	}

	@Test
	void 상한_100개_이하면_전부_남는다() {
		List<CollectedComment> candidates = List.of(comment("1"), comment("2"), comment("3"));

		assertThat(CommentWindowResolver.selectLatest(candidates)).hasSize(3);
	}
}
