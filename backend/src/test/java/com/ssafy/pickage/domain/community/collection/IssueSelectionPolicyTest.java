package com.ssafy.pickage.domain.community.collection;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.Test;

class IssueSelectionPolicyTest {

	private static SearchResultItem issue(int number, int commentCount, String updatedAt) {
		return new SearchResultItem(number, "title-" + number, "OPEN",
			Instant.parse(updatedAt), "someone", false, false, false, commentCount, 0);
	}

	@Test
	void 댓글_많은_순으로_최대_2건_고른다() {
		List<SearchResultItem> selected = IssueSelectionPolicy.select(List.of(
			issue(1, 5, "2026-01-01T00:00:00Z"),
			issue(2, 30, "2026-01-01T00:00:00Z"),
			issue(3, 10, "2026-01-01T00:00:00Z")));

		assertThat(selected).extracting(SearchResultItem::number).containsExactly(2, 3);
	}

	@Test
	void PR은_제외한다() {
		SearchResultItem pr = new SearchResultItem(1, "pr", "OPEN",
			Instant.parse("2026-01-01T00:00:00Z"), "someone", false, false, true, 100, 0);
		List<SearchResultItem> selected = IssueSelectionPolicy.select(List.of(pr, issue(2, 1, "2026-01-01T00:00:00Z")));

		assertThat(selected).extracting(SearchResultItem::number).containsExactly(2);
	}

	@Test
	void locked_이슈는_제외한다() {
		SearchResultItem locked = new SearchResultItem(1, "locked", "OPEN",
			Instant.parse("2026-01-01T00:00:00Z"), "someone", false, true, false, 100, 0);
		List<SearchResultItem> selected = IssueSelectionPolicy.select(List.of(locked, issue(2, 1, "2026-01-01T00:00:00Z")));

		assertThat(selected).extracting(SearchResultItem::number).containsExactly(2);
	}

	@Test
	void Bot_작성_이슈는_제외한다() {
		SearchResultItem bot = new SearchResultItem(1, "bot", "OPEN",
			Instant.parse("2026-01-01T00:00:00Z"), "some-bot", true, false, false, 100, 0);
		List<SearchResultItem> selected = IssueSelectionPolicy.select(List.of(bot, issue(2, 1, "2026-01-01T00:00:00Z")));

		assertThat(selected).extracting(SearchResultItem::number).containsExactly(2);
	}

	@Test
	void 댓글_수가_같으면_최신_갱신_순으로_정렬한다() {
		List<SearchResultItem> selected = IssueSelectionPolicy.select(List.of(
			issue(1, 10, "2026-01-01T00:00:00Z"),
			issue(2, 10, "2026-06-01T00:00:00Z"),
			issue(3, 10, "2026-03-01T00:00:00Z")));

		assertThat(selected).extracting(SearchResultItem::number).containsExactly(2, 3);
	}

	@Test
	void 댓글_수와_갱신시각도_같으면_이슈번호_큰_순으로_정렬한다() {
		List<SearchResultItem> selected = IssueSelectionPolicy.select(List.of(
			issue(5, 10, "2026-01-01T00:00:00Z"),
			issue(9, 10, "2026-01-01T00:00:00Z"),
			issue(7, 10, "2026-01-01T00:00:00Z")));

		assertThat(selected).extracting(SearchResultItem::number).containsExactly(9, 7);
	}

	@Test
	void 필터_후_0건이면_빈_목록을_돌려준다_추가_조회_안_함() {
		SearchResultItem onlyBot = new SearchResultItem(1, "bot", "OPEN",
			Instant.parse("2026-01-01T00:00:00Z"), "some-bot", true, false, false, 100, 0);

		assertThat(IssueSelectionPolicy.select(List.of(onlyBot))).isEmpty();
	}

	@Test
	void 빈_입력은_빈_결과다() {
		assertThat(IssueSelectionPolicy.select(List.of())).isEmpty();
	}
}
