package com.ssafy.pickage.domain.community.collection;

import java.time.Instant;
import java.util.List;

/**
 * 선택된 이슈 하나 + 수집한 댓글(원문 포함, 메모리 전용). {@code totalCommentCount}·
 * {@code reactionCount}는 GitHub 원천 값 그대로다 — 수집한 댓글이 100개로 잘려도 이
 * 값은 이슈 전체 댓글 수를 유지한다(구현계획 "수집 댓글 수·고유 참여자 수·저장소 전체
 * 수치로 바꾸지 않는다").
 */
public record CollectedIssue(
	int issueNumber,
	String title,
	String state,
	Instant updatedAt,
	String authorLogin,
	int totalCommentCount,
	int reactionCount,
	CommentCollectionStatus collectionStatus,
	List<CollectedComment> comments,
	List<String> limitations
) {
}
