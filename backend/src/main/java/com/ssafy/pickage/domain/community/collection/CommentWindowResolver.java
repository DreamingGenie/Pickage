package com.ssafy.pickage.domain.community.collection;

import java.math.BigInteger;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * "최신 100개" 확정 로직(구현계획 §저장소와 Issue, Jira 212 세부 항목)을 순수 함수로 분리한다.
 * 실제 HTTP 호출(어떤 page를 부를지 결정한 뒤 진짜로 부르는 것)은
 * {@link GitHubIssueCommentsClient}가 한다 — 이 클래스는 "몇 페이지를 더 불러야 하는지"와
 * "받은 후보들 중 무엇을 남길지"만 순수하게 계산한다.
 */
final class CommentWindowResolver {

	static final int TARGET_COMMENT_COUNT = 100;

	private CommentWindowResolver() {
	}

	/**
	 * 1페이지 응답의 {@code Link: rel="last"}에서 읽은 마지막 page 번호를 받아, 추가로 불러야
	 * 할 page 목록을 정한다. 최신 100개는 마지막 두 page(L, L-1)에 들어 있다 — 한 page가
	 * 정확히 100개씩이 아닐 수 있어 마지막 page 하나만으로는 100개를 못 채울 수 있기
	 * 때문이다. {@code L-1 == 1}이면 이미 1페이지 응답을 가지고 있으므로 다시 부르지
	 * 않는다(호출 3회가 아니라 2회로 끝난다).
	 *
	 * @param lastPageNumber 1이면(또는 Link에 rel="last"가 없어 1로 간주하면) 전체가 이미
	 *                       100개 이하라는 뜻 — 추가 호출이 필요 없다
	 */
	static List<Integer> planAdditionalPages(int lastPageNumber) {
		if (lastPageNumber <= 1) {
			return List.of();
		}
		if (lastPageNumber == 2) {
			return List.of(2);
		}
		return List.of(lastPageNumber, lastPageNumber - 1);
	}

	/**
	 * 여러 page에서 모은 후보(겹칠 수 있음)를 id 내림차순으로 정렬해 최신
	 * {@value #TARGET_COMMENT_COUNT}개만 남긴다. id는 {@link BigInteger}로 비교한다 —
	 * 십진 문자열을 그대로 수치 비교해 어떤 크기의 GitHub ID든 정밀도 손실 없이 다룬다.
	 */
	static List<CollectedComment> selectLatest(List<CollectedComment> candidates) {
		Map<String, CollectedComment> byId = new LinkedHashMap<>();
		for (CollectedComment comment : candidates) {
			byId.putIfAbsent(comment.sourceCommentId(), comment);
		}

		Comparator<CollectedComment> byIdDesc = Comparator
			.comparing((CollectedComment c) -> new BigInteger(c.sourceCommentId()))
			.reversed();

		return byId.values().stream()
			.sorted(byIdDesc)
			.limit(TARGET_COMMENT_COUNT)
			.toList();
	}
}
