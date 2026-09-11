package com.ssafy.pickage.domain.community.collection;

import java.util.Comparator;
import java.util.List;

/**
 * github-active-v1 정책(구현계획 §저장소와 Issue "Issue 정책")을 옮긴 순수 함수. HTTP 응답을
 * 이미 {@link SearchResultItem}으로 정규화한 뒤의 값만 다룬다 — 재시도(180일→365일)나
 * {@code incomplete_results} 판단은 원본 검색 응답 전체(특히 {@code total_count})가 있어야
 * 하므로 {@link IssueCollectionService}가 담당한다.
 *
 * <p>PR·locked·Bot 작성 이슈를 걸러낸 <b>뒤에</b> 0건이 남아도 여기서 페이지나 기간을 늘리지
 * 않는다(Jira 212 세부 항목) — 그건 "정책이 고른 결과가 없다"이지 "검색이 실패했다"가
 * 아니다.
 */
final class IssueSelectionPolicy {

	static final int MAX_SELECTED_ISSUES = 2;

	private IssueSelectionPolicy() {
	}

	/**
	 * GitHub가 이미 {@code sort=comments&order=desc}로 정렬해 준 상위 30건 안에서만
	 * 동작한다 — 이 메서드가 그 30건보다 더 넓게 다시 조회하지 않는다.
	 */
	static List<SearchResultItem> select(List<SearchResultItem> topThirty) {
		Comparator<SearchResultItem> byCommentCountDesc =
			Comparator.comparingInt(SearchResultItem::commentCount).reversed();
		Comparator<SearchResultItem> byUpdatedAtDesc =
			Comparator.comparing(SearchResultItem::updatedAt).reversed();
		Comparator<SearchResultItem> byNumberDesc =
			Comparator.comparingInt(SearchResultItem::number).reversed();

		return topThirty.stream()
			.filter(item -> !item.isPullRequest())
			.filter(item -> !item.locked())
			.filter(item -> !item.authorIsBot())
			.sorted(byCommentCountDesc.thenComparing(byUpdatedAtDesc).thenComparing(byNumberDesc))
			.limit(MAX_SELECTED_ISSUES)
			.toList();
	}
}
