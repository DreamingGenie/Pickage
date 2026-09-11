package com.ssafy.pickage.domain.community.collection;

import java.time.Instant;

/**
 * 이슈 댓글 하나(원문 포함, 메모리 전용). 이 record는 저장되지 않는다 — Phase 4(317)가
 * GMS에 넘긴 뒤 버린다. {@code sourceCommentId}는 {@code String}으로 보존한다(구현계획
 * §저장소와 Issue "ID는 십진 문자열로 보존하고 수치 비교한다" — Phase 1의
 * {@code MessagePayload.sourceCommentId}도 이미 String이라 downstream 정밀도 손실을
 * 처음부터 피한다).
 */
public record CollectedComment(
	String sourceCommentId,
	String authorLogin,
	String authorAssociation,
	boolean isBot,
	Instant createdAt,
	String body
) {
}
