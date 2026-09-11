package com.ssafy.pickage.domain.community.collection;

import java.time.Instant;

/**
 * GitHub Search API 응답 한 항목을 정규화한 값(순수 정책 판단용, HTTP 세부사항 없음).
 *
 * <p>{@code public}이다 — {@link SearchPage#items()}가 이 타입의 리스트를 노출하므로
 * {@code SearchPage}만 public이고 이 타입이 package-private이면 외부 호출자가 반환값을
 * 온전히 선언할 수 없다(리뷰에서 발견한 가시성 불일치 수정).
 */
public record SearchResultItem(
	int number,
	String title,
	String state,
	Instant updatedAt,
	String authorLogin,
	boolean authorIsBot,
	boolean locked,
	boolean isPullRequest,
	int commentCount,
	int reactionCount
) {
}
