package com.ssafy.pickage.domain.community.collection;

import java.util.List;

/**
 * 댓글 API 한 page 응답. {@code lastPageNumber}는 {@code Link: rel="last"} 헤더에서 읽은
 * 값이다 — 그 헤더 자체가 없으면(= 이 page가 전부다) 요청한 page 번호를 그대로 쓴다.
 *
 * <p>{@code public}이다 — {@link GitHubIssueCommentsClient#fetchPage}가 이미 public이라
 * 반환 타입도 맞춰야 한다(리뷰에서 발견한 가시성 불일치 수정).
 */
public record CommentsPage(List<CollectedComment> comments, int lastPageNumber) {
}
